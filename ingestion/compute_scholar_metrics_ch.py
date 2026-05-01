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
    accede incondicionalmente. Si la columna existe pero tiene NA (por LEFT join),
    también la rellena con el valor por defecto.
    """
    # Columnas numéricas — NaN para que los promedios sean correctos
    for col in ['fwci', 'citation_normalized_percentile',
                'is_in_top_10_percent', 'is_in_top_1_percent', 'citations']:
        if col not in df.columns:
            df[col] = np.nan
        # No rellenar NaN numéricos: son datos genuinamente ausentes

    # oa_status: necesita string, no NA (se compara con '== gold', etc.)
    if 'oa_status' not in df.columns:
        df['oa_status'] = 'closed'
    else:
        df['oa_status'] = df['oa_status'].fillna('closed')

    # is_oa: necesita ser 0/1 entero
    if 'is_oa' not in df.columns:
        df['is_oa'] = 0
    else:
        df['is_oa'] = pd.to_numeric(df['is_oa'], errors='coerce').fillna(0).astype(int)

    # Columnas de listas — lista vacía por fila
    for col in ['counts_by_year', 'indexed_in']:
        if col not in df.columns:
            df[col] = [[] for _ in range(len(df))]
        else:
            df[col] = df[col].apply(lambda x: x if isinstance(x, list) else [])

    # Columnas booleanas/enteras — 0 como fallback
    for col in ['is_retracted', 'journal_is_in_doaj', 'journal_is_core',
                'any_repository_has_fulltext']:
        if col not in df.columns:
            df[col] = 0
        else:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    # Columnas de texto
    if 'language' not in df.columns:
        df['language'] = 'en'
    else:
        df['language'] = df['language'].fillna('en')

    if 'license' not in df.columns:
        df['license'] = None

    if 'has_oa_data' not in df.columns:
        df['has_oa_data'] = 0
    else:
        df['has_oa_data'] = df['has_oa_data'].fillna(0).astype(int)

    if 'openalex_url' not in df.columns:
        df['openalex_url'] = None

    # Columnas de costos APC
    for col in ['apc_paid_usd', 'apc_list_usd']:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    return df


def aggregate_metrics(df_papers: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    """Wrapper de aggregate_metrics del script original que garantiza
    la existencia de todas las columnas esperadas antes de delegar."""
    df_papers = _ensure_ch_columns(df_papers)
    return _orig.aggregate_metrics(df_papers, group_cols)

# --- Lógica de ClickHouse ---

def _build_topics_from_row(row):
    """
    Construye la lista de topics en formato dict compatible con compute_interdisciplinarity
    y el sunburst del dashboard (path=['domain','field','subfield','topic']).

    - Si el JOIN con la tabla `topics` de CH funcionó, `primary_topic_name` tiene el
      display_name real del tópico (máxima granularidad).
    - Si no, cae en `subfield_name` como aproximación.
    """
    domain   = row.get('domain_name')   or 'Sin Dominio'
    field    = row.get('field_name')    or 'Sin Campo'
    subfield = row.get('subfield_name') or 'Sin Subcampo'
    # topic_name: display_name real si vino del JOIN, si no: subfield_name
    topic_name = row.get('primary_topic_name') or subfield

    all_t = row.get('all_topics')
    if isinstance(all_t, (list, np.ndarray)) and len(all_t) > 0:
        # Solo tenemos el nombre del tópico PRIMARIO (topic_id = all_topics[0])
        # Para los secundarios reutilizamos subfield como nivel de granularidad
        entries = []
        for idx, _ in enumerate(all_t):
            t_name = topic_name if idx == 0 else subfield
            entries.append({
                'topic':    t_name,
                'subfield': subfield,
                'field':    field,
                'domain':   domain,
            })
        return entries

    # Fallback: sólo tópico primario
    if pd.notnull(row.get('topic_id')):
        return [{'topic': topic_name, 'subfield': subfield,
                 'field': field, 'domain': domain}]
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

    # Sub-batching interno: ClickHouse limita el tamaño de query (~256KB).
    # Los oa_ids y dois se procesan en sub-lotes de 500 para no superar ese límite.
    # Con DOIs como URLs completas cada lote de 50k supera ese límite.
    # Procesamos en sub-lotes de 500 y concatenamos.
    CH_SUB = 500
    sub_dfs = []

    # Intentar JOIN con tabla `topics` para obtener el display_name del tópico primario.
    # Si la tabla no existe en CH, fallback a query sin JOIN.
    _topic_join = """
        LEFT JOIN (
            SELECT id, display_name AS primary_topic_name
            FROM topics
        ) t ON wf.topic_id = t.id
    """
    _topic_col  = "t.primary_topic_name,"
    _topic_alias = "wf."  # prefijo para columnas de works_flat cuando hay JOIN

    def _run_sub_query(sub_oa, sub_doi, use_join=True):
        sub_conds, sub_params = [], {}
        if sub_oa:
            sub_conds.append(('wf.' if use_join else '') + 'id IN %(oa_ids)s')
            sub_params['oa_ids'] = sub_oa
        if sub_doi:
            sub_conds.append(('wf.' if use_join else '') + 'doi IN %(dois)s')
            sub_params['dois'] = [f'https://doi.org/{d}' for d in sub_doi]
        if not sub_conds:
            return None

        if use_join:
            q = f"""
            SELECT
                wf.id, wf.doi, wf.title, wf.publication_year AS year,
                wf.cited_by_count AS citations,
                wf.fwci, wf.percentile AS citation_normalized_percentile,
                wf.is_top_10 AS is_in_top_10_percent, wf.is_top_1 AS is_in_top_1_percent,
                wf.source_id, wf.source_type, wf.is_oa, wf.oa_status,
                wf.topic_id, wf.subfield_name, wf.field_name, wf.domain_name,
                wf.all_topics, wf.keywords, wf.sdgs,
                wf.country_codes,
                wf.referenced_works_count, wf.referenced_works,
                wf.is_retracted, wf.language, wf.type,
                t.primary_topic_name
            FROM works_flat wf
            LEFT JOIN (
                SELECT id, display_name AS primary_topic_name
                FROM topics
            ) t ON wf.topic_id = t.id
            WHERE {' OR '.join(sub_conds)}
            """
        else:
            q = f"""
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
            WHERE {' OR '.join(sub_conds)}
            """
        return ch_client.query_df(q, parameters=sub_params)

    # Determinar si el JOIN con topics funciona (solo checar en el primer sub-lote)
    _use_topic_join = None

    for i in range(0, max(len(oa_ids), len(dois), 1), CH_SUB):
        sub_oa  = oa_ids[i:i+CH_SUB]
        sub_doi = dois[i:i+CH_SUB]
        if not sub_oa and not sub_doi:
            continue
        try:
            if _use_topic_join is None:
                # Primer intento: con JOIN para obtener topic display_name
                try:
                    chunk = _run_sub_query(sub_oa, sub_doi, use_join=True)
                    _use_topic_join = True
                except Exception:
                    _use_topic_join = False
                    chunk = _run_sub_query(sub_oa, sub_doi, use_join=False)
            else:
                chunk = _run_sub_query(sub_oa, sub_doi, use_join=_use_topic_join)

            if chunk is not None and not chunk.empty:
                sub_dfs.append(chunk)
        except Exception as e:
            print(f"  ⚠️ Sub-lote CH falló: {e}")


    if not sub_dfs:
        return pd.DataFrame(columns=['paper_id'])
    df = pd.concat(sub_dfs, ignore_index=True).drop_duplicates(subset=['id'])


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
    
    # Campos de auditoría del nodo Academic (SIIA + SNII LLM resolver)
    _AUDIT_RETURN = """
               a.siia_url AS siia_url,
               a.audit_verdict AS audit_verdict,
               a.audit_confidence AS audit_confidence,
               a.audit_reason AS audit_reason,
               a.audit_timestamp AS audit_timestamp,
               a.match_reason AS match_reason,
               a.discarded_candidates AS discarded_candidates"""

    if academic_filter:
        query = f"""
        MATCH (a:Academic {{name: $academic}})
        OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity)
        OPTIONAL MATCH (e)-[:PART_OF]->(p_inst:Institution)
        WITH a, collect(DISTINCT {{
            ent: e.name,
            inst: CASE WHEN p_inst IS NOT NULL THEN p_inst.name
                       ELSE (CASE WHEN e:Institution THEN e.name ELSE null END) END
        }}) AS affiliations
        OPTIONAL MATCH (a)-[:AUTHORED]->(p:Paper)
        RETURN a.name AS academic_name,
               a.orcid AS orcid,
               a.scopus_id AS scopus_id,
               a.is_snii AS is_snii,
               affiliations,
               p.id AS paper_id,
               {_AUDIT_RETURN}
        """
        params = {{"academic": academic_filter}}
    elif entity_filter:
        query = f"""
        MATCH (e:Entity {{name: $entity}})<-[:AFFILIATED_TO]-(a:Academic)
        OPTIONAL MATCH (e)-[:PART_OF]->(p_inst:Institution)
        WITH e, a,
             CASE WHEN p_inst IS NOT NULL THEN p_inst.name
                  ELSE (CASE WHEN e:Institution THEN e.name ELSE null END) END AS inst_name
        WITH a, collect(DISTINCT {{ent: e.name, inst: inst_name}}) AS affiliations
        OPTIONAL MATCH (a)-[:AUTHORED]->(p:Paper)
        RETURN a.name AS academic_name,
               a.orcid AS orcid,
               a.scopus_id AS scopus_id,
               a.is_snii AS is_snii,
               affiliations,
               p.id AS paper_id,
               {_AUDIT_RETURN}
        """
        params = {{"entity": entity_filter}}
    else:
        query = f"""
        MATCH (a:Academic)
        OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity)
        OPTIONAL MATCH (e)-[:PART_OF]->(p_inst:Institution)
        WITH a, collect(DISTINCT {{
            ent: e.name,
            inst: CASE WHEN p_inst IS NOT NULL THEN p_inst.name
                       ELSE (CASE WHEN e:Institution THEN e.name ELSE null END) END
        }}) AS affiliations
        OPTIONAL MATCH (a)-[:AUTHORED]->(p:Paper)
        RETURN a.name AS academic_name,
               a.orcid AS orcid,
               a.scopus_id AS scopus_id,
               a.is_snii AS is_snii,
               affiliations,
               p.id AS paper_id,
               {_AUDIT_RETURN}
        """
        params = {}

    with graph_store.driver.session() as session:
        neo_df = pd.DataFrame([dict(r) for r in session.run(query, **params)])

    if neo_df.empty:
        yield pd.DataFrame()
        return

    # Sin filtros (todos los académicos) el DataFrame puede ser enorme.
    # Procesamos por lòtes de paper_ids para no saturar RAM ni ClickHouse.
    all_paper_ids = neo_df['paper_id'].dropna().unique().tolist()
    total = len(all_paper_ids)
    if total == 0:
        yield pd.DataFrame()
        return

    BATCH = 5000   # reducido de 50k: cada sub-batch de 500 IDs en CH es ~17KB
    print(f"  → {total} paper_ids únicos | procesando en lotes de {BATCH}...")

    for i in range(0, total, BATCH):
        batch_ids = all_paper_ids[i:i+BATCH]
        df_meta = fetch_metadata_from_clickhouse(batch_ids)
        df_chunk = neo_df[neo_df['paper_id'].isin(batch_ids)].copy()
        if not df_meta.empty:
            df_chunk = df_chunk.merge(df_meta, on='paper_id', how='left')

        # Garantizar columnas requeridas por aggregate_metrics tras el LEFT join
        # (ausentes cuando ningún paper del batch tiene match en CH)
        if 'has_oa_data' not in df_chunk.columns:
            df_chunk['has_oa_data'] = 0
        else:
            df_chunk['has_oa_data'] = df_chunk['has_oa_data'].fillna(0).astype(int)
        if 'openalex_url' not in df_chunk.columns:
            df_chunk['openalex_url'] = None

        # Mapeos finales
        df_chunk['entities'] = df_chunk['affiliations'].apply(
            lambda x: ";".join(list(set([a['ent'] for a in x if a['ent']]))) if isinstance(x, list) else "Sin Entidad"
        )
        df_chunk['institutions'] = df_chunk['affiliations'].apply(
            lambda x: ";".join(list(set([a['inst'] for a in x if a['inst']]))) if isinstance(x, list) else "Sin Institución"
        )
        if 'topics' not in df_chunk.columns:
            df_chunk['topics'] = [[] for _ in range(len(df_chunk))]
        else:
            df_chunk['topics'] = df_chunk['topics'].apply(lambda x: x if isinstance(x, list) else [])

        print(f"    Lote {i//BATCH + 1}/{-(-total//BATCH)}: {len(df_chunk)} filas")
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

    # Batching para no saturar CH con un IN clause de millones de DOIs
    all_paper_ids = neo_df['paper_id'].dropna().unique().tolist()
    BATCH = 5000
    meta_chunks = []
    for i in range(0, len(all_paper_ids), BATCH):
        chunk_meta = fetch_metadata_from_clickhouse(all_paper_ids[i:i+BATCH])
        if not chunk_meta.empty:
            meta_chunks.append(chunk_meta)
    df_meta = pd.concat(meta_chunks, ignore_index=True) if meta_chunks else pd.DataFrame(columns=['paper_id'])
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

def _compute_topics_fast(df: pd.DataFrame) -> tuple:
    """
    Versión vectorizada del procesamiento de tópicos.
    Reemplaza el loop iterrows() (O(n)) por explode + groupby (C-level).
    Retorna (df_topics_agg, df_evo_agg) o (None, None) si no hay tópicos.
    """
    if 'topics' not in df.columns:
        return None, None

    # Explotar la columna topics (lista de dicts) a filas individuales
    df_exp = df[['academic_name', 'year', 'topics']].copy()
    df_exp = df_exp.explode('topics')
    df_exp = df_exp[df_exp['topics'].apply(lambda x: isinstance(x, dict))]
    if df_exp.empty:
        return None, None

    df_exp['domain']   = df_exp['topics'].apply(lambda x: x.get('domain')   or 'Sin Dominio')
    df_exp['field']    = df_exp['topics'].apply(lambda x: x.get('field')    or 'Sin Campo')
    df_exp['subfield'] = df_exp['topics'].apply(lambda x: x.get('subfield') or 'Sin Subcampo')
    df_exp['topic']    = df_exp['topics'].apply(lambda x: x.get('topic')    or 'Sin Tópico')

    # Totales (sunburst)
    df_agg = (df_exp
              .groupby(['academic_name', 'domain', 'field', 'subfield', 'topic'])
              .size().reset_index(name='value'))

    # Evolución temporal
    df_yr = df_exp.dropna(subset=['year'])
    df_yr = df_yr[df_yr['year'].apply(lambda y: str(y).isdigit() if pd.notna(y) else False)]
    df_evo = None
    if not df_yr.empty:
        df_yr['year'] = df_yr['year'].astype(int)
        df_evo = (df_yr
                  .groupby(['academic_name', 'year', 'domain', 'field', 'subfield', 'topic'])
                  .size().reset_index(name='value'))

    return df_agg, df_evo


def process_and_save(entity_filter=None, academic_filter=None, source_filter='all'):
    from collections import Counter
    print(f"🚀 Iniciando proceso optimizado con ClickHouse (Fuente: {source_filter})...")
    updated_files = set()

    # ── Acumuladores por académico ────────────────────────────────────────────
    # Para runs completos (todo México) procesamos incrementalmente:
    # acumulamos datos por académico y guardamos en cuanto completamos su info.
    academic_buffers: dict = {}   # {ac_name -> list of df chunks}
    academics_map: dict   = {}   # {ac_name -> [(ent, inst)]}

    def _flush_academic(ac_name: str, frames: list):
        """Procesa y guarda todos los parquets de un académico."""
        if not frames:
            return
        df_ac = pd.concat(frames, ignore_index=True).drop_duplicates(subset=['paper_id'])
        if df_ac.empty:
            return

        aff_map = {ac_name: academics_map.get(ac_name, [('Sin Entidad', 'SIN INSTITUCIÓN')])}

        def _sv(df, name, lvl='academic'):
            save_disaggregated_parquets(df, name, lvl,
                                        academics_map=aff_map if lvl == 'academic' else None,
                                        updated_files=updated_files)

        # Papers raw (sin columnas internas CH)
        _CH_INT = ['doi_norm', 'id', 'all_topics', 'sdgs', 'topic_id',
                   'source_id', 'source_type', 'subfield_name', 'field_name',
                   'domain_name', 'country_codes', 'doi', 'title', 'primary_topic_name']
        _sv(df_ac.drop(columns=[c for c in _CH_INT if c in df_ac.columns]),
            'papers_profesor.parquet')

        # Tópicos (vectorizado)
        df_t_agg, df_t_evo = _compute_topics_fast(df_ac)
        empty_t  = pd.DataFrame(columns=['academic_name','domain','field','subfield','topic','value'])
        empty_te = pd.DataFrame(columns=['academic_name','year','domain','field','subfield','topic','value'])
        _sv(df_t_agg  if df_t_agg  is not None else empty_t,  'topics_investigador.parquet')
        _sv(df_t_evo  if df_t_evo  is not None else empty_te, 'thematic_evolution_investigador.parquet')

        # Métricas anuales
        if 'year' in df_ac.columns:
            df_ac['year'] = pd.to_numeric(df_ac['year'], errors='coerce')
            df_yr = df_ac.dropna(subset=['year'])
            if not df_yr.empty:
                _sv(aggregate_metrics(df_yr, ['academic_name', 'entities', 'year']),
                    'investigador_annual.parquet')

        # Totales + interdisciplinariedad
        df_tot = aggregate_metrics(df_ac, ['academic_name', 'entities'])
        if 'topics' in df_ac.columns:
            inter = []
            for an, grp in df_ac.groupby('academic_name'):
                idx = compute_interdisciplinarity(grp['topics'])
                idx['academic_name'] = an
                inter.append(idx)
            if inter:
                df_tot = df_tot.merge(pd.DataFrame(inter), on='academic_name', how='left')
        _sv(df_tot, 'investigador_total.parquet')

        # Keywords
        if 'keywords' in df_ac.columns:
            cnt = Counter()
            for kws in df_ac['keywords']:
                if isinstance(kws, list):
                    cnt.update([k for k in kws if k])
            if cnt:
                kw_df = pd.DataFrame(cnt.most_common(1000), columns=['keyword', 'freq'])
                kw_df['academic_name'] = ac_name
                _sv(kw_df, 'keywords_investigador.parquet')

        # Reciente
        if 'year' in df_ac.columns:
            df_rec = df_ac[df_ac['year'].between(2021, CURRENT_YEAR)]
            if not df_rec.empty:
                df_rec_tot = aggregate_metrics(df_rec, ['academic_name', 'entities'])
                if 'topics' in df_rec.columns:
                    inter_r = []
                    for an, grp in df_rec.groupby('academic_name'):
                        idx = compute_interdisciplinarity(grp['topics'])
                        idx['academic_name'] = an
                        inter_r.append(idx)
                    if inter_r:
                        df_rec_tot = df_rec_tot.merge(
                            pd.DataFrame(inter_r)[['academic_name', 'gini_topics']],
                            on='academic_name', how='left')
                _sv(df_rec_tot, 'investigador_recent.parquet')

    # ── 1. Streaming de chunks de Neo4j → procesamiento incremental ───────────
    processed_academics: set = set()

    for chunk_df in extract_academic_papers(academic_filter, entity_filter, source_filter):
        if chunk_df.empty:
            continue

        # Actualizar academics_map con las afiliaciones que vemos en este chunk
        for _, row in chunk_df[['academic_name', 'affiliations']].drop_duplicates('academic_name').iterrows():
            if row['academic_name'] not in academics_map:
                aff = row['affiliations']
                pairs = [(a.get('ent'), a.get('inst') or 'SIN INSTITUCIÓN')
                         for a in aff if isinstance(a, dict) and a.get('ent')] if isinstance(aff, list) else []
                academics_map[row['academic_name']] = pairs or [('Sin Entidad', 'SIN INSTITUCIÓN')]

        # Acumular frames por académico
        for ac_name, grp in chunk_df.groupby('academic_name'):
            academic_buffers.setdefault(ac_name, []).append(grp)

        # Heurística: si un académico ya tiene >500 papers acumulados, procesar ya
        # (para académicos muy prolíficos o cuando el chunk es el único de ese académico)
        ready = [ac for ac, frames in academic_buffers.items()
                 if sum(len(f) for f in frames) >= 500]
        for ac_name in ready:
            _flush_academic(ac_name, academic_buffers.pop(ac_name))
            processed_academics.add(ac_name)

    # Procesar los académicos restantes en el buffer
    for ac_name, frames in academic_buffers.items():
        _flush_academic(ac_name, frames)

    total_ac = len(processed_academics) + len(academic_buffers)
    print(f"✅ {total_ac} académicos procesados.")

    # ── 2. Métricas a nivel entidad ───────────────────────────────────────────
    if entity_filter or not academic_filter:
        print("⏳ Extrayendo métricas de entidades...")
        df_inst_raw = extract_entity_papers(entity_filter, source_filter)
        if not df_inst_raw.empty:
            df_inst_raw = df_inst_raw.drop_duplicates(subset=['entity_name', 'paper_id'])
            if 'year' in df_inst_raw.columns:
                df_inst_raw['year'] = pd.to_numeric(df_inst_raw['year'], errors='coerce')

            def _sv_ent(df, name):
                save_disaggregated_parquets(df, name, 'entity', updated_files=updated_files)

            # Papers raw y métricas totales
            _sv_ent(df_inst_raw, 'papers_institucion.parquet')
            _sv_ent(aggregate_metrics(df_inst_raw, ['entity_name']), 'institucion_total.parquet')

            # Métricas anuales por entidad
            df_inst_yr = df_inst_raw.dropna(subset=['year'])
            if not df_inst_yr.empty:
                _sv_ent(aggregate_metrics(df_inst_yr, ['entity_name', 'year']),
                        'institucion_annual.parquet')

            # Tópicos por entidad (vectorizado, mismo helper que académicos)
            # _compute_topics_fast espera columna 'academic_name'; renombrar temporalmente
            df_inst_t = df_inst_raw.rename(columns={'entity_name': 'academic_name'})
            df_t_ent, df_te_ent = _compute_topics_fast(df_inst_t)
            if df_t_ent is not None and not df_t_ent.empty:
                df_t_ent  = df_t_ent.rename(columns={'academic_name': 'entity_name'})
                _sv_ent(df_t_ent, 'topics_institucion.parquet')
            if df_te_ent is not None and not df_te_ent.empty:
                df_te_ent = df_te_ent.rename(columns={'academic_name': 'entity_name'})
                _sv_ent(df_te_ent, 'thematic_evolution_institucion.parquet')

            # Keywords por entidad
            if 'keywords' in df_inst_raw.columns:
                from collections import Counter as _Ctr
                kw_rows = []
                for ent_name, grp in df_inst_raw.groupby('entity_name'):
                    cnt = _Ctr()
                    for kws in grp['keywords']:
                        if isinstance(kws, list):
                            cnt.update([k for k in kws if k])
                    for kw, freq in cnt.most_common(1000):
                        kw_rows.append({'entity_name': ent_name, 'keyword': kw, 'freq': freq})
                if kw_rows:
                    _sv_ent(pd.DataFrame(kw_rows), 'keywords_institucion.parquet')


    print(f"✅ Proceso completado. {len(updated_files)} archivos actualizados.")





if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity")
    parser.add_argument("--academic")
    args = parser.parse_args()
    process_and_save(entity_filter=args.entity, academic_filter=args.academic)
