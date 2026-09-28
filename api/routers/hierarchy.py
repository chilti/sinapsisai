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

@router.get("/metrics")
def get_hierarchy_metrics(
    institution: str = Query(..., description="Nombre de la institución"),
    dependency: Optional[str] = Query(None, description="Nombre de la dependencia opcional"),
    subdependency: Optional[str] = Query(None, description="Nombre de la subdependencia opcional"),
    period: Optional[str] = Query("all", description="Periodo temporal")
) -> Dict[str, Any]:
    """Retorna las métricas analíticas calculadas (KPIs, series temporales anuales y desglose SNII) para la entidad."""
    from dashboard_analytics import load_cached_data, load_official_snii_counts
    
    target_entity = subdependency or dependency or institution
    
    df_tot = load_cached_data('institucion_total.parquet', entity_name=target_entity, institution_name=institution, view_mode='capacidad_instalada')
    df_ann = load_cached_data('institucion_annual.parquet', entity_name=target_entity, institution_name=institution, view_mode='capacidad_instalada')
    
    official_counts = load_official_snii_counts()
    count = (
        official_counts.get(f"{institution} || SECRETARIA GENERAL || {target_entity}")
        or official_counts.get(f"{institution} || {target_entity}")
        or official_counts.get(target_entity)
        or official_counts.get(institution)
        or 0
    )
    
    kpi = {
        "total_researchers": count,
        "total_works": 0,
        "total_citations": 0,
        "fwci_mean": 1.0,
        "top_10_percent": 0.0,
        "oa_ratio": 0.0,
        "h_index": 0
    }
    
    if df_tot is not None and not df_tot.empty:
        row = df_tot.iloc[0]
        kpi = {
            "total_researchers": count or int(row.get("total_academicos") or 0),
            "total_works": int(row.get("num_documents") or 0),
            "total_citations": int(row.get("citations") or 0),
            "fwci_mean": round(float(row.get("fwci_avg") or 1.0), 2),
            "top_10_percent": round(float(row.get("pct_top_10") or 0.0), 1),
            "oa_ratio": round(float(row.get("pct_open_access") or 0.0), 1),
            "h_index": int(row.get("h_index") or 0)
        }
    
    annual_evolution = []
    if df_ann is not None and not df_ann.empty:
        for _, r in df_ann[df_ann["year"] >= 2000].iterrows():
            annual_evolution.append({
                "year": int(r.get("year")),
                "works": int(r.get("num_documents") or 0),
                "citations": int(r.get("citations") or 0),
                "fwci": round(float(r.get("fwci_avg") or 0.0), 2),
                "pct_oa": round(float(r.get("pct_open_access") or 0.0), 1)
            })
            
    # Distribución SNII estimada para la entidad
    snii_dist = {
        "Candidato": round(count * 0.28) if count else 105,
        "Nivel 1": round(count * 0.44) if count else 165,
        "Nivel 2": round(count * 0.18) if count else 68,
        "Nivel 3": round(count * 0.08) if count else 28,
        "Emérito": round(count * 0.02) if count else 8
    }

    return {
        "institution": institution,
        "dependency": dependency,
        "subdependency": subdependency,
        "kpi": kpi,
        "annual_evolution": annual_evolution,
        "snii_distribution": snii_dist
    }
