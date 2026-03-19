"""
Cálculo de Métricas y Trayectorias (Offline)
Extrae datos de Neo4j y precalcula los indicadores para el dashboard.
 Guarda los resultados en data/cache/*.parquet para consulta rápida en Streamlit.
"""
import os
import sys
import json
import argparse
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


def extract_academic_papers(academic_filter=None, entity_filter=None, source_filter='all'):
    """Descarga los metadatos completos de todas las publicaciones por Académico."""
    graph_store = Neo4jGraphStore()
    
    label_filter = ""
    if source_filter == 'wos':
        label_filter = ":IndexedWoS"
    elif source_filter == 'openalex':
        label_filter = ":IndexedOpenAlex"

    if academic_filter:
        print(f"  -> Filtrando por Académico: {academic_filter} (Fuente: {source_filter})")
        query = """
        MATCH (a:Academic {name: $academic})-[:AUTHORED]->(p{label_filter})
        OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity)
        OPTIONAL MATCH (a)-[:AFFILIATED_WITH]->(i:Institution)
        OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
        OPTIONAL MATCH (p)-[:HAS_TOPIC]->(t:Topic)
        RETURN a.name AS academic_name,
               a.orcid AS orcid,
               a.scopus_id AS scopus_id,
               a.siia_url AS siia_url,
               a.audit_verdict AS audit_verdict,
               a.audit_reason AS audit_reason,
               a.match_reason AS match_reason,
               a.audit_confidence AS audit_confidence,
               a.audit_timestamp AS audit_timestamp,
               a.is_snii AS is_snii,
               collect(DISTINCT e.name) AS entities,
               collect(DISTINCT i.name) AS institutions,
               p.id AS paper_id,
               p.doi AS paper_doi,
               p.year AS year,
               p.citations AS citations,
               p.raw_metadata AS raw_metadata,
               collect(DISTINCT {id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}) AS sdgs,
               collect(DISTINCT {topic: t.name, domain: t.domain, field: t.field, subfield: t.subfield}) AS graph_topics
        """.replace("{label_filter}", label_filter)
        params = {"academic": academic_filter}
    elif entity_filter:
        print(f"  -> Filtrando por Entidad (Investigadores): {entity_filter} (Fuente: {source_filter})")
        query = """
        MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p{label_filter})
        OPTIONAL MATCH (a)-[:AFFILIATED_WITH]->(i:Institution)
        OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
        OPTIONAL MATCH (p)-[:HAS_TOPIC]->(t:Topic)
        RETURN a.name AS academic_name,
               a.orcid AS orcid,
               a.scopus_id AS scopus_id,
               a.siia_url AS siia_url,
               a.audit_verdict AS audit_verdict,
               a.audit_reason AS audit_reason,
               a.match_reason AS match_reason,
               a.audit_confidence AS audit_confidence,
               a.audit_timestamp AS audit_timestamp,
               a.is_snii AS is_snii,
               collect(DISTINCT e.name) AS entities,
               collect(DISTINCT i.name) AS institutions,
               p.id AS paper_id,
               p.doi AS paper_doi,
               p.year AS year,
               p.citations AS citations,
               p.raw_metadata AS raw_metadata,
               collect(DISTINCT {id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}) AS sdgs,
               collect(DISTINCT {topic: t.name, domain: t.domain, field: t.field, subfield: t.subfield}) AS graph_topics
        """.replace("{label_filter}", label_filter)
        params = {"entity": entity_filter}
    else:
        print(f"  -> Procesando todos los académicos (Fuente: {source_filter})")
        query = """
        MATCH (a:Academic)-[:AUTHORED]->(p{label_filter})
        OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity)
        OPTIONAL MATCH (a)-[:AFFILIATED_WITH]->(i:Institution)
        OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
        OPTIONAL MATCH (p)-[:HAS_TOPIC]->(t:Topic)
        RETURN a.name AS academic_name,
               a.orcid AS orcid,
               a.scopus_id AS scopus_id,
               a.siia_url AS siia_url,
               a.audit_verdict AS audit_verdict,
               a.audit_reason AS audit_reason,
               a.audit_confidence AS audit_confidence,
               a.audit_timestamp AS audit_timestamp,
               a.is_snii AS is_snii,
               collect(DISTINCT e.name) AS entities,
               collect(DISTINCT i.name) AS institutions,
               p.id AS paper_id,
               p.doi AS paper_doi,
               p.year AS year,
               p.citations AS citations,
               p.raw_metadata AS raw_metadata,
               collect(DISTINCT {id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}) AS sdgs,
               collect(DISTINCT {topic: t.name, domain: t.domain, field: t.field, subfield: t.subfield}) AS graph_topics
        """.replace("{label_filter}", label_filter)
        params = {}
    
    records = []
    with graph_store.driver.session() as session:
        result = session.run(query, **params)
        for row in result:
            raw_meta = {}
            if row['raw_metadata']:
                try:
                    raw_meta = json.loads(row['raw_metadata'])
                except:
                    pass
            
            # Identificar papers enriquecidos por OpenAlex (resiliente a campos faltantes en caché)
            has_oa_link = any([
                bool(raw_meta.get('openalex_url')),
                bool(raw_meta.get('id')),
                raw_meta.get('fwci') is not None,
                bool(raw_meta.get('OpenAlex_Topics'))
            ])
            oa_url_raw = raw_meta.get('openalex_url') or raw_meta.get('id')
            
            title = raw_meta.get('Title') or raw_meta.get('title') or raw_meta.get('TI') or 'No Title'
            source = raw_meta.get('Source') or raw_meta.get('source_title') or raw_meta.get('journal_iso_source_abbreviation') or raw_meta.get('publication_name') or raw_meta.get('SO') or 'Unknown'
            
            # Lógica de enlace: Priorizar DOI recuperado, evitar placeholders de orcid
            doi_val = row.get('paper_doi') or row['paper_id']
            doi_link = None
            if doi_val and str(doi_val).startswith("10."):
                doi_link = "https://doi.org/" + str(doi_val).lower()
            elif doi_val and not any(x in str(doi_val).lower() for x in ["urn:", "orcid-work:"]):
                doi_link = "https://doi.org/" + str(doi_val)
            
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
            
            is_in_top_1_percent = raw_meta.get('is_in_top_1_percent')
            if is_in_top_1_percent is None and 'raw_metadata' in raw_meta:
                is_in_top_1_percent = raw_meta['raw_metadata'].get('is_in_top_1_percent')

            # Impact Indicators (FWCI, Percentile, Top 10%, Top 1%)
            # Only set numerical values if OA enrichment is confirmed
            if has_oa_link:
                fwci = raw_meta.get('fwci')
                if fwci is None and 'raw_metadata' in raw_meta:
                    fwci = raw_meta['raw_metadata'].get('fwci')
                fwci = float(fwci) if fwci is not None else np.nan
                
                percentile = raw_meta.get('citation_normalized_percentile')
                if percentile is None and 'raw_metadata' in raw_meta:
                    percentile = raw_meta['raw_metadata'].get('citation_normalized_percentile')
                percentile = float(percentile) if percentile is not None else np.nan
                
                is_in_top_10_percent = float(is_in_top_10_percent) if is_in_top_10_percent is not None else np.nan
                is_in_top_1_percent = float(is_in_top_1_percent) if is_in_top_1_percent is not None else np.nan
            else:
                fwci = np.nan
                percentile = np.nan
                is_in_top_10_percent = np.nan
                is_in_top_1_percent = np.nan

            # Lógica de Citas: Priorizar OpenAlex
            citations = row.get('citations')
            if isinstance(citations, (int, float)) and not np.isnan(citations):
                citations = int(citations)
            elif isinstance(citations, str) and citations.isdigit():
                citations = int(citations)
            else:
                citations = 0
            
            if has_oa_link:
                oa_cites = raw_meta.get('cited_by_count')
                if oa_cites is None:
                    counts = raw_meta.get('counts_by_year', [])
                    if isinstance(counts, list) and counts:
                        oa_cites = sum(y.get('cited_by_count', 0) for y in counts)
                    else:
                        oa_cites = 0
                if oa_cites is not None and int(oa_cites) > citations:
                    citations = int(oa_cites)

            records.append({
                'academic_name': row['academic_name'],
                'orcid':     row['orcid'],
                'scopus_id': row['scopus_id'],
                'siia_url':  row['siia_url'],
                'audit_verdict': row.get('audit_verdict'),
                'audit_reason': row.get('audit_reason'),
                'audit_confidence': row.get('audit_confidence'),
                'audit_timestamp': row.get('audit_timestamp'),
                'match_reason':    row.get('match_reason'),
                'is_snii':   bool(row.get('is_snii', False)),
                'entities':  ";".join(row['entities']) if row['entities'] else "Sin Entidad",
                'institutions': ";".join(row['institutions']) if row.get('institutions') else "Sin Institución",
                'paper_id':  row['paper_id'],
                'year':      row['year'],
                'citations': citations,
                'Title':  title,
                'Source': source,
                'DOI':    doi_link,
                'Link':   doi_link,
                'openalex_url': raw_meta.get('openalex_url'),
                'has_oa_data':  int(has_oa_link),
                'fwci':                         fwci,
                'is_oa':                        int(is_oa),
                'oa_status':                    oa_status,
                'is_in_top_10_percent':         is_in_top_10_percent,
                'is_in_top_1_percent':          is_in_top_1_percent,
                'citation_normalized_percentile': percentile,
                'counts_by_year':        raw_meta.get('counts_by_year') or [],
                'referenced_works_count': int(raw_meta.get('referenced_works_count', 0) or 0),
                'referenced_works':      raw_meta.get('referenced_works') or [],
                'apc_paid_usd': float(raw_meta.get('apc_paid_usd', 0) or 0),
                'apc_list_usd': float(raw_meta.get('apc_list_usd', 0) or 0),
                'author_count':             int(raw_meta.get('author_count', 0) or 0),
                'countries_distinct_count': int(raw_meta.get('countries_distinct_count', 0) or 0),
                'institutions_distinct_count': int(raw_meta.get('institutions_distinct_count', 0) or 0),
                'countries':            raw_meta.get('countries') or [],
                'coauthor_institutions': raw_meta.get('coauthor_institutions') or [],
                'license':                   raw_meta.get('license'),
                'any_repository_has_fulltext': bool(raw_meta.get('any_repository_has_fulltext', False)),
                'locations_count':           int(raw_meta.get('locations_count', 0) or 0),
                'oa_url':                    raw_meta.get('oa_url'),
                'indexed_in':        raw_meta.get('indexed_in') or [],
                'is_retracted':      bool(raw_meta.get('is_retracted', False)),
                'language':          raw_meta.get('language', 'en') or 'en',
                'type':              raw_meta.get('type', 'article'),
                'journal_is_oa':      bool(raw_meta.get('journal_is_oa', False)),
                'journal_is_in_doaj': bool(raw_meta.get('journal_is_in_doaj', False)),
                'journal_is_core':    bool(raw_meta.get('journal_is_core', False)),
                'issn':               raw_meta.get('issn'),
                'primary_topic_name':     raw_meta.get('primary_topic_name'),
                'primary_topic_domain':   raw_meta.get('primary_topic_domain'),
                'primary_topic_field':    raw_meta.get('primary_topic_field'),
                'primary_topic_subfield': raw_meta.get('primary_topic_subfield'),
                'primary_topic_score':    raw_meta.get('primary_topic_score'),
                'keywords':              raw_meta.get('keywords') or [],
                'topics': row.get('graph_topics', [])
            })
            
            # temas y sdgs desde el grafo (Neo4j)
            sdgs = row.get('sdgs', [])
            sdg_id, sdg_name, sdg_conf, sdg_reas = None, None, None, None
            if sdgs:
                # Tomamos el primero que tenga ID válido
                first_sdg = [s for s in sdgs if s.get('id') is not None]
                if first_sdg:
                    sdg_id = first_sdg[0].get('id')
                    sdg_name = first_sdg[0].get('name')
                    sdg_conf = first_sdg[0].get('confidence')
                    sdg_reas = first_sdg[0].get('reasoning')

            records[-1].update({
                'ODS_ID': sdg_id,
                'ODS_Nombre': sdg_name,
                'ODS_Confianza': sdg_conf,
                'ODS_Justificacion': sdg_reas
            })
            
            # Flush batch to avoid loading everything in memory if later used in a loop
            if len(records) >= 5000:
                yield pd.DataFrame(records)
                records = []
                
    if records:
        yield pd.DataFrame(records)

def extract_entity_papers(entity_filter=None, source_filter='all'):
    """Descarga los papers asociados históricamente a una Institución/Entidad."""
    graph_store = Neo4jGraphStore()
    
    label_filter = ""
    if source_filter == 'wos':
        label_filter = ":IndexedWoS"
    elif source_filter == 'openalex':
        label_filter = ":IndexedOpenAlex"

    if entity_filter:
        print(f"  -> Filtrando por Entidad (Papers): {entity_filter} (Fuente: {source_filter})")
        query = """
        MATCH (e:Entity {name: $entity})
        OPTIONAL MATCH (e)<-[:AFFILIATED_TO]-(a:Academic)-[:AFFILIATED_WITH]->(i:Institution)
        OPTIONAL MATCH (e)-[:HAS_PAPER]->(p:Paper{label_filter})
        OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
        RETURN e.name AS entity_name,
               collect(DISTINCT i.name) AS institutions,
               p.id AS paper_id,
               p.doi AS paper_doi,
               p.year AS year,
               p.citations AS citations,
               p.raw_metadata AS raw_metadata,
               collect({id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}) AS sdgs
        """.replace("{label_filter}", label_filter)
        params = {"entity": entity_filter}
    else:
        print(f"  -> Procesando todas las entidades (Fuente: {source_filter})")
        query = """
        MATCH (e:Entity)-[:HAS_PAPER]->(p:Paper{label_filter})
        OPTIONAL MATCH (e)<-[:AFFILIATED_TO]-(a:Academic)-[:AFFILIATED_WITH]->(i:Institution)
        OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
        RETURN e.name AS entity_name,
               collect(DISTINCT i.name) AS institutions,
               p.id AS paper_id,
               p.doi AS paper_doi,
               p.year AS year,
               p.citations AS citations,
               p.raw_metadata AS raw_metadata,
               collect({id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}) AS sdgs
        """.replace("{label_filter}", label_filter)
        params = {}
        
    records = []
    with graph_store.driver.session() as session:
        result = session.run(query, **params)
        for row in result:
            raw_meta = {}
            if row['raw_metadata']:
                try:
                    raw_meta = json.loads(row['raw_metadata'])
                except:
                    pass
            
            # Identificar papers enriquecidos por OpenAlex (resiliente a campos faltantes)
            has_oa_link = any([
                bool(raw_meta.get('openalex_url')),
                bool(raw_meta.get('id')),
                raw_meta.get('fwci') is not None,
                bool(raw_meta.get('OpenAlex_Topics'))
            ])
            oa_url_raw = raw_meta.get('openalex_url') or raw_meta.get('id')
            
            title = raw_meta.get('Title') or raw_meta.get('title') or raw_meta.get('TI') or 'No Title'
            source = raw_meta.get('Source') or raw_meta.get('source_title') or raw_meta.get('journal_iso_source_abbreviation') or raw_meta.get('publication_name') or raw_meta.get('SO') or 'Unknown'
            # Lógica de enlace: Priorizar DOI recuperado, evitar placeholders de orcid
            doi_val = row.get('paper_doi') or row['paper_id']
            doi_link = None
            if doi_val and str(doi_val).startswith("10."):
                doi_link = "https://doi.org/" + str(doi_val).lower()
            elif doi_val and not any(x in str(doi_val).lower() for x in ["urn:", "orcid-work:"]):
                doi_link = "https://doi.org/" + str(doi_val)
            
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
            
            is_in_top_1_percent = raw_meta.get('is_in_top_1_percent')
            if is_in_top_1_percent is None and 'raw_metadata' in raw_meta:
                is_in_top_1_percent = raw_meta['raw_metadata'].get('is_in_top_1_percent')

            # Impact Indicators (Only if enriched)
            if has_oa_link:
                fwci = raw_meta.get('fwci')
                if fwci is None and 'raw_metadata' in raw_meta:
                    fwci = raw_meta['raw_metadata'].get('fwci')
                fwci = float(fwci) if fwci is not None else np.nan
                
                percentile = raw_meta.get('citation_normalized_percentile')
                if percentile is None and 'raw_metadata' in raw_meta:
                    percentile = raw_meta['raw_metadata'].get('citation_normalized_percentile')
                percentile = float(percentile) if percentile is not None else np.nan
                
                is_in_top_10_percent = float(is_in_top_10_percent) if is_in_top_10_percent is not None else np.nan
                is_in_top_1_percent = float(is_in_top_1_percent) if is_in_top_1_percent is not None else np.nan
            else:
                fwci = np.nan
                percentile = np.nan
                is_in_top_10_percent = np.nan
                is_in_top_1_percent = np.nan
            
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

            # Lógica de Citas: Priorizar OpenAlex
            citations = row.get('citations')
            if isinstance(citations, (int, float)) and not np.isnan(citations):
                citations = int(citations)
            elif isinstance(citations, str) and citations.isdigit():
                citations = int(citations)
            else:
                citations = 0
            
            if has_oa_link:
                oa_cites = raw_meta.get('cited_by_count')
                if oa_cites is None:
                    counts = raw_meta.get('counts_by_year', [])
                    if isinstance(counts, list) and counts:
                        oa_cites = sum(y.get('cited_by_count', 0) for y in counts)
                    else:
                        oa_cites = 0
                if oa_cites is not None and int(oa_cites) > citations:
                    citations = int(oa_cites)

            records.append({
                'entity_name': row['entity_name'],
                'institutions': ";".join(row['institutions']) if row.get('institutions') else "Sin Institución",
                'paper_id': row['paper_id'],
                'year': row['year'],
                'citations': citations,
                'Title': title,
                'Source': source,
                'DOI': doi_link,
                'Link': doi_link,
                'openalex_url': raw_meta.get('openalex_url'),
                'has_oa_data':  int(has_oa_link),
                # ── Impacto ────────────────────────────────────────────────────
                'fwci':                         fwci,
                'is_oa':                        int(is_oa),
                'oa_status':                    oa_status,
                'is_in_top_10_percent':         is_in_top_10_percent,
                'is_in_top_1_percent':          is_in_top_1_percent,
                'citation_normalized_percentile': percentile,
                # ── Trayectoria de citas ────────────────────────────────────────
                'counts_by_year':        raw_meta.get('counts_by_year') or [],
                'referenced_works_count': int(raw_meta.get('referenced_works_count', 0) or 0),
                'referenced_works':      raw_meta.get('referenced_works') or [],
                # ── APC ─────────────────────────────────────────────────────────
                'apc_paid_usd': float(raw_meta.get('apc_paid_usd', 0) or 0),
                'apc_list_usd': float(raw_meta.get('apc_list_usd', 0) or 0),
                # ── Colaboración ────────────────────────────────────────────────
                'author_count':             int(raw_meta.get('author_count', 0) or 0),
                'countries_distinct_count': int(raw_meta.get('countries_distinct_count', 0) or 0),
                'institutions_distinct_count': int(raw_meta.get('institutions_distinct_count', 0) or 0),
                'countries':            raw_meta.get('countries') or [],
                'coauthor_institutions': raw_meta.get('coauthor_institutions') or [],
                # ── OA avanzado ─────────────────────────────────────────────────
                'license':                   raw_meta.get('license'),
                'any_repository_has_fulltext': bool(raw_meta.get('any_repository_has_fulltext', False)),
                'locations_count':           int(raw_meta.get('locations_count', 0) or 0),
                'oa_url':                    raw_meta.get('oa_url'),
                # ── Indexación ─────────────────────────────────────────────────
                'indexed_in':        raw_meta.get('indexed_in') or [],
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
                'keywords':              raw_meta.get('keywords') or [],
                # ── Tópicos y ODS ──────────────────────────────────────────────
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

    # Identificar papers con datos reales de OpenAlex (enriquecidos)
    _has_oa = df_papers['has_oa_data'] == 1 if 'has_oa_data' in df_papers.columns else df_papers['openalex_url'].notna()

    # Limpiar columnas de impacto: si no hay OA, deben ser NaN para no sesgar promedios
    impact_cols = ['fwci', 'citation_normalized_percentile', 
                   'is_in_top_10_percent', 'is_in_top_1_percent']
    for col in impact_cols:
        if col in df_papers.columns:
            df_papers[col] = pd.to_numeric(df_papers[col], errors='coerce')
            df_papers.loc[~_has_oa, col] = np.nan

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
        'is_english': 'sum',
        'is_cc_by': 'sum'
    }
    
    # Validaciones para columnas audit e is_snii (sólo si existen)
    audit_cols = ['audit_verdict', 'audit_reason', 'audit_confidence', 'audit_timestamp', 'is_snii']
    for acol in audit_cols:
        if acol in df_papers.columns:
            if acol == 'is_snii':
                agg_funcs[acol] = 'max' # Si algun registro dice True, es SNII
            else:
                agg_funcs[acol] = 'first'
    
    # Agregar columnas informativas si existen y no están en group_cols
    for col in ['orcid', 'scopus_id', 'entities', 'institutions', 'siia_url']:
        if col in df_papers.columns and col not in group_cols:
            agg_funcs[col] = 'first'
    
    # Filtrar agg_funcs: sólo columnas que realmente existan en el df actual
    agg_funcs = {k: v for k, v in agg_funcs.items() if k in df_papers.columns}
    
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
    df_agg['fwci_avg'] = df_agg['fwci_avg'].replace([np.inf, -np.inf], 0)
    df_agg['percentile_avg'] = df_agg['percentile_avg'].replace([np.inf, -np.inf], 0)
    
    # Calcular Citations per Paper (CPP)
    df_agg['citations_per_paper'] = df_agg['citations'] / df_agg['num_documents'].replace(0, 1)
    
    # Calcular indice H para el agrupamiento
    h_series = df_papers.groupby(group_cols)['citations'].apply(list).apply(_get_h_index).reset_index(name='h_index')
    
    df_agg = df_agg.merge(h_series, on=group_cols, how='left')
    return df_agg

def save_disaggregated_parquets(df, base_name, group_level, academics_map=None, include_academics_list=False):
    """
    Guarda el dataframe en carpetas separadas:
    data/dash_cache/<Entidad>/<Academico>/archivo.parquet
    o data/dash_cache/<Entidad>/archivo.parquet
    """
    # Remove if df.empty: return to allow overwriting with empty dataframes for cleanup
    
    if group_level == 'academic':
        # Aseguramos que todos los académicos en el mapa sean procesados para evitar archivos huérfanos/viejos
        academics_to_process = list(academics_map.keys()) if academics_map else (df['academic_name'].unique().tolist() if not df.empty else [])
        
        for ac_name in academics_to_process:
            grp = df[df['academic_name'] == ac_name] if not df.empty else pd.DataFrame(columns=df.columns)
            
            entities = []
            if academics_map and ac_name in academics_map:
                entities = academics_map[ac_name]
            elif not grp.empty:
                entities_val = grp['entities'].iloc[0]
                if isinstance(entities_val, list):
                    entities = entities_val
                elif isinstance(entities_val, str):
                    entities = [e.strip() for e in entities_val.split(';') if e.strip()]
            
            if not entities:
                entities = ['Sin Entidad']
                
            # Buscar Institución (preferencia por la jerarquía)
            institutions = []
            if 'institutions' in grp.columns and not grp.empty:
                inst_val = grp['institutions'].iloc[0]
                if isinstance(inst_val, list):
                    institutions = inst_val
                elif isinstance(inst_val, str):
                    institutions = [i.strip() for i in inst_val.split(';') if i.strip()]
            
            if not institutions or institutions == ["Sin Institución"]:
                institutions = ["Universidad Nacional Autónoma de México (UNAM)"] # Default Legacy

            for ent in entities:
                for inst in institutions:
                    safe_inst = str(inst).replace('/', '_').replace('\\', '_')
                    safe_ent = str(ent).replace('/', '_').replace('\\', '_')
                    safe_ac = str(ac_name).replace('/', '_').replace('\\', '_')
                    
                    # 1. Ruta Jerárquica (Nacional)
                    target_dir = CACHE_DIR / safe_inst / safe_ent / safe_ac
                    target_dir.mkdir(parents=True, exist_ok=True)
                    grp.to_parquet(target_dir / base_name, index=False)
                    
                    # 2. Ruta Plana (Legacy / Fallback)
                    legacy_dir = CACHE_DIR / safe_ent / safe_ac
                    legacy_dir.mkdir(parents=True, exist_ok=True)
                    grp.to_parquet(legacy_dir / base_name, index=False)
                
    elif group_level == 'entity':
        # Aseguramos que todas las entidades sean procesadas si el df está incompleto
        entities_to_process = df['entity_name'].unique().tolist() if not df.empty else []
        
        if len(entities_to_process) == 0:
             try:
                 graph_store = Neo4jGraphStore()
                 with graph_store.driver.session() as session:
                     res = session.run("MATCH (e:Entity) RETURN e.name AS name")
                     entities_to_process = [r['name'] for r in res]
                 graph_store.close()
             except: pass
        
        graph_store = Neo4jGraphStore()
        for ent_name in entities_to_process:
            grp = df[df['entity_name'] == ent_name] if not df.empty else pd.DataFrame(columns=df.columns)
            
            # Buscar Institución
            institutions = []
            if 'institutions' in grp.columns and not grp.empty:
                inst_val = grp['institutions'].iloc[0]
                if isinstance(inst_val, list):
                    institutions = inst_val
                elif isinstance(inst_val, str):
                    institutions = [i.strip() for i in inst_val.split(';') if i.strip()]
            
            if not institutions or institutions == ["Sin Institución"]:
                institutions = ["Universidad Nacional Autónoma de México (UNAM)"]

            safe_ent = str(ent_name).replace('/', '_').replace('\\', '_')
            
            for inst in institutions:
                safe_inst = str(inst).replace('/', '_').replace('\\', '_')
                
                # 1. Ruta Jerárquica
                target_dir = CACHE_DIR / safe_inst / safe_ent
                target_dir.mkdir(parents=True, exist_ok=True)
                
                # Enriquecimiento de académicos_list (mantenlo para la carpeta final)
                grp_final = grp.copy()
                if include_academics_list and ent_name not in ["UNAM", "Mexico", "México"]:
                    try:
                        with graph_store.driver.session() as session:
                            res = session.run("MATCH (e:Entity {name: $ent})<-[:AFFILIATED_TO]-(a:Academic) RETURN a.name AS name", ent=ent_name)
                            academics = [r['name'] for r in res]
                        grp_final['academics_list'] = json.dumps(academics, ensure_ascii=False)
                    except:
                        grp_final['academics_list'] = "[]"
                
                grp_final.to_parquet(target_dir / base_name, index=False)
                
                # 2. Ruta Plana (Legacy)
                legacy_dir = CACHE_DIR / safe_ent
                legacy_dir.mkdir(parents=True, exist_ok=True)
                grp_final.to_parquet(legacy_dir / base_name, index=False)
                
        graph_store.close()

def process_and_save(entity_filter=None, academic_filter=None, source_filter='all'):
    print(f"Iniciando Pre-cálculo de Métricas (Fuente: {source_filter})...")
    
    # 1. Extracción y Enriquecimiento por lotes
    df_raw_list = []
    for chunk_df in extract_academic_papers(academic_filter=academic_filter, entity_filter=entity_filter, source_filter=source_filter):
        print(f"  → Procesando bloque de {len(chunk_df)} papers...")
        chunk_df['year'] = pd.to_numeric(chunk_df['year'], errors='coerce')
        chunk_df = chunk_df.dropna(subset=['year'])
        chunk_df = chunk_df[chunk_df['year'] >= 1900]
        
        # Saneo rápido
        list_cols = ['keywords', 'topics', 'indexed_in']
        for c in list_cols:
            if c in chunk_df.columns:
                chunk_df[c] = chunk_df[c].apply(lambda x: list(x) if isinstance(x, (list, tuple)) else [])
        
        df_raw_list.append(chunk_df)

    if not df_raw_list:
        print("❌ No se encontraron datos.")
        return
        
    df_raw = pd.concat(df_raw_list, ignore_index=True)
    print(f"✅ Total {len(df_raw)} publicaciones cargadas.")
    
    # Construir mapa de academicos a entidades
    academics_map = {}
    for _, row in df_raw.iterrows():
        ac_name = row['academic_name']
        entities = []
        entities_val = row['entities']
        if isinstance(entities_val, list):
            entities = entities_val
        elif isinstance(entities_val, str):
            entities = [e.strip() for e in entities_val.split(';') if e.strip()]
        
        if ac_name not in academics_map:
            academics_map[ac_name] = set(entities)
        else:
            academics_map[ac_name].update(entities)
    
    # Convertir sets a listas para compatibilidad posterior
    academics_map = {k: list(v) for k, v in academics_map.items()}
    
    # Sanear columnas tipo lista para PyArrow
    list_cols = ['keywords', 'topics', 'countries', 'coauthor_institutions', 'referenced_works', 'counts_by_year', 'indexed_in']
    for c in list_cols:
        if c in df_raw.columns:
            df_raw[c] = df_raw[c].apply(lambda x: list(x) if isinstance(x, (list, tuple, np.ndarray)) else [])

    # Exportar listado general de papers de Académicos
    save_disaggregated_parquets(df_raw, 'papers_profesor.parquet', 'academic', academics_map)
    
    # TOPICOS SUNBURST
    print("⏳ Precalculando agrupaciones de Tópicos (Sunburst)...")
    topics_list = []
    for _, row in df_raw.iterrows():
        ac_name = row['academic_name']
        year = row['year']
        
        # PRIORIDAD 1: Usar Primary Topic de OpenAlex (Asegura 1:1 para que coincidan conteos)
        p_topic = row.get('primary_topic_name')
        if p_topic and p_topic != 'Unknown':
            topics_list.append({
                'academic_name': ac_name,
                'year': int(year),
                'domain': row.get('primary_topic_domain', 'Unknown'),
                'field': row.get('primary_topic_field', 'Unknown'),
                'subfield': row.get('primary_topic_subfield', 'Unknown'),
                'topic': p_topic
            })
        else:
            # PRIORIDAD 2: Si no hay primario, intentar el primer tópico de la lista (del grafo)
            topics = row.get('topics', [])
            if isinstance(topics, list) and topics:
                # Tomamos solo el primero para mantener coherencia en las cuentas totales
                t = topics[0]
                if isinstance(t, dict) and t.get('topic'):
                    topics_list.append({
                        'academic_name': ac_name,
                        'year': int(year),
                        'domain': t.get('domain', 'Unknown'),
                        'field': t.get('field', 'Unknown'),
                        'subfield': t.get('subfield', 'Unknown'),
                        'topic': t.get('topic', 'Unknown')
                    })
    if topics_list:
        df_topics = pd.DataFrame(topics_list)
        df_topics['count'] = 1
        # Evolución (con año)
        df_topics_evol = df_topics.groupby(['academic_name', 'year', 'domain', 'field', 'subfield', 'topic']).size().reset_index(name='value')
        save_disaggregated_parquets(df_topics_evol, 'thematic_evolution_investigador.parquet', 'academic', academics_map)
        
        # Totales (para Sunburst, agrupado sin año)
        df_topics_agg = df_topics.groupby(['academic_name', 'domain', 'field', 'subfield', 'topic']).size().reset_index(name='value')
        save_disaggregated_parquets(df_topics_agg, 'topics_investigador.parquet', 'academic', academics_map)
    else:
        # Escribir parquet vacío para que el dashboard muestre mensaje en vez de None
        print("⚠️  No se encontraron tópicos en raw_metadata ni en nodos :Topic del grafo.")
        df_topics_agg = pd.DataFrame(columns=['academic_name', 'domain', 'field', 'subfield', 'topic', 'value'])
        save_disaggregated_parquets(df_topics_agg, 'topics_investigador.parquet', 'academic', academics_map)
        save_disaggregated_parquets(pd.DataFrame(columns=['academic_name', 'year', 'domain', 'field', 'subfield', 'topic', 'value']), 'thematic_evolution_investigador.parquet', 'academic', academics_map)
    # Limpiar archivos de versiones anteriores si existen
    if os.path.exists(CACHE_DIR / 'concepts_investigador.parquet'):
        os.remove(CACHE_DIR / 'concepts_investigador.parquet')
    if os.path.exists(CACHE_DIR / 'concepts_institucion.parquet'):
        os.remove(CACHE_DIR / 'concepts_institucion.parquet')

    # 2. AGREGARES A NIVEL INVESTIGADOR
    print("⏳ Agregando métricas a nivel Investigador...")
    # Agregamos 'entities' para conservar las afiliaciones en el agrupamiento
    df_inv_annual = aggregate_metrics(df_raw, ['academic_name', 'entities', 'year'])
    save_disaggregated_parquets(df_inv_annual, 'investigador_annual.parquet', 'academic', academics_map)
    
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

    save_disaggregated_parquets(df_inv_tot, 'investigador_total.parquet', 'academic', academics_map)
    
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
            for kw, freq in cnt.most_common(1000):
                kw_rows.append({'academic_name': ac_name, 'keyword': kw, 'freq': freq})
        if kw_rows:
            save_disaggregated_parquets(pd.DataFrame(kw_rows), 'keywords_investigador.parquet', 'academic', academics_map)
            print(f"  → keywords_investigador.parquet: {len(kw_rows)} filas incremental o total")

    df_raw_recent = df_raw[(df_raw['year'] >= 2021) & (df_raw['year'] <= 2025)]
    df_inv_recent = aggregate_metrics(df_raw_recent, ['academic_name', 'entities'])
    save_disaggregated_parquets(df_inv_recent, 'investigador_recent.parquet', 'academic', academics_map)
    
    # 3. AGREGADOS A NIVEL INSTITUCIÓN (Macro)
    df_inst_raw = pd.DataFrame()
    if entity_filter or not academic_filter:
        print(f"⏳ Extrayendo y agregando métricas de DOIs de Entidades (Fuente: {source_filter})...")
        df_inst_raw = extract_entity_papers(entity_filter=entity_filter, source_filter=source_filter)
    if not df_inst_raw.empty:
        df_inst_raw['year'] = pd.to_numeric(df_inst_raw['year'], errors='coerce')
        df_inst_raw = df_inst_raw.dropna(subset=['year'])
        # Filtrar años inválidos
        df_inst_raw = df_inst_raw[df_inst_raw['year'] >= 1900]
        
        # Sanear columnas tipo lista para PyArrow
        list_cols = ['keywords', 'topics', 'countries', 'coauthor_institutions', 'referenced_works', 'counts_by_year', 'indexed_in']
        for c in list_cols:
            if c in df_inst_raw.columns:
                df_inst_raw[c] = df_inst_raw[c].apply(lambda x: list(x) if isinstance(x, (list, tuple, np.ndarray)) else [])

        # Exportar listado general de papers de Institucion
        save_disaggregated_parquets(df_inst_raw, 'papers_institucion.parquet', 'entity')
        
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

        save_disaggregated_parquets(df_inst_tot, 'institucion_total.parquet', 'entity', include_academics_list=True)

        # ── Keywords por entidad ───────────────────────────────────────────────
        if 'keywords' in df_inst_raw.columns:
            from collections import Counter
            kw_inst_rows = []
            for e_name, grp in df_inst_raw.groupby('entity_name'):
                cnt = Counter()
                for kws in grp['keywords']:
                    if isinstance(kws, list):
                        cnt.update([k for k in kws if k])
                for kw, freq in cnt.most_common(1000):
                    kw_inst_rows.append({'entity_name': e_name, 'keyword': kw, 'freq': freq})
            if kw_inst_rows:
                save_disaggregated_parquets(pd.DataFrame(kw_inst_rows), 'keywords_institucion.parquet', 'entity')
                print(f"  → keywords_institucion.parquet: {len(kw_inst_rows)} filas incremental o total")

    
        df_inst_ann = aggregate_metrics(df_inst_raw, ['entity_name', 'year'])
        save_disaggregated_parquets(df_inst_ann, 'institucion_annual.parquet', 'entity')
        
        # Tópicos Entidad Real
        inst_topics_list = []
        for _, row in df_inst_raw.iterrows():
            e_name = row['entity_name']
            year = row['year']
            
            # PRIORIDAD 1: Primary Topic (OpenAlex) para evitar explosión de registros
            p_topic = row.get('primary_topic_name')
            if p_topic and p_topic != 'Unknown':
                inst_topics_list.append({
                    'entity_name': e_name,
                    'year': int(year),
                    'domain': row.get('primary_topic_domain', 'Unknown'),
                    'field': row.get('primary_topic_field', 'Unknown'),
                    'subfield': row.get('primary_topic_subfield', 'Unknown'),
                    'topic': p_topic
                })
            else:
                # PRIORIDAD 2: Primer tópico de la lista (Grafo)
                topics = row.get('topics', [])
                if isinstance(topics, list) and topics:
                    t = topics[0]
                    if isinstance(t, dict) and t.get('topic'):
                        inst_topics_list.append({
                            'entity_name': e_name,
                            'year': int(year),
                            'domain': t.get('domain', 'Unknown'),
                            'field': t.get('field', 'Unknown'),
                            'subfield': t.get('subfield', 'Unknown'),
                            'topic': t.get('topic', 'Unknown')
                        })
        if inst_topics_list:
            df_inst_t_raw = pd.DataFrame(inst_topics_list)
            # Aseguramos que 'year' existe en inst_topics_list
            # Evolución (con año)
            df_inst_evol = df_inst_t_raw.groupby(['entity_name', 'year', 'domain', 'field', 'subfield', 'topic']).size().reset_index(name='value')
            save_disaggregated_parquets(df_inst_evol, 'thematic_evolution_institucion.parquet', 'entity')
            
            df_inst_t = df_inst_t_raw.groupby(['entity_name', 'domain', 'field', 'subfield', 'topic']).size().reset_index(name='value')
            save_disaggregated_parquets(df_inst_t, 'topics_institucion.parquet', 'entity')

    else:
        if academic_filter and not entity_filter:
            print("⏩ Saltando métricas institucionales (Modo Académico detectado para velocidad).")
        else:
            print("⚠ No hay artículos cargados por Entidad. Institucion View estará vacía.")
    
    # 4. PRECALCULO DE UMAP (Trayectorias)
    print("⏳ Proyectando UMAP de Trayectorias (Desempeño Académico)...")
    umap_df = df_inv_recent
    if os.path.exists(CACHE_DIR / 'investigador_recent.parquet'):
        try:
            umap_df = pd.read_parquet(CACHE_DIR / 'investigador_recent.parquet')
        except Exception:
            pass

    if not umap_df.empty and len(umap_df) >= 3:
        # Usamos FWCI, Citas Norm (Percentiles), Produccion y H-index para construir el espacio
        features = ['num_documents', 'pct_top_10', 'pct_1', 'percentile_avg', 'fwci_avg', 'h_index']
        valid_df = umap_df.dropna(subset=features).copy()
        
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
    parser = argparse.ArgumentParser(description="Calcula y guarda métricas académicas en parquets.")
    parser.add_argument("--entity", type=str, help="Nombre de la entidad para filtrar")
    parser.add_argument("--academic", type=str, help="Nombre del académico para filtrar")
    parser.add_argument("--source", type=str, choices=['wos', 'openalex', 'all'], default='all', 
                        help="Fuente de indización (wos, openalex, all)")
    args = parser.parse_args()
    
    process_and_save(entity_filter=args.entity, academic_filter=args.academic, source_filter=args.source)
