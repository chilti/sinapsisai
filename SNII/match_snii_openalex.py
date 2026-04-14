import os
import sys
import json
import time
import httpx
import pandas as pd
import pyalex
from Levenshtein import jaro_winkler
from dotenv import load_dotenv

# Añadir path raíz para importaciones
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from SNII.match_snii_orcid import normalize_text, load_snii_authors
from lib.llm_utils import get_chat_model, handle_llm_exception, wait_for_llm_recovery

# Cargar configuración
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

LOCAL_API = os.getenv("OPENALEX_LOCAL_API", "http://localhost:5012")
OUTPUT_PATH = os.path.join("data", "snii_llm_verified_matches.json")

# Configurar Pyalex para la API oficial (Polite Pool)
pyalex.config.email = os.getenv("EMAIL_ADDRESS", "sin_correo@ciencias.unam.mx")

# --- Inicialización Centralizada del LLM ---
llm = get_chat_model(temperature=0)
from lib.llm_utils import get_openai_client
client_llm = get_openai_client()

def get_token_sorted_name(name_str):
    """Normaliza, elimina guiones y ordena tokens del nombre."""
    clean = normalize_text(name_str).replace(',', ' ').replace('-', ' ')
    tokens = sorted([t for t in clean.split() if len(t) > 1])
    return " ".join(tokens)

def generate_search_variants(full_name):
    """Genera variantes de búsqueda para maximizar el hit en el índice de OpenAlex."""
    variants = []
    clean_original = full_name.replace(',', ' ').strip()
    variants.append(clean_original)
    
    if ',' in full_name:
        parts = full_name.split(',')
        surnames = parts[0].strip()
        names_str = parts[1].strip()
        name_tokens = [t.strip() for t in names_str.split() if len(t.strip()) > 1 or t.endswith('.')]
        
        variants.append(f"{names_str} {surnames}")
        if len(name_tokens) > 1:
            for token in name_tokens:
                variants.append(f"{token} {surnames}")
                
        if ' ' in surnames:
            hyphenated_surnames = surnames.replace(' ', '-')
            variants.append(f"{names_str} {hyphenated_surnames}")
            if len(name_tokens) > 1:
                for token in name_tokens:
                    variants.append(f"{token} {hyphenated_surnames}")
        
        variants.append(surnames)
        if ' ' in surnames:
            variants.append(surnames.replace(' ', '-'))
            
    return list(dict.fromkeys(variants))

def filter_by_recent_affiliation(author_data, start_year=2018, end_year=2025):
    """Verifica actividad reciente y retorna mejor institución."""
    # Soportar dict (API Local) o Author object (Pyalex)
    affiliations = author_data.get('affiliations', [])
    sorted_affs = sorted(affiliations, key=lambda x: max(x.get('years', [0])) if x.get('years') else 0, reverse=True)
    
    recent_match = False
    best_inst = ""
    all_years = []
    
    for aff in sorted_affs:
        years = aff.get('years', [])
        all_years.extend(years)
        if any(start_year <= y <= end_year for y in years):
            recent_match = True
            if not best_inst:
                inst_obj = aff.get('institution', {})
                best_inst = inst_obj.get('display_name', '') if isinstance(inst_obj, dict) else str(inst_obj)
                
    return recent_match, best_inst, sorted(list(set(all_years)))

def clean_orcid(orcid_str):
    """Limpia el ORCID para dejar solo el ID de 19 caracteres."""
    if not orcid_str: return None
    return orcid_str.split('/')[-1].strip()

def map_author_data(author, source="Unknown"):
    """Mapea datos de autor de cualquier fuente al formato interno, incluyendo ORCID."""
    is_recent, recent_inst, active_years = filter_by_recent_affiliation(author)
    
    # Extraer ORCID de la fuente (OpenAlex suele devolverlo como URL completa)
    raw_orcid = author.get('orcid')
    if not raw_orcid and 'ids' in author:
        raw_orcid = author['ids'].get('orcid')
        
    return {
        "name": author.get('display_name') or author.get('name'),
        "openalex_id": author.get('id') or author.get('openalex_id'),
        "orcid": clean_orcid(raw_orcid),
        "institution": recent_inst or author.get('last_known_institution', {}).get('display_name', 'Unknown'),
        "years": active_years[-5:] if active_years else [],
        "found_source": source
    }

def search_author_by_orcid_local(orcid):
    """Busca un autor por su ORCID en la API Local."""
    url = f"{LOCAL_API}/authors"
    params = {"filter": f"orcid:{orcid}"}
    try:
        with httpx.Client(verify=False, timeout=15) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                results = resp.json().get('results', [])
                return [map_author_data(r, "LocalORCID") for r in results]
    except Exception:
        pass
    return []

def search_author_by_orcid_official(orcid):
    """Busca un autor por su ORCID en la API Oficial."""
    try:
        results = pyalex.Authors().filter(orcid=orcid).get()
        return [map_author_data(r, "OfficialORCID") for r in results]
    except Exception as e:
        print(f"      [WARN] Error en búsqueda ORCID Oficial: {e}")
    return []

def search_authors_local(name):
    """Búsqueda por nombre en API Local."""
    search_query = name.replace(',', ' ')
    url = f"{LOCAL_API}/authors"
    params = {"search": search_query, "per_page": 5}
    try:
        with httpx.Client(verify=False, timeout=15) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                results = resp.json().get('results', [])
                return [map_author_data(r, "LocalName") for r in results]
    except Exception:
        pass
    return []

def search_authors_official(name):
    """Búsqueda por nombre en API Oficial."""
    try:
        results = pyalex.Authors().search(name).get(per_page=5)
        return [map_author_data(r, "OfficialName") for r in results]
    except Exception as e:
        print(f"      [WARN] Error en API Oficial: {e}")
    return []

def challenge_openalex_id_with_llm(snii_info, candidates):
    """Somete los candidatos a juicio del LLM."""
    from langchain_core.messages import HumanMessage
    if not candidates: return None
    
    candidates_str = ""
    for i, c in enumerate(candidates):
        candidates_str += f"{i+1}. Nombre: {c['name']} | ID: {c['openalex_id']} | ORCID: {c.get('orcid')} | Inst: {c['institution']} | Años Activos: {c['years']}\n"
        
    prompt = f"""Eres un experto en bibliometría académica. Tu tarea es identificar si alguno de los candidatos de OpenAlex coincide con el investigador del SNII.
    
INVESTIGADOR SNII BUSCADO:
{snii_info}

CANDIDATOS ENCONTRADOS EN OPENALEX:
{candidates_str}

Instrucciones:
1. Valida como MATCH si el nombre coincide plenamente y la institución es la misma (o muy similar), incluso si la actividad reciente es escasa.
2. Si un candidato tiene el MISMO ORCID que el buscado (si se proporciona), es un match casi seguro.
3. Considera actividad relevante a partir de 2018 en adelante.
4. Analiza variaciones de nombre (apellidos invertidos, nombres omitidos).
5. Responde estrictamente en JSON plano con este formato:
{{
    "match": true/false,
    "candidate_index": int (1-based) o null,
    "reason": "justificación breve",
    "discarded_candidates": [
        {{"name": "...", "reason": "..."}}
    ]
}}

Respuesta:"""

    def perform_invoke():
        response = llm.invoke([HumanMessage(content=prompt)])
        res_text = response.content.strip()
        if "```json" in res_text:
            res_text = res_text.split("```json")[1].split("```")[0].strip()
        return json.loads(res_text)

    try:
        return perform_invoke()
    except Exception as e:
        try:
            handle_llm_exception(e)
            print(f"      [ERROR] Fallo en LLM Judge: {e}")
            return None
        except ConnectionError as ce:
            print(f"      [CRITICAL) Error de conexión LLM: {ce}")
            if wait_for_llm_recovery(client_llm):
                try:
                    return perform_invoke()
                except Exception as e2:
                    print(f"      [ERROR] Error tras recuperación: {e2}")
            return None

# --- Lock global para escritura segura al JSON ---
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

_save_lock = threading.Lock()
_counter_lock = threading.Lock()
_processed_count = 0

def _atomic_save(results):
    """Guardado atómico del JSON con lock."""
    with _save_lock:
        temp_path = OUTPUT_PATH + ".tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, OUTPUT_PATH)

def process_single_entry(entry, total, results, min_score=0.75):
    """Procesa un solo investigador: búsqueda + puntuación + juicio LLM."""
    global _processed_count
    
    snii_name = entry['snii_author']
    inst = entry.get('snii_institution', '')
    sub = entry.get('snii_subdependency', '')
    snii_orcid = clean_orcid(entry.get('matched_orcid'))
    
    snii_info = f"Nombre: {snii_name} | Institución: {inst} | Subdependencia: {sub} | ORCID previo: {snii_orcid or 'N/A'}"
    snii_sorted = get_token_sorted_name(snii_name)
    
    with _counter_lock:
        _processed_count += 1
        current = _processed_count
    
    print(f"\n[CHECK] [{current}/{total}] Procesando: {snii_name}")
    
    candidates_map = {}
    
    # --- PASO 0: Búsqueda por ORCID (Prioridad Máxima) ---
    if snii_orcid:
        print(f"   -> [{snii_name[:20]}] Buscando por ORCID '{snii_orcid}' en Local...")
        orcid_results = search_author_by_orcid_local(snii_orcid)
        if not orcid_results:
            print(f"   -> [{snii_name[:20]}] Buscando por ORCID '{snii_orcid}' en Oficial...")
            orcid_results = search_author_by_orcid_official(snii_orcid)
        
        for cand in orcid_results:
            candidates_map[cand['openalex_id']] = cand
    
    # --- PASO 1: Búsqueda por Variantes de Nombre (Local) ---
    search_variants = generate_search_variants(snii_name)
    for variant in search_variants:
        local_results = search_authors_local(variant)
        for cand in local_results:
            cid = cand['openalex_id']
            if cid not in candidates_map:
                candidates_map[cid] = cand
    
    # --- PASO 2: Fallback API Oficial ---
    if not candidates_map:
        for variant in search_variants:
            official_results = search_authors_official(variant)
            for cand in official_results:
                cid = cand['openalex_id']
                if cid not in candidates_map:
                    candidates_map[cid] = cand
                
    # --- PASO 3: Filtrado y Puntuación ---
    potential_candidates = []
    for cid, cand in candidates_map.items():
        is_recent, recent_inst, active_years = filter_by_recent_affiliation(cand)
        cand_sorted = get_token_sorted_name(cand['name'])
        score = jaro_winkler(snii_sorted, cand_sorted)
        source = cand.get('found_source', 'Unknown')
        
        inst_log = cand.get('institution', 'Unknown')
        id_short = str(cid).split('/')[-1]
        print(f"      - [{source}] {cand['name'][:25]}... | {id_short} | Inst: {inst_log[:30]} | Score: {score:.3f}")
        
        if cand.get('orcid') == snii_orcid or score >= min_score:
            cand['score'] = score
            potential_candidates.append(cand)

    # --- PASO 4: Juicio del LLM ---
    if potential_candidates:
        print(f"   -> [{snii_name[:20]}] {len(potential_candidates)} potenciales. Juicio LLM...")
        judgment = challenge_openalex_id_with_llm(snii_info, potential_candidates)
        
        if judgment and judgment.get('match'):
            idx = judgment['candidate_index']
            if idx and 1 <= idx <= len(potential_candidates):
                match_data = potential_candidates[idx-1]
                print(f"   [OK] [{snii_name[:20]}] VALIDADO: {match_data['openalex_id']} ({match_data['name']})")
                entry["matched_openalex_id"] = match_data['openalex_id']
                
                discov_orcid = match_data.get('orcid')
                if discov_orcid:
                    if not snii_orcid:
                        print(f"   [NEW] [{snii_name[:20]}] ORCID DESCUBIERTO: {discov_orcid}")
                        entry["matched_orcid"] = discov_orcid
                    elif snii_orcid != discov_orcid:
                        print(f"   [WARN] [{snii_name[:20]}] Conflicto ORCID: SNII({snii_orcid}) vs OA({discov_orcid})")
                
                entry["oa_audit"] = {
                    "reason": judgment.get('reason'),
                    "source": match_data.get('found_source'),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            else:
                print(f"   [FAIL] [{snii_name[:20]}] LLM devolvió índice inválido.")
                entry["oa_audit"] = {
                    "reason": "LLM devolvió índice inválido",
                    "source": "LLM",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
        else:
            reason = judgment.get('reason') if judgment else 'Sin respuesta del LLM'
            discarded = judgment.get('discarded_candidates', []) if judgment else []
            print(f"   [FAIL] [{snii_name[:20]}] Descartado. Razón: {reason}")
            entry["matched_openalex_id"] = False
            entry["oa_audit"] = {
                "reason": reason,
                "discarded_candidates": discarded,
                "source": "LLM",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
    else:
        print(f"   [FAIL] [{snii_name[:20]}] Sin candidatos válidos.")
        entry["matched_openalex_id"] = False
        entry["oa_audit"] = {
            "reason": "No se encontraron candidatos en ninguna fuente",
            "source": "Search",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    
    # Guardado periódico thread-safe
    if current % 20 == 0:
        _atomic_save(results)
        print(f"   [SAVE] Progreso guardado ({current}/{total})")
    
    return current

def run_openalex_matching(limit=0, min_score=0.75, workers=4):
    """Proceso principal de matching bidireccional, robusto y paralelo."""
    global _processed_count
    _processed_count = 0
    
    print(f"[INFO] Iniciando Enriquecimiento Bidireccional SNII-OpenAlex ({workers} workers)...")
    
    results = []
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
            results = json.load(f)
    else:
        print(f"[FAIL] No se encontró el archivo central en {OUTPUT_PATH}")
        return

    to_process = [r for r in results if not r.get('matched_openalex_id')]
    print(f"[INFO] Investigadores pendientes: {len(to_process)}")
    if not to_process:
        print("[OK] Todos los registros ya están enriquecidos.")
        return

    if limit > 0:
        to_process = to_process[:limit]
    total = len(to_process)
    print(f"[INFO] Procesando {total} registros con {workers} hilos...")
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(process_single_entry, entry, total, results, min_score): entry
            for entry in to_process
        }
        
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                entry = futures[future]
                print(f"   [ERROR] Excepción procesando {entry.get('snii_author', '?')}: {e}")

    # Guardado final
    _atomic_save(results)
    print(f"\n[DONE] Enriquecimiento bidireccional completado. {total} registros procesados.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich SNII JSON with OpenAlex IDs and ORCID Discovery")
    parser.add_argument("--limit", type=int, default=0, help="Límite de registros (0 = sin límite)")
    parser.add_argument("--workers", type=int, default=4, help="Número de hilos paralelos")
    args = parser.parse_args()
    run_openalex_matching(limit=args.limit, workers=args.workers)

