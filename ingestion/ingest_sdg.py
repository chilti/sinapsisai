import os
import json
import uuid
import sys
import argparse
import time
from dotenv import load_dotenv

# Asegurar que el directorio raíz esté en el path para importar lib.llm_utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.llm_utils import get_openai_client, handle_llm_exception, wait_for_llm_recovery
from database.knowledge_graph import Neo4jGraphStore

load_dotenv()

import httpx
# Cliente compatible con OpenAI para conectar con LM Studio desde la librería central
client = get_openai_client(async_mode=False)
MODELO_A_USAR = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")

neo4j = Neo4jGraphStore()

# --- CONFIGURACIÓN BATCH ---
BATCH_SIZE = 5 # Procesamos de 5 en 5 para mayor estabilidad

# --- SYSTEM PROMPT BATCH ---
SYSTEM_PROMPT_BATCH = """
You are an expert in bibliometrics and sustainability. 
Your task is to analyze a LIST of scientific articles and classify EACH ONE into THE MOST RELEVANT Sustainable Development Goal (SDG).

Rules:
1. Analyze the semantic content of the title and abstract for each article.
2. Identify the SINGLE main Sustainable Development Goal (SDG) for each.
3. If an article has no clear relationship with any SDG, use "null". 
4. Answer EXCLUSIVELY in a valid JSON LIST format.
5. You MUST output the sdg_name in ENGLISH.

Expected JSON response format (a list of objects):
[
  {
    "doi": "original DOI provided",
    "sdg_id": "SDG X",
    "sdg_name": "Official SDG name in English",
    "confidence": "XX%",
    "reasoning": "Brief 1-sentence justification"
  },
  ...
]
"""

def limpiar_json(texto_respuesta):
    """Limpia los bloques de código markdown si el modelo los incluye"""
    texto_respuesta = texto_respuesta.strip()
    if "```json" in texto_respuesta:
        texto_respuesta = texto_respuesta.split("```json")[-1].split("```")[0]
    elif "```" in texto_respuesta:
         texto_respuesta = texto_respuesta.split("```")[-1].split("```")[0]
    return texto_respuesta.strip()
    
def get_sdgs_from_local_api_batch(dois):
    """Consulta la API local de OpenAlex para obtener los ODS de un lote de papers."""
    if not dois:
        return {}
        
    local_api = os.getenv("OPENALEX_LOCAL_API", "http://localhost:5012")
    url = f"{local_api}/works"
    # El filtro DOI soporta el operador | para múltiples valores
    # Limpiar DOIs por si acaso traen la URL completa
    clean_dois = [d.replace("https://doi.org/", "").replace("http://doi.org/", "").strip() for d in dois]
    filter_val = "|".join(clean_dois)
    params = {"filter": f"doi:{filter_val}", "per_page": len(dois)}
    
    results_map = {}
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                for r in results:
                    doi_full = r.get("doi")
                    if not doi_full:
                        continue
                    doi_clean = doi_full.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
                    
                    sdgs = r.get("sustainable_development_goals", [])
                    if sdgs:
                        # Retornamos el de mayor puntuación
                        best_sdg = sorted(sdgs, key=lambda x: x.get('score', 0), reverse=True)[0]
                        sdg_url = best_sdg.get('id', '')
                        sdg_num = sdg_url.split('/')[-1]
                        
                        results_map[doi_clean] = {
                            "sdg_id": f"SDG {sdg_num}",
                            "sdg_name": best_sdg.get('display_name'),
                            "confidence": f"{int(best_sdg.get('score', 0) * 100)}%",
                            "reasoning": "Retrieved from OpenAlex Local API"
                        }
    except Exception as e:
        print(f"  ⚠️ Error consultando API local para lote: {e}")
    
    return results_map

def clasificar_papers_batch(lista_papers):
    """Envía un lote de papers al LLM para clasificación conjunta."""
    if not lista_papers:
        return []
        
    articles_prompt = ""
    for idx, p in enumerate(lista_papers):
        # Limpiamos para no romper el prompt
        t = str(p['title']).replace('"', "'")
        a = str(p['abstract']).replace('"', "'")[:1500]
        articles_prompt += f"\n--- ARTICLE {idx+1} ---\nDOI: {p['doi']}\nTitle: {t}\nAbstract: {a}\n"

    try:
        completion = client.chat.completions.create(
            model=MODELO_A_USAR,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_BATCH},
                {"role": "user", "content": f"Articles to classify:\n{articles_prompt}"}
            ],
            temperature=0.1,
            max_tokens=2500
        )
        
        respuesta_raw = completion.choices[0].message.content
        respuesta_limpia = limpiar_json(respuesta_raw)
        
        try:
            resultados = json.loads(respuesta_limpia)
            if isinstance(resultados, list):
                return resultados
            else:
                print(f"⚠️ El LLM no devolvió una lista JSON. Recomponiendo como lista...")
                return [resultados]
        except json.JSONDecodeError:
            print(f"⚠️ Error decodificando el JSON batch del LLM.")
            # Si falla el JSON, devolvemos lista vacía para que no se marquen como procesados
            return []
            
    except Exception as e:
        # Usar el manejador centralizado para detectar caídas del servidor
        handle_llm_exception(e)
        raise e # Re-lanzamos para que lo atrape el bucle de recuperación


def fetch_unclassified_papers(entity_filter=None, academic_filter=None, force=False):
    """Obtiene los papers de Neo4j que aún no tienen clasificación SDG."""
    where_clause = "WITH p WHERE COALESCE(p.sdg_processed, false) = false"
    if force:
        where_clause = "WITH p WHERE p.raw_metadata IS NOT NULL"

    if entity_filter:
        query = f"""
        MATCH (e:Entity {{name: $entity}})
        OPTIONAL MATCH (e)-[:HAS_PAPER]->(p1:Paper)
        OPTIONAL MATCH (e)<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p2:Paper)
        WITH collect(p1) + collect(p2) AS all_p
        UNWIND all_p AS p
        {where_clause}
        RETURN DISTINCT p.doi AS doi, p.title AS title, p.raw_metadata AS metadata, COALESCE(p.sdg_processed, false) AS processed
        """
        params = {"entity": entity_filter}
    elif academic_filter:
        query = f"""
        MATCH (a:Academic {{name: $academic}})-[:AUTHORED]->(p:Paper)
        {where_clause}
        RETURN DISTINCT p.doi AS doi, p.title AS title, p.raw_metadata AS metadata, COALESCE(p.sdg_processed, false) AS processed
        """
        params = {"academic": academic_filter}
    else:
        query = f"""
        MATCH (p:Paper)
        {where_clause}
        RETURN p.doi AS doi, p.title AS title, p.raw_metadata AS metadata, COALESCE(p.sdg_processed, false) AS processed
        """
        params = {}
    
    records = []
    with neo4j.driver.session() as session:
        result = session.run(query, **params)
        for r in result:
            doi = r['doi']
            title = r['title']
            raw_meta = r['metadata']
            abstract = ""
            if raw_meta:
                try:
                    meta = json.loads(raw_meta)
                    Abstract = meta.get('Abstract', '')
                    if Abstract:
                        abstract = Abstract
                except:
                    pass
            records.append({
                'doi': doi, 
                'title': title, 
                'abstract': abstract, 
                'processed': r.get('processed', False)
            })
    return records

def count_unclassified_papers(entity_filter=None, academic_filter=None, force=False):
    """Obtiene el conteo total de papers pendientes."""
    where_clause = "WITH p WHERE COALESCE(p.sdg_processed, false) = false"
    if force:
        where_clause = "WITH p WHERE p.raw_metadata IS NOT NULL"

    if entity_filter:
        query = f"""
        MATCH (e:Entity {{name: $entity}})
        OPTIONAL MATCH (e)-[:HAS_PAPER]->(p1:Paper)
        OPTIONAL MATCH (e)<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p2:Paper)
        WITH collect(p1) + collect(p2) AS all_p
        UNWIND all_p AS p
        {where_clause}
        RETURN count(DISTINCT p) AS total
        """
        params = {"entity": entity_filter}
    elif academic_filter:
        query = f"""
        MATCH (a:Academic {{name: $academic}})-[:AUTHORED]->(p:Paper)
        {where_clause}
        RETURN count(DISTINCT p) AS total
        """
        params = {"academic": academic_filter}
    else:
        query = f"""
        MATCH (p:Paper)
        {where_clause}
        RETURN count(p) AS total
        """
        params = {}
    
    with neo4j.driver.session() as session:
        result = session.run(query, **params)
        return result.single()["total"]

def assign_sdg_to_neo4j(doi, sdg_data):
    """Crea el Nodo SDG y la relación ADDRESSES en Neo4j."""
    sdg_id = str(sdg_data.get('sdg_id', '')).upper().strip()
    reasoning = sdg_data.get('reasoning', '')
    
    if not sdg_id or sdg_id == "NULL" or "X" in sdg_id:
        query_null = "MATCH (p:Paper {doi: $doi}) SET p.sdg_reasoning = $reasoning"
        with neo4j.driver.session() as session:
            session.run(query_null, doi=doi, reasoning=reasoning)
        return
        
    sdg_name = sdg_data.get('sdg_name', '')
    confidence = sdg_data.get('confidence', '')

    query = """
    MATCH (p:Paper {doi: $doi})
    MERGE (s:SDG {id: $sdg_id})
    ON CREATE SET s.name = $sdg_name
    MERGE (p)-[r:ADDRESSES]->(s)
    SET r.confidence = $confidence, r.reasoning = $reasoning
    """
    
    with neo4j.driver.session() as session:
        session.run(query, doi=doi, sdg_id=sdg_id, sdg_name=sdg_name, confidence=confidence, reasoning=reasoning)

def run(entity_filter=None, academic_filter=None, force=False):
    print("Iniciando clasificación ODS...")
    if force:
        print("  -> MODO FORZADO ACTIVADO (Re-procesando clasificados)")
        
    total_total = count_unclassified_papers(entity_filter=entity_filter, academic_filter=academic_filter, force=force)
    print(f"[OK] Se encontraron {total_total} papers para clasificar.")
    
    all_papers = fetch_unclassified_papers(entity_filter=entity_filter, academic_filter=academic_filter, force=force)
    if not all_papers:
        print("No hay papers pendientes por clasificar.")
        return

    papers_to_classify_llm = []
    procesados_api = 0
    API_BATCH_SIZE = 25
    
    print(f"Paso 1: Consultando API Local de OpenAlex (Lotes de {API_BATCH_SIZE})...")
    for i in range(0, len(all_papers), API_BATCH_SIZE):
        batch_papers = all_papers[i:i + API_BATCH_SIZE]
        batch_dois = [p['doi'] for p in batch_papers]
        
        results_api = get_sdgs_from_local_api_batch(batch_dois)
        
        for p in batch_papers:
            doi = p['doi']
            # Normalizar para el matching
            doi_clean = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
            sdg_from_api = results_api.get(doi_clean)
            
            if sdg_from_api:
                assign_sdg_to_neo4j(doi, sdg_from_api)
                # Marco documento como procesado
                query_mark = "MATCH (p:Paper {doi: $doi}) SET p.sdg_processed = true"
                with neo4j.driver.session() as session:
                    session.run(query_mark, doi=doi)
                
                procesados_api += 1
                print(f"  [{procesados_api + len(papers_to_classify_llm)}/{total_total}] {doi} -> ✅ En API Local ({sdg_from_api['sdg_id']})")
            else:
                # REGLA: Si ya tenia SDG y el api local devuelve null, NO recalcular con LLM
                if p.get('processed') is True:
                    print(f"  [{procesados_api + len(papers_to_classify_llm) + 1}/{total_total}] {doi} -> ⏭️  Saltando LLM (Ya tenia SDG y API devolvio null)")
                    # Incrementamos algo para que el conteo de progreso no se desfase visualmente si queremos
                    # pero lo importante es NO añadirlo a papers_to_classify_llm
                else:
                    papers_to_classify_llm.append(p)
            
    print(f"\n[OK] {procesados_api} papers clasificados vía API Local.")
    
    if not papers_to_classify_llm:
        print("Todos los papers fueron clasificados vía API. Fin.")
        return

    print(f"\nPaso 2: Clasificando {len(papers_to_classify_llm)} papers restantes vía LLM (Lotes de {BATCH_SIZE})...")
    procesados_llm = 0
    
    # Procesamos en lotes
    for i in range(0, len(papers_to_classify_llm), BATCH_SIZE):
        lote = papers_to_classify_llm[i:i + BATCH_SIZE]
        
        resultados_batch = []
        try:
            resultados_batch = clasificar_papers_batch(lote)
        except ConnectionError as ce:
            print(f"\n❌ Fallo critico en LLM durante lote: {ce}")
            if wait_for_llm_recovery(client):
                try:
                    resultados_batch = clasificar_papers_batch(lote)
                except Exception as e2:
                    print(f"Error tras recuperacion: {e2}")
                    resultados_batch = []
            else:
                print("❌ Finalizando proceso por falta de respuesta del LLM.")
                break
        except Exception as e:
            print(f"\n⚠️ Error inesperado en el lote: {e}")
            resultados_batch = []

        # Procesamos los resultados que hayamos obtenido del lote
        if resultados_batch:
            res_map = {str(r.get('doi')): r for r in resultados_batch if 'doi' in r}
            
            for p in lote:
                doi = p['doi']
                res = res_map.get(doi)
                
                if res:
                    assign_sdg_to_neo4j(doi, res)
                    query_mark = "MATCH (p:Paper {doi: $doi}) SET p.sdg_processed = true"
                    with neo4j.driver.session() as session:
                        session.run(query_mark, doi=doi)
                    
                    sdg_result = res.get('sdg_id')
                    print(f"  [LLM {procesados_llm+1}/{len(papers_to_classify_llm)}] {doi} -> {sdg_result}")
                else:
                    print(f"  [LLM {procesados_llm+1}/{len(papers_to_classify_llm)}] {doi} -> ❌ No se encontro en el lote LLM")
                
                procesados_llm += 1
        else:
            print(f"❌ El lote que empezaba en {lote[0]['doi']} fallo completamente en LLM.")
            procesados_llm += len(lote)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clasifica papers en ODS usando LLM en modo BATCH.")
    parser.add_argument("--entity", type=str, help="Nombre de la entidad para filtrar")
    parser.add_argument("--academic", type=str, help="Nombre del académico para filtrar")
    parser.add_argument("--force", action="store_true", help="Forzar re-clasificación")
    args = parser.parse_args()
    
    run(entity_filter=args.entity, academic_filter=args.academic, force=args.force)
