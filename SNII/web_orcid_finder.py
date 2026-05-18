"""
SNII/web_orcid_finder.py
────────────────────────
Buscador web de ORCIDs para investigadores SNII mediante DuckDuckGo.
Usa LLM (vía LM Studio) para validar la relación entre el investigador y el perfil hallado.
"""

import os
import sys
import json
import time
import pandas as pd
import httpx
from duckduckgo_search import DDGS
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Añadir path raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from scripts.tools.match_snii_orcid import SNII_PATH, normalize_text

# Cargar .env
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

# --- Config LLM (Sincronizado con vectorize_researchers.py) ---
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
if not base_url.endswith("/"): 
    base_url += "/"

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

def search_web_orcid(name, institution):
    """Realiza búsqueda en DuckDuckGo y devuelve los resultados relevantes."""
    query = f"{name} {institution} orcid.org"
    results = []
    try:
        with DDGS() as ddgs:
            # Buscamos los primeros 5 resultados
            ddg_gen = ddgs.text(query, max_results=5)
            for r in ddg_gen:
                results.append(r)
    except Exception as e:
        print(f"      ⚠️ Error en búsqueda DDG: {e}")
    return results

def verify_with_llm(snii_info, search_results):
    """Envía los candidatos al LLM para validación."""
    if not search_results: return None
    
    candidates_str = ""
    for i, res in enumerate(search_results):
        candidates_str += f"{i+1}. Título: {res['title']}\n   Snippet: {res['body']}\n   Link: {res['href']}\n\n"
        
    prompt = f"""Eres un experto investigador bibliográfico. Tu tarea es identificar si alguno de los resultados de búsqueda web coincide con el investigador del SNII.
    
Investigador SNII buscado:
{snii_info}

Candidatos encontrados en la web:
{candidates_str}

Instrucciones:
1. Analiza el nombre y la afiliación mencionada en los snippets o títulos de los resultados.
2. Identifica si alguno contiene un link de ORCID (orcid.org/XXXX-XXXX-XXXX-XXXX) que pertenezca al investigador.
3. Si hay una coincidencia clara, responde con el ORCID y el link.
4. Si ninguno coincide con seguridad, responde 'NINGUNO'.
5. Formato de respuesta: JSON plano con las llaves: "match" (bool), "orcid" (str o null), "link" (str o null), "reason" (str breve).

Respuesta:"""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        res_text = response.content.strip()
        # Limpiar posibles bloques de código
        if "```json" in res_text:
            res_text = res_text.split("```json")[1].split("```")[0].strip()
        
        return json.loads(res_text)
    except Exception as e:
        print(f"      ⚠️ Error consultando LLM: {e}")
        return None

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Buscador Web de ORCID")
    parser.add_argument("--limit", type=int, help="Límite de investigadores a procesar")
    args = parser.parse_args()

    # 1. Cargar Investigadores
    if not os.path.exists(SNII_PATH):
        print(f"❌ No se encontró el Excel del SNII en {SNII_PATH}")
        return
        
    print(f"📋 Cargando SNII desde {SNII_PATH}...")
    df = pd.read_excel(SNII_PATH)
    
    # 2. Cargar Matches Previos (para saltar los ya encontrados)
    matches_json_path = os.path.join("data", "snii_llm_verified_matches.json")
    already_found = set()
    if os.path.exists(matches_json_path):
        print(f"📂 Cargando matches previos desde {matches_json_path}...")
        with open(matches_json_path, 'r', encoding='utf-8') as f:
            prev_data = json.load(f)
            for entry in prev_data:
                # Saltamos si hubo match o si ya se procesó (incluso como fallo) para no duplicar
                if entry.get('match') or entry.get('matched_orcid'):
                    already_found.add(entry.get('snii_author'))
    else:
        print("💡 No se encontró el archivo de matches previos. Se procesará toda la lista.")

    # 3. Cargar (o crear) el tracker de búsqueda web
    web_matches_path = os.path.join("data", "snii_web_search_results.json")
    web_results = []
    if os.path.exists(web_matches_path):
        with open(web_matches_path, 'r', encoding='utf-8') as f:
            web_results = json.load(f)
    
    web_processed_names = {r['snii_author'] for r in web_results}
    
    name_col = 'NOMBRE DEL INVESTIGADOR'
    inst_col = 'INSTITUCIÓN DE ACREDITACIÓN'
    sub_inst_col = 'SUBDEPENDENCIA DE ACREDITACIÓN'
    
    # Filtrar solo los que NO están en ninguna lista
    mask = (~df[name_col].isin(already_found)) & (~df[name_col].isin(web_processed_names))
    pending_df = df[mask].copy()
    
    if args.limit:
        pending_df = pending_df.head(args.limit)
        
    print(f"🔎 Investigadores pendientes de búsqueda web: {len(pending_df)}")

    if pending_df.empty:
        print("✅ No hay investigadores pendientes de procesamiento web.")
        return

    try:
        for idx, row in pending_df.iterrows():
            name = str(row[name_col])
            inst = str(row[inst_col]) if pd.notna(row[inst_col]) else ""
            sub = str(row[sub_inst_col]) if pd.notna(row[sub_inst_col]) else ""
            
            snii_info = f"Nombre: {name} | Institución: {inst} | Subdependencia: {sub}"
            
            print(f"\n🚀 Procesando [{idx+1}/{len(pending_df)}]: {name}...")
            
            # Búsqueda
            results = search_web_orcid(name, f"{inst} {sub}")
            
            result_entry = {
                "snii_author": name,
                "snii_institution": inst,
                "snii_subdependency": sub,
                "match": False,
                "matched_orcid": None,
                "link": None,
                "reason": "No web results found",
                "source": "Web Search (DDG)"
            }

            if results:
                # Validación LLM
                match_data = verify_with_llm(snii_info, results)
                if match_data and match_data.get('match'):
                    print(f"   ✅ MATCH WEB: {match_data.get('orcid')} - {name}")
                    result_entry.update({
                        "match": True,
                        "matched_orcid": match_data.get('orcid'),
                        "link": match_data.get('link'),
                        "reason": match_data.get('reason')
                    })
                else:
                    reason = match_data.get('reason') if match_data else "LLM validation failed"
                    print(f"   ❌ No validado: {reason}")
                    result_entry["reason"] = reason
            
            web_results.append(result_entry)
            
            # Guardado incremental
            with open(web_matches_path, "w", encoding="utf-8") as f:
                json.dump(web_results, f, ensure_ascii=False, indent=2)
                
            time.sleep(2) # Pausa por cortesía

    except KeyboardInterrupt:
        print("\n🛑 Proceso interrumpido por el usuario. Guardando progreso...")
    finally:
        with open(web_matches_path, "w", encoding="utf-8") as f:
            json.dump(web_results, f, ensure_ascii=False, indent=2)
        print(f"\n✨ Resultados parciales guardados en {web_matches_path}")

if __name__ == "__main__":
    main()
