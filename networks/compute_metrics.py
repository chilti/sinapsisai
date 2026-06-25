import os
import sys
import pandas as pd
import cudf
import cugraph
from cugraph.layout import force_atlas2

OUTPUT_DIR = "data/networks"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def process_coauthorship():
    print("\n🚀 Procesando Red de Coautoría en GPU...")
    
    edges_path = os.path.join(OUTPUT_DIR, "coauthorship_edges.parquet")
    nodes_path = os.path.join(OUTPUT_DIR, "coauthorship_nodes.parquet")
    
    if not os.path.exists(edges_path) or not os.path.exists(nodes_path):
        print("❌ Error: Faltan archivos parquet de entrada para coautoría.")
        return
        
    # Cargar datos en cuDF
    df_edges = cudf.read_parquet(edges_path)
    df_nodes = cudf.read_parquet(nodes_path)
    
    print(f"  -> Cargados {len(df_nodes)} nodos y {len(df_edges)} aristas.")
    
    # Crear grafo
    G = cugraph.Graph()
    G.from_cudf_edgelist(
        df_edges, 
        source='source', 
        destination='target', 
        edge_attr='weight', 
        renumber=True
    )
    
    # 1. PageRank
    print("  -> Calculando PageRank...")
    df_pr = cugraph.pagerank(G)
    
    # 2. Louvain (Comunidades)
    print("  -> Calculando Comunidades Louvain...")
    df_louvain, modularity = cugraph.louvain(G)
    print(f"     Modularity: {modularity:.4f}")
    
    # 3. Layout ForceAtlas2
    print("  -> Generando coordenadas 2D (ForceAtlas2)...")
    # max_iter=500 es adecuado para grafos de ~80k nodos en GPU
    df_layout = force_atlas2(G, max_iter=500, prevent_overlapping=False)
    
    # Combinar métricas
    df_metrics = df_layout.merge(df_pr, on='vertex', how='left')
    df_metrics = df_metrics.merge(df_louvain, on='vertex', how='left')
    df_metrics = df_metrics.rename(columns={'vertex': 'id', 'partition': 'community'})
    
    # Unir con metadatos de los nodos
    # Convertir id de df_nodes a string si no lo está
    df_nodes['id'] = df_nodes['id'].astype(str)
    df_metrics['id'] = df_metrics['id'].astype(str)
    
    df_final = df_nodes.merge(df_metrics, on='id', how='left')
    
    # Rellenar valores nulos para nodos aislados
    df_final['x'] = df_final['x'].fillna(0.0)
    df_final['y'] = df_final['y'].fillna(0.0)
    df_final['pagerank'] = df_final['pagerank'].fillna(0.0)
    df_final['community'] = df_final['community'].fillna(-1)
    
    out_path = os.path.join(OUTPUT_DIR, "coauthorship_results.parquet")
    df_final.to_parquet(out_path)
    print(f"  -> Guardados resultados en {out_path} ({len(df_final)} registros)")


def process_institutional():
    print("\n🚀 Procesando Red Institucional en GPU...")
    
    edges_path = os.path.join(OUTPUT_DIR, "institutional_edges.parquet")
    nodes_path = os.path.join(OUTPUT_DIR, "institutional_nodes.parquet")
    
    if not os.path.exists(edges_path) or not os.path.exists(nodes_path):
        print("❌ Error: Faltan archivos parquet de entrada para red institucional.")
        return
        
    df_edges = cudf.read_parquet(edges_path)
    df_nodes = cudf.read_parquet(nodes_path)
    
    print(f"  -> Cargados {len(df_nodes)} nodos y {len(df_edges)} aristas.")
    
    if len(df_edges) == 0:
        print("⚠️ No hay colaboraciones institucionales registradas.")
        return
        
    # Crear grafo
    G = cugraph.Graph()
    G.from_cudf_edgelist(
        df_edges, 
        source='source', 
        destination='target', 
        edge_attr='weight', 
        renumber=True
    )
    
    # 1. PageRank
    print("  -> Calculando PageRank...")
    df_pr = cugraph.pagerank(G)
    
    # 2. Louvain
    print("  -> Calculando Comunidades Louvain...")
    df_louvain, modularity = cugraph.louvain(G)
    
    # 3. Layout ForceAtlas2 (más iteraciones para asegurar convergencia en grafo pequeño)
    print("  -> Generando coordenadas 2D (ForceAtlas2)...")
    df_layout = force_atlas2(G, max_iter=800, prevent_overlapping=False)
    
    # Combinar métricas
    df_metrics = df_layout.merge(df_pr, on='vertex', how='left')
    df_metrics = df_metrics.merge(df_louvain, on='vertex', how='left')
    df_metrics = df_metrics.rename(columns={'vertex': 'id', 'partition': 'community'})
    
    df_nodes['id'] = df_nodes['id'].astype(str)
    df_metrics['id'] = df_metrics['id'].astype(str)
    
    df_final = df_nodes.merge(df_metrics, on='id', how='left')
    df_final['x'] = df_final['x'].fillna(0.0)
    df_final['y'] = df_final['y'].fillna(0.0)
    df_final['pagerank'] = df_final['pagerank'].fillna(0.0)
    df_final['community'] = df_final['community'].fillna(-1)
    
    out_path = os.path.join(OUTPUT_DIR, "institutional_results.parquet")
    df_final.to_parquet(out_path)
    print(f"  -> Guardados resultados en {out_path} ({len(df_final)} registros)")


def process_bipartite():
    print("\n🚀 Procesando Red Bipartita Autor-Concepto en GPU...")
    
    topic_edges_path = os.path.join(OUTPUT_DIR, "topic_edges.parquet")
    sdg_edges_path = os.path.join(OUTPUT_DIR, "sdg_edges.parquet")
    author_nodes_path = os.path.join(OUTPUT_DIR, "coauthorship_nodes.parquet")
    concept_nodes_path = os.path.join(OUTPUT_DIR, "concept_nodes.parquet")
    
    if not all(os.path.exists(p) for p in [topic_edges_path, sdg_edges_path, author_nodes_path, concept_nodes_path]):
        print("❌ Error: Faltan archivos parquet de entrada para red bipartita.")
        return
        
    df_topic_edges = cudf.read_parquet(topic_edges_path)
    df_sdg_edges = cudf.read_parquet(sdg_edges_path)
    df_author_nodes = cudf.read_parquet(author_nodes_path)
    df_concept_nodes = cudf.read_parquet(concept_nodes_path)
    
    # Combinar aristas
    df_edges = cudf.concat([df_topic_edges, df_sdg_edges], ignore_index=True)
    print(f"  -> Cargadas {len(df_edges)} aristas totales (Tópicos + ODS).")
    
    # Crear grafo bipartito
    G = cugraph.Graph()
    G.from_cudf_edgelist(
        df_edges, 
        source='source', 
        destination='target', 
        edge_attr='weight', 
        renumber=True
    )
    
    # 1. PageRank
    print("  -> Calculando PageRank...")
    df_pr = cugraph.pagerank(G)
    
    # 2. Louvain
    print("  -> Calculando Comunidades Louvain...")
    df_louvain, modularity = cugraph.louvain(G)
    
    # 3. HITS (Hubs y Authorities para Red Bipartita)
    print("  -> Calculando HITS...")
    # HITS espera store_transposed flag, pero cugraph lo maneja internamente con advertencia
    df_hits = cugraph.hits(G, max_iter=100)
    
    # 4. Layout ForceAtlas2
    print("  -> Generando coordenadas 2D (ForceAtlas2)...")
    df_layout = force_atlas2(G, max_iter=500, prevent_overlapping=False)
    
    # Combinar métricas
    df_metrics = df_layout.merge(df_pr, on='vertex', how='left')
    df_metrics = df_metrics.merge(df_louvain, on='vertex', how='left')
    df_metrics = df_metrics.merge(df_hits, on='vertex', how='left')
    df_metrics = df_metrics.rename(columns={'vertex': 'id', 'partition': 'community'})
    
    # Dividir y guardar los resultados por separado para Autores y Conceptos (facilita la visualización)
    df_metrics['id'] = df_metrics['id'].astype(str)
    df_author_nodes['id'] = df_author_nodes['id'].astype(str)
    df_concept_nodes['id'] = df_concept_nodes['id'].astype(str)
    
    # Autores
    df_auth_final = df_author_nodes.merge(df_metrics, on='id', how='left')
    df_auth_final['x'] = df_auth_final['x'].fillna(0.0)
    df_auth_final['y'] = df_auth_final['y'].fillna(0.0)
    df_auth_final['pagerank'] = df_auth_final['pagerank'].fillna(0.0)
    df_auth_final['community'] = df_auth_final['community'].fillna(-1)
    df_auth_final['hubs'] = df_auth_final['hubs'].fillna(0.0)
    df_auth_final['authorities'] = df_auth_final['authorities'].fillna(0.0)
    
    auth_out = os.path.join(OUTPUT_DIR, "bipartite_authors_results.parquet")
    df_auth_final.to_parquet(auth_out)
    print(f"  -> Guardados resultados de autores en {auth_out} ({len(df_auth_final)} registros)")
    
    # Conceptos
    df_concept_final = df_concept_nodes.merge(df_metrics, on='id', how='left')
    df_concept_final['x'] = df_concept_final['x'].fillna(0.0)
    df_concept_final['y'] = df_concept_final['y'].fillna(0.0)
    df_concept_final['pagerank'] = df_concept_final['pagerank'].fillna(0.0)
    df_concept_final['community'] = df_concept_final['community'].fillna(-1)
    df_concept_final['hubs'] = df_concept_final['hubs'].fillna(0.0)
    df_concept_final['authorities'] = df_concept_final['authorities'].fillna(0.0)
    
    concept_out = os.path.join(OUTPUT_DIR, "bipartite_concepts_results.parquet")
    df_concept_final.to_parquet(concept_out)
    print(f"  -> Guardados resultados de conceptos en {concept_out} ({len(df_concept_final)} registros)")


def main():
    process_coauthorship()
    print("-" * 50)
    process_institutional()
    print("-" * 50)
    process_bipartite()
    print("\n✅ Métricas de red computadas con éxito.")

if __name__ == "__main__":
    main()
