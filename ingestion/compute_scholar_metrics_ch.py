"""
Cálculo de Métricas y Trayectorias (Optimizado con ClickHouse)
Este script replica la lógica de compute_scholar_metrics.py pero extrae los metadatos
de los artículos desde la tabla plana de ClickHouse (works_flat).
"""
import os
import sys
import json
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from umap import UMAP
from sklearn.preprocessing import StandardScaler
from tqdm import tqdm
from dotenv import load_dotenv
import unicodedata

import warnings
warnings.filterwarnings('ignore')

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# Añadir el path del grafo
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Cargar variables de entorno
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env')))

from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client

BASE_PATH = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
CACHE_DIR = BASE_PATH / 'data' / 'cache_ch'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CURRENT_YEAR = 2026

# --- Helpers de compatibilidad ---

def _get_h_index(citations_list):
    cites = sorted([c for c in citations_list if pd.notnull(c)], reverse=True)
    h = 0
    for i, c in enumerate(cites):
        if c >= (i + 1):
            h = i + 1
        else:
            break
    return h

def _clean_keywords(kw_list):
    if not isinstance(kw_list, (list, np.ndarray)): return []
    return [str(k) for k in kw_list if k]

def _clean_topics(topics_list):
    if not isinstance(topics_list, (list, np.ndarray)): return []
    res = []
    for t in topics_list:
        if isinstance(t, dict):
            name = t.get('display_name') or t.get('name') or t.get('topic')
            if name: res.append(str(name))
        elif t:
            res.append(str(t))
    return res

def compute_citation_velocity(counts_by_year, pub_year) -> dict:
    if not isinstance(counts_by_year, list) or not counts_by_year:
        return {'velocity': np.nan, 'recent_cites_3yr': 0, 'early_impact': 0, 'peak_year': pub_year, 'half_life': np.nan}
    try:
        pub_year = int(pub_year)
    except:
        return {'velocity': np.nan, 'recent_cites_3yr': 0, 'early_impact': 0, 'peak_year': pub_year, 'half_life': np.nan}

    age = max(1, CURRENT_YEAR - pub_year)
    total = sum(y.get('cited_by_count', 0) for y in counts_by_year)
    recent = sum(y.get('cited_by_count', 0) for y in counts_by_year if y.get('year', 0) >= CURRENT_YEAR - 3)
    early = sum(y.get('cited_by_count', 0) for y in counts_by_year if y.get('year', 0) <= pub_year + 1)
    peak_entry = max(counts_by_year, key=lambda x: x.get('cited_by_count', 0), default={})
    peak_year = peak_entry.get('year', pub_year)

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
        'velocity': round(total / age, 3),
        'recent_cites_3yr': int(recent),
        'early_impact': int(early),
        'peak_year': int(peak_year),
        'half_life': half_life,
    }

def compute_interdisciplinarity(topics_series) -> dict:
    from collections import Counter
    topic_counts = Counter()
    domain_counts = Counter()

    for topics in topics_series:
        if not isinstance(topics, list): continue
        for t in topics:
            if not isinstance(t, dict): continue
            topic_name = t.get('topic')
            domain_name = t.get('domain')
            if topic_name: topic_counts[topic_name] += 1
            if domain_name: domain_counts[domain_name] += 1

    if not topic_counts:
        return {'gini_topics': np.nan, 'domain_diversity': 0, 'unique_topics': 0, 'top_topic': None, 'top_domain': None}

    counts = np.array(sorted(topic_counts.values()), dtype=float)
    n = len(counts)
    if n > 1:
        cum = np.cumsum(counts)
        gini = 1 - (2 * cum.sum() - counts.sum() + counts[-1]) / (n * counts.sum())
        gini = round(float(np.clip(gini, 0, 1)), 4)
    else:
        gini = 0.0

    top_topic = topic_counts.most_common(1)[0][0]
    top_domain = domain_counts.most_common(1)[0][0] if domain_counts else None

    return {
        'gini_topics': gini,
        'domain_diversity': len(domain_counts),
        'unique_topics': len(topic_counts),
        'top_topic': top_topic,
        'top_domain': top_domain,
    }

# --- Lógica de ClickHouse ---

def fetch_metadata_from_clickhouse(paper_ids):
    if not paper_ids: return pd.DataFrame()
    clean_ids = [str(pid).split('/')[-1] for pid in paper_ids if pid]
    
    query = """
    SELECT 
        id, doi, title, publication_year as year, cited_by_count as citations,
        fwci, percentile as citation_normalized_percentile,
        is_top_10 as is_in_top_10_percent, is_top_1 as is_in_top_1_percent,
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
        # Asegurar que al menos tenga la columna para el merge
        df['paper_id'] = pd.Series(dtype='object')
        return df

    # Reconstrucción de topics para compatibilidad
    df['topics_list'] = df.apply(lambda r: [{
        'topic': r['topic_id'],
        'subfield': r['subfield_name'],
        'field': r['field_name'],
        'domain': r['domain_name']
    }] if pd.notnull(r['topic_id']) else [], axis=1)
    
    df['paper_id'] = df['id']
    df['Title'] = df['title']
    df['Source'] = df['source_id']
    df['has_oa_data'] = 1
    df['ODS'] = df['sdgs']
    df['countries'] = df['country_codes']
    
    # DOI link
    df['DOI'] = df['doi'].apply(lambda d: f"https://doi.org/{d}" if d and str(d).startswith("10.") else d)
    
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
        df_chunk['entities'] = df_chunk['affiliations'].apply(lambda x: ";".join(list(set([a['ent'] for a in x if a['ent']]))) if isinstance(x, list) else "Sin Entidad")
        df_chunk['institutions'] = df_chunk['affiliations'].apply(lambda x: ";".join(list(set([a['inst'] for a in x if a['inst']]))) if isinstance(x, list) else "Sin Institución")
        df_chunk['topics'] = df_chunk['topics_list']
        
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

    if neo_df.empty: return pd.DataFrame()
    all_paper_ids = neo_df['paper_id'].dropna().unique().tolist()
    df_meta = fetch_metadata_from_clickhouse(all_paper_ids)
    df_final = neo_df.merge(df_meta, on='paper_id', how='left')
    df_final['institutions'] = df_final['institutions'].apply(lambda x: ";".join(x) if isinstance(x, list) else "Sin Institución")
    df_final['topics'] = df_final['topics_list']
    return df_final

# --- Agregación y Guardado ---

def aggregate_metrics(df_papers, group_cols):
    if df_papers.empty: return pd.DataFrame()
    for col in ['fwci', 'is_in_top_10_percent', 'is_in_top_1_percent', 'citation_normalized_percentile']:
        if col in df_papers.columns: df_papers[col] = pd.to_numeric(df_papers[col], errors='coerce')

    if 'oa_status' in df_papers.columns:
        df_papers['is_oa_gold'] = (df_papers['oa_status'] == 'gold').astype(int)
        df_papers['is_oa_green'] = (df_papers['oa_status'] == 'green').astype(int)
        df_papers['is_oa_hybrid'] = (df_papers['oa_status'] == 'hybrid').astype(int)
        df_papers['is_oa_bronze'] = (df_papers['oa_status'] == 'bronze').astype(int)
        df_papers['is_oa_closed'] = (df_papers['oa_status'] == 'closed').astype(int)

    agg_funcs = {
        'paper_id': 'count', 'citations': 'sum', 'fwci': 'mean',
        'citation_normalized_percentile': 'mean', 'is_in_top_10_percent': 'mean',
        'is_in_top_1_percent': 'mean', 'is_oa': 'mean',
        'is_oa_gold': 'mean', 'is_oa_green': 'mean', 'is_oa_hybrid': 'mean', 'is_oa_bronze': 'mean', 'is_oa_closed': 'mean'
    }
    
    # Audit cols
    for acol in ['audit_verdict', 'audit_reason', 'audit_confidence', 'is_snii']:
        if acol in df_papers.columns: agg_funcs[acol] = 'max' if acol == 'is_snii' else 'first'
    
    for col in ['orcid', 'scopus_id', 'entities', 'institutions']:
        if col in df_papers.columns and col not in group_cols: agg_funcs[col] = 'first'

    df_agg = df_papers.groupby(group_cols).agg({k:v for k,v in agg_funcs.items() if k in df_papers.columns}).reset_index()
    df_agg.rename(columns={
        'paper_id': 'num_documents', 'fwci': 'fwci_avg', 'citation_normalized_percentile': 'percentile_avg',
        'is_in_top_10_percent': 'pct_top_10', 'is_in_top_1_percent': 'pct_1', 'is_oa': 'pct_open_access'
    }, inplace=True)
    
    for col in [c for c in df_agg.columns if c.startswith('pct_') or c.startswith('is_oa_')]:
        df_agg[col] *= 100
        
    return df_agg

def save_disaggregated_parquets(df, base_name, group_level='academic', academics_map=None, updated_files=None):
    if df.empty: return
    for name, grp in df.groupby('academic_name' if group_level == 'academic' else 'entity_name'):
        safe_name = str(name).replace('/', '_').replace('\\', '_')
        path = CACHE_DIR / safe_name
        path.mkdir(parents=True, exist_ok=True)
        grp.to_parquet(path / base_name, index=False)
        if updated_files is not None: updated_files.add(str((path / base_name).absolute()))

def normalize_name(text):
    if not isinstance(text, str): return ""
    return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').upper().strip()

def process_and_save(entity_filter=None, academic_filter=None, source_filter='all'):
    print(f"🚀 Iniciando proceso optimizado con ClickHouse (Fuente: {source_filter})...")
    updated_files = set()
    
    df_raw_list = []
    for chunk_df in extract_academic_papers(academic_filter, entity_filter, source_filter):
        if not chunk_df.empty: df_raw_list.append(chunk_df)
    
    if not df_raw_list: return print("❌ No se encontraron datos.")
    df_raw = pd.concat(df_raw_list, ignore_index=True).drop_duplicates(subset=['academic_name', 'paper_id'])
    print(f"✅ {len(df_raw)} papers cargados.")

    # Guardar parquets básicos
    save_disaggregated_parquets(df_raw, 'papers_profesor.parquet', 'academic', updated_files=updated_files)
    
    df_inv_tot = aggregate_metrics(df_raw, ['academic_name'])
    save_disaggregated_parquets(df_inv_tot, 'investigador_total.parquet', 'academic', updated_files=updated_files)
    
    # Entidad
    df_inst_raw = extract_entity_papers(entity_filter, source_filter)
    if not df_inst_raw.empty:
        save_disaggregated_parquets(df_inst_raw, 'papers_institucion.parquet', 'entity', updated_files=updated_files)
        df_inst_tot = aggregate_metrics(df_inst_raw, ['entity_name'])
        save_disaggregated_parquets(df_inst_tot, 'institucion_total.parquet', 'entity', updated_files=updated_files)

    print("✅ Proceso completado exitosamente.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity")
    parser.add_argument("--academic")
    args = parser.parse_args()
    process_and_save(entity_filter=args.entity, academic_filter=args.academic)
