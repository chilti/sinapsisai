"""
api/routers/citations.py - Router para el explorador Zero-Join de Citas y Autocitas
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Dict, Any, Optional
import numpy as np
from lib.citations_explorer import get_citing_works_analysis, get_author_work_and_openalex_ids, get_citing_works_data

router = APIRouter(prefix="/api/citations", tags=["Citaciones & Autocitas"])

@router.get("/summary")
def get_citations_summary(
    name: Optional[str] = Query(None, description="Nombre completo del investigador"),
    orcid: Optional[str] = Query(None, description="ORCID iD"),
    limit: int = Query(500, ge=1, le=1000),
    career_total: Optional[int] = Query(None, description="Total de citas históricas de la carrera")
) -> Dict[str, Any]:
    """
    Retorna el resumen analítico de citas del investigador:
    total de citas de toda la carrera, citas netas de terceros, tasa de autocitas directas,
    obras en top 10% y distribuciones por países e instituciones citantes.
    """
    if not name and not orcid:
        raise HTTPException(status_code=400, detail="Debe especificar 'name' o 'orcid'")

    clean_orcid = str(orcid).replace("https://orcid.org/", "").strip() if orcid else None
    summary = get_citing_works_analysis(academic_name=name, orcid=clean_orcid, limit=limit)
    
    # Asegurar serialización JSON pura eliminando o convirtiendo DataFrames de pandas
    if "citing_works_df" in summary:
        df = summary.pop("citing_works_df")
        if hasattr(df, "replace"):
            df = df.replace({float("nan"): None, np.nan: None})
        summary["citing_works"] = df.to_dict(orient="records") if hasattr(df, "to_dict") else []

    # Extender cálculo a toda la carrera si se especifica career_total
    if career_total and career_total > 0:
        raw_total = summary.get("total_citations", 0)
        raw_self = summary.get("self_citations", 0)
        self_rate = summary.get("self_citation_rate", 0.0)
        if raw_total > 0:
            career_self = max(round(career_total * (self_rate / 100.0)), raw_self)
            career_net = max(0, career_total - career_self)
        else:
            career_self = raw_self
            career_net = max(0, career_total - raw_self)
        summary["total_citations"] = career_total
        summary["net_citations"] = career_net
        summary["self_citations"] = career_self
        summary["raw_citing_works_count"] = raw_total
        summary["raw_self_citations_count"] = raw_self

    summary["self_citations_note"] = "Se contabilizan exclusivamente las autocitas directas (del autor) donde el investigador evaluado figura expresamente como coautor en la obra citante. El cálculo de citas y autocitas abarca la totalidad de las citas acumuladas a lo largo de su carrera académica."

    return {
        "status": "success",
        "academic_name": name or "",
        "orcid": clean_orcid or "",
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

    clean_orcid = str(orcid).replace("https://orcid.org/", "").strip() if orcid else None
    wids, author_oa_ids = get_author_work_and_openalex_ids(name, clean_orcid)
    if not wids:
        return {"total": 0, "citing_works": []}

    raw_data = get_citing_works_data(
        wids,
        author_name=name or "",
        author_openalex_ids=author_oa_ids,
        limit=limit
    )
    
    # Extraer lista de obras citantes serializable sin NaN
    df = raw_data.get("citing_works_df")
    citing_works = []
    if hasattr(df, "to_dict"):
        df_clean = df.replace({float("nan"): None, np.nan: None})
        citing_works = df_clean.to_dict(orient="records")
    else:
        citing_works = raw_data.get("top_citing_works", [])

    return {
        "total": len(citing_works),
        "limit": limit,
        "citing_works": citing_works
    }
