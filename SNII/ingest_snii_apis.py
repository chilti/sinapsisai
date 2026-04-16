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

from lib.llm_utils import get_embeddings_model

# --- Config Embeddings ---
# Usamos la fábrica centralizada que ya maneja Auth, SSL y Timeouts
embeddings_model = get_embeddings_model()

def get_embeddings(texts: list, batch_size: int = 5, force_local: bool = False) -> list:
    if not texts: return []
    all_embeddings = []
    
    if force_local:
        try:
            import lmstudio as lms
            _local_model_name = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
            model = lms.embedding_model(_local_model_name)
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

def obtener_metadatos_de_openalex_autor(openalex_author_id, force_local=False):
    """Obtiene los trabajos de un autor directamente desde su OpenAlex Author ID.
    Soporta tanto la API local como la API oficial de pyalex.
    """
    if not openalex_author_id:
        return {}
    
    # Normalizar el ID: aceptar URL completa o solo el código (A123456)
    oa_id_clean = str(openalex_author_id).split('/')[-1].strip()
    
    metadatos = {}
    env_path_local = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
    load_dotenv(env_path_local)
    local_api = os.getenv("OPENALEX_LOCAL_API", "http://localhost:5012")
    
    # --- Intento 1: API Local ---
    if not force_local:
        try:
            url = f"{local_api}/works"
            params = {"filter": f"author.id:{oa_id_clean}", "per_page": 200}
            with httpx.Client(verify=False, timeout=30) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    works = resp.json().get('results', [])
                    for w in works:
                        doi = w.get('doi') or w.get('id')
                        if doi:
                            doi_clean = str(doi).replace('https://doi.org/', '').replace('http://doi.org/', '').strip('/')
                            if doi_clean and doi_clean not in metadatos:
                                metadatos[doi_clean] = {
                                    'Title': w.get('title', 'Sin Título'),
                                    'Year': w.get('publication_year', 0),
                                    'DOI': doi_clean,
                                    'Source': 'OpenAlex_AuthorID_Local',
                                    'Authors': None,
                                    'Cited_by': w.get('cited_by_count', 0),
                                    'Abstract': None,
                                    '_raw_oa': w  # Conservar raw para enriquecimiento posterior
                                }
                    if metadatos:
                        print(f"    [OpenAlex Local] Author {oa_id_clean}: {len(metadatos)} trabajos.")
                        return metadatos
        except Exception as e:
            print(f"    [WARN] Error API Local OpenAlex Author: {e}")
    
    # --- Intento 2: API Oficial (pyalex) ---
    try:
        from pyalex import Works
        results = Works().filter(authorships={"author": {"id": oa_id_clean}}).paginate(per_page=200)
        for page in results:
            for w in page:
                doi = w.get('doi') or w.get('id')
                if doi:
                    doi_clean = str(doi).replace('https://doi.org/', '').replace('http://doi.org/', '').strip('/')
                    if doi_clean and doi_clean not in metadatos:
                        metadatos[doi_clean] = {
                            'Title': w.get('title', 'Sin Título'),
                            'Year': w.get('publication_year', 0),
                            'DOI': doi_clean,
                            'Source': 'OpenAlex_AuthorID_Oficial',
                            'Authors': None,
                            'Cited_by': w.get('cited_by_count', 0),
                            'Abstract': deconstruct_abstract(w.get('abstract_inverted_index'))
                        }
        if metadatos:
            print(f"    [OpenAlex Oficial] Author {oa_id_clean}: {len(metadatos)} trabajos.")
    except Exception as e:
        print(f"    [WARN] Error API Oficial OpenAlex Author: {e}")
    
    return metadatos



def process_and_ingest_snii(json_path, force=False, force_local=False, target_name=None, limit_acads=None, confirmed_only=False, offset=0):
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

    if offset > 0:
        print(f"⏭️ Aplicando offset de {offset} registros.")
        registros_to_process = registros_to_process[offset:]

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
        # Caso A: Tiene ORCID y match confirmado (máxima confianza)
        # Caso B: Solo tiene OpenAlex ID (sin ORCID, pero con match validado por LLM o por búsqueda)
        openalex_id = data.get('matched_openalex_id')
        has_openalex_id = openalex_id and openalex_id is not False
        
        is_false_positive = audit.get('verdict') == 'FALSE_POSITIVE'
        is_valid_match = data.get('match') is True and not is_false_positive
        
        # Permitir ingesta si hay match válido + (ORCID o OpenAlex ID)
        is_safe_match = is_valid_match and (orcid or has_openalex_id)
        
        if not is_safe_match:
            print(f"  ℹ️ Saltando recolección de publicaciones (Match: {data.get('match')}, Veredicto: {audit.get('verdict')}, ORCID: {orcid}, OA_ID: {openalex_id})")
            continue

        # 4. Verificar existencia de publicaciones (evitar procesar de nuevo si no se fuerza)
        if hasattr(graph_store, 'check_academic_exists') and graph_store.check_academic_exists(academic_name) and not force:
            print(f"  📍 Publicaciones ya existen en Neo4j. Saltando recolección API...")
            continue

        # 5. Recolectar publicaciones según el caso disponible
        meta_unificada = {}
        
        if orcid:
            # Caso A: ORCID disponible — fuente más fiable
            print(f"  🧬 Iniciando recopilación por ORCID: {orcid}...")
            meta_unificada = obtener_metadatos_de_orcid(orcid)
        
        if not meta_unificada and has_openalex_id:
            # Caso B: Sin ORCID o ORCID sin resultados — usar OpenAlex Author ID
            print(f"  🔍 Sin resultados por ORCID. Recopilando por OpenAlex ID: {openalex_id}...")
            meta_unificada = obtener_metadatos_de_openalex_autor(openalex_id, force_local=force_local)

        if not meta_unificada:
            print("  -> Sin publicaciones rastreables por ninguna fuente.")
            continue
            
        print(f"  -> {len(meta_unificada)} artículos únicos. Enriqueciendo...")

        # --- OPT: Batch processing DOIs ---
        dois_to_fetch = [doi for doi in meta_unificada.keys() if not doi.startswith('orcid-work:')]
        non_doi_works = {doi: rec for doi, rec in meta_unificada.items() if doi.startswith('orcid-work:')}
        
        # 1. Fetch OpenAlex data in batches if possible
        openalex_blocked = force_local or getattr(openalex_utils, 'OFFICIAL_API_BLOCKED', False)
        batch_results = {}
        if dois_to_fetch:
            print(f"      📡 Consultando lote de {len(dois_to_fetch)} DOIs...")
            batch_results = openalex_utils.get_works_batch(dois_to_fetch, local_only=openalex_blocked)
        
        neo4j_batch = []
        batch_payloads = []
        batch_texts = []

        # 2. Process combined results (Batch + Single Fallbacks)
        all_processing_tasks = list(meta_unificada.items())
        
        for doi, record in all_processing_tasks:
            text_for_embedding = f"Title: {record.get('Title')}\n"
            work = None
            
            # Recuperar trabajo de OpenAlex (de batch o búsqueda individual si falla)
            _doi_clean = doi if not doi.startswith('orcid-work:') else None
            _doi_key = _doi_clean.lower() if _doi_clean else None
            
            if _doi_key and _doi_key in batch_results:
                work = batch_results[_doi_key]
            elif not _doi_clean or _doi_key not in batch_results:
                # Si no tiene DOI o no se encontró en el lote (posible título), intentar búsqueda individual
                try:
                    work = openalex_utils.get_work(doi=_doi_clean, title=record.get('Title'), local_only=openalex_blocked)
                except Exception:
                    work = None

            if work:
                authorships = work.get('authorships', [])
                record['Authors'] = "; ".join([au['author']['display_name'] for au in authorships])
                record['Keywords_oa'] = "; ".join([kw['display_name'] for kw in work.get('keywords', [])])
                record['Abstract_oa'] = deconstruct_abstract(work.get('abstract_inverted_index'))
                record['openalex_url'] = work.get('id')
                if record['Abstract_oa']: record['Abstract'] = record['Abstract_oa']
                record['Cited_by'] = work.get('cited_by_count', record.get('Cited_by', 0))
                record['Source'] += ' + OpenAlex'

            # --- Qdrant logic ---
            qdrant_exists = False
            if hasattr(vector_store, 'check_document_exists'):
                qdrant_exists = vector_store.check_document_exists(doi=doi, title=record.get("Title"))
                
            if not qdrant_exists:
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

            # --- Prepare Neo4j Batch Data ---
            # Determinar system_id (igual que en add_api_paper)
            if orcid:
                system_id = orcid
            else:
                system_id = academic_name # Simplified for batch
            
            # Funders/Awards extraction
            funders_list = []
            awards_list = []
            grants = work.get("grants", []) if work else []
            for g in grants:
                if g.get("funder_display_name"):
                    funders_list.append({"name": g.get("funder_display_name"), "openalex_id": g.get("funder") or ""})
                if g.get("award_id"):
                    awards_list.append(g.get("award_id"))

            audit = data.get('audit', {})
            neo4j_batch.append({
                "system_id": system_id,
                "academic_name": academic_name,
                "orcid": orcid,
                "doi": doi,
                "title": record.get("Title", "No Title"),
                "year": int(record.get("Year", 0)) if record.get("Year") else 0,
                "citations": int(record.get("Cited_by", 0)) if record.get("Cited_by") else 0,
                "raw_metadata": json.dumps(record, ensure_ascii=False),
                "audit_verdict": audit.get('verdict'),
                "audit_reason": audit.get('reason'),
                "audit_confidence": audit.get('confidence'),
                "audit_timestamp": audit.get('timestamp'),
                "funders": funders_list,
                "awards": list(set(awards_list))
            })

        # --- Final Batch Ingestion ---
        if neo4j_batch:
            print(f"      🗄️ Insertando lote de {len(neo4j_batch)} artículos en Neo4j...")
            graph_store.add_api_papers_batch(neo4j_batch)
            
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
    parser.add_argument("--offset", type=int, default=0, help="Empezar desde el registro N")
    args = parser.parse_args()
    
    try:
        process_and_ingest_snii(
            args.input, 
            force=args.force, 
            force_local=args.local, 
            target_name=args.name, 
            limit_acads=args.limit,
            confirmed_only=args.confirmed_only,
            offset=args.offset
        )
    finally:
        graph_store.close()
        print("\n🎉 Proceso completado.")
