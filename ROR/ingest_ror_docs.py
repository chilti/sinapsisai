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
from dotenv import load_dotenv

# Añadir path raíz ANTES de importar módulos locales
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# Configuración utf-8
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from ingestion import openalex_utils
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from langchain_openai import OpenAIEmbeddings

# Cargar .env de la raíz
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

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
        self.vector_store = QdrantStore(collection_name="api_papers")
        self.graph_store = Neo4jGraphStore()
        
    def load_mapping(self):
        path = 'ROR/snii_ror_mapping.json'
        if not os.path.exists(path):
            print(f"❌ No se encontró el mapeo: {path}")
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def ingest_by_ror(self, ror_id: str, institution_name: str, subdependency_name: str = "SIN INFORMACIÓN", local_only: bool = False):
        print(f"\n🔍 Procesando ROR: {ror_id} ({institution_name} | {subdependency_name})")
        if local_only:
            print("   ℹ️ Modo 'Local Only' activado. Saltando API oficial.")
        
        # 1. Buscar trabajos en OpenAlex usando el generador de openalex_utils
        try:
            processed_count = 0
            for page in openalex_utils.get_works_by_ror(ror_id, per_page=100, local_only=local_only):
                self._process_works_batch(page, institution_name, subdependency_name)
                processed_count += len(page)
            
            if processed_count > 0:
                print(f"   ✅ Se procesaron {processed_count} trabajos para este ROR.")
            else:
                print(f"   ⚠️ No se encontraron trabajos o hubo un error para este ROR.")
                
        except Exception as e:
            print(f"   ❌ Error durante la recuperación de OpenAlex: {e}")

    def _process_works_batch(self, works, inst_name, sub_name):
        batch_payloads = []
        batch_texts = []
        
        for work in works:
            doi_raw = work.get('doi')
            if not doi_raw: continue
            doi = doi_raw.replace("https://doi.org/", "").strip().lower()
            
            # 1. Verificar si ya existe en ambas bases
            exists_graph = self.graph_store.check_paper_exists(doi)
            exists_qdrant = self.vector_store.check_document_exists(doi)
            
            # 2. Si ya existe en Neo4j, saltar (o actualizar si fuera necesario, pero por ahora saltamos por eficiencia)
            if exists_graph:
                # Si falta en Qdrant pero existe en Neo4j, aún podemos vectorizarlo
                if not exists_qdrant:
                    self._prepare_for_qdrant(work, inst_name, sub_name, batch_texts, batch_payloads)
                continue
            
            # 3. Si no existe en Neo4j, procesar e insertar
            # 3a. Preparar para Qdrant (si no existe)
            if not exists_qdrant:
                self._prepare_for_qdrant(work, inst_name, sub_name, batch_texts, batch_payloads)

            # 3b. Preparar datos para Neo4j (basado en el esquema de add_paper)
            authors = []
            for auth in work.get('authorships', []):
                author_name = auth.get('author', {}).get('display_name', 'Unknown')
                insts = []
                for inst_data in auth.get('institutions', []):
                    insts.append({
                        "id": inst_data.get('id'),
                        "name": inst_data.get('display_name') or inst_data.get('name') or "Institución Desconocida"
                    })
                authors.append({"name": author_name, "institutions": insts})

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
            
            # Guardamos el paper (la validación de existencia ya se hizo arriba)
            self.graph_store.add_paper(paper_data)
            
            # 4. Marcar como IndexedOpenAlex
            self.graph_store.mark_paper_as_indexed(doi, 'openalex')
            self.graph_store.set_paper_openalex_id(doi, work.get('id'))
            
            # 5. Link Jerárquico
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

    def _prepare_for_qdrant(self, work, inst_name, sub_name, batch_texts, batch_payloads):
        """Prepara un documento para ser vectorizado en Qdrant."""
        title = work.get('display_name') or work.get('title') or "Sin Título"
        abstract = deconstruct_abstract(work.get('abstract_inverted_index'))
        year = work.get('publication_year', 0)
        
        doi_raw = work.get('doi')
        if not doi_raw: return
        doi = doi_raw.replace("https://doi.org/", "").strip().lower()

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

    def run(self, limit=None, local_only=False):
        mapping = self.load_mapping()
        print(f"DEBUG: {len(mapping)} entries in mapping.")
        count = 0
        for key, data in mapping.items():
            ror_id = data.get('best_match_ror')
            conf = data.get('confidence', 0)
            
            # print(f"DEBUG: Testing {key} | ROR: {ror_id} | Conf: {conf}") # Limpiar debug ruidoso
            
            if not ror_id or conf < 70:
                continue
            
            if limit and count >= limit: 
                break
            
            parts = key.split(' || ')
            inst = parts[0]
            sub = parts[1] if len(parts) > 1 else "SIN INFORMACIÓN"
            
            self.ingest_by_ror(ror_id, inst, sub, local_only=local_only)
            count += 1

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingesta de documentos ROR desde OpenAlex")
    parser.add_argument("--limit", type=int, help="Límite de instituciones a procesar")
    parser.add_argument("--local-only", action="store_true", help="Usar sólo la API local de OpenAlex")
    args = parser.parse_args()
    
    ingestor = RORIngestor()
    try:
        ingestor.run(limit=args.limit, local_only=args.local_only)
    finally:
        ingestor.graph_store.close()
        print("\n🎉 Finalizado.")
