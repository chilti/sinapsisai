"""
sync_analytics_pipeline.py
==========================
Orquestador unificado para sincronizar el pipeline de métricas en ClickHouse.

Fases:
  1. Sync Paper Entity Map: Neo4j (CREDITED_TO) -> ClickHouse (paper_entity_map)
  2. Sync Paper Author Map: SNII Excel + Neo4j (AUTHORED) -> ClickHouse (paper_author_map)
  3. Materialize Works: ClickHouse (works_flat + works_seed_mexico) -> ClickHouse (works_academic_all)

Uso:
  python ingestion/sync_analytics_pipeline.py --all
  python ingestion/sync_analytics_pipeline.py --phase maps
  python ingestion/sync_analytics_pipeline.py --phase works
"""

import os
import sys
import argparse
import pandas as pd
import re
from pathlib import Path
from dotenv import load_dotenv

# Configuración de rutas
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))
load_dotenv(str(_THIS.parent / '.env'))

from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client

# --- Constantes ---
TABLE_ENTITY_MAP = 'paper_entity_map'
TABLE_AUTHOR_MAP = 'paper_author_map'
TABLE_WORKS_ALL  = 'works_academic_all'

SNII_EXCEL = 'data/Investigadores_vigentes_2025.xlsx'
SNII_SHEET = "4T_2025 (44,794)"

def normalize_doi(doi: str) -> str:
    if not doi: return None
    s = str(doi).lower().strip()
    return s.replace('https://doi.org/', '').replace('http://doi.org/', '').replace('doi.org/', '')

def normalize_paper_id(pid: str) -> str:
    if not pid: return None
    s = str(pid).strip()
    if re.match(r'^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$', s): return None
    short = s.rstrip('/').split('/')[-1].upper()
    if short.startswith('W') and short[1:].isdigit():
        return f'https://openalex.org/{short}'
    if 'openalex.org/W' in s:
        return s.replace('http://', 'https://')
    return None# --- Fase 1: Sync Entity Map (Producción Institucional) ---
def sync_entity_map():
    print(f"\n[Fase 1] Sincronizando {TABLE_ENTITY_MAP} desde Neo4j (Firmas)...")
    gs = Neo4jGraphStore()
    client = ch_client.get_client()
    
    # Truncar tabla para asegurar limpieza total (Regla de Producción No-Agregada)
    client.command(f"TRUNCATE TABLE {TABLE_ENTITY_MAP}")
    
    batch_size = 5000
    skip = 0
    total_synced = 0
    
    # Query que respeta la jerarquía estricta
    query = """
    MATCH (p:Paper)-[:CREDITED_TO|PRODUCED]->(e)
    WHERE e:Institution OR e:Dependency OR e:Subdependency
    OPTIONAL MATCH path = (e)-[:PART_OF*0..2]->(i:Institution)
    WITH p, e, i, [n in nodes(path) | {name: n.name, label: labels(n)[0]}] AS hierarchy
    RETURN 
        p.id AS paper_id,
        p.title AS paper_title,
        p.year AS paper_year,
        p.citations AS citations,
        coalesce(i.ror, i.id) AS institution_ror,
        hierarchy,
        p.sources AS sources,
        p.openalex_id IS NOT NULL AS is_openalex
    SKIP $skip LIMIT $limit
    """
    
    while True:
        with gs.driver.session() as session:
            results = session.run(query, skip=skip, limit=batch_size)
            rows = []
            batch_count = 0
            for r in results:
                batch_count += 1
                h_list = r['hierarchy'] or []
                
                # Mapeo de jerarquía (de arriba hacia abajo)
                inst_name = ""
                dep_name = "SIN INFORMACIÓN"
                sub_name = "SIN INFORMACIÓN"
                
                for item in reversed(h_list):
                    if item['label'] == 'Institution': inst_name = item['name']
                    elif item['label'] == 'Dependency': dep_name = item['name']
                    elif item['label'] == 'Subdependency': sub_name = item['name']

                pid = r['paper_id']
                if '/' in pid and not pid.startswith('http'):
                    pid = normalize_doi(pid)
                
                rows.append({
                    'paper_id': pid,
                    'institution': inst_name,
                    'institution_ror': r['institution_ror'] or '',
                    'dependency': dep_name,
                    'subdependency': sub_name,
                    'paper_title': r['paper_title'] or '',
                    'paper_year': int(r['paper_year'] or 0),
                    'citations': int(r['citations'] or 0),
                    'is_wos': 1 if 'WoS' in (r['sources'] or []) else 0,
                    'is_scopus': 1 if 'Scopus' in (r['sources'] or []) else 0,
                    'is_pubmed': 1 if 'PubMed' in (r['sources'] or []) else 0,
                    'is_openalex': 1 if r['is_openalex'] else 0,
                    'is_doaj': 0,
                    'is_semantic_scholar': 0,
                    'is_dimensions': 1 if 'Dimensions' in (r['sources'] or []) else 0,
                    'is_lens': 0,
                    'source': 'Neo4j CREDITED_TO'
                })
            
            if not rows:
                break
                
            df = pd.DataFrame(rows)
            client.insert_df(TABLE_ENTITY_MAP, df)
            total_synced += len(rows)
            print(f"   📥 {total_synced} relaciones de firma sincronizadas...", end="\r")
            skip += batch_size
            if batch_count < batch_size: break
            
    gs.close()
    print(f"\n✅ Fase 1 completada. {total_synced} registros sincronizados.")

# --- Fase 2: Sync Author Map (Capacidad Instalada) ---
def sync_author_map():
    print(f"\n[Fase 2] Sincronizando {TABLE_AUTHOR_MAP} desde Neo4j (Talento)...")
    gs = Neo4jGraphStore()
    client = ch_client.get_client()
    
    # Truncar tabla para limpieza
    client.command(f"TRUNCATE TABLE {TABLE_AUTHOR_MAP}")

    batch_size = 5000
    skip = 0
    total_relations = 0
    
    # Query que busca por Afiliación en el Grafo (Independiente de Excel)
    query = """
    MATCH (a:Person)-[:AFFILIATED_TO]->(e)
    WHERE e:Institution OR e:Dependency OR e:Subdependency
    OPTIONAL MATCH path = (e)-[:PART_OF*0..2]->(i:Institution)
    WITH a, e, i, [n in nodes(path) | {name: n.name, label: labels(n)[0]}] AS hierarchy
    MATCH (a)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
    RETURN 
        a.fullname AS academic_name,
        a.id AS cvu,
        a.orcid AS orcid,
        a.openalex_id AS author_oa_id,
        p.id AS paper_id,
        p.title AS title,
        p.year AS year,
        p.citations AS citations,
        p.sources AS sources,
        p.openalex_id IS NOT NULL AS is_openalex,
        hierarchy,
        a.is_snii AS is_snii
    SKIP $skip LIMIT $limit
    """

    while True:
        with gs.driver.session() as session:
            results = session.run(query, skip=skip, limit=batch_size)
            rows = []
            batch_count = 0
            for r in results:
                batch_count += 1
                h_list = r['hierarchy'] or []
                
                # Mapeo de jerarquía (de arriba hacia abajo)
                inst_name = ""
                dep_name = "SIN INFORMACIÓN"
                sub_name = "SIN INFORMACIÓN"
                
                for item in reversed(h_list):
                    if item['label'] == 'Institution': inst_name = item['name']
                    elif item['label'] == 'Dependency': dep_name = item['name']
                    elif item['label'] == 'Subdependency': sub_name = item['name']

                p_id = normalize_paper_id(r['paper_id']) or r['paper_id']
                if '/' in p_id and not p_id.startswith('http'):
                    p_id = normalize_doi(p_id)
                
                rows.append({
                    'paper_id': p_id,
                    'academic_name': r['academic_name'],
                    'cvu': r['cvu'] or '',
                    'orcid': r['orcid'] or '',
                    'openalex_id': r['author_oa_id'] or '',
                    'institution': inst_name,
                    'institution_ror': '',
                    'dependency': dep_name,
                    'subdependency': sub_name,
                    'paper_title': r.get('title') or '',
                    'paper_year': int(r.get('year') or 0),
                    'citations': int(r.get('citations') or 0),
                    'is_wos': 1 if 'WoS' in (r['sources'] or []) else 0,
                    'is_scopus': 1 if 'Scopus' in (r['sources'] or []) else 0,
                    'is_pubmed': 1 if 'PubMed' in (r['sources'] or []) else 0,
                    'is_openalex': 1 if r['is_openalex'] else 0,
                    'is_doaj': 0,
                    'is_semantic_scholar': 0,
                    'is_dimensions': 1 if 'Dimensions' in (r['sources'] or []) else 0,
                    'is_lens': 0,
                    'is_snii': 1 if r['is_snii'] else 0,
                    'source': 'Neo4j Affiliation Sync'
                })
            
            if not rows:
                break
                
            client.insert_df(TABLE_AUTHOR_MAP, pd.DataFrame(rows))
            total_relations += len(rows)
            print(f"   📥 {total_relations} relaciones talento-paper sincronizadas...", end="\r")
            skip += batch_size
            if batch_count < batch_size: break
            
    gs.close()
    print(f"\n✅ Fase 2 completada. {total_relations} relaciones sincronizadas.")

# --- Fase 3: Materialize Works ---
def materialize_works():
    print(f"\n[Fase 3] Materializando {TABLE_WORKS_ALL} desde works_flat y works_seed_mexico...")
    client = ch_client.get_client()
    
    # Lista de columnas con CAST para asegurar compatibilidad de tipos
    # Mismatch detectados: publication_year, cited_by_count, is_oa, etc.
    cols_flat = [
        "id", "raw_data", "doi", "title", "CAST(publication_year AS Int32) AS publication_year", 
        "CAST(cited_by_count AS Int64) AS cited_by_count", "CAST(is_oa AS String) AS is_oa", 
        "CAST(type AS String) AS type", "updated_date", "is_xpac", "CAST(source_id AS String) AS source_id", 
        "author_names", "institution_rors", "institution_names", "primary_topic_id", "institution_ids", 
        "subfield", "field", "domain", "topic", "CAST(language AS String) AS language", 
        "CAST(oa_status AS String) AS oa_status", "fwci", "percentile", "is_top_10", "is_top_1", 
        "country_code", "CAST(source_type AS String) AS source_type", "sdg_ids", "awards", "concept_ids", 
        "all_country_codes", "apc_paid_usd", "apc_list_usd", "counts_by_year", "is_doaj_indexed", 
        "is_doaj_journal", "is_core_journal", "is_retracted", "has_repository_fulltext", "license", 
        "referenced_works_count", "keywords", "CAST(sdgs AS Array(String)) AS sdgs", 
        "journal_is_in_doaj", "journal_is_core", "any_repository_has_fulltext"
    ]
    
    cols_target = [
        "id", "raw_data", "doi", "title", "publication_year", "cited_by_count", "is_oa", "type", 
        "updated_date", "is_xpac", "source_id", "author_names", "institution_rors", "institution_names", 
        "primary_topic_id", "institution_ids", "subfield", "field", "domain", "topic", "language", 
        "oa_status", "fwci", "percentile", "is_top_10", "is_top_1", "country_code", "source_type", 
        "sdg_ids", "awards", "concept_ids", "all_country_codes", "apc_paid_usd", "apc_list_usd", 
        "counts_by_year", "is_doaj_indexed", "is_doaj_journal", "is_core_journal", "is_retracted", 
        "has_repository_fulltext", "license", "referenced_works_count", "keywords", "sdgs", 
        "journal_is_in_doaj", "journal_is_core", "any_repository_has_fulltext"
    ]

    cols_flat_str = ", ".join(cols_flat)
    cols_target_str = ", ".join(cols_target)
    
    query = f"""
    INSERT INTO {TABLE_WORKS_ALL} ({cols_target_str})
    SELECT {cols_target_str} FROM (
        SELECT {cols_flat_str} FROM works_flat
        UNION ALL
        SELECT {cols_flat_str} FROM works_seed_mexico
    ) AS combined
    WHERE (
        combined.id IN (SELECT paper_id FROM {TABLE_AUTHOR_MAP} WHERE paper_id LIKE 'https://%%')
        OR
        combined.id IN (SELECT 'https://openalex.org/' || paper_id FROM {TABLE_AUTHOR_MAP} WHERE paper_id LIKE 'W%%')
        OR
        lower(replaceOne(combined.doi, 'https://doi.org/', '')) IN (SELECT lower(paper_id) FROM {TABLE_AUTHOR_MAP} WHERE paper_id NOT LIKE 'W%%' AND paper_id NOT LIKE 'https://%%')
        OR
        combined.id IN (SELECT paper_id FROM {TABLE_ENTITY_MAP} WHERE paper_id LIKE 'https://%%')
        OR
        combined.id IN (SELECT 'https://openalex.org/' || paper_id FROM {TABLE_ENTITY_MAP} WHERE paper_id LIKE 'W%%')
        OR
        lower(replaceOne(combined.doi, 'https://doi.org/', '')) IN (SELECT lower(paper_id) FROM {TABLE_ENTITY_MAP} WHERE paper_id NOT LIKE 'W%%' AND paper_id NOT LIKE 'https://%%')
    )
    AND combined.id NOT IN (SELECT id FROM {TABLE_WORKS_ALL})
    """
    
    print("📥 Ejecutando inserción masiva en ClickHouse...")
    try:
        client.command(query)
        # Verificar cuántos hay ahora
        res = client.query("SELECT count() FROM " + TABLE_WORKS_ALL)
        count = res.result_rows[0][0]
        print(f"✅ Fase 3 completada. Total actual en {TABLE_WORKS_ALL}: {count:,} papers.")
    except Exception as e:
        print(f"❌ Error en Fase 3: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline de sincronización analítica Neo4j -> ClickHouse")
    parser.add_argument("--phase", choices=['maps', 'works', 'all'], default='all', help="Fase a ejecutar")
    args = parser.parse_args()
    
    if args.phase in ['maps', 'all']:
        sync_entity_map()
        sync_author_map()
        
    if args.phase in ['works', 'all']:
        materialize_works()
    
    print("\n🎉 Pipeline finalizado con éxito.")
