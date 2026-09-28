"""
api/routers/maps.py - Router para datos cartográficos y proyecciones WebGL (Nomic, SPECTER2)
"""
import os
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from typing import Dict, Any, List
from api.constants import TILES_DIR

router = APIRouter(prefix="/api/maps", tags=["Mapas de la Ciencia"])

@router.get("/spaces")
def get_embedding_spaces() -> Dict[str, Any]:
    """Retorna los espacios de embeddings y teselas disponibles."""
    return {
        "spaces": [
            {
                "id": "nomic",
                "name": "Nomic v1.5 (Multidisciplinario General)",
                "clusters_file": "articles_nomic_clusters.json",
                "data_file": "articles_nomic_data.json",
                "meta_file": "articles_nomic_meta.json"
            },
            {
                "id": "specter",
                "name": "SPECTER2 (Representación Científica Especializada)",
                "clusters_file": "articles_specter_clusters.json",
                "data_file": "articles_specter_data.json",
                "meta_file": "articles_specter_meta.json"
            },
            {
                "id": "preview",
                "name": "Vista Rápida / Muestreo Preliminar",
                "clusters_file": "articles_clusters.json",
                "data_file": "articles_data_preview.json",
                "meta_file": "articles_meta.json"
            }
        ],
        "default": "preview"
    }

@router.get("/clusters")
def get_clusters_metadata(space: str = Query("preview")) -> Dict[str, Any]:
    """Retorna los metadatos de clusters temáticos para la leyenda y filtros."""
    mapping = {
        "nomic": "articles_nomic_clusters.json",
        "specter": "articles_specter_clusters.json",
        "preview": "articles_clusters.json"
    }
    filename = mapping.get(space, "articles_clusters.json")
    file_path = TILES_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Archivo de clusters '{filename}' no encontrado")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            clusters_data = json.load(f)
        return {
            "status": "success",
            "space": space,
            "clusters": clusters_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo archivo de clusters: {e}")

@router.get("/data-file")
def get_data_file(space: str = Query("preview")):
    """Descarga o transmite el archivo de partículas JSON para renderizado en WebGL."""
    mapping = {
        "nomic": "articles_nomic_data.json",
        "specter": "articles_specter_data.json",
        "preview": "articles_data_preview.json"
    }
    filename = mapping.get(space, "articles_data_preview.json")
    file_path = TILES_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Archivo de partículas '{filename}' no encontrado")

    return FileResponse(file_path, media_type="application/json")
