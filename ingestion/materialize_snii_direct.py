"""
materialize_snii_direct.py
==========================
Materialización directa de Investigadores SNII a ClickHouse sin pasar por Neo4j.
Usa la lógica de consulta a OpenAlex Local para máxima velocidad.
"""
import os
import sys
import json
import pandas as pd
from pathlib import Path
from tqdm import tqdm
from dotenv import load_dotenv

# Configuración de rutas
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))
load_dotenv(str(_THIS.parent / '.env'))

from database.clickhouse_db import ch_client
from SNII.ingest_snii_apis import obtener_metadatos_de_openalex_autor

TABLE_NAME = 'paper_author_map' # O la tabla que prefieras para el dashboard

def materialize(limit_rors=None):
    print(f"🚀 Iniciando materialización directa Excel -> OpenAlex -> ClickHouse")
    
    # 1. Cargar auditoría (fuente de verdad de IDs)
    AUDIT_PATH = 'data/snii_full_identity_audit.json'
    if not os.path.exists(AUDIT_PATH):
        print(f"❌ No se encontró {AUDIT_PATH}")
        return

    with open(AUDIT_PATH, 'r', encoding='utf-8') as f:
        registros = json.load(f)
    
    # Filtrar solo los confirmados que tengan OpenAlex ID
    confirmados = [r for r in registros if r.get('audit', {}).get('verdict') == "CONFIRMED" and r.get('matched_openalex_id')]
    print(f"✅ Investigadores confirmados con OpenAlex ID: {len(confirmados)}")

    # 2. Preparar ClickHouse
    client = ch_client.get_client()
    
    # DDL simplificado para el dashboard
    DDL = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        paper_id          String,
        academic_name     String,
        cvu               String,
        orcid             String,
        openalex_id       String,
        institution       String,
        dependency        String,
        subdependency     String,
        paper_title       String,
        paper_year        UInt16,
        citations         UInt32,
        is_wos            UInt8,
        is_scopus         UInt8,
        is_pubmed         UInt8,
        is_openalex       UInt8,
        is_doaj           UInt8,
        is_semantic_scholar UInt8,
        is_dimensions     UInt8,
        is_lens           UInt8,
        is_snii           UInt8,
        source            String
    )
    ENGINE = ReplacingMergeTree()
    ORDER BY (institution, paper_id, cvu)
    """
    client.command(DDL)

    rows_to_insert = []
    total_papers = 0
    
    # 3. Procesar cada investigador
    # Usamos tqdm para ver el progreso real
    for i, data in enumerate(tqdm(confirmados, desc="Procesando investigadores")):
        oa_id = data.get('matched_openalex_id')
        name = data.get('snii_author')
        cvu = data.get('cvu')
        orcid = data.get('matched_orcid', '')
        
        # Jerarquía del registro
        inst = data.get('snii_institution', 'INSTITUCIÓN DESCONOCIDA')
        dep = data.get('snii_dependency', 'SIN INFORMACIÓN')
        sub = data.get('snii_subdependency', 'SIN INFORMACIÓN')

        # Obtener trabajos usando la lógica optimizada (Intentará Local primero)
        # force_local=True para no saturar la API oficial
        works_dict = obtener_metadatos_de_openalex_autor(oa_id, force_local=True)
        
        for doi, w in works_dict.items():
            # Detección de bases de indización
            oa_ids_dict = w.get('ids', {})
            
            rows_to_insert.append({
                'paper_id': doi,
                'academic_name': name,
                'cvu': str(cvu),
                'orcid': orcid,
                'openalex_id': oa_id,
                'institution': inst,
                'dependency': dep,
                'subdependency': sub,
                'paper_title': w.get('Title', ''),
                'paper_year': int(w.get('Year', 0)),
                'citations': int(w.get('Cited_by', 0)),
                'is_wos': 1 if 'wos' in oa_ids_dict else 0,
                'is_scopus': 1 if 'scopus' in oa_ids_dict else 0,
                'is_pubmed': 1 if 'pmid' in oa_ids_dict else 0,
                'is_openalex': 1,
                'is_doaj': 1 if w.get('is_oa') and 'doaj' in str(w.get('locations', [])).lower() else 0,
                'is_semantic_scholar': 1 if 'mag' in oa_ids_dict else 0,
                'is_dimensions': 1 if 'mag' in oa_ids_dict else 0,
                'is_lens': 1 if 'mag' in oa_ids_dict or 'pmid' in oa_ids_dict else 0,
                'is_snii': 1,
                'source': 'SNII_Direct_Materialization'
            })
            total_papers += 1

        # Insertar en bloques para eficiencia
        if len(rows_to_insert) >= 5000:
            client.insert_df(TABLE_NAME, pd.DataFrame(rows_to_insert))
            rows_to_insert = []

    # Insertar remanente
    if rows_to_insert:
        client.insert_df(TABLE_NAME, pd.DataFrame(rows_to_insert))

    print(f"\n✅ Finalizado.")
    print(f"📊 Investigadores procesados: {len(confirmados)}")
    print(f"📄 Total de registros insertados en ClickHouse: {total_papers}")

if __name__ == "__main__":
    materialize()
