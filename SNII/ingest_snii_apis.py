"""
ingest_snii_apis.py
Toma snii_llm_verified_matches.json y extrae artículos desde Scopus, ORCID y OpenAlex,
guardándolos en Qdrant (colección: api_papers) y Neo4j (Label: APIPaper, ligados a Academic).
Asigna afiliación jerárquica: Academia -> Subdependencia -> Institución.
"""

import sys
import os
import json
import time
import requests
import pyalex
import httpx
from dotenv import load_dotenv, find_dotenv

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from ingestion import openalex_utils

# Es preferible que inicialice si están las librerías
try:
    import pybliometrics
    from pybliometrics.scopus import AuthorRetrieval
    pybliometrics.scopus.init()
except Exception:
    print("Nota: pybliometrics puede no estar completamente configurado con la API key de Scopus.")

# Cargar .env de forma robusta
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

pyalex.config.email = os.getenv("EMAIL_ADDRESS", "sin_correo@ciencias.unam.mx")
if os.getenv("OPENALEX_API_KEY"):
    pyalex.config.api_key = os.getenv("OPENALEX_API_KEY")

from langchain_openai import OpenAIEmbeddings

# --- Config Embeddings ---
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
if not base_url.endswith("/"):
    base_url += "/"
model_name = os.getenv("EMBEDDING_MODEL", "text-embedding-nomic-ai-nomic-embed-text-v2-moe")
auth_url = base_url
if user and password:
    if "://" in base_url:
        proto, rest = base_url.split("://", 1)
        auth_url = f"{proto}://{user}:{password}@{rest}"
    else:
        auth_url = f"http://{user}:{password}@{base_url}"

http_client = httpx.Client(verify=False, timeout=120)

embeddings_model = OpenAIEmbeddings(
    model=model_name,
    base_url=auth_url,
    api_key="lm-studio",
    http_client=http_client,
    check_embedding_ctx_length=False
)

def get_embeddings(texts: list, batch_size: int = 5, force_local: bool = False) -> list:
    if not texts: return []
    all_embeddings = []
    
    if force_local:
        try:
            import lmstudio as lms
            model = lms.embedding_model(model_name)
            for text in texts:
                clean_t = str(text) if text else " "
                emb = model.embed(clean_t)
                if hasattr(emb, "embedding"):
                    val = emb.embedding
                elif hasattr(emb, "tolist"):
                    val = emb.tolist()
                elif isinstance(emb, list):
                    val = emb
                else:
                    val = list(emb)
                all_embeddings.append(val)
            return all_embeddings
        except Exception as e:
            print(f"⚠️ Error con librería 'lmstudio': {e}. Cayendo a LangChain...")

    for i in range(0, len(texts), batch_size):
        batch = [str(t) if t else " " for t in texts[i:i+batch_size]]
        embs = embeddings_model.embed_documents(batch)
        all_embeddings.extend(embs)
    return all_embeddings

# --- Bases de Datos ---
vector_store = QdrantStore(collection_name="api_papers")
graph_store = Neo4jGraphStore()

# --- Helpers de APIs ---

def _clean_t(t): 
    return "".join(c for c in str(t).lower() if c.isalnum())

def deconstruct_abstract(inverted_abstract):
    if not inverted_abstract: return None
    try:
        abstract_len = max(pos for val in inverted_abstract.values() for pos in val) + 1
        abstract_list = [""] * abstract_len
        for word, positions in inverted_abstract.items():
            for pos in positions: abstract_list[pos] = word
        return " ".join(filter(None, abstract_list))
    except (ValueError, TypeError):
        return None

def obtener_metadatos_de_scopus(scopus_ids):
    if not scopus_ids: return {}
    if not isinstance(scopus_ids, list):
        if isinstance(scopus_ids, str):
            scopus_ids = [s.strip() for s in scopus_ids.split(',')]
        else:
            scopus_ids = [scopus_ids]

    metadatos = {}
    for sid in scopus_ids:
        if not sid: continue
        sid = str(sid).strip()
        import re
        match = re.search(r'\d{8,12}', sid)
        if match:
            sid = match.group(0)
            
        try:
            au = AuthorRetrieval(sid)
            docs = list(au.get_documents())
            print(f"    [Scopus] ID {sid}: {len(docs)} documentos encontrados.")
            for pub in docs:
                if pub.doi and pub.doi not in metadatos:
                    metadatos[pub.doi] = {
                        'Title': pub.title,
                        'Year': pub.coverDate.split('-')[0] if pub.coverDate else 0,
                        'DOI': pub.doi,
                        'Source': 'Scopus',
                        'Authors': pub.author_names,
                        'Cited_by': pub.citedby_count,
                        'Abstract': pub.abstract if hasattr(pub, 'abstract') else None
                    }
        except Exception as e:
            print(f"    Advertencia en Scopus para {sid}: {e}")
    return metadatos

def obtener_metadatos_de_orcid(orcid_url):
    if not orcid_url: return {}
    orcid_id = str(orcid_url).rstrip('/').split('/')[-1]
    import re
    if not re.search(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', orcid_id, re.IGNORECASE):
        return {}

    metadatos = {}
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            for work_group in response.json().get('group', []):
                summary = work_group.get('work-summary', [{}])[0]
                ext_ids_node = summary.get('external-ids')
                ext_ids_list = []
                if ext_ids_node and isinstance(ext_ids_node, dict):
                    ext_ids_list = ext_ids_node.get('external-id', [])
                    if isinstance(ext_ids_list, dict): ext_ids_list = [ext_ids_list]

                doi_raw = next((eid.get('external-id-value') for eid in ext_ids_list
                                 if isinstance(eid, dict) and eid.get('external-id-type') == 'doi'), None)
                if doi_raw:
                    doi = (str(doi_raw).strip()
                           .replace('https://doi.org/', '')
                           .replace('http://doi.org/',  '')
                           .replace('https://dx.doi.org/', '')
                           .strip('/'))
                else:
                    put_code = summary.get('put-code')
                    doi = f"orcid-work:{put_code}" if put_code else None

                if doi and doi not in metadatos:
                    pub_date = summary.get('publication-date', {}) or {}
                    title_node = summary.get('title', {}) or {}
                    metadatos[doi] = {
                        'Title': title_node.get('title', {}).get('value') if title_node.get('title') else 'Sin Título',
                        'Year': pub_date.get('year', {}).get('value') if pub_date.get('year') else 0,
                        'DOI': doi,
                        'Source': 'ORCID',
                        'Authors': None,
                        'Cited_by': 0,
                        'Abstract': None
                    }
    except Exception as e:
        print(f"    Advertencia en ORCID para {orcid_id}: {e}")
    
    if metadatos:
        print(f"    [ORCID] ID {orcid_id}: {len(metadatos)} documentos encontrados.")
    return metadatos

# --- Lógica principal de ingesta SNII ---

def process_and_ingest_snii(json_path, force=False, force_local=False, target_name=None, limit_acads=None, confirmed_only=False):
    if not os.path.exists(json_path):
        print(f"No se encontró el archivo: {json_path}")
        return
        
    with open(json_path, 'r', encoding='utf-8') as f:
        registros = json.load(f)

    print(f"📊 Procesando padrón SNII...")
    
    # Procesar TODOS los registros, pero priorizando confirmados
    def sort_priority(r):
        v = r.get('audit', {}).get('verdict')
        if v == "CONFIRMED": return 2
        if v == "DOUBTFUL": return 1
        return 0
    
    registros.sort(key=sort_priority, reverse=True)
    
    if confirmed_only:
        registros_to_process = [r for r in registros if r.get('audit', {}).get('verdict') == "CONFIRMED"]
        print(f"✅ Filtrando solo confirmados: {len(registros_to_process)}")
    else:
        registros_to_process = registros
        print(f"✅ Registros totales para procesar: {len(registros_to_process)} (Priorizando confirmados)")

    count = 0
    for data in registros_to_process:
        academic_name = data.get('snii_author')
        if not academic_name: continue

        if limit_acads and count >= limit_acads:
            print(f"🛑 Límite de {limit_acads} alcanzado.")
            break
            
        if target_name and target_name.lower() not in academic_name.lower():
            continue
            
        count += 1
        inst_name = data.get('snii_institution', 'INSTITUCIÓN DESCONOCIDA')
        sub_name = data.get('snii_subdependency', 'SIN INFORMACIÓN')
        orcid = data.get('matched_orcid')
        
        # 1. Actualizar metadatos básicos y auditoría directamente (Independiente de si tiene papers)
        audit = data.get('audit', {})
        print(f"\n🏷️ [{academic_name}] Actualizando metadatos y afiliación...")
        
        # Usar el nuevo método para persistir auditoría incluso sin papers
        if hasattr(graph_store, 'update_academic_metadata'):
            graph_store.update_academic_metadata(
                academic_name=academic_name,
                orcid=orcid if data.get('match') is True and audit.get('verdict') != 'FALSE_POSITIVE' else None,
                scopus_id=data.get('scopus_ids'),
                audit_verdict=audit.get('verdict'),
                audit_reason=audit.get('reason'),
                audit_confidence=audit.get('confidence'),
                audit_timestamp=audit.get('timestamp'),
                match_reason=data.get('reason'),
                discarded_candidates=data.get('discarded_candidates'),
                is_snii=True
            )
        else:
            graph_store.set_academic_snii(academic_name, True)

        # 2. Asegurar afiliación jerárquica
        graph_store.add_academic_full_affiliation(academic_name, inst_name, sub_name)

        # 3. Determinar si es seguro recolectar publicaciones
        # NO recolectar si: no hay orcid, o es match=false, o es veredicto FALSE_POSITIVE
        is_safe_match = data.get('match') is True and orcid and audit.get('verdict') != 'FALSE_POSITIVE'
        
        if not is_safe_match:
            print(f"  ℹ️ Saltando recolección de publicaciones (Match: {data.get('match')}, Veredicto: {audit.get('verdict')})")
            continue

        # 4. Verificar existencia de publicaciones (evitar procesar de nuevo si no se fuerza)
        if hasattr(graph_store, 'check_academic_exists') and graph_store.check_academic_exists(academic_name) and not force:
            print(f"  📍 Publicaciones ya existen en Neo4j. Saltando recolección API...")
            continue

        print(f"  🧬 Iniciando recopilación API para {orcid}...")
        
        # 1. Recolección de ORCID
        meta_unificada = obtener_metadatos_de_orcid(orcid)
        
        if not meta_unificada:
            print("  -> Sin publicaciones rastreables.")
            continue
            
        print(f"  -> {len(meta_unificada)} artículos únicos. Enriqueciendo...")

        batch_payloads = []
        batch_texts = []
        # Determinar si usamos OpenAlex local o oficial
        openalex_blocked = force_local or getattr(openalex_utils, 'OFFICIAL_API_BLOCKED', False)
        for doi, record in meta_unificada.items():
            text_for_embedding = f"Title: {record.get('Title')}\n"
            paper_exists = False
            
            # OpenAlex enrichment (con fallback local)
            try:
                _doi_clean = doi if not doi.startswith('orcid-work:') else None
                
                # OPT: Si el paper ya existe en Neo4j, saltamos el enriquecimiento API costoso.
                if _doi_clean and graph_store.check_paper_exists(_doi_clean):
                    print(f"      📍 Paper {_doi_clean} ya existe en el grafo. Saltando OpenAlex para ahorrar API, pero se agregará a Qdrant si falta.")
                    paper_exists = True
                    work = None
                else:
                    work = openalex_utils.get_work(doi=_doi_clean, title=record.get('Title'), local_only=openalex_blocked)
                    if not openalex_blocked and getattr(openalex_utils, 'OFFICIAL_API_BLOCKED', False):
                        openalex_blocked = True

                if work:
                    authorships = work.get('authorships', [])
                    record['Authors'] = "; ".join([au['author']['display_name'] for au in authorships])
                    record['Keywords_oa'] = "; ".join([kw['display_name'] for kw in work.get('keywords', [])])
                    record['Abstract_oa'] = deconstruct_abstract(work.get('abstract_inverted_index'))
                    record['openalex_url'] = work.get('id')
                    if record['Abstract_oa']: record['Abstract'] = record['Abstract_oa']
                    record['Cited_by'] = work.get('cited_by_count', record.get('Cited_by', 0))
                    record['Source'] += ' + OpenAlex'
            except Exception:
                pass
            
            # Procesar Qdrant para todos (existan o no en Neo4j, ya que UUID previene duplicados en Qdrant)
            qdrant_exists = False
            if hasattr(vector_store, 'check_document_exists'):
                qdrant_exists = vector_store.check_document_exists(doi=doi, title=record.get("Title"))
                
            if qdrant_exists:
                pass # Ya está en Qdrant de una corrida anterior
            else:
                if record.get('Abstract'):
                    text_for_embedding += f"Abstract: {record['Abstract']}"
                    
                payload_qdrant = {
                    "academic_name": academic_name,
                    "doi":           doi,
                    "title":         record.get("Title"),
                    "year":          record.get("Year"),
                    "source":        record.get("Source"),
                    "entity":        sub_name if sub_name != "SIN INFORMACIÓN" else inst_name,
                    "text":          text_for_embedding
                }
                batch_texts.append(text_for_embedding)
                batch_payloads.append(payload_qdrant)
            
            neo4j_data = {
                "doi": doi, "title": record.get("Title", "No Title"), "year": record.get("Year", 0),
                "citations": record.get("Cited_by", 0), "raw_metadata": record
            }
            # Pasar auditoría y razonamiento
            audit = data.get('audit', {})
            graph_store.add_api_paper(
                neo4j_data, 
                academic_name=academic_name, 
                orcid=orcid,
                audit_verdict=audit.get('verdict'),
                audit_reason=audit.get('reason'),
                audit_confidence=audit.get('confidence'),
                audit_timestamp=audit.get('timestamp'),
                match_reason=data.get('reason'),
                discarded_candidates=data.get('discarded_candidates'),
                entity_name=sub_name if sub_name != "SIN INFORMACIÓN" else inst_name
            )
            
        # Afiliación Jerárquica
        graph_store.add_academic_full_affiliation(academic_name, inst_name, sub_name)
            
        if batch_texts:
            print(f"  -> Vectorizando {len(batch_texts)} artículos...")
            try:
                embeddings = []
                for i in range(0, len(batch_texts), 32):
                    batch_subset = batch_texts[i:i+32]
                    embeddings.extend(get_embeddings(batch_subset, force_local=force_local))
                vector_store.add_documents(batch_payloads, embeddings)
                print(f"  ✅ Completado para {academic_name}.")
            except Exception as e:
                print(f"  ❌ Error en vectores: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingesta API para padrón SNII consolidado")
    parser.add_argument("--input", default=os.path.join("data", "snii_llm_verified_matches.json"), help="JSON SNII")
    parser.add_argument("--limit", type=int, help="Límite")
    parser.add_argument("--name", type=str, help="Nombre")
    parser.add_argument("--force", action="store_true", help="Forzar")
    parser.add_argument("--local", action="store_true", help="Usar recursos locales (OpenAlex y Embeddings) para evitar límites de API")
    parser.add_argument("--confirmed-only", action="store_true", help="Procesar solo los auditados como CONFIRMED")
    args = parser.parse_args()
    
    try:
        process_and_ingest_snii(
            args.input, 
            force=args.force, 
            force_local=args.local, 
            target_name=args.name, 
            limit_acads=args.limit,
            confirmed_only=args.confirmed_only
        )
    finally:
        graph_store.close()
        print("\n🎉 Proceso completado.")
