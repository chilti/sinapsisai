import sys
import os
import json
import time

# Añadir el path del grafo
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore
import pyalex

pyalex.config.email = "test@example.com"

def patch_metadata():
    graph_store = Neo4jGraphStore()
    dois = []
    
    print("Mapeando DOIs desde Neo4j...")
    with graph_store.driver.session() as session:
        # Extraer papers que tienen raw_metadata para parchear
        result = session.run("MATCH (p:Paper) WHERE p.raw_metadata IS NOT NULL RETURN p.id as doi, p.raw_metadata as meta")
        for row in result:
            dois.append((row['doi'], row['meta']))
            
    # Filtrar solo validos para pyalex
    dois_filtrados = [d for d in dois if d[0].startswith("10.") and not d[0].startswith("urn:")]
    print(f"Encontrados {len(dois_filtrados)} DOIs válidos en Neo4j. Consultando OpenAlex...")
    
    # Procesar en lotes de 20 (limite pyalex filter)
    batch_size = 20
    updated_count = 0
    total = len(dois_filtrados)
    
    for i in range(0, total, batch_size):
        batch = dois_filtrados[i:i+batch_size]
        valid_dois = [d[0].replace("https://doi.org/", "").strip().lower() for d in batch]
        
        if not valid_dois: continue
        
        # Primero intentamos como lote de 20
        oa_data = {}
        try:
            query_dois = "|".join([f"https://doi.org/{d}" for d in valid_dois])
            works = pyalex.Works().filter(doi=query_dois).get()
            oa_data = {w['doi'].replace("https://doi.org/", "").lower(): w for w in works if w.get('doi')}
        except Exception as e:
            # Si el lote de 20 falla (usualmente por un DOI 404 malformado), iteramos uno por uno
            for d in valid_dois:
                try:
                    w = pyalex.Works().filter(doi=f"https://doi.org/{d}").get()
                    if w and w[0].get('doi'):
                        oa_data[w[0]['doi'].replace("https://doi.org/", "").lower()] = w[0]
                except:
                    pass
        
        # Una vez traido el mapeo, parchar la base Neo4j        
        with graph_store.driver.session() as session:
            for doi_full, raw_meta_json in batch:
                clean_doi = doi_full.replace("https://doi.org/", "").strip().lower()
                if clean_doi in oa_data:
                    work = oa_data[clean_doi]
                    # Deserializar robusto
                    if isinstance(raw_meta_json, dict):
                        meta = raw_meta_json
                    else:
                        try:
                            # Reemplazar comillas simples si el stringificado de python las dejó (común en repr dicts)
                            if isinstance(raw_meta_json, str) and raw_meta_json.startswith("{'") and "'" in raw_meta_json:
                                import ast
                                meta = ast.literal_eval(raw_meta_json)
                            else:
                                meta = json.loads(raw_meta_json)
                        except Exception as e:
                            print(f"\n[!] JSON Parse Error para {clean_doi}: {e} | Snippet: {str(raw_meta_json)[:50]}", flush=True)
                            continue
                        
                    # Actualizar
                    meta['fwci'] = work.get('fwci', None)
                    meta['open_access'] = work.get('open_access', {})
                    if work.get('citation_normalized_percentile'):
                        perc_data = work['citation_normalized_percentile']
                        meta['citation_normalized_percentile'] = perc_data.get('value', 0.0)
                        meta['is_in_top_1_percent'] = perc_data.get('is_in_top_1_percent', False)
                        meta['is_in_top_10_percent'] = perc_data.get('is_in_top_10_percent', False)
                        
                    # Guardar de vuelta
                    session.run("MATCH (p:Paper {id: $id}) SET p.raw_metadata = $meta", 
                               id=doi_full, meta=json.dumps(meta))
                    updated_count += 1
                else:
                    if(i==0): print(f"\n[!] {clean_doi} no encontrado en la repuesta de OpenAlex. (Muestra de rechazo)", flush=True)
                    
        print(f"Lote {i//batch_size + 1}: Actualizados {updated_count}/{total} papers.", end="\r", flush=True)
        time.sleep(0.1)
            
    print(f"\n🎉 Parche completado. {updated_count} papers en Neo4j fortalecidos con métricas OpenAlex.")
    graph_store.close()

if __name__ == "__main__":
    patch_metadata()
