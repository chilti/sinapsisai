"""
api/routers/citations.py - Router para el explorador Zero-Join de Citas y Autocitas
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, Optional
from lib.citations_explorer import get_citing_works_analysis, get_author_work_and_openalex_ids, get_citing_works_data

router = APIRouter(prefix="/api/citations", tags=["Citaciones & Autocitas"])

@router.get("/summary")
def get_citations_summary(
    name: Optional[str] = Query(None, description="Nombre completo del investigador"),
    orcid: Optional[str] = Query(None, description="ORCID iD"),
    limit: int = Query(500, ge=1, le=1000)
) -> Dict[str, Any]:
    """
    Retorna el resumen analítico Zero-Join de citas del investigador:
    total de citas, citas netas de terceros, tasa de autocitas directas,
    obras en top 10% y distribuciones por países e instituciones citantes.
    """
    if not name and not orcid:
        raise HTTPException(status_code=400, detail="Debe especificar 'name' o 'orcid'")

    summary = get_citing_works_analysis(academic_name=name, orcid=orcid, limit=limit)
    
    # Asegurar serialización JSON pura eliminando o convirtiendo DataFrames de pandas
    if "citing_works_df" in summary:
        df = summary.pop("citing_works_df")
        summary["citing_works"] = df.to_dict(orient="records") if hasattr(df, "to_dict") else []

    return {
        "status": "success",
        "academic_name": name or "",
        "orcid": orcid or "",
        "data": summary
    }

@router.get("/citing-works")
def get_citing_works(
    name: Optional[str] = Query(None),
    orcid: Optional[str] = Query(None),
    limit: int = Query(250, ge=1, le=1000)
) -> Dict[str, Any]:
    """Retorna la lista detallada de artículos citantes con detección de autocita y coautores."""
    if not name and not orcid:
        raise HTTPException(status_code=400, detail="Debe especificar 'name' o 'orcid'")

    wids, author_oa_ids = get_author_work_and_openalex_ids(name, orcid)
    if not wids:
        return {"total": 0, "citing_works": []}

    raw_data = get_citing_works_data(
        wids,
        author_name=name or "",
        author_openalex_ids=author_oa_ids,
        limit=limit
    )
    
    # Extraer lista de obras citantes serializable
    df = raw_data.get("citing_works_df")
    citing_works = df.to_dict(orient="records") if hasattr(df, "to_dict") else raw_data.get("top_citing_works", [])

    return {
        "total": len(citing_works),
        "limit": limit,
        "citing_works": citing_works
    }
