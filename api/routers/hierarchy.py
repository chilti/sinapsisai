"""
api/routers/hierarchy.py - Router para navegación y búsqueda en la jerarquía institucional
"""
from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict, Any, Optional
from api.db import get_cached_hierarchy, get_neo4j_store

router = APIRouter(prefix="/api/hierarchy", tags=["Jerarquía Institucional"])

@router.get("/institutions")
def list_institutions() -> Dict[str, Any]:
    """Retorna la lista de todas las instituciones registradas."""
    hierarchy = get_cached_hierarchy()
    institutions = sorted([k for k in hierarchy.keys() if k != "MÉXICO"])
    return {
        "total": len(institutions),
        "institutions": institutions,
        "default": "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)" if "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)" in institutions else (institutions[0] if institutions else "")
    }

@router.get("/dependencies")
def list_dependencies(institution: str = Query(..., description="Nombre oficial de la institución")) -> Dict[str, Any]:
    """Retorna las dependencias directas bajo una institución."""
    hierarchy = get_cached_hierarchy()
    dep_data = hierarchy.get(institution, {})
    deps = list(dep_data.keys()) if isinstance(dep_data, dict) else list(dep_data)
    deps_sorted = sorted([d for d in deps if d])
    return {
        "institution": institution,
        "total": len(deps_sorted),
        "dependencies": deps_sorted
    }

@router.get("/subdependencies")
def list_subdependencies(
    institution: str = Query(..., description="Nombre de la institución"),
    dependency: str = Query(..., description="Nombre de la dependencia")
) -> Dict[str, Any]:
    """Retorna las subdependencias o centros bajo una dependencia institucional."""
    hierarchy = get_cached_hierarchy()
    dep_data = hierarchy.get(institution, {})
    subs = []
    if isinstance(dep_data, dict):
        subs = dep_data.get(dependency, [])
    subs_sorted = sorted([s for s in subs if s])
    return {
        "institution": institution,
        "dependency": dependency,
        "total": len(subs_sorted),
        "subdependencies": subs_sorted
    }

@router.get("/search")
def search_entities(
    q: str = Query(..., min_length=2, description="Texto de búsqueda para autocompletado global"),
    limit: int = Query(10, ge=1, le=50)
) -> Dict[str, Any]:
    """Búsqueda global unificada en el Grafo de Conocimiento (Investigadores e Instituciones)."""
    try:
        neo = get_neo4j_store()
        results = neo.global_search(q, limit=limit)
        return {
            "query": q,
            "total": len(results),
            "results": results
        }
    except Exception as e:
        return {
            "query": q,
            "total": 0,
            "results": [],
            "error": str(e)
        }
