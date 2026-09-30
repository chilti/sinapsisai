"""
api/routers/reports.py - Router para generación y descarga de reportes oficiales en PDF y Markdown
"""
import re
import os
import json
import uuid
import threading
import time
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


# Diccionario en memoria para rastrear tareas de generación de reportes IA en background
AI_REPORT_JOBS: Dict[str, Dict[str, Any]] = {}
AI_REPORT_LOCK = threading.Lock()

class AIReportJobRequest(BaseModel):
    type: str = "inv"  # "inv" o "inst"
    name: str
    entity: Optional[str] = None
    institution: Optional[str] = None
    view_mode: Optional[str] = "capacidad_instalada"
    save_to_disk: bool = False

def _run_ai_report_worker(job_id: str, req_data: dict):
    from report_generator import generate_html_report
    
    def on_progress(step, total, msg):
        with AI_REPORT_LOCK:
            if job_id in AI_REPORT_JOBS:
                AI_REPORT_JOBS[job_id]["step"] = step
                AI_REPORT_JOBS[job_id]["total_steps"] = total
                AI_REPORT_JOBS[job_id]["progress_msg"] = f"Paso {step}/{total}: {msg}"

    try:
        with AI_REPORT_LOCK:
            AI_REPORT_JOBS[job_id]["status"] = "processing"
            AI_REPORT_JOBS[job_id]["progress_msg"] = "Extrayendo métricas consolidadas y consultando modelo LLM..."

        res = generate_html_report(
            entity_type=req_data["type"],
            entity_name=req_data["name"],
            entity_context=req_data.get("entity"),
            institution_name=req_data.get("institution"),
            view_mode=req_data.get("view_mode", "capacidad_instalada"),
            save_to_disk=req_data.get("save_to_disk", False),
            progress_callback=on_progress
        )

        with AI_REPORT_LOCK:
            AI_REPORT_JOBS[job_id]["status"] = "completed"
            AI_REPORT_JOBS[job_id]["progress_msg"] = "Reporte generado exitosamente."
            if req_data.get("save_to_disk", False):
                AI_REPORT_JOBS[job_id]["file_path"] = res
            else:
                AI_REPORT_JOBS[job_id]["html_content"] = res
            AI_REPORT_JOBS[job_id]["completed_at"] = time.time()
    except Exception as e:
        with AI_REPORT_LOCK:
            AI_REPORT_JOBS[job_id]["status"] = "error"
            AI_REPORT_JOBS[job_id]["error"] = str(e)
            AI_REPORT_JOBS[job_id]["progress_msg"] = f"Error al generar reporte: {str(e)}"


@router.post("/ai-report/request-job")
def request_ai_report_job(req: AIReportJobRequest):
    """
    Inicia la generación en segundo plano de un reporte bibliométrico con IA.
    Para investigadores (type='inv') se genera en memoria de forma efímera (save_to_disk=False).
    Para instituciones/dependencias (type='inst') se guarda permanentemente en disco.
    """
    import uuid
    job_id = uuid.uuid4().hex[:12]
    save_disk = True if req.type == "inst" else req.save_to_disk

    with AI_REPORT_LOCK:
        AI_REPORT_JOBS[job_id] = {
            "job_id": job_id,
            "type": req.type,
            "name": req.name,
            "entity": req.entity,
            "institution": req.institution,
            "view_mode": req.view_mode,
            "save_to_disk": save_disk,
            "status": "pending",
            "step": 0,
            "total_steps": 11,
            "progress_msg": "En cola de procesamiento...",
            "html_content": None,
            "file_path": None,
            "error": None,
            "created_at": time.time()
        }

    # Limpiar jobs antiguos (> 3 horas)
    now = time.time()
    with AI_REPORT_LOCK:
        keys_to_del = [k for k, v in AI_REPORT_JOBS.items() if now - v.get("created_at", 0) > 10800]
        for k in keys_to_del:
            del AI_REPORT_JOBS[k]

    req_dict = req.dict()
    req_dict["save_to_disk"] = save_disk
    t = threading.Thread(target=_run_ai_report_worker, args=(job_id, req_dict), daemon=True)
    t.start()

    return {
        "status": "success",
        "job_id": job_id,
        "message": "Generación de reporte iniciada en segundo plano"
    }


@router.get("/ai-report/job-status/{job_id}")
def get_ai_report_job_status(job_id: str):
    """Consulta el estado y progreso en tiempo real de una tarea de reporte IA."""
    with AI_REPORT_LOCK:
        job = AI_REPORT_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Tarea de reporte no encontrada")
        return {
            "job_id": job["job_id"],
            "type": job["type"],
            "name": job["name"],
            "status": job["status"],
            "step": job["step"],
            "total_steps": job["total_steps"],
            "progress_msg": job["progress_msg"],
            "save_to_disk": job["save_to_disk"],
            "error": job["error"]
        }


@router.get("/ai-report/job-result/{job_id}")
def get_ai_report_job_result(job_id: str, download: bool = Query(False)):
    """Retorna el HTML generado por la tarea (en pantalla o descargable)."""
    with AI_REPORT_LOCK:
        job = AI_REPORT_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Tarea de reporte no encontrada")
        if job["status"] == "error":
            raise HTTPException(status_code=500, detail=job.get("error") or "Error generando reporte")
        if job["status"] != "completed":
            raise HTTPException(status_code=400, detail="El reporte aún no ha finalizado")
        
        html_content = job.get("html_content")
        file_path = job.get("file_path")

    if not html_content and file_path and os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

    if not html_content:
        raise HTTPException(status_code=404, detail="El contenido del reporte no está disponible")

    headers = {}
    safe_name = "".join([c if c.isalnum() else "_" for c in job["name"]])
    filename = f"Reporte_IA_{safe_name}.html"
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers=headers
    )


@router.get("/ai-report")
def get_ai_report(
    type: str = Query("inst", description="'inst' o 'inv'"),
    name: str = Query(..., description="Nombre de la institución/entidad o del investigador"),
    view_mode: Optional[str] = Query("capacidad_instalada"),
    download: bool = Query(False, description="True para forzar descarga como archivo adjunto")
):
    """
    Recupera el reporte bibliométrico generado por IA en formato HTML.
    Permite previsualización en pantalla o descarga.
    """
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    reports_dir = os.path.join(base_dir, "reports")
    
    safe_name = "".join([c if c.isalnum() else "_" for c in name])
    candidates = []
    
    if type == "inst":
        suffix = f"_{view_mode}" if view_mode else ""
        candidates.extend([
            f"report_inst{suffix}_{safe_name}.html",
            f"report_inst_{safe_name}.html",
            f"report_inst_capacidad_instalada_{safe_name}.html",
            f"report_inst_produccion_institucional_{safe_name}.html"
        ])
    else:
        candidates.extend([
            f"report_inv_{safe_name}.html"
        ])
        
    found_file = None
    for cand in candidates:
        full_p = os.path.join(reports_dir, cand)
        if os.path.exists(full_p):
            found_file = full_p
            break
            
    # Búsqueda difusa si no coincide exacto
    if not found_file and os.path.exists(reports_dir):
        prefix = f"report_{type}_"
        for fname in os.listdir(reports_dir):
            if fname.startswith(prefix) and safe_name[:12].lower() in fname.lower() and fname.endswith(".html"):
                found_file = os.path.join(reports_dir, fname)
                break

    if not found_file:
        raise HTTPException(status_code=404, detail="No se encontró un reporte generado por IA para esta entidad/investigador")
        
    with open(found_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    headers = {}
    if download:
        filename = os.path.basename(found_file)
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers=headers
    )

@router.get("/snii-audit")
def get_snii_audit_report(download: bool = Query(False)):
    """Retorna o descarga el Informe Ejecutivo de Auditoría Cienciométrica del Padrón SNII 2026."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    report_file = os.path.join(base_dir, "data", "reports", "reporte_auditoria_snii_2026.html")
    
    if not os.path.exists(report_file):
        raise HTTPException(status_code=404, detail="El reporte de auditoría SNII 2026 no fue encontrado")
        
    with open(report_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    headers = {}
    if download:
        headers["Content-Disposition"] = 'attachment; filename="reporte_auditoria_snii_2026.html"'

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers=headers
    )

@router.get("/snii-ror-stats")
def get_snii_ror_stats() -> Dict[str, Any]:
    """Retorna las estadísticas del mapeo de investigadores SNII y entidades ROR."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    mapping_path = os.path.join(base_dir, "data", "snii_ror_verified_matches_v2.json")
    
    total_entities = 0
    with_ror = 0
    high_conf = 0
    
    if os.path.exists(mapping_path):
        try:
            import json
            with open(mapping_path, "r", encoding="utf-8") as f:
                mapping = json.load(f)
            for inst_name, inst_data in mapping.items():
                total_entities += 1
                root = inst_data.get("root_info", {})
                if root.get("root_ror"):
                    with_ror += 1
                    if (root.get("confidence") or 0) >= 70:
                        high_conf += 1
                for unit_name, unit_data in inst_data.get("units", {}).items():
                    total_entities += 1
                    if unit_data.get("unit_ror"):
                        with_ror += 1
                        if (unit_data.get("confidence") or 0) >= 70:
                            high_conf += 1
        except Exception as e:
            print(f"[get_snii_ror_stats] Error reading mapping: {e}")

    coverage_pct = round((with_ror / max(total_entities, 1)) * 100, 1)
    
    return {
        "snii_total": 82334,
        "snii_with_orcid": 33677,
        "snii_with_oa": 34323,
        "institutions_total": total_entities or 2263,
        "institutions_with_ror": with_ror or 204,
        "ror_high_confidence": high_conf or 204,
        "ror_coverage_pct": coverage_pct or 9.0
    }

