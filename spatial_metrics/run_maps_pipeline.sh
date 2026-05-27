#!/bin/bash
set -e

echo "========================================="
echo "🚀 Iniciando Pipeline de Mapas Espaciales"
echo "========================================="

# Asegurarse de estar en el directorio correcto
cd "$(dirname "$0")/.."

echo ""
echo "Paso 1: Extrayendo Vectores (Neo4j, Qdrant, ClickHouse)..."
/home/ambientesPy/revistaslatam/bin/python3 spatial_metrics/extract_vectors.py "$@"

echo ""
echo "Paso 2: Construyendo Tiles (UMAP 2D)..."
/home/ambientesPy/revistaslatam/bin/python3 spatial_metrics/build_tiles.py "$@"

echo ""
echo "Paso 3: Generando datos JSON para el visualizador WebGL..."
/home/ambientesPy/revistaslatam/bin/python3 spatial_metrics/build_map_data.py "$@"

echo ""
echo "Paso 4: Clustering semántico y etiquetado de nivel 1 (HDBSCAN + LLM)..."
# 4.1. Nomic Articles
if [ -f "data/maps/articles_nomic_umap.csv" ]; then
    echo "  -> Agrupando artículos Nomic..."
    /home/ambientesPy/revistaslatam/bin/python3 spatial_metrics/cluster_articles.py \
        --csv data/maps/articles_nomic_umap.csv \
        --parquet data/maps/articles_nomic_vectors.parquet \
        --out-json public/tiles/articles_nomic_clusters.json "$@"
    cp public/tiles/articles_nomic_clusters.json public/tiles/articles_clusters.json
fi
# 4.2. SPECTER2 Articles
if [ -f "data/maps/articles_specter_umap.csv" ]; then
    echo "  -> Agrupando artículos SPECTER2..."
    /home/ambientesPy/revistaslatam/bin/python3 spatial_metrics/cluster_articles.py \
        --csv data/maps/articles_specter_umap.csv \
        --parquet data/maps/articles_specter_vectors.parquet \
        --out-json public/tiles/articles_specter_clusters.json "$@"
fi

echo ""
echo "Paso 5: Generando sub-etiquetas de nivel 2 (KMeans + centroide + LLM)..."
# 5.1. Nomic Articles
if [ -f "public/tiles/articles_nomic_clusters.json" ]; then
    echo "  -> Generando sub-etiquetas artículos Nomic..."
    /home/ambientesPy/revistaslatam/bin/python3 spatial_metrics/generate_sublabels.py \
        --csv data/maps/articles_nomic_umap.csv \
        --vectors data/maps/articles_nomic_vectors.parquet \
        --json public/tiles/articles_nomic_clusters.json \
        --min-size 1200 \
        --n-sub 4 "$@"
    cp public/tiles/articles_nomic_clusters.json public/tiles/articles_clusters.json
fi
# 5.2. SPECTER2 Articles
if [ -f "public/tiles/articles_specter_clusters.json" ]; then
    echo "  -> Generando sub-etiquetas artículos SPECTER2..."
    /home/ambientesPy/revistaslatam/bin/python3 spatial_metrics/generate_sublabels.py \
        --csv data/maps/articles_specter_umap.csv \
        --vectors data/maps/articles_specter_vectors.parquet \
        --json public/tiles/articles_specter_clusters.json \
        --min-size 1200 \
        --n-sub 4 "$@"
fi

echo ""
echo "========================================="
echo "✅ Pipeline completado exitosamente."
echo "========================================="

