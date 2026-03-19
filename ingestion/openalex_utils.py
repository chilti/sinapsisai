import os
import httpx
import time
import json
from dotenv import load_dotenv

# Configuración
LOCAL_OPENALEX_URL = "http://127.0.0.1:5009/works"
OFFICIAL_OPENALEX_URL = "https://api.openalex.org/works"

# Cargar variables de entorno si no están cargadas
load_dotenv()

def _clean_title(t):
    """Limpia el título para comparación exacta."""
    if not t: return ""
    return "".join(c for c in str(t).lower() if c.isalnum())

def get_work(doi=None, title=None, email=None, api_key=None):
    """
    Busca un trabajo en OpenAlex. 
    1. Intenta la API oficial por DOI o búsqueda por título.
    2. Si falla (403, 429, timeout) o no encuentra, intenta la API local.
    """
    email = email or os.getenv("EMAIL_ADDRESS", "sin_correo@ciencias.unam.mx")
    api_key = api_key or os.getenv("OPENALEX_API_KEY")
    
    headers = {"User-Agent": "SinapsisAI/1.0 (mailto:" + email + ")"}
    if api_key:
        headers["api_key"] = api_key

    # 1. Intentar API Oficial (DOI)
    if doi:
        try:
            clean_doi = doi.replace("https://doi.org/", "").strip()
            url = f"{OFFICIAL_OPENALEX_URL}/https://doi.org/{clean_doi}"
            resp = httpx.get(url, headers=headers, timeout=10, follow_redirects=True)
            if resp.status_code == 200:
                print(f"      ✅ [API Oficial] Encontrado por DOI: {doi}")
                return resp.json()
            elif resp.status_code in [403, 429]:
                print(f"      ⚠️  [API Oficial] Bloqueo {resp.status_code}. Pasando a API local...")
                # No retornamos, para intentar la local si hace falta, pero primero intentamos título oficial
            else:
                print(f"      ❌ [API Oficial] DOI no encontrado ({resp.status_code}).")
        except Exception as e:
            print(f"      ⚠️  Error en API Oficial (DOI): {e}")

    # 1b. Intentar API Oficial (Título)
    if title and len(title) > 10:
        try:
            params = {"search": title, "mailto": email}
            resp = httpx.get(OFFICIAL_OPENALEX_URL, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                results = resp.json().get('results', [])
                if results:
                    candidate = results[0]
                    if _clean_title(title) == _clean_title(candidate.get('title')):
                        print(f"      ✅ [API Oficial] Encontrado por Título Exacto.")
                        return candidate
            elif resp.status_code in [403, 429]:
                 print(f"      ⚠️  [API Oficial] Bloqueo de Título {resp.status_code}.")
        except Exception as e:
            print(f"      ⚠️  Error en API Oficial (Título): {e}")

    # 2. Intentar API Local (Fallback)
    try:
        print(f"      🏠 Consultando API Local (127.0.0.1:5009)...")
        if doi:
            clean_doi = doi.replace("https://doi.org/", "").strip()
            # Asumiendo que la API local soporta /works/https://doi.org/... o similar
            # Si no, intentamos por filtro
            url = f"{LOCAL_OPENALEX_URL}/https://doi.org/{clean_doi}"
            resp = httpx.get(url, timeout=5)
            if resp.status_code == 200:
                print(f"      ✅ [API Local] Encontrado por DOI: {doi}")
                return resp.json()
            else:
                # Intentar por filtro si el ID directo no funciona en la local
                resp = httpx.get(LOCAL_OPENALEX_URL, params={"filter": f"doi:https://doi.org/{clean_doi}"}, timeout=5)
                if resp.status_code == 200:
                    results = resp.json().get('results', [])
                    if results:
                        print(f"      ✅ [API Local] Encontrado por DOI (filtro): {doi}")
                        return results[0]

        if title:
            # La API local debería soportar search o filter
            params = {"search": title}
            resp = httpx.get(LOCAL_OPENALEX_URL, params=params, timeout=5)
            if resp.status_code == 200:
                results = resp.json().get('results', [])
                if results:
                    candidate = results[0]
                    # Validación de título exacto opcional pero recomendada
                    if _clean_title(title) == _clean_title(candidate.get('title')):
                        print(f"      ✅ [API Local] Encontrado por Título Exacto.")
                        return candidate
        
    except Exception as e:
        print(f"      ❌ Error en API Local: {e}")

    return None

def get_works_batch(dois, email=None):
    """
    Busca múltiples DOIs. 
    Ideal para ingest_entity_docs que procesa lotes.
    """
    if not dois: return {}
    
    email = email or os.getenv("EMAIL_ADDRESS", "sin_correo@ciencias.unam.mx")
    headers = {"User-Agent": "SinapsisAI/1.0 (mailto:" + email + ")"}
    
    results_dict = {}
    
    # Intentar oficial primero (usando filtro OR que es eficiente)
    try:
        doi_query = "|".join([f"https://doi.org/{d}" for d in dois])
        resp = httpx.get(OFFICIAL_OPENALEX_URL, params={"filter": f"doi:{doi_query}"}, headers=headers, timeout=15)
        if resp.status_code == 200:
            works = resp.json().get('results', [])
            for w in works:
                d_key = w.get('doi', '').replace("https://doi.org/", "").lower()
                if d_key: results_dict[d_key] = w
            
            # Si ya tenemos todos, retornar
            if len(results_dict) >= len(dois):
                return results_dict
    except Exception as e:
        print(f"      ⚠️ Error batch oficial: {e}")

    # Fallback local para los que falten
    missing = [d for d in dois if d.lower() not in results_dict]
    if missing:
        try:
            print(f"      🏠 Batch: Consultando {len(missing)} faltantes en API Local...")
            doi_query = "|".join([f"https://doi.org/{d}" for d in missing])
            resp = httpx.get(LOCAL_OPENALEX_URL, params={"filter": f"doi:{doi_query}"}, timeout=10)
            if resp.status_code == 200:
                works = resp.json().get('results', [])
                for w in works:
                    d_key = w.get('doi', '').replace("https://doi.org/", "").lower()
                    if d_key: results_dict[d_key] = w
        except Exception as e:
             print(f"      ❌ Error batch local: {e}")

    return results_dict
