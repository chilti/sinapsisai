"""
SNII/challenge_orcid_validity.py
────────────────────────────────
Audit de ORCIDs encontrados para investigadores SNII.
Utiliza:
1. ClickHouse (Local ORCID records)
2. DuckDuckGo (Web Search)
3. LLM (Juez final)
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
from SNII.match_snii_orcid import get_client as get_ch_client

# Cargar .env
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

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

def get_orcid_details(orcid):
    """Obtiene detalles del ORCID desde ClickHouse."""
    client = get_ch_client()
    query = f"""
    SELECT given_names, family_name, credit_name, last_affiliation, last_affiliation_country, other_names, biography
    FROM openalex.orcid_records
    WHERE orcid = '{orcid}'
    """
    try:
        res = client.query(query).result_rows
        if res:
            r = res[0]
            return {
                "names": f"{r[0]} {r[1]}".strip(),
                "credit_name": r[2],
                "affiliation": r[3],
                "country": r[4],
                "other_names": r[5],
                "biography": r[6]
            }
    except Exception as e:
        print(f"      ⚠️ Error en ClickHouse para {orcid}: {e}")
    return None

def search_web_evidence(name, orcid):
    """Busca evidencia en la web para el investigador y su ORCID."""
    query = f"{name} orcid {orcid}"
    results = []
    try:
        with DDGS() as ddgs:
            ddg_gen = ddgs.text(query, max_results=3)
            for r in ddg_gen:
                results.append(r)
    except Exception as e:
        print(f"      ⚠️ Error en DDG: {e}")
    return results

def challenge_with_llm(snii_data, local_data, web_data):
    """Somete el match a juicio del LLM."""
    web_str = "\n".join([f"- {r['title']}: {r['body']}" for r in web_data]) if web_data else "No results."
    
    prompt = f"""Eres un auditor de integridad de datos académicos. Tu misión es RETAR la validez de un match de ORCID.
    
DATOS DEL SNII (Origen):
{snii_data}

DATOS EN NUESTRA BASE LOCAL (ORCID {local_data.get('orcid') if local_data else 'N/A'}):
{json.dumps(local_data, indent=2, ensure_ascii=False)}

EVIDENCIA WEB ENCONTRADA:
{web_str}

Instrucciones:
1. Compara si el investigador del SNII es REALMENTE la persona del perfil de ORCID.
2. Busca discrepancias graves: instituciones en países diferentes sin relación aparente, nombres que coinciden solo parcialmente pero tienen trayectorias distintas.
3. Determina si el match es SEGURO, DUDOSO o un FALSO POSITIVO.
4. Formato de respuesta: JSON plano con las llaves: "verdict" ("CONFIRMED", "DOUBTFUL", "FALSE_POSITIVE"), "confidence" (0-100), "reason" (explicación detallada).

Respuesta:"""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        res_text = response.content.strip()
        if "```json" in res_text:
            res_text = res_text.split("```json")[1].split("```")[0].strip()
        return json.loads(res_text)
    except Exception as e:
        print(f"      ⚠️ Error en LLM Challenge: {e}")
        return None

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Challenge ORCID Validity")
    parser.add_argument("--limit", type=int, help="Límite de auditorías")
    args = parser.parse_args()

    matches_path = os.path.join("data", "snii_llm_verified_matches.json")
    
    if not os.path.exists(matches_path):
        print(f"❌ No se encontró el archivo de matches en {matches_path}")
        return

    with open(matches_path, 'r', encoding='utf-8') as f:
        matches = json.load(f)

    # Identificar candidatos a auditar (los que tienen match: True y no han sido auditados)
    to_audit = [m for m in matches if m.get('match') and not m.get('audit')]
    
    if args.limit:
        to_audit = to_audit[:args.limit]

    if not to_audit:
        print("✅ No hay nuevos matches para auditar o todos ya están procesados.")
        return

    print(f"🛡️ Iniciando auditoría (Challenge) para {len(to_audit)} investigadores...")

    try:
        for m in to_audit:
            name = m['snii_author']
            orcid = m['matched_orcid']
            print(f"\n🧐 Auditando: {name} ({orcid})...")
            
            # 1. ClickHouse Details
            local_info = get_orcid_details(orcid)
            
            # 2. Web Evidence
            web_info = search_web_evidence(name, orcid)
            
            # 3. LLM Judgment
            snii_info = f"Nombre: {name} | Institución: {m.get('snii_institution')} | Subdependencia: {m.get('snii_subdependency')}"
            judgment = challenge_with_llm(snii_info, local_info, web_info)
            
            if judgment:
                print(f"   ⚖️ Veredicto: {judgment['verdict']} (Confianza: {judgment['confidence']}%)")
                
                # ANOTAR en el objeto original
                m["audit"] = {
                    "verdict": judgment['verdict'],
                    "confidence": judgment['confidence'],
                    "reason": judgment['reason'],
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                
                # Guardado incremental en el archivo original
                with open(matches_path, "w", encoding="utf-8") as f:
                    json.dump(matches, f, ensure_ascii=False, indent=2)
            
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n🛑 Auditoría interrumpida.")
    finally:
        print(f"\n✨ Proceso terminado. Archivo '{matches_path}' actualizado con anotaciones de auditoría.")

if __name__ == "__main__":
    main()
