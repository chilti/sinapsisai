import pandas as pd
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from database.clickhouse_db import ch_client

def format_authors(authors):
    if not isinstance(authors, (list, tuple)):
        return ""
    if len(authors) == 0:
        return ""
    if len(authors) <= 2:
        return " y ".join(str(a) for a in authors)
    return f"{authors[0]} et al."

def build_json(csv_path, out_path, name_col, inst_col, extra_cols=None, top_n_legend=20):
    if '--force' not in sys.argv and os.path.exists(out_path):
        print(f"  -> {out_path} ya existe. Saltando generación JSON...")
        return

    print(f"Procesando {csv_path}...")
    df = pd.read_csv(csv_path)
    
    institutions = df[inst_col].fillna('Sin Institución').unique().tolist()
    inst_map = {name: i for i, name in enumerate(institutions)}
    
    # Enriquecer artículos con autores y revistas si corresponde
    if 'articles' in csv_path and 'doi' in df.columns:
        print("  -> Extrayendo autores nacionales y revistas de ClickHouse...")
        
        # 1. Obtener works: id, doi, source_id para cruzar revista
        df_works = ch_client.query_df("SELECT id as openalex_id, doi, source_id FROM works_academic_all WHERE doi != ''")
        df_works['doi'] = df_works['doi'].astype(str).str.replace('https://doi.org/', '', regex=False)
        df_works = df_works.drop_duplicates(subset=['doi'])
        
        # 2. Obtener nombres de revistas desde tabla sources
        df_sources = ch_client.query_df("SELECT id as source_id, display_name as journal FROM sources")
        df_sources = df_sources.drop_duplicates(subset=['source_id'])
        df_works = df_works.merge(df_sources, on='source_id', how='left')
        
        # 3. Obtener autores nacionales agrupados por OpenAlex Work ID
        q_authors = "SELECT paper_id as openalex_id, groupArray(academic_name) as author_names FROM paper_author_map WHERE paper_id LIKE 'https://openalex.org/%' GROUP BY paper_id"
        df_authors = ch_client.query_df(q_authors)
        df_authors['authors'] = df_authors['author_names'].apply(format_authors)
        
        # 4. Unir con el dataset principal:
        #    doi -> openalex_id (y journal), luego openalex_id -> authors
        df = df.merge(df_works[['doi', 'openalex_id', 'journal']], on='doi', how='left')
        df = df.merge(df_authors[['openalex_id', 'authors']], on='openalex_id', how='left')
        
        df['authors'] = df['authors'].fillna('')
        df['journal'] = df['journal'].fillna('')
        df['openalex_id'] = df['openalex_id'].fillna('')
        
        if extra_cols is None:
            extra_cols = []
        extra_cols.extend(['authors', 'journal', 'openalex_id'])
        
        # Si el CSV ya tiene cluster_label (generado por cluster_articles.py), lo añadimos
        if 'cluster_label' in df.columns:
            df['cluster_label'] = df['cluster_label'].fillna('Ruido')
            extra_cols.append('cluster_label')
    
    data = {
        'x': df['x'].round(4).tolist(),
        'y': df['y'].round(4).tolist(),
        'names': df[name_col].astype(str).fillna('').tolist(),
        'institutions': df[inst_col].astype(str).fillna('Sin Institución').tolist(),
        'inst_idx': df[inst_col].fillna('Sin Institución').map(inst_map).tolist(),
        'inst_labels': institutions[:top_n_legend],
        'total': len(df)
    }
    
    # Agregar metadatos adicionales si se solicitan
    if extra_cols:
        data['extras'] = {}
        for col in extra_cols:
            if col in df.columns:
                data['extras'][col] = df[col].astype(str).fillna('').tolist()
    
    with open(out_path, 'w') as f:
        json.dump(data, f)
        
    print(f"Exportados {len(df)} puntos a {out_path}. Tamaño: {os.path.getsize(out_path)/1024/1024:.1f} MB")

if __name__ == '__main__':
    # Personas
    build_json(
        'data/maps/people_umap.csv', 
        'public/tiles/people_data.json', 
        name_col='fullname', 
        inst_col='institution',
        extra_cols=['is_snii', 'snii_level']
    )
    
    # Personas (Estructura + Temas + ODS)
    build_json(
        'data/maps/people_topics_umap.csv', 
        'public/tiles/people_topics_data.json', 
        name_col='fullname', 
        inst_col='institution',
        extra_cols=['is_snii', 'snii_level']
    )
    
    # Artículos (Original de Qdrant, conservado por compatibilidad si existe)
    if os.path.exists('data/maps/articles_umap.csv'):
        build_json(
            'data/maps/articles_umap.csv', 
            'public/tiles/articles_data.json', 
            name_col='title', 
            inst_col='institution',
            extra_cols=['year', 'cluster_label', 'doi']
        )
    
    # Desempeño (usando institution como categoría primaria)
    build_json(
        'data/maps/performance_umap.csv', 
        'public/tiles/performance_data.json', 
        name_col='fullname', 
        inst_col='country', # Agrupar por país en la leyenda de desempeño
        extra_cols=['institution', 'dependency', 'pct_top_10', 'fwci_avg', 'pct_1', 'percentile_avg']
    )
    
    # --- Nuevos Mapas ---
    
    # 1. Artículos (Nomic desde ClickHouse)
    if os.path.exists('data/maps/articles_nomic_umap.csv'):
        build_json(
            'data/maps/articles_nomic_umap.csv',
            'public/tiles/articles_nomic_data.json',
            name_col='title',
            inst_col='institution',
            extra_cols=['year', 'cluster_label', 'doi']
        )
        # Hacer copia a articles_data.json para compatibilidad con la vista por defecto
        import shutil
        shutil.copy('public/tiles/articles_nomic_data.json', 'public/tiles/articles_data.json')
        print("Copied articles_nomic_data.json to articles_data.json (default)")
        
    # 2. Artículos (SPECTER2 desde ClickHouse)
    if os.path.exists('data/maps/articles_specter_umap.csv'):
        build_json(
            'data/maps/articles_specter_umap.csv',
            'public/tiles/articles_specter_data.json',
            name_col='title',
            inst_col='institution',
            extra_cols=['year', 'cluster_label', 'doi']
        )
        
    # 3. Académicos (Semántica SPECTER2)
    if os.path.exists('data/maps/people_semantic_umap.csv'):
        build_json(
            'data/maps/people_semantic_umap.csv',
            'public/tiles/people_semantic_data.json',
            name_col='fullname',
            inst_col='institution',
            extra_cols=['is_snii', 'snii_level', 'dependency']
        )
    
    print("Todo listo.")

