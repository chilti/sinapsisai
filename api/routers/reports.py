"""
api/routers/reports.py - Router para generación y descarga de reportes oficiales en PDF y Markdown
"""
import re
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from lib.dossier_generator import (
    generate_dossier_data,
    generate_dossier_pdf,
    generate_dossier_markdown
)

router = APIRouter(prefix="/api/reports", tags=["Reportes & Dossiers"])

class DossierRequest(BaseModel):
    academic_name: str
    orcid: Optional[str] = None
    period_years: Optional[int] = None

@router.post("/dossier/data")
def get_dossier_preview(req: DossierRequest) -> Dict[str, Any]:
    """Computa los datos estructurados del dossier para previsualización."""
    data = generate_dossier_data(
        academic_name=req.academic_name,
        orcid=req.orcid
    )
    if not data or not (data.get("catalog") or data.get("works")):
        raise HTTPException(status_code=404, detail="No se encontraron obras para generar el reporte")
    return {"status": "success", "data": data}

@router.post("/dossier/markdown")
def download_dossier_markdown(req: DossierRequest):
    """Genera y descarga el reporte en formato Markdown estructurado."""
    data = generate_dossier_data(
        academic_name=req.academic_name,
        orcid=req.orcid
    )
    if not data or not (data.get("catalog") or data.get("works")):
        raise HTTPException(status_code=404, detail="No se encontraron obras para generar el reporte")

    md_text = generate_dossier_markdown(data)
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', req.academic_name)
    filename = f"Reporte_Trayectoria_{clean_name}.md"

    return Response(
        content=md_text.encode("utf-8"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

@router.post("/dossier/pdf")
def download_dossier_pdf(req: DossierRequest):
    """Genera y descarga el informe oficial en formato PDF de alta calidad con WeasyPrint."""
    data = generate_dossier_data(
        academic_name=req.academic_name,
        orcid=req.orcid
    )
    if not data or not (data.get("catalog") or data.get("works")):
        raise HTTPException(status_code=404, detail="No se encontraron obras para generar el reporte")

    pdf_bytes = generate_dossier_pdf(data)
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', req.academic_name)
    filename = f"Reporte_Trayectoria_{clean_name}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
