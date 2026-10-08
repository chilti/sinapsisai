"""
api/routers/auth_curation.py - Router para autenticación ORCID, acreditaciones y curación
"""
import os
import sys
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from api.db import get_curation, get_neo4j_store
from lib.auth import exchange_code_for_token, get_orcid_login_url, trigger_background_sync

router = APIRouter(prefix="/api/auth", tags=["Autenticación & Curación"])

class TokenExchangeRequest(BaseModel):
    code: str
    redirect_uri: Optional[str] = None

class IndependentRegisterRequest(BaseModel):
    orcid: str
    full_name: str
    area_name: Optional[str] = None

class LinkProfileRequest(BaseModel):
    orcid: str
    user_name: str
    academic_id: str

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

class CancelTaskRequest(BaseModel):
    task_id: Optional[str] = None

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

    # Obtener estado de perfil vinculado en Neo4j si ya existe
    profile_info = {}
    try:
        neo = get_neo4j_store()
        u_prof = neo.get_user_profile(orcid)
        if u_prof and u_prof.get("academic_id"):
            profile_info = {
                "is_linked": True,
                "academic_id": u_prof.get("academic_id"),
                "academic_name": u_prof.get("academic_name") or u_prof.get("name"),
                "institution": u_prof.get("institution") or "INDEPENDIENTE",
                "entity": u_prof.get("entity") or "INDEPENDIENTE",
                "is_snii": bool(u_prof.get("is_snii")),
                "is_independent": (u_prof.get("institution") == "INDEPENDIENTE" or not u_prof.get("is_snii"))
            }
    except Exception as e_prof:
        print(f"[WARN] Error consultando perfil de usuario {orcid}: {e_prof}")

    return {
        "status": "success",
        "orcid": orcid,
        "name": name,
        "role": user_role,
        "is_admin": is_super or is_inst,
        "access_token": token_data.get("access_token"),
        "scope": token_data.get("scope"),
        "profile": profile_info
    }

# --- Estado de Perfil e Identidad Académica ---

@router.get("/profile-status")
def get_profile_status(orcid: str = Query(...)) -> Dict[str, Any]:
    """
    Retorna el estado de vinculación de un usuario con un perfil de académico (SNII o independiente).
    Si no está vinculado, busca coincidencias automáticas en el padrón institucional por ORCID.
    """
    if not orcid:
        raise HTTPException(status_code=400, detail="El ORCID es obligatorio")
    
    neo = get_neo4j_store()
    user_prof = neo.get_user_profile(orcid)
    if user_prof and user_prof.get("academic_id"):
        return {
            "status": "success",
            "is_linked": True,
            "academic_id": user_prof.get("academic_id"),
            "academic_name": user_prof.get("academic_name") or user_prof.get("name"),
            "institution": user_prof.get("institution") or "INDEPENDIENTE",
            "entity": user_prof.get("entity") or "INDEPENDIENTE",
            "is_snii": bool(user_prof.get("is_snii")),
            "is_independent": (user_prof.get("institution") == "INDEPENDIENTE" or not user_prof.get("is_snii")),
            "suggested_match": None
        }

    # Si no está vinculado, verificar si el ORCID existe en el padrón
    suggested = neo.find_academic_by_orcid(orcid)
    return {
        "status": "success",
        "is_linked": False,
        "academic_id": None,
        "academic_name": None,
        "institution": None,
        "is_snii": False,
        "is_independent": False,
        "suggested_match": suggested
    }

@router.get("/search-padron")
def search_padron(query: str = Query(..., min_length=2)) -> Dict[str, Any]:
    """Busca académicos en el padrón institucional para vinculación manual."""
    neo = get_neo4j_store()
    clean_q = query.strip()
    cquery = """
    MATCH (a:Person)
    WHERE toUpper(a.fullname) CONTAINS toUpper($q) OR toUpper(a.id) CONTAINS toUpper($q)
    RETURN a.id as id, a.fullname as name, a.orcid as existing_orcid, a.orcids as existing_orcids,
           a.institution as institution, a.is_snii as is_snii
    LIMIT 10
    """
    with neo.driver.session() as session:
        results = session.run(cquery, q=clean_q).data()
    return {
        "status": "success",
        "total": len(results),
        "results": results
    }

@router.post("/link-profile")
def link_profile(req: LinkProfileRequest) -> Dict[str, Any]:
    """Vincula un usuario autenticado a un académico existente en el padrón institucional."""
    if not req.orcid or not req.academic_id:
        raise HTTPException(status_code=400, detail="ORCID y academic_id son obligatorios")
        
    neo = get_neo4j_store()
    neo.upsert_user(req.orcid, req.user_name)
    neo.link_user_to_academic(req.orcid, req.academic_id)
    
    # Iniciar cosecha/sincronización en background
    try:
        trigger_background_sync(req.orcid, req.user_name, force=False)
    except Exception as e:
        print(f"[WARN] Error disparando background sync para link-profile: {e}")

    return {
        "status": "success",
        "message": f"Perfil vinculado exitosamente con el registro institucional {req.academic_id}"
    }

@router.post("/register-independent")
def register_independent_academic(req: IndependentRegisterRequest) -> Dict[str, Any]:
    """
    Registra un investigador independiente / no-SNII / internacional.
    Crea el nodo en Neo4j vinculado al usuario sin alterar censos institucionales,
    y dispara la ingesta y cálculo de métricas en segundo plano.
    """
    if not req.orcid or not req.full_name or not req.full_name.strip():
        raise HTTPException(status_code=400, detail="El ORCID y el nombre completo son obligatorios.")

    neo = get_neo4j_store()
    res = neo.create_independent_academic_and_link(
        orcid=req.orcid,
        full_name=req.full_name.strip(),
        area_name=req.area_name if req.area_name and req.area_name != "OTRA / SIN INFORMACIÓN" else None
    )

    # Disparar background sync para cosechar OpenAlex, ORCID API, Scopus y métricas ClickHouse
    try:
        trigger_background_sync(req.orcid, req.full_name.strip(), force=True)
    except Exception as e:
        print(f"[WARN] Error disparando background sync para independiente: {e}")

    return {
        "status": "success",
        "academic_id": res.get("academic_id", req.orcid),
        "academic_name": res.get("academic_name", req.full_name.strip()),
        "is_independent": True,
        "message": f"¡Perfil de investigador independiente registrado con éxito para {req.full_name.strip()}! Hemos iniciado la descarga de tu producción científica en segundo plano."
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

# --- Pipelines y Operaciones en Segundo Plano ---

PYTHON_EXEC = "/home/ambientesPy/revistaslatam/bin/python"
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class TaskState:
    def __init__(self, task_id: str, action: str, label: str):
        self.task_id = task_id
        self.action = action
        self.label = label
        self.status = "running"  # running, completed, failed, cancelled
        self.progress = 5
        self.current_step = "Iniciando..."
        self.logs: List[str] = [f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Tarea '{label}' iniciada."]
        self.created_at = datetime.now().isoformat()
        self.ended_at: Optional[str] = None
        self.proc: Optional[subprocess.Popen] = None
        self._cancelled = False

    def add_log(self, msg: str):
        self.logs.append(msg)
        if len(self.logs) > 3000:
            self.logs = self.logs[-2000:]

    def to_dict(self, since_index: int = 0) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "label": self.label,
            "status": self.status,
            "progress": self.progress,
            "current_step": self.current_step,
            "logs": self.logs[since_index:],
            "total_logs": len(self.logs),
            "created_at": self.created_at,
            "ended_at": self.ended_at
        }

ACTIVE_TASKS: Dict[str, TaskState] = {}
TASKS_LOCK = threading.Lock()
LATEST_TASK_ID: Optional[str] = None

def _build_task_steps(req: PipelineRunRequest) -> List[Dict[str, Any]]:
    steps = []
    academic = (req.academic_filter or "").strip()
    institution = (req.institution_filter or "").strip()
    phase = req.sync_phase or "all"
    use_local = req.use_local_llm if req.use_local_llm is not None else True
    sync_ch = bool(req.sync_ch)

    if req.action == "e2e_pipeline":
        sync_cmd = [PYTHON_EXEC, "ingestion/sync_works.py"]
        if academic:
            sync_cmd.extend(["--sync-academics", "--name", academic])
        elif institution:
            sync_cmd.extend(["--sync-entities", "--name", institution])
        else:
            sync_cmd.append("--all")
        if sync_ch:
            sync_cmd.append("--ch")
        if use_local:
            sync_cmd.append("--local")

        steps.append({
            "label": "1/3 Sincronización de Obras (OpenAlex / ORCID / Scopus)",
            "cmd": sync_cmd,
            "start_prog": 5,
            "end_prog": 35
        })

        map_cmd = [PYTHON_EXEC, "ingestion/sync_analytics_pipeline.py", "--phase", phase]
        if academic:
            map_cmd.extend(["--academic", academic])
        if institution:
            map_cmd.extend(["--institution", institution])

        steps.append({
            "label": "2/3 Mapeos Analíticos y Proyección en ClickHouse",
            "cmd": map_cmd,
            "start_prog": 35,
            "end_prog": 70
        })

        metrics_cmd = [PYTHON_EXEC, "ingestion/compute_scholar_metrics_ch.py"]
        if academic:
            metrics_cmd.extend(["--academic", academic])
        if institution:
            metrics_cmd.extend(["--institution", institution])

        steps.append({
            "label": "3/3 Cómputo de Métricas Cienciométricas y Parquets",
            "cmd": metrics_cmd,
            "start_prog": 70,
            "end_prog": 98
        })

    elif req.action == "harvest_works":
        sync_cmd = [PYTHON_EXEC, "ingestion/sync_works.py"]
        if academic:
            sync_cmd.extend(["--sync-academics", "--name", academic])
        elif institution:
            sync_cmd.extend(["--sync-entities", "--name", institution])
        else:
            sync_cmd.append("--all")
        if sync_ch:
            sync_cmd.append("--ch")
        if use_local:
            sync_cmd.append("--local")
        steps.append({
            "label": "Cosecha de Obras OpenAlex / Scopus / ORCID",
            "cmd": sync_cmd,
            "start_prog": 5,
            "end_prog": 95
        })

    elif req.action == "ch_sync":
        map_cmd = [PYTHON_EXEC, "ingestion/sync_analytics_pipeline.py", "--phase", phase]
        if academic:
            map_cmd.extend(["--academic", academic])
        if institution:
            map_cmd.extend(["--institution", institution])
        steps.append({
            "label": "Sincronización ClickHouse y Mapeos Analíticos",
            "cmd": map_cmd,
            "start_prog": 5,
            "end_prog": 95
        })

    elif req.action == "compute_metrics":
        metrics_cmd = [PYTHON_EXEC, "ingestion/compute_scholar_metrics_ch.py"]
        if academic:
            metrics_cmd.extend(["--academic", academic])
        if institution:
            metrics_cmd.extend(["--institution", institution])
        steps.append({
            "label": "Cómputo de Métricas Cienciométricas",
            "cmd": metrics_cmd,
            "start_prog": 5,
            "end_prog": 95
        })

    elif req.action == "ror_step1":
        steps.append({
            "label": "2.1 Extracción de Catálogo ROR Mexicano",
            "cmd": [PYTHON_EXEC, "ROR/extract_mexican_rors.py"],
            "start_prog": 10,
            "end_prog": 95
        })

    elif req.action == "ror_step2":
        steps.append({
            "label": "2.2 Resolución de Padrón a ROR",
            "cmd": [PYTHON_EXEC, "ROR/snii_ror_resolver2.py"],
            "start_prog": 10,
            "end_prog": 95
        })

    elif req.action == "ror_step3":
        steps.append({
            "label": "2.3 Sincronización ROR en Neo4j",
            "cmd": [PYTHON_EXEC, "ROR/ingest_ror_docs2.py"],
            "start_prog": 10,
            "end_prog": 95
        })

    elif req.action == "missing_orcids":
        steps.append({
            "label": "Barrido de Investigadores sin ORCID",
            "cmd": [PYTHON_EXEC, "ingestion/challenge_neo4j_orcids.py"],
            "start_prog": 10,
            "end_prog": 95
        })
    else:
        raise ValueError(f"Acción '{req.action}' no reconocida")

    return steps

def _run_pipeline_worker(task: TaskState, steps: List[Dict[str, Any]]):
    try:
        base_dir_str = str(BASE_DIR)
        for i, step in enumerate(steps):
            if task._cancelled:
                break
            task.current_step = step["label"]
            task.progress = step["start_prog"]
            task.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] ▶️ {step['label']}")
            task.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] 💻 Comando: {' '.join(step['cmd'])}")

            proc = subprocess.Popen(
                step["cmd"],
                cwd=base_dir_str,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            task.proc = proc

            for line in iter(proc.stdout.readline, ''):
                if task._cancelled:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    break
                line_str = line.strip()
                if line_str:
                    task.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] {line_str}")

            proc.stdout.close()
            ret_code = proc.wait()

            if task._cancelled:
                task.status = "cancelled"
                task.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 Paso cancelado por el usuario.")
                break

            if ret_code != 0:
                task.status = "failed"
                task.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ El paso falló con código {ret_code}")
                break
            else:
                task.progress = step["end_prog"]
                task.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Paso completado.")

        if not task._cancelled and task.status != "failed":
            task.status = "completed"
            task.progress = 100
            task.current_step = "Finalizado"
            task.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🎉 Tarea finalizada exitosamente.")
            try:
                from utils.pipeline_metadata import save_pipeline_metadata
                save_pipeline_metadata(BASE_DIR)
                task.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] 📋 Metadatos del snapshot y pipeline actualizados.")
            except Exception as me:
                task.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ No se pudieron guardar metadatos: {me}")

    except Exception as e:
        task.status = "failed"
        task.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] 💥 Error inesperado: {str(e)}")
    finally:
        task.ended_at = datetime.now().isoformat()
        task.proc = None

def cancel_task(task_id: str) -> bool:
    with TASKS_LOCK:
        task = ACTIVE_TASKS.get(task_id)
        if not task:
            return False
        task._cancelled = True
        task.status = "cancelled"
        if task.proc and task.proc.poll() is None:
            try:
                task.proc.terminate()
                task.proc.kill()
            except Exception:
                pass
        task.add_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 Cancelación solicitada por el usuario.")
        return True

def _get_system_pipeline_status() -> Optional[Dict[str, Any]]:
    """Detecta si hay un pipeline ejecutándose directamente en terminal (por ej. vía nohup/bash)."""
    try:
        res = subprocess.run(
            ["pgrep", "-fa", "ingestion/sync_works.py|ingestion/sync_analytics_pipeline.py|ingestion/compute_scholar_metrics_ch.py"],
            stdout=subprocess.PIPE, text=True, timeout=2
        )
        pids = [p.strip() for p in res.stdout.strip().split("\n") if p.strip()]
        if pids:
            log_path = BASE_DIR / "pipeline_e2e.log"
            if not log_path.exists():
                log_path = Path("/home/sinapsisai/pipeline_e2e.log")
            recent_logs = []
            if log_path.exists():
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        recent_logs = [l.strip() for l in lines[-40:] if l.strip()]
                except Exception:
                    pass
            return {
                "system_active": True,
                "pids": pids,
                "logs": recent_logs
            }
    except Exception:
        pass
    return None

@router.post("/pipeline/trigger")
def trigger_pipeline(req: PipelineRunRequest) -> Dict[str, Any]:
    """Inicia la ejecución real del pipeline configurado en segundo plano."""
    global LATEST_TASK_ID
    with TASKS_LOCK:
        for tid, t in ACTIVE_TASKS.items():
            if t.status == "running":
                raise HTTPException(
                    status_code=409,
                    detail=f"Ya existe una tarea en ejecución: {t.label} (ID: {tid}). Espera o cancélala antes de iniciar otra."
                )

        try:
            steps = _build_task_steps(req)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        task_id = f"task_{req.action}_{int(datetime.now().timestamp())}"
        action_labels = {
            "e2e_pipeline": "Pipeline Completo E2E",
            "harvest_works": "Cosecha de Obras OpenAlex",
            "ch_sync": "Sincronización ClickHouse",
            "compute_metrics": "Cómputo de Métricas",
            "ror_step1": "2.1 Extraer Catálogo ROR",
            "ror_step2": "2.2 Resolver Padrón a ROR",
            "ror_step3": "2.3 Sincronizar Neo4j",
            "missing_orcids": "Barrido sin ORCID"
        }
        label = action_labels.get(req.action, req.action)
        task = TaskState(task_id, req.action, label)
        ACTIVE_TASKS[task_id] = task
        LATEST_TASK_ID = task_id

    worker_thread = threading.Thread(
        target=_run_pipeline_worker,
        args=(task, steps),
        daemon=True
    )
    worker_thread.start()

    return {
        "status": "started",
        "task_id": task_id,
        "action": req.action,
        "label": label,
        "message": f"Tarea '{label}' iniciada exitosamente en segundo plano."
    }

@router.get("/pipeline/status")
def get_pipeline_status(task_id: Optional[str] = Query(None), since_index: int = Query(0)) -> Dict[str, Any]:
    """Consulta el estado, progreso y bitácora en vivo de una tarea o del pipeline del sistema."""
    global LATEST_TASK_ID
    target_id = task_id or LATEST_TASK_ID
    if target_id:
        with TASKS_LOCK:
            task = ACTIVE_TASKS.get(target_id)
            if task:
                return {
                    "status": "success",
                    **task.to_dict(since_index=since_index)
                }

    # Si no hay tarea disparada desde panel, verificar si hay ejecución en terminal
    sys_status = _get_system_pipeline_status()
    if sys_status and sys_status["system_active"]:
        return {
            "status": "system_running",
            "task_id": "terminal_process",
            "label": "Pipeline en Ejecución desde Terminal",
            "task_status": "running",
            "progress": 50,
            "current_step": "Ejecución externa en terminal",
            "logs": sys_status["logs"],
            "total_logs": len(sys_status["logs"]),
            "is_system_job": True
        }

    return {
        "status": "idle",
        "message": "No hay tareas activas en segundo plano."
    }

@router.post("/pipeline/cancel")
def cancel_pipeline(req: Optional[CancelTaskRequest] = None, task_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Cancela una tarea en ejecución."""
    target_id = (req.task_id if req and req.task_id else None) or task_id or LATEST_TASK_ID
    if not target_id:
        raise HTTPException(status_code=400, detail="Debe especificar un task_id para cancelar.")
    ok = cancel_task(target_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"No se encontró o no se pudo cancelar la tarea {target_id}")
    return {
        "status": "success",
        "message": f"Tarea {target_id} cancelada exitosamente."
    }
