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

    def _ror_to_openalex_id(self, ror_id: str) -> str | None:
        """Devuelve el OpenAlex institution ID (https://openalex.org/I...) dado un ROR."""
        try:
            ch = ch_client.get_client()
            result = ch.query(
                "SELECT DISTINCT id FROM institutions WHERE ror = {ror:String} LIMIT 1",
                parameters={'ror': ror_id}
            )
            if result.result_rows:
                return result.result_rows[0][0]   # e.g. 'https://openalex.org/I8961855'
        except Exception as e:
            print(f"   ⚠️  Error buscando OpenAlex ID para ROR {ror_id}: {e}")
        return None

    def _iter_works_from_ch(self, target_id: str, batch_size: int = 500):
        """
        Generador que itera works_flat FINAL filtrando por institution_ids (OpenAlex ID).
        Construye dicts de work desde columnas estructuradas (works_flat no tiene raw_data).
        Keyset pagination por id — sin límite de 10k, sin duplicados de snapshot.
        """
        if target_id.startswith('https://openalex.org/'):
            oa_id = target_id
        else:
            oa_id = self._ror_to_openalex_id(target_id)
            
        if not oa_id:
            print(f"   ❌ No se encontró OpenAlex ID para {target_id}. Saltando.")
            return

        print(f"   🗄️  ClickHouse directo: {oa_id} ({target_id})")
        ch = ch_client.get_client()
        last_id = ''
        page = 0
        total_yielded = 0

        while True:
            try:
                rows = ch.query(
                    """
                    SELECT
                        id, doi, title, publication_year, cited_by_count,
                        is_oa, type, pmid, mag_id, fwci, percentile,
                        is_top_10, is_top_1, source_id,
                        domain_name, field_name, subfield_name, topic_id, sdgs
                    FROM works_flat FINAL
                    WHERE has(institution_ids, {oa_id:String})
                      AND id > {last_id:String}
                    ORDER BY id
                    LIMIT {batch_size:UInt32}
                    """,
                    parameters={
                        'oa_id': oa_id,
                        'last_id': last_id,
                        'batch_size': batch_size,
                    }
                ).result_rows
            except Exception as e:
                print(f"   ❌ Error en batch {page}: {e}")
                break

            if not rows:
                break

            batch = []
            for row in rows:
                (wid, doi, title, year, cites,
                 is_oa, wtype, pmid, mag_id, fwci, percentile,
                 is_top_10, is_top_1, source_id,
                 dom, fld, subf, top, sdgs) = row
                # Reconstruir dict compatible con _process_works_batch_multi
                batch.append({
                    'id':               wid,
                    'doi':              doi or None,
                    'display_name':     title or '',
                    'publication_year': int(year or 0),
                    'cited_by_count':   int(cites or 0),
                    'is_oa':            bool(is_oa),
                    'type':             wtype or '',
                    'fwci':             float(fwci or 0),
                    'topic_domain':     dom,
                    'topic_field':      fld,
                    'topic_subfield':   subf,
                    'topic_name':       top,
                    'sdgs':             sdgs,
                    'authorships':      [],
                    'concepts':         [],
                    'ids': {
                        'pmid': pmid or '',
                        'mag':  mag_id or '',
                    },
                })

            if not batch:
                break

            total_yielded += len(batch)
            page += 1
            print(f"   📄 Batch {page}: {len(batch)} works (total: {total_yielded:,})")
            yield batch

            if len(rows) < batch_size:
                break

            # Keyset: id de la última fila (columna 0)
            last_id = rows[-1][0]

        print(f"   ✅ ClickHouse: {total_yielded:,} works totales para {target_id}")


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
                for ent in entities:
                    inst, dep, sub = ent['inst'], ent['dep'], ent['sub']
                    self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Institution', doi)
                    if dep != "SIN INFORMACIÓN":
                        self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Dependency', doi)
                    if sub != "SIN INFORMACIÓN":
                        self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Subdependency', doi)
                continue

            # 2. Verificar si ya existe en las bases (para DOIs no vistos en este run)
            exists_graph = self.graph_store.check_paper_exists(doi)
            exists_qdrant = self.vector_store.check_document_exists(doi)
            
            # 3. Si ya existe en Neo4j, ENRIQUECER en lugar de saltar
            if exists_graph:
                self.graph_store.mark_paper_as_indexed(doi, 'openalex')
                self.graph_store.set_paper_openalex_id(doi, work.get('id'))
                
                for ent in entities:
                    inst, dep, sub = ent['inst'], ent['dep'], ent['sub']
                    if sub != "SIN INFORMACIÓN":
                        self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Subdependency', doi)
                    elif dep != "SIN INFORMACIÓN":
                        self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Dependency', doi)
                    else:
                        self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Institution', doi)
                
                if not exists_qdrant:
                    self._prepare_for_qdrant_multi(work, entities, batch_texts, batch_payloads)
                
                self.processed_dois.add(doi)
                continue
            
            # 4. Si no existe en Neo4j, procesar e insertar
            if not exists_qdrant:
                self._prepare_for_qdrant_multi(work, entities, batch_texts, batch_payloads)

            # Desactivamos la extracción de autores y conceptos para el pipeline ROR
            # authors, concepts = self._extract_authors_and_concepts(work)

            paper_data = {
                "paper_id": doi,
                "doi": doi,
                "title": work.get('display_name') or work.get('title') or "Sin Título",
                "year": work.get('publication_year', 0),
                "citations": work.get('cited_by_count', 0),
                "authors": [],
                "concepts": [],
                "raw_metadata": work
            }
            
            self.graph_store.add_paper(paper_data)
            self.graph_store.mark_paper_as_indexed(doi, 'openalex')
            self.graph_store.set_paper_openalex_id(doi, work.get('id'))
            
            for ent in entities:
                inst, dep, sub = ent['inst'], ent['dep'], ent['sub']
                if sub != "SIN INFORMACIÓN":
                    self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Subdependency', doi)
                elif dep != "SIN INFORMACIÓN":
                    self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Dependency', doi)
                else:
                    self.graph_store.add_hierarchical_entity_paper_link(inst, dep, sub, 'Institution', doi)
            
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

    def run(self, limit=None, local_only=False, save_to_ch=False, target_name=None):
        self.save_to_ch = save_to_ch
        mapping = self.load_mapping()
        print(f"📊 Cargados {len(mapping)} registros del mapeo ROR.")
        
        # 1. Agrupar entidades por Target ID (Priorizar OpenAlex ID, si no ROR)
        ror_groups = {} # target_id -> list of (inst, sub, is_specific)
        for key, data in mapping.items():
            matched_oa = data.get('matched_openalex_id')
            parent_oa = data.get('parent_openalex_id')
            matched_ror = data.get('matched_ror')
            parent_ror = data.get('parent_ror')
            
            # VALIDACIÓN CRÍTICA: Si es una dependencia/subdependencia pero hereda el ID exacto del padre,
            # no tiene identidad propia en OpenAlex y descargar al padre colapsaría el sistema. La saltamos.
            if "||" in key:
                if (matched_oa and parent_oa and matched_oa == parent_oa) or \
                   (matched_ror and parent_ror and matched_ror == parent_ror):
                    continue
            
            target_id = matched_oa or matched_ror or data.get('best_match_ror')
            conf = data.get('confidence', 0)
            
            if not target_id or conf < 70: continue
                
            if target_id not in ror_groups: ror_groups[target_id] = []
            
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
            actual_ror = data.get('matched_ror') or data.get('best_match_ror')
            
            # Evitar duplicados exactos en el mapeo para este ROR
            ent_entry = {
                "inst": inst, "dep": dep, "sub": sub,
                "parent_ror": parent_ror, "parent_oa": parent_oa,
                "matched_ror": actual_ror, "matched_oa": matched_oa,
                "is_sub_match": is_sub_match
            }
            if ent_entry not in ror_groups[target_id]:
                ror_groups[target_id].append(ent_entry)

        if target_name:
            filtered_groups = {}
            # Normalizar el target (quitar espacios alrededor de || si existen)
            target_normalized = "||".join([p.strip() for p in target_name.split('||')]).lower()
            for ror_id, entries in ror_groups.items():
                for ent in entries:
                    # Reconstruir la llave original normalizada
                    ent_str = f"{ent['inst']}||{ent['dep']}||{ent['sub']}".lower()
                    
                    if target_normalized in ent_str or target_name.lower() in ent_str:
                        if ror_id not in filtered_groups: filtered_groups[ror_id] = []
                        if ent not in filtered_groups[ror_id]: filtered_groups[ror_id].append(ent)
            ror_groups = filtered_groups
            print(f"🎯 Filtrado por '{target_name}': {len(ror_groups)} RORs listos para procesar.")

        print(f"🎯 Identificados {len(ror_groups)} RORs únicos para procesar.")
        
        count = 0
        total_rors = len(ror_groups)
        for target_id, entities in ror_groups.items():
            if limit and count >= limit: break
            count += 1
            # Construir la jerarquía completa para el log
            inst_log = entities[0]['inst']
            dep_log = entities[0]['dep']
            sub_log = entities[0]['sub']
            
            jerarquia = inst_log
            if dep_log != "SIN INFORMACIÓN":
                jerarquia += f" || {dep_log}"
            if sub_log != "SIN INFORMACIÓN":
                jerarquia += f" || {sub_log}"
                
            print(f"\n🚀 [{count}/{total_rors}] Procesando Entidad {target_id}\n   🏢 Jerarquía: {jerarquia}")
            
            try:
                processed_count = 0
                for page in self._iter_works_from_ch(target_id):
                    self._process_works_batch_multi(page, entities, target_id)
                    processed_count += len(page)
                print(f"   ✅ Finalizado: {processed_count} trabajos.")
            except Exception as e:
                print(f"   ❌ Error: {e}")

    def _process_works_batch_multi(self, works, entities, target_id):
        """Procesa trabajos vinculándolos a los 3 niveles y actualizando metadata."""
        batch_payloads = []
        batch_texts = []
        
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

        print(f"      🔍 Qdrant: {len(works)} trabajos. {len(works) - len(missing_dois_in_qdrant)} ya existen, {len(missing_dois_in_qdrant)} nuevos.")

        for work in works:
            doi = (work.get('doi') or '').replace("https://doi.org/", "").lower()
            
            # En ROR no siempre tenemos el CVU, así que pasamos None
            # Llamamos a ingest_paper_row por cada entidad para asegurar los links CREDITED_TO
            for ent in entities:
                row = {
                    "paper_id": doi,
                    "title": work.get('display_name') or "Sin Título",
                    "year": work.get('publication_year', 0),
                    "citations": work.get('cited_by_count', 0),
                    "doi": doi,
                    "openalex_id": work.get('id'),
                    "wos_id": work.get('ids', {}).get('wos'),
                    "scopus_id": work.get('ids', {}).get('scopus'),
                    "fwci": work.get('fwci'),
                    "topic_domain": work.get('topic_domain'),
                    "topic_field": work.get('topic_field'),
                    "topic_subfield": work.get('topic_subfield'),
                    "topic_name": work.get('topic_name'),
                    "sdgs": work.get('sdgs', []),
                    "author_cvu": None,
                    "author_position": None,
                    "is_corresponding": False,
                    "institucion": ent['inst'],
                    "dependencia": ent['dep'],
                    "subdependencia": ent['sub']
                }
                self.graph_store.ingest_paper_row(row)
            
            # 2. Qdrant
            u_str = doi if doi and str(doi).strip().lower() != "none" else work.get('display_name')
            exists_qdrant = u_str not in missing_dois_in_qdrant
            if not exists_qdrant:
                self._prepare_for_qdrant_multi(work, entities, batch_texts, batch_payloads)
            
            self.processed_dois.add(doi)

        if len(works) > 0:
            print(f"      🗄️ Neo4j: {len(works)} artículos procesados.")

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
                raw_doi = (w.get('doi') or '').replace('https://doi.org/', '').strip().lower()
                openalex_url = w.get('id') or ''
                # Preferir DOI normalizado (coincide con LIKE '10.%' en _Q_PROD)
                # Si no hay DOI, usar W-ID corto sin el prefijo https://openalex.org/
                if raw_doi and raw_doi.startswith('10.'):
                    paper_id = raw_doi
                elif openalex_url.startswith('https://openalex.org/'):
                    paper_id = openalex_url.replace('https://openalex.org/', '')  # → 'W4404983616'
                else:
                    paper_id = openalex_url or raw_doi
                if not paper_id:
                    continue

                ids = w.get('ids', {})
                for ent in entities:
                    rows.append({
                        'paper_id': paper_id,
                        'institution': ent['inst'],
                        'institution_ror': ent['matched_ror'],
                        'dependency': ent['dep'],
                        'dependency_id': '',
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
                        'source': 'CH_Direct_Ingest'
                    })
            if rows:
                import pandas as pd
                df_to_insert = pd.DataFrame(rows).drop_duplicates(subset=['paper_id', 'institution', 'dependency', 'subdependency'])
                ch.insert_df('paper_entity_map', df_to_insert)
                print(f"      📊 [ClickHouse] {len(df_to_insert)} mapeos únicos sincronizados (de {len(rows)} totales).")
        except Exception as e:
            print(f"      [WARN] Error en ClickHouse Sync: {e}")

    def _prepare_for_qdrant_multi(self, work, entities, batch_texts, batch_payloads):
        ent = entities[0]
        ref_inst, ref_dep, ref_sub = ent['inst'], ent['dep'], ent['sub']
        title = work.get('display_name') or "Sin Título"
        abstract = deconstruct_abstract(work.get('abstract_inverted_index'))
        doi = (work.get('doi') or '').replace("https://doi.org/", "").lower()
        
        text_content = f"Title: {title}\nAbstract: {abstract or ''}".strip()
        batch_texts.append(text_content)
        batch_payloads.append({
            "paper_id": doi, 
            "title": title, 
            "doi": doi,
            "institution": ref_inst,
            "dependency": ref_dep,
            "subdependency": ref_sub,
            "text": text_content
        })

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingesta de documentos ROR desde OpenAlex")
    parser.add_argument("--limit", type=int, help="Límite de instituciones a procesar")
    parser.add_argument("--local-only", action="store_true", help="Usar sólo la API local de OpenAlex")
    parser.add_argument("--ch", action="store_true", help="Sincronizar con ClickHouse (paper_entity_map)")
    parser.add_argument("--name", type=str, help="Filtrar por nombre de institución, dependencia o subdependencia")
    args = parser.parse_args()
    
    ingestor = RORIngestor()
    try:
        ingestor.run(limit=args.limit, local_only=args.local_only, save_to_ch=args.ch, target_name=args.name)
    except KeyboardInterrupt:
        print("\n\n🛑 Proceso interrumpido por el usuario.")
    finally:
        ingestor.graph_store.close()
        print("\n🎉 Finalizado.")
