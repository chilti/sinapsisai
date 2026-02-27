import os
import json
import uuid
import sys
from openai import OpenAI
from dotenv import load_dotenv

# Asegurar que reconozca los módulos del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

load_dotenv()

# --- CONFIGURACIÓN ---
URL_LM_STUDIO = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
MODELO_A_USAR = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# Cliente compatible con OpenAI para conectar con LM Studio
client = OpenAI(base_url=URL_LM_STUDIO, api_key="lm-studio")

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
        
        datos_ods = json.loads(respuesta_limpia)
        return datos_ods
        
    except Exception as e:
        print(f"\nError procesando paper: {e}")
        return None

def fetch_unclassified_papers():
    """Obtiene los papers de Neo4j que aún no tienen clasificación SDG."""
    query = """
    MATCH (p:Paper)
    WHERE COALESCE(p.sdg_processed, false) = false
    RETURN p.doi AS doi, p.title AS title, p.raw_metadata AS metadata
    LIMIT 50
    """
    records = []
    with neo4j.driver.session() as session:
        result = session.run(query)
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

def run():
    print("Iniciando clasificación SDG con LLM...")
    while True:
        papers = fetch_unclassified_papers()
        if not papers:
            print("No hay más papers pendientes por clasificar.")
            break
            
        print(f"Procesando lote de {len(papers)} papers...")
        for p in papers:
            doi = p['doi']
            titulo = p['title']
            abstract = p['abstract']
            
            # TODO: Add logic to flag paper as 'processed_sdg: true' even if it returns null, 
            # to avoid picking it up again in fetch_unclassified_papers.
            
            res = clasificar_paper(titulo, abstract)
            
            # Marco documento como procesado garantizado, para no volver a intentarlo
            query_mark = "MATCH (p:Paper {doi: $doi}) SET p.sdg_processed = true"
            with neo4j.driver.session() as session:
                session.run(query_mark, doi=doi)
                
            if res:
                assign_sdg_to_neo4j(doi, res)
                
                sdg_result = res.get('sdg_id')
                if not sdg_result or sdg_result.lower() == "null":
                    razon = res.get('reasoning', 'Sin justificación')
                    print(f"✅ {doi} -> null ({razon})")
                else:
                    print(f"✅ {doi} -> {sdg_result}")
            else:
                 print(f"❌ Falló clasificación LLM para {doi}")

if __name__ == "__main__":
    run()
