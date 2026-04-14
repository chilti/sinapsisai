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
    
    # Variante original limpia
    clean_original = full_name.replace(',', ' ').strip()
    variants.append(clean_original)
    
    # Manejar formato "SURNAMES, NAME"
    if ',' in full_name:
        parts = full_name.split(',')
        surnames = parts[0].strip()
        names = parts[1].strip()
        
        # Variante: "Name Surnames" (muy común en OpenAlex)
        variants.append(f"{names} {surnames}")
        
        # Variante: "Name Surnames-con-guion" (formato internacional común)
        # Solo si surnames tiene espacios (más de un apellido)
        if ' ' in surnames:
            hyphenated_surnames = surnames.replace(' ', '-')
            variants.append(f"{names} {hyphenated_surnames}")
            
    # Eliminar duplicados manteniendo orden
    return list(dict.fromkeys(variants))

def filter_by_recent_affiliation(author_data, start_year=2021, end_year=2025):
    """Verifica actividad reciente y retorna mejor institución."""
    # Soportar tanto dict (API Local) como Author object (Pyalex)
    affiliations = author_data.get('affiliations', [])
    
    # Algunos resultados de Pyalex vienen con estructuras ligeramente diferentes
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
                # API Local usa display_name dentro de institution
                inst_obj = aff.get('institution', {})
                best_inst = inst_obj.get('display_name', '') if isinstance(inst_obj, dict) else str(inst_obj)
                
    return recent_match, best_inst, sorted(list(set(all_years)))

def map_pyalex_author(author):
    """Convierte un objeto Author de Pyalex al formato interno de candidatos."""
    # Intentar obtener institución reciente
    is_recent, recent_inst, active_years = filter_by_recent_affiliation(author)
    
    return {
        "name": author.get('display_name'),
        "openalex_id": author.get('id'),
        "institution": recent_inst or author.get('last_known_institution', {}).get('display_name', 'Unknown'),
        "years": active_years[-5:] if active_years else []
    }

def search_authors_local(name):
    """Consulta autores en la API local de OpenAlex."""
    search_query = name.replace(',', ' ')
    url = f"{LOCAL_API}/authors"
    params = {"search": search_query, "per_page": 5}
    try:
        with httpx.Client(verify=False, timeout=15) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json().get('results', [])
    except Exception:
        pass
    return []

def search_authors_official(name):
    """Consulta autores en la API Oficial de OpenAlex usando Pyalex."""
    try:
        # Usamos search para mayor flexibilidad
        results = pyalex.Authors().search(name).limit(5).get()
        return [map_pyalex_author(a) for a in results]
    except Exception as e:
        print(f"      [WARN] Error en API Oficial: {e}")
    return []

def challenge_openalex_id_with_llm(snii_info, candidates):
    """Somete los candidatos de OpenAlex a juicio del LLM."""
    from langchain_core.messages import HumanMessage
    if not candidates: return None
    
    candidates_str = ""
    for i, c in enumerate(candidates):
        candidates_str += f"{i+1}. Nombre: {c['name']} | ID: {c['openalex_id']} | Inst: {c['institution']} | Años Activos: {c['years']}\n"
        
    prompt = f"""Eres un experto en bibliometría académica. Tu tarea es identificar si alguno de los candidatos de OpenAlex coincide con el investigador del SNII.
    
INVESTIGADOR SNII BUSCADO:
{snii_info}

CANDIDATOS ENCONTRADOS EN OPENALEX:
{candidates_str}

Instrucciones:
1. Prioriza autores con actividad reciente (2021-2025) y coincidencia institucional.
2. Analiza variaciones de nombre (apellidos invertidos, nombres omitidos).
3. Responde estrictamente en JSON plano con este formato:
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
            print(f"      [CRITICAL] Error de conexión LLM: {ce}")
            if wait_for_llm_recovery(client_llm):
                try:
                    return perform_invoke()
                except Exception as e2:
                    print(f"      [ERROR] Error tras recuperación: {e2}")
            return None

def run_openalex_matching(limit=50, min_score=0.75):
    """Proceso principal de matching con múltiples estrategias de búsqueda."""
    print(f"[INFO] Iniciando Enriquecimiento de OpenAlex IDs (Estrategia Robusta)...")
    
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

    count = 0
    for entry in to_process:
        if count >= limit: break
        
        snii_name = entry['snii_author']
        inst = entry.get('snii_institution', '')
        sub = entry.get('snii_subdependency', '')
        snii_info = f"Nombre: {snii_name} | Institución: {inst} | Subdependencia: {sub}"
        snii_sorted = get_token_sorted_name(snii_name)
        
        print(f"\n[CHECK] [{count+1}/{limit}] Procesando: {snii_name}")
        
        # 1. Generar variantes de búsqueda
        search_variants = generate_search_variants(snii_name)
        
        raw_candidates = []
        found_source = None
        
        # 2. Estrategia A: API Local con variantes
        for variant in search_variants:
            print(f"   -> Buscando variante local: '{variant}'...")
            local_results = search_authors_local(variant)
            if local_results:
                raw_candidates = local_results
                found_source = "Local"
                break
        
        # 3. Estrategia B: API Oficial Fallback (si local no devolvió nada)
        if not raw_candidates:
            print(f"   [!] Local falló. Intentando API Oficial con variantes...")
            for variant in search_variants:
                print(f"      -> Buscando variante oficial: '{variant}'...")
                official_results = search_authors_official(variant)
                if official_results:
                    raw_candidates = official_results
                    found_source = "Official"
                    break
                    
        # 4. Filtrar y puntuar candidatos encontrados
        potential_candidates = []
        if raw_candidates:
            for cand in raw_candidates:
                cand_name = cand.get('name') or cand.get('display_name')
                # Normalizar si viene de API Local (dict) o de Official (ya normalizado parcialmente)
                is_recent, recent_inst, active_years = filter_by_recent_affiliation(cand)
                cand_sorted = get_token_sorted_name(cand_name)
                score = jaro_winkler(snii_sorted, cand_sorted)
                
                print(f"      - [{found_source}] Candidato: {cand_name[:30]}... | Score: {score:.3f}")
                
                if score >= min_score:
                    potential_candidates.append({
                        "name": cand_name,
                        "openalex_id": cand.get('id') or cand.get('openalex_id'),
                        "institution": recent_inst or cand.get('last_known_institution', {}).get('display_name', 'Unknown'),
                        "years": active_years[-5:] if active_years else [],
                        "score": score
                    })

        # 5. Juicio del LLM
        if potential_candidates:
            print(f"   -> {len(potential_candidates)} potenciales. Juicio LLM... {potential_candidates}")
            judgment = challenge_openalex_id_with_llm(snii_info, potential_candidates)
            
            if judgment and judgment.get('match'):
                idx = judgment['candidate_index']
                if idx and 1 <= idx <= len(potential_candidates):
                    match_data = potential_candidates[idx-1]
                    print(f"   [OK] VALIDADO: {match_data['openalex_id']} ({match_data['name']})")
                    entry["matched_openalex_id"] = match_data['openalex_id']
                    entry["oa_audit"] = {
                        "reason": judgment.get('reason'),
                        "source": found_source,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                else:
                    print("   [FAIL] LLM devolvió índice inválido.")
            else:
                reason = judgment.get('reason') if judgment else 'Descartado'
                print(f"   [FAIL] Descartado. Razón: {reason}")
                entry["matched_openalex_id"] = False 
        else:
            print(f"   [FAIL] Sin candidatos válidos tras todas las variantes.")
            
        count += 1
        
        # Guardado atómico
        if count % 5 == 0:
            temp_path = OUTPUT_PATH + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, OUTPUT_PATH)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n[DONE] Enriquecimiento completado.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich SNII JSON with OpenAlex IDs using Robust Logic")
    parser.add_argument("--limit", type=int, default=10, help="Límite de registros")
    args = parser.parse_args()
    run_openalex_matching(limit=args.limit)
