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
    print(f"Procesando {csv_path}...")
    df = pd.read_csv(csv_path)
    
    institutions = df[inst_col].fillna('Sin Institución').unique().tolist()
    inst_map = {name: i for i, name in enumerate(institutions)}
    
    # Enriquecer artículos con autores y revistas si corresponde
    if 'articles' in csv_path and 'doi' in df.columns:
        print("  -> Extrayendo autores nacionales y revistas de ClickHouse...")
        
        # 1. Obtener autores nacionales agrupados por DOI desde paper_author_map
        q_authors = "SELECT paper_id as doi, groupArray(academic_name) as author_names FROM paper_author_map GROUP BY paper_id"
        df_authors = ch_client.query_df(q_authors)
        df_authors = df_authors.drop_duplicates(subset=['doi'])
        
        # 2. Obtener source_id y openalex_id de los works para cruzar la revista
        df_works = ch_client.query_df("SELECT id as openalex_id, doi, source_id FROM works_academic_all WHERE doi != ''")
        
        # Limpiar el prefijo de doi para que coincida con el UMAP
        df_works['doi'] = df_works['doi'].astype(str).str.replace('https://doi.org/', '', regex=False)
        df_works = df_works.drop_duplicates(subset=['doi'])
        
        # 3. Obtener nombres de las revistas y evitar duplicados de origen
        df_sources = ch_client.query_df("SELECT id as source_id, display_name as journal FROM sources")
        df_sources = df_sources.drop_duplicates(subset=['source_id'])
        
        # 4. Hacer los joins en pandas
        df_works = df_works.merge(df_sources, on='source_id', how='left')
        
        # 5. Formatear autores nacionales
        df_authors['authors'] = df_authors['author_names'].apply(format_authors)
        
        # 6. Unir con el dataset principal
        df = df.merge(df_authors[['doi', 'authors']], on='doi', how='left')
        df = df.merge(df_works[['doi', 'journal', 'openalex_id']], on='doi', how='left')
        
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
    
    # Artículos
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
    
    print("Todo listo.")
