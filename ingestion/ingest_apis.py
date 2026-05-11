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
from dotenv import load_dotenv, find_dotenv

import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client
from ingestion import openalex_utils

# Es preferible que inicialice si están las librerías
try:
    import pybliometrics
    from pybliometrics.scopus import AuthorRetrieval
    pybliometrics.scopus.init()
except Exception:
    print("Nota: pybliometrics puede no estar completamente configurado con la API key de Scopus.")

# Cargar .env de forma robusta asumiendo que está un nivel arriba (raíz del proyecto)
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
            # Tomar modelo desde env para evitar variable indefinida
            _local_model_name = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
            model = lms.embedding_model(_local_model_name)
            
            for text in texts:
                clean_t = str(text) if text else " "
                emb = model.embed(clean_t)
                # Normalizar el objeto retornado por lmstudio (puede ser objeto, lista o array)
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
    if not scopus_ids: return {}
    
    # Si viene como representación de lista en string "['123', '456']"
    import ast
    if isinstance(scopus_ids, str):
        try:
            parsed = ast.literal_eval(scopus_ids)
            if isinstance(parsed, list):
                scopus_ids = parsed
            else:
                scopus_ids = [scopus_ids]
        except Exception:
            # Si falla, podría ser separado por comas
            scopus_ids = [s.strip() for s in scopus_ids.split(',')]
            
    if not isinstance(scopus_ids, list):
        scopus_ids = [scopus_ids]

    metadatos = {}
    for sid in scopus_ids:
        if not sid: continue
        sid = str(sid).strip()
        # Extraer ID numérico si viene como URL (https://www.scopus.com/authid/detail.uri?authorId=...)
        if 'authorId=' in sid:
            sid = sid.split('authorId=')[-1].split('&')[0]
        # Extraer usando nuestra regex limpia por si hay basura
        import re
        match = re.search(r'\d{8,12}', sid)
        if match:
            sid = match.group(0)
            
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
    if not orcid_url: return {}
    
    # Extraer el ID (los 16 dígitos) por si viene como URL o como string puro
    orcid_url = str(orcid_url).strip()
    orcid_id = orcid_url.rstrip('/').split('/')[-1]
    
    # Validar formato básico de ORCID (ej: 0000-0001-2345-6789 o termina en X)
    import re
    if not re.search(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', orcid_id, re.IGNORECASE):
        print(f"    [ORCID] Formato inválido ignorado: '{orcid_url}'")
        return {}

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

                # Buscar DOI primero y normalizarlo (ORCID puede devolver URL completa)
                _doi_raw = next((eid.get('external-id-value') for eid in ext_ids_list
                                 if isinstance(eid, dict) and eid.get('external-id-type') == 'doi'), None)
                if _doi_raw:
                    doi = (str(_doi_raw).strip()
                           .replace('https://doi.org/', '')
                           .replace('http://doi.org/',  '')
                           .replace('https://dx.doi.org/', '')
                           .replace('http://dx.doi.org/', '')
                           .strip('/'))
                else:
                    doi = None
                
                # Si no hay DOI, intentar resolver desde arXiv
                if not doi:
                    arxiv_id = next((eid.get('external-id-value') for eid in ext_ids_list 
                                     if isinstance(eid, dict) and eid.get('external-id-type') == 'arxiv'), None)
                    if arxiv_id:
                        doi = _resolve_arxiv_to_doi(arxiv_id)
                        if doi:
                            print(f"    ✅ arXiv {arxiv_id} → DOI {doi}")
                
                # Si sigue sin haber DOI, usar el put-code interno de ORCID como ID único
                if not doi:
                    put_code = summary.get('put-code')
                    if put_code:
                        doi = f"orcid-work:{put_code}"

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
    
    if metadatos:
        print(f"    [ORCID] ID {orcid_id}: {len(metadatos)} documentos encontrados.")
        
    return metadatos

def obtener_metadatos_de_openalex_autor(openalex_author_id: str, force_local: bool = False) -> dict:
    """Obtiene los trabajos de un autor directamente desde su OpenAlex Author ID.
    Soporta tanto la API local (--local) como la API oficial de pyalex.
    """
    if not openalex_author_id:
        return {}
    
    oa_id_clean = str(openalex_author_id).split('/')[-1].strip()
    metadatos = {}
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

# --- Lógica principal de ingesta ---

def process_and_ingest_academics(json_path, force=False, force_local=False, target_name=None, is_snii=False, limit_acads=None, override_entity=None, institution_name=None, dependency_name=None, subdependency_name=None, save_to_ch=False, source_override=None):
    if not os.path.exists(json_path):
        print(f"No se encontró el archivo: {json_path}")
        return
        
    with open(json_path, 'r', encoding='utf-8') as f:
        academicos = json.load(f)

    # Cargar padrón SNII para verificación de estatus
    from match_snii_orcid import SNII_PATH, normalize_text
    snii_names = set()
    if os.path.exists(SNII_PATH):
        try:
            df_snii = pd.read_excel(SNII_PATH, sheet_name='4T_2025 (44,794)')
            # Usar columna de nombre robusta
            name_col = next((c for c in df_snii.columns if 'NOMBRE' in c.upper()), df_snii.columns[0])
            snii_names = {normalize_text(str(n)).upper() for n in df_snii[name_col].dropna()}
        except Exception as e:
            print(f"⚠️ No se pudo cargar el padrón SNII para validación: {e}")

    count = 0
    for academic_name, data in academicos.items():
        if limit_acads and count >= limit_acads:
            print(f"🛑 Límite de {limit_acads} académicos alcanzado para este archivo.")
            break
            
        if target_name and target_name.lower() not in academic_name.lower():
            continue
            
        count += 1
        original_name = data.get('original_name', academic_name)
        entity_name = override_entity or data.get('entity', 'UNAM')
        
        # Lógica de Integridad SNII
        norm_name = normalize_text(academic_name).upper()
        in_snii_catalog = norm_name in snii_names
        
        if is_snii or in_snii_catalog:
            print(f"🧬 [{academic_name}] Confirmado como SNII (Catálogo o Fuente)...")
            graph_store.set_academic_snii(academic_name, True)
            current_is_snii = True
        else:
            print(f"📝 [{academic_name}] No detectado en SNII. Registrando como Personal Académico Extra...")
            graph_store.set_academic_snii(academic_name, False)
            current_is_snii = False
            
            # Tarea 1.3: Agregar a extra_academics_matches.json si no es SNII
            extra_path = os.path.join("data", "extra_academics_matches.json")
            extra_data = []
            if os.path.exists(extra_path):
                with open(extra_path, "r", encoding="utf-8") as ef:
                    try: extra_data = json.load(ef)
                    except: extra_data = []
            
            # Verificar si ya existe en el extra JSON
            if not any(normalize_text(r.get('snii_author', '')).upper() == norm_name for r in extra_data):
                extra_entry = {
                    "snii_author": academic_name,
                    "snii_institution": institution_name,
                    "snii_dependency": dependency_name or entity_name,
                    "snii_subdependency": subdependency_name or "NO APLICA",
                    "snii_cvu": data.get('cvu', ''),
                    "match": True if data.get('orcid') or data.get('openalex_id') or data.get('scopus') else False,
                    "matched_orcid": data.get('orcid'),
                    "matched_openalex_id": data.get('openalex_id'),
                    "scopus_ids": data.get('scopus'),
                    "source": "Manual Ingestion (Non-SNII)",
                    "is_snii": False
                }
                extra_data.append(extra_entry)
                with open(extra_path, "w", encoding="utf-8") as ef:
                    json.dump(extra_data, ef, ensure_ascii=False, indent=2)

        # 1. Checar flag previas
        if data.get('already_in_db', False) and not force:
            mapped_name = data.get('mapped_name', academic_name)
            print(f"\n[{academic_name}] Ya existe como '{mapped_name}' (cached en excel). Saltar recoleccion.")
            graph_store.add_academic_full_affiliation(mapped_name, institution_name, dependency_name, subdependency_name)
            continue
            
        # 2. Checar base de datos directo (por si se interrumpió y se vuelve a correr)
        # Si ya es SNII en Neo4j, respetamos ese estatus y solo actualizamos afiliación
        is_already_snii = False
        if hasattr(graph_store, 'get_academic_ids'):
            meta = graph_store.get_academic_ids(academic_name)
            if meta and meta.get('is_snii'):
                is_already_snii = True

        if (is_already_snii or (hasattr(graph_store, 'check_academic_exists') and graph_store.check_academic_exists(academic_name))) and not force:
            print(f"\n[{academic_name}] Ya existe en Neo4j (SNII={is_already_snii}). Saltando recopilación API y asegurando afiliación.")
            graph_store.add_academic_full_affiliation(academic_name, institution_name, dependency_name, subdependency_name)
            continue

        scopus_id = data.get('scopus', [])
        orcid = data.get('orcid', '') or ''
        siia_url = data.get('siia', '')
        
        # --- Enriquecer con IDs guardados en Neo4j (por pipeline SNII) ---
        # El matching SNII puede haber descubierto ORCID o OpenAlex IDs que no están en el JSON
        neo4j_ids = {"orcid": None, "openalex_id": None}
        if hasattr(graph_store, 'get_academic_ids'):
            neo4j_ids = graph_store.get_academic_ids(academic_name)
        orcid = orcid or neo4j_ids.get('orcid') or ''
        openalex_author_id = data.get('openalex_id') or neo4j_ids.get('openalex_id')
        
        print(f"\n[{academic_name}] Iniciando recopilación API... ORCID={orcid or 'N/A'} | OA_ID={openalex_author_id or 'N/A'}")
        
        # 1. Scopus (si tiene ID)
        meta_scopus = obtener_metadatos_de_scopus(scopus_id)
        
        # 2. ORCID (si tiene ID)
        meta_orcid = obtener_metadatos_de_orcid(orcid) if orcid else {}
        
        # 3. OpenAlex Author ID (respeta --local)
        meta_oa_author = {}
        if openalex_author_id:
            meta_oa_author = obtener_metadatos_de_openalex_autor(openalex_author_id, force_local=force_local)
        
        # Combinar priorizando Scopus > ORCID > OpenAlex Author ID (de mayor a menor confianza)
        def _clean_t(t): return "".join(c for c in str(t).lower() if c.isalnum())
        scopus_titles = {_clean_t(d.get('Title', '')) for d in meta_scopus.values() if d.get('Title')}
        orcid_titles  = {_clean_t(d.get('Title', '')) for d in meta_orcid.values() if d.get('Title')}
        
        meta_unificada = meta_scopus.copy()
        
        # Fusionar ORCID
        for doi, m_data in meta_orcid.items():
            if doi in meta_unificada: continue
            c_title = _clean_t(m_data.get('Title', ''))
            if doi.startswith('orcid-work') and c_title in scopus_titles and c_title != "": continue
            if c_title in scopus_titles and c_title != "": continue
            meta_unificada[doi] = m_data
        
        # Fusionar OpenAlex Author ID (evitar duplicados por título)
        all_titles_so_far = scopus_titles | orcid_titles
        for doi, m_data in meta_oa_author.items():
            if doi in meta_unificada: continue
            c_title = _clean_t(m_data.get('Title', ''))
            if c_title in all_titles_so_far and c_title != "": continue
            meta_unificada[doi] = m_data

        

        if not meta_unificada:
            print("  -> Sin publicaciones rastreables.")
            continue
            
        print(f"  -> {len(meta_unificada)} artículos únicos encontrados. Enriqueciendo...")

        # --- OPT: Batch OpenAlex fetching (una sola llamada para todos los DOIs) ---
        dois_to_fetch = [doi for doi in meta_unificada.keys() if not doi.startswith('orcid-work:')]
        openalex_blocked = force_local or getattr(openalex_utils, 'OFFICIAL_API_BLOCKED', False)
        batch_results = {}
        if dois_to_fetch:
            print(f"      📡 Consultando lote de {len(dois_to_fetch)} DOIs en OpenAlex...")
            batch_results = openalex_utils.get_works_batch(dois_to_fetch, local_only=openalex_blocked)

        neo4j_batch = []
        batch_payloads = []
        batch_texts = []

        for doi, base_metadata in meta_unificada.items():
            record = base_metadata.copy()
            text_for_embedding = f"Title: {record.get('Title')}\n"
            paper_exists = False

            # Recuperar el trabajo de OpenAlex desde el lote o con fallback individual
            _doi_clean = (doi.replace('https://doi.org/', '')
                             .replace('http://doi.org/', '')
                             .replace('https://dx.doi.org/', '')
                             .strip('/') if doi and not doi.startswith('orcid-work:') else None)
            _doi_key = _doi_clean.lower() if _doi_clean else None
            work = None

            if _doi_key and _doi_key in batch_results:
                work = batch_results[_doi_key]
            elif _doi_clean:
                # Fallback: paper ya en grafo → saltar enriquecimiento
                if graph_store.check_paper_exists(_doi_clean):
                    print(f"      📍 Paper {_doi_clean} ya existe en el grafo. Saltando OpenAlex...")
                    paper_exists = True
                else:
                    try:
                        work = openalex_utils.get_work(doi=_doi_clean, title=record.get('Title'), local_only=openalex_blocked)
                        if not openalex_blocked and getattr(openalex_utils, 'OFFICIAL_API_BLOCKED', False):
                            openalex_blocked = True
                    except Exception as e:
                        print(f"    Advertencia en OpenAlex para {doi}: {e}")

            if work:
                authorships = work.get('authorships', [])
                record['Authors'] = "; ".join([au['author']['display_name'] for au in authorships])
                record['Keywords_oa'] = "; ".join([kw['display_name'] for kw in work.get('keywords', [])])
                record['Abstract_oa'] = deconstruct_abstract(work.get('abstract_inverted_index'))
                record['openalex_url'] = work.get('id')
                record['Title'] = work.get('title') or record.get('Title')
                
                if record['Abstract_oa']:
                    record['Abstract'] = record['Abstract_oa']
                    
                record['Cited_by'] = work.get('cited_by_count', record.get('Cited_by', 0))
                record['fwci'] = work.get('fwci', None)
                record['open_access'] = work.get('open_access', {})

                if work.get('citation_normalized_percentile'):
                    perc_data = work['citation_normalized_percentile']
                    record['citation_normalized_percentile'] = perc_data.get('value', 0.0)
                    record['is_in_top_1_percent']  = perc_data.get('is_in_top_1_percent', False)
                    record['is_in_top_10_percent'] = perc_data.get('is_in_top_10_percent', False)

                cyp = work.get('cited_by_percentile_year') or {}
                record['cited_by_percentile_year_min'] = cyp.get('min')
                record['cited_by_percentile_year_max'] = cyp.get('max')
                record['counts_by_year']          = work.get('counts_by_year', [])
                record['referenced_works_count']  = work.get('referenced_works_count', 0)
                record['referenced_works']        = work.get('referenced_works', [])
                record['apc_paid_usd'] = (work.get('apc_paid') or {}).get('value_usd', 0) or 0
                record['apc_list_usd'] = (work.get('apc_list') or {}).get('value_usd', 0) or 0

                _auths = work.get('authorships', [])
                record['author_count']               = len(_auths)
                record['countries_distinct_count']   = work.get('countries_distinct_count', 0)
                record['institutions_distinct_count']= work.get('institutions_distinct_count', 0)
                record['countries'] = list({c for a in _auths for c in a.get('countries', [])})
                record['coauthor_institutions'] = [
                    {
                        'author': (a.get('author') or {}).get('display_name'),
                        'orcid':  (a.get('author') or {}).get('orcid'),
                        'position': a.get('author_position'),
                        'is_corresponding': a.get('is_corresponding', False),
                        'countries': a.get('countries', []),
                        'institutions': [
                            {'name': i.get('display_name'), 'ror': i.get('ror'),
                             'country': i.get('country_code'), 'type': i.get('type')}
                            for i in a.get('institutions', [])
                        ]
                    }
                    for a in _auths
                ]

                _loc = work.get('primary_location') or {}
                record['license']                    = _loc.get('license')
                record['any_repository_has_fulltext']= (work.get('open_access') or {}).get('any_repository_has_fulltext', False)
                record['oa_url']                     = (work.get('open_access') or {}).get('oa_url')
                record['locations_count']            = work.get('locations_count', 0)
                record['indexed_in']   = work.get('indexed_in', [])
                record['is_retracted'] = work.get('is_retracted', False)
                record['language']     = work.get('language', 'en')
                record['type']         = work.get('type', 'article')

                _src = _loc.get('source') or {}
                record['journal_is_oa']      = _src.get('is_oa', False)
                record['journal_is_in_doaj'] = _src.get('is_in_doaj', False)
                record['journal_is_core']    = _src.get('is_core', False)
                record['issn']               = _src.get('issn_l')
                record['journal_type']       = _src.get('type')

                pt = work.get('primary_topic') or {}
                record['primary_topic_name']     = pt.get('display_name')
                record['primary_topic_score']    = pt.get('score')
                record['primary_topic_field']    = (pt.get('field') or {}).get('display_name')
                record['primary_topic_subfield'] = (pt.get('subfield') or {}).get('display_name')
                record['primary_topic_domain']   = (pt.get('domain') or {}).get('display_name')

                topics = []
                for t in work.get('topics', []):
                    try:
                        topics.append({
                            'domain':   (t.get('domain') or {}).get('display_name'),
                            'field':    (t.get('field') or {}).get('display_name'),
                            'subfield': (t.get('subfield') or {}).get('display_name'),
                            'topic':    t.get('display_name'),
                            'score':    t.get('score'),
                        })
                    except Exception:
                        pass
                record['OpenAlex_Topics'] = topics
                record['keywords'] = [k.get('display_name') for k in work.get('keywords', [])[:15]]
                record['sustainable_development_goals'] = [
                    {'id': s.get('id', '').rstrip('/').split('/')[-1],
                     'display_name': s.get('display_name'),
                     'score': s.get('score')}
                    for s in work.get('sustainable_development_goals', [])
                ]
                record['Source'] += ' + OpenAlex'

            # --- Qdrant ---
            if not paper_exists:
                if record.get('Abstract'):
                    text_for_embedding += f"Abstract: {record['Abstract']}"
                    
                payload_qdrant = {
                    "academic_name": academic_name,
                    "doi":           doi,
                    "title":         record.get("Title"),
                    "year":          record.get("Year"),
                    "source":        record.get("Source"),
                    "entity":        entity_name,
                    "text":          text_for_embedding,
                    "is_oa":         (record.get("open_access") or {}).get("is_oa", False),
                    "oa_status":     (record.get("open_access") or {}).get("oa_status", "closed"),
                    "language":      record.get("language", "en"),
                    "fwci":          record.get("fwci"),
                    "country_codes": record.get("countries", []),
                    "indexed_in":    record.get("indexed_in", []),
                    "primary_topic_domain": record.get("primary_topic_domain"),
                }
                batch_texts.append(text_for_embedding)
                batch_payloads.append(payload_qdrant)

            # --- Acumular para Neo4j batch ---
            if not paper_exists:
                grants = work.get("grants", []) if work else []
                funders_list = []
                awards_list = []
                for g in grants:
                    if g.get("funder_display_name"):
                        funders_list.append({"name": g.get("funder_display_name"), "openalex_id": g.get("funder") or ""})
                    if g.get("award_id"):
                        awards_list.append(g.get("award_id"))

                scopus_str = "; ".join(scopus_id) if isinstance(scopus_id, list) else scopus_id
                neo4j_batch.append({
                    "system_id":    orcid or academic_name,
                    "academic_name": academic_name,
                    "orcid":        orcid or None,
                    "openalex_id":  openalex_author_id or None,
                    "scopus_id":    scopus_str,
                    "siia_url":     siia_url,
                    "entity_name":  entity_name,
                    "doi":          doi,
                    "paper_openalex_id": record.get("openalex_url"), # ID de OpenAlex para vincular citas
                    "title":        record.get("Title", "No Title"),
                    "year":         int(record.get("Year", 0)) if record.get("Year") else 0,
                    "citations":    int(record.get("Cited_by", 0)) if record.get("Cited_by") else 0,
                    "raw_metadata": json.dumps(record, ensure_ascii=False),
                    "funders":      funders_list,
                    "awards":       list(set(awards_list)),
                })

        # --- Inserción en lote en Neo4j ---
        if neo4j_batch:
            # Sincronización con ClickHouse (Dual Write)
            if save_to_ch:
                _sync_to_clickhouse(neo4j_batch, institution_name, dependency_name, subdependency_name, current_is_snii, source_override=source_override)

            if hasattr(graph_store, 'add_api_papers_batch'):
                print(f"      🗄️ Insertando lote de {len(neo4j_batch)} artículos en Neo4j...")
                graph_store.add_api_papers_batch(neo4j_batch)
            else:
                # Fallback al método individual si el grafo no soporta batch
                for item in neo4j_batch:
                    neo4j_data = {"doi": item["doi"], "title": item["title"], "year": item["year"],
                                  "citations": item["citations"], "raw_metadata": json.loads(item["raw_metadata"])}
                    graph_store.add_api_paper(neo4j_data, academic_name=item["academic_name"],
                                              orcid=item["orcid"], scopus_id=item["scopus_id"],
                                              siia_url=item["siia_url"], entity_name=item["entity_name"])

        # Afiliación del académico a su Entidad e Institución (3 niveles)
        graph_store.add_academic_full_affiliation(academic_name, institution_name, dependency_name, subdependency_name)
            
        # Vectorización e inserción en Qdrant
        if batch_texts:
            print(f"  -> Vectorizando {len(batch_texts)} textos de artículos e insertando en 'api_papers'...")
            try:
                embeddings = []
                for i in range(0, len(batch_texts), 32):
                    batch_subset = batch_texts[i:i+32]
                    embeddings.extend(get_embeddings(batch_subset, force_local=force_local))
                    
                vector_store.add_documents(batch_payloads, embeddings)
                print(f"  ✅ Guardado en Qdrant y Neo4j exitosamente para {academic_name}.")
            except Exception as e:
                print(f"  ❌ Error generando vectores para {academic_name}: {e}")
        else:
            print(f"  📍 Vectorización omitida (0 artículos nuevos). Guardado en Neo4j OK para {academic_name}.")



def _sync_to_clickhouse(batch_data, inst, dep, sub, is_snii, source_override=None):
    """Sincroniza los artículos con las tablas paper_author_map y paper_entity_map de ClickHouse."""
    try:
        import pandas as pd
        ch = ch_client.get_client()
        author_rows = []
        entity_rows = []
        
        for item in batch_data:
            doi = item['doi']
            raw = json.loads(item['raw_metadata'])
            ids = raw.get('ids', {})
            
            # Determinar banderas de indización
            src_ov = str(source_override).lower() if source_override else ""
            is_wos = 1 if (src_ov == 'wos' or 'wos' in ids or 'wos' in str(raw.get('indexed_in', [])).lower()) else 0
            is_scopus = 1 if (src_ov == 'scopus' or 'scopus' in ids or 'scopus' in str(raw.get('indexed_in', [])).lower()) else 0
            is_pubmed = 1 if (src_ov == 'pubmed' or 'pmid' in ids) else 0
            is_doaj = 1 if (src_ov == 'doaj' or raw.get('journal_is_in_doaj')) else 0

            # 1. Preparar fila para paper_author_map (Capacidad Instalada)
            author_rows.append({
                'paper_id': doi,
                'academic_name': item['academic_name'],
                'cvu': item.get('cvu', ''),
                'orcid': item['orcid'] or '',
                'openalex_id': item['openalex_id'] or '',
                'institution': inst or '',
                'institution_ror': '',
                'dependency': dep or '',
                'dependency_id': '',
                'subdependency': sub or '',
                'subdependency_id': '',
                'paper_title': item['title'],
                'paper_year': int(item['year']),
                'citations': int(item['citations']),
                'is_snii': 1 if is_snii else 0,
                'is_wos': is_wos,
                'is_scopus': is_scopus,
                'is_pubmed': is_pubmed,
                'is_openalex': 1,
                'is_doaj': is_doaj,
                'is_semantic_scholar': 1 if 'mag' in ids else 0,
                'is_dimensions': 1 if 'mag' in ids else 0,
                'is_lens': 1 if 'mag' in ids or 'pmid' in ids else 0,
                'source': f'Ingest_APIs_{source_override}' if source_override else 'Ingest_APIs_Dual'
            })
            
            # 2. Preparar fila para paper_entity_map (Producción Institucional)
            entity_rows.append({
                'paper_id': doi,
                'institution': inst or '',
                'institution_ror': '',
                'dependency': dep or '',
                'dependency_id': '',
                'subdependency': sub or '',
                'subdependency_id': '',
                'paper_title': item['title'],
                'paper_year': int(item['year']),
                'citations': int(item['citations']),
                'is_wos': is_wos,
                'is_scopus': is_scopus,
                'is_pubmed': is_pubmed,
                'is_openalex': 1,
                'is_doaj': is_doaj,
                'is_semantic_scholar': 1 if 'mag' in ids else 0,
                'is_dimensions': 1 if 'mag' in ids else 0,
                'is_lens': 1 if 'mag' in ids or 'pmid' in ids else 0,
                'source': f'Entity_Sync_{source_override}' if source_override else 'Ingest_APIs_Entity_Sync'
            })
            
        if author_rows:
            ch.insert_df('paper_author_map', pd.DataFrame(author_rows))
        if entity_rows:
            df_ent = pd.DataFrame(entity_rows).drop_duplicates(subset=['paper_id', 'institution', 'dependency', 'subdependency'])
            ch.insert_df('paper_entity_map', df_ent)
            print(f"      📊 [ClickHouse] {len(df_ent)} entidades únicas sincronizadas.")
            
        print(f"      📊 [ClickHouse] {len(author_rows)} autores sincronizados (Dual Write).")
    except Exception as e:
        print(f"      [WARN] Error sincronizando con ClickHouse: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingesta de metadatos desde APIs para académicos UNAM-SNII")
    parser.add_argument("input", nargs="?", help="Archivo JSON o DIRECTORIO a procesar")
    parser.add_argument("--limit_acads", type=int, help="Límite de académicos por entidad (pruebas)")
    parser.add_argument("--name", type=str, help="Filtrar por un académico específico")
    parser.add_argument("--force", action="store_true", help="Re-ingestar académicos existentes")
    parser.add_argument("--local", action="store_true", help="Usar SDK nativa de lmstudio para embeddings")
    parser.add_argument("--ch", action="store_true", help="Sincronizar con ClickHouse (Dual Write)")
    parser.add_argument("--source", type=str, help="Forzar origen de indización (wos, scopus, pubmed, doaj)")
    parser.add_argument("--hierarchy", type=str, help="Jerarquía completa: Institución || Dependencia || Subdependencia")
    
    args = parser.parse_args()

    # Validación: Si se pide un nombre específico, DEBE haber jerarquía
    if args.name and not args.hierarchy:
        parser.error("La opción --name requiere --hierarchy para asignar la afiliación correcta.")
    
    # Directorio base por defecto
    unam_data_dir = os.path.join("data", "UNAM")
    
    input_paths = []
    
    if args.input:
        if os.path.isfile(args.input):
            input_paths = [args.input]
        elif os.path.isdir(args.input):
            # Escanear directorio proporcionado
            input_paths = [os.path.join(args.input, f) for f in os.listdir(args.input) if f.startswith("profesores_SNII_") and f.endswith(".json")]
    else:
        # Escaneo automático del directorio estándar
        if os.path.exists(unam_data_dir):
            input_paths = [os.path.join(unam_data_dir, f) for f in os.listdir(unam_data_dir) if f.startswith("profesores_SNII_") and f.endswith(".json")]
    if not input_paths:
        print("❌ No se encontraron archivos para procesar. Verifica el directorio 'data/UNAM/'.")
        sys.exit(1)
        
    print(f"🚀 Iniciando procesamiento de {len(input_paths)} archivos de entidad...")
    
    try:
        # Parsear jerarquía si se proporciona
        h_inst, h_dep, h_sub = "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)", None, None
        if args.hierarchy:
            h_parts = [p.strip() for p in args.hierarchy.split("||")]
            h_inst = h_parts[0] if len(h_parts) > 0 else h_inst
            h_dep = h_parts[1] if len(h_parts) > 1 else None
            h_sub = h_parts[2] if len(h_parts) > 2 else h_sub

        for json_file in input_paths:
            print(f"\n📂 ************************************************************")
            print(f"📂 PROCESANDO ENTIDAD: {os.path.basename(json_file)}")
            print(f"📂 ************************************************************")
            
            # Detectar si es SNII por el nombre del archivo
            is_snii_file = "SNII" in os.path.basename(json_file)
            
            # Reutilizamos la lógica existente pero con el límite si existe
            process_and_ingest_academics(
                json_file, 
                force=args.force, 
                force_local=args.local, 
                target_name=args.name,
                is_snii=is_snii_file,
                limit_acads=args.limit_acads,
                override_entity=h_sub,
                institution_name=h_inst,
                dependency_name=h_dep,
                subdependency_name=h_sub,
                save_to_ch=args.ch,
                source_override=args.source
            )
            
    except KeyboardInterrupt:
        print("\n🛑 Proceso interrumpido por el usuario.")
    finally:
        print("\n🎉 Proceso global de ingesta de APIs completado.")
        graph_store.close()
