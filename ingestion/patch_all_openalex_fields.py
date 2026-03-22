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
from dotenv import load_dotenv

# Desactivar advertencias y SSL para entornos con proxies restrictivos
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

# Configuración
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'SNII')))
from database.knowledge_graph import Neo4jGraphStore
try:
    from match_snii_orcid import get_client as get_ch_client
except ImportError:
    get_ch_client = None
import pyalex

# Configuración PyAlex
pyalex.config.email = os.getenv("EMAIL_ADDRESS", "sin_correo@ciencias.unam.mx")
if os.getenv("OPENALEX_API_KEY"):
    pyalex.config.api_key = os.getenv("OPENALEX_API_KEY")

LOCAL_API_URL    = "http://127.0.0.1:5009/works"
OFFICIAL_API_URL = "https://api.openalex.org/works"

# Retraso entre requests oficiales (s). 0.2s = 5 req/s.
REQUEST_DELAY = 0.2

LOCAL_API_AVAILABLE = False
OFFICIAL_API_BLOCKED = False
CH_API_BLOCKED = False

def check_local_api() -> bool:
    """Comprueba si la API local de OpenAlex (port 5009) está levantada."""
    try:
        resp = httpx.get(LOCAL_API_URL, params={"filter": "doi:10.0000/test", "per_page": 1}, timeout=5)
        return resp.status_code in (200, 404)
    except Exception:
        return False

def _fetch_from_official_lookup(client: httpx.Client, doi: str) -> dict | None:
    """Step 1: Consulta oficial 1-a-1 por path de DOI (Lookup)."""
    global OFFICIAL_API_BLOCKED
    if OFFICIAL_API_BLOCKED:
        return None
    
    clean_doi = doi.replace("https://doi.org/", "").strip()
    url = f"https://api.openalex.org/works/doi:{clean_doi}"
    params = {"mailto": pyalex.config.email}
    if os.getenv("OPENALEX_API_KEY"):
        params["api_key"] = os.getenv("OPENALEX_API_KEY")
    
    try:
        resp = client.get(url, params=params, timeout=20, follow_redirects=True)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 403):
            print(f"\n      [!] API OFICIAL BLOQUEADA ({resp.status_code}). Pasando a Local para el resto de la corrida.")
            OFFICIAL_API_BLOCKED = True
        return None
    except Exception as e:
        print(f"      [!] Error en lookup oficial para {doi}: {e}")
        return None

def _fetch_from_clickhouse_bulk(dois: list[str]) -> dict:
    """Step 2: Consulta masiva a ClickHouse local."""
    global CH_API_BLOCKED
    if CH_API_BLOCKED or not get_ch_client or not dois:
        return {}
    try:
        from SNII.match_snii_orcid import CH_DB
        ch_table = os.getenv("CH_TABLE", "works")
        ch = get_ch_client()
        doi_list = [f"https://doi.org/{d.lower()}" for d in dois]
        placeholders = ", ".join([f"'{d}'" for d in doi_list])
        
        query = f"SELECT raw_data FROM {CH_DB}.{ch_table} WHERE doi IN ({placeholders}) LIMIT {len(dois)}"
        res = ch.query(query).result_rows
        
        found = {}
        for r in res:
            try:
                data = json.loads(r[0]) if isinstance(r[0], str) else r[0]
                d_val = (data.get('doi') or "").replace("https://doi.org/", "").strip().lower()
                if d_val:
                    found[d_val] = data
            except: continue
        return found
    except Exception as e:
        print(f"      [!] Step 2 (ClickHouse) no disponible: {e}. Desactivando CH para esta corrida.")
        CH_API_BLOCKED = True
        return {}

def _fetch_from_local_api_bulk(client: httpx.Client, dois: list[str]) -> dict:
    """Step 3: Consulta masiva a API Local port 5009."""
    if not LOCAL_API_AVAILABLE or not dois:
        return {}
    
    doi_filter = "|".join([f"https://doi.org/{d}" for d in dois])
    params = {"filter": f"doi:{doi_filter}", "per_page": len(dois)}
    try:
        resp = client.get(LOCAL_API_URL, params=params, timeout=30)
        if resp.status_code == 200:
            results = resp.json().get('results', [])
            out = {}
            for w in results:
                d_val = (w.get('doi') or "").replace("https://doi.org/", "").strip().lower()
                if d_val: out[d_val] = w
            return out
    except Exception as e:
        print(f"      [!] Error en Step 3 (API Local): {e}")
    return {}

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

def patch_all_fields(entity_filter=None, academic_filter=None, dry_run=False, skip_existing=False, limit=None, chunk_size=5000, batch_size=20, local_only=False):
    global LOCAL_API_AVAILABLE, OFFICIAL_API_BLOCKED
    LOCAL_API_AVAILABLE = check_local_api()
    if local_only:
        OFFICIAL_API_BLOCKED = True
        print("🔒 Modo --local-only activado. Se bloqueará la API oficial de OpenAlex.")
    if LOCAL_API_AVAILABLE:
        print(f"✅ API local de OpenAlex detectada en {LOCAL_API_URL} — se usará como fuente principal.")
    else:
        print(f"⚠️  API local de OpenAlex NO disponible en {LOCAL_API_URL}.")
        if local_only:
            print("❌ Se requiere --local-only pero la API local no está levantada. Abortando.")
            return
        print("   Usando API oficial (puede alcanzar rate limit). Considera levantar el servidor local.")


    from SNII.match_snii_orcid import NEO4J_URI, NEO4J_USER, NEO4J_PASS
    graph_store = Neo4jGraphStore(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASS)
    
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

            # API FETCH (Hierarchy: Official Lookup -> ClickHouse -> Local API)
            oa_data = {}
            with httpx.Client(verify=False, timeout=60.0) as client:
                doi_papers = []
                for p_rec in to_patch:
                    raw_doi = str(p_rec['doi'] or "")
                    clean_doi = raw_doi.replace("https://doi.org/", "").strip().lower()
                    if clean_doi.startswith("10."):
                        doi_papers.append((raw_doi, clean_doi))

                # --- STEP 1: Official API (1-by-1 Lookup) ---
                if not OFFICIAL_API_BLOCKED:
                    for raw, clean in doi_papers:
                        work = _fetch_from_official_lookup(client, clean)
                        if work:
                            oa_data[raw] = work
                            print(f"  🌐 [Oficial] Encontrado: {clean}", end="\r")
                            time.sleep(REQUEST_DELAY) # Rate limiting
                        if OFFICIAL_API_BLOCKED:
                            break

                # --- STEP 2: ClickHouse (Bulk Fallback) ---
                remaining = [p for p in doi_papers if p[0] not in oa_data]
                if remaining:
                    ch_results = _fetch_from_clickhouse_bulk([r[1] for r in remaining])
                    for raw, clean in remaining:
                        if clean in ch_results:
                            oa_data[raw] = ch_results[clean]
                            print(f"  🏠 [CH] Encontrado: {clean}", end="\r")

                # --- STEP 3: Local API 5009 (Final Fallback) ---
                missing = [p for p in doi_papers if p[0] not in oa_data]
                if missing and LOCAL_API_AVAILABLE:
                    api_results = _fetch_from_local_api_bulk(client, [m[1] for m in missing])
                    for raw, clean in missing:
                        if clean in api_results:
                            oa_data[raw] = api_results[clean]
                            print(f"  🏠 [Local API] Encontrado: {clean}", end="\r")

            # DB UPDATE
            updates_normal = []
            updates_with_doi = []
            
            for p_rec in to_patch:
                doi_key = str(p_rec['doi'] or "")
                if doi_key not in oa_data:
                    fuente = LOCAL_API_URL if LOCAL_API_AVAILABLE else OFFICIAL_API_URL
                    # print(f"      ⚠️  No encontrado en OpenAlex [{fuente}]: https://doi.org/{doi_key}")
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
                    json_str = json.dumps(meta, ensure_ascii=False)
                    
                    if found_doi and not doi_key.startswith("10."):
                        # Caso orcid-work -> DOI real descubierto
                        updates_with_doi.append({"id": p_rec['id'], "new_doi": found_doi, "citations": citations_val, "json": json_str})
                    else:
                        # Actualización normal
                        updates_normal.append({"id": p_rec['id'], "citations": citations_val, "json": json_str})
                    
                    updated += 1
                except:
                    errors += 1

            if updates_normal or updates_with_doi:
                with graph_store.driver.session() as session:
                    if updates_normal:
                        session.run("""
                            UNWIND $batch AS b
                            MATCH (p:Paper {id: b.id})
                            SET p.raw_metadata = b.json, p.citations = b.citations
                        """, batch=updates_normal)
                    if updates_with_doi:
                        session.run("""
                            UNWIND $batch AS b
                            MATCH (p:Paper {id: b.id})
                            SET p.raw_metadata = b.json, p.doi = b.new_doi, p.citations = b.citations
                        """, batch=updates_with_doi)

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
    parser.add_argument("--local-only", action="store_true",
                        help="Aborta si la API local de OpenAlex (puerto 5009) no está disponible.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch", type=int, default=20)
    parser.add_argument("--chunk", type=int, default=5000)
    args = parser.parse_args()

    patch_all_fields(entity_filter=args.entity, academic_filter=args.academic,
                     dry_run=args.dry_run,
                     skip_existing=args.skip_existing, limit=args.limit,
                     batch_size=args.batch, chunk_size=args.chunk,
                     local_only=args.local_only)
