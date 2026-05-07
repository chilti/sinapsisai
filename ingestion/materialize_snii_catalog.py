"""
materialize_snii_catalog.py
==========================
Genera la tabla maestra de ClickHouse unificando la identidad SNII (Neo4j)
con la jerarquía institucional de 3 niveles y sus publicaciones.
"""
import os
import sys
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

# Configuración de rutas
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))
load_dotenv(str(_THIS.parent / '.env'))

from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client

TABLE_NAME = 'snii_catalog_materialized'

def materialize(reset: bool = False):
    print(f"🚀 Iniciando materialización del catálogo SNII desde Neo4j...")
    
    gs = Neo4jGraphStore()
    client = ch_client.get_client()

    if reset:
        print(f"⚠️ Reseteando tabla {TABLE_NAME}...")
        client.command(f"DROP TABLE IF EXISTS {TABLE_NAME}")

    # DDL con soporte para jerarquía de 3 niveles y ROR
    DDL = f"""
    CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
        cvu               String,
        academic_name     String,
        orcid             String,
        openalex_id       String,
        institution       String,
        institution_ror   String,
        dependency        String,
        subdependency     String,
        paper_id          String,
        paper_title       String,
        paper_year        UInt16,
        citations         UInt32,
        audit_verdict     String
    )
    ENGINE = ReplacingMergeTree()
    ORDER BY (institution, dependency, cvu, paper_id)
    """
    client.command(DDL)

    # Consulta maestra en Neo4j:
    # Busca Académicos -> sus Jerarquías -> sus Papers
    # Nota: Usamos OPTIONAL MATCH para los papers por si hay investigadores sin obras aún
    query = """
    MATCH (a:Academic)
    MATCH (a)-[:AFFILIATED_TO]->(s:Subdependency)
    MATCH (s)-[:CHILD_OF]->(d:Dependency)
    MATCH (d)-[:CHILD_OF]->(i:Institution)
    
    OPTIONAL MATCH (a)-[:AUTHORED]->(p:Paper)
    
    RETURN 
        a.cvu as cvu, 
        a.name as academic_name, 
        a.orcid as orcid, 
        a.openalex_id as openalex_id,
        i.name as institution,
        i.ror as institution_ror,
        d.name as dependency,
        s.name as subdependency,
        p.id as paper_id,
        p.title as paper_title,
        p.year as paper_year,
        p.citations as citations,
        a.audit_verdict as audit_verdict
    """

    print("📡 Consultando Neo4j (esto puede tardar unos minutos)...")
    with gs.driver.session() as session:
        result = session.run(query)
        
        rows = []
        count = 0
        total_relations = 0
        
        for r in result:
            rows.append({
                'cvu': r['cvu'] or '',
                'academic_name': r['academic_name'] or '',
                'orcid': r['orcid'] or '',
                'openalex_id': r['openalex_id'] or '',
                'institution': r['institution'] or 'INSTITUCIÓN DESCONOCIDA',
                'institution_ror': r['institution_ror'] or '',
                'dependency': r['dependency'] or 'SIN INFORMACIÓN',
                'subdependency': r['subdependency'] or 'SIN INFORMACIÓN',
                'paper_id': r['paper_id'] or '',
                'paper_title': r['paper_title'] or '',
                'paper_year': int(r['paper_year'] or 0),
                'citations': int(r['citations'] or 0),
                'audit_verdict': r['audit_verdict'] or 'UNVERIFIED'
            })
            
            count += 1
            if r['paper_id']: total_relations += 1
            
            # Insertar en bloques de 10,000 para no saturar memoria
            if len(rows) >= 10000:
                client.insert_df(TABLE_NAME, pd.DataFrame(rows))
                rows = []
                print(f"   📥 Insertados {count} registros...")

        # Insertar remanente
        if rows:
            client.insert_df(TABLE_NAME, pd.DataFrame(rows))

    print(f"✅ Finalizado.")
    print(f"📊 Total registros procesados: {count}")
    print(f"📄 Total relaciones Paper-Autor: {total_relations}")
    
    gs.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--reset', action='store_true', help="Borrar y recrear la tabla")
    args = parser.parse_args()
    materialize(reset=args.reset)
