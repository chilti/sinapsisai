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
from database.clickhouse_db import ch_client
import pandas as pd
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
                # Usar DOI como llave principal, fallback al Scopus ID (eid)
                paper_key = pub.doi if pub.doi else pub.eid
                if paper_key and paper_key not in metadatos:
                    metadatos[paper_key] = {
                        'Title': pub.title,
                        'Year': pub.coverDate.split('-')[0] if pub.coverDate else 0,
                        'DOI': pub.doi,
                        'scopus_id': pub.eid,
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

                # 1. Intentar obtener DOI
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

                # 2. Extraer otros IDs de respaldo
                wos_id = next((eid.get('external-id-value') for eid in ext_ids_list
                                if isinstance(eid, dict) and eid.get('external-id-type') in ['wosid', 'eid']), None)
                sc_id = next((eid.get('external-id-value') for eid in ext_ids_list
                                if isinstance(eid, dict) and eid.get('external-id-type') == 'scopusid'), None)

                if doi and doi not in metadatos:
                    pub_date = summary.get('publication-date', {}) or {}
                    title_node = summary.get('title', {}) or {}
                    metadatos[doi] = {
                        'Title': title_node.get('title', {}).get('value') if title_node.get('title') else 'Sin Título',
                        'Year': pub_date.get('year', {}).get('value') if pub_date.get('year') else 0,
                        'DOI': doi,
                        'wos_id': wos_id,
                        'scopus_id': sc_id,
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
    # Intentar siempre local primero por eficiencia
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
                                'openalex_url': w.get('id'),
                                '_raw_oa': w
                            }
                if metadatos:
                    print(f"    [OpenAlex Local] Author {oa_id_clean}: {len(metadatos)} trabajos.")
                    return metadatos
    except Exception as e:
        print(f"    [WARN] Error API Local OpenAlex Author: {e}")
    
    # Si force_local es True y llegamos aquí, no intentamos la oficial
    if force_local:
        return {}
    
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
                            'Abstract': deconstruct_abstract(w.get('abstract_inverted_index')),
                            'openalex_url': w.get('id') # Persistir ID de OpenAlex
                        }
    except Exception as e:
        print(f"      ⚠ Error obteniendo trabajos de autor en API OpenAlex: {e}")
        
    return metadatos
def ingest_researcher_data(data, force=False, force_local=False, current_idx=None, total=None, save_to_ch=False):
    """Procesa e ingesta los datos de un único investigador."""
    academic_name = data.get('snii_author')
    if not academic_name: return
    
    # 1. Generar ID único consistente con knowledge_graph.py
    cvu = data.get('snii_cvu') or data.get('CVU') or data.get('CVU padrón corregido')
    if cvu and str(cvu).strip().isdigit():
        person_id = str(cvu).strip()
    else:
        person_id = "EXT_" + "".join(filter(str.isalnum, academic_name)).upper()

    # Preparar datos para ingesta taxonómica
    # Si el JSON viene de snii_llm_verified_matches, mapear nombres
    row_for_graph = {
        'NOMBRE DEL INVESTIGADOR': academic_name,
        'CVU': cvu,
        'NIVEL': data.get('snii_level') or data.get('nivel'),
        'ENTIDAD DE ACREDITACIÓN': data.get('snii_state') or data.get('entidad_federativa'),
        'INSTITUCION DE ACREDITACION': data.get('snii_institution'),
        'DEPENDENCIA DE ACREDITACIÓN': data.get('snii_dependency'),
        'SUBDEPENDENCIA DE ACREDITACIÓN': data.get('snii_subdependency'),
        'ÁREA DE CONOCIMIENTO': data.get('snii_area'),
        'DISCIPLINA': data.get('snii_discipline'),
        'SUBDISCIPLINA': data.get('snii_subdiscipline'),
        'ESPECIALIDAD': data.get('snii_specialty')
    }
    
    if current_idx and total:
        print(f"\n🏷️ [{current_idx}/{total}] [{academic_name}] ID: {person_id} - Ingestando esquema...")
    else:
        print(f"\n🏷️ [{academic_name}] ID: {person_id} - Ingestando esquema...")
    
    # 2. Ingestar Metadatos Taxonómicos e Institucionales (Nueva lógica atómica)
    graph_store.ingest_academic_row(row_for_graph)

    # 3. Enriquecer con identificadores externos y auditoría
    audit = data.get('audit', {})
    
    # Fallbacks si el JSON no tiene objeto 'audit' (formato heurístico)
    verdict = audit.get('verdict') or ('CONFIRMED' if data.get('match') is True and data.get('confidence') == 'AUTO_HIGH' else None)
    reason = audit.get('reason') or data.get('reason')
    confidence = audit.get('confidence') or data.get('confidence')
    
    orcid = data.get('matched_orcid') or data.get('orcid')
    
    graph_store.update_academic_metadata(
        academic_id=person_id,
        cvu=cvu,
        orcid=orcid if data.get('match') is True and verdict != 'FALSE_POSITIVE' else None,
        scopus_id=data.get('scopus_ids') or data.get('scopus_id'),
        audit_verdict=verdict,
        audit_reason=reason,
        audit_confidence=confidence,
        audit_timestamp=audit.get('timestamp'),
        is_snii=True
    )


    # --- Enriquecer con IDs desde Neo4j ---
    neo4j_ids = {"orcid": None, "openalex_id": None}
    if hasattr(graph_store, 'get_academic_ids'):
        neo4j_ids = graph_store.get_academic_ids(person_id)
    
    # Prioridad: data > Neo4j
    orcid = orcid or neo4j_ids.get('orcid')
    
    oa_ids = data.get('openalex_ids') or []
    if isinstance(oa_ids, str): oa_ids = [oa_ids]
    
    legacy_oa_id = data.get('matched_openalex_id') or data.get('openalex_id')
    if legacy_oa_id and legacy_oa_id not in oa_ids:
        oa_ids.append(legacy_oa_id)
    if not oa_ids and neo4j_ids.get('openalex_id'):
        oa_ids.append(neo4j_ids.get('openalex_id'))
    scopus_ids = data.get('scopus_ids')

    # 3. Determinar si es seguro recolectar publicaciones
    has_openalex_ids = len(oa_ids) > 0
    is_false_positive = verdict == 'FALSE_POSITIVE'
    is_valid_match = data.get('match') is True and not is_false_positive
    is_safe_match = is_valid_match and (orcid or has_openalex_ids)
    
    if not is_safe_match:
        print(f"  ℹ️ Saltando recolección de publicaciones (Match: {data.get('match')}, Veredicto: {audit.get('verdict')}, ORCID: {orcid}, OA_IDs: {oa_ids})")
        return

    # 4. Verificar existencia de publicaciones
    if hasattr(graph_store, 'check_academic_exists') and graph_store.check_academic_exists(person_id) and not force:
        print(f"  📍 Publicaciones ya existen en Neo4j. Saltando recolección API...")
        return

    # 5. Recolectar publicaciones
    meta_scopus = obtener_metadatos_de_scopus(scopus_ids) if scopus_ids else {}
    meta_orcid = obtener_metadatos_de_orcid(orcid) if orcid else {}
    
    meta_oa_author = {}
    for oa_id in oa_ids:
        if oa_id and oa_id is not False:
            oa_works = obtener_metadatos_de_openalex_autor(oa_id, force_local=force_local)
            if oa_works:
                meta_oa_author.update(oa_works)

    # Fusionar con deduplicación por título
    scopus_titles = {_clean_t(d.get('Title', '')) for d in meta_scopus.values() if d.get('Title')}
    orcid_titles  = {_clean_t(d.get('Title', '')) for d in meta_orcid.values() if d.get('Title')}
    
    meta_unificada = meta_scopus.copy()
    for d, m_data in meta_orcid.items():
        if d in meta_unificada: continue
        c_title = _clean_t(m_data.get('Title', ''))
        if c_title in scopus_titles and c_title != "": continue
        meta_unificada[d] = m_data
        
    all_titles_so_far = scopus_titles | orcid_titles
    for d, m_data in meta_oa_author.items():
        if d in meta_unificada: continue
        c_title = _clean_t(m_data.get('Title', ''))
        if c_title in all_titles_so_far and c_title != "": continue
        meta_unificada[d] = m_data

    if not meta_unificada:
        print("  -> Sin publicaciones rastreables por ninguna fuente.")
        return
        
    print(f"  -> {len(meta_unificada)} artículos únicos encontrados. Enriqueciendo...")

    # Batch processing DOIs
    dois_to_fetch = [doi for doi in meta_unificada.keys() if not doi.startswith('orcid-work:')]
    
    openalex_blocked = force_local or getattr(openalex_utils, 'OFFICIAL_API_BLOCKED', False)
    batch_results = {}
    if dois_to_fetch:
        print(f"      📡 Consultando lote de {len(dois_to_fetch)} DOIs...")
        batch_results = openalex_utils.get_works_batch(dois_to_fetch, local_only=openalex_blocked)
    
    neo4j_batch = []
    batch_payloads = []
    batch_texts = []

    # Optimización: Filtrar documentos que ya existen en Qdrant por lote
    ids_to_check = [{"doi": d, "title": r.get("Title")} for d, r in meta_unificada.items()]
    missing_dois_in_qdrant = set()
    if hasattr(vector_store, 'filter_existing_ids'):
        missing_dois_in_qdrant = set(vector_store.filter_existing_ids(ids_to_check))
    else:
        # Fallback si el método no existe aún en el objeto instanciado
        missing_dois_in_qdrant = {d for d in meta_unificada.keys()}

    print(f"      🔍 Qdrant Check: {len(meta_unificada)} trabajos totales. {len(meta_unificada) - len(missing_dois_in_qdrant)} ya existen, {len(missing_dois_in_qdrant)} nuevos para vectorizar.")

    for doi, record in meta_unificada.items():
        text_for_embedding = f"Title: {record.get('Title')}\n"
        work = None
        
        # (Lógica de OpenAlex ya procesada en batch_results)
        _doi_clean = doi if not doi.startswith('orcid-work:') else None
        _doi_key = _doi_clean.lower() if _doi_clean else None
        
        if _doi_key and _doi_key in batch_results:
            work = batch_results[_doi_key]
        elif not _doi_clean or _doi_key not in batch_results:
            try:
                work = openalex_utils.get_work(doi=_doi_clean, title=record.get('Title'), local_only=openalex_blocked, quiet=True)
            except:
                work = None

        if work:
            authorships = work.get('authorships', [])
            record['Authors'] = "; ".join([au['author']['display_name'] for au in authorships])
            record['Keywords_oa'] = "; ".join([kw['display_name'] for kw in work.get('keywords', [])])
            record['Abstract_oa'] = deconstruct_abstract(work.get('abstract_inverted_index'))
            record['openalex_url'] = work.get('id')
            if record['Abstract_oa']: record['Abstract'] = record['Abstract_oa']
            record['Cited_by'] = work.get('cited_by_count', record.get('Cited_by', 0))
            record['fwci'] = work.get('fwci')
            record['Source'] += ' + OpenAlex'
            
            # Extraer Topic Principal (primer tópico de la lista)
            topics = work.get('topics', [])
            if topics:
                main_t = topics[0]
                record['topic_domain'] = main_t.get('domain', {}).get('display_name')
                record['topic_field'] = main_t.get('field', {}).get('display_name')
                record['topic_subfield'] = main_t.get('subfield', {}).get('display_name')
                record['topic_name'] = main_t.get('display_name')
            
            # Extraer SDGs
            sdgs_list = [s.get('display_name') for s in work.get('sustainable_development_goals', []) if s.get('display_name')]
            record['sdgs'] = sdgs_list

        # Verificar existencia en Qdrant usando el set pre-calculado
        u_str = doi if doi and str(doi).strip().lower() != "none" else record.get("Title")
        qdrant_exists = u_str not in missing_dois_in_qdrant
            
        if not qdrant_exists:
            if record.get('Abstract'):
                text_for_embedding += f"Abstract: {record['Abstract']}"
            
            payload_qdrant = {
                "academic_name": academic_name,
                "person_id":     person_id,
                "doi":           doi,
                "title":         record.get("Title"),
                "year":          record.get("Year"),
                "source":        record.get("Source"),
                "institution":   data.get('snii_institution'),
                "dependency":    data.get('snii_dependency'),
                "subdependency": data.get('snii_subdependency'),
                "text":          text_for_embedding
            }
            batch_texts.append(text_for_embedding)
            batch_payloads.append(payload_qdrant)

        system_id = orcid if orcid else academic_name
        funders_list = []
        awards_list = []
        grants = work.get("grants", []) if work else []
        for g in grants:
            if g.get("funder_display_name"):
                funders_list.append({"name": g.get("funder_display_name"), "openalex_id": g.get("funder") or ""})
            if g.get("award_id"):
                awards_list.append(g.get("award_id"))

        # Mapear para ingest_paper_row
        neo4j_batch.append({
            "system_id": person_id,
            "academic_name": academic_name,
            "doi": doi,
            "title": record.get("Title"),
            "year": int(record.get("Year", 0)) if record.get("Year") else 0,
            "citations": int(record.get("Cited_by", 0)) if record.get("Cited_by") else 0,
            "orcid": orcid,
            "openalex_id": record.get("openalex_url"),
            "author_openalex_id": ",".join(oa_ids) if oa_ids else None,
            "wos_id": record.get("wos_id"),
            "scopus_id": record.get("scopus_id"),
            "semantic_id": record.get("semantic_scholar_id"),
            "fwci": record.get("fwci"),
            "topic_domain": record.get("topic_domain"),
            "topic_field": record.get("topic_field"),
            "topic_subfield": record.get("topic_subfield"),
            "topic_name": record.get("topic_name"),
            "sdgs": record.get("sdgs", []),
            "author_position": record.get("author_position"),
            "is_corresponding": record.get("is_corresponding", False),
            "institucion": None, # Deshabilitado para SNII. Solo crear Capacidad Instalada (AUTHOR_OF).
            "dependencia": None,
            "subdependencia": None,
            "funders": funders_list,
            "awards": list(set(awards_list)),
            "raw_metadata": json.dumps(record, ensure_ascii=False),
            "audit_verdict": audit.get('verdict') if audit else None
        })

    if neo4j_batch:
        print(f"      🗄️ Insertando lote de {len(neo4j_batch)} artículos en Neo4j...")
        graph_store.add_api_papers_batch(neo4j_batch)
        
    # --- DUAL WRITE TO CLICKHOUSE ---
    if save_to_ch and neo4j_batch:
        try:
            ch = ch_client.get_client()
            rows_ch = []
            for item in neo4j_batch:
                # Recuperar metadatos crudos para detectar bases
                raw_data = json.loads(item['raw_metadata'])
                oa_data = raw_data.get('_raw_oa', {})
                oa_ids_dict = oa_data.get('ids', {})
                
                rows_ch.append({
                    'paper_id': item.get('openalex_id') or item.get('doi'),
                    'academic_name': item['academic_name'],
                    'cvu': str(person_id),
                    'orcid': item.get('orcid') or '',
                    'openalex_id': item.get('author_openalex_id') or '',
                    'institution': data.get('snii_institution'),
                    'institution_ror': '',
                    'dependency': data.get('snii_dependency'),
                    'subdependency': data.get('snii_subdependency'),
                    'paper_title': item['title'],
                    'paper_year': int(item['year']),
                    'citations': int(item['citations']),
                    'is_wos': 1 if 'wos' in oa_ids_dict else 0,
                    'is_scopus': 1 if 'scopus' in oa_ids_dict else 0,
                    'is_pubmed': 1 if 'pmid' in oa_ids_dict else 0,
                    'is_openalex': 1,
                    'is_doaj': 1 if oa_data.get('is_oa') and 'doaj' in str(oa_data.get('locations', [])).lower() else 0,
                    'is_semantic_scholar': 1 if 'mag' in oa_ids_dict else 0,
                    'is_dimensions': 1 if 'mag' in oa_ids_dict else 0,
                    'is_lens': 1 if 'mag' in oa_ids_dict or 'pmid' in oa_ids_dict else 0,
                    'is_snii': 1,
                    'source': 'SNII_Dual_Ingest',
                    'audit_verdict': item.get('audit_verdict') or 'UNVERIFIED'
                })
            if rows_ch:
                ch.insert_df('paper_author_map', pd.DataFrame(rows_ch))
                print(f"      📊 [ClickHouse] {len(rows_ch)} registros sincronizados con índices (WoS/Scopus/etc).")
        except Exception as e:
            print(f"      [WARN] Error al sincronizar con ClickHouse: {e}")

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


def process_and_ingest_snii(json_path, force=False, force_local=False, target_name=None, target_orcid=None, limit_acads=None, confirmed_only=False, offset=0, save_to_ch=False):
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
        # Inyectar ORCID si se proporciona por parámetro (prioridad sobre el JSON)
        if target_name and target_orcid and academic_name.lower() == target_name.lower():
             data['matched_orcid'] = target_orcid
             print(f"      🎯 [Override] Usando ORCID proporcionado: {target_orcid}")
             
        try:
            ingest_researcher_data(data, force=force, force_local=force_local, current_idx=count, total=len(registros_to_process), save_to_ch=save_to_ch)
        except KeyboardInterrupt:
            print("\n\n🛑 [Ctrl+C detectado] Abortando procesamiento de forma segura...")
            break

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingesta API para padrón SNII consolidado")
    parser.add_argument("--input", default=os.path.join("data", "snii_llm_verified_matches.json"), help="JSON SNII")
    parser.add_argument("--limit", type=int, help="Límite")
    parser.add_argument("--name", type=str, help="Nombre")
    parser.add_argument("--orcid", type=str, help="ORCID explícito para el académico")
    parser.add_argument("--force", action="store_true", help="Forzar")
    parser.add_argument("--local", action="store_true", help="Usar recursos locales (OpenAlex y Embeddings) para evitar límites de API")
    parser.add_argument("--confirmed-only", action="store_true", help="Procesar solo los auditados como CONFIRMED")
    parser.add_argument("--offset", type=int, default=0, help="Empezar desde el registro N")
    parser.add_argument("--ch", action="store_true", help="Sincronizar simultáneamente con ClickHouse (paper_author_map)")
    args = parser.parse_args()
    
    try:
        process_and_ingest_snii(
            args.input, 
            force=args.force, 
            force_local=args.local, 
            target_name=args.name, 
            target_orcid=args.orcid,
            limit_acads=args.limit,
            confirmed_only=args.confirmed_only,
            offset=args.offset,
            save_to_ch=args.ch
        )
    except KeyboardInterrupt:
        print("\n\n🛑 Proceso interrumpido por el usuario. Cerrando conexiones...")
    finally:
        graph_store.close()
        print("\n🎉 Proceso completado.")
