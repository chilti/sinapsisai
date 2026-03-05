"""
Cálculo de Métricas y Trayectorias (Offline)
Extrae datos de Neo4j y precalcula los indicadores para el dashboard.
 Guarda los resultados en data/cache/*.parquet para consulta rápida en Streamlit.
"""
import os
import sys
import json
import numpy as np

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass
import pandas as pd
from pathlib import Path
from umap import UMAP
from sklearn.preprocessing import StandardScaler

import warnings
warnings.filterwarnings('ignore') # UMAP genera warnings de numba

# Añadir el path del grafo
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

BASE_PATH = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
CACHE_DIR = BASE_PATH / 'data' / 'cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _get_h_index(citations_list):
    """Calcula el índice H a partir de una lista de citas."""
    cites = sorted([c for c in citations_list if pd.notnull(c)], reverse=True)
    h = 0
    for i, c in enumerate(cites):
        if c >= (i + 1):
            h = i + 1
        else:
            break
    return h

CURRENT_YEAR = 2026

def compute_citation_velocity(counts_by_year, pub_year) -> dict:
    """
    Deriva métricas de trayectoria de citas a partir de counts_by_year de OpenAlex.
    Retorna: velocity (citas/año), recent_cites_3yr, early_impact (año de pub +1),
             peak_year y half_life (año en que se acumuló el 50% de las citas).
    """
    if not isinstance(counts_by_year, list) or not counts_by_year:
        return {'velocity': np.nan, 'recent_cites_3yr': 0,
                'early_impact': 0, 'peak_year': pub_year, 'half_life': np.nan}
    try:
        pub_year = int(pub_year)
    except (TypeError, ValueError):
        return {'velocity': np.nan, 'recent_cites_3yr': 0,
                'early_impact': 0, 'peak_year': pub_year, 'half_life': np.nan}

    age   = max(1, CURRENT_YEAR - pub_year)
    total = sum(y.get('cited_by_count', 0) for y in counts_by_year)
    recent = sum(y.get('cited_by_count', 0) for y in counts_by_year
                 if y.get('year', 0) >= CURRENT_YEAR - 3)
    early  = sum(y.get('cited_by_count', 0) for y in counts_by_year
                 if y.get('year', 0) <= pub_year + 1)
    peak_entry = max(counts_by_year, key=lambda x: x.get('cited_by_count', 0), default={})
    peak_year  = peak_entry.get('year', pub_year)

    # Vida media: año en que se acumula el 50% de las citas
    half_life = np.nan
    if total > 0:
        sorted_by_year = sorted(counts_by_year, key=lambda x: x.get('year', 0))
        cumsum = 0
        for entry in sorted_by_year:
            cumsum += entry.get('cited_by_count', 0)
            if cumsum >= total / 2:
                half_life = CURRENT_YEAR - entry.get('year', CURRENT_YEAR)
                break

    return {
        'velocity':         round(total / age, 3),
        'recent_cites_3yr': int(recent),
        'early_impact':     int(early),
        'peak_year':        int(peak_year),
        'half_life':        half_life,
    }

def compute_interdisciplinarity(topics_series) -> dict:
    """
    Calcula métricas temáticas de un grupo de papers (serie de listas de topics).
    - gini_topics:       Gini sobre distribución de cuentas por topic (0=mono, 1=disperso)
    - domain_diversity:  Número de dominios distintos cubiertos (0-4)
    - unique_topics:     Número de topics únicos
    - top_topic:         Topic más frecuente
    - top_domain:        Dominio más frecuente
    """
    from collections import Counter
    topic_counts   = Counter()
    domain_counts  = Counter()

    for topics in topics_series:
        if not isinstance(topics, list):
            continue
        for t in topics:
            if not isinstance(t, dict):
                continue
            topic_name  = t.get('topic')
            domain_name = t.get('domain')
            if topic_name:
                topic_counts[topic_name]  += 1
            if domain_name:
                domain_counts[domain_name] += 1

    if not topic_counts:
        return {
            'gini_topics': np.nan, 'domain_diversity': 0,
            'unique_topics': 0, 'top_topic': None, 'top_domain': None
        }

    # Gini sobre counts de topics
    counts = np.array(sorted(topic_counts.values()), dtype=float)
    n = len(counts)
    if n > 1:
        cum = np.cumsum(counts)
        gini = 1 - (2 * cum.sum() - counts.sum() + counts[-1]) / (n * counts.sum())
        gini = round(float(np.clip(gini, 0, 1)), 4)
    else:
        gini = 0.0

    top_topic  = topic_counts.most_common(1)[0][0]
    top_domain = domain_counts.most_common(1)[0][0] if domain_counts else None

    return {
        'gini_topics':     gini,
        'domain_diversity': len(domain_counts),
        'unique_topics':   len(topic_counts),
        'top_topic':       top_topic,
        'top_domain':      top_domain,
    }


def extract_academic_papers():

    """Descarga los metadatos completos de todas las publicaciones por Académico."""
    graph_store = Neo4jGraphStore()
    
    query = """
    MATCH (a:Academic)-[:AUTHORED]->(p)
    OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity)
    OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
    OPTIONAL MATCH (p)-[:HAS_TOPIC]->(t:Topic)
    RETURN a.name AS academic_name,
           a.orcid AS orcid,
           a.scopus_id AS scopus_id,
           a.siia_url AS siia_url,
           collect(DISTINCT e.name) AS entities,
           p.id AS paper_id,
           p.year AS year,
           p.citations AS citations,
           p.raw_metadata AS raw_metadata,
           collect(DISTINCT {id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}) AS sdgs,
           collect(DISTINCT {topic: t.name, domain: t.domain, field: t.field, subfield: t.subfield}) AS graph_topics
    """
    
    records = []
    with graph_store.driver.session() as session:
        result = session.run(query)
        for row in result:
            raw_meta = {}
            if row['raw_metadata']:
                try:
                    raw_meta = json.loads(row['raw_metadata'])
                except:
                    pass
            
            # Robust Extraction (handles both ingest_apis and ingest_entity_docs formats)
            fwci = raw_meta.get('fwci')
            if fwci is None and 'raw_metadata' in raw_meta:
                fwci = raw_meta['raw_metadata'].get('fwci')

            title = raw_meta.get('Title') or raw_meta.get('title') or raw_meta.get('TI') or 'No Title'
            source = raw_meta.get('Source') or raw_meta.get('source_title') or raw_meta.get('journal_iso_source_abbreviation') or raw_meta.get('publication_name') or raw_meta.get('SO') or 'Unknown'
            doi_link = "https://doi.org/" + row['paper_id'] if row['paper_id'] and not "urn:" in row['paper_id'] else None
            
            # Open Access Logic
            is_oa = False
            oa_status = 'closed'
            oa_data = raw_meta.get('open_access')
            if oa_data is None and 'raw_metadata' in raw_meta:
                oa_data = raw_meta['raw_metadata'].get('open_access')

            if isinstance(oa_data, dict):
                is_oa = oa_data.get('is_oa', False)
                oa_status = str(oa_data.get('oa_status', 'closed')).lower()
            elif 'OA' in raw_meta:
                 oa_str = str(raw_meta.get('OA', '')).lower()
                 if 'green' in oa_str: oa_status = 'green'
                 elif 'gold' in oa_str: oa_status = 'gold'
                 elif 'hybrid' in oa_str: oa_status = 'hybrid'
                 elif 'bronze' in oa_str: oa_status = 'bronze'
                 is_oa = oa_status != 'closed'
                 
            is_in_top_10_percent = raw_meta.get('is_in_top_10_percent')
            if is_in_top_10_percent is None and 'raw_metadata' in raw_meta:
                is_in_top_10_percent = raw_meta['raw_metadata'].get('is_in_top_10_percent')
            is_in_top_10_percent = int(is_in_top_10_percent or 0)

            is_in_top_1_percent = raw_meta.get('is_in_top_1_percent')
            if is_in_top_1_percent is None and 'raw_metadata' in raw_meta:
                is_in_top_1_percent = raw_meta['raw_metadata'].get('is_in_top_1_percent')
            is_in_top_1_percent = int(is_in_top_1_percent or 0)

            citation_normalized_percentile = raw_meta.get('citation_normalized_percentile')
            if citation_normalized_percentile is None and 'raw_metadata' in raw_meta:
                citation_normalized_percentile = raw_meta['raw_metadata'].get('citation_normalized_percentile')
            citation_normalized_percentile = float(citation_normalized_percentile) if citation_normalized_percentile is not None else np.nan
            
            topics = raw_meta.get('OpenAlex_Topics') or raw_meta.get('topics')
            if topics is None and 'raw_metadata' in raw_meta:
                topics = raw_meta['raw_metadata'].get('OpenAlex_Topics') or raw_meta['raw_metadata'].get('topics')
            # Fallback: usar los nodos :Topic del grafo si raw_metadata no tiene topics
            if not isinstance(topics, list) or not topics:
                graph_topics = row.get('graph_topics', []) or []
                topics = [
                    {'topic': gt['topic'], 'domain': gt.get('domain', ''), 'field': gt.get('field', ''), 'subfield': gt.get('subfield', '')}
                    for gt in graph_topics if gt.get('topic')
                ]
            if not isinstance(topics, list): topics = []
            
            # Manejo de ODS (primer ODS para retrocompatibilidad de columnas planas si se requiere, 
            # pero la lista completa está en 'sdgs')
            sdg_id, sdg_name, sdg_conf, sdg_reas = None, None, None, None
            if row['sdgs']:
                first_sdg = [s for s in row['sdgs'] if s['id'] is not None]
                if first_sdg:
                    sdg_id = first_sdg[0]['id']
                    sdg_name = first_sdg[0]['name']
                    sdg_conf = first_sdg[0]['confidence']
                    sdg_reas = first_sdg[0]['reasoning']

            records.append({
                'academic_name': row['academic_name'],
                'orcid':     row['orcid'],
                'scopus_id': row['scopus_id'],
                'siia_url':  row['siia_url'],
                'entities':  ";".join(row['entities']) if row['entities'] else "",
                'paper_id':  row['paper_id'],
                'year':      row['year'],
                'citations': row['citations'],
                'Title':  title,
                'Source': source,
                'DOI':    doi_link,
                'Link':   doi_link,
                'openalex_url': raw_meta.get('openalex_url'),
                # ── Impacto ────────────────────────────────────────────────────
                'fwci':                         fwci,
                'is_oa':                        int(is_oa),
                'oa_status':                    oa_status,
                'is_in_top_10_percent':         is_in_top_10_percent,
                'is_in_top_1_percent':          is_in_top_1_percent,
                'citation_normalized_percentile': citation_normalized_percentile,
                # ── Trayectoria de citas ────────────────────────────────────────
                'counts_by_year':        raw_meta.get('counts_by_year', []),
                'referenced_works_count': int(raw_meta.get('referenced_works_count', 0) or 0),
                'referenced_works':      raw_meta.get('referenced_works', []),
                # ── APC ─────────────────────────────────────────────────────────
                'apc_paid_usd': float(raw_meta.get('apc_paid_usd', 0) or 0),
                'apc_list_usd': float(raw_meta.get('apc_list_usd', 0) or 0),
                # ── Colaboración ────────────────────────────────────────────────
                'author_count':             int(raw_meta.get('author_count', 0) or 0),
                'countries_distinct_count': int(raw_meta.get('countries_distinct_count', 0) or 0),
                'institutions_distinct_count': int(raw_meta.get('institutions_distinct_count', 0) or 0),
                'countries':            raw_meta.get('countries', []),
                'coauthor_institutions': raw_meta.get('coauthor_institutions', []),
                # ── OA avanzado ─────────────────────────────────────────────────
                'license':                   raw_meta.get('license'),
                'any_repository_has_fulltext': bool(raw_meta.get('any_repository_has_fulltext', False)),
                'locations_count':           int(raw_meta.get('locations_count', 0) or 0),
                'oa_url':                    raw_meta.get('oa_url'),
                # ── Indexación ─────────────────────────────────────────────────
                'indexed_in':        raw_meta.get('indexed_in', []),
                'is_retracted':      bool(raw_meta.get('is_retracted', False)),
                'language':          raw_meta.get('language', 'en') or 'en',
                'type':              raw_meta.get('type', 'article'),
                # ── Revista ────────────────────────────────────────────────────
                'journal_is_oa':      bool(raw_meta.get('journal_is_oa', False)),
                'journal_is_in_doaj': bool(raw_meta.get('journal_is_in_doaj', False)),
                'journal_is_core':    bool(raw_meta.get('journal_is_core', False)),
                'issn':               raw_meta.get('issn'),
                # ── Tópico primario ─────────────────────────────────────────────
                'primary_topic_name':     raw_meta.get('primary_topic_name'),
                'primary_topic_domain':   raw_meta.get('primary_topic_domain'),
                'primary_topic_field':    raw_meta.get('primary_topic_field'),
                'primary_topic_subfield': raw_meta.get('primary_topic_subfield'),
                'primary_topic_score':    raw_meta.get('primary_topic_score'),
                'keywords':              raw_meta.get('keywords', []),
                # ── Tópicos y ODS ──────────────────────────────────────────────
                'topics': topics,
                'ODS_ID':           sdg_id,
                'ODS_Nombre':       sdg_name,
                'ODS_Confianza':    sdg_conf,
                'ODS_Justificacion': sdg_reas
            })
            
    return pd.DataFrame(records)

def extract_entity_papers():
    """Descarga los papers asociados históricamente a una Institución/Entidad."""
    graph_store = Neo4jGraphStore()
    query = """
    MATCH (e:Entity)-[:HAS_PAPER]->(p:Paper)
    OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
    RETURN e.name AS entity_name,
           p.id AS paper_id,
           p.year AS year,
           p.citations AS citations,
           p.raw_metadata AS raw_metadata,
           collect({id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}) AS sdgs
    """
    records = []
    with graph_store.driver.session() as session:
        result = session.run(query)
        for row in result:
            raw_meta = {}
            if row['raw_metadata']:
                try:
                    raw_meta = json.loads(row['raw_metadata'])
                except:
                    pass
            
            # Robust Extraction (handles both ingest_apis and ingest_entity_docs formats)
            fwci = raw_meta.get('fwci')
            if fwci is None and 'raw_metadata' in raw_meta:
                fwci = raw_meta['raw_metadata'].get('fwci')

            title = raw_meta.get('Title') or raw_meta.get('title') or raw_meta.get('TI') or 'No Title'
            source = raw_meta.get('Source') or raw_meta.get('source_title') or raw_meta.get('journal_iso_source_abbreviation') or raw_meta.get('publication_name') or raw_meta.get('SO') or 'Unknown'
            doi_link = "https://doi.org/" + row['paper_id'] if row['paper_id'] and not "urn:" in row['paper_id'] else None
            
            # Open Access Logic
            is_oa = False
            oa_status = 'closed'
            oa_data = raw_meta.get('open_access')
            if oa_data is None and 'raw_metadata' in raw_meta:
                oa_data = raw_meta['raw_metadata'].get('open_access')

            if isinstance(oa_data, dict):
                is_oa = oa_data.get('is_oa', False)
                oa_status = str(oa_data.get('oa_status', 'closed')).lower()
            elif 'OA' in raw_meta:
                 oa_str = str(raw_meta.get('OA', '')).lower()
                 if 'green' in oa_str: oa_status = 'green'
                 elif 'gold' in oa_str: oa_status = 'gold'
                 elif 'hybrid' in oa_str: oa_status = 'hybrid'
                 elif 'bronze' in oa_str: oa_status = 'bronze'
                 is_oa = oa_status != 'closed'
                 
            is_in_top_10_percent = raw_meta.get('is_in_top_10_percent')
            if is_in_top_10_percent is None and 'raw_metadata' in raw_meta:
                is_in_top_10_percent = raw_meta['raw_metadata'].get('is_in_top_10_percent')
            is_in_top_10_percent = int(is_in_top_10_percent or 0)

            is_in_top_1_percent = raw_meta.get('is_in_top_1_percent')
            if is_in_top_1_percent is None and 'raw_metadata' in raw_meta:
                is_in_top_1_percent = raw_meta['raw_metadata'].get('is_in_top_1_percent')
            is_in_top_1_percent = int(is_in_top_1_percent or 0)

            citation_normalized_percentile = raw_meta.get('citation_normalized_percentile')
            if citation_normalized_percentile is None and 'raw_metadata' in raw_meta:
                citation_normalized_percentile = raw_meta['raw_metadata'].get('citation_normalized_percentile')
            citation_normalized_percentile = float(citation_normalized_percentile) if citation_normalized_percentile is not None else np.nan
            
            topics = raw_meta.get('OpenAlex_Topics') or raw_meta.get('topics')
            if topics is None and 'raw_metadata' in raw_meta:
                topics = raw_meta['raw_metadata'].get('OpenAlex_Topics') or raw_meta['raw_metadata'].get('topics')
            if not isinstance(topics, list): topics = []
            
            # Manejo de ODS
            sdg_id, sdg_name, sdg_conf, sdg_reas = None, None, None, None
            if row['sdgs']:
                first_sdg = [s for s in row['sdgs'] if s['id'] is not None]
                if first_sdg:
                    sdg_id = first_sdg[0]['id']
                    sdg_name = first_sdg[0]['name']
                    sdg_conf = first_sdg[0]['confidence']
                    sdg_reas = first_sdg[0]['reasoning']

            records.append({
                'entity_name': row['entity_name'],
                'paper_id': row['paper_id'],
                'year': row['year'],
                'citations': row['citations'],
                'Title': title,
                'Source': source,
                'DOI': doi_link,
                'Link': doi_link,
                'fwci': fwci,
                'is_oa': int(is_oa),
                'oa_status': oa_status,
                'is_in_top_10_percent': is_in_top_10_percent,
                'is_in_top_1_percent': is_in_top_1_percent,
                'citation_normalized_percentile': citation_normalized_percentile,
                'topics': topics,
                'ODS_ID': sdg_id,
                'ODS_Nombre': sdg_name,
                'ODS_Confianza': sdg_conf,
                'ODS_Justificacion': sdg_reas
            })
            
    return pd.DataFrame(records)

def aggregate_metrics(df_papers, group_cols):
    """Realiza la agregación principal de base para los grupos especificados usando los datos nativos de OpenAlex."""
    if df_papers.empty: return pd.DataFrame()
    
    # Preparamos las columnas
    if 'fwci' in df_papers.columns:
        df_papers['fwci'] = pd.to_numeric(df_papers['fwci'], errors='coerce')
    if 'is_in_top_10_percent' in df_papers.columns:
        df_papers['is_in_top_10_percent'] = pd.to_numeric(df_papers['is_in_top_10_percent'], errors='coerce').fillna(0).astype(int)
    if 'is_in_top_1_percent' in df_papers.columns:
        df_papers['is_in_top_1_percent'] = pd.to_numeric(df_papers['is_in_top_1_percent'], errors='coerce').fillna(0).astype(int)
    if 'citation_normalized_percentile' in df_papers.columns:
        df_papers['citation_normalized_percentile'] = pd.to_numeric(df_papers['citation_normalized_percentile'], errors='coerce')
    
    if 'oa_status' in df_papers.columns:
        df_papers['is_oa_gold']   = (df_papers['oa_status'] == 'gold').astype(int)
        df_papers['is_oa_green']  = (df_papers['oa_status'] == 'green').astype(int)
        df_papers['is_oa_hybrid'] = (df_papers['oa_status'] == 'hybrid').astype(int)
        df_papers['is_oa_bronze'] = (df_papers['oa_status'] == 'bronze').astype(int)
        df_papers['is_oa_closed'] = (df_papers['oa_status'] == 'closed').astype(int)

    # ── Nuevos campos de alto impacto ───────────────────────────────
    # Máscara de papers SIN enriquecimiento de OpenAlex.
    # (fwci es el indicador más confiable de que OpenAlex procesó el paper)
    _has_oa = df_papers.get('fwci', pd.Series([np.nan]*len(df_papers))).notna()

    # Velocidad de citas por paper
    if 'counts_by_year' in df_papers.columns and 'year' in df_papers.columns:
        vel_data = df_papers.apply(
            lambda r: compute_citation_velocity(
                r.get('counts_by_year', []), r.get('year', CURRENT_YEAR)
            ), axis=1, result_type='expand'
        )
        for col in ['velocity', 'recent_cites_3yr', 'early_impact', 'half_life']:
            df_papers[col] = vel_data[col]
    else:
        for col in ['velocity', 'recent_cites_3yr', 'early_impact', 'half_life']:
            df_papers[col] = np.nan

    # APC — suma bruta mantiene 0 válido; % sólo sobre papers con datos OA
    for col in ['apc_paid_usd', 'apc_list_usd']:
        if col in df_papers.columns:
            df_papers[col] = pd.to_numeric(df_papers[col], errors='coerce').fillna(0)
        else:
            df_papers[col] = 0.0
    # has_apc: NaN para papers sin información OA, 1/0 para los que sí tienen
    df_papers['has_apc'] = np.where(_has_oa, (df_papers['apc_paid_usd'] > 0).astype(float), np.nan)

    # Colaboración — usar NaN para papers sin enriquecimiento OA
    if 'countries_distinct_count' in df_papers.columns:
        df_papers['countries_distinct_count'] = pd.to_numeric(df_papers['countries_distinct_count'], errors='coerce')
        # is_international: 1/0/NaN según si hay datos de OA
        df_papers['is_international'] = np.where(
            _has_oa,
            (df_papers['countries_distinct_count'].fillna(0) >= 2).astype(float),
            np.nan
        )
        # avg_countries: NaN si no hay datos OA
        df_papers.loc[~_has_oa, 'countries_distinct_count'] = np.nan
    else:
        df_papers['countries_distinct_count'] = np.nan
        df_papers['is_international'] = np.nan

    if 'author_count' in df_papers.columns:
        df_papers['author_count'] = pd.to_numeric(df_papers['author_count'], errors='coerce')
        # Si no hay ó si es 0 y no hay datos OA, dejar NaN
        df_papers.loc[~_has_oa | (df_papers['author_count'] == 0), 'author_count'] = np.nan
    else:
        df_papers['author_count'] = np.nan

    # Indexación y acceso
    for bool_col in ['journal_is_in_doaj', 'journal_is_core', 'is_retracted', 'any_repository_has_fulltext']:
        if bool_col in df_papers.columns:
            df_papers[bool_col] = df_papers[bool_col].fillna(False).astype(int)
        else:
            df_papers[bool_col] = 0

    if 'indexed_in' in df_papers.columns:
        df_papers['in_pubmed'] = df_papers['indexed_in'].apply(
            lambda x: int('pubmed' in (x or [])) if isinstance(x, list) else 0
        )
        df_papers['in_doaj'] = df_papers['indexed_in'].apply(
            lambda x: int('doaj' in (x or [])) if isinstance(x, list) else 0
        )
    else:
        df_papers['in_pubmed'] = 0
        df_papers['in_doaj']   = 0

    if 'language' in df_papers.columns:
        df_papers['is_english'] = (df_papers['language'].fillna('').str.lower() == 'en').astype(int)
    else:
        df_papers['is_english'] = 0

    if 'license' in df_papers.columns:
        df_papers['is_cc_by'] = (df_papers['license'].fillna('').str.lower().str.contains('cc-by', na=False)).astype(int)
    else:
        df_papers['is_cc_by'] = 0

    agg_funcs = {
        'paper_id': 'count',
        'citations': 'sum',
        'fwci': 'mean',
        'citation_normalized_percentile': 'mean',
        'is_in_top_10_percent': 'mean',
        'is_in_top_1_percent': 'mean',
        'is_oa': 'mean',
        'is_oa_gold': 'mean',
        'is_oa_green': 'mean',
        'is_oa_hybrid': 'mean',
        'is_oa_bronze': 'mean',
        'is_oa_closed': 'mean',
        # Velocidad de citas
        'velocity':          'mean',
        'recent_cites_3yr':  'sum',
        'early_impact':      'mean',
        'half_life':         'mean',
        # APC
        'apc_paid_usd': 'sum',
        'apc_list_usd': 'sum',
        'has_apc':      'mean',
        # Colaboración
        'is_international':       'mean',
        'countries_distinct_count': 'mean',
        'author_count':           'mean',
        # Indexación / visibilidad
        'in_pubmed':             'mean',
        'in_doaj':               'mean',
        'journal_is_in_doaj':    'mean',
        'journal_is_core':       'mean',
        'is_retracted':          'mean',
        'any_repository_has_fulltext': 'mean',
        # Idioma y licencia
        'is_english': 'mean',
        'is_cc_by':   'mean',
    }
    
    # Agregar columnas informativas si existen y no están en group_cols
    for col in ['orcid', 'scopus_id', 'entities', 'siia_url']:
        if col in df_papers.columns and col not in group_cols:
            agg_funcs[col] = 'first'
    
    df_agg = df_papers.groupby(group_cols).agg(agg_funcs).reset_index()
    df_agg.rename(columns={
        'paper_id':                       'num_documents',
        'fwci':                           'fwci_avg',
        'citation_normalized_percentile': 'percentile_avg',
        'is_in_top_10_percent':           'pct_top_10',
        'is_in_top_1_percent':            'pct_1',
        'is_oa':                          'pct_open_access',
        'is_oa_gold':                     'pct_oa_gold',
        'is_oa_green':                    'pct_oa_green',
        'is_oa_hybrid':                   'pct_oa_hybrid',
        'is_oa_bronze':                   'pct_oa_bronze',
        'is_oa_closed':                   'pct_oa_closed',
        # Velocidad
        'velocity':          'velocity_avg',
        'half_life':         'half_life_avg',
        # APC
        'has_apc':           'pct_apc',
        # Colaboración
        'is_international':         'pct_international',
        'countries_distinct_count': 'avg_countries',
        'author_count':             'avg_author_count',
        # Indexación
        'in_pubmed':                'pct_pubmed',
        'in_doaj':                  'pct_doaj_indexed',
        'journal_is_in_doaj':       'pct_doaj_journal',
        'journal_is_core':          'pct_core_journal',
        'is_retracted':             'pct_retracted',
        'any_repository_has_fulltext': 'pct_repository',
        # Idioma / licencia
        'is_english':        'pct_english',
        'is_cc_by':          'pct_cc_by',
    }, inplace=True)

    # pct a base 100
    pct_cols = ['pct_top_10', 'pct_1', 'pct_open_access', 'pct_oa_gold', 'pct_oa_green',
                'pct_oa_hybrid', 'pct_oa_bronze', 'pct_oa_closed',
                'pct_apc', 'pct_international', 'pct_pubmed', 'pct_doaj_indexed',
                'pct_doaj_journal', 'pct_core_journal', 'pct_retracted',
                'pct_repository', 'pct_english', 'pct_cc_by']
    for col in pct_cols:
        if col in df_agg.columns:
            df_agg[col] *= 100

    # Llenar nulos - FWCI NO se debe llenar con citas/doc, se queda como NaN si no hay data.
    df_agg['fwci_avg'] = df_agg['fwci_avg'].replace([np.inf, -np.inf], np.nan)
    df_agg['percentile_avg'] = df_agg['percentile_avg'].replace([np.inf, -np.inf], np.nan)
    
    # Calcular Citations per Paper (CPP)
    df_agg['citations_per_paper'] = df_agg['citations'] / df_agg['num_documents'].replace(0, 1)
    
    # Calcular indice H para el agrupamiento
    h_series = df_papers.groupby(group_cols)['citations'].apply(list).apply(_get_h_index).reset_index(name='h_index')
    
    df_agg = df_agg.merge(h_series, on=group_cols, how='left')
    return df_agg

def process_and_save():
    print("Iniciando Pre-cálculo de Métricas desde Neo4j...")
    
    # 1. Extracción y Enriquecimiento
    df_raw = extract_academic_papers()
    if df_raw.empty:
        print("❌ No se encontraron datos de publicaciones en Neo4j. Ingeste datos primero.")
        return
        
    print(f"✅ {len(df_raw)} publicaciones extraídas.")
    df_raw['year'] = pd.to_numeric(df_raw['year'], errors='coerce')
    df_raw = df_raw.dropna(subset=['year'])
    # Filtrar años inválidos (0 o muy antiguos) para evitar errores en gráficas temporales
    df_raw = df_raw[df_raw['year'] >= 1900] 
    
    # Exportar listado general de papers de Académicos
    df_raw.to_parquet(CACHE_DIR / 'papers_profesor.parquet', index=False)
    
    # TOPICOS SUNBURST
    print("⏳ Precalculando agrupaciones de Tópicos (Sunburst)...")
    topics_list = []
    for _, row in df_raw.iterrows():
        ac_name = row['academic_name']
        year = row['year']
        topics = row.get('topics', [])
        if isinstance(topics, list):
            for t in topics:
                if isinstance(t, dict) and t.get('topic'):
                    topics_list.append({
                        'academic_name': ac_name,
                        'year': year,
                        'domain': t.get('domain', 'Unknown'),
                        'field': t.get('field', 'Unknown'),
                        'subfield': t.get('subfield', 'Unknown'),
                        'topic': t.get('topic', 'Unknown')
                    })
    if topics_list:
        df_topics = pd.DataFrame(topics_list)
        df_topics['count'] = 1
        df_topics_agg = df_topics.groupby(['academic_name', 'domain', 'field', 'subfield', 'topic']).size().reset_index(name='value')
    else:
        # Escribir parquet vacío para que el dashboard muestre mensaje en vez de None
        print("⚠️  No se encontraron tópicos en raw_metadata ni en nodos :Topic del grafo.")
        df_topics_agg = pd.DataFrame(columns=['academic_name', 'domain', 'field', 'subfield', 'topic', 'value'])
    df_topics_agg.to_parquet(CACHE_DIR / 'topics_investigador.parquet', index=False)
    # Limpiar archivos de versiones anteriores si existen
    if os.path.exists(CACHE_DIR / 'concepts_investigador.parquet'):
        os.remove(CACHE_DIR / 'concepts_investigador.parquet')
    if os.path.exists(CACHE_DIR / 'concepts_institucion.parquet'):
        os.remove(CACHE_DIR / 'concepts_institucion.parquet')

    # 2. AGREGARES A NIVEL INVESTIGADOR
    print("⏳ Agregando métricas a nivel Investigador...")
    # Agregamos 'entities' para conservar las afiliaciones en el agrupamiento
    df_inv_annual = aggregate_metrics(df_raw, ['academic_name', 'entities', 'year'])
    df_inv_annual.to_parquet(CACHE_DIR / 'investigador_annual.parquet', index=False)
    
    df_inv_tot = aggregate_metrics(df_raw, ['academic_name', 'entities'])

    # ── Interdisciplinariedad por investigador ─────────────────────────────────
    print("⏳ Calculando índice de interdisciplinariedad por investigador...")
    if 'topics' in df_raw.columns:
        inter_rows = []
        for ac_name, grp in df_raw.groupby('academic_name'):
            idx = compute_interdisciplinarity(grp['topics'])
            idx['academic_name'] = ac_name
            inter_rows.append(idx)
        if inter_rows:
            df_inter = pd.DataFrame(inter_rows)
            df_inv_tot = df_inv_tot.merge(df_inter, on='academic_name', how='left')

    df_inv_tot.to_parquet(CACHE_DIR / 'investigador_total.parquet', index=False)
    
    # ── Keywords por investigador ──────────────────────────────────────────────
    print("⏳ Calculando keywords por investigador...")
    if 'keywords' in df_raw.columns:
        from collections import Counter
        kw_rows = []
        for ac_name, grp in df_raw.groupby('academic_name'):
            cnt = Counter()
            for kws in grp['keywords']:
                if isinstance(kws, list):
                    cnt.update([k for k in kws if k])
            for kw, freq in cnt.most_common(50):
                kw_rows.append({'academic_name': ac_name, 'keyword': kw, 'freq': freq})
        if kw_rows:
            pd.DataFrame(kw_rows).to_parquet(CACHE_DIR / 'keywords_investigador.parquet', index=False)
            print(f"  → keywords_investigador.parquet: {len(kw_rows)} filas")

    df_raw_recent = df_raw[(df_raw['year'] >= 2021) & (df_raw['year'] <= 2025)]
    df_inv_recent = aggregate_metrics(df_raw_recent, ['academic_name', 'entities'])
    df_inv_recent.to_parquet(CACHE_DIR / 'investigador_recent.parquet', index=False)
    
    # 3. AGREGARES A NIVEL INSTITUCIÓN (Macro) - Ahora usa la información general de la Entidad
    print("⏳ Extrayendo y agregando métricas de DOIs de Entidades...")
    df_inst_raw = extract_entity_papers()
    if not df_inst_raw.empty:
        df_inst_raw['year'] = pd.to_numeric(df_inst_raw['year'], errors='coerce')
        df_inst_raw = df_inst_raw.dropna(subset=['year'])
        # Filtrar años inválidos
        df_inst_raw = df_inst_raw[df_inst_raw['year'] >= 1900]
        # Exportar listado general de papers de Institucion
        df_inst_raw.to_parquet(CACHE_DIR / 'papers_institucion.parquet', index=False)
        
        df_inst_tot = aggregate_metrics(df_inst_raw, ['entity_name'])

        # ── Interdisciplinariedad por entidad ──────────────────────────────────
        if 'topics' in df_inst_raw.columns:
            inter_rows_inst = []
            for e_name, grp in df_inst_raw.groupby('entity_name'):
                idx = compute_interdisciplinarity(grp['topics'])
                idx['entity_name'] = e_name
                inter_rows_inst.append(idx)
            if inter_rows_inst:
                df_inter_inst = pd.DataFrame(inter_rows_inst)
                df_inst_tot = df_inst_tot.merge(df_inter_inst, on='entity_name', how='left')

        df_inst_tot.to_parquet(CACHE_DIR / 'institucion_total.parquet', index=False)

        # ── Keywords por entidad ───────────────────────────────────────────────
        if 'keywords' in df_inst_raw.columns:
            from collections import Counter
            kw_inst_rows = []
            for e_name, grp in df_inst_raw.groupby('entity_name'):
                cnt = Counter()
                for kws in grp['keywords']:
                    if isinstance(kws, list):
                        cnt.update([k for k in kws if k])
                for kw, freq in cnt.most_common(100):
                    kw_inst_rows.append({'entity_name': e_name, 'keyword': kw, 'freq': freq})
            if kw_inst_rows:
                pd.DataFrame(kw_inst_rows).to_parquet(CACHE_DIR / 'keywords_institucion.parquet', index=False)
                print(f"  → keywords_institucion.parquet: {len(kw_inst_rows)} filas")

    
        df_inst_ann = aggregate_metrics(df_inst_raw, ['entity_name', 'year'])
        df_inst_ann.to_parquet(CACHE_DIR / 'institucion_annual.parquet', index=False)
        
        # Tópicos Entidad Real
        inst_topics_list = []
        for _, row in df_inst_raw.iterrows():
            e_name = row['entity_name']
            topics = row.get('topics', [])
            if isinstance(topics, list):
                for t in topics:
                    if isinstance(t, dict) and t.get('topic'):
                        inst_topics_list.append({
                            'entity_name': e_name,
                            'domain': t.get('domain', 'Unknown'),
                            'field': t.get('field', 'Unknown'),
                            'subfield': t.get('subfield', 'Unknown'),
                            'topic': t.get('topic', 'Unknown')
                        })
        if inst_topics_list:
            df_inst_t = pd.DataFrame(inst_topics_list)
            df_inst_t = df_inst_t.groupby(['entity_name', 'domain', 'field', 'subfield', 'topic']).size().reset_index(name='value')
            df_inst_t.to_parquet(CACHE_DIR / 'topics_institucion.parquet', index=False)
    else:
        print("⚠ No hay artículos cargados por Entidad. Institucion View estará vacía.")
    
    # 4. PRECALCULO DE UMAP (Trayectorias)
    print("⏳ Proyectando UMAP de Trayectorias (Desempeño Académico)...")
    if not df_inv_recent.empty and len(df_inv_recent) >= 3:
        # Usamos FWCI, Citas Norm (Percentiles), Produccion y H-index para construir el espacio
        features = ['num_documents', 'pct_top_10', 'pct_1', 'percentile_avg', 'fwci_avg', 'h_index']
        valid_df = df_inv_recent.dropna(subset=features).copy()
        
        if len(valid_df) > 1:
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(valid_df[features])
            
            # n_neighbors ajustable al tamano pequeno de la facultad min(15, count-1)
            nn = min(15, len(valid_df) - 1)
            if nn < 2: nn = 2
            
            reducer = UMAP(n_neighbors=nn, min_dist=0.1, random_state=42)
            embedding = reducer.fit_transform(X_scaled)
            
            valid_df['umap_x'] = embedding[:, 0]
            valid_df['umap_y'] = embedding[:, 1]
            
            valid_df.to_parquet(CACHE_DIR / 'umap_investigadores.parquet', index=False)
            print(f"✅ UMAP Generado para {len(valid_df)} investigadores.")
        else:
            print("⚠ Insuficientes investigadores válidos para UMAP en el periodo reciente.")
    else:
        print("⚠ Datos insuficientes para generar UMAP.")

    print("\n🎉 Todas las métricas y Parquets se han generado exitosamente en data/cache/")

if __name__ == "__main__":
    process_and_save()
