"""
lib/orcid_sync.py - Sincronización Bidireccional hacia la API de ORCID (v3.0)
Permite a los investigadores exportar sus obras curadas y validadas en SNII Info TlachIA
directamente a su perfil oficial de ORCID (POST /v3.0/{orcid}/work).
"""

import os
import re
import json
import requests
from typing import Dict, List, Optional, Set, Any
from dotenv import load_dotenv

load_dotenv("/home/sinapsisai/.env")

# URLs de la API de ORCID
ORCID_PROD_API = "https://api.orcid.org/v3.0"
ORCID_SANDBOX_API = "https://api.sandbox.orcid.org/v3.0"


def get_api_base_url(is_sandbox: bool = False) -> str:
    """Devuelve la URL base de la API según el entorno."""
    if is_sandbox or os.getenv("ORCID_USE_SANDBOX", "false").lower() in ("true", "1", "yes"):
        return ORCID_SANDBOX_API
    return ORCID_PROD_API


def normalize_orcid(orcid_str: str) -> str:
    """Extrae el formato canónico 0000-0000-0000-0000 de un string o URL."""
    if not orcid_str:
        return ""
    clean = str(orcid_str).strip().rstrip('/')
    match = re.search(r'\d{4}-\d{4}-\d{4}-[\dX]{4}', clean)
    if match:
        return match.group(0)
    return clean.split('/')[-1]


def get_write_token(orcid: str, explicit_token: Optional[str] = None) -> Optional[str]:
    """
    Obtiene el token de acceso con permisos de escritura.
    Primero busca explicit_token, luego en SQLite curation_hub.db (descifrado).
    """
    if explicit_token and explicit_token.strip():
        return explicit_token.strip()

    from lib.curation_service import get_user_token
    bare_orcid = normalize_orcid(orcid)
    
    # 1. Intentar token específico para /activities/update
    token = get_user_token(bare_orcid, scope="/activities/update")
    if token:
        return token
        
    # 2. Intentar cualquier token guardado
    token = get_user_token(bare_orcid)
    return token


def map_work_type(raw_type: Optional[str]) -> str:
    """Mapea tipos de publicación heterogéneos al vocabulario estándar de ORCID."""
    if not raw_type:
        return "journal-article"
    t = str(raw_type).lower().strip()
    if any(k in t for k in ["article", "journal", "articulo", "revista"]):
        return "journal-article"
    elif any(k in t for k in ["book", "libro", "monograph"]):
        return "book"
    elif any(k in t for k in ["chapter", "capitulo", "section"]):
        return "book-chapter"
    elif any(k in t for k in ["conference", "proceedings", "congreso", "ponencia"]):
        return "conference-paper"
    elif any(k in t for k in ["thesis", "tesis", "dissertation"]):
        return "dissertation-thesis"
    elif any(k in t for k in ["preprint", "working paper"]):
        return "working-paper"
    elif any(k in t for k in ["patent", "patente"]):
        return "patent"
    elif any(k in t for k in ["dataset", "datos"]):
        return "data-set"
    return "journal-article"


def build_orcid_work_payload(work: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transforma un diccionario de publicación (ClickHouse, Neo4j, .bib)
    al esquema JSON oficial de ORCID Work v3.0.
    """
    title_str = work.get("title") or work.get("paper_title") or "Sin título"
    journal_str = work.get("journal") or work.get("journal_name") or work.get("venue") or ""
    year_val = work.get("year") or work.get("publication_year") or work.get("paper_year")
    doi_str = work.get("doi") or work.get("DOI") or ""
    abstract_str = work.get("abstract") or work.get("Abstract") or work.get("short_description") or ""
    work_type = map_work_type(work.get("type") or work.get("work_type"))

    # Limpiar DOI
    clean_doi = str(doi_str).replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    if clean_doi.lower() in ["none", "null", ""]:
        clean_doi = ""

    payload: Dict[str, Any] = {
        "title": {
            "title": {"value": str(title_str).strip()}
        },
        "type": work_type
    }

    if journal_str:
        payload["journal-title"] = {"value": str(journal_str).strip()}

    if abstract_str:
        # ORCID limita la descripción a 5000 caracteres
        payload["short-description"] = str(abstract_str)[:4900].strip()

    # Fecha de publicación
    if year_val:
        try:
            y_int = int(str(year_val).split('-')[0].strip())
            if 1800 <= y_int <= 2100:
                payload["publication-date"] = {
                    "year": {"value": f"{y_int:04d}"},
                    "month": None,
                    "day": None
                }
        except (ValueError, TypeError):
            pass

    # Identificadores externos (DOI, Handle, WOS, Scopus EID)
    external_ids_list = []
    if clean_doi:
        external_ids_list.append({
            "external-id-type": "doi",
            "external-id-value": clean_doi,
            "external-id-url": {"value": f"https://doi.org/{clean_doi}"},
            "external-id-relationship": "self"
        })

    # Si hay Scopus EID
    scopus_eid = work.get("scopus_id") or work.get("scopus_eid") or work.get("paper_scopus_eid")
    if scopus_eid and str(scopus_eid).strip():
        clean_eid = str(scopus_eid).strip()
        external_ids_list.append({
            "external-id-type": "eid",
            "external-id-value": clean_eid,
            "external-id-url": {"value": f"https://www.scopus.com/record/display.uri?eid={clean_eid}&origin=inward"},
            "external-id-relationship": "self"
        })

    # Si hay OpenAlex Work ID (W...)
    oa_id = work.get("paper_openalex_id") or work.get("openalex_id")
    if oa_id and str(oa_id).startswith("W") and str(oa_id)[1:].isdigit():
        external_ids_list.append({
            "external-id-type": "uri",
            "external-id-value": f"https://openalex.org/{oa_id}",
            "external-id-url": {"value": f"https://openalex.org/{oa_id}"},
            "external-id-relationship": "self"
        })

    if external_ids_list:
        payload["external-ids"] = {"external-id": external_ids_list}

    # URL directa de la obra
    if clean_doi:
        payload["url"] = {"value": f"https://doi.org/{clean_doi}"}

    # Autores / Contribuidores
    authors_raw = work.get("authors") or work.get("author_names") or ""
    if authors_raw:
        contrib_list = []
        if isinstance(authors_raw, list):
            auth_names = [str(a).strip() for a in authors_raw if str(a).strip()]
        elif isinstance(authors_raw, str):
            if ";" in authors_raw:
                auth_names = [a.strip() for a in authors_raw.split(";") if a.strip()]
            elif " and " in authors_raw:
                auth_names = [a.strip() for a in authors_raw.split(" and ") if a.strip()]
            else:
                auth_names = [a.strip() for a in authors_raw.split(",") if a.strip()]
        else:
            auth_names = []

        for name in auth_names[:20]:  # Limitar para evitar payloads gigantes
            contrib_list.append({
                "credit-name": {"value": name},
                "contributor-attributes": {
                    "contributor-role": "author"
                }
            })
        if contrib_list:
            payload["contributors"] = {"contributor": contrib_list}

    # Cita en formato BibTeX si existe
    bibtex_raw = work.get("bibtex_raw") or work.get("bibtex")
    if bibtex_raw:
        payload["citation"] = {
            "citation-type": "bibtex",
            "citation-value": str(bibtex_raw).strip()
        }

    return payload


def get_existing_dois_in_orcid(orcid: str, token: str, is_sandbox: bool = False) -> Set[str]:
    """
    Consulta la API de ORCID para obtener la lista de DOIs que el usuario
    ya tiene registrados en su perfil. Permite evitar duplicaciones.
    """
    clean_orc = normalize_orcid(orcid)
    base_url = get_api_base_url(is_sandbox)
    endpoint = f"{base_url}/{clean_orc}/works"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    dois = set()
    try:
        resp = requests.get(endpoint, headers=headers, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            for group in data.get("group", []):
                for summary in group.get("work-summary", []):
                    ext_ids = summary.get("external-ids", {}).get("external-id", [])
                    for ext in ext_ids:
                        if ext.get("external-id-type", "").lower() == "doi":
                            doi_val = ext.get("external-id-value", "").lower().strip()
                            clean = doi_val.replace("https://doi.org/", "").replace("http://doi.org/", "")
                            if clean:
                                dois.add(clean)
    except Exception as e:
        print(f"[orcid_sync] Error consultando DOIs existentes en ORCID: {e}")

    return dois


def push_work_to_orcid(
    orcid: str,
    work: Dict[str, Any],
    token: Optional[str] = None,
    is_sandbox: bool = False,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Envía una obra individual a la API de ORCID (POST /v3.0/{orcid}/work).
    
    Retorna:
        dict con status: 'CREATED', 'ALREADY_EXISTS', 'ERROR', 'DRY_RUN'
    """
    clean_orc = normalize_orcid(orcid)
    payload = build_orcid_work_payload(work)

    if dry_run:
        return {
            "status": "DRY_RUN",
            "title": payload.get("title", {}).get("title", {}).get("value"),
            "payload": payload
        }

    auth_token = get_write_token(clean_orc, explicit_token=token)
    if not auth_token:
        return {
            "status": "ERROR",
            "error": "No se encontró token de escritura (/activities/update) para este ORCID.",
            "title": payload.get("title", {}).get("title", {}).get("value")
        }

    base_url = get_api_base_url(is_sandbox)
    endpoint = f"{base_url}/{clean_orc}/work"
    headers = {
        "Content-Type": "application/vnd.orcid+json",
        "Accept": "application/json",
        "Authorization": f"Bearer {auth_token}"
    }

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=15)
        
        # 201 Created es la respuesta exitosa en ORCID
        if resp.status_code == 201:
            put_code = None
            loc = resp.headers.get("Location")
            if loc:
                put_code = loc.split('/')[-1]
            return {
                "status": "CREATED",
                "put_code": put_code,
                "title": payload.get("title", {}).get("title", {}).get("value"),
                "status_code": 201
            }
        elif resp.status_code == 409:
            # 409 Conflict: la obra o DOI ya está registrada por esta fuente
            return {
                "status": "ALREADY_EXISTS",
                "title": payload.get("title", {}).get("title", {}).get("value"),
                "status_code": 409
            }
        else:
            err_detail = ""
            try:
                err_data = resp.json()
                err_detail = err_data.get("user-message") or err_data.get("developer-message") or str(err_data)
            except Exception:
                err_detail = resp.text[:300]
                
            return {
                "status": "ERROR",
                "status_code": resp.status_code,
                "error": f"HTTP {resp.status_code}: {err_detail}",
                "title": payload.get("title", {}).get("title", {}).get("value")
            }
    except requests.exceptions.RequestException as e:
        return {
            "status": "ERROR",
            "error": f"Fallo de conexión con la API de ORCID: {e}",
            "title": payload.get("title", {}).get("title", {}).get("value")
        }


def sync_curated_works_to_orcid(
    orcid: str,
    works: List[Dict[str, Any]],
    token: Optional[str] = None,
    is_sandbox: bool = False,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Sincroniza un lote de obras curadas con ORCID evitando duplicados de DOIs.
    """
    clean_orc = normalize_orcid(orcid)
    auth_token = get_write_token(clean_orc, explicit_token=token)

    if not auth_token and not dry_run:
        return {
            "total": len(works),
            "pushed": 0,
            "already_exists": 0,
            "failed": len(works),
            "error": "Falta token con scope /activities/update.",
            "details": []
        }

    # 1. Obtener DOIs ya presentes en ORCID
    existing_dois = set()
    if not dry_run and auth_token:
        existing_dois = get_existing_dois_in_orcid(clean_orc, auth_token, is_sandbox)

    results = {
        "total": len(works),
        "pushed": 0,
        "already_exists": 0,
        "failed": 0,
        "details": []
    }

    for w in works:
        doi = str(w.get("doi") or "").replace("https://doi.org/", "").strip().lower()
        title = w.get("title") or w.get("paper_title") or "Sin título"

        # Verificar si ya existe en ORCID
        if doi and doi in existing_dois:
            results["already_exists"] += 1
            results["details"].append({
                "title": title,
                "doi": doi,
                "status": "ALREADY_EXISTS",
                "message": "La obra ya se encuentra registrada en tu perfil de ORCID con este DOI."
            })
            continue

        res = push_work_to_orcid(clean_orc, w, token=auth_token, is_sandbox=is_sandbox, dry_run=dry_run)
        st_code = res.get("status")

        if st_code == "CREATED":
            results["pushed"] += 1
            if doi:
                existing_dois.add(doi)
            results["details"].append({
                "title": title,
                "doi": doi,
                "status": "CREATED",
                "put_code": res.get("put_code")
            })
        elif st_code == "ALREADY_EXISTS":
            results["already_exists"] += 1
            results["details"].append({
                "title": title,
                "doi": doi,
                "status": "ALREADY_EXISTS"
            })
        elif st_code == "DRY_RUN":
            results["pushed"] += 1
            results["details"].append({
                "title": title,
                "doi": doi,
                "status": "DRY_RUN",
                "payload": res.get("payload")
            })
        else:
            results["failed"] += 1
            results["details"].append({
                "title": title,
                "doi": doi,
                "status": "ERROR",
                "error": res.get("error")
            })

    return results
