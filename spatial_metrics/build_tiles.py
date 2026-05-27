import os
import sys
import pandas as pd
import numpy as np
import time
import subprocess
import shutil
try:
    import umap
except ImportError:
    print("⚠️ Faltan dependencias. Por favor instala: pip install umap-learn")
    sys.exit(1)

INPUT_DIR = "data/maps"
OUTPUT_DIR = "public/tiles"

def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def rotate_backup(filepath, max_backups=3):
    if not os.path.exists(filepath):
        return
    print(f"  -> Respaldando {filepath}...")
    for i in range(max_backups - 1, 0, -1):
        src = f"{filepath}.{i}"
        dst = f"{filepath}.{i+1}"
        if os.path.exists(src):
            shutil.move(src, dst)
    shutil.move(filepath, f"{filepath}.1")

def run_umap(df, vector_col='embedding', n_neighbors=15, min_dist=0.1, metric='cosine', spread=1.0):
    """
    Ejecuta UMAP sobre una columna de vectores en un DataFrame y devuelve x e y.
    """
    print(f"  -> Ejecutando UMAP ({len(df)} puntos)... esto puede tardar un momento.")
    vectors = np.stack(df[vector_col].values)
    
    
    # Configuramos UMAP
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=min_dist,
        spread=spread,
        metric=metric,
        random_state=42, # Para reproducibilidad
        n_jobs=-1        # Usar todos los cores disponibles
    )
    
    start_time = time.time()
    embedding_2d = reducer.fit_transform(vectors)
    print(f"  -> UMAP completado en {time.time() - start_time:.1f} segundos.")
    
    # Jitter post-UMAP: Aplicamos el ruido a las coordenadas 2D finales. 
    # Así preservamos la topología general pero expandimos los "agujeros negros".
    np.random.seed(42)
    jitter = np.random.normal(0, 0.1, embedding_2d.shape)
    embedding_2d = embedding_2d + jitter
    
    return embedding_2d[:, 0], embedding_2d[:, 1]

def run_quadfeather(input_csv, output_dir):
    """
    Llama a la CLI de quadfeather para procesar el CSV generado y convertirlo en baldosas.
    """
    print(f"  -> Ejecutando Quadfeather para {input_csv} -> {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    
    # Limpiar carpeta temporal de quadfeather si existe
    tmp_dir = os.path.join(os.path.dirname(input_csv), "_deepscatter_tmp")
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
        
    # quadfeather requiere que el archivo de entrada contenga 'x' e 'y'.
    # Comando CLI: quadfeather --files input.csv --out output_dir
    cmd = [
        "quadfeather",
        "--files", input_csv,
        "--destination", output_dir
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print(f"  -> ✅ Quadfeather completado. Baldosas en {output_dir}")
    except subprocess.CalledProcessError as e:
        print(f"  -> ❌ Error ejecutando Quadfeather: {e}")
    except FileNotFoundError:
        print("  -> ❌ Error: 'quadfeather' no está instalado o no está en el PATH. (pip install quadfeather)")

def process_people_map():
    print("\n🗺️ Procesando Mapa de Personas (FastRP)...")
    input_file = os.path.join(INPUT_DIR, "people_vectors.parquet")
    if not os.path.exists(input_file):
        print("  -> Archivo no encontrado. Ejecuta extract_vectors.py primero.")
        return
        
    csv_path = os.path.join(INPUT_DIR, "people_umap.csv")
    
    if not os.path.exists(csv_path):
        df = pd.read_parquet(input_file)
        if df.empty: return
        df['x'], df['y'] = run_umap(df, vector_col='embedding', metric='cosine')
        df_clean = df.drop(columns=['embedding'])
        df_clean.to_csv(csv_path, index=False)
    else:
        print(f"  -> {csv_path} ya existe. Saltando UMAP...")
        
    # NOTA: Ya no usamos quadfeather, usamos JSON.

def process_people_topics_map():
    print("\n🗺️ Procesando Mapa de Personas (FastRP con Temas y ODS)...")
    input_file = os.path.join(INPUT_DIR, "people_topics_vectors.parquet")
    if not os.path.exists(input_file):
        print("  -> Archivo no encontrado. Ejecuta extract_vectors.py primero.")
        return
        
    csv_path = os.path.join(INPUT_DIR, "people_topics_umap.csv")
    
    if not os.path.exists(csv_path):
        df = pd.read_parquet(input_file)
        if df.empty: return
        df['x'], df['y'] = run_umap(df, vector_col='embedding', metric='cosine')
        df_clean = df.drop(columns=['embedding'])
        df_clean.to_csv(csv_path, index=False)
    else:
        print(f"  -> {csv_path} ya existe. Saltando UMAP...")
        
    # NOTA: No llamamos a quadfeather porque este nuevo mapa usa el pipeline JSON.

def process_articles_map():
    print("\n🗺️ Procesando Mapa de Artículos (Nomic)...")
    input_file = os.path.join(INPUT_DIR, "articles_vectors.parquet")
    if not os.path.exists(input_file):
        print("  -> Archivo no encontrado. Ejecuta extract_vectors.py primero.")
        return
        
    csv_path = os.path.join(INPUT_DIR, "articles_umap.csv")
    
    force = '--force' in sys.argv
    if force and os.path.exists(csv_path):
        rotate_backup(csv_path)
        
    if not os.path.exists(csv_path):
        df = pd.read_parquet(input_file)
        # Ajustamos min_dist y spread para separar más los clústeres entre sí
        df['x'], df['y'] = run_umap(df, vector_col='embedding', metric='cosine', n_neighbors=15, min_dist=0.5, spread=1.5)
        df_clean = df.drop(columns=['embedding'])
        df_clean.to_csv(csv_path, index=False)
    else:
        print(f"  -> {csv_path} ya existe. Usa --force para regenerar y respaldar. Saltando UMAP...")
    
    # NOTA: Ya no usamos quadfeather, usamos JSON.

def process_performance_maps():
    print("\n🗺️ Procesando Mapas de Desempeño Institucional (4D)...")
    input_file = os.path.join(INPUT_DIR, "performance_vectors.parquet")
    if not os.path.exists(input_file):
        print("  -> Archivo no encontrado. Ejecuta extract_vectors.py primero.")
        return
        
    csv_path = os.path.join(INPUT_DIR, "performance_umap.csv")
    
    if not os.path.exists(csv_path):
        df = pd.read_parquet(input_file)
        if df.empty: return
        df['x'], df['y'] = run_umap(df, vector_col='embedding', metric='euclidean')
        df_clean = df.drop(columns=['embedding'])
        df_clean.to_csv(csv_path, index=False)
    else:
        print(f"  -> {csv_path} ya existe. Saltando UMAP...")


def process_articles_nomic_map():
    print("\n🗺️ Procesando Mapa de Artículos (Nomic desde ClickHouse)...")
    input_file = os.path.join(INPUT_DIR, "articles_nomic_vectors.parquet")
    if not os.path.exists(input_file):
        print("  -> Archivo no encontrado. Ejecuta extract_vectors.py primero.")
        return
        
    csv_path = os.path.join(INPUT_DIR, "articles_nomic_umap.csv")
    
    force = '--force' in sys.argv
    if force and os.path.exists(csv_path):
        rotate_backup(csv_path)
        
    if not os.path.exists(csv_path):
        df = pd.read_parquet(input_file)
        if df.empty: return
        df['x'], df['y'] = run_umap(df, vector_col='embedding', metric='cosine', n_neighbors=15, min_dist=0.5, spread=1.5)
        df_clean = df.drop(columns=['embedding'])
        df_clean.to_csv(csv_path, index=False)
    else:
        print(f"  -> {csv_path} ya existe. Saltando UMAP...")


def process_articles_specter_map():
    print("\n🗺️ Procesando Mapa de Artículos (SPECTER2 desde ClickHouse)...")
    input_file = os.path.join(INPUT_DIR, "articles_specter_vectors.parquet")
    if not os.path.exists(input_file):
        print("  -> Archivo no encontrado. Ejecuta extract_vectors.py primero.")
        return
        
    csv_path = os.path.join(INPUT_DIR, "articles_specter_umap.csv")
    
    force = '--force' in sys.argv
    if force and os.path.exists(csv_path):
        rotate_backup(csv_path)
        
    if not os.path.exists(csv_path):
        df = pd.read_parquet(input_file)
        if df.empty: return
        df['x'], df['y'] = run_umap(df, vector_col='embedding', metric='cosine', n_neighbors=15, min_dist=0.5, spread=1.5)
        df_clean = df.drop(columns=['embedding'])
        df_clean.to_csv(csv_path, index=False)
    else:
        print(f"  -> {csv_path} ya existe. Saltando UMAP...")


def process_people_semantic_map():
    print("\n🗺️ Procesando Mapa de Académicos (Semántica SPECTER2 desde ClickHouse)...")
    input_file = os.path.join(INPUT_DIR, "people_semantic_vectors.parquet")
    if not os.path.exists(input_file):
        print("  -> Archivo no encontrado. Ejecuta extract_vectors.py primero.")
        return
        
    csv_path = os.path.join(INPUT_DIR, "people_semantic_umap.csv")
    
    force = '--force' in sys.argv
    if force and os.path.exists(csv_path):
        rotate_backup(csv_path)
        
    if not os.path.exists(csv_path):
        df = pd.read_parquet(input_file)
        if df.empty: return
        df['x'], df['y'] = run_umap(df, vector_col='embedding', metric='cosine', n_neighbors=15, min_dist=0.1, spread=1.0)
        df_clean = df.drop(columns=['embedding'])
        df_clean.to_csv(csv_path, index=False)
    else:
        print(f"  -> {csv_path} ya existe. Saltando UMAP...")


if __name__ == "__main__":
    ensure_dirs()
    print("=== Iniciando Construcción de Tiles (UMAP) ===")
    
    process_people_map()
    process_people_topics_map()
    process_articles_map()
    process_performance_maps()
    
    # Nuevos mapas
    process_articles_nomic_map()
    process_articles_specter_map()
    process_people_semantic_map()
    
    print("\n=== Proceso completado ===")

