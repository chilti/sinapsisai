import os
import json
import pandas as pd

INPUT_DIR = "data/networks"
OUTPUT_DIR = "public/tiles"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def name_communities(df, label_col='cluster_label', id_col='id', name_col='name', pagerank_col='pagerank', community_col='community'):
    """
    Asigna nombres descriptivos a las comunidades de Louvain usando el nodo con mayor PageRank.
    """
    # Encontrar el nodo más importante (mayor pagerank) por cada comunidad
    top_nodes = df.groupby(community_col).apply(
        lambda g: g.nlargest(1, pagerank_col) if len(g) > 0 else None,
        include_groups=False
    ).reset_index()
    
    # Crear un diccionario de mapeo: community_id -> nombre_descriptivo
    community_map = {}
    for _, row in top_nodes.iterrows():
        comm_val = row[community_col]
        # Extraer el nombre del nodo principal
        # Dado que pandas groupby/apply devuelve un multi-index o filas de dataframe,
        # buscamos la fila en df original para evitar discrepancias.
        top_node_row = df[(df[community_col] == comm_val) & (df[pagerank_col] == row[pagerank_col])]
        if not top_node_row.empty:
            top_name = top_node_row.iloc[0][name_col]
            community_map[comm_val] = f"Grupo {int(comm_val)} - Preside: {top_name}"
        else:
            community_map[comm_val] = f"Grupo {int(comm_val)}"
            
    # Asignar -1 (sin comunidad) a 'Ruido'
    community_map[-1] = 'Ruido'
    
    return community_map

def build_network_json_file(df, out_path, name_col, category_col, extra_cols=None, top_n_legend=25, links=None):
    """
    Genera un archivo JSON compatible con regl-scatterplot para visualización de red.
    """
    print(f"Procesando y guardando {out_path}...")
    
    # Rellenar nulos — IMPORTANTE: fillna() debe ir ANTES de astype(str),
    # porque astype convierte pd.NA al string literal '<NA>' y fillna ya no lo detecta.
    df['x'] = df['x'].fillna(0.0)
    df['y'] = df['y'].fillna(0.0)
    df[name_col] = df[name_col].fillna('Sin Nombre').astype(str).replace('<NA>', 'Sin Nombre').str.strip()
    df[name_col] = df[name_col].replace('', 'Sin Nombre')
    df[category_col] = df[category_col].fillna('Desconocido').astype(str).replace('<NA>', 'Desconocido').str.strip()
    df[category_col] = df[category_col].replace('', 'Desconocido')

    
    # Categorías únicas
    categories = df[category_col].unique().tolist()
    cat_map = {name: i for i, name in enumerate(categories)}
    
    # Estructura base del JSON
    data = {
        'x': df['x'].round(4).tolist(),
        'y': df['y'].round(4).tolist(),
        'names': df[name_col].str.slice(0, 90).tolist(),
        'inst_idx': df[category_col].map(cat_map).tolist(),
        'institutions_list': categories,
        'inst_labels': categories[:top_n_legend],
        'total': len(df)
    }
    
    if links is not None:
        data['links'] = links
        
    # Agregar extras
    if extra_cols:
        data['extras'] = {}
        for col in extra_cols:
            if col in df.columns:
                if col == 'cluster_label':
                    # Codificación por diccionario de los temas/comunidades
                    unique_labels = df['cluster_label'].unique().tolist()
                    label_map = {name: i for i, name in enumerate(unique_labels)}
                    data['cluster_labels_list'] = unique_labels
                    data['extras']['cluster_label'] = df['cluster_label'].map(label_map).tolist()
                elif col == 'is_snii':
                    data['extras']['is_snii'] = df['is_snii'].astype(int).tolist()
                elif col == 'pagerank':
                    data['extras']['pagerank'] = df['pagerank'].round(6).tolist()
                else:
                    data['extras'][col] = df[col].tolist()
                    
    with open(out_path, 'w') as f:
        json.dump(data, f)
        
    print(f"  -> Exportado {len(df)} puntos. Tamaño: {os.path.getsize(out_path)/1024/1024:.2f} MB")


def export_coauthorship():
    path = os.path.join(INPUT_DIR, "coauthorship_results.parquet")
    if not os.path.exists(path):
        print("❌ Error: No existe coauthorship_results.parquet")
        return
        
    df = pd.read_parquet(path)
    
    # Excluir nodos sin fullname (Person con nombres nulos o vacíos en Neo4j)
    before = len(df)
    df = df[df['fullname'].notna() & (df['fullname'].astype(str).str.strip() != '') & (df['fullname'].astype(str) != '<NA>')]
    excluded = before - len(df)
    print(f"  -> Excluidos {excluded} nodos sin fullname. Quedan {len(df)} nodos.")
    
    # Renombrar columnas para usar el helper
    df['name'] = df['fullname']
    
    # Generar etiquetas descriptivas de comunidades
    comm_map = name_communities(df)
    df['cluster_label'] = df['community'].map(comm_map)
    
    # Mapear aristas a índices enteros (los nodos excluidos quedan como NaN y se descartan)
    id_to_idx = {nid: i for i, nid in enumerate(df['id'])}
    edges_path = os.path.join(INPUT_DIR, "coauthorship_edges.parquet")
    links = []
    if os.path.exists(edges_path):
        print("Cargando y mapeando aristas de coautoría...")
        edges_df = pd.read_parquet(edges_path)
        edges_df['source_idx'] = edges_df['source'].map(id_to_idx)
        edges_df['target_idx'] = edges_df['target'].map(id_to_idx)
        links = edges_df.dropna(subset=['source_idx', 'target_idx'])[['source_idx', 'target_idx']].astype(int).values.tolist()
        print(f"  -> Mapeadas {len(links)} aristas (tras excluir nodos sin nombre).")
    else:
        print("⚠️ Advertencia: No existe coauthorship_edges.parquet")
        
    out_path = os.path.join(OUTPUT_DIR, "network_coauthorship_data.json")
    build_network_json_file(
        df, 
        out_path, 
        name_col='fullname', 
        category_col='institution',
        extra_cols=['cluster_label', 'pagerank', 'is_snii', 'snii_level'],
        links=links
    )


def export_institutional():
    path = os.path.join(INPUT_DIR, "institutional_results.parquet")
    if not os.path.exists(path):
        print("❌ Error: No existe institutional_results.parquet")
        return
        
    df = pd.read_parquet(path)
    
    # Generar etiquetas descriptivas de comunidades
    comm_map = name_communities(df)
    df['cluster_label'] = df['community'].map(comm_map)
    
    # Mapear aristas a índices enteros
    id_to_idx = {nid: i for i, nid in enumerate(df['id'])}
    edges_path = os.path.join(INPUT_DIR, "institutional_edges.parquet")
    links = []
    if os.path.exists(edges_path):
        print("Cargando y mapeando aristas institucionales...")
        edges_df = pd.read_parquet(edges_path)
        edges_df['source_idx'] = edges_df['source'].map(id_to_idx)
        edges_df['target_idx'] = edges_df['target'].map(id_to_idx)
        links = edges_df.dropna(subset=['source_idx', 'target_idx'])[['source_idx', 'target_idx']].astype(int).values.tolist()
        print(f"  -> Mapeadas {len(links)} aristas.")
    else:
        print("⚠️ Advertencia: No existe institutional_edges.parquet")
        
    out_path = os.path.join(OUTPUT_DIR, "network_institutional_data.json")
    build_network_json_file(
        df, 
        out_path, 
        name_col='name', 
        category_col='type',
        extra_cols=['cluster_label', 'pagerank', 'country_code'],
        links=links
    )


def export_bipartite():
    auth_path = os.path.join(INPUT_DIR, "bipartite_authors_results.parquet")
    concept_path = os.path.join(INPUT_DIR, "bipartite_concepts_results.parquet")
    
    if not os.path.exists(auth_path) or not os.path.exists(concept_path):
        print("❌ Error: Faltan archivos de resultados de red bipartita.")
        return
        
    df_auth = pd.read_parquet(auth_path)
    df_concept = pd.read_parquet(concept_path)
    
    # Normalizar columnas para la unión
    df_auth_sub = pd.DataFrame({
        'id': df_auth['id'],
        'name': df_auth['fullname'],
        'type': 'Investigador',
        'x': df_auth['x'],
        'y': df_auth['y'],
        'pagerank': df_auth['pagerank'],
        'community': df_auth['community']
    })
    
    # Tópico u ODS
    df_concept['type'] = df_concept['type'].fillna('TOPIC').map({
        'TOPIC': 'Tema de OpenAlex',
        'SDG': 'ODS (Objetivo Sostenible)'
    })
    
    df_concept_sub = pd.DataFrame({
        'id': df_concept['id'],
        'name': df_concept['name'],
        'type': df_concept['type'],
        'x': df_concept['x'],
        'y': df_concept['y'],
        'pagerank': df_concept['pagerank'],
        'community': df_concept['community']
    })
    
    # Combinar
    df_comb = pd.concat([df_auth_sub, df_concept_sub], ignore_index=True)
    
    # Generar etiquetas descriptivas de comunidades para la red bipartita
    comm_map = name_communities(df_comb)
    df_comb['cluster_label'] = df_comb['community'].map(comm_map)
    
    # Mapear aristas a índices enteros
    id_to_idx = {nid: i for i, nid in enumerate(df_comb['id'])}
    topic_edges_path = os.path.join(INPUT_DIR, "topic_edges.parquet")
    sdg_edges_path = os.path.join(INPUT_DIR, "sdg_edges.parquet")
    links = []
    
    # 1. Aristas Autor-Tópico
    if os.path.exists(topic_edges_path):
        print("Cargando y mapeando aristas Autor-Tópico...")
        t_df = pd.read_parquet(topic_edges_path)
        t_df['source_idx'] = t_df['source'].map(id_to_idx)
        t_df['target_idx'] = t_df['target'].map(id_to_idx)
        t_links = t_df.dropna(subset=['source_idx', 'target_idx'])[['source_idx', 'target_idx']].astype(int).values.tolist()
        links.extend(t_links)
        print(f"  -> Mapeadas {len(t_links)} aristas Autor-Tópico.")
        
    # 2. Aristas Autor-ODS
    if os.path.exists(sdg_edges_path):
        print("Cargando y mapeando aristas Autor-ODS...")
        s_df = pd.read_parquet(sdg_edges_path)
        s_df['source_idx'] = s_df['source'].map(id_to_idx)
        s_df['target_idx'] = s_df['target'].map(id_to_idx)
        s_links = s_df.dropna(subset=['source_idx', 'target_idx'])[['source_idx', 'target_idx']].astype(int).values.tolist()
        links.extend(s_links)
        print(f"  -> Mapeadas {len(s_links)} aristas Autor-ODS.")
        
    out_path = os.path.join(OUTPUT_DIR, "network_bipartite_data.json")
    build_network_json_file(
        df_comb, 
        out_path, 
        name_col='name', 
        category_col='type',
        extra_cols=['cluster_label', 'pagerank'],
        links=links
    )


def main():
    export_coauthorship()
    print("-" * 50)
    export_institutional()
    print("-" * 50)
    export_bipartite()
    print("\n✅ Archivos JSON de visualización de red generados exitosamente.")

if __name__ == "__main__":
    main()
