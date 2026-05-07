"""
ingest_ror_docs.py
==================
Toma el mapeo data/snii_ror_verified_matches.json y para cada ROR identificado,
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
from database.clickhouse_db import ch_client
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
        # Cache de DOIs procesados en esta ejecución para evitar redundancia
        self.processed_dois = set()
        
    def _extract_authors_and_concepts(self, work):
        """Extrae autores y conceptos formateados para Neo4jGraphStore."""
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
        return authors, concepts
        
    def load_mapping(self):
        path = os.path.join('data', 'snii_ror_verified_matches.json')
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
                self._process_works_batch(page, entities)
                processed_count += len(page)
            
            if processed_count > 0:
                print(f"   ✅ Se procesaron {processed_count} trabajos para este ROR.")
            else:
                print(f"   ⚠️ No se encontraron trabajos o hubo un error para este ROR.")
                
        except Exception as e:
            print(f"   ❌ Error durante la recuperación de OpenAlex: {e}")

    def _process_works_batch(self, works, entities):
        batch_payloads = []
        batch_texts = []
        
        # Enriquecer metadatos de la institución (Entity) con el primer work válido de la página
        if works:
            inst_name = entities[0]['inst']
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

        # Deduplicación local del batch para no repetir vectorización en la misma página
        batch_seen = set()

        for work in works:
            doi_raw = work.get('doi')
            if not doi_raw: continue
            doi = doi_raw.replace("https://doi.org/", "").strip().lower()
            
            # Evitar duplicados en el mismo batch (página de OpenAlex)
            if doi in batch_seen: continue
            batch_seen.add(doi)

            # 1. Verificar si ya fue procesado en esta ejecución (ahorro de DB)
            if doi in self.processed_dois:
                # Solo aseguramos el link por si acaso es una nueva entidad vinculada al mismo DOI
                self.graph_store.add_entity_paper_link(inst_name, doi)
                if sub_name and sub_name != "SIN INFORMACIÓN":
                    self.graph_store.add_entity_paper_link(sub_name, doi)
                continue

            # 2. Verificar si ya existe en las bases (para DOIs no vistos en este run)
            exists_graph = self.graph_store.check_paper_exists(doi)
            exists_qdrant = self.vector_store.check_document_exists(doi)
            
            # 3. Si ya existe en Neo4j, ENRIQUECER en lugar de saltar
            if exists_graph:
                self.graph_store.mark_paper_as_indexed(doi, 'openalex')
                self.graph_store.set_paper_openalex_id(doi, work.get('id'))
                self.graph_store.add_entity_paper_link(inst_name, doi)
                if sub_name and sub_name != "SIN INFORMACIÓN":
                    self.graph_store.add_entity_paper_link(sub_name, doi)
                
                if not exists_qdrant:
                    self._prepare_for_qdrant(work, inst_name, sub_name, batch_texts, batch_payloads)
                
                self.processed_dois.add(doi)
                continue
            
            # 4. Si no existe en Neo4j, procesar e insertar
            if not exists_qdrant:
                self._prepare_for_qdrant(work, inst_name, sub_name, batch_texts, batch_payloads)

            authors, concepts = self._extract_authors_and_concepts(work)

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
            
            self.graph_store.add_paper(paper_data)
            self.graph_store.mark_paper_as_indexed(doi, 'openalex')
            self.graph_store.set_paper_openalex_id(doi, work.get('id'))
            
            self.graph_store.add_entity_paper_link(inst_name, doi)
            if sub_name and sub_name != "SIN INFORMACIÓN":
                 self.graph_store.add_entity_paper_link(sub_name, doi)
            
            self.processed_dois.add(doi)

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

    def run(self, limit=None, local_only=False, save_to_ch=False):
        self.save_to_ch = save_to_ch
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
            
            parts = [p.strip() for p in key.split('||')]
            if len(parts) == 3:
                inst, dep, sub = parts
            else:
                inst = parts[0] if len(parts) > 0 else "SIN INFORMACIÓN"
                dep = parts[1] if len(parts) > 1 else "SIN INFORMACIÓN"
                sub = parts[2] if len(parts) > 2 else "SIN INFORMACIÓN"
            
            # Guardamos todos los datos necesarios para la metadata
            matched_oa = data.get('matched_openalex_id')
            parent_oa = data.get('parent_openalex_id')
            is_sub_match = data.get('is_subdependency_match', False)
            
            ror_groups[ror_id].append({
                "inst": inst, "dep": dep, "sub": sub,
                "parent_ror": parent_ror, "parent_oa": parent_oa,
                "matched_ror": ror_id, "matched_oa": matched_oa,
                "is_sub_match": is_sub_match
            })

        print(f"🎯 Identificados {len(ror_groups)} RORs únicos para procesar.")
        
        count = 0
        total_rors = len(ror_groups)
        for ror_id, entities in ror_groups.items():
            if limit and count >= limit: break
            count += 1
            main_inst = entities[0]['inst']
            print(f"\n🚀 [{count}/{total_rors}] Procesando ROR {ror_id} ({main_inst})")
            
            try:
                processed_count = 0
                for page in openalex_utils.get_works_by_ror(ror_id, per_page=100, local_only=local_only):
                    self._process_works_batch_multi(page, entities, ror_id)
                    processed_count += len(page)
                print(f"   ✅ Finalizado: {processed_count} trabajos.")
            except Exception as e:
                print(f"   ❌ Error: {e}")

    def _process_works_batch_multi(self, works, entities, ror_id):
        """Procesa trabajos vinculándolos a los 3 niveles y actualizando metadata."""
        batch_payloads = []
        batch_texts = []
        batch_seen = set()
        
        # 1. Actualizar metadata de las entidades primero
        if works:
            for ent in entities:
                inst, dep, sub = ent['inst'], ent['dep'], ent['sub']
                p_ror, p_oa = ent['parent_ror'], ent['parent_oa']
                m_ror, m_oa = ent['matched_ror'], ent['matched_oa']
                is_sub = ent['is_sub_match']
                
                # Inst
                if p_ror or p_oa:
                    self.graph_store.upsert_hierarchical_entity_metadata(inst, dep, sub, 'Institution', p_ror, p_oa)
                # Dep
                if dep != "SIN INFORMACIÓN":
                    if not is_sub and (m_ror or m_oa):
                        self.graph_store.upsert_hierarchical_entity_metadata(inst, dep, sub, 'Dependency', m_ror, m_oa)
                    elif p_ror or p_oa:
                        self.graph_store.upsert_hierarchical_entity_metadata(inst, dep, sub, 'Dependency', p_ror, p_oa)
                # Sub
                if sub != "SIN INFORMACIÓN":
                    if is_sub and (m_ror or m_oa):
                        self.graph_store.upsert_hierarchical_entity_metadata(inst, dep, sub, 'Subdependency', m_ror, m_oa)
                    elif p_ror or p_oa:
                        self.graph_store.upsert_hierarchical_entity_metadata(inst, dep, sub, 'Subdependency', p_ror, p_oa)

        # Optimización: Filtrar documentos que ya existen en Qdrant por lote
        ids_to_check = [{"doi": (w.get('doi') or '').replace("https://doi.org/", "").lower(), "title": w.get('display_name')} for w in works]
        missing_dois_in_qdrant = set()
        if hasattr(self.vector_store, 'filter_existing_ids'):
            missing_dois_in_qdrant = set(self.vector_store.filter_existing_ids(ids_to_check))
        else:
            missing_dois_in_qdrant = {(w.get('doi') or '').replace("https://doi.org/", "").lower() for w in works}

        print(f"      🔍 Qdrant: {len(works)} trabajos encontrados. {len(works) - len(missing_dois_in_qdrant)} ya existen, {len(missing_dois_in_qdrant)} nuevos para vectorizar.")

        for work in works:
            doi = (work.get('doi') or '').replace("https://doi.org/", "").lower()
            if not doi: continue
            
            # 1. Si ya se procesó en este run, solo actualizamos links
            if doi in self.processed_dois:
                for ent in entities:
                    inst, dep, sub = ent['inst'], ent['dep'], ent['sub']
                    self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Institution', doi)
                    if dep != "SIN INFORMACIÓN":
                        self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Dependency', doi)
                    if sub != "SIN INFORMACIÓN":
                        self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Subdependency', doi)
                continue

            # 2. Verificar existencia en bases
            exists_graph = self.graph_store.check_paper_exists(doi)
            
            # Usar el set pre-calculado para Qdrant
            u_str = doi if doi and str(doi).strip().lower() != "none" else work.get('display_name')
            exists_qdrant = u_str not in missing_dois_in_qdrant

            if not exists_graph:
                authors, concepts = self._extract_authors_and_concepts(work)
                self.graph_store.add_paper({
                    "paper_id": doi, "doi": doi, 
                    "title": work.get('display_name') or "Sin Título",
                    "year": work.get('publication_year', 0),
                    "citations": work.get('cited_by_count', 0),
                    "authors": authors,
                    "concepts": concepts,
                    "raw_metadata": work
                })

            self.graph_store.mark_paper_as_indexed(doi, 'openalex')
            self.graph_store.set_paper_openalex_id(doi, work.get('id'))

            # VINCULACIÓN 3 NIVELES
            for ent in entities:
                inst, dep, sub = ent['inst'], ent['dep'], ent['sub']
                self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Institution', doi)
                if dep != "SIN INFORMACIÓN":
                    self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Dependency', doi)
                if sub != "SIN INFORMACIÓN":
                    self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Subdependency', doi)
                
            if not exists_qdrant:
                self._prepare_for_qdrant_multi(work, entities, batch_texts, batch_payloads)
            
            self.processed_dois.add(doi)

        if len(works) > 0:
            print(f"      🗄️ Neo4j: {len(works)} artículos vinculados a jerarquía institucional.")

        # Vectorizar
        if batch_texts:
            try:
                embeddings = embeddings_model.embed_documents(batch_texts)
                self.vector_store.add_documents(batch_payloads, embeddings)
            except: pass

        # --- DUAL WRITE TO CLICKHOUSE ---
        if self.save_to_ch and works:
            self._sync_to_clickhouse(works, entities)

    def _sync_to_clickhouse(self, works, entities):
        try:
            ch = ch_client.get_client()
            rows = []
            for w in works:
                doi = (w.get('doi') or w.get('id') or '').replace("https://doi.org/", "").lower()
                if not doi: continue
                
                ids = w.get('ids', {})
                
                # Para cada entidad mapeada a este ROR, creamos una entrada en la tabla de entidades
                for ent in entities:
                    rows.append({
                        'paper_id': doi,
                        'institution': ent['inst'],
                        'institution_ror': ent['matched_ror'],
                        'dependency': ent['dep'],
                        'dependency_id': '', # Se podría derivar si fuera necesario
                        'subdependency': ent['sub'],
                        'subdependency_id': '',
                        'paper_title': w.get('display_name') or '',
                        'paper_year': int(w.get('publication_year') or 0),
                        'citations': int(w.get('cited_by_count') or 0),
                        'is_wos': 1 if 'wos' in ids else 0,
                        'is_scopus': 1 if 'scopus' in ids else 0,
                        'is_pubmed': 1 if 'pmid' in ids else 0,
                        'is_openalex': 1,
                        'is_doaj': 1 if w.get('is_oa') and 'doaj' in str(w.get('locations', [])).lower() else 0,
                        'is_semantic_scholar': 1 if 'mag' in ids else 0,
                        'is_dimensions': 1 if 'mag' in ids else 0,
                        'is_lens': 1 if 'mag' in ids or 'pmid' in ids else 0,
                        'source': 'ROR_Dual_Ingest'
                    })
            if rows:
                import pandas as pd
                ch.insert_df('paper_entity_map', pd.DataFrame(rows))
                print(f"      📊 [ClickHouse] {len(rows)} mapeos de entidades sincronizados.")
        except Exception as e:
            print(f"      [WARN] Error en ClickHouse Sync: {e}")

    def _prepare_for_qdrant_multi(self, work, entities, batch_texts, batch_payloads):
        ent = entities[0]
        ref_inst, ref_dep, ref_sub = ent['inst'], ent['dep'], ent['sub']
        title = work.get('display_name') or "Sin Título"
        abstract = deconstruct_abstract(work.get('abstract_inverted_index'))
        doi = (work.get('doi') or '').replace("https://doi.org/", "").lower()
        
        # Escoger la entidad mas especifica para Qdrant
        entity_qdrant = ref_sub if ref_sub != "SIN INFORMACIÓN" else (ref_dep if ref_dep != "SIN INFORMACIÓN" else ref_inst)
        
        text_content = f"Title: {title}\nAbstract: {abstract or ''}".strip()
        batch_texts.append(text_content)
        batch_payloads.append({
            "paper_id": doi, "title": title, "doi": doi,
            "entity": entity_qdrant,
            "text": text_content
        })

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingesta de documentos ROR desde OpenAlex")
    parser.add_argument("--limit", type=int, help="Límite de instituciones a procesar")
    parser.add_argument("--local-only", action="store_true", help="Usar sólo la API local de OpenAlex")
    parser.add_argument("--ch", action="store_true", help="Sincronizar con ClickHouse (paper_entity_map)")
    args = parser.parse_args()
    
    ingestor = RORIngestor()
    try:
        ingestor.run(limit=args.limit, local_only=args.local_only, save_to_ch=args.ch)
    except KeyboardInterrupt:
        print("\n\n🛑 Proceso interrumpido por el usuario.")
    finally:
        ingestor.graph_store.close()
        print("\n🎉 Finalizado.")
