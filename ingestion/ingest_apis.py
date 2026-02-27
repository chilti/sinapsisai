"""
ingest_apis.py
Toma profesores_datos.json y extrae artículos desde Scopus, ORCID y OpenAlex,
guardándolos en Qdrant (colección separada: api_papers) y Neo4j (Label: APIPaper, ligados a Academic).
Conserva todos los campos de metadata descargados.
"""

import sys
import os
import json
import time
import requests
import pyalex
import httpx
from dotenv import load_dotenv

import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore

# Es preferible que inicialice si están las librerías
try:
    import pybliometrics
    from pybliometrics.scopus import AuthorRetrieval
    pybliometrics.scopus.init()
except Exception:
    print("Nota: pybliometrics puede no estar completamente configurado con la API key de Scopus.")

load_dotenv()

pyalex.config.email = os.getenv("EMAIL_ADDRESS", "[EMAIL_ADDRESS]")

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
            # Usar la SDK nativa para forzar la carga en memoria si no lo está
            model = lms.embedding_model(model_name)
            
            # El SDK de lms suele soportar batches o iteraciones directas
            for text in texts:
                clean_t = str(text) if text else " "
                emb = model.embed(clean_t)
                all_embeddings.append(emb)
            return all_embeddings
        except ImportError:
            print("⚠️ Error: La librería 'lmstudio' no está instalada. Ejecuta 'pip install lmstudio'. Cayendo a LangChain...")

    # Fallback / Modo servidor estándar (LangChain OpenAI)
    for i in range(0, len(texts), batch_size):
        batch = [str(t) if t else " " for t in texts[i:i+batch_size]]
        embs = embeddings_model.embed_documents(batch)
        all_embeddings.extend(embs)
    return all_embeddings

# --- Inicializar Bases de Datos Diferenciadas ---
# Colección distinta para embeddings generados por API
vector_store = QdrantStore(collection_name="api_papers")
graph_store = Neo4jGraphStore()

# --- Helpers de APIs ---

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
    print(f"  -> {scopus_ids}")

    if not scopus_ids: return {}
    if isinstance(scopus_ids, str): scopus_ids = [scopus_ids]
    metadatos = {}
    for sid in scopus_ids:
        # Extraer ID numérico si viene como URL (https://www.scopus.com/authid/detail.uri?authorId=...)
        if 'authorId=' in sid:
            sid = sid.split('authorId=')[-1].split('&')[0]
            
        try:
            au = AuthorRetrieval(sid)
            docs = list(au.get_documents())
            print(f"    [Scopus] ID {sid}: {len(docs)} documentos encontrados. Con DOI: {sum(1 for p in docs if p.doi)}")
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

def _resolve_arxiv_to_doi(arxiv_id: str) -> str | None:
    """Intenta resolver un arXiv ID a un DOI oficial via OpenAlex."""
    if not arxiv_id:
        return None
    # Normalizar: puede venir como 'arxiv:XXXX.XXXXX' o solo 'XXXX.XXXXX'
    clean_id = arxiv_id.lower().replace("arxiv:", "").strip()
    try:
        url = f"https://api.openalex.org/works/https://arxiv.org/abs/{clean_id}"
        r = requests.get(url, headers={"User-Agent": "SinapsisAI/1.0"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            doi = data.get("doi", "")
            if doi:
                return doi.replace("https://doi.org/", "")
    except Exception:
        pass
    return None

def obtener_metadatos_de_orcid(orcid_url):
    print(f"  -> {orcid_url}")
    if not orcid_url or 'http' not in orcid_url: return {}
    orcid_id = orcid_url.rstrip('/').split('/')[-1]
    metadatos = {}
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            for work_group in response.json().get('group', []):
                summary = work_group.get('work-summary', [{}])[0]
                
                # Manejar de forma segura external-ids nulo (puede ser None dict en JSON)
                ext_ids_node = summary.get('external-ids')
                ext_ids_list = []
                if ext_ids_node and isinstance(ext_ids_node, dict):
                    ext_ids_list = ext_ids_node.get('external-id', [])
                    # ORCID a veces regresa un solo dict si hay 1 solo ID, en lugar de lista
                    if isinstance(ext_ids_list, dict):
                        ext_ids_list = [ext_ids_list]

                # Buscar DOI primero
                doi = next((eid.get('external-id-value') for eid in ext_ids_list 
                            if isinstance(eid, dict) and eid.get('external-id-type') == 'doi'), None)
                
                # Si no hay DOI, intentar resolver desde arXiv
                if not doi:
                    arxiv_id = next((eid.get('external-id-value') for eid in ext_ids_list 
                                     if isinstance(eid, dict) and eid.get('external-id-type') == 'arxiv'), None)
                    if arxiv_id:
                        doi = _resolve_arxiv_to_doi(arxiv_id)
                        if doi:
                            print(f"    ✅ arXiv {arxiv_id} → DOI {doi}")
                
                pub_date = summary.get('publication-date', {}) or {}
                
                if doi and doi not in metadatos:
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
    return metadatos

# --- Lógica principal de ingesta ---

def process_and_ingest_academics(json_path, force=False, force_local=False, target_name=None):
    if not os.path.exists(json_path):
        print(f"No se encontró el archivo: {json_path}")
        return
        
    with open(json_path, 'r', encoding='utf-8') as f:
        academicos = json.load(f)

    for academic_name, data in academicos.items():
        if target_name and target_name.lower() not in academic_name.lower():
            continue
        
        print(f"\n[{academic_name}] Procesando...")
        print(f"  -> {data}")

        original_name = data.get('original_name', academic_name)
        entity_name = data.get('entity', 'UNAM')
        
        # 1. Checar flag previas
        if data.get('already_in_db', False) and not force:
            mapped_name = data.get('mapped_name', academic_name)
            print(f"\n[{academic_name}] Ya existe como '{mapped_name}' (cached en excel). Saltar recoleccion.")
            graph_store.add_academic_affiliation(mapped_name, entity_name)
            continue
            
        # 2. Checar base de datos directo (por si se interrumpió y se vuelve a correr)
        if hasattr(graph_store, 'check_academic_exists') and graph_store.check_academic_exists(academic_name) and not force:
            print(f"\n[{academic_name}] Ya existe en Neo4j. Saltando recopilación API y agregando afiliación a '{entity_name}'.")
            graph_store.add_academic_affiliation(academic_name, entity_name)
            continue

        scopus_id = data.get('scopus', [])
        orcid = data.get('orcid', '')
        
        print(f"\n[{academic_name}] Iniciando recopilación API...")
        
        # 1. Traemos la lista de DOIs que ha publicado
        meta_scopus = obtener_metadatos_de_scopus(scopus_id)
        meta_orcid = obtener_metadatos_de_orcid(orcid)
        
        # Combinar priorizando Scopus
        meta_unificada = meta_scopus.copy()
        for doi, m_data in meta_orcid.items():
            if doi not in meta_unificada:
                meta_unificada[doi] = m_data

        print(f"  -> {len(meta_scopus)} artículos únicos encontrados en Scopus. Enriqueciendo...")
        print(f"  -> {len(meta_orcid)} artículos únicos encontrados en ORCID. Enriqueciendo...")
        print(f"  -> {len(meta_unificada)} artículos únicos encontrados. Enriqueciendo...")

        if not meta_unificada:
            print("  -> Sin publicaciones rastreables.")
            continue
            
        print(f"  -> {len(meta_unificada)} artículos únicos encontrados. Enriqueciendo...")

        batch_payloads = []
        batch_texts = []
        
        for doi, base_metadata in meta_unificada.items():
            record = base_metadata.copy()
            text_for_embedding = f"Title: {record.get('Title')}\n"
            
            # Enriquecemos con OpenAlex
            try:
                work = pyalex.Works()["https://doi.org/" + doi]
                authorships = work.get('authorships', [])
                record['Authors'] = "; ".join([au['author']['display_name'] for au in authorships])
                record['Keywords_oa'] = "; ".join([kw['display_name'] for kw in work.get('keywords', [])])
                record['Abstract_oa'] = deconstruct_abstract(work.get('abstract_inverted_index'))
                
                if record['Abstract_oa']:
                    record['Abstract'] = record['Abstract_oa']
                    
                record['Cited_by'] = work.get('cited_by_count', record.get('Cited_by', 0))
                topics = []
                for t in work.get('topics', []):
                    try:
                        topics.append({
                            'domain': t.get('domain', {}).get('display_name'),
                            'field': t.get('field', {}).get('display_name'),
                            'subfield': t.get('subfield', {}).get('display_name'),
                            'topic': t.get('display_name')
                        })
                    except:
                        pass
                record['OpenAlex_Topics'] = topics
                record['Source'] += ' + OpenAlex'
            except Exception:
                pass # Si OpenAlex falla, seguimos con los datos base
            
            # Qdrant solo necesita un texto para el embedding y un payload
            if record.get('Abstract'):
                text_for_embedding += f"Abstract: {record['Abstract']}"
                
            payload_qdrant = {
                "academic_name": academic_name,
                "doi": doi,
                "title": record.get("Title"),
                "year": record.get("Year"),
                "source": record.get("Source"),
                "text": text_for_embedding
            }
            batch_texts.append(text_for_embedding)
            batch_payloads.append(payload_qdrant)
            
            # Formatear paramétros para Neo4j (usa raw_metadata para guardar TODOS los campos en json)
            neo4j_data = {
                "doi": doi,
                "title": record.get("Title", "No Title"),
                "year": record.get("Year", 0),
                "citations": record.get("Cited_by", 0),
                "raw_metadata": record # TODO EL JSON
            }
            # Guardamos la relación en el grafo
            graph_store.add_api_paper(neo4j_data, academic_name=academic_name)
            time.sleep(0.05)
            
        # Afiliación del académico a su Entidad
        graph_store.add_academic_affiliation(academic_name, entity_name)
            
        # Ingesta en Qdrant por lotes de este académico para no saturar al LLM
        print(f"  -> Vectorizando {len(batch_texts)} textos de artículos e insertando en 'api_papers'...")
        try:
            # Por limitaciones de tamaño del LLM embebedor, vamos de 32 en 32
            embeddings = []
            for i in range(0, len(batch_texts), 32):
                batch_subset = batch_texts[i:i+32]
                embeddings.extend(get_embeddings(batch_subset, force_local=force_local))
                
            vector_store.add_documents(batch_payloads, embeddings)
            print(f"  ✅ Guardado en Qdrant y Neo4j exitosamente para {academic_name}.")
        except Exception as e:
            print(f"  ❌ Error generando vectores para {academic_name}: {e}")

if __name__ == "__main__":
    base_json = os.path.join(os.path.dirname(__file__), "profesores_Instituto_de_Ciencias_Nucleares.json")
    force_run = False
    force_local = False
    target_name = None
    
    # Parseo manual para soportar --name "Nombre"
    args = []
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--name" and i + 1 < len(sys.argv):
            target_name = sys.argv[i+1]
            i += 2
        elif arg.startswith("--"):
            i += 1
        else:
            args.append(arg)
            i += 1
            
    flags = [a for a in sys.argv[1:] if a.startswith("--") and not a == "--name"]
    
    if len(args) > 0:
        base_json = args[0]
        
    if "--force" in flags:
        force_run = True
        print("⚠️ Flag --force detectada: Se reescribirá la información de académicos existentes.")
        
    if "--local" in flags:
        force_local = True
        print("⚠️ Flag --local detectada: Usando SDK nativa de lmstudio para embeddings.")
        
    if target_name:
        print(f"🔎 Filtrando ejecución solo para el académico que coincida con: '{target_name}'")
        
    process_and_ingest_academics(base_json, force=force_run, force_local=force_local, target_name=target_name)
    print("\n🎉 Proceso global de ingesta de APIs completado.")
