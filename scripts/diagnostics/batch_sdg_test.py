import os
import sys
import json
import time

# Asegurar que el directorio raíz esté en el path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from lib.llm_utils import get_openai_client, handle_llm_exception
from database.knowledge_graph import Neo4jGraphStore

# --- SYSTEM PROMPT BATCH ---
SYSTEM_PROMPT_BATCH = """
You are an expert in bibliometrics and sustainability. 
Your task is to analyze a LIST of scientific articles and classify EACH ONE into THE MOST RELEVANT Sustainable Development Goal (SDG).

Rules:
1. Identify the SINGLE main Sustainable Development Goal (SDG) for each article.
2. If an article has no clear relationship with any SDG, use "null". 
3. Answer EXCLUSIVELY in a valid JSON LIST format.
4. You MUST output the sdg_name in ENGLISH.

Return a JSON list of objects matches this structure for EACH article:
{
  "doi": "original DOI provided",
  "sdg_id": "SDG X",
  "sdg_name": "Official SDG name in English",
  "confidence": "XX%",
  "reasoning": "Brief 1-sentence justification"
}
"""

def test_batch_classification(batch_size=3):
    neo4j = Neo4jGraphStore()
    client = get_openai_client()
    model = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")

    print(f"--- Iniciando Experimento Batch (n={batch_size}) ---")
    
    # 1. Obtener papers de muestra con metadatos de OpenAlex
    query = """
    MATCH (p:Paper)
    WHERE p.raw_metadata IS NOT NULL 
    RETURN p.doi as doi, p.title as title, p.raw_metadata as metadata
    LIMIT $limit
    """
    
    papers_raw = []
    with neo4j.driver.session() as session:
        res = session.run(query, limit=50) # Tomamos una muestra más grande para filtrar
        for r in res:
            papers_raw.append(dict(r))

    papers = []
    for p in papers_raw:
        abstract = ""
        try:
            meta = json.loads(p['metadata'])
            abstract = meta.get('Abstract')
            if abstract is None:
                abstract = ""
        except:
            pass
        
        if len(str(abstract)) > 50:
            papers.append({
                'doi': p['doi'],
                'title': p['title'],
                'abstract': abstract
            })
            if len(papers) >= batch_size:
                break

    if len(papers) < batch_size:
        print(f"No se encontraron suficientes papers ({len(papers)}/{batch_size}). Abortando.")
        return

    # 2. Construir el prompt de lote
    articles_text = ""
    for idx, p in enumerate(papers):
        articles_text += f"\n--- ARTICLE {idx+1} ---\nDOI: {p['doi']}\nTitle: {p['title']}\nAbstract: {p['abstract']}\n"

    print(f"Enviando lote de {len(papers)} artículos al modelo {model}...")
    start_time = time.time()
    
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_BATCH},
                {"role": "user", "content": f"Articles to classify:\n{articles_text}"}
            ],
            temperature=0.2,
            max_tokens=1000
        )
        
        raw_response = completion.choices[0].message.content
        duration = time.time() - start_time
        
        print(f"\nRespuesta recibida en {duration:.2f} segundos.")
        print("-" * 30)
        print("Respuesta RAW del modelo:")
        print(raw_response)
        print("-" * 30)
        
        # Limpiar y parsear
        clean_res = raw_response.strip()
        if clean_res.startswith("```json"):
            clean_res = clean_res.replace("```json", "").replace("```", "").strip()
        elif clean_res.startswith("```"):
            clean_res = clean_res.replace("```", "").strip()
            
        try:
            results = json.loads(clean_res)
            print(f"JSON detectado correctamente. Se procesaron {len(results)} resultados.")
            for r in results:
                print(f"  > {r.get('doi')}: {r.get('sdg_id')} ({r.get('sdg_name')})")
            
            avg_per_paper = duration / len(papers)
            print(f"\nPROMEDIO: {avg_per_paper:.2f} segundos por artículo.")
            
        except json.JSONDecodeError:
            print("ERROR: La respuesta del modelo no es un JSON válido.")
            
    except Exception as e:
        handle_llm_exception(e)
        print(f"Error durante la clasificación: {e}")
    finally:
        neo4j.close()

if __name__ == "__main__":
    test_batch_classification(batch_size=3)
