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
CURRENT_YEAR                = _orig.CURRENT_YEAR

BASE_PATH = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
CACHE_DIR = BASE_PATH / 'data' / 'cache_ch'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# --- Helpers locales (solo los que NO se importan del script original) ---

def normalize_name(text):
    if not isinstance(text, str): return ""
    return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').upper().strip()


def _ensure_ch_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Garantiza que el DataFrame tenga todas las columnas que aggregate_metrics
    del script original accede incondicionalmente (tras el rename de agg_funcs).
    Si una columna no existe se agrega con valor neutro.
    """
    # Columnas numéricas — NaN para que los promedios sean correctos
    for col in ['fwci', 'citation_normalized_percentile',
                'is_in_top_10_percent', 'is_in_top_1_percent',
                'citations']:
        if col not in df.columns:
            df[col] = np.nan

    # Columnas de OA — 0/closed como fallback conservador
    if 'is_oa' not in df.columns:
        df['is_oa'] = 0
    if 'oa_status' not in df.columns:
        df['oa_status'] = 'closed'

    # Columnas de listas — lista vacía por fila
    for col in ['counts_by_year', 'indexed_in']:
        if col not in df.columns:
            df[col] = [[] for _ in range(len(df))]

    # Columnas booleanas / enteras
    for col in ['is_retracted', 'journal_is_in_doaj', 'journal_is_core',
                'any_repository_has_fulltext']:
        if col not in df.columns:
            df[col] = 0

    # Columnas de texto
    if 'language' not in df.columns:
        df['language'] = 'en'
    if 'license' not in df.columns:
        df['license'] = None
    if 'has_oa_data' not in df.columns:
        df['has_oa_data'] = 0
    if 'openalex_url' not in df.columns:
        df['openalex_url'] = None

    # Columnas de costos APC
    for col in ['apc_paid_usd', 'apc_list_usd']:
        if col not in df.columns:
            df[col] = 0.0

    return df


def aggregate_metrics(df_papers: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    """Wrapper de aggregate_metrics del script original que garantiza
    la existencia de todas las columnas esperadas antes de delegar."""
    df_papers = _ensure_ch_columns(df_papers)
    return _orig.aggregate_metrics(df_papers, group_cols)

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
    """Recupera metadatos de works_flat en ClickHouse.

    Neo4j puede guardar como paper_id tanto DOIs ('10.xxx') como OpenAlex IDs ('Wxxxxxxx').
    Se clasifican y se consultan las dos columnas correspondientes en works_flat.
    """
    import re
    if not paper_ids:
        return pd.DataFrame(columns=['paper_id'])

    _oa_re = re.compile(r'^W\d+$', re.IGNORECASE)
    oa_ids, dois = [], []
    key_to_orig: dict = {}   # clave normalizada -> paper_id original de Neo4j

    for pid in paper_ids:
        if not pid:
            continue
        short = str(pid).rstrip('/').split('/')[-1]
        if _oa_re.match(short):
            k = short.upper()
            oa_ids.append(k)
            key_to_orig[k] = pid
        else:
            doi_clean = (str(pid)
                         .replace('https://doi.org/', '')
                         .replace('http://doi.org/', '')
                         .lower().strip('/'))
            if doi_clean.startswith('10.'):
                dois.append(doi_clean)
                key_to_orig[doi_clean] = pid

    if not oa_ids and not dois:
        return pd.DataFrame(columns=['paper_id'])

    conditions, params = [], {}
    if oa_ids:
        conditions.append('id IN %(oa_ids)s')
        params['oa_ids'] = oa_ids
    if dois:
        conditions.append('doi IN %(dois)s')
        # works_flat almacena DOIs como URL completa: 'https://doi.org/10.xxxx'
        params['dois'] = [f'https://doi.org/{d}' for d in dois]

    query = f"""
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
    WHERE {' OR '.join(conditions)}
    """

    df = ch_client.query_df(query, parameters=params)
    if df.empty:
        return pd.DataFrame(columns=['paper_id'])

    # --- Resolver paper_id al valor original de Neo4j ---
    df['doi_norm'] = df['doi'].apply(
        lambda d: str(d).replace('https://doi.org/', '').replace('http://doi.org/', '')
                        .lower().strip('/') if d else None
    )

    def _resolve_pid(row):
        oa = str(row['id']).upper() if row['id'] else None
        if oa and oa in key_to_orig:
            return key_to_orig[oa]
        doi = row['doi_norm']
        if doi and doi in key_to_orig:
            return key_to_orig[doi]
        return doi or row['id']

    df['paper_id'] = df.apply(_resolve_pid, axis=1)
    df = df.drop_duplicates(subset=['paper_id'])

    # --- Columna topics ---
    df['topics'] = df.apply(_build_topics_from_row, axis=1)

    # --- Alias de conveniencia ---
    df['Title']       = df['title']
    df['Source']      = df['source_id']
    df['has_oa_data'] = 1
    df['ODS']         = df['sdgs']
    df['countries']   = df['country_codes']
    df['DOI']         = df['doi'].apply(
        lambda d: f"https://doi.org/{d}" if d and str(d).startswith('10.') else d
    )
    df['Link']        = df['DOI']
    df['openalex_url'] = df['id'].apply(
        lambda x: f"https://openalex.org/{x}" if x else None
    )

    # Defaults seguros para columnas opcionales
    for col in ['apc_paid_usd', 'apc_list_usd']:
        if col not in df.columns:
            df[col] = 0.0
    for col in ['counts_by_year', 'indexed_in']:
        if col not in df.columns:
            df[col] = [[] for _ in range(len(df))]
    for col in ['journal_is_in_doaj', 'journal_is_core', 'any_repository_has_fulltext']:
        if col not in df.columns:
            df[col] = False
    if 'locations_count' not in df.columns:
        df['locations_count'] = 0

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

        # Garantizar columnas requeridas por aggregate_metrics tras el LEFT join
        # (ausentes cuando ningún paper del batch tiene match en CH)
        if 'has_oa_data' not in df_chunk.columns:
            df_chunk['has_oa_data'] = 0
        else:
            df_chunk['has_oa_data'] = df_chunk['has_oa_data'].fillna(0).astype(int)
        if 'openalex_url' not in df_chunk.columns:
            df_chunk['openalex_url'] = None

        # Mapeos finales
        df_chunk['entities']      = df_chunk['affiliations'].apply(
            lambda x: ";".join(list(set([a['ent'] for a in x if a['ent']]))) if isinstance(x, list) else "Sin Entidad"
        )
        df_chunk['institutions']  = df_chunk['affiliations'].apply(
            lambda x: ";".join(list(set([a['inst'] for a in x if a['inst']]))) if isinstance(x, list) else "Sin Institución"
        )
        # 'topics' ya viene de fetch_metadata_from_clickhouse;
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

    # Garantizar columnas requeridas por aggregate_metrics tras el LEFT join
    if 'has_oa_data' not in df_final.columns:
        df_final['has_oa_data'] = 0
    else:
        df_final['has_oa_data'] = df_final['has_oa_data'].fillna(0).astype(int)
    if 'openalex_url' not in df_final.columns:
        df_final['openalex_url'] = None

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
    from collections import Counter
    print(f"🚀 Iniciando proceso optimizado con ClickHouse (Fuente: {source_filter})...")
    updated_files = set()

    # ── 1. Extracción de papers por académico ──────────────────────────────────
    df_raw_list = []
    for chunk_df in extract_academic_papers(academic_filter, entity_filter, source_filter):
        if not chunk_df.empty:
            df_raw_list.append(chunk_df)

    if not df_raw_list:
        return print("❌ No se encontraron datos.")
    df_raw = pd.concat(df_raw_list, ignore_index=True).drop_duplicates(subset=['academic_name', 'paper_id'])
    print(f"✅ {len(df_raw)} papers cargados.")

    # academics_map: {nombre -> [(ent, inst), ...]}
    academics_map = {}
    for _, row in df_raw[['academic_name', 'affiliations']].drop_duplicates('academic_name').iterrows():
        aff = row['affiliations']
        pairs = []
        if isinstance(aff, list):
            for a in aff:
                if isinstance(a, dict) and a.get('ent'):
                    pairs.append((a.get('ent'), a.get('inst') or 'SIN INSTITUCIÓN'))
        academics_map[row['academic_name']] = pairs or [('Sin Entidad', 'SIN INSTITUCIÓN')]

    def _save(df, name, lvl):
        save_disaggregated_parquets(df, name, lvl,
                                    academics_map=academics_map if lvl == 'academic' else None,
                                    updated_files=updated_files)

    # ── 2. Papers raw por académico ────────────────────────────────────────────
    _save(df_raw, 'papers_profesor.parquet', 'academic')

    # ── 3. Tópicos ────────────────────────────────────────────────────────────
    if 'topics' in df_raw.columns:
        topic_rows, topic_evo_rows = [], []
        for _, r in df_raw.iterrows():
            ac_name = r['academic_name']
            yr = r.get('year')
            for t in (r['topics'] if isinstance(r['topics'], list) else []):
                if not isinstance(t, dict):
                    continue
                entry = {
                    'academic_name': ac_name,
                    'domain':   t.get('domain') or 'Sin Dominio',
                    'field':    t.get('field')  or 'Sin Campo',
                    'subfield': t.get('subfield') or 'Sin Subcampo',
                    'topic':    t.get('topic')   or 'Sin Tópico',
                }
                topic_rows.append(entry)
                if yr and not pd.isna(yr):
                    topic_evo_rows.append({**entry, 'year': int(yr)})

        if topic_rows:
            df_topics = pd.DataFrame(topic_rows)
            df_topics_agg = df_topics.groupby(
                ['academic_name', 'domain', 'field', 'subfield', 'topic']
            ).size().reset_index(name='value')
            _save(df_topics_agg, 'topics_investigador.parquet', 'academic')

            if topic_evo_rows:
                df_evo = pd.DataFrame(topic_evo_rows)
                df_evo_agg = df_evo.groupby(
                    ['academic_name', 'year', 'domain', 'field', 'subfield', 'topic']
                ).size().reset_index(name='value')
                _save(df_evo_agg, 'thematic_evolution_investigador.parquet', 'academic')
        else:
            empty_t  = pd.DataFrame(columns=['academic_name', 'domain', 'field', 'subfield', 'topic', 'value'])
            empty_te = pd.DataFrame(columns=['academic_name', 'year', 'domain', 'field', 'subfield', 'topic', 'value'])
            _save(empty_t,  'topics_investigador.parquet', 'academic')
            _save(empty_te, 'thematic_evolution_investigador.parquet', 'academic')

    # ── 4. Métricas anuales por investigador ──────────────────────────────────
    print("⏳ Agregando métricas anuales por investigador...")
    if 'year' in df_raw.columns:
        df_raw['year'] = pd.to_numeric(df_raw['year'], errors='coerce')
        df_raw_yr = df_raw.dropna(subset=['year'])
        df_inv_annual = aggregate_metrics(df_raw_yr, ['academic_name', 'entities', 'year'])
        _save(df_inv_annual, 'investigador_annual.parquet', 'academic')

    # ── 5. Métricas totales por investigador + interdisciplinariedad ───────────
    print("⏳ Agregando métricas totales por investigador...")
    df_inv_tot = aggregate_metrics(df_raw, ['academic_name', 'entities'])

    if 'topics' in df_raw.columns:
        inter_rows = []
        for ac_name, grp in df_raw.groupby('academic_name'):
            idx = compute_interdisciplinarity(grp['topics'])
            idx['academic_name'] = ac_name
            inter_rows.append(idx)
        if inter_rows:
            df_inter = pd.DataFrame(inter_rows)
            df_inv_tot = df_inv_tot.merge(df_inter, on='academic_name', how='left')

    _save(df_inv_tot, 'investigador_total.parquet', 'academic')

    # ── 6. Keywords por investigador ──────────────────────────────────────────
    if 'keywords' in df_raw.columns:
        print("⏳ Calculando keywords por investigador...")
        kw_rows = []
        for ac_name, grp in df_raw.groupby('academic_name'):
            cnt = Counter()
            for kws in grp['keywords']:
                if isinstance(kws, list):
                    cnt.update([k for k in kws if k])
            for kw, freq in cnt.most_common(1000):
                kw_rows.append({'academic_name': ac_name, 'keyword': kw, 'freq': freq})
        if kw_rows:
            _save(pd.DataFrame(kw_rows), 'keywords_investigador.parquet', 'academic')

    # ── 7. Métricas recientes (2021-2025) ─────────────────────────────────────
    if 'year' in df_raw.columns:
        df_raw_recent = df_raw[df_raw['year'].between(2021, CURRENT_YEAR)]
        if not df_raw_recent.empty:
            df_inv_recent = aggregate_metrics(df_raw_recent, ['academic_name', 'entities'])
            if 'topics' in df_raw_recent.columns:
                inter_r = []
                for ac_name, grp in df_raw_recent.groupby('academic_name'):
                    idx = compute_interdisciplinarity(grp['topics'])
                    idx['academic_name'] = ac_name
                    inter_r.append(idx)
                if inter_r:
                    df_inter_r = pd.DataFrame(inter_r)
                    df_inv_recent = df_inv_recent.merge(
                        df_inter_r[['academic_name', 'gini_topics']], on='academic_name', how='left'
                    )
            _save(df_inv_recent, 'investigador_recent.parquet', 'academic')

    # ── 8. Métricas a nivel entidad ───────────────────────────────────────────
    if entity_filter or not academic_filter:
        print("⏳ Extrayendo métricas de entidades...")
        df_inst_raw = extract_entity_papers(entity_filter, source_filter)
        if not df_inst_raw.empty:
            df_inst_raw = df_inst_raw.drop_duplicates(subset=['entity_name', 'paper_id'])
            if 'year' in df_inst_raw.columns:
                df_inst_raw['year'] = pd.to_numeric(df_inst_raw['year'], errors='coerce')
            _save(df_inst_raw, 'papers_institucion.parquet', 'entity')
            df_inst_tot = aggregate_metrics(df_inst_raw, ['entity_name'])
            _save(df_inst_tot, 'institucion_total.parquet', 'entity')

    print(f"✅ Proceso completado. {len(updated_files)} archivos actualizados.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity")
    parser.add_argument("--academic")
    args = parser.parse_args()
    process_and_save(entity_filter=args.entity, academic_filter=args.academic)
