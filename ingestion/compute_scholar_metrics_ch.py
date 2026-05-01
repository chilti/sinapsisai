"""
Cálculo de Métricas y Trayectorias (Optimizado con ClickHouse)
Este script replica la lógica de compute_scholar_metrics.py pero extrae los metadatos
de los artículos desde la tabla plana de ClickHouse (works_flat).
Reutiliza las funciones de cálculo del script original para mantener equivalencia exacta.
"""
import os
import sys
import json
import argparse
import importlib.util
import numpy as np
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
import unicodedata

import warnings
warnings.filterwarnings('ignore')

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Añadir el path del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Cargar variables de entorno
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env')))

from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client

# Importar helpers puros del script original por ruta absoluta (sin depender de __init__.py)
_THIS_DIR  = Path(os.path.abspath(os.path.dirname(__file__)))
_ORIG_PATH = _THIS_DIR / 'compute_scholar_metrics.py'
_spec      = importlib.util.spec_from_file_location('compute_scholar_metrics', _ORIG_PATH)
_orig      = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_orig)

_get_h_index                = _orig._get_h_index
_clean_keywords             = _orig._clean_keywords
_clean_topics               = _orig._clean_topics
compute_citation_velocity   = _orig.compute_citation_velocity
compute_interdisciplinarity = _orig.compute_interdisciplinarity
aggregate_metrics           = _orig.aggregate_metrics
CURRENT_YEAR                = _orig.CURRENT_YEAR

BASE_PATH = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
CACHE_DIR = BASE_PATH / 'data' / 'cache_ch'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# --- Helpers locales (solo los que NO se importan del script original) ---

def normalize_name(text):
    if not isinstance(text, str): return ""
    return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').upper().strip()

# --- Lógica de ClickHouse ---

def _build_topics_from_row(row):
    """
    Construye la lista de topics en formato dict compatible con compute_interdisciplinarity.
    Prioriza all_topics (array de CH) sobre los campos del topic primario.
    """
    # Preferir all_topics si es un array no vacío (viene de CH como lista de strings o dicts)
    all_t = row.get('all_topics')
    if isinstance(all_t, (list, np.ndarray)) and len(all_t) > 0:
        result = []
        for t in all_t:
            if isinstance(t, dict):
                result.append(t)
            elif t:
                result.append({'topic': str(t), 'domain': row.get('domain_name'), 'field': row.get('field_name'), 'subfield': row.get('subfield_name')})
        return result
    # Fallback al topic primario
    if pd.notnull(row.get('topic_id')):
        return [{
            'topic': row['topic_id'],
            'subfield': row.get('subfield_name'),
            'field': row.get('field_name'),
            'domain': row.get('domain_name'),
        }]
    return []


def fetch_metadata_from_clickhouse(paper_ids):
    """Recupera metadatos de works_flat en ClickHouse y los mapea a las columnas
    esperadas por aggregate_metrics / save_disaggregated_parquets."""
    if not paper_ids:
        return pd.DataFrame()
    clean_ids = [str(pid).split('/')[-1] for pid in paper_ids if pid]

    query = """
    SELECT
        id, doi, title, publication_year AS year, cited_by_count AS citations,
        fwci, percentile AS citation_normalized_percentile,
        is_top_10 AS is_in_top_10_percent, is_top_1 AS is_in_top_1_percent,
        source_id, source_type, is_oa, oa_status,
        topic_id, subfield_name, field_name, domain_name,
        all_topics, keywords, sdgs,
        country_codes,
        referenced_works_count, referenced_works,
        is_retracted, language, type
    FROM works_flat
    WHERE id IN %(ids)s
    """

    df = ch_client.query_df(query, parameters={'ids': clean_ids})
    if df.empty:
        # Devolver DF vacío con paper_id definido para que el LEFT merge no falle
        return pd.DataFrame(columns=['paper_id'])

    # --- Columna 'topics' compatible con compute_interdisciplinarity ---
    df['topics'] = df.apply(_build_topics_from_row, axis=1)

    # --- Alias de conveniencia ---
    df['paper_id']  = df['id']
    df['Title']     = df['title']
    df['Source']    = df['source_id']
    df['has_oa_data'] = 1
    df['ODS']       = df['sdgs']
    df['countries'] = df['country_codes']

    # DOI link
    df['DOI'] = df['doi'].apply(
        lambda d: f"https://doi.org/{d}" if d and str(d).startswith('10.') else d
    )

    # Columnas esperadas por aggregate_metrics que no vienen directas de CH
    for col in ['apc_paid_usd', 'apc_list_usd']:
        if col not in df.columns:
            df[col] = 0.0
    for col in ['counts_by_year', 'indexed_in', 'referenced_works']:
        if col not in df.columns:
            df[col] = [[] for _ in range(len(df))]
    for col in ['journal_is_in_doaj', 'journal_is_core', 'any_repository_has_fulltext']:
        if col not in df.columns:
            df[col] = False
    if 'locations_count' not in df.columns:
        df['locations_count'] = 0
    if 'openalex_url' not in df.columns:
        df['openalex_url'] = df['id'].apply(lambda x: f"https://openalex.org/{x}" if x else None)

    return df

def extract_academic_papers(academic_filter=None, entity_filter=None, source_filter='all'):
    graph_store = Neo4jGraphStore()
    
    if academic_filter:
        query = "MATCH (a:Academic {name: $academic}) OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity) OPTIONAL MATCH (e)-[:PART_OF]->(p_inst:Institution) WITH a, collect(DISTINCT {ent: e.name, inst: CASE WHEN p_inst IS NOT NULL THEN p_inst.name ELSE (CASE WHEN e:Institution THEN e.name ELSE null END) END}) AS affiliations OPTIONAL MATCH (a)-[:AUTHORED]->(p:Paper) RETURN a.name AS academic_name, a.orcid AS orcid, a.scopus_id AS scopus_id, a.is_snii AS is_snii, affiliations, p.id AS paper_id"
        params = {"academic": academic_filter}
    elif entity_filter:
        query = "MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic) OPTIONAL MATCH (e)-[:PART_OF]->(p_inst:Institution) WITH e, a, CASE WHEN p_inst IS NOT NULL THEN p_inst.name ELSE (CASE WHEN e:Institution THEN e.name ELSE null END) END AS inst_name WITH a, collect(DISTINCT {ent: e.name, inst: inst_name}) AS affiliations OPTIONAL MATCH (a)-[:AUTHORED]->(p:Paper) RETURN a.name AS academic_name, a.orcid AS orcid, a.scopus_id AS scopus_id, a.is_snii AS is_snii, affiliations, p.id AS paper_id"
        params = {"entity": entity_filter}
    else:
        query = "MATCH (a:Academic) OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity) OPTIONAL MATCH (e)-[:PART_OF]->(p_inst:Institution) WITH a, collect(DISTINCT {ent: e.name, inst: CASE WHEN p_inst IS NOT NULL THEN p_inst.name ELSE (CASE WHEN e:Institution THEN e.name ELSE null END) END}) AS affiliations OPTIONAL MATCH (a)-[:AUTHORED]->(p:Paper) RETURN a.name AS academic_name, a.orcid AS orcid, a.scopus_id AS scopus_id, a.is_snii AS is_snii, affiliations, p.id AS paper_id"
        params = {}

    with graph_store.driver.session() as session:
        neo_df = pd.DataFrame([dict(r) for r in session.run(query, **params)])
    
    if neo_df.empty:
        yield pd.DataFrame()
        return

    all_paper_ids = neo_df['paper_id'].dropna().unique().tolist()
    batch_size = 50000
    for i in range(0, len(all_paper_ids), batch_size):
        batch_ids = all_paper_ids[i:i+batch_size]
        df_meta = fetch_metadata_from_clickhouse(batch_ids)
        df_chunk = neo_df[neo_df['paper_id'].isin(batch_ids)].merge(df_meta, on='paper_id', how='left')

        # Mapeos finales
        df_chunk['entities']      = df_chunk['affiliations'].apply(
            lambda x: ";".join(list(set([a['ent'] for a in x if a['ent']]))) if isinstance(x, list) else "Sin Entidad"
        )
        df_chunk['institutions']  = df_chunk['affiliations'].apply(
            lambda x: ";".join(list(set([a['inst'] for a in x if a['inst']]))) if isinstance(x, list) else "Sin Institución"
        )
        # 'topics' ya viene correctamente construida desde fetch_metadata_from_clickhouse;
        # si falta (paper sin match en CH), inicializar como lista vacía.
        if 'topics' not in df_chunk.columns:
            df_chunk['topics'] = [[] for _ in range(len(df_chunk))]
        else:
            df_chunk['topics'] = df_chunk['topics'].apply(lambda x: x if isinstance(x, list) else [])

        yield df_chunk

def extract_entity_papers(entity_filter=None, source_filter='all'):
    graph_store = Neo4jGraphStore()
    if entity_filter:
        query = "MATCH (e:Entity {name: $entity}) OPTIONAL MATCH (e)-[:PART_OF]->(p_inst:Institution) WITH e, collect(DISTINCT CASE WHEN p_inst IS NOT NULL THEN p_inst.name ELSE (CASE WHEN e:Institution THEN e.name ELSE null END) END) AS institutions MATCH (e)-[:HAS_PAPER]->(p:Paper) RETURN e.name AS entity_name, institutions, p.id AS paper_id"
        params = {"entity": entity_filter}
    else:
        query = "MATCH (e:Entity)-[:HAS_PAPER]->(p:Paper) OPTIONAL MATCH (e)-[:PART_OF]->(p_inst:Institution) RETURN e.name AS entity_name, collect(DISTINCT CASE WHEN p_inst IS NOT NULL THEN p_inst.name ELSE (CASE WHEN e:Institution THEN e.name ELSE null END) END) AS institutions, p.id AS paper_id"
        params = {}

    with graph_store.driver.session() as session:
        neo_df = pd.DataFrame([dict(r) for r in session.run(query, **params)])

    if neo_df.empty:
        return pd.DataFrame()
    all_paper_ids = neo_df['paper_id'].dropna().unique().tolist()
    df_meta = fetch_metadata_from_clickhouse(all_paper_ids)
    df_final = neo_df.merge(df_meta, on='paper_id', how='left')
    df_final['institutions'] = df_final['institutions'].apply(
        lambda x: ";".join(x) if isinstance(x, list) else "Sin Institución"
    )
    # 'topics' ya viene de fetch_metadata_from_clickhouse; garantizar lista vacía si falta
    if 'topics' not in df_final.columns:
        df_final['topics'] = [[] for _ in range(len(df_final))]
    else:
        df_final['topics'] = df_final['topics'].apply(lambda x: x if isinstance(x, list) else [])
    return df_final

# --- Guardado (versión local que escribe en cache_ch, no en cache) ---

def save_disaggregated_parquets(df, base_name, group_level='academic',
                                academics_map=None, updated_files=None, **_kwargs):
    """
    Guarda parquets en data/cache_ch con estructura jerárquica equivalente al
    save_disaggregated_parquets original, pero apuntando a CACHE_DIR = cache_ch.
    """
    if df is None or df.empty:
        return

    if group_level == 'academic':
        names = list(academics_map.keys()) if academics_map else df['academic_name'].unique().tolist()
        for ac_name in names:
            grp = df[df['academic_name'] == ac_name] if not df.empty else pd.DataFrame(columns=df.columns)
            affiliations = []
            if academics_map and ac_name in academics_map:
                affiliations = academics_map[ac_name]
            elif not grp.empty and 'affiliations' in grp.columns:
                aff_val = grp['affiliations'].iloc[0]
                if isinstance(aff_val, list):
                    affiliations = [(a.get('ent'), a.get('inst')) for a in aff_val if isinstance(a, dict) and a.get('ent')]
            if not affiliations:
                affiliations = [('Sin Entidad', 'SIN INSTITUCIÓN')]
            for ent, inst in affiliations:
                if not inst or str(inst) in ('Sin Institución', 'SIN INSTITUCIÓN', 'None'):
                    inst = 'SIN INSTITUCIÓN'
                if not ent:
                    ent = 'Sin Entidad'
                target_dir = CACHE_DIR / str(inst).replace('/', '_') / str(ent).replace('/', '_') / str(ac_name).replace('/', '_')
                target_dir.mkdir(parents=True, exist_ok=True)
                final_path = target_dir / base_name
                grp.to_parquet(final_path, index=False)
                if updated_files is not None:
                    updated_files.add(str(final_path.absolute()))

    elif group_level == 'entity':
        for ent_name in df['entity_name'].unique().tolist():
            grp = df[df['entity_name'] == ent_name]
            inst_val = grp['institutions'].iloc[0] if 'institutions' in grp.columns and not grp.empty else 'SIN INSTITUCIÓN'
            institutions = [i.strip() for i in str(inst_val).split(';')] if inst_val else ['SIN INSTITUCIÓN']
            for inst in institutions:
                target_dir = CACHE_DIR / str(inst).replace('/', '_') / str(ent_name).replace('/', '_')
                target_dir.mkdir(parents=True, exist_ok=True)
                final_path = target_dir / base_name
                grp.to_parquet(final_path, index=False)
                if updated_files is not None:
                    updated_files.add(str(final_path.absolute()))

def process_and_save(entity_filter=None, academic_filter=None, source_filter='all'):
    print(f"🚀 Iniciando proceso optimizado con ClickHouse (Fuente: {source_filter})...")
    updated_files = set()
    
    df_raw_list = []
    for chunk_df in extract_academic_papers(academic_filter, entity_filter, source_filter):
        if not chunk_df.empty:
            df_raw_list.append(chunk_df)

    if not df_raw_list:
        return print("❌ No se encontraron datos.")
    df_raw = pd.concat(df_raw_list, ignore_index=True).drop_duplicates(subset=['academic_name', 'paper_id'])
    print(f"✅ {len(df_raw)} papers cargados.")

    # Guardar parquets básicos (usando CACHE_DIR de este script, no el original)
    _save_ch = lambda df, name, lvl: save_disaggregated_parquets(
        df, name, lvl, updated_files=updated_files
    )

    _save_ch(df_raw, 'papers_profesor.parquet', 'academic')

    df_inv_tot = aggregate_metrics(df_raw, ['academic_name'])
    _save_ch(df_inv_tot, 'investigador_total.parquet', 'academic')

    # Entidad
    df_inst_raw = extract_entity_papers(entity_filter, source_filter)
    if not df_inst_raw.empty:
        _save_ch(df_inst_raw, 'papers_institucion.parquet', 'entity')
        df_inst_tot = aggregate_metrics(df_inst_raw, ['entity_name'])
        _save_ch(df_inst_tot, 'institucion_total.parquet', 'entity')

    print("✅ Proceso completado exitosamente.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity")
    parser.add_argument("--academic")
    args = parser.parse_args()
    process_and_save(entity_filter=args.entity, academic_filter=args.academic)
