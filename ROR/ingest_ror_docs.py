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
        
        # Enriquecer metadatos de la institución (Entity) con el primer work válido de la página
        if works:
            print(f"   📂 Procesando bloque de {len(works)} trabajos para [{inst_name}]...")
            first_work = works[0]
            for auth in first_work.get('authorships', []):
                for inst_data in auth.get('institutions', []):
                    # Si el nombre coincide o estamos procesando por ROR, actualizamos metadatos
                    if inst_data.get('display_name') == inst_name or inst_data.get('name') == inst_name:
                        self.graph_store.upsert_institution_metadata({
                            "name": inst_name,
                            "id": inst_data.get('id'),
                            "ror": inst_data.get('ror'),
                            "country_code": inst_data.get('country_code'),
                            "type": inst_data.get('type')
                        })
                        break

        for work in works:
            doi_raw = work.get('doi')
            if not doi_raw: continue
            doi = doi_raw.replace("https://doi.org/", "").strip().lower()
            
            # 1. Verificar si ya existe en ambas bases
            exists_graph = self.graph_store.check_paper_exists(doi)
            exists_qdrant = self.vector_store.check_document_exists(doi)
            
            # 2. Si ya existe en Neo4j, ENRIQUECER en lugar de saltar
            if exists_graph:
                # Marcamos como IndexedOpenAlex (aunque ya sea IndexedWoS)
                self.graph_store.mark_paper_as_indexed(doi, 'openalex')
                self.graph_store.set_paper_openalex_id(doi, work.get('id'))
                
                # Link Jerárquico (Asegurar que esté vinculado a esta institución/subdependencia)
                self.graph_store.add_entity_paper_link(inst_name, doi)
                if sub_name and sub_name != "SIN INFORMACIÓN":
                    self.graph_store.add_entity_paper_link(sub_name, doi)
                
                # Si falta en Qdrant pero existe en Neo4j, lo vectorizamos
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
                        "name": inst_data.get('display_name') or inst_data.get('name'),
                        "ror": inst_data.get('ror'),
                        "country_code": inst_data.get('country_code'),
                        "type": inst_data.get('type')
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
            print(f"      -> Vectorizando {len(batch_texts)} nuevos artículos para [{inst_name}]...")
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
        print(f"📊 Cargados {len(mapping)} registros del mapeo ROR.")
        
        # 1. Agrupar entidades por ROR
        ror_groups = {} # ror_id -> list of (inst, sub, is_specific)
        for key, data in mapping.items():
            ror_id = data.get('matched_ror') or data.get('best_match_ror')
            parent_ror = data.get('parent_ror')
            conf = data.get('confidence', 0)
            
            if not ror_id or conf < 70: continue
                
            if ror_id not in ror_groups: ror_groups[ror_id] = []
            
            parts = key.split(' || ')
            inst = parts[0]
            sub = parts[-1] if len(parts) > 1 else "SIN INFORMACIÓN"
            
            # Es específico si el ROR es distinto al del padre 
            # O si la entidad misma es la institución (sub es SIN INFORMACIÓN)
            is_specific = (ror_id != parent_ror) or (sub == "SIN INFORMACIÓN")
            
            ror_groups[ror_id].append((inst, sub, is_specific))

        print(f"🎯 Identificados {len(ror_groups)} RORs únicos para procesar.")
        
        count = 0
        for ror_id, entities in ror_groups.items():
            if limit and count >= limit: break
            
            main_inst = entities[0][0]
            print(f"\n🚀 Procesando ROR {ror_id} ({main_inst})")
            
            try:
                processed_count = 0
                for page in openalex_utils.get_works_by_ror(ror_id, per_page=100, local_only=local_only):
                    self._process_works_batch_multi(page, entities, ror_id)
                    processed_count += len(page)
                print(f"   ✅ Finalizado: {processed_count} trabajos.")
            except Exception as e:
                print(f"   ❌ Error: {e}")
            count += 1

    def _process_works_batch_multi(self, works, entities, ror_id):
        """Procesa trabajos vinculándolos solo a las entidades con ID específico."""
        batch_payloads = []
        batch_texts = []
        
        for work in works:
            doi_raw = work.get('doi')
            if not doi_raw: continue
            doi = doi_raw.replace("https://doi.org/", "").strip().lower()
            
            if not self.graph_store.check_paper_exists(doi):
                # (Lógica simplificada de inserción)
                self.graph_store.add_paper({
                    "paper_id": doi, "doi": doi, 
                    "title": work.get('display_name') or "Sin Título",
                    "year": work.get('publication_year', 0),
                    "citations": work.get('cited_by_count', 0),
                    "raw_metadata": work
                })

            self.graph_store.mark_paper_as_indexed(doi, 'openalex')
            self.graph_store.set_paper_openalex_id(doi, work.get('id'))

            # VINCULACIÓN RESTRINGIDA (Regla del Usuario)
            for inst_name, sub_name, is_specific in entities:
                # 1. Siempre a la Institución
                self.graph_store.add_entity_paper_link(inst_name, doi)
                
                # 2. Solo a la Subdependencia si el ROR es específico para ella
                if sub_name and sub_name != "SIN INFORMACIÓN" and is_specific:
                    self.graph_store.add_entity_paper_link(sub_name, doi)
                
            exists_qdrant = self.vector_store.check_document_exists(doi)
            if not exists_qdrant:
                self._prepare_for_qdrant_multi(work, entities, batch_texts, batch_payloads)

        # Vectorizar
        if batch_texts:
            try:
                embeddings = embeddings_model.embed_documents(batch_texts)
                self.vector_store.add_documents(batch_payloads, embeddings)
            except: pass

    def _prepare_for_qdrant_multi(self, work, entities, batch_texts, batch_payloads):
        ref_inst, ref_sub = entities[0]
        title = work.get('display_name') or "Sin Título"
        abstract = deconstruct_abstract(work.get('abstract_inverted_index'))
        doi = work.get('doi', '').replace("https://doi.org/", "").lower()
        
        text_content = f"Title: {title}\nAbstract: {abstract or ''}".strip()
        batch_texts.append(text_content)
        batch_payloads.append({
            "paper_id": doi, "title": title, "doi": doi,
            "entity": ref_sub if ref_sub != "SIN INFORMACIÓN" else ref_inst,
            "text": text_content
        })

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
