"""
compute_scholar_metrics_ch.py (v3)
===================================
Pipeline simplificado: ClickHouse es la única fuente de datos bibliométricos.

Fuentes:
  - Capacidad Instalada  : works_flat JOIN paper_author_map
  - Producción Inst. MX  : works_seed_mexico (papers firmados con institución MX)

Jerarquía de parquets generados:
  cache_ch/{institución}/{entidad}/{académico}/investigador_*.parquet
  cache_ch/{institución}/{entidad}/institucion_*.parquet
  cache_ch/{institución}/capacidad_instalada/institucion_*.parquet
  cache_ch/{institución}/produccion_institucional/institucion_*.parquet
  cache_ch/MEXICO/capacidad_instalada/institucion_*.parquet
  cache_ch/MEXICO/produccion_institucional/institucion_*.parquet
"""
import os, sys, argparse, importlib.util, warnings
import numpy as np
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
import unicodedata

warnings.filterwarnings('ignore')
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env')))

from database.clickhouse_db import ch_client

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

# Capacidad Instalada — papers identificados por OpenAlex Work ID (W...)
_Q_CAP_OA = """
SELECT
    pm.academic_name, pm.entity, pm.institution,
    pm.orcid, pm.openalex_id, pm.is_snii, pm.audit_verdict,
    wf.id           AS paper_id,
    wf.doi,
    wf.title        AS Title,
    wf.publication_year AS year,
    wf.cited_by_count   AS citations,
    wf.fwci,
    wf.percentile   AS citation_normalized_percentile,
    wf.is_top_10    AS is_in_top_10_percent,
    wf.is_top_1     AS is_in_top_1_percent,
    wf.is_oa, wf.oa_status,
    wf.topic_id AS topic, wf.subfield_name AS subfield, 
    wf.field_name AS field, wf.domain_name AS domain,
    wf.language, wf.type, wf.source_id AS Source, wf.source_type,
    wf.is_retracted, wf.referenced_works_count, wf.keywords, wf.sdgs AS ODS,
    wf.author_ids AS author_names, wf.country_codes AS all_country_codes
FROM works_flat wf
JOIN paper_author_map pm ON wf.id = pm.paper_id
LEFT JOIN topics t ON wf.topic_id = t.id
{filter}
"""

# Capacidad Instalada — papers identificados por DOI
_Q_CAP_DOI = """
SELECT
    pm.academic_name, pm.entity, pm.institution,
    pm.orcid, pm.openalex_id, pm.is_snii, pm.audit_verdict,
    wf.id           AS paper_id,
    wf.doi,
    wf.title        AS Title,
    wf.publication_year AS year,
    wf.cited_by_count   AS citations,
    wf.fwci,
    wf.percentile   AS citation_normalized_percentile,
    wf.is_top_10    AS is_in_top_10_percent,
    wf.is_top_1     AS is_in_top_1_percent,
    wf.is_oa, wf.oa_status,
    wf.topic_id AS topic, wf.subfield_name AS subfield, 
    wf.field_name AS field, wf.domain_name AS domain,
    wf.language, wf.type, wf.source_id AS Source, wf.source_type,
    wf.is_retracted, wf.referenced_works_count, wf.keywords, wf.sdgs AS ODS,
    wf.author_ids AS author_names, wf.country_codes AS all_country_codes
FROM works_flat wf
JOIN paper_author_map pm ON wf.doi = pm.paper_id
LEFT JOIN topics t ON wf.topic_id = t.id
{filter}
"""

# Producción Institucional: works_seed_mexico
_Q_PROD = """
SELECT
    id          AS paper_id,
    doi,
    title       AS Title,
    publication_year AS year,
    cited_by_count   AS citations,
    fwci,
    percentile  AS citation_normalized_percentile,
    is_top_10   AS is_in_top_10_percent,
    is_top_1    AS is_in_top_1_percent,
    is_oa,
    oa_status,
    topic,
    subfield,
    field,
    domain,
    language,
    type,
    source_id   AS Source,
    source_type,
    sdg_ids     AS ODS,
    author_names,
    all_country_codes,
    institution_rors
FROM works_seed_mexico
{filter}
"""


def _query_cap(filter_sql: str, params: dict = None) -> pd.DataFrame:
    """
    Ejecuta las dos variantes del JOIN (por OA ID y por DOI) y las combina.
    Esto es necesario porque paper_author_map puede contener tanto
    OpenAlex Work IDs (W...) como DOIs (https://doi.org/...) como paper_id.
    """
    p = params or {}
    frames = []
    for q_tmpl in [_Q_CAP_OA, _Q_CAP_DOI]:
        q = q_tmpl.format(filter=filter_sql)
        try:
            df = ch_client.query_df(q, parameters=p)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            print(f"  \u26a0\ufe0f query CH: {e}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=['paper_id', 'academic_name'])



def _query_prod(filter_sql: str, params: dict = None) -> pd.DataFrame:
    q = _Q_PROD.format(filter=filter_sql)
    return ch_client.query_df(q, parameters=params or {})


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
            
    # Otras columnas necesarias para aggregate_metrics (Legacy compatibility)
    df['has_oa_data'] = 1
    
    # 1. Autores y Países (Contar elementos si son listas)
    # El dashboard a veces espera la lista, a veces el conteo. 
    # El agregador original usa la lista para promediar len().
    
    # 2. Citas por año (Velocity fallback)
    if 'citations' in df.columns and 'year' in df.columns:
        # Calcular velocidad aproximada: citas / edad_del_paper
        current_year = 2026
        df['age'] = (current_year - df['year']).clip(lower=1)
        df['velocity'] = df['citations'] / df['age']
    
    # 3. Citas últimos 3 años (Fallback a 0 si no hay counts_by_year)
    df['recent_cites_3yr'] = 0
    
    # 4. Vida Media (Referenced works)
    if 'referenced_works_count' not in df.columns:
        df['referenced_works_count'] = 0
    
    # 5. ODS (Mapear IDs a nombres)
    if 'ODS' in df.columns:
        def _get_ods_names(x):
            if not isinstance(x, (list, np.ndarray)): return []
            return [ODS_MAP.get(str(i).split('/')[-1], str(i)) for i in x if i]
        df['ODS_Nombre'] = df['ODS'].apply(lambda x: _get_ods_names(x)[0] if _get_ods_names(x) else None)
    else:
        df['ODS_Nombre'] = None

    for c in ['keywords', 'ODS']:
        if c not in df.columns:
            df[c] = [[] for _ in range(len(df))]

    if 'referenced_works_count' not in df.columns:
        df['referenced_works_count'] = 0

    if 'counts_by_year' not in df.columns:
        df['counts_by_year'] = [[] for _ in range(len(df))]

    return df

    for c in ['apc_paid_usd', 'apc_list_usd']:
        if c not in df.columns:
            df[c] = 0.0

    for c in ['journal_is_in_doaj', 'journal_is_core', 'any_repository_has_fulltext']:
        if c not in df.columns:
            df[c] = 0

    if 'language' not in df.columns:
        df['language'] = 'en'
    if 'has_oa_data' not in df.columns:
        df['has_oa_data'] = 1

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
                              label: str = 'MEXICO'):
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

    # Añadir columna de agrupación para reutilizar aggregate_metrics
    df['_grp'] = label
    df['topics'] = _topics_as_list(df)

    _save_parquet(df, out_dir / 'papers_institucion.parquet', updated_files)
    
    df_tot = aggregate_metrics(df, ['_grp'])
    
    # Calcular Gini temático para la institución
    inter = compute_interdisciplinarity(df['topics'])
    for k, v in inter.items():
        df_tot[k] = v

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
            if isinstance(kws, list):
                cnt.update([k for k in kws if k])
        if cnt:
            kw_df = pd.DataFrame(cnt.most_common(1000), columns=['keyword', 'freq'])
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
    """Procesa y guarda los 7 parquets de un académico."""
    if df_ac.empty:
        return

    safe_inst = _safe_name(institution)
    safe_ent  = _safe_name(entity)
    safe_ac   = _safe_name(ac_name)
    d = CACHE_DIR / safe_inst / safe_ent / safe_ac

    df_ac = df_ac.drop_duplicates(subset=['paper_id']).copy()
    df_ac['year'] = pd.to_numeric(df_ac.get('year'), errors='coerce')

    # Columnas derivadas para el dashboard
    df_ac['entities']     = entity
    df_ac['institutions'] = institution
    df_ac['has_oa_data']  = 1
    df_ac['DOI']  = df_ac['doi'].apply(
        lambda x: f'https://doi.org/{x}' if x and str(x).startswith('10.') else x)
    df_ac['Link']         = df_ac['DOI']
    df_ac['openalex_url'] = df_ac['paper_id'].apply(
        lambda x: f'https://openalex.org/{x}' if x and str(x).startswith('W') else None)
    df_ac['topics'] = _topics_as_list(df_ac)
    df_ac['academic_name'] = ac_name

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


def process_and_save(entity_filter=None, academic_filter=None, 
                     source_filter='all', institution_filter=None):
    print("🚀 Iniciando pipeline v3 (ClickHouse JOIN directo)...")
    updated_files = set()

    # ── Obtener jerarquía desde Neo4j (para saber qué entidades procesar) ──
    print("\n[1] Cargando jerarquía institucional desde Neo4j...")
    from database.knowledge_graph import Neo4jGraphStore
    gs = Neo4jGraphStore()

    _HIER_QUERY = """
    MATCH (i:Institution)
    OPTIONAL MATCH (i)<-[:PART_OF]-(dep:Entity)
    OPTIONAL MATCH (dep)<-[:PART_OF]-(sub:Entity)
    RETURN i.name AS inst, dep.name AS dep, sub.name AS sub
    """
    # Mapa: {inst: {dep: [subs]}}
    hier = {}
    with gs.driver.session() as session:
        for r in session.run(_HIER_QUERY):
            inst = r["inst"]
            dep  = r["dep"]
            sub  = r["sub"]
            if not inst: continue
            if inst not in hier: hier[inst] = {}
            if dep:
                if dep not in hier[inst]: hier[inst][dep] = []
                if sub and sub not in hier[inst][dep]:
                    hier[inst][dep].append(sub)

    # Filtros opcionales
    if institution_filter:
        hier = {k: v for k, v in hier.items() if k == institution_filter}
        if not hier:
            print(f"⚠️ Institución '{institution_filter}' no encontrada en el grafo.")
            return

    if entity_filter:
        hier = {i: {e: s for e, s in ents.items() if e == entity_filter}
                for i, ents in hier.items() if entity_filter in ents}

    total_entities = sum(1 + len(subs) for ents in hier.values() for subs in ents.values())
    print(f"  → {len(hier)} institución(es) en jerarquía Neo4j")

    # Cargar mapa nombre → ROR para Producción Institucional
    ror_map = _get_institution_rors()
    mx_cap_frames = []
    done = 0

    # ── Procesar institución por institución ──────────────────────────────
    for inst_name, entities in hier.items():
        safe_inst = _safe_name(inst_name)
        print(f"\n📍 {inst_name}")

        # ─ Nivel Institución (todos sus académicos) ───────────────────────
        done += 1
        where = "WHERE pm.institution = %(inst)s AND pm.entity = %(ent)s"
        params = {'inst': inst_name, 'ent': inst_name}
        df_inst = _query_cap(where, params)

        if df_inst.empty:
            print(f"  ⚠️ Sin papers para la institución")
        else:
            df_inst = df_inst.drop_duplicates(subset=['paper_id', 'academic_name'])
            print(f"  📄 {len(df_inst):,} papers (nivel institución)")

            # Académicos individuales
            for ac_name, df_ac in df_inst.groupby('academic_name'):
                _flush_academic(ac_name, df_ac.copy(), inst_name, inst_name, updated_files)

            cap_dir = CACHE_DIR / safe_inst / 'capacidad_instalada'
            _save_aggregate_parquets(df_inst, cap_dir, updated_files, label=inst_name)

            cols_mx = ['paper_id', 'year', 'citations', 'fwci',
                       'citation_normalized_percentile', 'is_in_top_10_percent',
                       'is_in_top_1_percent', 'is_oa', 'oa_status',
                       'topic_name', 'subfield_name', 'field_name', 'domain_name',
                       'keywords', 'language', 'type']
            mx_cap_frames.append(df_inst[[c for c in cols_mx if c in df_inst.columns]])

        # Producción Institucional via ROR
        rors = ror_map.get(inst_name, [])
        if rors:
            ror_list = ', '.join(f"'{r}'" for r in rors)
            df_prod = _query_prod(f"WHERE hasAny(institution_rors, [{ror_list}])")
            if not df_prod.empty:
                prod_dir = CACHE_DIR / safe_inst / 'produccion_institucional'
                _save_aggregate_parquets(df_prod, prod_dir, updated_files, label=inst_name)
                print(f"  🏛️ {len(df_prod):,} papers (Prod. Institucional)")

        # ─ Nivel Dependencia y Subdependencia ────────────────────────────
        for dep_name, subs in entities.items():
            safe_dep = _safe_name(dep_name)
            done += 1

            # Dependencia
            df_dep = _query_cap(
                "WHERE pm.institution = %(inst)s AND pm.entity = %(ent)s",
                {'inst': inst_name, 'ent': dep_name})
            if not df_dep.empty:
                df_dep = df_dep.drop_duplicates(subset=['paper_id', 'academic_name'])
                print(f"  ├─ {dep_name}: {len(df_dep):,} papers")
                dep_dir = CACHE_DIR / safe_inst / safe_dep
                _save_aggregate_parquets(df_dep, dep_dir, updated_files, label=dep_name)

            # Subdependencias
            for sub_name in subs:
                safe_sub = _safe_name(sub_name)
                df_sub = _query_cap(
                    "WHERE pm.institution = %(inst)s AND pm.entity = %(ent)s",
                    {'inst': inst_name, 'ent': sub_name})
                if not df_sub.empty:
                    df_sub = df_sub.drop_duplicates(subset=['paper_id', 'academic_name'])
                    print(f"  │  └─ {sub_name}: {len(df_sub):,} papers")
                    # Académicos a nivel subdependencia
                    for ac_name, df_ac in df_sub.groupby('academic_name'):
                        _flush_academic(ac_name, df_ac.copy(), sub_name, inst_name, updated_files)
                    sub_dir = CACHE_DIR / safe_inst / safe_sub
                    _save_aggregate_parquets(df_sub, sub_dir, updated_files, label=sub_name)
                    del df_sub
            if not df_dep.empty:
                del df_dep
        if 'df_inst' in dir() and df_inst is not None:
            del df_inst

    # ── Nivel México — Capacidad Instalada ────────────────────────────────
    if mx_cap_frames and not academic_filter and not entity_filter:
        print("\n⏳ Calculando métricas de México (Capacidad Instalada)...")
        df_mx = pd.concat(mx_cap_frames, ignore_index=True).drop_duplicates(subset=['paper_id'])
        mx_cap_dir = CACHE_DIR / 'MEXICO' / 'capacidad_instalada'
        _save_aggregate_parquets(df_mx, mx_cap_dir, updated_files, label='MEXICO')
        del df_mx

    # ── Nivel México — Producción Institucional ───────────────────────────
    if not academic_filter and not entity_filter:
        print("⏳ Calculando métricas de México (Producción Institucional)...")
        df_mx_prod = _query_prod("")  # sin WHERE = todos los papers mexicanos
        if not df_mx_prod.empty:
            mx_prod_dir = CACHE_DIR / 'MEXICO' / 'produccion_institucional'
            _save_aggregate_parquets(df_mx_prod, mx_prod_dir, updated_files, label='MEXICO')
            print(f"  🇲🇽 {len(df_mx_prod):,} papers en works_seed_mexico")
        del df_mx_prod

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
        source_filter=args.source)
