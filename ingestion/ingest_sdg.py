import os
import json
import uuid
import sys
import argparse
import time
from dotenv import load_dotenv

# Asegurar que el directorio raíz esté en el path para importar lib.llm_utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.llm_utils import get_openai_client, handle_llm_exception
from database.knowledge_graph import Neo4jGraphStore

load_dotenv()

import httpx
# Cliente compatible con OpenAI para conectar con LM Studio desde la librería central
client = get_openai_client(async_mode=False)
MODELO_A_USAR = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")

neo4j = Neo4jGraphStore()

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """
You are an expert in bibliometrics and sustainability. Your task is to analyze the title and abstract of a scientific article and classify it into THE MOST RELEVANT Sustainable Development Goal (SDG) (only one).

Rules:
1. Analyze the semantic content of the title and abstract.
2. Identify the SINGLE main Sustainable Development Goal (SDG).
3. If the article has no clear relationship with any SDG, use "null". Justify the non-assignment in the response using the reasoning field.
4. Answer EXCLUSIVELY in valid JSON format.
5. You MUST output the sdg_name in ENGLISH.

Expected JSON response format:
{
  "sdg_id": "SDG X",
  "sdg_name": "Official SDG name in English",
  "confidence": "XX%",
  "reasoning": "Brief 1-sentence justification"
}
"""

def limpiar_json(texto_respuesta):
    """Limpia los bloques de código markdown si el modelo los incluye"""
    texto_respuesta = texto_respuesta.strip()
    if texto_respuesta.startswith("```json"):
        texto_respuesta = texto_respuesta.replace("```json", "").replace("```", "")
    elif texto_respuesta.startswith("```"):
         texto_respuesta = texto_respuesta.replace("```", "")
    return texto_respuesta.strip()

def clasificar_paper(titulo, abstract):
    texto_a_analizar = f"Title: {titulo}\n\nAbstract: {abstract}"
    
    if not titulo and not abstract:
        return None

    try:
        completion = client.chat.completions.create(
            model=MODELO_A_USAR,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Paper:\n{texto_a_analizar}"}
            ],
            temperature=0.4,
            max_tokens=200
        )
        
        respuesta_raw = completion.choices[0].message.content
        respuesta_limpia = limpiar_json(respuesta_raw)
        try:
            datos_ods = json.loads(respuesta_limpia)
            return datos_ods
        except json.JSONDecodeError:
            print(f"\n⚠️ Error decodificando JSON del LLM para {titulo[:30]}...")
            print(f"   Respuesta RAW: {respuesta_raw[:200]}...")
            return None
        
    except Exception as e:
        # Usar el manejador centralizado para detectar caídas del servidor
        handle_llm_exception(e)
        print(f"\nError procesando paper: {e}")
        return None

def esperar_recuperacion_llm(max_intentos=5, delay_segundos=300):
    """
    Entra en un bucle de espera activa si el servidor LLM falla.
    Retorna True si el servidor se recupera, False en caso contrario.
    """
    print(f"\n[!] INICIANDO MODO RECUPERACION. El servidor LLM no responde o el modelo crasheo.")
    print(f"    Se realizaran hasta {max_intentos} intentos de reconexion cada {delay_segundos//60} minutos.")
    
    for i in range(1, max_intentos + 1):
        print(f"\n[Intento {i}/{max_intentos}] Esperando {delay_segundos//60} minutos...")
        time.sleep(delay_segundos)
        
        try:
            print(f"    Verificando estado del servidor...")
            # Un simple 'ping' listando modelos para ver si el server esta vivo
            client.models.list()
            print(f"    [OK] El servidor LLM ha respondido. Reanudando proceso...")
            return True
        except Exception as e:
            print(f"    [Error] El servidor sigue caido: {e}")
            
    print("\n[CRITICAL] No se pudo recuperar la conexion con el LLM tras varios intentos.")
    return False

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
        RETURN DISTINCT p.doi AS doi, p.title AS title, p.raw_metadata AS metadata
        """
        params = {"entity": entity_filter}
    elif academic_filter:
        query = f"""
        MATCH (a:Academic {{name: $academic}})-[:AUTHORED]->(p:Paper)
        {where_clause}
        RETURN DISTINCT p.doi AS doi, p.title AS title, p.raw_metadata AS metadata
        """
        params = {"academic": academic_filter}
    else:
        query = f"""
        MATCH (p:Paper)
        {where_clause}
        RETURN p.doi AS doi, p.title AS title, p.raw_metadata AS metadata
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
                    # Intentamos sacar el abstract del raw metadata de OpenAlex si existe
                    Abstract = meta.get('Abstract', '')
                    if Abstract:
                        abstract = Abstract
                except:
                    pass
            records.append({'doi': doi, 'title': title, 'abstract': abstract})
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
        # Guardar la justificación del rechazo en el nodo Paper
        query_null = "MATCH (p:Paper {doi: $doi}) SET p.sdg_reasoning = $reasoning"
        with neo4j.driver.session() as session:
            session.run(query_null, doi=doi, reasoning=reasoning)
        return # No asignado a un SDG específico
        
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
    print("Iniciando clasificación SDG con LLM...")
    if force:
        print("  -> MODO FORZADO ACTIVADO (Re-procesando clasificados)")
        
    total_total = count_unclassified_papers(entity_filter=entity_filter, academic_filter=academic_filter, force=force)
    print(f"[OK] Se encontraron {total_total} papers para clasificar por ODS.")
    
    procesados = 0
    papers = fetch_unclassified_papers(entity_filter=entity_filter, academic_filter=academic_filter, force=force)
    
    if not papers:
        print("No hay papers pendientes por clasificar.")
        return

    print(f"Procesando {len(papers)} papers...")
    consecutive_errors = 0
    max_consecutive = 5

    for p in papers:
            doi = p['doi']
            titulo = p['title']
            abstract = p['abstract']
            
            try:
                res = clasificar_paper(titulo, abstract)
                consecutive_errors = 0 
                
                # Marco documento como procesado garantizado solo si el LLM respondió correctamente
                query_mark = "MATCH (p:Paper {doi: $doi}) SET p.sdg_processed = true"
                with neo4j.driver.session() as session:
                    session.run(query_mark, doi=doi)
            except ConnectionError as ce:
                print(f"\n❌ Fallo critico en LLM: {ce}")
                if esperar_recuperacion_llm():
                    # Si se recupero, volvemos a intentar el MISMO paper
                    try:
                        res = clasificar_paper(titulo, abstract)
                    except Exception as e2:
                        print(f"Error tras recuperacion: {e2}")
                        res = None
                else:
                    print("❌ Finalizando proceso por falta de respuesta del LLM.")
                    break
            except Exception as e:
                consecutive_errors += 1
                res = None
                print(f"\n⚠️ Error inesperado ({consecutive_errors}/{max_consecutive}): {e}")
                if consecutive_errors >= max_consecutive:
                    print("❌ Demasiados errores consecutivos. Abortando.")
                    break
                
            if res:
                assign_sdg_to_neo4j(doi, res)
                
                sdg_result = res.get('sdg_id')
                # Truncar título para el print
                title_short = (titulo[:50] + '...') if len(titulo) > 50 else titulo
                if not sdg_result or sdg_result.lower() == "null":
                    razon = res.get('reasoning', 'Sin justificación')
                    print(f"  [{procesados+1}/{total_total}] {doi} ({title_short}) -> null ({razon})")
                else:
                    print(f"  [{procesados+1}/{total_total}] {doi} ({title_short}) -> {sdg_result}")
            else:
                 print(f"❌ Falló clasificación LLM para {doi}")
            
            procesados += 1

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clasifica papers en Objetivos de Desarrollo Sostenible (SDG) usando LLM.")
    parser.add_argument("--entity", type=str, help="Nombre de la entidad para filtrar")
    parser.add_argument("--academic", type=str, help="Nombre del académico para filtrar")
    parser.add_argument("--force", action="store_true", help="Forzar re-clasificación de papers ya procesados")
    args = parser.parse_args()
    
    run(entity_filter=args.entity, academic_filter=args.academic, force=args.force)
