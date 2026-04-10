import os
import sys
import json
import time
import httpx
import pandas as pd
from Levenshtein import jaro_winkler
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Añadir path raíz para importaciones
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from SNII.match_snii_orcid import normalize_text, load_snii_authors

# Cargar configuración
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

LOCAL_API = os.getenv("OPENALEX_LOCAL_API", "http://localhost:5012")
OUTPUT_PATH = os.path.join("data", "snii_llm_verified_matches.json")

# --- Config LLM ---
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
if not base_url.endswith("/"): base_url += "/"

auth_url = base_url
if user and password:
    if "://" in base_url:
        proto, rest = base_url.split("://", 1)
        auth_url = f"{proto}://{user}:{password}@{rest}"
    else:
        auth_url = f"http://{user}:{password}@{base_url}"

http_client = httpx.Client(verify=False, timeout=120)
llm_model_name = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")

llm = ChatOpenAI(
    model=llm_model_name,
    base_url=auth_url,
    api_key="lm-studio",
    http_client=http_client,
    temperature=0
)

def get_token_sorted_name(name_str):
    """Normaliza y ordena tokens del nombrepara comparación fuzzy."""
    clean = normalize_text(name_str).replace(',', ' ')
    tokens = sorted([t for t in clean.split() if len(t) > 1])
    return " ".join(tokens)

def filter_by_recent_affiliation(author_data, start_year=2021, end_year=2025):
    """
    Verifica si el autor tiene actividad en instituciones entre 2021 y 2025.
    Retorna (bool, last_inst_name, total_years).
    """
    affiliations = author_data.get('affiliations', [])
    sorted_affs = sorted(affiliations, key=lambda x: max(x.get('years', [0])), reverse=True)
    
    recent_match = False
    best_inst = ""
    all_years = []
    
    for aff in sorted_affs:
        years = aff.get('years', [])
        all_years.extend(years)
        if any(start_year <= y <= end_year for y in years):
            recent_match = True
            if not best_inst:
                best_inst = aff.get('institution', {}).get('display_name', '')
                
    return recent_match, best_inst, sorted(list(set(all_years)))

def search_authors_local(name):
    """Consulta autores en la API local de OpenAlex."""
    url = f"{LOCAL_API}/authors"
    params = {"search": name, "per_page": 10}
    try:
        with httpx.Client(verify=False, timeout=30) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json().get('results', [])
    except Exception as e:
        print(f"      ⚠️ Error consultando API Local: {e}")
    return []

def challenge_openalex_id_with_llm(snii_info, candidates):
    """Somete los candidatos de OpenAlex a juicio del LLM."""
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

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        res_text = response.content.strip()
        if "```json" in res_text:
            res_text = res_text.split("```json")[1].split("```")[0].strip()
        return json.loads(res_text)
    except Exception as e:
        print(f"      ⚠️ Error en LLM Judge: {e}")
        return None

def run_openalex_matching(limit=50, min_score=0.75):
    """Proceso principal de matching enriqueciendo el JSON central."""
    print(f"🚀 Iniciando Enriquecimiento de OpenAlex IDs en JSON Central...")
    
    # 1. Cargar JSON Central
    results = []
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
            results = json.load(f)
    else:
        print(f"❌ No se encontró el archivo central en {OUTPUT_PATH}")
        return

    # Crear lookup por nombre para mapear rápido
    lookup = { (r['snii_author'], r.get('snii_institution', ''), r.get('snii_subdependency', '')): i for i, r in enumerate(results) }
    
    # Identificar investigadores que necesitan OpenAlex ID (prioridad los que no lo tienen)
    to_process = [r for r in results if not r.get('matched_openalex_id')]
    
    print(f"   Investigadores sin OpenAlex ID: {len(to_process)}")
    if not to_process:
        print("✅ Todos los registros ya están enriquecidos.")
        return

    count = 0
    for entry in to_process:
        if count >= limit: break
        
        name = entry['snii_author']
        inst = entry.get('snii_institution', '')
        sub = entry.get('snii_subdependency', '')
        snii_info = f"Nombre: {name} | Institución: {inst} | Subdependencia: {sub}"
        
        print(f"\n🧐 [{count+1}/{limit}] Procesando: {name}")
        
        # A. Búsqueda y Filtrado Heurístico
        raw_candidates = search_authors_local(name)
        potential_candidates = []
        snii_sorted = get_token_sorted_name(name)
        
        for cand in raw_candidates:
            cand_name = cand.get('display_name', '')
            is_recent, recent_inst, active_years = filter_by_recent_affiliation(cand)
            score = jaro_winkler(snii_sorted, get_token_sorted_name(cand_name))
            
            if score >= min_score:
                potential_candidates.append({
                    "name": cand_name,
                    "openalex_id": cand.get('id'),
                    "institution": recent_inst or cand.get('last_known_institution', {}).get('display_name', ''),
                    "years": active_years[-5:] if active_years else [],
                    "score": score
                })
        
        # B. Juicio del LLM
        if potential_candidates:
            print(f"   -> {len(potential_candidates)} candidatos potenciales. Consultando al LLM Juez...")
            judgment = challenge_openalex_id_with_llm(snii_info, potential_candidates)
            
            if judgment and judgment.get('match'):
                idx = judgment['candidate_index']
                if idx and 1 <= idx <= len(potential_candidates):
                    match_data = potential_candidates[idx-1]
                    print(f"   ✅ LLM VALIDÓ: {match_data['openalex_id']} ({match_data['name']})")
                    
                    # Actualizar entrada en el JSON original
                    entry["matched_openalex_id"] = match_data['openalex_id']
                    entry["oa_audit"] = {
                        "reason": judgment.get('reason'),
                        "discarded": judgment.get('discarded_candidates'),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                else:
                    print("   ❌ LLM devolvió índice inválido.")
            else:
                print(f"   ❌ LLM descartó los candidatos. Razón: {judgment.get('reason') if judgment else 'Error'}")
                entry["matched_openalex_id"] = False # Marcar para no repetir infinitamente
        else:
            print("   ❌ No se encontraron candidatos con puntaje suficiente en OpenAlex Local.")
            # Opcional: Podríamos marcar como False o dejar vacío para intentar después en remoto
            
        count += 1
        
        # Guardado atómico cada 5
        if count % 5 == 0:
            temp_path = OUTPUT_PATH + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, OUTPUT_PATH)

    # Guardado final
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✨ Enriquecimiento completado. Archivo '{OUTPUT_PATH}' actualizado.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich SNII JSON with OpenAlex IDs using LLM")
    parser.add_argument("--limit", type=int, default=10, help="Límite de registros a enriquecer")
    args = parser.parse_args()
    
    run_openalex_matching(limit=args.limit)
