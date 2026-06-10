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
def sync_entity_map(entity=None, institution=None):
    print(f"\n[Fase 1] Sincronizando {TABLE_ENTITY_MAP} desde Neo4j (Firmas)...")
    if entity:
        print(f"   Filtro aplicado: Entidad = '{entity}', Institución = '{institution}'")
        
    gs = Neo4jGraphStore()
    client = ch_client.get_client()
    
    if entity and institution:
        escaped_inst = institution.replace("'", "''")
        escaped_ent = entity.replace("'", "''")
        print(f"   🧹 Limpiando registros antiguos para {entity} en ClickHouse...")
        client.command(f"ALTER TABLE {TABLE_ENTITY_MAP} DELETE WHERE institution = '{escaped_inst}' AND (dependency = '{escaped_ent}' OR subdependency = '{escaped_ent}')")
    else:
        # Truncar tabla para asegurar limpieza total (Regla de Producción No-Agregada)
        client.command(f"TRUNCATE TABLE {TABLE_ENTITY_MAP}")
    
    batch_size = 5000
    skip = 0
    total_synced = 0
    
    if entity and institution:
        query = """
        MATCH (e {name: $entity_name})-[:PART_OF*0..2]->(i:Institution {name: $institution_name})
        MATCH (p:Paper)-[:CREDITED_TO|PRODUCED]->(e)
        OPTIONAL MATCH path = (e)-[:PART_OF*0..2]->(i)
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
        params_base = {"entity_name": entity, "institution_name": institution}
    else:
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
        params_base = {}
    
    while True:
        with gs.driver.session() as session:
            params = params_base.copy()
            params.update({"skip": skip, "limit": batch_size})
            results = session.run(query, **params)
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

                # Helper to safely get string from list
                def safe_str(val):
                    if not val: return ''
                    if isinstance(val, list): return val[0] if val else ''
                    return str(val)

                pid = safe_str(r['paper_id'])
                if '/' in pid and not pid.startswith('http'):
                    pid = normalize_doi(pid)
                
                rows.append({
                    'paper_id': pid,
                    'institution': safe_str(inst_name),
                    'institution_ror': safe_str(r['institution_ror']),
                    'dependency': safe_str(dep_name),
                    'subdependency': safe_str(sub_name),
                    'paper_title': safe_str(r['paper_title']),
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
            try:
                client.insert_df(TABLE_ENTITY_MAP, df)
            except Exception as e:
                print(f"Error inserting batch: {e}")
                for i, row in df.iterrows():
                    for col in df.columns:
                        if isinstance(row[col], list):
                            print(f"List found in column {col} at index {i}: {row[col]}")
                raise e
            total_synced += len(rows)
            print(f"   📥 {total_synced} relaciones de firma sincronizadas...", end="\r")
            skip += batch_size
            if batch_count < batch_size: break
            
    gs.close()
    print(f"\n✅ Fase 1 completada. {total_synced} registros sincronizados.")

# --- Fase 2: Sync Author Map (Capacidad Instalada) ---
def sync_author_map(academic=None, entity=None, institution=None):
    print(f"\n[Fase 2] Sincronizando {TABLE_AUTHOR_MAP} desde Neo4j (Talento)...")
    if academic:
        print(f"   Filtro aplicado: Académico = '{academic}', Institución = '{institution}'")
    elif entity:
        print(f"   Filtro aplicado: Entidad = '{entity}', Institución = '{institution}'")
        
    gs = Neo4jGraphStore()
    client = ch_client.get_client()
    
    if academic and institution:
        escaped_inst = institution.replace("'", "''")
        escaped_acad = academic.replace("'", "''")
        print(f"   🧹 Limpiando registros antiguos para {academic} en ClickHouse...")
        client.command(f"ALTER TABLE {TABLE_AUTHOR_MAP} DELETE WHERE academic_name = '{escaped_acad}' AND institution = '{escaped_inst}'")
    elif entity and institution:
        escaped_inst = institution.replace("'", "''")
        escaped_ent = entity.replace("'", "''")
        print(f"   🧹 Limpiando registros antiguos para {entity} en ClickHouse...")
        client.command(f"ALTER TABLE {TABLE_AUTHOR_MAP} DELETE WHERE institution = '{escaped_inst}' AND (dependency = '{escaped_ent}' OR subdependency = '{escaped_ent}')")
    else:
        # Truncar tabla para limpieza
        client.command(f"TRUNCATE TABLE {TABLE_AUTHOR_MAP}")

    batch_size = 5000
    skip = 0
    total_relations = 0
    
    if academic and institution:
        query = """
        MATCH (a:Person {fullname: $academic_name})-[:AFFILIATED_TO]->(e)-[:PART_OF*0..2]->(i:Institution {name: $institution_name})
        OPTIONAL MATCH path = (e)-[:PART_OF*0..2]->(i)
        WITH a, e, i, [n in nodes(path) | {name: n.name, label: labels(n)[0]}] AS hierarchy
        MATCH (a)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
        RETURN 
            a.fullname AS academic_name,
            a.id AS cvu,
            coalesce(a.orcid, a.orcids) AS orcid,
            coalesce(a.openalex_id, a.openalex_ids) AS author_oa_id,
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
        params_base = {"academic_name": academic, "institution_name": institution}
    elif entity and institution:
        query = """
        MATCH (e {name: $entity_name})-[:PART_OF*0..2]->(i:Institution {name: $institution_name})
        MATCH (a:Person)-[:AFFILIATED_TO]->(e)
        OPTIONAL MATCH path = (e)-[:PART_OF*0..2]->(i)
        WITH a, e, i, [n in nodes(path) | {name: n.name, label: labels(n)[0]}] AS hierarchy
        MATCH (a)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
        RETURN 
            a.fullname AS academic_name,
            a.id AS cvu,
            coalesce(a.orcid, a.orcids) AS orcid,
            coalesce(a.openalex_id, a.openalex_ids) AS author_oa_id,
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
        params_base = {"entity_name": entity, "institution_name": institution}
    else:
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
            coalesce(a.orcid, a.orcids) AS orcid,
            coalesce(a.openalex_id, a.openalex_ids) AS author_oa_id,
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
        params_base = {}

    while True:
        with gs.driver.session() as session:
            params = params_base.copy()
            params.update({"skip": skip, "limit": batch_size})
            results = session.run(query, **params)
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

                # Helper to safely get string from list
                def safe_str(val):
                    if not val: return ''
                    if isinstance(val, list): return val[0] if val else ''
                    return str(val)

                p_id = normalize_paper_id(r['paper_id']) or safe_str(r['paper_id'])
                if '/' in p_id and not p_id.startswith('http'):
                    p_id = normalize_doi(p_id)
                
                rows.append({
                    'paper_id': p_id,
                    'academic_name': safe_str(r['academic_name']),
                    'cvu': safe_str(r['cvu']),
                    'orcid': safe_str(r['orcid']),
                    'openalex_id': safe_str(r['author_oa_id']),
                    'institution': safe_str(inst_name),
                    'institution_ror': '',
                    'dependency': safe_str(dep_name),
                    'subdependency': safe_str(sub_name),
                    'paper_title': safe_str(r.get('title')),
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
                
            try:
                client.insert_df(TABLE_AUTHOR_MAP, pd.DataFrame(rows))
            except Exception as e:
                print(f"Error inserting batch: {e}")
                df_auth = pd.DataFrame(rows)
                for i, row in df_auth.iterrows():
                    for col in df_auth.columns:
                        if isinstance(row[col], list):
                            print(f"List found in column {col} at index {i}: {row[col]}")
                raise e
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
    
    print("📥 Ejecutando inserción incremental en ClickHouse (preserva registros existentes)...")
    try:
        client.command(query)
        res = client.query("SELECT count() FROM " + TABLE_WORKS_ALL)
        count = res.result_rows[0][0]
        print(f"✅ Fase 3 completada. Total actual en {TABLE_WORKS_ALL}: {count:,} papers.")
        
        # --- Preservar embeddings desde embeddings_cache ---
        # Actualizar embedding_nomic/specter sólo para los que no los tienen aún
        print("🔗 Sincronizando embeddings desde embeddings_cache hacia works_academic_all...")
        emb_query = f"""
        ALTER TABLE {TABLE_WORKS_ALL} UPDATE
            embedding_specter = ec.embedding_specter2,
            embedding_nomic   = ec.embedding_specter2  -- placeholder hasta tener Nomic en CH
        FROM (SELECT id, embedding_specter2 FROM embeddings_cache WHERE length(embedding_specter2) > 0) AS ec
        WHERE {TABLE_WORKS_ALL}.id = ec.id
          AND length({TABLE_WORKS_ALL}.embedding_specter) = 0
        """
        try:
            client.command(emb_query)
            r_emb = client.query(f"SELECT count() FROM {TABLE_WORKS_ALL} WHERE length(embedding_specter) > 0")
            print(f"   ✅ {r_emb.result_rows[0][0]:,} artículos con embedding_specter en {TABLE_WORKS_ALL}.")
        except Exception as e_emb:
            print(f"   ⚠️  No se pudo sincronizar embeddings (puede requerir ALTER TABLE): {e_emb}")
            
    except Exception as e:
        print(f"❌ Error en Fase 3: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline de sincronización analítica Neo4j -> ClickHouse")
    parser.add_argument("--phase", choices=['maps', 'works', 'all'], default='all', help="Fase a ejecutar")
    parser.add_argument("--academic", type=str, help="Sincronizar solo un académico específico")
    parser.add_argument("--entity", type=str, help="Sincronizar solo una dependencia/subdependencia específica")
    parser.add_argument("--institution", type=str, help="Institución padre obligatoria si se usa --academic o --entity")
    args = parser.parse_args()
    
    if args.academic and not args.institution:
        print("❌ Error: Debes proveer --institution si usas --academic para evitar problemas de homónimos.")
        sys.exit(1)
        
    if args.entity and not args.institution:
        print("❌ Error: Debes proveer --institution si usas --entity para identificar unívocamente la dependencia.")
        sys.exit(1)
        
    if args.academic and args.entity:
        print("❌ Error: No puedes usar --academic y --entity al mismo tiempo.")
        sys.exit(1)
    
    if args.phase in ['maps', 'all']:
        if not args.academic:
            sync_entity_map(entity=args.entity, institution=args.institution)
        sync_author_map(academic=args.academic, entity=args.entity, institution=args.institution)
        
    if args.phase in ['works', 'all']:
        materialize_works()
    
    print("\n🎉 Pipeline finalizado con éxito.")
