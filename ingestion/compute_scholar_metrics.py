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

def extract_academic_papers():
    """Descarga los metadatos completos de todas las publicaciones por Académico."""
    graph_store = Neo4jGraphStore()
    
    query = """
    MATCH (a:Academic)-[:AUTHORED]->(p)
    OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity)
    OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
    RETURN a.name AS academic_name,
           collect(DISTINCT e.name) AS entities,
           p.id AS paper_id,
           p.year AS year,
           p.citations AS citations,
           p.raw_metadata AS raw_metadata,
           s.id AS sdg_id,
           s.name AS sdg_name,
           r.confidence AS sdg_confidence,
           r.reasoning AS sdg_reasoning
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
            
            fwci = raw_meta.get('fwci', None) 
            title = raw_meta.get('Title', 'No Title')
            source = raw_meta.get('Source', 'Unknown')
            doi_link = "https://doi.org/" + row['paper_id'] if row['paper_id'] and not "urn:" in row['paper_id'] else None
            
            topics = raw_meta.get('OpenAlex_Topics', [])
            if not isinstance(topics, list): topics = []
            
            records.append({
                'academic_name': row['academic_name'],
                'entities': ";".join(row['entities']) if row['entities'] else "UNAM",
                'paper_id': row['paper_id'],
                'year': row['year'],
                'citations': row['citations'],
                'Title': title,
                'Source': source,
                'DOI': doi_link,
                'Link': doi_link,
                'fwci': fwci,
                'topics': topics,
                'ODS_ID': row['sdg_id'] if row['sdg_id'] else None,
                'ODS_Nombre': row['sdg_name'] if row['sdg_name'] else None,
                'ODS_Confianza': row['sdg_confidence'] if row['sdg_confidence'] else None,
                'ODS_Justificacion': row['sdg_reasoning'] if row['sdg_reasoning'] else None
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
           s.id AS sdg_id,
           s.name AS sdg_name,
           r.confidence AS sdg_confidence,
           r.reasoning AS sdg_reasoning
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
            
            fwci = raw_meta.get('fwci', None) 
            title = raw_meta.get('Title', 'No Title')
            source = raw_meta.get('Source', 'Unknown')
            doi_link = "https://doi.org/" + row['paper_id'] if row['paper_id'] and not "urn:" in row['paper_id'] else None
            
            topics = raw_meta.get('OpenAlex_Topics', [])
            if not isinstance(topics, list): topics = []
            
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
                'topics': topics,
                'ODS_ID': row['sdg_id'] if row['sdg_id'] else None,
                'ODS_Nombre': row['sdg_name'] if row['sdg_name'] else None,
                'ODS_Confianza': row['sdg_confidence'] if row['sdg_confidence'] else None,
                'ODS_Justificacion': row['sdg_reasoning'] if row['sdg_reasoning'] else None
            })
            
    return pd.DataFrame(records)

def compute_percentiles(df):
    """Calcula percentiles globales localmente para simular Top 10% y 1% si no existen."""
    # Como la base local es la "institución", los percentiles son intrainstitucionales
    df['percentile'] = df['citations'].rank(pct=True) * 100
    df['is_top_10'] = (df['percentile'] >= 90).astype(int)
    df['is_top_1'] = (df['percentile'] >= 99).astype(int)
    return df

def aggregate_metrics(df_papers, group_cols):
    """Realiza la agregación principal de base para los grupos especificados."""
    if df_papers.empty: return pd.DataFrame()
    
    agg_funcs = {
        'paper_id': 'count',
        'citations': 'sum',
        'fwci': 'mean',
        'percentile': 'mean',
        'is_top_10': 'mean',  # Al promediar el int 0/1 nos da la proporcion 0.0-1.0
        'is_top_1': 'mean'
    }
    
    df_agg = df_papers.groupby(group_cols).agg(agg_funcs).reset_index()
    df_agg.rename(columns={
        'paper_id': 'num_documents',
        'fwci': 'fwci_avg',
        'percentile': 'percentile_avg',
        'is_top_10': 'pct_top_10',
        'is_top_1': 'pct_1'
    }, inplace=True)
    
    # pct a base 100
    df_agg['pct_top_10'] *= 100
    df_agg['pct_1'] *= 100
    
    # Llenar nulos
    df_agg['fwci_avg'] = df_agg['fwci_avg'].fillna(df_agg['citations'] / df_agg['num_documents'].replace(0,1)) # Proxy si no hay FWCI real
    df_agg['percentile_avg'] = df_agg['percentile_avg'].fillna(50)
    
    # Calcular indice H para el agrupamiento
    # Agrupamos la serie de citas original
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
    df_raw = compute_percentiles(df_raw)
    
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
        # Sumamos por investigador y jerarquía
        df_topics_agg = df_topics.groupby(['academic_name', 'domain', 'field', 'subfield', 'topic']).size().reset_index(name='value')
        df_topics_agg.to_parquet(CACHE_DIR / 'topics_investigador.parquet', index=False)
        # Limpiamos remanentes
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
    df_inv_tot.to_parquet(CACHE_DIR / 'investigador_total.parquet', index=False)
    
    df_raw_recent = df_raw[(df_raw['year'] >= 2021) & (df_raw['year'] <= 2025)]
    df_inv_recent = aggregate_metrics(df_raw_recent, ['academic_name', 'entities'])
    df_inv_recent.to_parquet(CACHE_DIR / 'investigador_recent.parquet', index=False)
    
    # 3. AGREGARES A NIVEL INSTITUCIÓN (Macro) - Ahora usa la información general de la Entidad
    print("⏳ Extrayendo y agregando métricas de DOIs de Entidades...")
    df_inst_raw = extract_entity_papers()
    if not df_inst_raw.empty:
        df_inst_raw['year'] = pd.to_numeric(df_inst_raw['year'], errors='coerce')
        df_inst_raw = df_inst_raw.dropna(subset=['year'])
        df_inst_raw = compute_percentiles(df_inst_raw)
        
        # Exportar listado general de papers de Institucion
        df_inst_raw.to_parquet(CACHE_DIR / 'papers_institucion.parquet', index=False)
        
        df_inst_tot = aggregate_metrics(df_inst_raw, ['entity_name'])
        df_inst_tot.to_parquet(CACHE_DIR / 'institucion_total.parquet', index=False)
    
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
