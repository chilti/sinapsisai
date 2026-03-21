"""
patch_all_openalex_fields.py (Optimized for Large Scale)
──────────────────────────────────────────────────────
Rellena campos de OpenAlex en Neo4j usando paginación para evitar agotar RAM.
Optimizado para entidades grandes (ej. "México") con cientos de miles de papers.
"""

import sys
import os
import json
import time
import argparse
import ast
import urllib3
import httpx
import ssl

# Desactivar advertencias y SSL para entornos con proxies restrictivos
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore
import pyalex
from dotenv import load_dotenv

# Configuración PyAlex
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)
pyalex.config.email = os.getenv("EMAIL_ADDRESS", "sin_correo@ciencias.unam.mx")
if os.getenv("OPENALEX_API_KEY"):
    pyalex.config.api_key = os.getenv("OPENALEX_API_KEY")

LOCAL_API_URL  = "http://127.0.0.1:5009/works"
OFFICIAL_API_URL = "https://api.openalex.org/works"

# Retraso entre requests (s). Sube a 1.0 si siguen bloqueando.
REQUEST_DELAY = 0.15  # 150ms → ~6 req/s, por debajo del límite sin API key de OpenAlex (10/s)

def _fetch_dois_batch(client: httpx.Client, dois: list[str], use_local: bool = True) -> dict:
    """Obtiene los metadatos de hasta 50 DOIs en un solo request.
    Intenta la API local primero y cae a la oficial si falla.
    Devuelve un dict doi_clean -> work.
    """
    if not dois:
        return {}
    filter_str = "|".join(dois)
    params = {"filter": f"doi:{filter_str}", "per-page": len(dois), "mailto": pyalex.config.email}
    
    def _try(url, retries=3, backoff=1.0):
        for attempt in range(retries):
            try:
                resp = client.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    return resp.json().get('results', [])
                if resp.status_code in (429, 403):
                    wait = backoff * (2 ** attempt)
                    print(f"\n      [!] Rate limit ({resp.status_code}) en {url}. Esperando {wait}s...")
                    time.sleep(wait)
                else:
                    return []
            except Exception as e:
                print(f"      [!] Error HTTP: {e}")
                time.sleep(backoff)
        return []
    
    results = _try(LOCAL_API_URL) if use_local else []
    if not results:
        results = _try(OFFICIAL_API_URL)
    
    out = {}
    for w in results:
        doi_val = (w.get('doi') or "").replace("https://doi.org/", "").strip().lower()
        if doi_val:
            out[doi_val] = w
    return out

def extract_new_fields(work: dict) -> dict:
    """Devuelve un dict con campos de OpenAlex procesados."""
    oa     = work.get('open_access') or {}
    _auths = work.get('authorships', [])
    _loc   = work.get('primary_location') or {}
    _src   = _loc.get('source') or {}
    pt     = work.get('primary_topic') or {}
    cyp    = work.get('cited_by_percentile_year') or {}

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
        except: pass

    coauthor_institutions = [
        {
            'author':   (a.get('author') or {}).get('display_name'),
            'orcid':    (a.get('author') or {}).get('orcid'),
            'countries': a.get('countries', []),
            'institutions': [{'name': i.get('display_name')} for i in a.get('institutions', [])]
        }
        for a in _auths
    ]

    return {
        'openalex_url':                 work.get('id'),
        'fwci':                         work.get('fwci'),
        'cited_by_count':               work.get('cited_by_count', 0),
        'open_access':                  oa,
        'citation_normalized_percentile': (work.get('citation_normalized_percentile') or {}).get('value'),
        'is_in_top_1_percent':          (work.get('citation_normalized_percentile') or {}).get('is_in_top_1_percent', False),
        'is_in_top_10_percent':         (work.get('citation_normalized_percentile') or {}).get('is_in_top_10_percent', False),
        'counts_by_year':         work.get('counts_by_year', []),
        'referenced_works_count': work.get('referenced_works_count', 0),
        'apc_paid_usd': (work.get('apc_paid') or {}).get('value_usd', 0) or 0,
        'author_count':               len(_auths),
        'countries_distinct_count':   work.get('countries_distinct_count', 0),
        'institutions_distinct_count': work.get('institutions_distinct_count', 0),
        'countries':                  work.get('countries', []),
        'coauthor_institutions':      coauthor_institutions,
        'journal_is_core':    _src.get('is_core', False),
        'primary_topic_name': pt.get('display_name'),
        'OpenAlex_Topics':    topics,
        'keywords':           [k.get('display_name') for k in work.get('keywords', [])[:10]],
        'grants':             work.get('grants', []),
    }

def _parse_raw_meta(raw_meta_json):
    if isinstance(raw_meta_json, dict): return raw_meta_json
    if not raw_meta_json: return {}
    try:
        return json.loads(raw_meta_json)
    except:
        try: return ast.literal_eval(raw_meta_json)
        except: return {}

def patch_all_fields(entity_filter=None, academic_filter=None, dry_run=False, skip_existing=False, limit=None, chunk_size=5000, batch_size=20):
    graph_store = Neo4jGraphStore()
    
    # 1. Contar total de trabajos a procesar
    with graph_store.driver.session() as session:
        if entity_filter:
            count_query = """
            MATCH (e:Entity {name: $entity})
            OPTIONAL MATCH (e)-[:HAS_PAPER]->(p1:Paper)
            OPTIONAL MATCH (e)<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p2:Paper)
            WITH collect(p1) + collect(p2) AS all_p
            UNWIND all_p AS p
            RETURN count(DISTINCT p) AS total
            """
            total_papers = session.run(count_query, entity=entity_filter).single()['total']
        elif academic_filter:
            count_query = """
            MATCH (a:Academic {name: $academic})-[:AUTHORED]->(p:Paper)
            RETURN count(DISTINCT p) AS total
            """
            total_papers = session.run(count_query, academic=academic_filter).single()['total']
        else:
            total_papers = session.run("MATCH (p:Paper) RETURN count(p) AS total").single()['total']

    if limit: total_papers = min(total_papers, limit)
    print(f"🚀 Iniciando parche para {total_papers} papers...")

    processed = 0
    updated = 0
    skipped = 0
    errors = 0

    # 2. Iterar por CHUNKS para no saturar memoria
    for skip in range(0, total_papers, chunk_size):
        remaining_in_chunk = min(chunk_size, total_papers - skip)
        print(f"\n📦 Procesando chunk {skip} a {skip + remaining_in_chunk}...")
        
        chunk_papers = []
        with graph_store.driver.session() as session:
            if entity_filter:
                query = """
                MATCH (e:Entity {name: $entity})
                OPTIONAL MATCH (e)-[:HAS_PAPER]->(p1:Paper)
                OPTIONAL MATCH (e)<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p2:Paper)
                WITH collect(p1) + collect(p2) AS all_p
                UNWIND all_p AS p
                WITH DISTINCT p
                RETURN p.id AS id, p.doi AS doi, p.title AS title, p.raw_metadata AS meta
                SKIP $skip LIMIT $limit
                """
                result = session.run(query, entity=entity_filter, skip=skip, limit=remaining_in_chunk)
            elif academic_filter:
                query = """
                MATCH (a:Academic {name: $academic})-[:AUTHORED]->(p:Paper)
                RETURN DISTINCT p.id AS id, p.doi AS doi, p.title AS title, p.raw_metadata AS meta
                SKIP $skip LIMIT $limit
                """
                result = session.run(query, academic=academic_filter, skip=skip, limit=remaining_in_chunk)
            else:
                query = """
                MATCH (p:Paper)
                RETURN p.id AS id, p.doi AS doi, p.title AS title, p.raw_metadata AS meta
                SKIP $skip LIMIT $limit
                """
                result = session.run(query, skip=skip, limit=remaining_in_chunk)
            
            for row in result:
                chunk_papers.append(row)

        # 3. Procesar el chunk en BATCHES de API (20 en 20)
        for i in range(0, len(chunk_papers), batch_size):
            batch = chunk_papers[i:i+batch_size]
            
            # Filtrar por skip_existing si es necesario
            to_patch = []
            for p in batch:
                if skip_existing:
                    meta = _parse_raw_meta(p['meta'])
                    if 'author_count' in meta and 'counts_by_year' in meta:
                        skipped += 1
                        continue
                
                # Permitir papers con DOI real O con IDs temporales de ORCID si tienen título largo
                has_real_doi = p['doi'] and str(p['doi']).startswith("10.")
                has_title = p['title'] and len(str(p['title'])) > 20
                
                if has_real_doi or has_title:
                    to_patch.append(p)
                else:
                    skipped += 1

            if not to_patch: continue
            if dry_run:
                updated += len(to_patch)
                print(f"  [DRY] Parchearía batch de {len(to_patch)}", end="\r")
                continue

            # API FETCH
            oa_data = {}
            with httpx.Client(verify=False, timeout=60.0) as client:
                # Separa los que tienen DOI real
                doi_papers    = []
                for p_rec in to_patch:
                    raw_doi   = str(p_rec['doi'] or "")
                    clean_doi = raw_doi.replace("https://doi.org/", "").strip().lower()
                    if clean_doi.startswith("10."):
                        doi_papers.append((raw_doi, clean_doi))

                # BATCH FETCH DE DOIs en bloques de 50
                DOI_CHUNK = 50
                for k in range(0, len(doi_papers), DOI_CHUNK):
                    chunk       = doi_papers[k:k + DOI_CHUNK]
                    clean_dois  = [cd for _, cd in chunk]
                    batch_result = _fetch_dois_batch(client, clean_dois)
                    for orig_raw, orig_clean in chunk:
                        if orig_clean in batch_result:
                            oa_data[orig_raw] = batch_result[orig_clean]
                    time.sleep(REQUEST_DELAY)

            # DB UPDATE
            with graph_store.driver.session() as session:
                for p_rec in to_patch:
                    doi_key = str(p_rec['doi'] or "")
                    if doi_key not in oa_data:
                        errors += 1
                        continue
                    
                    try:
                        meta = _parse_raw_meta(p_rec['meta'])
                        oa_work = oa_data[doi_key]
                        new_data = extract_new_fields(oa_work)
                        meta.update(new_data)
                        
                        # Si recuperamos un DOI de OpenAlex que no teníamos, lo actualizamos en el nodo
                        found_doi = oa_work.get('doi')
                        if found_doi: 
                            found_doi = found_doi.replace("https://doi.org/", "").lower()
                        
                        # Extraer citas directamente para guardarlo ademas en Propiedades del Nodo
                        citations_val = int(oa_work.get('cited_by_count', 0) or 0)
                        
                        if found_doi and not doi_key.startswith("10."):
                            # Caso orcid-work -> DOI real descubierto
                            session.run("""
                                MATCH (p:Paper {id: $id}) 
                                SET p.raw_metadata = $json, p.doi = $new_doi, p.citations = $citations
                            """, id=p_rec['id'], json=json.dumps(meta, ensure_ascii=False), new_doi=found_doi, citations=citations_val)
                        else:
                            # Actualización normal
                            session.run("MATCH (p:Paper {id: $id}) SET p.raw_metadata = $json, p.citations = $citations", 
                                        id=p_rec['id'], json=json.dumps(meta, ensure_ascii=False), citations=citations_val)
                        updated += 1
                    except:
                        errors += 1

            processed += len(batch)
            print(f"  📊 {skip+i+len(batch)}/{total_papers} | OK: {updated} | Skip: {skipped} | Err: {errors}", end="\r")

    print(f"\n\n✨ Finalizado. {updated} actualizados, {skipped} omitidos, {errors} errores.")
    graph_store.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity", type=str, default=None)
    parser.add_argument("--academic", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch", type=int, default=20)
    parser.add_argument("--chunk", type=int, default=5000)
    args = parser.parse_args()

    patch_all_fields(entity_filter=args.entity, academic_filter=args.academic,
                     dry_run=args.dry_run, 
                     skip_existing=args.skip_existing, limit=args.limit, 
                     batch_size=args.batch, chunk_size=args.chunk)
