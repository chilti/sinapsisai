"""
api/routers/auth_curation.py - Router para autenticación ORCID, acreditaciones y curación
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from api.db import get_curation
from lib.auth import exchange_code_for_token, get_orcid_login_url

router = APIRouter(prefix="/api/auth", tags=["Autenticación & Curación"])

class TokenExchangeRequest(BaseModel):
    code: str
    redirect_uri: Optional[str] = None

class AccreditationRequest(BaseModel):
    user_orcid: str
    user_name: str
    institution_name: str
    institutional_email: str
    position: str
    notes: Optional[str] = ""

class ApprovalRequest(BaseModel):
    request_id: Optional[int] = None
    user_orcid: Optional[str] = None
    approver_orcid: Optional[str] = "super_admin"
    reason: Optional[str] = ""

class AliasRequest(BaseModel):
    canonical_entity: str
    alias: str
    created_by: Optional[str] = "admin"

class BibtexImportRequest(BaseModel):
    user_orcid: str
    bibtex_content: str

class PipelineRunRequest(BaseModel):
    action: str
    academic_filter: Optional[str] = None
    institution_filter: Optional[str] = None
    use_local_llm: Optional[bool] = True
    sync_ch: Optional[bool] = False
    sync_phase: Optional[str] = "all"

class WorkCurationRequest(BaseModel):
    user_orcid: str
    work_id: str
    work_title: Optional[str] = ""
    reason: Optional[str] = ""

@router.get("/orcid/login-url")
def get_login_url(redirect_uri: Optional[str] = None) -> Dict[str, Any]:
    """Genera la URL de autorización OAuth de ORCID."""
    url = get_orcid_login_url(redirect_uri=redirect_uri)
    return {"login_url": url, "redirect_uri": redirect_uri}

@router.post("/orcid/token")
def exchange_orcid_token(req: TokenExchangeRequest) -> Dict[str, Any]:
    """Intercambia el código OAuth de ORCID por los datos de perfil del usuario."""
    token_data = exchange_code_for_token(req.code, redirect_uri=req.redirect_uri)
    if not token_data or "orcid" not in token_data:
        raise HTTPException(status_code=400, detail="Error intercambiando el código de autorización de ORCID")

    orcid = token_data.get("orcid")
    name = token_data.get("name", "")
    
    curation = get_curation()
    user_role_info = curation.get_user_roles(orcid) if hasattr(curation, "get_user_roles") else {}
    is_super = user_role_info.get("role") == "super_admin"
    is_inst = curation.is_user_institutional_admin(orcid) if hasattr(curation, "is_user_institutional_admin") else False
    user_role = "super_admin" if is_super else ("admin_institucional" if is_inst else "investigador")

    return {
        "status": "success",
        "orcid": orcid,
        "name": name,
        "role": user_role,
        "is_admin": is_super or is_inst,
        "access_token": token_data.get("access_token"),
        "scope": token_data.get("scope")
    }

# --- Curación y Acreditación ---

@router.post("/accreditation/request")
def submit_accreditation_request(req: AccreditationRequest) -> Dict[str, Any]:
    """Registra una solicitud de acreditación institucional (restringida a nivel jerárquico mínimo)."""
    curation = get_curation()
    ok, msg = curation.request_accreditation(
        user_orcid=req.user_orcid,
        user_name=req.user_name,
        institution_name=req.institution_name,
        institutional_email=req.institutional_email,
        position=req.position,
        notes=req.notes or ""
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": msg}

@router.get("/accreditation/requests")
def list_accreditation_requests(status: str = Query("pending")) -> Dict[str, Any]:
    """Lista las solicitudes de acreditación institucional (para administradores)."""
    curation = get_curation()
    requests = curation.list_pending_accreditations()
    return {
        "status": "success",
        "total": len(requests),
        "requests": requests
    }

@router.get("/accreditation/admins")
def list_active_admins() -> Dict[str, Any]:
    """Lista todos los administradores institucionales activos."""
    curation = get_curation()
    admins = curation.list_active_institutional_admins()
    return {
        "status": "success",
        "total": len(admins),
        "admins": admins
    }

@router.post("/accreditation/approve")
def approve_accreditation(req: ApprovalRequest) -> Dict[str, Any]:
    """Aprueba una solicitud de acreditación institucional."""
    curation = get_curation()
    target_orcid = req.user_orcid or req.approver_orcid
    ok = curation.decide_accreditation(user_orcid=target_orcid, decision="APPROVE", decided_by=req.approver_orcid or "super_admin")
    if not ok:
        raise HTTPException(status_code=400, detail="No se pudo aprobar la acreditación")
    return {"status": "success", "message": f"Acreditación aprobada exitosamente para {target_orcid}"}

@router.post("/accreditation/reject")
def reject_accreditation(req: ApprovalRequest) -> Dict[str, Any]:
    """Rechaza una solicitud de acreditación institucional."""
    curation = get_curation()
    target_orcid = req.user_orcid or req.approver_orcid
    ok = curation.decide_accreditation(user_orcid=target_orcid, decision="REJECT", decided_by=req.approver_orcid or "super_admin")
    if not ok:
        raise HTTPException(status_code=400, detail="No se pudo rechazar la acreditación")
    return {"status": "success", "message": f"Acreditación rechazada para {target_orcid}"}

@router.post("/accreditation/revoke")
def revoke_accreditation(req: ApprovalRequest) -> Dict[str, Any]:
    """Revoca permisos de administrador institucional a un usuario."""
    curation = get_curation()
    target_orcid = req.user_orcid or ""
    ok = curation.decide_accreditation(user_orcid=target_orcid, decision="REJECT", decided_by=req.approver_orcid or "super_admin")
    return {"status": "success", "message": f"Permisos revocados para {target_orcid}"}

# --- Alias Institucionales ---

@router.get("/institutions/aliases")
def list_institutional_aliases(institution: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Retorna los alias registrados para una institución o el catálogo completo."""
    curation = get_curation()
    aliases = curation.get_institutional_aliases(institution)
    return {
        "status": "success",
        "total": len(aliases),
        "aliases": aliases
    }

@router.post("/institutions/aliases")
def create_institutional_alias(req: AliasRequest) -> Dict[str, Any]:
    """Registra una nueva variante o alias para una institución."""
    curation = get_curation()
    ok = curation.add_institutional_alias(
        institution_name=req.canonical_entity,
        alias=req.alias,
        created_by=req.created_by or "admin"
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Error registrando alias institucional")
    return {"status": "success", "message": "Alias registrado correctamente"}

# --- Obras, Curación y BibTeX ---

@router.post("/works/disclaim")
def disclaim_work(req: WorkCurationRequest) -> Dict[str, Any]:
    """Desvincula un artículo del perfil del investigador (mover a lista de exclusión)."""
    curation = get_curation()
    ok = curation.disclaim_work(req.user_orcid, req.work_id, req.work_title or "", req.reason or "")
    if not ok:
        raise HTTPException(status_code=400, detail="Error al desvincular el trabajo")
    return {"status": "success", "message": "Trabajo desvinculado"}

@router.post("/works/restore")
def restore_work(req: WorkCurationRequest) -> Dict[str, Any]:
    """Restaura un artículo previamente desvinculado hacia el perfil activo."""
    curation = get_curation()
    ok = curation.claim_work(req.user_orcid, req.work_id, req.work_title or "")
    if not ok:
        raise HTTPException(status_code=400, detail="Error al restaurar el trabajo")
    return {"status": "success", "message": "Trabajo restaurado"}

@router.get("/works/excluded")
def get_excluded_works(orcid: str = Query(...)) -> Dict[str, Any]:
    """Retorna la lista de obras desvinculadas por el usuario."""
    curation = get_curation()
    excluded = curation.list_disclaimed_works(orcid)
    return {
        "status": "success",
        "total": len(excluded),
        "excluded_works": excluded
    }

@router.get("/works/custom")
def get_custom_works(orcid: str = Query(...)) -> Dict[str, Any]:
    """Retorna las obras manuales / no indizadas cargadas por el usuario."""
    curation = get_curation()
    custom = curation.list_custom_works(orcid)
    return {
        "status": "success",
        "total": len(custom),
        "custom_works": custom
    }

@router.post("/works/import-bibtex")
def import_bibtex(req: BibtexImportRequest) -> Dict[str, Any]:
    """Importa obras personalizadas desde contenido de archivo BibTeX (.bib)."""
    curation = get_curation()
    count, msg = curation.import_bibtex_file(req.user_orcid, req.bibtex_content)
    return {
        "status": "success",
        "imported_count": count,
        "message": msg
    }

# --- Pipelines y Operaciones ---

@router.post("/pipeline/trigger")
def trigger_pipeline(req: PipelineRunRequest) -> Dict[str, Any]:
    """Simula o ejecuta tareas administrativas de pipeline en segundo plano."""
    return {
        "status": "success",
        "action": req.action,
        "task_id": f"task_{req.action}_{int(datetime.now().timestamp())}",
        "message": f"Tarea '{req.action}' iniciada satisfactoriamente con parámetros configurados."
    }
