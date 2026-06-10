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

LOCAL_BASE    = os.getenv("OPENALEX_LOCAL_API", "http://localhost:5012")
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

# --- Persistent Client Management ---
_PERSISTENT_CLIENT = None

def _get_client():
    global _PERSISTENT_CLIENT
    if _PERSISTENT_CLIENT is None or _PERSISTENT_CLIENT.is_closed:
        _PERSISTENT_CLIENT = httpx.Client(verify=False, timeout=20, follow_redirects=True)
    return _PERSISTENT_CLIENT

def close_client():
    global _PERSISTENT_CLIENT
    if _PERSISTENT_CLIENT is not None:
        _PERSISTENT_CLIENT.close()
        _PERSISTENT_CLIENT = None

def _backoff_get(url: str, params: dict = None,
                 retries: int = 3, base_wait: float = 1.0) -> httpx.Response | None:
    """GET con reintentos y backoff exponencial en 429/403."""
    client = _get_client()
    for attempt in range(retries):
        try:

            resp = client.get(url, params=params,
                              headers={"User-Agent": _user_agent()},
                              timeout=60, follow_redirects=True)
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
             local_only: bool = False, quiet: bool = False) -> dict | None:
    """
    Busca un trabajo en OpenAlex.
    Orden: API local → API oficial.
    Si local_only=True, no toca la API oficial.
    """
    global OFFICIAL_API_BLOCKED

    # ── 1. API LOCAL ─────────────────────────────────────────
    if doi:
        clean_doi = doi.replace("https://doi.org/", "").strip()
        url = f"{LOCAL_BASE}/works/doi:{clean_doi}"
        resp = _backoff_get(url)
        if resp and resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get("id"):
                if not quiet: print(f"      ✅ [Local] Encontrado por DOI directo: {clean_doi}")
                return data

    if title and len(title) > 10:
        resp = _backoff_get(f"{LOCAL_BASE}/works",
                            {"search": title, "per_page": 1})
        if resp and resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                ratio = difflib.SequenceMatcher(
                    None, _clean_title(title), _clean_title(results[0].get("title"))
                ).ratio()
                if ratio > 0.95:
                    if not quiet: print(f"      ✅ [Local] Encontrado por título (sim={ratio:.2f}): {title[:60]}")
                    return results[0]

    if local_only:
        return None

    # ── 2. API OFICIAL ───────────────────────────────────────
    if OFFICIAL_API_BLOCKED:
        return None

    auth = _auth_params()

    if doi:
        clean_doi = doi.replace("https://doi.org/", "").strip()
        url = f"{OFFICIAL_BASE}/works/doi:{clean_doi}"
        resp = _backoff_get(url, auth)
        if resp and resp.status_code == 200:
            if not quiet: print(f"      ✅ [Oficial] Encontrado por DOI: {clean_doi}")
            return resp.json()
        if resp and resp.status_code in (403, 429):
            OFFICIAL_API_BLOCKED = True
            return None

    if title and len(title) > 10:
        params = {**auth, "search": title, "per_page": 5}
        resp = _backoff_get(f"{OFFICIAL_BASE}/works", params)
        if resp and resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                ratio = difflib.SequenceMatcher(
                    None, _clean_title(title), _clean_title(results[0].get("title"))
                ).ratio()
                if ratio > 0.95:
                    if not quiet: print(f"      ✅ [Oficial] Encontrado por título (sim={ratio:.2f}): {title[:60]}")
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
    Busca múltiples DOIs usando filter=doi:a|b|c.
    Procesa en fragmentos de 50 para evitar URLs demasiado largas.
    Retorna dict {doi_clean: work_dict}.
    """
    global OFFICIAL_API_BLOCKED
    if not dois:
        return {}

    results_dict = {}
    
    # Normalizar DOIs de entrada
    clean_input_dois = [d.replace("https://doi.org/", "").strip().lower() for d in dois if d]
    
    def _fetch_chunk(base_url: str, chunk: list, extra_params: dict = None, is_global: bool = False) -> list:
        # OpenAlex prefiere el DOI sin el prefijo https://doi.org/ en los filtros
        doi_filter = "|".join([d.replace("https://doi.org/", "") for d in chunk])
        params = {"filter": f"doi:{doi_filter}", "per_page": len(chunk)}
        if is_global:
            params["global"] = "true"
        if extra_params:
            params.update(extra_params)
        resp = _backoff_get(f"{base_url}/works", params)
        if resp and resp.status_code == 200:
            results = resp.json().get("results", [])
            return results
        return []

    # Procesar por trozos de 50
    chunk_size = 50
    for i in range(0, len(clean_input_dois), chunk_size):
        chunk = clean_input_dois[i:i+chunk_size]
        
        # 1. Local (Seed Mexico)
        works = _fetch_chunk(LOCAL_BASE, chunk)
        
        # 1.1 Fallback Local (Global) - DESACTIVADO para evitar timeouts
        # missing_after_seed = [d for d in chunk if d not in [ (w.get("doi") or "").replace("https://doi.org/", "").strip().lower() for w in works ]]
        # if missing_after_seed:
        #     works_global = _fetch_chunk(LOCAL_BASE, missing_after_seed, is_global=True)
        #     works.extend(works_global)

        for w in works:
            d_key = (w.get("doi") or "").replace("https://doi.org/", "").strip().lower()
            if d_key:
                results_dict[d_key] = w

        # 2. Oficial (solo si faltan y no estamos bloqueados)
        missing_in_chunk = [d for d in chunk if d.lower() not in results_dict]
        if missing_in_chunk and not local_only and not OFFICIAL_API_BLOCKED:
            auth = _auth_params()
            works_off = _fetch_chunk(OFFICIAL_BASE, missing_in_chunk, auth)
            for w in works_off:
                d_key = (w.get("doi") or "").replace("https://doi.org/", "").strip().lower()
                if d_key:
                    results_dict[d_key] = w
            
            # Verificar si nos bloquearon tras este chunk
            if len(missing_in_chunk) > 0 and len(works_off) == 0:
                # Podría ser bloqueo o simplemente que no existen, pero _backoff_get ya marca OFFICIAL_API_BLOCKED
                pass

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
        url = f"{OFFICIAL_BASE}/works"
        # Pagination loop (usando cursor o offset, pero para ROR simple el offset/page suele bastar)
        page = 1
        while True:
            p = {**auth, "filter": f"institutions.ror:{ror_id}", "per_page": per_page, "page": page}
            r = _backoff_get(url, p)
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


# ─────────────────────────────────────────────────────────────────
# fetch_all_works_by_author_id: Recupera TODAS las obras de un
# autor con paginación completa (local page=N + pyalex fallback)
# ─────────────────────────────────────────────────────────────────
def fetch_all_works_by_author_id(
    openalex_author_id: str,
    force_local: bool = False,
    per_page: int = 200,
) -> dict:
    """
    Obtiene la lista completa de trabajos de un autor por su OpenAlex Author ID.
    Soporta:
      - API local con paginación por `page=N` (sin límite de 1 página)
      - Fallback a pyalex (API oficial) con `.paginate()`

    Args:
        openalex_author_id: ID completo o código corto (A1234567).
        force_local: Si True, no usa la API oficial aunque la local falle.
        per_page: Tamaño de página para la API local.

    Returns:
        dict {doi_or_id: record_dict}
    """
    if not openalex_author_id:
        return {}

    oa_id_clean = str(openalex_author_id).split('/')[-1].strip()
    metadatos: dict = {}

    def _build_record(w: dict, source: str) -> dict:
        doi = w.get('doi') or w.get('id') or ''
        doi_clean = (str(doi)
                     .replace('https://doi.org/', '')
                     .replace('http://doi.org/', '')
                     .strip('/'))
        return doi_clean, {
            'Title':       w.get('title', 'Sin Título'),
            'Year':        w.get('publication_year', 0),
            'DOI':         doi_clean,
            'Source':      source,
            'Authors':     None,
            'Cited_by':    w.get('cited_by_count', 0),
            'Abstract':    None,
            'openalex_url': w.get('id'),
            '_raw_oa':     w,
        }

    # ── Intento 1: API local con paginación completa ──────────────
    try:
        client = _get_client()
        url    = f"{LOCAL_BASE}/works"
        page   = 1
        total_local = 0
        while True:
            params = {
                "filter":   f"author.id:{oa_id_clean}",
                "per_page": per_page,
                "page":     page,
            }
            resp = client.get(url, params=params, timeout=60)
            if resp.status_code != 200:
                break
            data    = resp.json()
            works   = data.get('results', [])
            if not works:
                break
            for w in works:
                key, rec = _build_record(w, 'OpenAlex_AuthorID_Local')
                if key and key not in metadatos:
                    metadatos[key] = rec
                    total_local += 1
            if len(works) < per_page:
                break
            page += 1

        if metadatos:
            print(f"    [OpenAlex Local] Author {oa_id_clean}: "
                  f"{len(metadatos)} trabajos ({page} página(s)).")
            return metadatos

    except Exception as e:
        print(f"    [WARN] Error API Local OpenAlex Author ({oa_id_clean}): {e}")

    # ── Intento 2: ClickHouse directo (works_flat.author_ids) ─────
    # La API local no soporta filter=author.id en todos los despliegues.
    # Fallback a una consulta directa sobre works_flat que sí es eficiente
    # porque author_ids es un Array(String) con índice bloom filter.
    oa_url_full = (openalex_author_id
                   if openalex_author_id.startswith('https://')
                   else f"https://openalex.org/{oa_id_clean}")
    try:
        from database.clickhouse_db import ch_client
        ch = ch_client.get_client()
        rows = ch.query(
            """
            SELECT id, doi, title, publication_year, cited_by_count,
                   abstract, fwci, is_oa, oa_status
            FROM works_flat
            WHERE has(author_ids, {oa_url:String})
            LIMIT 2000
            """,
            parameters={'oa_url': oa_url_full}
        ).result_rows
        if rows:
            for row in rows:
                oa_id_w, doi_w, title_w, year_w, cit_w, abs_w, fwci_w, is_oa_w, oa_st_w = row
                doi_clean = (str(doi_w or oa_id_w)
                             .replace('https://doi.org/', '')
                             .replace('http://doi.org/', '')
                             .strip('/'))
                if doi_clean and doi_clean not in metadatos:
                    metadatos[doi_clean] = {
                        'Title':        title_w or 'Sin Título',
                        'Year':         year_w or 0,
                        'DOI':          doi_clean,
                        'Source':       'OpenAlex_AuthorID_ClickHouse',
                        'Authors':      None,
                        'Cited_by':     cit_w or 0,
                        'Abstract':     abs_w or None,
                        'fwci':         fwci_w,
                        'openalex_url': oa_id_w,
                        '_raw_oa':      {'id': oa_id_w, 'doi': doi_w,
                                         'is_oa': is_oa_w, 'oa_status': oa_st_w},
                    }
            if metadatos:
                print(f"    [OpenAlex ClickHouse] Author {oa_id_clean}: "
                      f"{len(metadatos)} trabajos.")
                return metadatos
    except Exception as e:
        print(f"    [WARN] ClickHouse fallback para author_ids ({oa_id_clean}): {e}")

    if force_local:
        return {}

    # ── Intento 2: pyalex con paginación completa ─────────────────
    try:
        import pyalex
        results = (pyalex.Works()
                   .filter(authorships={"author": {"id": oa_id_clean}})
                   .paginate(per_page=per_page))
        pages_fetched = 0
        for page_data in results:
            pages_fetched += 1
            for w in page_data:
                doi = w.get('doi') or w.get('id') or ''
                doi_clean = (str(doi)
                             .replace('https://doi.org/', '')
                             .replace('http://doi.org/', '')
                             .strip('/'))
                if doi_clean and doi_clean not in metadatos:
                    try:
                        from ingestion import openalex_utils as _self
                        abstract = _self._deconstruct_abstract(
                            w.get('abstract_inverted_index'))
                    except Exception:
                        abstract = None
                    metadatos[doi_clean] = {
                        'Title':        w.get('title', 'Sin Título'),
                        'Year':         w.get('publication_year', 0),
                        'DOI':          doi_clean,
                        'Source':       'OpenAlex_AuthorID_Oficial',
                        'Authors':      None,
                        'Cited_by':     w.get('cited_by_count', 0),
                        'Abstract':     abstract,
                        'openalex_url': w.get('id'),
                        '_raw_oa':      w,
                    }
        if metadatos:
            print(f"    [OpenAlex Oficial] Author {oa_id_clean}: "
                  f"{len(metadatos)} trabajos ({pages_fetched} página(s)).")
    except Exception as e:
        print(f"    [WARN] Error API Oficial OpenAlex Author ({oa_id_clean}): {e}")

    return metadatos


def _deconstruct_abstract(inv: dict) -> str | None:
    """Reconstruye el abstract desde el índice invertido de OpenAlex."""
    if not inv:
        return None
    try:
        length = max(pos for positions in inv.values() for pos in positions) + 1
        words  = [''] * length
        for word, positions in inv.items():
            for pos in positions:
                words[pos] = word
        return ' '.join(w for w in words if w)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────
# resolve_author_oa_id: Resuelve OpenAlex Author IDs activamente
# buscando por ORCID o Scopus en ClickHouse y pyalex (fallback).
# Devuelve LISTA con todos los IDs únicos encontrados.
# ─────────────────────────────────────────────────────────────────
def resolve_author_oa_id(
    orcid: str = None,
    scopus_ids=None,
    force_local: bool = False,
    force_scopus: bool = False,
) -> list:
    """
    Busca todos los OpenAlex Author IDs a partir de ORCID o Scopus IDs.

    Orden:
      1. ORCID  -> SELECT DISTINCT id FROM authors WHERE orcid = ? (ClickHouse)
      2. Scopus -> JSONExtractString(raw_data, 'ids', 'scopus') = ? (ClickHouse)
      3. pyalex (API oficial) -- solo si force_local=False

    Returns:
        list de IDs de autor unicos. Lista vacia si no se encuentra nada.
    """
    found: list = []

    def _is_author_id(oa_id: str) -> bool:
        clean = str(oa_id).split("/")[-1]
        return clean.startswith("A") and clean[1:].isdigit()

    orcid_clean = None
    orcid_url   = None
    if orcid:
        raw = str(orcid).strip()
        if "orcid.org/" in raw:
            orcid_url   = raw if raw.startswith("https://") else "https://orcid.org/" + raw.split("orcid.org/")[-1]
            orcid_clean = raw.split("orcid.org/")[-1]
        else:
            orcid_clean = raw
            orcid_url   = "https://orcid.org/" + raw

    if scopus_ids is None:
        scopus_ids = []
    elif isinstance(scopus_ids, str):
        scopus_ids = [s.strip() for s in scopus_ids.replace(";", ",").split(",") if s.strip()]

    try:
        from database.clickhouse_db import ch_client
        ch = ch_client.get_client()

        if orcid_url or orcid_clean:
            for orcid_val in filter(None, [orcid_url, orcid_clean]):
                rows = ch.query(
                    "SELECT DISTINCT id FROM authors WHERE orcid = {o:String}",
                    parameters={"o": orcid_val}
                ).result_rows
                for r in rows:
                    if r[0] and _is_author_id(r[0]) and r[0] not in found:
                        found.append(r[0])
                if found:
                    break

        if found and not force_scopus:
            pass  # Se salta el escaneo de Scopus en ClickHouse porque es muy costoso y ya resolvimos por ORCID
        else:
            for sid in scopus_ids:
                sid_str = str(sid).strip()
                if not sid_str:
                    continue
                rows = ch.query(
                    "SELECT DISTINCT id FROM authors WHERE JSONExtractString(raw_data, 'ids', 'scopus') = {s:String}",
                    parameters={"s": sid_str}
                ).result_rows
                for r in rows:
                    if r[0] and _is_author_id(r[0]) and r[0] not in found:
                        found.append(r[0])

    except Exception as e:
        print(f"      [resolve_author_oa_id] ClickHouse error: {e}")

    if found:
        if len(found) > 1:
            print(f"      [resolve_author_oa_id] {len(found)} perfiles OA: {found}")
        return found

    if force_local:
        return []

    try:
        import pyalex
        if orcid_clean:
            results = pyalex.Authors().filter(orcid=orcid_clean).get()
            for r in results:
                oa_id = r.get("id")
                if oa_id and _is_author_id(oa_id) and oa_id not in found:
                    found.append(oa_id)
        for sid in scopus_ids:
            results = pyalex.Authors().filter(ids={"scopus": str(sid).strip()}).get()
            for r in results:
                oa_id = r.get("id")
                if oa_id and _is_author_id(oa_id) and oa_id not in found:
                    found.append(oa_id)
    except Exception as e:
        print(f"      [resolve_author_oa_id] pyalex error: {e}")

    return found
