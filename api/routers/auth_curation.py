"""
api/routers/auth_curation.py - Router para autenticación ORCID, acreditaciones y curación
"""
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from api.db import get_curation
from lib.auth import exchange_code_for_token, get_orcid_login_url

router = APIRouter(prefix="/api/auth", tags=["Autenticación & Curación"])

class TokenExchangeRequest(BaseModel):
    code: str

class AccreditationRequest(BaseModel):
    user_orcid: str
    user_name: str
    institution_name: str
    institutional_email: str
    position: str
    notes: Optional[str] = ""

class ApprovalRequest(BaseModel):
    request_id: int
    approver_orcid: str
    reason: Optional[str] = ""

class WorkCurationRequest(BaseModel):
    user_orcid: str
    work_id: str
    work_title: Optional[str] = ""
    reason: Optional[str] = ""

@router.get("/orcid/login-url")
def get_login_url() -> Dict[str, Any]:
    """Genera la URL de autorización OAuth de ORCID."""
    url = get_orcid_login_url()
    return {"login_url": url}

@router.post("/orcid/token")
def exchange_orcid_token(req: TokenExchangeRequest) -> Dict[str, Any]:
    """Intercambia el código OAuth de ORCID por los datos de perfil del usuario."""
    token_data = exchange_code_for_token(req.code)
    if not token_data or "orcid" not in token_data:
        raise HTTPException(status_code=400, detail="Error intercambiando el código de autorización de ORCID")

    orcid = token_data.get("orcid")
    name = token_data.get("name", "")
    
    curation = get_curation()
    is_super = curation.is_user_super_admin(orcid)
    is_inst = curation.is_user_institutional_admin(orcid)
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

@router.post("/accreditation/approve")
def approve_accreditation(req: ApprovalRequest) -> Dict[str, Any]:
    """Aprueba una solicitud de acreditación institucional."""
    curation = get_curation()
    ok = curation.decide_accreditation(user_orcid=req.approver_orcid, decision="approved", decided_by=req.approver_orcid)
    if not ok:
        raise HTTPException(status_code=400, detail="No se pudo aprobar la acreditación")
    return {"status": "success", "message": "Acreditación aprobada exitosamente"}

@router.post("/accreditation/reject")
def reject_accreditation(req: ApprovalRequest) -> Dict[str, Any]:
    """Rechaza una solicitud de acreditación institucional."""
    curation = get_curation()
    ok = curation.decide_accreditation(user_orcid=req.approver_orcid, decision="rejected", decided_by=req.approver_orcid)
    if not ok:
        raise HTTPException(status_code=400, detail="No se pudo rechazar la acreditación")
    return {"status": "success", "message": "Acreditación rechazada"}

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
