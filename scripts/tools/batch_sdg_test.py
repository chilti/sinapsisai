import os
import sys
import json
import time
from dotenv import load_dotenv

# Asegurar que el directorio raíz esté en el path para importar lib/database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from lib.llm_utils import get_openai_client, handle_llm_exception
from database.knowledge_graph import Neo4jGraphStore

load_dotenv()

# --- SYSTEM PROMPT BATCH ---
# Diseñado para procesar múltiples artículos y devolver una lista JSON estructurada
SYSTEM_PROMPT_BATCH = """
You are an expert in bibliometrics and sustainability. 
Your task is to analyze a LIST of scientific articles and classify EACH ONE into THE MOST RELEVANT Sustainable Development Goal (SDG).

Rules:
1. Identify the SINGLE main Sustainable Development Goal (SDG) for each article.
2. If an article has no clear relationship with any SDG, use "null". 
3. Answer EXCLUSIVELY in a valid JSON LIST format.
4. You MUST output the sdg_name in ENGLISH.

Return a JSON list of objects matching this structure for EACH article:
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

def test_batch_classification(batch_size=5):
    neo4j = Neo4jGraphStore()
    client = get_openai_client(async_mode=False)
    model = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")

    print(f"--- [EXP] Iniciando Experimento Batch ODS ---")
    
    # 1. Obtener papers de muestra con metadatos reales
    # Buscamos artículos que tengan raw_metadata
    query = """
    MATCH (p:Paper)
    WHERE p.raw_metadata IS NOT NULL 
    RETURN p.doi as doi, p.title as title, p.raw_metadata as metadata
    LIMIT 100
    """
    
    papers_raw = []
    try:
        with neo4j.driver.session() as session:
            res = session.run(query)
            for r in res:
                papers_raw.append(dict(r))
    except Exception as e:
        print(f"[ERROR] No se pudo conectar a Neo4j: {e}")
        return

    # Filtrar aquellos que tengan un abstract decente en los metadatos
    papers = []
    for p in papers_raw:
        abstract = ""
        try:
            meta = json.loads(p['metadata'])
            abstract = meta.get('Abstract') or meta.get('abstract') or ""
        except:
            pass
        
        if len(str(abstract)) > 100:
            papers.append({
                'doi': p['doi'],
                'title': p['title'],
                'abstract': abstract
            })
            if len(papers) >= batch_size:
                break

    if not papers:
        print("[FAIL] No se encontraron papers con abstracts suficientes en la muestra. Abortando.")
        return

    print(f"[INFO] Encontrados {len(papers)} papers validos. Preparando lote...")

    # 2. Construir el prompt de lote
    articles_text = ""
    for idx, p in enumerate(papers):
        # Limpieza básica para evitar romper la estructura del prompt
        safe_title = str(p['title']).replace('"', "'")
        safe_abstract = str(p['abstract']).replace('"', "'")[:1500]
        articles_text += f"\n--- ARTICLE {idx+1} ---\nDOI: {p['doi']}\nTitle: {safe_title}\nAbstract: {safe_abstract}\n"

    print(f"[INFO] Enviando lote al modelo {model}...")
    start_time = time.time()
    
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_BATCH},
                {"role": "user", "content": f"Articles to classify:\n{articles_text}"}
            ],
            temperature=0.1,
            max_tokens=2000
        )
        
        raw_response = completion.choices[0].message.content
        duration = time.time() - start_time
        
        print(f"\n[TIME] Respuesta recibida en {duration:.2f} segundos.")
        print("-" * 30)
        print("Respuesta RAW del modelo:")
        print(raw_response)
        print("-" * 30)
        
        # Limpiar bloques de código markdown si los hay
        clean_res = raw_response.strip()
        if "```json" in clean_res:
            clean_res = clean_res.split("```json")[-1].split("```")[0].strip()
        elif "```" in clean_res:
             clean_res = clean_res.split("```")[-1].split("```")[0].strip()
            
        try:
            results = json.loads(clean_res)
            print(f"[OK] JSON parseado. Se procesaron {len(results)} resultados en el lote.")
            for r in results:
                doi = r.get('doi', 'N/A')
                sdg = r.get('sdg_id', 'null')
                conf = r.get('confidence', '0%')
                print(f"  > {doi}: {sdg} (Conf: {conf})")
            
            avg_per_paper = duration / len(papers)
            print(f"\n[STATS] EFICIENCIA: {avg_per_paper:.2f} segundos por articulo.")
            print(f"       (Total: {duration:.2f}s para {len(papers)} papers).")
            
        except json.JSONDecodeError:
            print("[ERROR] La respuesta del modelo no es un JSON estructurado valido (lista).")
            
    except Exception as e:
        handle_llm_exception(e)
        print(f"[ERROR] Excepción durante la clasificacion: {e}")
    finally:
        neo4j.close()

if __name__ == "__main__":
    test_batch_classification(batch_size=5)
