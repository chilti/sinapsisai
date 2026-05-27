import pandas as pd
import numpy as np
import hdbscan
import umap
import time
import json
import os
import sys
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

# Añadir la raíz del proyecto al sys.path para poder importar de 'lib'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# Stop words combinados (Inglés + Español básico)
spanish_stop_words = [
    "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o", "en", "de", "del", "al", "a", 
    "ante", "bajo", "cabe", "con", "contra", "desde", "durante", "entre", "hacia", "hasta", 
    "mediante", "para", "por", "según", "sin", "so", "sobre", "tras", "que", "es", "se", "su", 
    "sus", "como", "más", "pero", "este", "esta", "estos", "estas", "son", "fue", "lo", "ya", 
    "muy", "también", "nos", "sí", "qué", "cuando", "donde", "quien", "porque", "estudio", 
    "análisis", "efecto", "uso", "study", "analysis", "effect", "use", "based"
]
all_stops = list(ENGLISH_STOP_WORDS) + spanish_stop_words

def get_top_keywords(titles, n=3):
    if len(titles) == 0: return ""
    vectorizer = TfidfVectorizer(stop_words=all_stops, max_features=2000, ngram_range=(1, 2))
    try:
        X = vectorizer.fit_transform(titles)
        features = vectorizer.get_feature_names_out()
        
        # Sum TF-IDF scores for the cluster
        sums = X.sum(axis=0)
        words = [(features[col], sums[0, col]) for col in range(sums.shape[1])]
        
        # Filtrar n-gramas muy cortos
        words = [w for w in words if len(w[0]) > 3]
        words = sorted(words, key=lambda x: x[1], reverse=True)
        
        # Eliminar superposiciones de palabras (ej. no tener "machine" y "machine learning")
        final_words = []
        for w, score in words:
            if len(final_words) >= n: break
            # Checar si la palabra está contenida en otra ya elegida, o viceversa
            is_redundant = False
            for fw in final_words:
                if w in fw or fw in w:
                    is_redundant = True
                    break
            if not is_redundant:
                final_words.append(w)
                
        return " / ".join([w.title() for w in final_words])
    except Exception as e:
        print(f"Error tf-idf: {e}")
        return ""

def cluster_and_label(csv_path, parquet_path='data/maps/articles_vectors.parquet', out_json='public/tiles/articles_clusters.json', label_only=False):
    if '--force' not in sys.argv and os.path.exists(out_json):
        print(f"  -> {out_json} ya existe. Saltando clustering...")
        return

    print(f"Cargando {csv_path} para metadata 2D...")
    df = pd.read_csv(csv_path)
    
    print(f"Cargando {parquet_path} para extraer embeddings originales...")
    df_vectors = pd.read_parquet(parquet_path)
    vectors = np.stack(df_vectors['embedding'].values)
    
    if label_only and 'cluster' in df.columns:
        print("Reusando clústeres existentes en el CSV para re-etiquetado rápido...")
    else:
        print("Ejecutando UMAP para reducción de dimensionalidad latente (5D)...")
        start = time.time()
        reducer = umap.UMAP(
            n_components=5,
            n_neighbors=15,
            min_dist=0.0, # 0.0 para maximizar la densidad local y ayudar a HDBSCAN
            metric='cosine',
            random_state=42,
            n_jobs=-1
        )
        embeddings_5d = reducer.fit_transform(vectors)
        print(f"UMAP 5D completado en {time.time() - start:.1f} segundos.")
        
        print("Ejecutando HDBSCAN sobre el espacio 5D...")
        start = time.time()
        # Como UMAP a 5D agrupa muy bien, podemos reducir el min_cluster_size para encontrar sub-temas más específicos
        clusterer = hdbscan.HDBSCAN(min_cluster_size=300, min_samples=30, core_dist_n_jobs=-1)
        df['cluster'] = clusterer.fit_predict(embeddings_5d)
        print(f"HDBSCAN completado en {time.time() - start:.1f} segundos. {df['cluster'].nunique() - 1} clusters encontrados (más ruido).")
    
    print("Generando etiquetas semánticas híbridas (Centroides + TF-IDF + LLM)...")
    cluster_labels = {}
    cluster_centers = []
    
    # Intentar instanciar cliente LLM local
    client = None
    model_name = None
    try:
        from lib.llm_utils import get_openai_client, LLMConfig
        client = get_openai_client(async_mode=False)
        model_name = LLMConfig.get_model_name()
        print(f"  -> Conectado exitosamente al cliente LLM (modelo: {model_name})")
    except Exception as e:
        print(f"  -> ⚠️ No se pudo inicializar el cliente LLM. Se usará fallback de TF-IDF: {e}")
    
    for c in sorted(df['cluster'].unique()):
        if c == -1: 
            cluster_labels[c] = "Ruido"
            continue
            
        cluster_df = df[df['cluster'] == c]
        cluster_indices = cluster_df.index.tolist()
        titles = cluster_df['title'].dropna().astype(str).tolist()
        
        # 1. Obtener palabras clave TF-IDF del clúster (top 5 para el prompt)
        keywords_str = get_top_keywords(titles, n=5)
        
        # Fallback inicial usando TF-IDF clásico de 2 palabras
        label = get_top_keywords(titles, n=2)
        
        # 2. Calcular proximidad al centroide si hay cliente LLM y suficientes elementos
        if client is not None and len(cluster_indices) > 0:
            try:
                # Extraer embeddings del clúster
                vectors_C = vectors[cluster_indices]
                
                # Centroide geométrico
                centroid = np.mean(vectors_C, axis=0)
                
                # Evitar divisiones por cero en el cálculo de distancia coseno
                norms_C = np.linalg.norm(vectors_C, axis=1)
                centroid_norm = np.linalg.norm(centroid)
                
                if centroid_norm > 0:
                    sims = np.dot(vectors_C, centroid) / (norms_C * centroid_norm + 1e-9)
                    dists = 1.0 - sims
                    
                    # Top 10 títulos más representativos (más cercanos al centroide)
                    closest_local_indices = np.argsort(dists)[:10]
                    closest_global_indices = [cluster_indices[idx] for idx in closest_local_indices]
                    
                    representative_titles = df.loc[closest_global_indices, 'title'].dropna().tolist()
                    representative_bullet_points = "\n".join([f"- {t}" for t in representative_titles])
                    
                    # 3. Invocar al LLM local
                    prompt = f"""Analiza los siguientes títulos de artículos de investigación y palabras clave que pertenecen al mismo grupo temático (clúster).
Genera un título o etiqueta sumamente descriptivo, corto y conciso para este grupo.

Reglas obligatorias:
1. La etiqueta debe resumir el área temática común de forma clara.
2. Debe ser muy corta (máximo de 2 a 4 palabras).
3. Debe estar en ESPAÑOL (traduce los términos si es necesario para mantener coherencia).
4. Responde ÚNICAMENTE con la etiqueta generada, sin explicaciones, sin comillas, sin introducciones.

Palabras clave (TF-IDF):
{keywords_str}

Títulos representativos:
{representative_bullet_points}

Etiqueta del grupo:"""
                    
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": "Eres un asistente científico experto en organizar y etiquetar literatura académica mexicana."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.1,
                        max_tokens=256,
                        timeout=15.0
                    )
                    
                    llm_label = response.choices[0].message.content.strip()
                    llm_label = llm_label.replace('"', '').replace("'", "").strip()
                    if llm_label:
                        label = llm_label
            except Exception as ex:
                print(f"  -> Error al consultar LLM para clúster {c} (usando fallback TF-IDF): {ex}")
        
        cx = float(cluster_df['x'].median()) # Median es más robusto a outliers que mean
        cy = float(cluster_df['y'].median())
        
        cluster_labels[c] = label
        cluster_centers.append({
            'cluster_id': int(c),
            'label': label, 
            'x': cx, 
            'y': cy, 
            'size': len(cluster_df)
        })
        print(f"Cluster {c}: {label} ({len(cluster_df)} docs)")
        
    df['cluster_label'] = df['cluster'].map(cluster_labels)
    
    print("Guardando CSV actualizado...")
    df.to_csv(csv_path, index=False)
    
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(cluster_centers, f, ensure_ascii=False)
        
    print(f"Clusters exportados a {out_json}")
    print("Todo listo.")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Clasificar y etiquetar artículos.")
    parser.add_argument('--csv', default='data/maps/articles_umap.csv', help="Ruta al CSV de coordenadas UMAP")
    parser.add_argument('--parquet', default='data/maps/articles_vectors.parquet', help="Ruta al parquet de vectores originales")
    parser.add_argument('--out-json', default='public/tiles/articles_clusters.json', help="Ruta de destino del JSON de clusters")
    parser.add_argument('--label-only', action='store_true', help="Re-etiquetar usando clústeres existentes en el CSV sin volver a correr UMAP/HDBSCAN.")
    parser.add_argument('--force', action='store_true', help="Forzar la regeneración de clusters e ignorar cache")
    args = parser.parse_args()
    
    cluster_and_label(
        csv_path=args.csv,
        parquet_path=args.parquet,
        out_json=args.out_json,
        label_only=args.label_only
    )

