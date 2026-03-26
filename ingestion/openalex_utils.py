"""
openalex_utils.py
─────────────────
Utilidades para consultar OpenAlex (API local y oficial).

Cambios de la nueva API (2024-2025):
- Autenticación: ?api_key=KEY  (ya no se usa mailto como auth principal)
- DOI lookup directo: GET /works/doi:10.xxx  o  /works/https://doi.org/10.xxx
- Filtro multi-DOI:   ?filter=doi:10.a|10.b|10.c
- Parámetro per_page (antes per-page)
- Base URL: https://api.openalex.org  (sin cambios)

Prioridad: API local (5009) → API oficial como fallback.
"""

import os
import httpx
import time
import difflib
from dotenv import load_dotenv

load_dotenv()

LOCAL_BASE    = os.getenv("OPENALEX_LOCAL_API", "http://localhost:5009")
OFFICIAL_BASE = "https://api.openalex.org"

# Se pone True si la oficial responde con 403/429 para no seguir intentando
OFFICIAL_API_BLOCKED = False

def _email():
    return os.getenv("EMAIL_ADDRESS", "sin_correo@ciencias.unam.mx")

def _api_key():
    return os.getenv("OPENALEX_API_KEY")

def _auth_params() -> dict:
    """Devuelve los parámetros de autenticación correctos para la API oficial."""
    key = _api_key()
    if key:
        return {"api_key": key}
    # Fallback: mailto en User-Agent se sigue aceptando en el plan gratuito
    return {"mailto": _email()}

def _user_agent() -> str:
    return f"SinapsisAI/2.0 (mailto:{_email()})"

def _clean_title(t: str) -> str:
    if not t: return ""
    return "".join(c for c in str(t).lower() if c.isalnum())

def _backoff_get(client: httpx.Client, url: str, params: dict = None,
                 retries: int = 3, base_wait: float = 1.0) -> httpx.Response | None:
    """GET con reintentos y backoff exponencial en 429/403."""
    for attempt in range(retries):
        try:
            resp = client.get(url, params=params,
                              headers={"User-Agent": _user_agent()},
                              timeout=20, follow_redirects=True)
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 403):
                wait = base_wait * (2 ** attempt)
                print(f"      ⚠️  [{resp.status_code}] Rate limit en {url}. Esperando {wait:.0f}s...")
                time.sleep(wait)
            else:
                return resp   # 404, 500, etc — no reintentar
        except Exception as e:
            print(f"      ⚠️  Error HTTP ({url}): {e}")
            time.sleep(base_wait)
    return None


# ─────────────────────────────────────────────────────────────────
# get_work: Busca UN trabajo por DOI o título
# ─────────────────────────────────────────────────────────────────
def get_work(doi: str = None, title: str = None,
             email: str = None, api_key: str = None,
             local_only: bool = False) -> dict | None:
    """
    Busca un trabajo en OpenAlex.
    Orden: API local → API oficial.
    Si local_only=True, no toca la API oficial.
    """
    global OFFICIAL_API_BLOCKED

    with httpx.Client(verify=False, timeout=20) as client:

        # ── 1. API LOCAL ─────────────────────────────────────────
        if doi:
            clean_doi = doi.replace("https://doi.org/", "").strip()
            # Nuevo path directo: /works/doi:10.xxx
            url = f"{LOCAL_BASE}/works/doi:{clean_doi}"
            resp = _backoff_get(client, url)
            if resp and resp.status_code == 200:
                data = resp.json()
                # Respuesta directa (single work) o lista
                if isinstance(data, dict) and data.get("id"):
                    print(f"      ✅ [Local] Encontrado por DOI directo: {clean_doi}")
                    return data
                # Fallback con filtro (por si el servidor local usa otro estilo)
                resp2 = _backoff_get(client, f"{LOCAL_BASE}/works",
                                     {"filter": f"doi:https://doi.org/{clean_doi}", "per_page": 1})
                if resp2 and resp2.status_code == 200:
                    results = resp2.json().get("results", [])
                    if results:
                        print(f"      ✅ [Local] Encontrado por filtro DOI: {clean_doi}")
                        return results[0]

        if title and len(title) > 10:
            resp = _backoff_get(client, f"{LOCAL_BASE}/works",
                                {"search": title, "per_page": 1})
            if resp and resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    ratio = difflib.SequenceMatcher(
                        None, _clean_title(title), _clean_title(results[0].get("title"))
                    ).ratio()
                    if ratio > 0.95:
                        print(f"      ✅ [Local] Encontrado por título (sim={ratio:.2f}): {title[:60]}")
                        return results[0]

        if local_only:
            return None

        # ── 2. API OFICIAL ───────────────────────────────────────
        if OFFICIAL_API_BLOCKED:
            return None

        auth = _auth_params()

        if doi:
            clean_doi = doi.replace("https://doi.org/", "").strip()
            # Nuevo path directo documentado: GET /works/doi:10.xxx
            url = f"{OFFICIAL_BASE}/works/doi:{clean_doi}"
            resp = _backoff_get(client, url, auth)
            if resp and resp.status_code == 200:
                print(f"      ✅ [Oficial] Encontrado por DOI: {clean_doi}")
                return resp.json()
            if resp and resp.status_code in (403, 429):
                OFFICIAL_API_BLOCKED = True
                return None

        if title and len(title) > 10:
            params = {**auth, "search": title, "per_page": 5}
            resp = _backoff_get(client, f"{OFFICIAL_BASE}/works", params)
            if resp and resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    ratio = difflib.SequenceMatcher(
                        None, _clean_title(title), _clean_title(results[0].get("title"))
                    ).ratio()
                    if ratio > 0.95:
                        print(f"      ✅ [Oficial] Encontrado por título (sim={ratio:.2f}): {title[:60]}")
                        return results[0]
            if resp and resp.status_code in (403, 429):
                OFFICIAL_API_BLOCKED = True

    return None


# ─────────────────────────────────────────────────────────────────
# get_works_batch: Busca múltiples DOIs en una sola llamada
# ─────────────────────────────────────────────────────────────────
def get_works_batch(dois: list, email: str = None,
                    local_only: bool = False) -> dict:
    """
    Busca hasta 50 DOIs usando filter=doi:a|b|c.
    Retorna dict {doi_clean: work_dict}.
    Prioridad: local → oficial.
    """
    global OFFICIAL_API_BLOCKED
    if not dois:
        return {}

    results_dict = {}

    def _fetch(base_url: str, clean_dois: list, extra_params: dict = None) -> list:
        doi_filter = "|".join([f"https://doi.org/{d}" for d in clean_dois])
        params = {"filter": f"doi:{doi_filter}", "per_page": len(clean_dois)}
        if extra_params:
            params.update(extra_params)
        with httpx.Client(verify=False, timeout=30) as client:
            resp = _backoff_get(client, f"{base_url}/works", params)
            if resp and resp.status_code == 200:
                return resp.json().get("results", [])
        return []

    # 1. Local
    works = _fetch(LOCAL_BASE, dois)
    for w in works:
        d_key = (w.get("doi") or "").replace("https://doi.org/", "").strip().lower()
        if d_key:
            results_dict[d_key] = w

    # 2. Oficial para los faltantes
    missing = [d for d in dois if d.lower() not in results_dict]
    if missing and not local_only and not OFFICIAL_API_BLOCKED:
        auth = _auth_params()
        works = _fetch(OFFICIAL_BASE, missing, auth)
        for w in works:
            d_key = (w.get("doi") or "").replace("https://doi.org/", "").strip().lower()
            if d_key:
                results_dict[d_key] = w

    return results_dict


# ─────────────────────────────────────────────────────────────────
# get_works_by_ror: Recupera todos los trabajos por ROR
# ─────────────────────────────────────────────────────────────────
def get_works_by_ror(ror_id: str, per_page: int = 100, local_only: bool = False):
    """
    Generador que devuelve páginas de trabajos asociados a un ROR.
    Prioridad: API local → API oficial.
    """
    global OFFICIAL_API_BLOCKED

    ror_id_clean = ror_id.replace("https://ror.org/", "").strip()
    
    # Intentar Local
    try:
        with httpx.Client(verify=False, timeout=30) as client:
            # 1. Probar si el ROR existe localmente usando el nuevo path
            check_url = f"{LOCAL_BASE}/institutions/ror:{ror_id_clean}"
            resp_check = client.get(check_url, timeout=30)
            
            if resp_check.status_code != 200:
                # Fallback: intentar por búsqueda de works si el path directo no está listo
                url = f"{LOCAL_BASE}/works"
                params = {"filter": f"institutions.ror:{ror_id}", "per_page": 1, "skip_count": "true"}
                resp_check = client.get(url, params=params, timeout=30)

            if resp_check.status_code == 200:
                print(f"      ✅ [Local] ROR {ror_id_clean} disponible.")
                # Pagination loop - use full ROR URL for the filter (raw_data LIKE match)
                url = f"{LOCAL_BASE}/works"
                page = 1
                while True:
                    p = {"filter": f"institutions.ror:{ror_id}", "per_page": per_page, "page": page}
                    r = client.get(url, params=p, timeout=60)
                    if r.status_code != 200:
                        print(f"      ⚠️ [Local] HTTP {r.status_code} en página {page}. Deteniendo.")
                        break
                    if not r.content:
                        print(f"      ⚠️ [Local] Respuesta vacía en página {page}. Deteniendo.")
                        break
                    # Si el servidor devuelve HTML (SPA fallback), el filtro no está soportado localmente
                    ct = r.headers.get("content-type", "")
                    if "text/html" in ct:
                        print(f"      ℹ️ [Local] Filtro institutions.ror no soportado para {ror_id_clean}. Sin works locales.")
                        break
                    try:
                        data = r.json()
                    except Exception as json_err:
                        print(f"      ⚠️ [Local] Respuesta no-JSON en página {page}: {json_err}. Deteniendo.")
                        print(f"         Respuesta recibida: {r.text[:200]}")
                        break
                    
                    results = data.get("results", [])
                    if not results: break
                    
                    # VALIDACIÓN CRÍTICA: La API local a veces ignora el filtro y manda TODO
                    # Verificamos si al menos el primer resultado tiene el ROR solicitado
                    if page == 1 and results:
                        first_work = results[0]
                        found_ror = False
                        for auth in first_work.get('authorships', []):
                            for inst in auth.get('institutions', []):
                                if inst.get('ror') == ror_id or inst.get('ror') == f"https://ror.org/{ror_id_clean}":
                                    found_ror = True
                                    break
                        if not found_ror:
                            print(f"      ❌ [Local] ERROR CRÍTICO: El ROR {ror_id_clean} no aparece en los resultados. La API local parece estar ignorando el filtro.")
                            print(f"         Abortando para evitar ingesta masiva errónea.")
                            break
                    
                    yield results
                    if len(results) < per_page: break
                    page += 1
                return
    except Exception as e:
        print(f"      ⚠️ [Local] No disponible para ROR ({e}). Intentando oficial...")

    # Intentar Oficial
    if local_only or OFFICIAL_API_BLOCKED:
        return

    auth = _auth_params()
    try:
        with httpx.Client(verify=False, timeout=30) as client:
            url = f"{OFFICIAL_BASE}/works"
            # Pagination loop (usando cursor o offset, pero para ROR simple el offset/page suele bastar)
            page = 1
            while True:
                p = {**auth, "filter": f"institutions.ror:{ror_id}", "per_page": per_page, "page": page}
                r = _backoff_get(client, url, p)
                if not r or r.status_code != 200:
                    if r and r.status_code in (403, 429):
                        OFFICIAL_API_BLOCKED = True
                    break
                data = r.json()
                results = data.get("results", [])
                if not results: break
                yield results
                if len(results) < per_page: break
                page += 1
    except Exception as e:
        print(f"      ❌ [Oficial] Error recuperando ROR {ror_id_clean}: {e}")
