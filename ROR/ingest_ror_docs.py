"""
ingest_ror_docs.py
Toma el mapeo ROR/snii_ror_mapping.json y para cada ROR idenfiticado,
descarga los artículos de OpenAlex, los vectoriza y los guarda/marca en las bases.
Asegura que todos queden etiquetados como :IndexedOpenAlex.
"""

import sys
import os
import json
import time
import httpx
import pyalex
from dotenv import load_dotenv
from ingestion import openalex_utils

# Configuración utf-8
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from langchain_openai import OpenAIEmbeddings

# Cargar .env de la raíz
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

pyalex.config.email = os.getenv("EMAIL_ADDRESS", "sin_correo@ciencias.unam.mx")
if os.getenv("OPENALEX_API_KEY"):
    pyalex.config.api_key = os.getenv("OPENALEX_API_KEY")

# --- Config Embeddings ---
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
model_name = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
embedding_model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

if not base_url.endswith("/"): base_url += "/"
auth_url = base_url
if user and password:
    if "://" in base_url:
        proto, rest = base_url.split("://", 1)
        auth_url = f"{proto}://{user}:{password}@{rest}"

http_client = httpx.Client(verify=False, timeout=120)

embeddings_model = OpenAIEmbeddings(
    model=embedding_model,
    base_url=auth_url,
    api_key="lm-studio",
    http_client=http_client,
    check_embedding_ctx_length=False
)

def deconstruct_abstract(inverted_abstract):
    if not inverted_abstract: return None
    try:
        abstract_len = max(pos for val in inverted_abstract.values() for pos in val) + 1
        abstract_list = [""] * abstract_len
        for word, positions in inverted_abstract.items():
            for pos in positions: abstract_list[pos] = word
        return " ".join(filter(None, abstract_list))
    except: return None

class RORIngestor:
    def __init__(self):
        self.vector_store = QdrantStore(collection_name="scientific_papers")
        self.graph_store = Neo4jGraphStore()
        
    def load_mapping(self):
        path = 'ROR/snii_ror_mapping.json'
        if not os.path.exists(path):
            print(f"❌ No se encontró el mapeo: {path}")
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def ingest_by_ror(self, ror_id: str, institution_name: str, subdependency_name: str = "SIN INFORMACIÓN"):
        print(f"\n🔍 Procesando ROR: {ror_id} ({institution_name} | {subdependency_name})")
        
        # 1. Buscar trabajos en OpenAlex
        try:
            works_query = pyalex.Works().filter(institutions={"ror": ror_id})
            total_works = works_query.count()
            print(f"   -> Encontrados {total_works} trabajos en OpenAlex (API Oficial).")
        except Exception as e:
            print(f"   ⚠️ API Oficial falló o bloqueada ({e}). Intentando API Local (127.0.0.1:5009)...")
            # Guardar original
            original_url = pyalex.config.api_url
            try:
                pyalex.config.api_url = "http://127.0.0.1:5009"
                works_query = pyalex.Works().filter(institutions={"ror": ror_id})
                total_works = works_query.count()
                print(f"   -> Encontrados {total_works} trabajos en OpenAlex (API Local).")
            except Exception as e2:
                print(f"   ❌ Error final consultando OpenAlex (Local): {e2}")
                # Restaurar y salir
                pyalex.config.api_url = original_url
                return
            # Se queda con el api_url local para la paginación de abajo

        try:
            # Procesar por lotes (ej. 100)
            for page in works_query.paginate(per_page=100):
                self._process_works_batch(page, institution_name, subdependency_name)
        except Exception as e:
            print(f"   ❌ Error durante la paginación de OpenAlex: {e}")
        finally:
            # Restaurar URL original tras procesar
            pyalex.config.api_url = "https://api.openalex.org"

    def _process_works_batch(self, works, inst_name, sub_name):
        batch_payloads = []
        batch_texts = []
        
        for work in works:
            doi_raw = work.get('doi')
            if not doi_raw: continue
            doi = doi_raw.replace("https://doi.org/", "").strip().lower()
            
            # 1. Verificar si ya existe
            exists = self.graph_store.check_paper_exists(doi)
            
            # 2. Si no existe, preparar para Qdrant
            if not exists:
                title = work.get('display_name') or work.get('title') or "Sin Título"
                abstract = deconstruct_abstract(work.get('abstract_inverted_index'))
                year = work.get('publication_year', 0)
                
                text_content = f"Title: {title}\nAbstract: {abstract or ''}".strip()
                batch_texts.append(text_content)
                batch_payloads.append({
                    "paper_id": doi,
                    "title":    title,
                    "year":     year,
                    "doi":      doi,
                    "entity":   sub_name if sub_name != "SIN INFORMACIÓN" else inst_name,
                    "text":     text_content
                })

            # 3. Preparar datos para Neo4j (basado en el esquema de add_paper)
            # Extraer autores simplificados para el merge
            authors = []
            for auth in work.get('authorships', []):
                author_name = auth.get('author', {}).get('display_name', 'Unknown')
                insts = []
                for inst_data in auth.get('institutions', []):
                    insts.append({
                        "id": inst_data.get('id'),
                        "name": inst_data.get('display_name')
                    })
                authors.append({"name": author_name, "institutions": insts})

            # Extraer conceptos
            concepts = []
            for concept in work.get('concepts', []):
                concepts.append({
                    "id": concept.get('id'),
                    "name": concept.get('display_name')
                })

            paper_data = {
                "paper_id": doi,
                "doi": doi,
                "title": work.get('display_name') or work.get('title') or "Sin Título",
                "year": work.get('publication_year', 0),
                "citations": work.get('cited_by_count', 0),
                "authors": authors,
                "concepts": concepts,
                "raw_metadata": work
            }
            
            # Guardamos/Mergeamos el paper
            self.graph_store.add_paper(paper_data)
            
            # 4. Marcar como IndexedOpenAlex y poner su OA URL
            self.graph_store.mark_paper_as_indexed(doi, 'openalex')
            self.graph_store.set_paper_openalex_id(doi, work.get('id'))
            
            # 5. Link Jerárquico (Institución + Subdependencia)
            # Nota: add_academic_full_affiliation no sirve aquí porque es para Academic.
            # Usamos add_entity_paper_link para ambos niveles si aplica.
            self.graph_store.add_entity_paper_link(inst_name, doi)
            if sub_name and sub_name != "SIN INFORMACIÓN":
                 self.graph_store.add_entity_paper_link(sub_name, doi)

        # 6. Embeddings masivos
        if batch_texts:
            print(f"      -> Vectorizando {len(batch_texts)} nuevos artículos...")
            try:
                embeddings = embeddings_model.embed_documents(batch_texts)
                self.vector_store.add_documents(batch_payloads, embeddings)
            except Exception as e:
                print(f"      ❌ Error en vectorización: {e}")

    def run(self, limit=None):
        mapping = self.load_mapping()
        print(f"DEBUG: {len(mapping)} entries in mapping.")
        count = 0
        for key, data in mapping.items():
            ror_id = data.get('best_match_ror')
            conf = data.get('confidence', 0)
            
            print(f"DEBUG: Testing {key} | ROR: {ror_id} | Conf: {conf}")
            
            if not ror_id or conf < 70:
                print(f"DEBUG: Skipping {key} (Conf too low or No ROR)")
                continue
            
            if limit and count >= limit: 
                print(f"DEBUG: Limit {limit} reached.")
                break
            
            print(f"DEBUG: >>> CALLING INGEST for {key}")
            parts = key.split(' || ')
            inst = parts[0]
            sub = parts[1] if len(parts) > 1 else "SIN INFORMACIÓN"
            
            self.ingest_by_ror(ror_id, inst, sub)
            count += 1

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingesta de documentos ROR desde OpenAlex")
    parser.add_argument("--limit", type=int, help="Límite de instituciones a procesar")
    args = parser.parse_args()
    
    ingestor = RORIngestor()
    try:
        ingestor.run(limit=args.limit)
    finally:
        ingestor.graph_store.close()
        print("\n🎉 Finalizado.")
