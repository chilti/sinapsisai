# ingestion/enrich_with_s2.py
import os
import time
import json
import requests
from neo4j import GraphDatabase
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de Semantic Scholar
S2_API_KEY = os.getenv("SEMANTIC_SCHOLAR_S2_API_Key")

# Configuración Neo4j (USANDO INSTANCIA DE PRUEBAS MEXICO)
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = os.getenv("NEO4J_USER_MEXICO", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD_MEXICO")

class S2Enricher:
    def __init__(self):
        print(f"--- Conectando a Neo4j (TEST/MEXICO) en {NEO4J_URI} ---")
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        self.headers = {"x-api-key": S2_API_KEY} if S2_API_KEY else {}
        self.base_url = "https://api.semanticscholar.org/graph/v1/paper/batch"
        
        # Campos para explotación máxima
        self.fields = "paperId,externalIds,title,year,citationCount,influentialCitationCount,tldr,s2FieldsOfStudy"

    def close(self):
        self.driver.close()

    def get_papers_to_enrich(self, limit=1000):
        """Busca papers que tengan DOI real y no tengan datos de S2."""
        query = """
        MATCH (w:Paper) 
        WHERE w.doi IS NOT NULL 
          AND w.doi <> "" 
          AND w.s2_influential_citations IS NULL
        RETURN w.doi AS doi, w.id AS id
        LIMIT $limit
        """
        with self.driver.session() as session:
            result = session.run(query, limit=limit)
            papers = [{"doi": r["doi"], "id": r["id"]} for r in result]
            if papers:
                print(f"DEBUG: Primeros 3 DOIs encontrados: {[p['doi'] for p in papers[:3]]}")
            return papers

    def fetch_s2_batch(self, batch_dois):
        """Consulta Semantic Scholar en lote con limpieza de DOIs."""
        clean_ids = []
        for doi in batch_dois:
            if not doi: continue
            # Limpiar espacios y prefijos comunes
            c_doi = str(doi).strip().replace("https://doi.org/", "").replace("http://doi.org/", "")
            # S2 prefiere el prefijo DOI:
            if not c_doi.lower().startswith("doi:"):
                clean_ids.append(f"DOI:{c_doi}")
            else:
                clean_ids.append(c_doi)
        
        if not clean_ids: return None
        
        # Depuración: ver qué estamos enviando
        print(f"(Ej: {clean_ids[0]}) ", end="")
        
        params = {"fields": self.fields}
        payload = {"ids": clean_ids}
        
        try:
            response = requests.post(self.base_url, params=params, json=payload, headers=self.headers, timeout=30)
            if response.status_code == 429:
                print("\nWARNING: Rate limit (429) detectado. Pausando 30 segundos...")
                time.sleep(30)
                return None
            
            if response.status_code != 200:
                print(f"\nERROR S2 ({response.status_code}): {response.text}")
                return None

            return response.json()
        except Exception as e:
            print(f"\nERROR en la petición S2: {e}")
            return None

    def update_neo4j(self, s2_data):
        """Actualiza los nodos en Neo4j con los datos obtenidos."""
        query = """
        UNWIND $data AS item
        MATCH (w:Paper) 
        WHERE w.doi = item.doi 
           OR w.doi = item.clean_doi 
           OR toLower(w.doi) = toLower(item.doi)
        SET w.s2_id = item.paperId,
            w.s2_influential_citations = item.influentialCitationCount,
            w.s2_tldr = item.tldr_text,
            w.s2_metadata = item.raw_json
        """
        prepared_data = []
        for paper in s2_data:
            if not paper or "paperId" not in paper:
                continue
            
            ext_ids = paper.get("externalIds", {})
            doi = ext_ids.get("DOI")
            
            tldr_data = paper.get("tldr")
            tldr_text = tldr_data.get("text") if isinstance(tldr_data, dict) else None
            
            prepared_data.append({
                "doi": doi,
                "clean_doi": doi.lower() if doi else None,
                "paperId": paper.get("paperId"),
                "influentialCitationCount": paper.get("influentialCitationCount"),
                "tldr_text": tldr_text,
                "raw_json": json.dumps(paper)
            })
            
        if prepared_data:
            with self.driver.session() as session:
                session.run(query, data=prepared_data)
            return len(prepared_data)
        return 0

    def run(self, total_limit=1000, batch_size=50):
        print(f"START: Iniciando enriquecimiento S2 (Limite: {total_limit}, Batch: {batch_size})")
        papers = self.get_papers_to_enrich(limit=total_limit)
        
        if not papers:
            print("DONE: No hay papers en Neo4j (test) que necesiten enriquecimiento.")
            return

        print(f"INFO: Encontrados {len(papers)} papers pendientes.")

        for i in range(0, len(papers), batch_size):
            batch = papers[i:i + batch_size]
            batch_dois = [p["doi"] for p in batch]
            
            print(f"FETCH: Batch {i//batch_size + 1}/{(len(papers)-1)//batch_size + 1} | DOIs: {len(batch_dois)}... ", end="", flush=True)
            start_time = time.time()
            
            results = self.fetch_s2_batch(batch_dois)
            if results:
                updated = self.update_neo4j(results)
                print(f"OK: {updated} actualizados.")
            else:
                print("SKIP: Saltado.")

            elapsed = time.time() - start_time
            wait_time = max(0.1, 1.5 - elapsed)
            time.sleep(wait_time)

        print("\nFINISH: Proceso finalizado.")

if __name__ == "__main__":
    enricher = S2Enricher()
    try:
        enricher.run(total_limit=100, batch_size=20)
    finally:
        enricher.close()


if __name__ == "__main__":
    enricher = S2Enricher()
    try:
        # Prueba con un lote pequeño inicialmente para validar conexión
        enricher.run(total_limit=100, batch_size=20)
    finally:
        enricher.close()
