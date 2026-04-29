"""
snii_llm_identity_resolver.py

Resuelve la identidad de los investigadores del SNII 2025 contra mltiples
fuentes de datos externas (OpenAlex, ORCID dump, Neo4j local) mediante un
pipeline de bsqueda semntica + reranking con LLM.

Flujo principal:
  1. Por cada investigador en el Excel del SNII, genera un embedding semntico.
  2. Busca candidatos en:
       - OpenAlex Authors (ClickHouse local, bsqueda lexicogrfica + Jaro-Winkler)
       - ORCID Dump via Qdrant ('orcid_authors_vec')
       - Neo4j / SIIA local via Qdrant ('local_authors')  [prioridad UNAM]
       - ClickHouse text-search fuzzy (fallback)
  3. Presenta los candidatos a un LLM para verificacin y decisin final.
  4. Guarda resultados incrementales en data/snii_llm_verified_matches.json.
"""

import os
import sys
import json
import time
import pandas as pd
import httpx
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.messages import HumanMessage
from ingest_snii_apis import ingest_researcher_data

# Aadir path raz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.vector_store import QdrantStore
from match_snii_orcid import normalize_text, get_client as get_ch_client, get_orcid_client, SNII_PATH, CH_DB, CH_DB_ORCID

# Cargar .env
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

# --- Config MEX_KEYWORDS (para fallbacks Qdrant) ---
MEX_KEYWORDS = [
    "mexico", "mexic", "unam", "ipn", "cinvestav", "tecnologico", "autonoma", "itamb", "colmex",
    "buap", "uaslp", "udem", "itesm", "uam", "politecnico"
]

if os.path.exists(SNII_PATH):
    try:
        print("📡 Cargando instituciones desde SNII para expandir red de seguridad...")
        df_snii = pd.read_excel(SNII_PATH)
        # Normalizar nombres de columnas para evitar KeyErrors por acentos/encoding
        df_snii.columns = [normalize_text(c).upper() for c in df_snii.columns]
        
        name_col = 'NOMBRE DEL INVESTIGADOR'
        inst_col = 'INSTITUCION DE ACREDITACION'
        sub_col = 'SUBDEPENDENCIA DE ACREDITACION'

        instituciones = df_snii[inst_col].dropna().unique().tolist()
        subdependencias = df_snii[sub_col].dropna().unique().tolist()

        for ext_name in instituciones + subdependencias:
            clean_name = str(ext_name).lower().replace("'", "").strip()
            if len(clean_name) > 4:
                MEX_KEYWORDS.append(clean_name)

        MEX_KEYWORDS = list(set(MEX_KEYWORDS))
        print(f" Red de seguridad expandida a {len(MEX_KEYWORDS)} trminos clave.")
    except Exception as e:
        print(f" No se pudo expandir MEX_KEYWORDS desde Excel: {e}")

# --- Config Embeddings ---
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
if not base_url.endswith("/"):
    base_url += "/"
model_name = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
auth_url = base_url
if user and password:
    if "://" in base_url:
        proto, rest = base_url.split("://", 1)
        auth_url = f"{proto}://{user}:{password}@{rest}"
    else:
        auth_url = f"http://{user}:{password}@{base_url}"

# Cliente global para reutilizar conexiones (Pooling)
http_client = httpx.Client(verify=False, timeout=120)

# Cache para estado de API Local
LOCAL_API_DISABLED = False
LOCAL_API_FAILURES = 0

embeddings_model = OpenAIEmbeddings(
    model=model_name,
    base_url=auth_url,
    api_key="lm-studio",
    http_client=http_client,
    check_embedding_ctx_length=False
)

# --- Config LLM ---
llm_model_name = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
llm = ChatOpenAI(
    model=llm_model_name,
    base_url=auth_url,
    api_key="lm-studio",
    http_client=http_client,
    temperature=0
)


def get_embeddings(texts: list, batch_size: int = 10) -> list:
    """Genera embeddings en batches con reintentos automticos."""
    if not texts:
        return []
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = [str(t) if t else " " for t in texts[i:i + batch_size]]
        for attempt in range(5):
            try:
                embs = embeddings_model.embed_documents(batch)
                all_embeddings.extend(embs)
                break
            except Exception as e:
                wait = 10 * (attempt + 1)
                print(f"       Error embeddings (intento {attempt+1}/5): {e}. Reintentando en {wait}s...")
                time.sleep(wait)
        else:
            print(f"       Embeddings fallaron para batch {i}. Usando vector cero.")
            all_embeddings.extend([[0.0] * 768] * len(batch))
    return all_embeddings


# Cache para estado de API Local
LOCAL_API_DISABLED = False
LOCAL_API_FAILURES = 0

def get_author_works_titles(openalex_id, limit=3):
    """Obtiene titulos de obras recientes de un autor en OpenAlex."""
    global LOCAL_API_DISABLED, LOCAL_API_FAILURES
    if not openalex_id:
        return []
    oa_id_clean = str(openalex_id).split('/')[-1].strip()
    titles = []
    
    # Intentar API Local primero (si no esta deshabilitada)
    if not LOCAL_API_DISABLED:
        local_api = os.getenv("OPENALEX_LOCAL_API", "http://localhost:5012")
        try:
            url = f"{local_api}/works"
            params = {"filter": f"author.id:{oa_id_clean}", "per_page": limit, "sort": "publication_year:desc"}
            # Reducimos timeout a 2s para evitar bloqueos si la API no responde
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(url, params=params)
                if resp.status_code == 200:
                    results = resp.json().get('results', [])
                    titles = [w.get('title') for w in results if w.get('title')]
                    LOCAL_API_FAILURES = 0 # Reset si tiene exito
                else:
                    LOCAL_API_FAILURES += 1
        except Exception:
            LOCAL_API_FAILURES += 1
        
        if LOCAL_API_FAILURES >= 3:
            print(f"      [WARN] API Local en {local_api} no responde. Deshabilitando para este lote.")
            LOCAL_API_DISABLED = True

    # Si no hay titulos y no esta bloqueada, intentar API Oficial (pyalex) con backup
    if not titles:
        try:
            import pyalex
            results = pyalex.Works().filter(authorships={"author": {"id": oa_id_clean}}).sort(publication_year="desc").get(per_page=limit)
            titles = [w.get('title') for w in results if w.get('title')]
        except:
            pass
            
    return titles[:limit]


def get_orcid_works_titles(orcid_url, limit=3):
    """Obtiene ttulos de obras recientes de un perfil ORCID."""
    if not orcid_url:
        return []
    orcid_id = str(orcid_url).rstrip('/').split('/')[-1]
    import requests
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            works_data = response.json().get('group', [])
            titles = []
            for work_group in works_data[:limit*2]: # Pedir un poco ms por si hay nulos
                summary = work_group.get('work-summary', [{}])[0]
                title_node = summary.get('title', {}) or {}
                t = title_node.get('title', {}).get('value')
                if t:
                    titles.append(t)
                if len(titles) >= limit:
                    break
            return titles
    except:
        pass
    return []


def get_search_keys(name: str):
    """Extrae k1 y k2 (apellidos/nombres) para bsqueda en ClickHouse."""
    parts = [p.strip() for p in normalize_text(name).replace(',', ' ').split() if len(p) > 2]
    if len(parts) < 2:
        k1 = parts[0] if parts else normalize_text(name)
        k2 = k1
    else:
        if ',' in name:
            apellidos = [p for p in normalize_text(name.split(',')[0]).split() if len(p) > 2]
            nombres = [p for p in normalize_text(name.split(',')[1]).split() if len(p) > 2]
            k1 = apellidos[0] if apellidos else parts[0]
            k2 = nombres[0] if nombres else parts[-1]
        else:
            k1, k2 = parts[0], parts[-1]
    return k1, k2


def get_accent_insensitive_regex(text: str) -> str:
    """Genera una regex para ClickHouse que ignora acentos y es case-insensitive."""
    vowel_map = {
        'a': '[aáàâä]', 'e': '[eéèêë]', 'i': '[iíìîï]', 
        'o': '[oóòôö]', 'u': '[uúùûü]'
    }
    regex = ""
    for char in text.lower():
        regex += vowel_map.get(char, char)
    return f"(?i){regex}"


def search_openalex_authors_batch(names_info: list, limit_per_name: int = 5) -> dict:
    """Busca candidatos en ClickHouse para un lote de investigadores usando Regex de alto rendimiento.
    names_info: lista de diccionarios {snii_name, k1, k2}
    Retorna: {snii_name: [candidatos]}
    """
    if not names_info:
        return {}
    
    try:
        print("      [DEBUG] Iniciando busqueda batch en OpenAlex...")
        ch = get_ch_client()
        clauses = []
        for info in names_info:
            r1 = get_accent_insensitive_regex(info['k1'].replace("'", "''"))
            r2 = get_accent_insensitive_regex(info['k2'].replace("'", "''"))
            # Usamos match() de ClickHouse para bsqueda por regex multi-token
            clauses.append(f"(match(display_name, '{r1}') AND match(display_name, '{r2}'))")
        
        # Optimizacin: Pre-filtro rpido para reducir el escaneo de filas
        # Obtenemos todos los tokens (k1) de los investigadores en el lote
        all_k1 = list(set([info['k1'].lower() for info in names_info if len(info['k1']) > 2]))
        if not all_k1:
            return {info['snii_name']: [] for info in names_info}
            
        pre_filter = f"multiSearchAnyCaseInsensitive(display_name, {all_k1})"
        
        where_clause = " OR ".join(clauses)
        
        # Lmite proporcional al lote
        query_limit = min(len(names_info) * limit_per_name * 10, 2000)
        
        query = f"""
        SELECT id, display_name, orcid, raw_data, ids
        FROM {CH_DB}.authors_seed_mexico
        WHERE ({pre_filter}) AND ({where_clause})
        LIMIT {query_limit}
        """
        rows = ch.query(query).result_rows
        print(f"      [DEBUG] OpenAlex devolvio {len(rows)} filas.")
        
        from Levenshtein import jaro_winkler
        results_map = {info['snii_name']: [] for info in names_info}
        
        # Cache de nombres normalizados para el batch
        batch_normalized = {}
        for info in names_info:
            name = info['snii_name']
            batch_normalized[name] = " ".join(sorted([t for t in normalize_text(name).replace(',', ' ').split() if len(t) > 1]))

        for r in rows:
            openalex_id, disp_name, orcid_val, raw_data_str, ids_json = r[0], r[1], r[2], r[3], r[4]
            
            # Extraer afiliacin una sola vez por candidato
            inst_name = ""
            try:
                raw_data = json.loads(raw_data_str) if isinstance(raw_data_str, str) else raw_data_str
                affils = raw_data.get('affiliations') or []
                if affils and isinstance(affils, list) and len(affils) > 0:
                    inst_info = affils[0].get('institution')
                    if inst_info and isinstance(inst_info, dict):
                        inst_name = inst_info.get('display_name')
                if not inst_name:
                    lki_list = raw_data.get('last_known_institutions')
                    if lki_list and isinstance(lki_list, list) and len(lki_list) > 0:
                        inst_name = lki_list[0].get('display_name')
                if not inst_name:
                    lki_dict = raw_data.get('last_known_institution')
                    if lki_dict and isinstance(lki_dict, dict):
                        inst_name = lki_dict.get('display_name')
            except: pass
            
            cand_norm = " ".join(sorted([t for t in normalize_text(str(disp_name)).replace(',', ' ').split() if len(t) > 1]))
            
            # Comparar este candidato contra CADA investigador del batch
            for snii_name, sorted_seed in batch_normalized.items():
                ns = jaro_winkler(sorted_seed, cand_norm)
                if ns > 0.75:
                    scopus_ids = []
                    try:
                        ids_data = json.loads(ids_json) if isinstance(ids_json, str) else (ids_json or {})
                        scopus_raw = ids_data.get('scopus') or []
                        scopus_ids = [scopus_raw] if isinstance(scopus_raw, str) else scopus_raw
                    except: pass
                    
                    results_map[snii_name].append({
                        "openalex_id": openalex_id,
                        "name": disp_name,
                        "orcid": orcid_val or None,
                        "inst": inst_name or "",
                        "scopus_ids": scopus_ids,
                        "score": ns
                    })
        
        # Sort and limit
        for name in results_map:
            results_map[name].sort(key=lambda x: x['score'], reverse=True)
            results_map[name] = results_map[name][:limit_per_name]
            for cand in results_map[name]:
                cand['works'] = [] # Títulos eliminados de la identificación para mayor velocidad

        return results_map
    except Exception as e:
        print(f"      [ERROR] Error en busqueda batch OpenAlex: {e}")
        return {info['snii_name']: [] for info in names_info}


def search_orcid_records_batch(names_info: list, limit_per_name: int = 5) -> dict:
    """Busca candidatos en el dump de ORCID (ClickHouse) para un lote de investigadores."""
    if not names_info:
        return {}
    
    try:
        print("      [DEBUG] Iniciando busqueda batch en ORCID...")
        ch = get_orcid_client()
        # Verificar si la base de datos de ORCID existe en este servidor (con manejo de errores para evitar cuelgues)
        try:
            db_exists = ch.query(f"SELECT count() FROM system.databases WHERE name = '{CH_DB_ORCID}'").result_rows[0][0]
            if not db_exists:
                print(f"      [INFO] Base de datos {CH_DB_ORCID} no encontrada en ClickHouse Local. Saltando.")
                return {info['snii_name']: [] for info in names_info}
        except Exception as conn_err:
            print(f"      [WARN] No se pudo conectar a ClickHouse Local (ORCID): {conn_err}. Saltando busqueda ORCID.")
            return {info['snii_name']: [] for info in names_info}

        clauses = []
        for info in names_info:
            k1 = info['k1'].replace("'", "''").lower()
            k2 = info['k2'].replace("'", "''").lower()
            clauses.append(f"( (lower(family_name) LIKE '%{k1}%' OR lower(credit_name) LIKE '%{k1}%') AND (lower(given_names) LIKE '%{k2}%' OR lower(credit_name) LIKE '%{k2}%') )")

        # Optimizacin: Pre-filtro rpido con multiSearch
        all_tokens = []
        for info in names_info:
            all_tokens.append(info['k1'].lower())
            all_tokens.append(info['k2'].lower())
        all_tokens = list(set([t for t in all_tokens if len(t) > 2]))
        
        pre_filter = f"multiSearchAnyCaseInsensitive(credit_name, {all_tokens}) OR multiSearchAnyCaseInsensitive(family_name, {all_tokens})"
        
        where_clause = " OR ".join(clauses)
        
        query = f"""
        SELECT orcid, given_names, family_name, credit_name, last_affiliation 
        FROM {CH_DB_ORCID}.orcid_records 
        WHERE ({pre_filter}) AND ({where_clause})
        LIMIT {len(names_info) * limit_per_name * 10}
        """
        rows = ch.query(query).result_rows
        
        from Levenshtein import jaro_winkler
        results_map = {info['snii_name']: [] for info in names_info}
        
        # Cache de nombres normalizados para el batch
        batch_normalized = {}
        for info in names_info:
            name = info['snii_name']
            batch_normalized[name] = " ".join(sorted([t for t in normalize_text(name).replace(',', ' ').split() if len(t) > 1]))

        for r in rows:
            orc, gn, fn, cn, aff = r[0], str(r[1] or ''), str(r[2] or ''), str(r[3] or ''), str(r[4] or '')
            cand_name = f"{gn} {fn}".strip() if not cn else cn
            cand_norm = " ".join(sorted([t for t in normalize_text(cand_name).replace(',', ' ').split() if len(t) > 1]))
            
            for snii_name, sorted_seed in batch_normalized.items():
                ns = jaro_winkler(sorted_seed, cand_norm)
                if ns > 0.8:
                    results_map[snii_name].append({
                        "score": ns,
                        "name": cand_name,
                        "orcid": orc,
                        "aff": aff
                    })
        
        # Sort and limit for each name
        for name in results_map:
            results_map[name].sort(key=lambda x: x['score'], reverse=True)
            results_map[name] = results_map[name][:limit_per_name]
            
        return results_map
    except Exception as e:
        print(f"       Error en bsqueda batch ORCID: {e}")
        return {info['snii_name']: [] for info in names_info}


def search_openalex_authors(name: str, institution: str, limit: int = 5) -> list:
    """Intenta buscar un autor usando la API Local (Modo Rayo) y cae a ClickHouse si falla."""
    local_api = os.getenv("OPENALEX_LOCAL_API", "http://localhost:5012")
    
    # 1. Intentar API Local (Modo Rayo)
    try:
        url = f"{local_api}/authors"
        params = {"filter": f"display_name.search:{name}", "per_page": limit}
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 200:
                results = resp.json().get('results', [])
                if results:
                    print(f"       [INFO] {len(results)} candidatos encontrados via API Local.")
                    cands = []
                    for r in results:
                        # Adaptar formato de API al formato interno
                        cands.append({
                            "openalex_id": r.get('id'),
                            "name": r.get('display_name'),
                            "orcid": r.get('orcid'),
                            "inst": (r.get('last_known_institution') or {}).get('display_name', ""),
                            "scopus_ids": (r.get('ids') or {}).get('scopus', []),
                            "score": 0.9 # Score base alto para resultados de API de busqueda
                        })
                    return cands
    except Exception as e:
        print(f"       [DEBUG] API Local no disponible para busqueda individual: {e}")

    # 2. Fallback a ClickHouse (Lógica Batch individualizada)
    print(f"       [INFO] Consultando ClickHouse (Fallback)...")
    k1, k2 = get_search_keys(name)
    res = search_openalex_authors_batch([{'snii_name': name, 'k1': k1, 'k2': k2}], limit_per_name=limit)
    return res.get(name, [])


def resolve_snii_identities(limit_test=None, target_name=None, force=False, ingest=False, force_ingest=False):
    """Pipeline principal: SNII  candidatos multi-fuente  verificacin LLM  JSON de resultados."""
    print("\n Resolviendo identidades SNII con LLM (bsqueda semntica + reranking)...")

    # Flag global para evitar trabarnos si la API oficial nos bloquea
    api_oficial_bloqueada = False

    df = pd.read_excel(SNII_PATH)

    if target_name:
        mask = df['NOMBRE DEL INVESTIGADOR'].str.contains(target_name, case=False, na=False)
        df = df[mask].reset_index(drop=True)
        if df.empty:
            print(f"     No se encontr ningn investigador que coincida con '{target_name}' en el padrn SNII.")
            return
        print(f"    Modo bsqueda individual: {len(df)} registro(s) encontrado(s) para '{target_name}'.")

    if limit_test and not target_name:
        df = df.head(limit_test)
        print(f"   Modo prueba: procesando solo {limit_test} registros.")

    local_store = QdrantStore(collection_name="local_authors")
    orcid_store = QdrantStore(collection_name="orcid_authors_vec")

    name_col = 'NOMBRE DEL INVESTIGADOR'
    inst_col = 'INSTITUCION DE ACREDITACION'
    dep_inst_col = 'DEPENDENCIA DE ACREDITACION'
    sub_inst_col = 'SUBDEPENDENCIA DE ACREDITACION'

    # Normalizar columnas del dataframe principal
    df.columns = [normalize_text(c).upper() for c in df.columns]

    output_path = os.path.join("data", "snii_llm_verified_matches.json")
    verified_results = []
    lookup = {}  # (name, inst, sub) -> index
    processed_in_this_run = set()

    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                temp_data = json.load(f)
                # Deduplicar al cargar
                seen_keys = set()
                for r in temp_data:
                    key = (r["snii_author"], r.get("snii_institution", ""), r.get("snii_subdependency", ""))
                    if key not in seen_keys:
                        lookup[key] = len(verified_results)
                        verified_results.append(r)
                        seen_keys.add(key)
            print(f"   Cargados {len(verified_results)} registros previos deduplicados.")
        except Exception as e:
            print(f"    No se pudo cargar progreso previo: {e}")

    #  Bucle Principal por Lotes 
    batch_size = 10 # Reducido de 50 a 10 para evitar timeouts en ClickHouse por Regex pesado
    rows_list = list(df.iterrows())
    
    for b_idx in range(0, len(rows_list), batch_size):
        chunk = rows_list[b_idx : b_idx + batch_size]
        
        # 1. Bsqueda Batch de candidatos (OpenAlex + ORCID)
        batch_query_info = []
        for _, row in chunk:
            s_name = str(row[name_col]).strip()
            k1, k2 = get_search_keys(s_name)
            batch_query_info.append({'snii_name': s_name, 'k1': k1, 'k2': k2})
        
        print(f"\n Consultando lote de {len(batch_query_info)} investigadores en ClickHouse (OpenAlex + ORCID)...")
        batch_oa_map = search_openalex_authors_batch(batch_query_info, limit_per_name=5)
        batch_orcid_map = search_orcid_records_batch(batch_query_info, limit_per_name=4)

        for idx, row in chunk:
            snii_name = "Desconocido"
            final_inst = "Desconocido"
            final_sub = "Desconocido"
            key = None
            try:
                snii_name = str(row[name_col]).strip()

                raw_inst = str(row[inst_col]).strip() if pd.notna(row[inst_col]) else ""
                raw_dep = str(row[dep_inst_col]).strip() if pd.notna(row[dep_inst_col]) else ""
                raw_sub = str(row[sub_inst_col]).strip() if pd.notna(row[sub_inst_col]) else ""

                if raw_inst.upper() in ["SIN INSTITUCIN", "SIN INSTITUCION"]:
                    final_inst = "SIN INSTITUCIN"
                    final_sub = "NO APLICA"
                elif raw_sub.upper() in ["SIN INFORMACION", "SIN INFORMACIN", ""]:
                    final_inst = raw_inst
                    final_sub = raw_dep if raw_dep else raw_sub
                else:
                    final_inst = raw_inst
                    final_sub = raw_sub

                key = (snii_name, final_inst, final_sub)

                # Evitar procesar lo mismo dos veces en la misma corrida (duplicados en Excel)
                if key in processed_in_this_run:
                    continue

                # Si ya existe match confirmado y no forzamos, saltar
                if key in lookup and not force:
                    existing_record = verified_results[lookup[key]]
                    if existing_record.get("match") is True:
                        if ingest:
                            print(f"       [Auto-Ingest] Usando match previo para {snii_name}...")
                            try:
                                ingest_researcher_data(existing_record, force=force_ingest, force_local=True)
                            except Exception as e:
                                print(f"       Error en Auto-Ingest previo: {e}")
                        processed_in_this_run.add(key)
                        continue

                snii_info = f"Nombre: {snii_name} | Institucin: {final_inst} | Subdependencia: {final_sub}"

                print(f"   [{idx+1}/{len(df)}] Verificando: {snii_name}...")

                # Obtener embedding del autor SNII
                emb = get_embeddings([snii_info])[0]

                all_candidates = []
                is_unam = any(k in final_inst.lower() for k in ['unam', 'nacional autonoma de mexico', 'nacional autnoma de mxico'])

                #  OpenAlex Authors (Ya pre-cargados en Batch) 
                openalex_candidates = batch_oa_map.get(snii_name, [])
                
                # --- NUEVO: Lgica de Auto-Confirmacin (Ahorro de LLM) ---
                best_oa = openalex_candidates[0] if openalex_candidates else None
                if best_oa and best_oa['score'] > 0.98:
                    # Si el nombre es casi idntico y la institucin coincide, auto-confirmamos
                    cand_inst = best_oa['affiliation'].lower()
                    if any(k in cand_inst for k in normalize_text(final_inst).split()):
                        print(f"       [Auto-Match] Confianza alta para {snii_name}. Saltando LLM.")
                        match_result = {
                            "snii_author": snii_name,
                            "snii_institution": final_inst,
                            "snii_subdependency": final_sub,
                            "match": True,
                            "source": best_oa['source'],
                            "openalex_id": best_oa['openalex_id'],
                            "name": best_oa['name'],
                            "orcid": best_oa['orcid'],
                            "affiliation": best_oa['affiliation'],
                            "scopus_ids": best_oa.get('scopus_ids', []),
                            "confidence": "AUTO_HIGH",
                            "reason": "Nombre e Institucin con coincidencia exacta (Heurstica)"
                        }
                        verified_results.append(match_result)
                        with open(output_path, "w", encoding="utf-8") as f:
                            json.dump(verified_results, f, ensure_ascii=False, indent=2)
                        processed_in_this_run.add(key)
                        continue

                for c in openalex_candidates:
                    all_candidates.append({
                        "source": "OpenAlex DB Local",
                        "openalex_id": c['openalex_id'],
                        "name": c['name'],
                        "orcid": c['orcid'],
                        "affiliation": c['inst'],
                        "scopus_ids": c.get('scopus_ids', []),
                        "works": c.get('works', []),
                        "score_vec": c['score']
                    })

                # Saltamos Qdrant si ya tenemos suficientes candidatos de calidad de OpenAlex
                high_quality_oa = [c for c in openalex_candidates if c['score'] >= 0.95 and (c.get('orcid') or c.get('inst'))]

                if is_unam and not high_quality_oa:
                    # UNAM: Priorizar local via Qdrant (ah est SIIA)
                    local_candidates = local_store.search(emb, limit=5)
                    orcid_candidates = orcid_store.search(emb, limit=2)
                    for c in local_candidates:
                        works = get_orcid_works_titles(c.get("orcid")) if c.get("orcid") else []
                        all_candidates.append({
                            "source": "Local (Neo4j/SIIA)",
                            "name": c.get("name"), "orcid": c.get("orcid"), "affiliation": c.get("affiliation"),
                            "works": works, "score_vec": c.get("score")
                        })
                    for c in orcid_candidates:
                        orcid_works = get_orcid_works_titles(c.get("orcid"))
                        all_candidates.append({
                            "source": "ORCID Dump (Qdrant)",
                            "name": c.get("name"), "orcid": c.get("orcid"), "affiliation": c.get("affiliation"),
                            "works": orcid_works, "score_vec": c.get("score")
                        })
                elif not high_quality_oa:
                    # Resto del pas: ORCID Qdrant + ClickHouse Batch Match
                    orcid_vec_candidates = orcid_store.search(emb, limit=5)
                    for c in orcid_vec_candidates:
                        orcid_works = get_orcid_works_titles(c.get("orcid"))
                        all_candidates.append({
                            "source": "ORCID Dump (Qdrant)",
                            "name": c.get("name"), "orcid": c.get("orcid"), "affiliation": c.get("affiliation"),
                            "works": orcid_works, "score_vec": c.get("score")
                        })

                    # ORCID ClickHouse Batch (ya pre-cargado)
                    orcid_ch_candidates = batch_orcid_map.get(snii_name, [])
                    for c in orcid_ch_candidates:
                        if not any(a.get('orcid') == c['orcid'] for a in all_candidates):
                            ch_works = get_orcid_works_titles(c.get("orcid"))
                            all_candidates.append({
                                "source": "ClickHouse ORCID Dump",
                                "name": c['name'], "orcid": c['orcid'], "affiliation": c['aff'],
                                "works": ch_works, "score_vec": c['score']
                            })

                # --- Fallback de OpenAlex (Prioridad API Local) ---
                if not high_quality_oa:
                    print(f"       Consultando API Local de OpenAlex (Modo Rayo)...")
                    cands_oa_api = search_openalex_authors(snii_name, final_inst)
                    for c in cands_oa_api:
                        if not any(a.get('openalex_id') == c['openalex_id'] for a in all_candidates):
                            # El fetch de obras ya viene dentro de search_openalex_authors o se hace aqui
                            all_candidates.append({
                                "source": "OpenAlex Local (API)",
                                "openalex_id": c['openalex_id'], "name": c['name'], "orcid": c['orcid'], "affiliation": c['inst'],
                                "works": c.get('works', []), "score_vec": 0.0
                            })

                # Preparar Prompt para el LLM y mostrar candidatos
                candidates_str = ""
                if not all_candidates:
                    print("       No se encontraron candidatos en ninguna fuente.")
                else:
                    print(f"       {len(all_candidates)} candidato(s) encontrado(s):")
                    for i, cand in enumerate(all_candidates):
                        works_str = f" | Obras: {', '.join(cand['works'])}" if cand.get('works') else ""
                        cand_info = f"[{cand['source']}] {cand['name']} | ORCID: {cand['orcid']} | Afiliacin: {cand['affiliation']}{works_str}"
                        print(f"         {i+1}. {cand_info}")
                        candidates_str += f"{i+1}. {cand_info}\n"

                prompt = f"""Eres un experto investigador bibliogrfico. Tu tarea es identificar si alguno de los candidatos recuperados coincide exactamente con el investigador del SNII.

Investigador SNII buscado:
{snii_info}

Candidatos potenciales:
{candidates_str}

Instrucciones vitales:
1. Analiza el nombre (variaciones por apellidos compuestos, omisiones de nombre central, apodos, etc).
2. Analiza la afiliacin desglosada en Nivel 1 (Institucin) y Nivel 2 (Subdependencia).
3. ATENCIN: Si el investigador SNII indica 'Institucin: SIN INSTITUCIN', DEBES IGNORAR por completo las afiliaciones de los candidatos y realizar el match 100% evaluando la compatibilidad de los nombres. No penalices al candidato por tener una institucin registrada en ORCID si al SNII le falta el dato!
4. Si crees que hay coincidencia segura con uno o MS perfiles (ej. perfiles fragmentados del mismo autor en OpenAlex), responde con una lista de sus nmeros en "matched_candidate_indices".
5. No respondas con "NINGUNO" si hay dudas; mejor marca "match": false.
6. Requisito de formato de salida estricto: JSON plano {{
    "match": true/false, 
    "matched_candidate_indices": [int, int] o [], 
    "orcid": "el ORCID si lo encontraste", 
    "reason": "breve justificacin",
    "discarded_candidates": [
        {{"index": int, "name": "...", "orcid": "...", "reason": "razn breve del descarte"}}
    ]
}}. No agregues markdown de bloques de cdigo.

Respuesta:"""

                max_retries = 3
                res_json = {}
                for attempt in range(max_retries):
                    try:
                        response = llm.invoke([HumanMessage(content=prompt)])
                        res_text = response.content.strip()
                        # Limpiar posibles bloques de cdigo
                        if "```json" in res_text:
                            res_text = res_text.split("```json")[1].split("```")[0].strip()
                        elif "```" in res_text:
                            res_text = res_text.split("```")[1].split("```")[0].strip()

                        res_json = json.loads(res_text)
                        break # xito
                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 10
                            print(f"       Error LLM/JSON (intento {attempt+1}/{max_retries}): {e}. Reintentando en {wait_time}s...")
                            time.sleep(wait_time)
                        else:
                            raise e

                result_entry = {
                    "snii_author": snii_name,
                    "snii_institution": final_inst,
                    "snii_subdependency": final_sub,
                    "match": False,
                    "matched_author": None,
                    "matched_orcid": None,
                    "reason": res_json.get("reason", "No match"),
                    "discarded_candidates": res_json.get("discarded_candidates", []),
                    "source": None
                }

                if res_json.get("match"):
                    m_indices = res_json.get("matched_candidate_indices") or []
                    if not m_indices and res_json.get("candidate_index"):
                        m_indices = [res_json.get("candidate_index")]
                        
                    valid_matches = []
                    for m_idx in m_indices:
                        if m_idx and 1 <= m_idx <= len(all_candidates):
                            valid_matches.append(all_candidates[m_idx - 1])
                    
                    if valid_matches:
                        confirmed_orcid = res_json.get("orcid")
                        if not confirmed_orcid or str(confirmed_orcid).lower() == 'none':
                            confirmed_orcid = next((m.get('orcid') for m in valid_matches if m.get('orcid') and str(m.get('orcid')).lower() != 'none'), None)

                        scopus_ids = []
                        for m in valid_matches:
                            if m.get('scopus_ids'):
                                scopus_ids.extend(m.get('scopus_ids'))
                                
                        openalex_ids = [m.get('openalex_id') for m in valid_matches if m.get('openalex_id')]
                        source_names = list(set(m['source'] for m in valid_matches))

                        if not scopus_ids and confirmed_orcid and str(confirmed_orcid).lower() != 'none':
                            clean_orcid = str(confirmed_orcid).replace('https://orcid.org/', '').strip()
                            try:
                                ch_remote = get_ch_client()
                                q_remote = f"SELECT ids FROM {CH_DB}.authors_seed_mexico WHERE orcid = '{clean_orcid}' LIMIT 1"
                                rows = ch_remote.query(q_remote).result_rows
                                if rows and rows[0][0]:
                                    ext = json.loads(rows[0][0]) if isinstance(rows[0][0], str) else rows[0][0]
                                    raw = ext.get('Scopus') or ext.get('scopus') or []
                                    scopus_ids = [raw] if isinstance(raw, str) else raw
                            except Exception as se:
                                print(f"       No se pudieron extraer Scopus IDs de Remote: {se}")

                        names_str = " + ".join([m['name'] for m in valid_matches])
                        print(f"       MATCH CONFIRMADO por LLM: [SNII] {snii_name}  [Match] {names_str} ({confirmed_orcid})")
                        result_entry.update({
                            "match": True,
                            "matched_author": valid_matches[0]['name'],
                            "matched_orcid": confirmed_orcid,
                            "openalex_ids": openalex_ids,
                            "matched_openalex_id": openalex_ids[0] if openalex_ids else None,
                            "scopus_ids": list(set(scopus_ids)),
                            "source": ", ".join(source_names)
                        })
                    else:
                        print(f"       NINGUNO: El LLM devolvi ndices invlidos para {snii_name}")
                else:
                    print(f"       NINGUNO: No se encontr match para {snii_name}")

                # Actualizar o Aadir (con Red de Seguridad)
                if key in lookup:
                    if result_entry.get("match") is False:
                        old_rec = verified_results[lookup[key]]
                        if old_rec.get("match") is True:
                            print(f"       [Safety] El LLM no confirm match esta vez, pero exista uno previo. Preservando datos anteriores.")
                            result_entry = old_rec
                    verified_results[lookup[key]] = result_entry
                else:
                    lookup[key] = len(verified_results)
                    verified_results.append(result_entry)
                    
                if result_entry.get("match") is True and ingest:
                    print(f"       [Auto-Ingest] Iniciando carga de trabajos para {snii_name}...")
                    try:
                        ingest_researcher_data(result_entry, force=force_ingest, force_local=True)
                    except Exception as e:
                        print(f"       Error en Auto-Ingest: {e}")

                processed_in_this_run.add(key)

                # Guardado incremental cada 10 registros
                if (idx + 1) % 10 == 0:
                    os.makedirs("data", exist_ok=True)
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(verified_results, f, ensure_ascii=False, indent=2)

            except Exception as e:
                print(f"       Error procesando {snii_name}: {e}")
                # Manejo de error con red de seguridad
                error_entry = {
                    "snii_author": snii_name,
                    "snii_institution": final_inst,
                    "snii_subdependency": final_sub,
                    "match": False,
                    "matched_author": None,
                    "matched_orcid": None,
                    "reason": f"Error en procesamiento: {e}",
                    "source": None
                }
                if key in lookup:
                    old_rec = verified_results[lookup[key]]
                    if old_rec.get("match") is True:
                        print(f"       [Safety] Error, pero exista un match previo. Preservando datos anteriores.")
                        error_entry = old_rec
                    verified_results[lookup[key]] = error_entry
                else:
                    lookup[key] = len(verified_results)
                    verified_results.append(error_entry)

                if error_entry.get("match") is True and ingest:
                    print(f"       [Auto-Ingest] Iniciando carga (va Safety Match) para {snii_name}...")
                    try:
                        ingest_researcher_data(error_entry, force=force_ingest, force_local=True)
                    except: pass

                processed_in_this_run.add(key)
                # Guardar progreso
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(verified_results, f, ensure_ascii=False, indent=2)

    # Guardado final
    os.makedirs("data", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(verified_results, f, ensure_ascii=False, indent=2)

    num_matches = sum(1 for r in verified_results if r.get('match') is True)
    print(f"\n Resolucin de identidades completada. {len(verified_results)} registros evaluados y guardados en {output_path}")
    print(f" Total de investigadores con match confirmado: {num_matches} ({num_matches / max(1, len(verified_results)) * 100:.1f}%)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Resuelve identidades SNII contra OpenAlex/ORCID usando LLM.")
    parser.add_argument("--limit", type=int, help="Lmite de registros del padrn completo para pruebas (opcional).")
    parser.add_argument("--name", type=str, help="Filtra el padrn SNII por nombre de investigador.")
    parser.add_argument("--force", action="store_true", help="Fuerza la re-verificacin incluso si ya existe match.")
    parser.add_argument("--ingest", action="store_true", help="Cargar automticamente los trabajos al confirmar match")
    parser.add_argument("--force-ingest", action="store_true", help="Forzar carga de trabajos incluso si ya existen")
    args = parser.parse_args()

    resolve_snii_identities(limit_test=args.limit, target_name=args.name, force=args.force, ingest=args.ingest, force_ingest=args.force_ingest)
