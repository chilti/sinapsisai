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
    if 'articles' in csv_path and 'id' in df.columns:
        print("  -> Extrayendo autores nacionales y revistas de ClickHouse...")
        
        # Función auxiliar para normalizar DOIs
        def clean_doi_str(val):
            if not val or pd.isna(val):
                return ""
            return str(val).replace('https://doi.org/', '').strip().lower()
        
        # 1. Obtener works: id as openalex_id, doi, source_id para cruzar revista
        df_works = ch_client.query_df("SELECT id as openalex_id, doi, source_id FROM works_academic_all")
        df_works = df_works.drop_duplicates(subset=['openalex_id'])
        df_works['clean_doi'] = df_works['doi'].fillna('').apply(clean_doi_str)
        df_works = df_works.drop(columns=['doi'])
        
        # 2. Obtener nombres de revistas desde tabla sources
        df_sources = ch_client.query_df("SELECT id as source_id, display_name as journal FROM sources")
        df_sources = df_sources.drop_duplicates(subset=['source_id'])
        
        # 3. Obtener autores nacionales agrupados por OpenAlex Work ID
        q_authors = "SELECT paper_id as openalex_id, groupArray(academic_name) as author_names FROM paper_author_map WHERE paper_id LIKE 'https://openalex.org/%' GROUP BY paper_id"
        df_authors = ch_client.query_df(q_authors)
        df_authors['authors'] = df_authors['author_names'].apply(format_authors)
        
        # 4. Unir con el dataset principal
        # Primero cruzamos por ID directo
        df = df.merge(df_works, left_on='id', right_on='openalex_id', how='left')
        
        # Si quedan registros sin openalex_id y tenemos doi en el CSV, intentamos cruzar por DOI
        if 'doi' in df.columns:
            df['clean_doi'] = df['doi'].fillna('').apply(clean_doi_str)
            df_works_doi = df_works[df_works['clean_doi'] != ''][['clean_doi', 'openalex_id', 'source_id']].rename(
                columns={'openalex_id': 'oa_id_by_doi', 'source_id': 'source_id_by_doi'}
            )
            df_works_doi = df_works_doi.drop_duplicates(subset=['clean_doi'])
            df = df.merge(df_works_doi, on='clean_doi', how='left')
            df['openalex_id'] = df['openalex_id'].fillna(df['oa_id_by_doi'])
            df['source_id'] = df['source_id'].fillna(df['source_id_by_doi'])
            df = df.drop(columns=['oa_id_by_doi', 'source_id_by_doi'])
            
        df = df.merge(df_sources, on='source_id', how='left')
        df = df.merge(df_authors[['openalex_id', 'authors']], on='openalex_id', how='left')
        
        df['authors'] = df['authors'].fillna('')
        df['journal'] = df['journal'].fillna('')
        df['openalex_id'] = df['openalex_id'].fillna(df['id'])
        
        if extra_cols is None:
            extra_cols = []
        extra_cols.extend(['authors', 'journal', 'openalex_id'])
        
        # Si el CSV ya tiene cluster_label (generado por cluster_articles.py), lo añadimos
        if 'cluster_label' in df.columns:
            df['cluster_label'] = df['cluster_label'].fillna('Ruido')
            extra_cols.append('cluster_label')
    
    # ── Optimización 1: Codificación por Diccionario de Instituciones ──
    # Ya no incluimos el array gigante 'institutions' de strings en data.
    # En su lugar, metemos 'institutions_list' con los valores únicos, e 'inst_idx' de enteros.
    data = {
        'x': df['x'].round(4).tolist(),
        'y': df['y'].round(4).tolist(),
        'names': df[name_col].astype(str).fillna('').str.slice(0, 90).tolist(),
        'inst_idx': df[inst_col].fillna('Sin Institución').map(inst_map).tolist(),
        'institutions_list': institutions,
        'inst_labels': institutions[:top_n_legend],
        'total': len(df)
    }
    
    # Agregar metadatos adicionales si se solicitan
    if extra_cols:
        data['extras'] = {}
        for col in extra_cols:
            if col in df.columns:
                # ── Optimización 2: Codificación por Diccionario para campos repetitivos ──
                if col == 'journal':
                    # Extraer revistas únicas
                    unique_journals = df['journal'].fillna('').astype(str).unique().tolist()
                    journal_map = {name: i for i, name in enumerate(unique_journals)}
                    data['journals_list'] = unique_journals
                    data['extras']['journal'] = df['journal'].fillna('').astype(str).map(journal_map).tolist()
                elif col == 'authors':
                    # Extraer autores únicos
                    unique_authors = df['authors'].fillna('').astype(str).unique().tolist()
                    author_map = {name: i for i, name in enumerate(unique_authors)}
                    data['authors_list'] = unique_authors
                    data['extras']['authors'] = df['authors'].fillna('').astype(str).map(author_map).tolist()
                elif col == 'cluster_label':
                    # Extraer cluster labels únicos
                    unique_labels = df['cluster_label'].fillna('Ruido').astype(str).unique().tolist()
                    label_map = {name: i for i, name in enumerate(unique_labels)}
                    data['cluster_labels_list'] = unique_labels
                    data['extras']['cluster_label'] = df['cluster_label'].fillna('Ruido').astype(str).map(label_map).tolist()
                elif col == 'openalex_id':
                    # Convertir a enteros para ahorrar espacio y memoria en JS (removiendo prefijo W)
                    def clean_oa_id(val):
                        if not val:
                            return 0
                        val_str = str(val).replace('https://openalex.org/', '').strip()
                        if val_str.startswith('W') and val_str[1:].isdigit():
                            return int(val_str[1:])
                        elif val_str.isdigit():
                            return int(val_str)
                        return 0
                    data['extras']['openalex_id'] = df['openalex_id'].fillna('').apply(clean_oa_id).tolist()
                else:
                    data['extras'][col] = df[col].astype(str).fillna('').tolist()
    
    # ── Optimización 3: Carga en Dos Fases para datasets grandes ──
    # Para datasets con >200K puntos, separamos datos de renderizado (ligero)
    # de metadatos (pesado: nombres, autores, revistas) para carga progresiva.
    SPLIT_THRESHOLD = 200_000
    
    if len(df) > SPLIT_THRESHOLD:
        # Archivo de renderizado (ligero): solo coordenadas, categorías y diccionarios
        render_data = {
            'x': data['x'],
            'y': data['y'],
            'inst_idx': data['inst_idx'],
            'institutions_list': data['institutions_list'],
            'inst_labels': data['inst_labels'],
            'total': data['total'],
            'has_meta': True,  # Flag para indicar al cliente que hay un archivo _meta.json
        }
        # Incluir cluster_label (indices enteros, compacto) y su diccionario
        if 'extras' in data and 'cluster_label' in data['extras']:
            render_data['extras'] = {'cluster_label': data['extras']['cluster_label']}
            if 'cluster_labels_list' in data:
                render_data['cluster_labels_list'] = data['cluster_labels_list']
        # Incluir year (enteros compactos)
        if 'extras' in data and 'year' in data['extras']:
            render_data.setdefault('extras', {})['year'] = data['extras']['year']
        
        with open(out_path, 'w') as f:
            json.dump(render_data, f)
        render_size = os.path.getsize(out_path) / 1024 / 1024
        
        # Archivo de metadatos (pesado): nombres, autores, revistas, openalex_id
        meta_data = {
            'names': data['names'],
        }
        # Mover extras pesados al archivo meta
        meta_extras = {}
        for key in ['authors', 'journal', 'openalex_id']:
            if 'extras' in data and key in data['extras']:
                meta_extras[key] = data['extras'][key]
        if meta_extras:
            meta_data['extras'] = meta_extras
        # Mover diccionarios de strings al archivo meta
        if 'authors_list' in data:
            meta_data['authors_list'] = data['authors_list']
        if 'journals_list' in data:
            meta_data['journals_list'] = data['journals_list']
            
        meta_path = out_path.replace('_data.json', '_meta.json')
        with open(meta_path, 'w') as f:
            json.dump(meta_data, f)
        meta_size = os.path.getsize(meta_path) / 1024 / 1024
        
        print(f"Exportados {len(df)} puntos (SPLIT):")
        print(f"  Render: {out_path} ({render_size:.1f} MB)")
        print(f"  Meta:   {meta_path} ({meta_size:.1f} MB)")
    else:
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
            extra_cols=['year', 'cluster_label']
        )
    
    # Desempeño (usando institution como categoría primaria)
    build_json(
        'data/maps/performance_umap.csv', 
        'public/tiles/performance_data.json', 
        name_col='fullname', 
        inst_col='country', # Agrupar por país en la leyenda de desempeño
        extra_cols=['institution', 'dependency', 'pct_top_10', 'fwci_avg', 'pct_1', 'percentile_avg', 'num_documents']
    )
    
    # --- Nuevos Mapas ---
    
    # 1. Artículos (Nomic desde ClickHouse)
    if os.path.exists('data/maps/articles_nomic_umap.csv'):
        build_json(
            'data/maps/articles_nomic_umap.csv',
            'public/tiles/articles_nomic_data.json',
            name_col='title',
            inst_col='institution',
            extra_cols=['year', 'cluster_label']
        )
        
    # 2. Artículos (SPECTER2 desde ClickHouse)
    if os.path.exists('data/maps/articles_specter_umap.csv'):
        build_json(
            'data/maps/articles_specter_umap.csv',
            'public/tiles/articles_specter_data.json',
            name_col='title',
            inst_col='institution',
            extra_cols=['year', 'cluster_label']
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

