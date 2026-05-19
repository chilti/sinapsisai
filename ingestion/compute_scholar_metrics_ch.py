"""
compute_scholar_metrics_ch.py (v4)
===================================
Pipeline de cómputo de métricas académicas institucionales.

Arquitectura de Fuentes
-----------------------
  Capacidad Instalada   → works_academic_all JOIN paper_author_map (por académico/ORCID)
  Producción Indizada   → Neo4j (CREDITED_TO) → JOIN works_academic_all (por entidad)
  Producción Total      → Neo4j get_total_paper_census() (incluye papers no en OpenAlex)
  Nivel México          → paper_entity_map JOIN works_academic_all (sin filtro de entidad)

Jerarquía Institucional (SNII)
-------------------------------
  Institution → Dependency → Subdependency

  La relación CREDITED_TO en Neo4j vincula cada Paper al nivel más específico disponible.
  La desambiguación de homónimos (e.g., dos "Facultad de Ciencias" en distintas universidades)
  se hace via PART_OF*1..2 → Institution en la query Cypher.

Dos Métricas de Producción en Dashboard
-----------------------------------------
  "Producción Total"        : Censo Neo4j (todos los papers ingresados, incl. WoS sin OA ID)
  "Indizada en OpenAlex"    : Papers recuperados de works_academic_all (tienen openalex_id o DOI)

Jerarquía de Parquets Generados
---------------------------------
  cache_ch/{institución}/{entidad}/{académico}/investigador_*.parquet
  cache_ch/{institución}/{entidad}/capacidad_instalada/institucion_*.parquet
  cache_ch/{institución}/{entidad}/produccion_institucional/institucion_*.parquet
  cache_ch/{institución}/capacidad_instalada/institucion_*.parquet
  cache_ch/{institución}/produccion_institucional/institucion_*.parquet
  cache_ch/MEXICO/capacidad_instalada/institucion_*.parquet
  cache_ch/MEXICO/produccion_institucional/institucion_*.parquet
"""
import os, sys, argparse, json, importlib.util, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
import unicodedata
from sklearn.preprocessing import StandardScaler
try:
    from umap import UMAP
except ImportError:
    UMAP = None

warnings.filterwarnings('ignore')
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env')))

from database.clickhouse_db import ch_client
from database.knowledge_graph import Neo4jGraphStore
from scripts.generate_snii_counts import generate_official_snii_counts

# ── Importar helpers del script original ───────────────────────────────────
_THIS_DIR  = Path(os.path.abspath(os.path.dirname(__file__)))
_ORIG_PATH = _THIS_DIR / 'compute_scholar_metrics.py'
_spec      = importlib.util.spec_from_file_location('compute_scholar_metrics', _ORIG_PATH)
_orig      = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_orig)

_get_h_index                = _orig._get_h_index
_clean_keywords             = _orig._clean_keywords
compute_citation_velocity   = _orig.compute_citation_velocity
compute_interdisciplinarity = _orig.compute_interdisciplinarity
CURRENT_YEAR                = _orig.CURRENT_YEAR

BASE_PATH = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
CACHE_DIR = BASE_PATH / 'data' / 'cache_ch'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Queries ClickHouse ─────────────────────────────────────────────────────

# Capacidad Instalada — JOIN dual: W-ID directo (nuevos) + DOI normalizado (legacy)
_Q_CAP_DOI = """
SELECT
    pm.academic_name, pm.institution, pm.dependency, pm.subdependency,
    pm.orcid, pm.openalex_id, pm.is_snii, pm.audit_verdict,
    wf.id           AS paper_id,
    wf.doi,
    wf.title        AS Title,
    wf.publication_year AS year,
    wf.cited_by_count   AS citations,
    wf.fwci,
    wf.percentile   AS citation_normalized_percentile,
    wf.is_top_10 AS is_in_top_10_percent,
    wf.is_top_1 AS is_in_top_1_percent,
    wf.is_oa, wf.oa_status,
    wf.topic, wf.subfield, wf.field, wf.domain,
    wf.language, wf.type,
    wf.source_id AS Source, wf.source_type,
    wf.is_retracted, wf.referenced_works_count, wf.keywords, if(empty(pm.ODS), wf.sdgs, pm.ODS) AS ODS,
    wf.author_names, wf.all_country_codes,
    wf.apc_paid_usd, wf.apc_list_usd, wf.counts_by_year, wf.license,
    wf.journal_is_in_doaj, wf.journal_is_core, wf.any_repository_has_fulltext,
    inst.ror AS ror_id,
    inst.id AS institution_id,
    inst.type AS institution_type,
    inst.country_code AS institution_country
FROM paper_author_map pm
JOIN works_academic_all wf ON lower(replaceOne(wf.doi, %(doi_prefix)s, %(doi_empty)s)) = lower(pm.paper_id)
LEFT JOIN institutions inst ON pm.institution_ror = inst.ror
{filter} AND pm.paper_id LIKE %(doi_like)s
"""

_Q_CAP_WID = """
SELECT
    pm.academic_name, pm.institution, pm.dependency, pm.subdependency,
    pm.orcid, pm.openalex_id, pm.is_snii, pm.audit_verdict,
    wf.id           AS paper_id,
    wf.doi,
    wf.title        AS Title,
    wf.publication_year AS year,
    wf.cited_by_count   AS citations,
    wf.fwci,
    wf.percentile   AS citation_normalized_percentile,
    wf.is_top_10 AS is_in_top_10_percent,
    wf.is_top_1 AS is_in_top_1_percent,
    wf.is_oa, wf.oa_status,
    wf.topic, wf.subfield, wf.field, wf.domain,
    wf.language, wf.type,
    wf.source_id AS Source, wf.source_type,
    wf.is_retracted, wf.referenced_works_count, wf.keywords, if(empty(pm.ODS), wf.sdgs, pm.ODS) AS ODS,
    wf.author_names, wf.all_country_codes,
    wf.apc_paid_usd, wf.apc_list_usd, wf.counts_by_year, wf.license,
    wf.journal_is_in_doaj, wf.journal_is_core, wf.any_repository_has_fulltext,
    inst.ror AS ror_id,
    inst.id AS institution_id,
    inst.type AS institution_type,
    inst.country_code AS institution_country
FROM paper_author_map pm
JOIN works_academic_all wf ON wf.id = 'https://openalex.org/' || pm.paper_id
LEFT JOIN institutions inst ON pm.institution_ror = inst.ror
{filter} AND pm.paper_id LIKE 'W%%'
"""

_Q_PROD_DOI = """
SELECT
    wf.id          AS paper_id,
    wf.doi,
    wf.title       AS Title,
    wf.publication_year AS year,
    wf.cited_by_count   AS citations,
    wf.fwci,
    wf.percentile  AS citation_normalized_percentile,
    wf.is_top_10   AS is_in_top_10_percent,
    wf.is_top_1    AS is_in_top_1_percent,
    wf.is_oa,
    wf.oa_status,
    wf.topic,
    wf.subfield,
    wf.field,
    wf.domain,
    wf.language,
    wf.type,
    wf.source_id   AS Source,
    wf.source_type,
    wf.is_retracted, wf.referenced_works_count, wf.keywords,
    pe.institution,
    pe.dependency,
    pe.subdependency,
    if(empty(pm.ODS), wf.sdgs, pm.ODS) AS ODS,
    wf.author_names,
    wf.all_country_codes,
    wf.institution_rors,
    wf.apc_paid_usd,
    wf.apc_list_usd,
    wf.counts_by_year,
    wf.license,
    wf.journal_is_in_doaj,
    wf.journal_is_core,
    wf.any_repository_has_fulltext,
    inst.ror AS ror_id,
    inst.id AS institution_id,
    inst.type AS institution_type,
    inst.country_code AS institution_country
FROM paper_entity_map pe
JOIN works_academic_all wf ON lower(replaceOne(wf.doi, %(doi_prefix)s, %(doi_empty)s)) = lower(pe.paper_id)
LEFT JOIN (
    SELECT paper_id, any(ODS) as ODS 
    FROM paper_author_map 
    GROUP BY paper_id
) pm ON wf.id = pm.paper_id
LEFT JOIN institutions inst ON pe.institution_ror = inst.ror
{filter} AND pe.paper_id LIKE %(doi_like)s
"""

_Q_PROD_WID = """
SELECT
    wf.id          AS paper_id,
    wf.doi,
    wf.title       AS Title,
    wf.publication_year AS year,
    wf.cited_by_count   AS citations,
    wf.fwci,
    wf.percentile  AS citation_normalized_percentile,
    wf.is_top_10   AS is_in_top_10_percent,
    wf.is_top_1    AS is_in_top_1_percent,
    wf.is_oa,
    wf.oa_status,
    wf.topic,
    wf.subfield,
    wf.field,
    wf.domain,
    wf.language,
    wf.type,
    wf.source_id   AS Source,
    wf.source_type,
    wf.is_retracted, wf.referenced_works_count, wf.keywords,
    pe.institution,
    pe.dependency,
    pe.subdependency,
    if(empty(pm.ODS), wf.sdgs, pm.ODS) AS ODS,
    wf.author_names,
    wf.all_country_codes,
    wf.institution_rors,
    wf.apc_paid_usd,
    wf.apc_list_usd,
    wf.counts_by_year,
    wf.license,
    wf.journal_is_in_doaj,
    wf.journal_is_core,
    wf.any_repository_has_fulltext,
    inst.ror AS ror_id,
    inst.id AS institution_id,
    inst.type AS institution_type,
    inst.country_code AS institution_country
FROM paper_entity_map pe
JOIN works_academic_all wf ON wf.id = 'https://openalex.org/' || pe.paper_id
LEFT JOIN (
    SELECT paper_id, any(ODS) as ODS 
    FROM paper_author_map 
    GROUP BY paper_id
) pm ON wf.id = pm.paper_id
LEFT JOIN institutions inst ON pe.institution_ror = inst.ror
{filter} AND pe.paper_id LIKE 'W%%'
"""


_DOI_PREFIX = 'https://doi.org/'
_DOI_PARAMS  = {'doi_prefix': _DOI_PREFIX, 'doi_empty': '', 'doi_like': '10.%'}

def _query_cap(filter_sql: str, params: dict = None) -> pd.DataFrame:
    p = dict(_DOI_PARAMS)
    p.update(params or {})
    
    df_doi = ch_client.query_df(_Q_CAP_DOI.format(filter=filter_sql), parameters=p)
    df_wid = ch_client.query_df(_Q_CAP_WID.format(filter=filter_sql), parameters=p)
    
    if df_doi.empty and df_wid.empty:
        return pd.DataFrame()
    return pd.concat([df_doi, df_wid], ignore_index=True)


def _query_prod(filter_sql: str, params: dict = None) -> pd.DataFrame:
    p = dict(_DOI_PARAMS)
    p.update(params or {})
    
    df_doi = ch_client.query_df(_Q_PROD_DOI.format(filter=filter_sql), parameters=p)
    df_wid = ch_client.query_df(_Q_PROD_WID.format(filter=filter_sql), parameters=p)
    
    if df_doi.empty and df_wid.empty:
        return pd.DataFrame()
    return pd.concat([df_doi, df_wid], ignore_index=True)


def _fetch_paper_ids_from_neo4j(
    graph: 'Neo4jGraphStore',
    inst_name: str,
    entity_name: str = None
) -> tuple[list[str], list[str]]:
    """
    Devuelve (openalex_ids, dois) de los papers vinculados via CREDITED_TO a la entidad.
    Si entity_name es None, busca a nivel Institution.
    Si entity_name está presente, busca en Dependency y Subdependency bajo esa institución
    para evitar homónimos (ej: FACULTAD DE CIENCIAS puede existir en varias universidades).
    """
    oa_ids, dois = [], []
    with graph.driver.session() as session:
        if entity_name is None:
            # Nivel Institución
            result = session.run(
                """
                MATCH (p:Paper)-[:CREDITED_TO]->(e:Institution {name: $inst})
                RETURN p.openalex_id AS oid, p.doi AS doi
                """,
                inst=inst_name
            )
        else:
            # Nivel Dependency o Subdependency (con desambiguación por institución)
            result = session.run(
                """
                MATCH (e)-[:PART_OF*1..2]->(i:Institution {name: $inst})
                WHERE (e:Dependency OR e:Subdependency) AND e.name = $entity
                MATCH (p:Paper)-[:CREDITED_TO]->(e)
                RETURN p.openalex_id AS oid, p.doi AS doi
                """,
                inst=inst_name,
                entity=entity_name
            )
        for rec in result:
            if rec['oid']:
                oa_ids.append(rec['oid'])
            elif rec['doi']:
                dois.append(rec['doi'])
    return oa_ids, dois


_Q_PROD_NEO4J_OID = """
SELECT
    wf.id AS paper_id, wf.doi, wf.title AS Title,
    wf.publication_year AS year, wf.cited_by_count AS citations,
    wf.fwci, wf.percentile AS citation_normalized_percentile,
    wf.is_top_10 AS is_in_top_10_percent, wf.is_top_1 AS is_in_top_1_percent,
    wf.is_oa, wf.oa_status, wf.topic, wf.subfield, wf.field, wf.domain,
    wf.language, wf.type, wf.source_id AS Source, wf.source_type,
    wf.is_retracted, wf.referenced_works_count, wf.keywords,
    wf.sdgs AS ODS, wf.author_names, wf.all_country_codes, wf.institution_rors,
    wf.apc_paid_usd, wf.apc_list_usd, wf.counts_by_year, wf.license,
    wf.journal_is_in_doaj, wf.journal_is_core, wf.any_repository_has_fulltext
FROM works_academic_all wf
WHERE wf.id IN ({placeholders})
"""

_Q_PROD_NEO4J_DOI = """
SELECT
    wf.id AS paper_id, wf.doi, wf.title AS Title,
    wf.publication_year AS year, wf.cited_by_count AS citations,
    wf.fwci, wf.percentile AS citation_normalized_percentile,
    wf.is_top_10 AS is_in_top_10_percent, wf.is_top_1 AS is_in_top_1_percent,
    wf.is_oa, wf.oa_status, wf.topic, wf.subfield, wf.field, wf.domain,
    wf.language, wf.type, wf.source_id AS Source, wf.source_type,
    wf.is_retracted, wf.referenced_works_count, wf.keywords,
    wf.sdgs AS ODS, wf.author_names, wf.all_country_codes, wf.institution_rors,
    wf.apc_paid_usd, wf.apc_list_usd, wf.counts_by_year, wf.license,
    wf.journal_is_in_doaj, wf.journal_is_core, wf.any_repository_has_fulltext
FROM works_academic_all wf
WHERE lower(replaceOne(wf.doi, 'https://doi.org/', '')) IN ({placeholders})
"""


def _query_prod_neo4j(
    oa_ids: list[str],
    dois: list[str],
    inst_name: str,
    dep_name: str = 'SIN INFORMACIÓN',
    sub_name: str = 'SIN INFORMACIÓN'
) -> pd.DataFrame:
    """
    Recupera metadatos de papers desde works_academic_all dado listas de
    OpenAlex IDs y DOIs obtenidos desde Neo4j (vía CREDITED_TO).
    Añade las columnas de jerarquía (institution/dependency/subdependency)
    que antes venían de paper_entity_map.
    """
    frames = []
    CHUNK = 1000  # ClickHouse soporta IN con miles, pero loteamos para seguridad

    for i in range(0, len(oa_ids), CHUNK):
        chunk = oa_ids[i:i+CHUNK]
        placeholders = ', '.join(f"'{v}'" for v in chunk)
        try:
            df = ch_client.query_df(_Q_PROD_NEO4J_OID.format(placeholders=placeholders))
            if not df.empty:
                frames.append(df)
        except Exception as e:
            print(f"      ⚠️ Error OID chunk {i}: {e}")

    for i in range(0, len(dois), CHUNK):
        chunk = [d.replace('https://doi.org/', '').lower() for d in dois[i:i+CHUNK]]
        placeholders = ', '.join(f"'{v}'" for v in chunk)
        try:
            df = ch_client.query_df(_Q_PROD_NEO4J_DOI.format(placeholders=placeholders))
            if not df.empty:
                frames.append(df)
        except Exception as e:
            print(f"      ⚠️ Error DOI chunk {i}: {e}")

    if not frames:
        return pd.DataFrame()

    df_out = pd.concat(frames, ignore_index=True).drop_duplicates(subset=['paper_id'])
    # Añadir columnas de jerarquía (sustituyen las que venían de paper_entity_map)
    df_out['institution'] = inst_name
    df_out['dependency']  = dep_name
    df_out['subdependency'] = sub_name
    return df_out


# ── Helpers de normalización ───────────────────────────────────────────────

def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Garantiza columnas mínimas para aggregate_metrics."""
    num_na = ['fwci', 'citation_normalized_percentile']
    for c in num_na:
        if c not in df.columns:
            df[c] = np.nan

    for c in ['is_in_top_10_percent', 'is_in_top_1_percent',
              'is_oa', 'is_retracted']:
        if c not in df.columns:
            df[c] = 0
        else:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)

    if 'oa_status' not in df.columns:
        df['oa_status'] = 'closed'
    else:
        df['oa_status'] = df['oa_status'].fillna('closed')

    for c in ['citations']:
        if c not in df.columns:
            df[c] = 0
        else:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)

    # Columnas de listas/arrays (Normalizar a nombres comunes para aggregate_metrics)
    # ClickHouse nos da author_names o author_ids y all_country_codes o country_codes
    mapping = {
        'author_names': 'authors',
        'all_country_codes': 'countries'
    }
    for old, new in mapping.items():
        if old in df.columns:
            df[new] = df[old].apply(lambda x: x if isinstance(x, (list, np.ndarray)) else [])
            
    # Calcular contadores reales desde las listas generadas
    if 'authors' in df.columns:
        df['author_count'] = df['authors'].apply(lambda x: len(x) if isinstance(x, (list, np.ndarray)) else 0)
    else:
        df['author_count'] = 0
        
    if 'countries' in df.columns:
        df['countries_distinct_count'] = df['countries'].apply(lambda x: len(set([c for c in x if c])) if isinstance(x, (list, np.ndarray)) else 0)
    else:
        df['countries_distinct_count'] = 0
            
    # Otras columnas necesarias para aggregate_metrics (Legacy compatibility)
    df['has_oa_data'] = 1
    
    # 1. Autores y Países (Contar elementos si son listas)
    # El dashboard a veces espera la lista, a veces el conteo. 
    # El agregador original usa la lista para promediar len().
    
    # 2. Citas por año (Trayectorias)
    if 'counts_by_year' in df.columns and 'year' in df.columns:
        # Reutilizar la función compute_citation_velocity del script original si es necesario,
        # pero aquí la implementamos compacta para eficiencia.
        def _calc_traj(row):
            counts = row.get('counts_by_year')
            if not isinstance(counts, (list, np.ndarray)) or not counts:
                return pd.Series([row['citations']/max(1, 2026-row['year']), 0, 0, 0])
            
            # Formato ClickHouse puede ser lista de JSONs o lista de Strings
            import ast
            parsed = []
            for c in counts:
                if isinstance(c, str):
                    try: parsed.append(ast.literal_eval(c))
                    except: continue
                elif isinstance(c, dict):
                    parsed.append(c)
            
            total = sum(c.get('cited_by_count', 0) for c in parsed)
            recent = sum(c.get('cited_by_count', 0) for c in parsed if c.get('year', 0) >= 2023)
            early = sum(c.get('cited_by_count', 0) for c in parsed if c.get('year', 0) <= row['year'] + 1)
            
            # Half life aproximado
            hl = 0
            if total > 0:
                sorted_c = sorted(parsed, key=lambda x: x.get('year', 0))
                cum = 0
                for c in sorted_c:
                    cum += c.get('cited_by_count', 0)
                    if cum >= total / 2:
                        hl = 2026 - c.get('year', 2026)
                        break
            return pd.Series([total/max(1, 2026-row['year']), recent, early, hl])

        df[['velocity', 'recent_cites_3yr', 'early_impact', 'half_life']] = df.apply(_calc_traj, axis=1)
    
    # 3. Visibilidad e Indexación
    index_cols = [
        'journal_is_in_doaj', 'journal_is_core', 'any_repository_has_fulltext',
        'is_wos', 'is_scopus', 'is_pubmed', 'is_openalex', 'is_doaj'
    ]
    for c in index_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
        else:
            df[c] = 0

    # 4. APC y Otros
    for c in ['apc_paid_usd', 'apc_list_usd']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        else:
            df[c] = 0.0

    # 5. ODS (Mapear IDs y Nombres)
    import ast
    if 'ODS' in df.columns:
        def _parse_ods(x):
            if not isinstance(x, (list, np.ndarray)): return None, None
            
            ids, names = [], []
            for item in x:
                if not item: continue
                # Parsear JSON si viene de ClickHouse
                if isinstance(item, str) and item.startswith('{'):
                    try:
                        import ast
                        item_dict = ast.literal_eval(item)
                        ods_id = str(item_dict.get('id', ''))
                    except:
                        ods_id = str(item)
                elif isinstance(item, dict):
                    ods_id = str(item.get('id', ''))
                else:
                    ods_id = str(item)
                
                if ods_id and 'sdg' in ods_id.lower():
                    # Extraer el numero
                    key = ods_id.split('/')[-1].replace('SDG ', '').strip()
                    ods_name = ODS_MAP.get(key, f"SDG {key}")
                    ids.append(ods_id)
                    names.append(ods_name)
            
            if not ids: return None, None
            return "; ".join(ids), "; ".join(names)

        ods_parsed = df['ODS'].apply(_parse_ods)
        df['ODS_ID'] = ods_parsed.apply(lambda x: x[0])
        df['ODS_Nombre'] = ods_parsed.apply(lambda x: x[1])
    else:
        df['ODS_ID'] = None
        df['ODS_Nombre'] = None

    for c in ['keywords', 'ODS']:
        if c not in df.columns:
            df[c] = [[] for _ in range(len(df))]

    # 6. Forzar tipos numéricos y parsear counts_by_year
    def _parse_cby(val):
        if isinstance(val, list): return val
        if isinstance(val, str) and val.startswith('['):
            try:
                import json
                return json.loads(val)
            except:
                return []
        return []

    if 'counts_by_year' in df.columns:
        df['counts_by_year'] = df['counts_by_year'].apply(_parse_cby)
    else:
        df['counts_by_year'] = [[] for _ in range(len(df))]

    cols_num = ['citations', 'year', 'fwci', 'percentile', 'is_in_top_10_percent', 
                'is_in_top_1_percent', 'is_oa', 'referenced_works_count', 'velocity']
    for c in cols_num:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

    for c in ['apc_paid_usd', 'apc_list_usd']:
        if c not in df.columns:
            df[c] = 0.0

    for c in ['journal_is_in_doaj', 'journal_is_core', 'any_repository_has_fulltext']:
        if c not in df.columns:
            df[c] = 0

    if 'counts_by_year' not in df.columns:
        df['counts_by_year'] = [[] for _ in range(len(df))]

    if 'language' not in df.columns:
        df['language'] = 'en'
    if 'has_oa_data' not in df.columns:
        df['has_oa_data'] = 1

    # Reconstruir columna 'topics' para retrocompatibilidad con métricas legacy (Gini, Domain Diversity)
    if 'topic' in df.columns and 'domain' in df.columns:
        df['topics'] = df.apply(
            lambda r: [{'topic': r['topic'], 'domain': r['domain']}] if pd.notna(r.get('topic')) and r.get('topic') else [],
            axis=1
        )
    else:
        df['topics'] = [[] for _ in range(len(df))]

    return df


def aggregate_metrics(df: pd.DataFrame, group_cols: list) -> pd.DataFrame:
    df = _ensure_columns(df)
    return _orig.aggregate_metrics(df, group_cols)


# ── Topics helpers ─────────────────────────────────────────────────────────

def _topics_agg(df: pd.DataFrame, group_col: str) -> tuple:
    """
    Agrega tópicos desde columnas planas (domain_name, field_name, subfield_name, topic_name).
    Retorna (df_totales, df_evolucion_temporal).
    """
    needed = ['domain', 'field', 'subfield', 'topic']
    if not all(c in df.columns for c in needed):
        return None, None

    base = df[[group_col, 'year', 'domain', 'field',
               'subfield', 'topic']].copy()
    base = base.dropna(subset=['domain'])
    base['domain']   = base['domain'].fillna('Sin Dominio')
    base['field']    = base['field'].fillna('Sin Campo')
    base['subfield'] = base['subfield'].fillna('Sin Subcampo')
    base['topic']    = base['topic'].fillna('Sin Tópico')

    # Definir estructura base por si no hay datos
    cols_tot = [group_col, 'domain', 'field', 'subfield', 'topic', 'value']
    cols_evo = [group_col, 'year', 'domain', 'field', 'subfield', 'topic', 'value']
    
    if base.empty:
        return pd.DataFrame(columns=cols_tot), pd.DataFrame(columns=cols_evo)

    df_tot = (base.groupby([group_col, 'domain', 'field', 'subfield', 'topic'])
              .size().reset_index(name='value'))

    base_yr = base.dropna(subset=['year'])
    base_yr = base_yr[base_yr['year'].apply(
        lambda y: str(y).isdigit() if pd.notna(y) else False)]
    
    if not base_yr.empty:
        base_yr['year'] = base_yr['year'].astype(int)
        df_evo = (base_yr
                  .groupby([group_col, 'year', 'domain', 'field', 'subfield', 'topic'])
                  .size().reset_index(name='value'))
    else:
        df_evo = pd.DataFrame(columns=cols_evo)

    return df_tot, df_evo


def _topics_as_list(df: pd.DataFrame) -> pd.Series:
    """
    Crea la columna 'topics' (lista de dicts) necesaria para
    compute_interdisciplinarity, a partir de columnas planas.
    """
    def _row(r):
        d = r.get('domain')   or 'Sin Dominio'
        f = r.get('field')    or 'Sin Campo'
        s = r.get('subfield') or 'Sin Subcampo'
        t = r.get('topic')    or s
        return [{'domain': d, 'field': f, 'subfield': s, 'topic': t}]
    return df.apply(_row, axis=1)


# ── Guardado de parquets ───────────────────────────────────────────────────

def _safe_name(s: str) -> str:
    return str(s).replace('/', '_').replace('\\', '_')




def _save_parquet(df: pd.DataFrame, path: Path, updated_files: set = None):
    if df is None or df.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    if updated_files is not None:
        updated_files.add(str(path.absolute()))


def _save_inst_parquets(df: pd.DataFrame, base_dir: Path,
                        group_col: str, updated_files: set = None):
    """
    Guarda los 6 parquets de nivel institución/entidad/México
    en base_dir/{nombre}/ agrupando por group_col.
    """
    if df is None or df.empty:
        return

    for name, grp in df.groupby(group_col):
        d = base_dir / _safe_name(name)
        grp = grp.drop_duplicates(subset=['paper_id'])
        if 'year' in grp.columns:
            grp['year'] = pd.to_numeric(grp['year'], errors='coerce')

        _save_parquet(grp, d / 'papers_institucion.parquet', updated_files)

        df_tot = aggregate_metrics(grp, [group_col])
        if group_col != 'entity_name':
            df_tot = df_tot.rename(columns={group_col: 'entity_name'})
        _save_parquet(df_tot, d / 'institucion_total.parquet', updated_files)

        df_yr = grp.dropna(subset=['year'])
        if not df_yr.empty:
            df_ann = aggregate_metrics(df_yr, [group_col, 'year'])
            if group_col != 'entity_name':
                df_ann = df_ann.rename(columns={group_col: 'entity_name'})
            _save_parquet(df_ann, d / 'institucion_annual.parquet', updated_files)

        df_t, df_te = _topics_agg(grp, group_col)
        if df_t is not None:
            if group_col != 'entity_name':
                df_t = df_t.rename(columns={group_col: 'entity_name'})
            _save_parquet(df_t, d / 'topics_institucion.parquet', updated_files)
        if df_te is not None:
            if group_col != 'entity_name':
                df_te = df_te.rename(columns={group_col: 'entity_name'})
            _save_parquet(df_te, d / 'thematic_evolution_institucion.parquet', updated_files)

        if 'keywords' in grp.columns:
            from collections import Counter
            cnt = Counter()
            for kws in grp['keywords']:
                if isinstance(kws, list):
                    cnt.update([k for k in kws if k])
            if cnt:
                kw_df = pd.DataFrame(cnt.most_common(1000),
                                     columns=['keyword', 'freq'])
                kw_df['entity_name'] = name
                _save_parquet(kw_df, d / 'keywords_institucion.parquet', updated_files)
        
        # Guardar académicos de esta unidad
        _save_academic_parquets(grp, d / 'academic', updated_files)


def _save_aggregate_parquets(df: pd.DataFrame, out_dir: Path,
                              updated_files: set = None,
                              label: str = 'MEXICO',
                              inst: str = None, dep: str = None, sub: str = None):
    """
    Guarda los 6 parquets de nivel México (o institución completa)
    en out_dir/ como un único agregado.
    """
    if df is None or df.empty:
        return
        
    # Normalizar columnas ANTES de guardar nada
    df = _ensure_columns(df)
    
    df = df.drop_duplicates(subset=['paper_id'])
    if 'year' in df.columns:
        df['year'] = pd.to_numeric(df['year'], errors='coerce')

    # Añadir columna de agrupación para reutilizar aggregate_metrics y para el dashboard
    df['entity_name'] = label
    df['_grp'] = label
    df['topics'] = _topics_as_list(df)

    _save_parquet(df, out_dir / 'papers_institucion.parquet', updated_files)
    
    df_tot = aggregate_metrics(df, ['_grp'])
    
    # Calcular Gini temático para la institución
    inter = compute_interdisciplinarity(df['topics'])
    for k, v in inter.items():
        df_tot[k] = v

    # Inyectar lista de académicos desde el Censo de Neo4j (Lista Maestra)
    # Usamos un diccionario indexado por nombre para deduplicar y permitir diccionarios de metadatos
    ac_map = {} 
    
    # 1. Académicos con obra (en ClickHouse)
    if 'academic_name' in df.columns:
        for a in df['academic_name'].dropna().unique():
            if a:
                name_str = str(a)
                ac_map[name_str] = {
                    "name": name_str,
                    "institution": inst or "MÉXICO",
                    "dependency": dep or "SIN INFORMACIÓN",
                    "subdependency": sub or "SIN INFORMACIÓN"
                }
    
    # Censo Neo4j (Total Papers)
    total_papers_neo4j = 0
    if inst:
        try:
            neo = Neo4jGraphStore()
            # Diferenciar entre Producción (CREDITED_TO) y Capacidad (Sumatoria Académicos)
            if 'capacidad_instalada' in str(out_dir):
                total_papers_neo4j = neo.get_total_capacity_census(inst, dep, sub)
            else:
                total_papers_neo4j = neo.get_total_paper_census(inst, dep, sub)
            neo.close()
        except Exception as e:
            print(f"  ⚠️ Error obteniendo censo Neo4j: {e}")
            total_papers_neo4j = int(df_tot['num_documents'].iloc[0]) if not df_tot.empty else 0

    df_tot['neo4j_total_papers'] = total_papers_neo4j
    
    # 2. Académicos del Censo y Conteo Total de Papers (en Neo4j)
    if inst:
        try:
            neo = Neo4jGraphStore()
            census = neo.get_hierarchical_academic_census(inst, dep, sub)
            neo.close()
            if census:
                for person in census:
                    # El censo de Neo4j tiene prioridad por tener la jerarquía verificada
                    ac_map[person['name']] = person
        except Exception as e:
            print(f"  ⚠️ Error obteniendo datos de Neo4j para {label}: {e}")

    # Convertir a lista ordenada de diccionarios para el JSON
    final_ac_list = sorted(list(ac_map.values()), key=lambda x: x['name'] or '')
    df_tot['academics_list'] = json.dumps(final_ac_list, ensure_ascii=False)

    # Inyectar conteo oficial SNII 2025
    path_counts = BASE_PATH / 'data' / 'official_snii_counts.json'
    if path_counts.exists():
        try:
            with open(path_counts, 'r', encoding='utf-8') as f:
                official_counts = json.load(f)
            df_tot['official_snii_count'] = official_counts.get(label, 0)
        except:
            df_tot['official_snii_count'] = 0
    else:
        df_tot['official_snii_count'] = 0

    _save_parquet(df_tot.rename(columns={'_grp': 'entity_name'}),
                  out_dir / 'institucion_total.parquet', updated_files)

    df_yr = df.dropna(subset=['year'])
    if not df_yr.empty:
        df_ann = aggregate_metrics(df_yr, ['_grp', 'year'])
        _save_parquet(df_ann.rename(columns={'_grp': 'entity_name'}),
                      out_dir / 'institucion_annual.parquet', updated_files)

    df_t, df_te = _topics_agg(df, '_grp')
    if df_t is not None:
        _save_parquet(df_t.rename(columns={'_grp': 'entity_name'}),
                      out_dir / 'topics_institucion.parquet', updated_files)
    if df_te is not None:
        _save_parquet(df_te.rename(columns={'_grp': 'entity_name'}),
                      out_dir / 'thematic_evolution_institucion.parquet', updated_files)

    if 'keywords' in df.columns:
        from collections import Counter
        cnt = Counter()
        for kws in df['keywords']:
            if not kws: continue
            if isinstance(kws, str):
                try: kws = json.loads(kws)
                except: continue
            if isinstance(kws, (list, np.ndarray)):
                # Algunos formatos traen [ {"keyword": "...", "score": ...} ]
                for k in kws:
                    if isinstance(k, dict):
                        name = k.get('keyword') or k.get('display_name')
                        if name: cnt[name] += 1
                    elif k:
                        cnt[str(k)] += 1
        if cnt:
            kw_df = pd.DataFrame(cnt.most_common(1000), columns=['keyword', 'freq'])
            kw_df['entity_name'] = label  # <-- CRITICAL: Required by dashboard to filter
            _save_parquet(kw_df, out_dir / 'keywords_institucion.parquet', updated_files)


def _save_academic_parquets(df: pd.DataFrame, out_dir: Path, updated_files: set = None):
    """Agrupa por académico y guarda sus parquets individuales."""
    if 'academic_name' not in df.columns:
        return
        
    for ac_name, grp in df.groupby('academic_name'):
        if not ac_name or str(ac_name).lower() == 'none':
            continue
            
        # Extraer entidad e institución de este grupo (usamos el primero)
        entity = grp['entity'].iloc[0] if 'entity' in grp.columns else "Desconocido"
        institution = grp['institution'].iloc[0] if 'institution' in grp.columns else "Desconocido"
        
        _flush_academic(ac_name, grp, entity, institution, updated_files)


# ── Procesamiento por académico ────────────────────────────────────────────

_PAPERS_DROP = ['topic_name', 'subfield_name', 'field_name', 'domain_name',
                'entity', 'institution']   # columnas internas, no van en papers_profesor


def _flush_academic(ac_name: str, df_ac: pd.DataFrame,
                    entity: str, institution: str, updated_files: set):
    """Procesa y guarda los 7 parquets de un académico. Soporta DFs vacíos para censo."""
    safe_inst = _safe_name(institution)
    safe_ent  = _safe_name(entity)
    safe_ac   = _safe_name(ac_name)
    d = CACHE_DIR / safe_inst / safe_ent / safe_ac

    if df_ac.empty:
        # Crear un DataFrame mínimo para que el dashboard no rompa y muestre info básica
        df_ac = pd.DataFrame([{
            'academic_name': ac_name,
            'entities': entity,
            'institutions': institution,
            'has_oa_data': 0,
            'citations': 0,
            'paper_id': None,
            'year': None,
            'title': 'Sin publicaciones registradas',
            'journal_name': None,
            'doi': None,
            'sdg_names': None,
            'openalex_url': None
        }])
    else:
        df_ac = df_ac.drop_duplicates(subset=['paper_id']).copy()
        df_ac['year'] = pd.to_numeric(df_ac.get('year'), errors='coerce')
        df_ac['entities']     = entity
        df_ac['institutions'] = institution
        df_ac['has_oa_data']  = 1
        df_ac['academic_name'] = ac_name

    # Columnas derivadas para el dashboard
    if 'doi' in df_ac.columns:
        df_ac['DOI']  = df_ac['doi'].apply(
            lambda x: f'https://doi.org/{x}' if x and str(x).startswith('10.') else x)
        df_ac['Link'] = df_ac['DOI']
    
    if 'paper_id' in df_ac.columns:
        df_ac['openalex_url'] = df_ac['paper_id'].apply(
            lambda x: f'https://openalex.org/{x}' if x and str(x).startswith('W') else None)

    df_ac['topics'] = _topics_as_list(df_ac)

    # papers_profesor (sin columnas internas)
    drop = [c for c in _PAPERS_DROP if c in df_ac.columns]
    _save_parquet(df_ac.drop(columns=drop), d / 'papers_profesor.parquet', updated_files)

    # Tópicos
    df_t, df_te = _topics_agg(df_ac, 'academic_name')
    empty_t  = pd.DataFrame(columns=['academic_name','domain','field','subfield','topic','value'])
    empty_te = pd.DataFrame(columns=['academic_name','year','domain','field','subfield','topic','value'])
    _save_parquet(df_t  if df_t  is not None else empty_t,
                  d / 'topics_investigador.parquet', updated_files)
    _save_parquet(df_te if df_te is not None else empty_te,
                  d / 'thematic_evolution_investigador.parquet', updated_files)

    # Métricas anuales
    df_yr = df_ac.dropna(subset=['year'])
    if not df_yr.empty:
        _save_parquet(aggregate_metrics(df_yr, ['academic_name', 'entities', 'year']),
                      d / 'investigador_annual.parquet', updated_files)

    # Totales + interdisciplinariedad
    df_tot = aggregate_metrics(df_ac, ['academic_name', 'entities'])
    
    # NUEVO: Inyectar censo total de papers para el académico desde Neo4j
    try:
        neo = Neo4jGraphStore()
        df_tot['neo4j_total_papers'] = neo.get_academic_paper_census(ac_name)
        neo.close()
    except:
        df_tot['neo4j_total_papers'] = int(df_tot['num_documents'].iloc[0]) if not df_tot.empty else 0

    inter = compute_interdisciplinarity(df_ac['topics'])
    inter['academic_name'] = ac_name
    df_tot = df_tot.merge(pd.DataFrame([inter]), on='academic_name', how='left')
    _save_parquet(df_tot, d / 'investigador_total.parquet', updated_files)

    # Reciente (2021–CURRENT_YEAR)
    df_rec = df_ac[df_ac['year'].between(2021, CURRENT_YEAR)] if 'year' in df_ac.columns else pd.DataFrame()
    if not df_rec.empty:
        df_rec_tot = aggregate_metrics(df_rec, ['academic_name', 'entities'])
        inter_r = compute_interdisciplinarity(df_rec['topics'])
        inter_r['academic_name'] = ac_name
        df_rec_tot = df_rec_tot.merge(
            pd.DataFrame([inter_r])[['academic_name', 'gini_topics']],
            on='academic_name', how='left')
        _save_parquet(df_rec_tot, d / 'investigador_recent.parquet', updated_files)

    # Keywords
    if 'keywords' in df_ac.columns:
        from collections import Counter
        cnt = Counter()
        for kws in df_ac['keywords']:
            if isinstance(kws, list):
                cnt.update([k for k in kws if k])
        if cnt:
            kw_df = pd.DataFrame(cnt.most_common(1000), columns=['keyword', 'freq'])
            kw_df['academic_name'] = ac_name
            _save_parquet(kw_df, d / 'keywords_investigador.parquet', updated_files)


# ── Lookup ROR de instituciones ───────────────────────────────────────────

def _get_institution_rors() -> dict:
    """
    Retorna {institution_name -> [ror_id, ...]} desde la tabla institutions en CH.
    Usado para filtrar works_seed_mexico por institución.
    """
    try:
        df = ch_client.query_df(
            "SELECT display_name, ror AS ror_id FROM institutions WHERE country_code = 'MX'")
        result = {}
        for _, row in df.iterrows():
            name = str(row['display_name'])
            ror  = str(row['ror_id'])
            result.setdefault(name, []).append(ror)
        return result
    except Exception as e:
        print(f"  ⚠️ No se pudo cargar RORs: {e}")
        return {}


# ── Pipeline principal ─────────────────────────────────────────────────────

# ── Mapeo ODS ──────────────────────────────────────────────────────────────
ODS_MAP = {
    '1': '1. Fin de la pobreza', '2': '2. Hambre cero', '3': '3. Salud y bienestar',
    '4': '4. Educación de calidad', '5': '5. Igualdad de género', '6': '6. Agua limpia y saneamiento',
    '7': '7. Energía asequible y no contaminante', '8': '8. Trabajo decente y crecimiento económico',
    '9': '9. Industria, innovación e infraestructura', '10': '10. Reducción de las desigualdades',
    '11': '11. Ciudades y comunidades sostenibles', '12': '12. Producción y consumo responsables',
    '13': '13. Acción por el clima', '14': '14. Vida submarina', '15': '15. Vida de ecosistemas terrestres',
    '16': '16. Paz, justicia e instituciones sólidas', '17': '17. Alianzas para lograr los objetivos'
}

# ── Funciones de carga de jerarquía y censo ──────────────────────────────

AUDIT_PATH = BASE_PATH / 'data' / 'snii_llm_verified_matches.json'

def normalize_text(text):
    if not text or pd.isna(text): return ""
    import unicodedata
    text = str(text)
    # Quitar acentos
    text = "".join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text.upper().strip()

def _count_official_census():
    """Calcula y guarda conteos oficiales desde el archivo Excel de SNII 2025."""
    try:
        excel_path = BASE_PATH / 'data' / 'Investigadores_vigentes_2025.xlsx'
        if not excel_path.exists():
            print(f"  ⚠️ No existe {excel_path}")
            return
        
        print(f"  📊 Cargando conteos oficiales desde Excel: {excel_path.name}...")
        # Usar la hoja 4T_2025 que es la más reciente/completa
        df = pd.read_excel(excel_path, sheet_name='4T_2025 (44,794)')
        
        # Normalizar nombres de columnas para detección robusta
        def _norm_col(c):
            return "".join(ch for ch in unicodedata.normalize('NFD', str(c)) if unicodedata.category(ch) != 'Mn').upper().strip()
        
        df.columns = [_norm_col(c) for c in df.columns]
        
        inst_col = 'INSTITUCION DE ACREDITACION'
        dep_col  = 'DEPENDENCIA DE ACREDITACION'
        sub_col  = 'SUBDEPENDENCIA DE ACREDITACION'
        
        # Fallback para columnas (por si varían ligeramente los nombres)
        if inst_col not in df.columns:
            inst_col = next((c for c in df.columns if 'INSTITUCION' in c and 'ACREDITACION' in c), inst_col)
        if dep_col not in df.columns:
            dep_col = next((c for c in df.columns if 'DEPENDENCIA' in c and 'ACREDITACION' in c), dep_col)
        if sub_col not in df.columns:
            sub_col = next((c for c in df.columns if 'SUBDEPENDENCIA' in c and 'ACREDITACION' in c), sub_col)

        def _clean(val):
            v = normalize_text(val)
            if not v or v in ["NAN", "NONE", "NULL", "SIN INFORMACION", "SIN INFORMACIN", "NO APLICA"]:
                return "NO APLICA"
            return v

        # Crear columnas limpias para agrupar
        df['INST_CLEAN'] = df[inst_col].fillna("SIN INSTITUCION").apply(_clean)
        df['DEP_CLEAN']  = df[dep_col].fillna("NO APLICA").apply(_clean)
        df['SUB_CLEAN']  = df[sub_col].fillna("NO APLICA").apply(_clean)

        counts = {}
        
        # 1. Conteos por Institución
        inst_counts = df.groupby('INST_CLEAN').size().to_dict()
        for inst, count in inst_counts.items():
            if inst != "NO APLICA":
                counts[inst] = int(count)
                
        # 2. Conteos jerárquicos (Inst || Dep) y (Inst || Dep || Sub)
        # Esto permite al dashboard encontrar el conteo por la ruta completa
        
        # Agregado por Dependencia
        dep_grp = df.groupby(['INST_CLEAN', 'DEP_CLEAN']).size().reset_index(name='count')
        for _, row in dep_grp.iterrows():
            if row['INST_CLEAN'] != "NO APLICA" and row['DEP_CLEAN'] != "NO APLICA":
                key_full = f"{row['INST_CLEAN']} || {row['DEP_CLEAN']}"
                counts[key_full] = int(row['count'])

        # Agregado por Subdependencia
        sub_grp = df.groupby(['INST_CLEAN', 'DEP_CLEAN', 'SUB_CLEAN']).size().reset_index(name='count')
        for _, row in sub_grp.iterrows():
            if row['INST_CLEAN'] != "NO APLICA" and row['DEP_CLEAN'] != "NO APLICA" and row['SUB_CLEAN'] != "NO APLICA":
                key_full = f"{row['INST_CLEAN']} || {row['DEP_CLEAN']} || {row['SUB_CLEAN']}"
                counts[key_full] = int(row['count'])


        output_path = BASE_PATH / 'data' / 'official_snii_counts.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(counts, f, indent=4, ensure_ascii=False)
        print(f"  → {len(counts)} conteos oficiales generados desde Excel y guardados.")
        
    except Exception as e:
        print(f"  ⚠️ Error calculando censo oficial desde Excel: {e}")

def _load_hierarchy_from_json(institution_filter=None):
    """Carga la jerarquía institucional desde el JSON de auditoría."""
    AUDIT_PATH = BASE_PATH / 'data' / 'snii_llm_verified_matches.json'
    if not AUDIT_PATH.exists():
        print(f"❌ No existe {AUDIT_PATH}")
        return {}
        
    hier = {}
    with open(AUDIT_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for r in data:
            inst = r.get('snii_institution')
            if not inst: continue
            
            if institution_filter and institution_filter not in inst:
                continue

            ror = r.get('matched_ror') or ''
            # Fallback para RORs mal formados
            if 'orcid.org' in ror or not ror.startswith('http'):
                if 'UNAM' in inst: ror = 'https://ror.org/01tmp8f25'
                else: ror = ''
                
            dep = r.get('snii_dependency', 'SIN INFORMACIÓN')
            sub = r.get('snii_subdependency', 'SIN INFORMACIÓN')

            if inst not in hier:
                hier[inst] = {'ror': ror, 'entities': {}}
            if dep not in hier[inst]['entities']:
                hier[inst]['entities'][dep] = {'subs': set()}
            if sub and sub != 'NO APLICA':
                hier[inst]['entities'][dep]['subs'].add(sub)
                
    # Convertir sets a listas
    for inst in hier:
        for dep in hier[inst]['entities']:
            hier[inst]['entities'][dep]['subs'] = list(hier[inst]['entities'][dep]['subs'])
            
    return hier


def _process_single_academic(academic_filter: str, updated_files: set):
    """
    Modo rápido: filtra paper_author_map por academic_name,
    lee la jerarquía de los propios registros y guarda sus parquets.
    Si no hay registros en CH, busca en Neo4j para crear al menos el placeholder del censo.
    """
    print(f"\n🔍 Modo académico individual: {academic_filter}")
    df = _query_cap(
        "WHERE pm.academic_name = %(ac)s",
        {'ac': academic_filter}
    )
    
    if df.empty:
        print("  ⚠ Sin registros en paper_author_map. Buscando en Neo4j (Censo)...")
        # Fallback a Neo4j para obtener jerarquía
        try:
            from database.knowledge_graph import Neo4jGraphStore
            gs = Neo4jGraphStore()
            # Buscar cualquier afiliación
            q = """
            MATCH (a:Academic {name: $name})-[:AFFILIATED_TO]->(ent)
            OPTIONAL MATCH (ent)-[:PART_OF]->(p1)-[:PART_OF]->(p2)
            RETURN ent.name as entity, 
                   COALESCE(p2.name, p1.name, ent.name) as institution
            LIMIT 1
            """
            with gs.driver.session() as session:
                res = session.run(q, name=academic_filter).single()
                if res:
                    entity = res['entity']
                    institution = res['institution']
                    print(f"  ✅ Jerarquía encontrada en Neo4j: {institution} -> {entity}")
                    _flush_academic(academic_filter, pd.DataFrame(), entity, institution, updated_files)
                else:
                    print("  ❌ Tampoco se encontró en Neo4j.")
            gs.close()
        except Exception as e:
            print(f"  ❌ Error consultando Neo4j: {e}")
        return

    print(f"  📊 {len(df):,} papers encontrados.")
    # ... rest of the logic ...
    df['entity'] = (
        df.get('subdependency', pd.Series(dtype=str))
          .fillna(df.get('dependency', pd.Series(dtype=str)))
          .fillna(df.get('institution', pd.Series(dtype=str)))
    )

    institution = df['institution'].mode().iloc[0] if 'institution' in df.columns else 'SIN INSTITUCIÓN'
    entity      = df['entity'].mode().iloc[0]

    df = _ensure_columns(df.copy())
    _flush_academic(academic_filter, df, entity, institution, updated_files)


def process_and_save(entity_filter=None, academic_filter=None, institution_filter=None, source_filter='all'):
    """
    Orquestador principal. Carga jerarquía, consulta ClickHouse y guarda Parquets.
    """
    updated_files = set()
    
    # ── [0] Conteos oficiales SNII 2025 ──
    print("\n[0] Actualizando conteos oficiales SNII 2025...")
    _count_official_census()

    # ── Modo académico individual: path rápido ─────────────────────────────
    if academic_filter:
        _process_single_academic(academic_filter, updated_files)
        print(f"\n✅ Completado. {len(updated_files)} archivos actualizados.")
        return

    # ── [1] Cargar jerarquía desde el JSON ──
    print(f"\n[1] Cargando jerarquía institucional desde {AUDIT_PATH.name}...")
    hier = _load_hierarchy_from_json(institution_filter)
    if not hier:
        print("❌ No se cargó ninguna institución.")
        return

    mx_cap_frames = []


    # ── [2] Procesar institución por institución ──────────────────────────────
    for inst_name, data in hier.items():
        inst_ror = data['ror']
        entities = data['entities']
        safe_inst = _safe_name(inst_name)
        
        # Saltar si la institución no contiene la entidad buscada
        if entity_filter:
            found_entity = False
            for d_name, d_data in entities.items():
                if d_name == entity_filter or entity_filter in d_data['subs']:
                    found_entity = True
                    break
            if not found_entity:
                continue

        print(f"\n📍 {inst_name} ({inst_ror})")

        # 1. Obtener capacidad instalada (con filtro de académico si existe)
        params = {'ror': inst_ror, 'inst': inst_name}
        # Filtrar por ROR si está disponible, si no por nombre exacto de institución
        if inst_ror:
            where_cap = "WHERE pm.institution_ror = %(ror)s"
        else:
            where_cap = "WHERE pm.institution = %(inst)s"
        if entity_filter:
            where_cap += " AND (pm.subdependency = %(entity)s OR pm.dependency = %(entity)s)"
            params['entity'] = entity_filter
        if academic_filter:
            where_cap += " AND pm.academic_name = %(ac)s"
            params['ac'] = academic_filter

        df_full_cap = _query_cap(where_cap, params)

        if df_full_cap.empty:
            print(f"  ⚠️ Sin papers en paper_author_map para {inst_name}. Probando fallback por nombre...")
            where_cap = "WHERE pm.institution = %(inst)s"
            if entity_filter:
                where_cap += " AND (pm.subdependency = %(entity)s OR pm.dependency = %(entity)s)"
            if academic_filter:
                where_cap += " AND pm.academic_name = %(ac)s"
            df_full_cap = _query_cap(where_cap, params | {'inst': inst_name})
            
        if df_full_cap.empty:
            print(f"  ❌ No se encontró capacidad instalada.")
        else:
            df_full_cap = _ensure_columns(df_full_cap)
            print(f"  📊 {df_full_cap['paper_id'].nunique():,} registros únicos recuperados. Iniciando agregación...")

            # 2. Visibilidad e Indexación
            for c in ['is_wos', 'is_scopus', 'is_pubmed', 'is_openalex', 'is_doaj']:
                if c in df_full_cap.columns:
                    df_full_cap[c] = pd.to_numeric(df_full_cap[c], errors='coerce').fillna(0).astype(int)

            # 3. Nivel Académico (ClickHouse + Censo Neo4j)
            df_full_cap['entity'] = df_full_cap['subdependency'].fillna(df_full_cap['dependency']).fillna(df_full_cap['institution'])

            # Obtener censo completo de esta institución desde Neo4j
            census_map = {}
            try:
                neo = Neo4jGraphStore()
                census_data = neo.get_hierarchical_academic_census(inst_name)
                neo.close()
                for c in census_data:
                    census_map[c['name']] = c
            except Exception as e:
                print(f"  ⚠️ Error de censo para {inst_name}: {e}")

            # Identificar todos los académicos únicos (unión de ambas fuentes)
            all_names = set(df_full_cap['academic_name'].unique()) | set(census_map.keys())

            for ac_name in all_names:
                if not ac_name or str(ac_name).lower() == 'none': continue

                df_ac = df_full_cap[df_full_cap['academic_name'] == ac_name]

                # Determinar afiliación (preferir ClickHouse si hay obra, si no Neo4j)
                if not df_ac.empty:
                    ac_entity = df_ac['entity'].mode()[0] if not df_ac['entity'].empty else inst_name
                else:
                    c_info = census_map.get(ac_name, {})
                    ac_entity = c_info.get('subdependency')
                    if not ac_entity or ac_entity == 'SIN INFORMACIÓN':
                        ac_entity = c_info.get('dependency')
                    if not ac_entity or ac_entity == 'SIN INFORMACIÓN':
                        ac_entity = inst_name

                # Filtro de entidad: si está activo, solo procesar académicos de esa entidad
                if entity_filter:
                    c_info = census_map.get(ac_name, {})
                    belong_census = (c_info.get('subdependency') == entity_filter or c_info.get('dependency') == entity_filter)
                    belong_click  = (not df_ac.empty and df_ac['entity'].iloc[0] == entity_filter)
                    if not (belong_census or belong_click):
                        continue

                _flush_academic(ac_name, df_ac.copy(), ac_entity, inst_name, updated_files)

            # 4. Agregación Bottom-Up (Dependencias y Subdependencias)
            # Solo si NO hay filtro de académico para no corromper agregados parciales
            if academic_filter:
                print(f"  ℹ️ Saltando agregaciones institucionales (filtro académico activo)")
                continue

            # Capacidad por Dependencia y Subdependencia
            if 'dependency' in df_full_cap.columns:
                for dep_name, df_dep in df_full_cap[df_full_cap['dependency'] != 'SIN INFORMACIÓN'].groupby('dependency'):
                    d_dep = CACHE_DIR / safe_inst / _safe_name(dep_name) / 'capacidad_instalada'
                    d_dep.mkdir(parents=True, exist_ok=True)
                    _save_aggregate_parquets(df_dep, d_dep, updated_files, label=dep_name, inst=inst_name, dep=dep_name)

                    # Subdependencias
                    if 'subdependency' in df_dep.columns:
                        for sub_name, df_sub in df_dep[df_dep['subdependency'] != 'SIN INFORMACIÓN'].groupby('subdependency'):
                            d_sub = CACHE_DIR / safe_inst / _safe_name(sub_name) / 'capacidad_instalada'
                            d_sub.mkdir(parents=True, exist_ok=True)
                            _save_aggregate_parquets(df_sub, d_sub, updated_files, label=sub_name, inst=inst_name, dep=dep_name, sub=sub_name)

            # Capacidad Institución (Total)
            if not entity_filter:
                cap_dir = CACHE_DIR / safe_inst / 'capacidad_instalada'
                _save_aggregate_parquets(df_full_cap, cap_dir, updated_files, label=inst_name, inst=inst_name)
                _save_aggregate_parquets(df_full_cap, CACHE_DIR / safe_inst, updated_files, label=inst_name, inst=inst_name)
                mx_cap_frames.append(df_full_cap)

        # 5. Producción Institucional (via Neo4j CREDITED_TO + JOIN works_academic_all)
        print(f"  ⏳ Consultando producción institucional desde Neo4j...")
        try:
            neo_prod = Neo4jGraphStore()
            oa_ids, dois = _fetch_paper_ids_from_neo4j(
                neo_prod, inst_name,
                entity_name=entity_filter  # None = nivel Institution
            )
            neo_prod.close()
        except Exception as e:
            print(f"  ⚠️ Error consultando Neo4j para producción: {e}")
            oa_ids, dois = [], []

        dep_label = entity_filter if entity_filter else 'SIN INFORMACIÓN'
        sub_label = entity_filter if entity_filter else 'SIN INFORMACIÓN'

        df_prod = _query_prod_neo4j(oa_ids, dois, inst_name, dep_label, sub_label)

        if not df_prod.empty:
            if not entity_filter:
                prod_dir = CACHE_DIR / safe_inst / 'produccion_institucional'
                _save_aggregate_parquets(df_prod, prod_dir, updated_files, label=inst_name, inst=inst_name)

            print(f"  🏛️ {df_prod['paper_id'].nunique():,} papers únicos (Producción Institucional - Indizada en OpenAlex)")

            # Reportar censo total desde Neo4j (Producción Total)
            try:
                neo_c = Neo4jGraphStore()
                target_e = entity_filter if entity_filter else None
                total_census = neo_c.get_total_paper_census(inst_name, target_e)
                print(f"  🌐 {total_census:,} papers totales en Censo Neo4j (Producción Total)")
                neo_c.close()
            except:
                pass

            # Producción por Dependencia y Subdependencia (anidada)
            if 'dependency' in df_prod.columns:
                for dep_name, df_dep_p in df_prod[df_prod['dependency'] != 'SIN INFORMACIÓN'].groupby('dependency'):
                    p_dep = CACHE_DIR / safe_inst / _safe_name(dep_name) / 'produccion_institucional'
                    _save_aggregate_parquets(df_dep_p, p_dep, updated_files, label=dep_name, inst=inst_name, dep=dep_name)

                    if 'subdependency' in df_dep_p.columns:
                        for sub_name, df_sub_p in df_dep_p[df_dep_p['subdependency'] != 'SIN INFORMACIÓN'].groupby('subdependency'):
                            p_sub = CACHE_DIR / safe_inst / _safe_name(sub_name) / 'produccion_institucional'
                            _save_aggregate_parquets(df_sub_p, p_sub, updated_files, label=sub_name, inst=inst_name, dep=dep_name, sub=sub_name)

        print(f"  ✅ Agregación completada para {inst_name}")

    # ── [3] Nivel México ──
    if mx_cap_frames and not academic_filter and not entity_filter and not institution_filter:
        print("\n⏳ Calculando métricas de México (Capacidad Instalada)...")
        df_mx = pd.concat(mx_cap_frames, ignore_index=True).drop_duplicates(subset=['paper_id'])
        mx_cap_dir = CACHE_DIR / 'MEXICO' / 'capacidad_instalada'
        _save_aggregate_parquets(df_mx, mx_cap_dir, updated_files, label='MEXICO')
        del df_mx

    # ── Nivel México — Producción Institucional ───────────────────────────
    if not academic_filter and not entity_filter and not institution_filter:
        print("⏳ Calculando métricas de México (Producción Institucional)...")
        df_mx_prod = _query_prod("")  # sin WHERE = todos los papers mexicanos
        if not df_mx_prod.empty:
            mx_prod_dir = CACHE_DIR / 'MEXICO' / 'produccion_institucional'
            _save_aggregate_parquets(df_mx_prod, mx_prod_dir, updated_files, label='MEXICO')
            print(f"  🇲🇽 {df_mx_prod['paper_id'].nunique():,} papers únicos en works_seed_mexico")
        del df_mx_prod

    # ── 5. PRECALCULO DE UMAP (Trayectorias) ──────────────────────────────────
    if UMAP and institution_filter and not academic_filter:
        print("\n⏳ Proyectando UMAP de Trayectorias (Desempeño Académico)...")
        # El DataFrame acumulado de investigadores para esta institución es df_inst (del loop principal)
        # Pero como se procesa por entidad, necesitamos recolectar los investigadores de la institución.
        # Por ahora, usaremos los parquets institucionales generados para reconstruir el UMAP.
        try:
            # Definir cap_dir para UMAP (respetando filtros)
            if entity_filter:
                cap_dir = CACHE_DIR / safe_inst / _safe_name(entity_filter) / 'capacidad_instalada'
            else:
                cap_dir = CACHE_DIR / safe_inst / 'capacidad_instalada'
                
            total_inst_path = cap_dir / 'institucion_total.parquet'
            if total_inst_path.exists():
                # Nota: UMAP requiere las métricas de CADA investigador, no el agregado institucional.
                # Buscaremos todos los parquets de investigadores bajo la carpeta de la institución.
                inv_files = list(cap_dir.glob('**/investigador_total.parquet'))
                if len(inv_files) >= 3:
                    inv_dfs = [pd.read_parquet(f) for f in inv_files]
                    umap_df = pd.concat(inv_dfs).drop_duplicates(subset=['academic_name'])
                    
                    features = ['pct_top_10', 'pct_1', 'percentile_avg', 'fwci_avg', 
                                'gini_topics', 'domain_diversity', 'unique_topics']
                    valid_df = umap_df.dropna(subset=features).copy()
                    
                    if len(valid_df) >= 3:
                        scaler = StandardScaler()
                        X_scaled = scaler.fit_transform(valid_df[features])
                        nn = min(15, len(valid_df) - 1)
                        reducer = UMAP(n_neighbors=nn, min_dist=0.1, random_state=42)
                        embedding = reducer.fit_transform(X_scaled)
                        valid_df['umap_x'] = embedding[:, 0]
                        valid_df['umap_y'] = embedding[:, 1]
                        
                        umap_out = cap_dir / 'umap_investigadores.parquet'
                        valid_df.to_parquet(umap_out, index=False)
                        print(f"  ✅ UMAP Generado para {len(valid_df)} investigadores en {cap_dir.name}")
                else:
                    print("  ⚠ Insuficientes investigadores para generar UMAP.")
        except Exception as e:
            print(f"  ⚠ Error en pre-cálculo de UMAP: {e}")

    print(f"\n✅ Completado. {len(updated_files)} archivos actualizados.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Calcula métricas bibliométricas desde ClickHouse (v3)')
    parser.add_argument('--entity',   help='Filtrar por entidad específica')
    parser.add_argument('--academic', help='Filtrar por académico específico')
    parser.add_argument('--institution', help='Filtrar por institución raíz')
    parser.add_argument('--source',   default='all')
    args = parser.parse_args()
    process_and_save(
        entity_filter=args.entity,
        academic_filter=args.academic,
        institution_filter=args.institution,
        source_filter=args.source
    )
