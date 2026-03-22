"""
ingestion/challenge_neo4j_orcids.py
───────────────────────────────────
Audit de ORCIDs almacenados en Neo4j para académicos.
Utiliza:
1. Neo4j (Grafo de Académicos)
2. ClickHouse (Local ORCID records)
3. DuckDuckGo (Web Search)
4. LLM (Juez final)
"""

import os
import sys
import json
import time
import httpx
import pandas as pd
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Añadir path raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore
from SNII.match_snii_orcid import get_client as get_ch_client, get_orcid_client, CH_DB_ORCID

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
    client = get_orcid_client()
    query = f"""
    SELECT given_names, family_name, credit_name, last_affiliation, last_affiliation_country, emails
    FROM {CH_DB_ORCID}.orcid_records
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
                "emails": r[5]
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

def challenge_with_llm(academic_data, local_data, web_data):
    """Somete el match a juicio del LLM."""
    web_str = "\n".join([f"- {r['title']}: {r['body']}" for r in web_data]) if web_data else "No results."
    
    prompt = f"""Eres un auditor de integridad de datos académicos. Tu misión es RETAR la validez de un match de ORCID almacenado en nuestro grafo de conocimiento.
    
DATOS EN NEO4J (Grafo):
{academic_data}

DATOS EN NUESTRA BASE LOCAL (ORCID {local_data.get('orcid') if local_data else 'N/A'}):
{json.dumps(local_data, indent=2, ensure_ascii=False)}

EVIDENCIA WEB ENCONTRADA:
{web_str}

Instrucciones:
1. Compara si el investigador de nuestro grafo es REALMENTE la persona del perfil de ORCID.
2. Busca discrepancias graves: instituciones contradictorias, trayectorias que no coinciden con el campo de especialidad.
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
    parser = argparse.ArgumentParser(description="Audit Neo4j Academic ORCIDs")
    parser.add_argument("--limit", type=int, help="Límite de académicos a auditar")
    parser.add_argument("--force", action="store_true", help="Auditar incluso los ya procesados (sobrescribe)")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Saltar los que ya tienen veredicto (por defecto)")
    args = parser.parse_args()

    graph = Neo4jGraphStore()
    
    # Lógica de filtrado: si es --force, no filtramos por audit_verdict NULL.
    # Si es --skip-existing (o por defecto), filtramos para procesar solo nuevos.
    do_skip = args.skip_existing and not args.force
    filter_query = "AND a.audit_verdict IS NULL" if do_skip else ""

    query = f"""
    MATCH (a:Academic)
    WHERE a.orcid IS NOT NULL {filter_query}
    RETURN a.name AS name, a.orcid AS orcid, a.siia_url AS siia
    """
    
    with graph.driver.session() as session:
        academics = list(session.run(query))
    
    if args.limit:
        academics = academics[:args.limit]
        
    print(f"🛡️ Iniciando auditoría para {len(academics)} académicos en Neo4j...")

    try:
        for idx, rec in enumerate(academics):
            name = rec["name"]
            orcid = rec["orcid"]
            print(f"\n🧐 Auditando [{idx+1}/{len(academics)}]: {name} ({orcid})...")
            
            # 1. ClickHouse Details
            local_info = get_orcid_details(orcid)
            
            # 2. Web Evidence
            web_info = search_web_evidence(name, orcid)
            
            # 3. LLM Judgment
            academic_info = f"Nombre: {name} | ORCID: {orcid} | SIIA: {rec.get('siia')}"
            judgment = challenge_with_llm(academic_info, local_info, web_info)
            
            if judgment:
                print(f"   ⚖️ Veredicto: {judgment['verdict']} (Confianza: {judgment['confidence']}%)")
                
                # Actualizar Neo4j
                update_query = """
                MATCH (a:Academic {name: $name})
                SET a.audit_verdict = $verdict,
                    a.audit_confidence = $confidence,
                    a.audit_reason = $reason,
                    a.audit_timestamp = $timestamp
                """
                with graph.driver.session() as session:
                    session.run(update_query, 
                        name=name, 
                        verdict=judgment['verdict'],
                        confidence=judgment['confidence'],
                        reason=judgment['reason'],
                        timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
                    )
                print(f"   ✅ Nodo actualizado en Neo4j.")
            
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n🛑 Auditoría interrumpida.")
    finally:
        graph.close()
        print(f"\n✨ Proceso de auditoría Neo4j finalizado.")

if __name__ == "__main__":
    main()
