"""
vectorize_researchers.py
────────────────────────
Implementa la estrategia de triple vectorización semántica en Qdrant:
1. Autores locales (Neo4j Mexico) -> coleccion 'local_authors'
2. Autores ORCID (Clickhouse) -> coleccion 'orcid_authors_vec'
3. Autores SNII 2025 (Excel) -> coleccion 'snii_authors_vec'
4. Validacion LLM (Reranking) -> json de resultados
"""

import os
import sys
import json
import pandas as pd
import httpx
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.messages import HumanMessage

# Añadir path raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from match_snii_orcid import normalize_text, get_client as get_ch_client, SNII_PATH

# Cargar .env
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

# --- Config Embeddings (Dinamización de MEX_KEYWORDS) ---
# Empezamos con una base sólida
MEX_KEYWORDS = [
    "mexico", "mexic", "unam", "ipn", "cinvestav", "tecnologico", "autonoma", "itamb", "colmex", 
    "buap", "uaslp", "udem", "itesm", "uam", "politecnico"
]

# Expandir red de seguridad con instituciones del SNII
if os.path.exists(SNII_PATH):
    try:
        print(f"📡 Cargando instituciones desde SNII para expandir red de seguridad...")
        df_snii = pd.read_excel(SNII_PATH)
        instituciones = df_snii['INSTITUCIÓN DE ACREDITACIÓN'].dropna().unique().tolist()
        subdependencias = df_snii['SUBDEPENDENCIA DE ACREDITACIÓN'].dropna().unique().tolist()
        
        # Combinar, limpiar (quitar comillas para SQL) y añadir palabras de más de 3 letras
        for ext_name in instituciones + subdependencias:
            # Limpieza básica para SQL
            clean_name = str(ext_name).lower().replace("'", "").strip()
            # Si tiene más de una palabra, tomamos la primera significativa o el nombre corto
            if len(clean_name) > 4:
                MEX_KEYWORDS.append(clean_name)
        
        # Eliminar duplicados y ordenar
        MEX_KEYWORDS = list(set(MEX_KEYWORDS))
        print(f"✅ Red de seguridad expandida a {len(MEX_KEYWORDS)} términos clave.")
    except Exception as e:
        print(f"⚠️ No se pudo expandir MEX_KEYWORDS desde Excel: {e}")

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

http_client = httpx.Client(verify=False, timeout=120)

embeddings_model = OpenAIEmbeddings(
    model=model_name,
    base_url=auth_url,
    api_key="lm-studio",
    http_client=http_client,
    check_embedding_ctx_length=False
)

def get_embeddings(texts: list, batch_size: int = 10) -> list:
    if not texts: return []
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = [str(t) if t else " " for t in texts[i:i+batch_size]]
        for attempt in range(5):
            try:
                embs = embeddings_model.embed_documents(batch)
                all_embeddings.extend(embs)
                break
            except Exception as e:
                wait = 10 * (attempt + 1)
                print(f"      ⚠️ Error embeddings (intento {attempt+1}/5): {e}. Reintentando en {wait}s...")
                time.sleep(wait)
        else:
            # Si todos los intentos fallaron, usar vector cero para no perder el registro
            print(f"      ❌ Embeddings fallaron para batch {i}. Usando vector cero.")
            all_embeddings.extend([[0.0] * 768] * len(batch))
    return all_embeddings

# --- Config LLM ---
llm_model_name = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
llm = ChatOpenAI(
    model=llm_model_name,
    base_url=auth_url,
    api_key="lm-studio",
    http_client=http_client,
    temperature=0
)

# --- Pasos de Vectorización ---

def vectorize_local_authors():
    """Paso 1: Neo4j (Mexico) -> Qdrant 'local_authors'"""
    print("\n🚀 Paso 1: Vectorizando autores locales de Neo4j...")
    from ingestion.extract_authors_local import _parse_meta
    
    graph = Neo4jGraphStore()
    q_store = QdrantStore(collection_name="local_authors")
    
    query = """
    MATCH (e:Entity {name: 'Mexico'})-[:HAS_PAPER]->(p:Paper)
    WHERE p.raw_metadata IS NOT NULL
    RETURN p.raw_metadata AS raw_json
    """
    
    docs_map = {} # orcid -> data
    with graph.driver.session() as session:
        result = list(session.run(query))
        print(f"   Papers recuperados de Neo4j {len(result)}...")
        for r in result:
            data = json.loads(r["raw_json"])
            authorships = data.get('authorships', [])
            for auth in authorships:
                author_info = auth.get('author', {})
                name = author_info.get('display_name')
                orcid_url = author_info.get('orcid')
                
                if not orcid_url or not name: continue
                
                # --- Filtro de Afiliación Mexicana ---
                insts = auth.get('institutions', [])
                is_mexican = False
                author_affs = []
                
                for inst in insts:
                    i_name = inst.get('display_name', '')
                    i_country = inst.get('country_code', '')
                    
                    if i_country == 'MX' or any(k in (i_name.lower() if i_name else "") for k in MEX_KEYWORDS):
                        is_mexican = True
                    
                    if i_name:
                        author_affs.append(i_name)
                
                if not is_mexican: 
                    continue
                
                orcid = orcid_url.split('/')[-1]
                main_aff = author_affs[0] if author_affs else "Sin Afiliación"
                
                if orcid not in docs_map:
                    docs_map[orcid] = {
                        "name": name,
                        "orcid": orcid,
                        "affiliations": {}
                    }
                
                docs_map[orcid]["affiliations"][main_aff] = docs_map[orcid]["affiliations"].get(main_aff, 0) + 1

    docs = []
    for orcid, d in docs_map.items():
        main_aff = max(d["affiliations"], key=d["affiliations"].get)
        text = f"{d['name']} ({main_aff})" if main_aff != "Sin Afiliación" else f"{d['name']}"
        docs.append({
            "text": text,
            "title": f"local_{orcid}",
            "name": d["name"],
            "orcid": orcid,
            "affiliation": main_aff
        })
    
    print(f"   Autores únicos con ORCID y afiliación MX identificados: {len(docs)}")

    if docs:
        print(f"   Generando embeddings para {len(docs)} autores locales...")
        texts = [d["text"] for d in docs]
        embs = get_embeddings(texts)
        q_store.add_documents(docs, embs)
    
    graph.close()

def vectorize_orcid_authors():
    """Paso 2: ORCID ClickHouse -> Qdrant 'orcid_authors_vec'"""
    print("\n🚀 Paso 2: Vectorizando autores ORCID (ClickHouse)...")
    ch_client = get_ch_client()
    q_store = QdrantStore(collection_name="orcid_authors_vec")
    
    # Construir condiciones dinámicas basadas en MEX_KEYWORDS para ClickHouse
    kw_conditions = " OR ".join([f"last_affiliation ILIKE '%{kw}%'" for kw in MEX_KEYWORDS])
    
    query = f"""
    SELECT orcid, given_names, family_name, credit_name, last_affiliation, last_affiliation_country
    FROM openalex.orcid_records
    WHERE (last_affiliation_country = 'MX') 
       OR ({kw_conditions})
    """
    
    print("   Consultando ClickHouse...")
    rows = ch_client.query(query).result_rows
    print(f"   {len(rows)} registros encontrados.")
    
    docs = []
    for r in rows:
        orcid, gn, fn, cn, aff, country = r
        full_name = cn if cn else f"{gn} {fn}".strip()
        
        text = f"{full_name} ({aff})" if aff else full_name
        docs.append({
            "text": text,
            "title": f"orcid_{orcid}", # ID determinista basado en ORCID
            "orcid": orcid,
            "name": full_name,
            "affiliation": aff,
            "country": country
        })
    
    if docs:
        print(f"   Generando embeddings para {len(docs)} autores ORCID...")
        batch_size = 100
        for i in range(0, len(docs), batch_size):
            batch_docs = docs[i:i+batch_size]
            texts = [d["text"] for d in batch_docs]
            embs = get_embeddings(texts)
            q_store.add_documents(batch_docs, embs)
            if (i + batch_size) % 500 == 0:
                print(f"      - {i+len(batch_docs)}/{len(docs)} procesados.")

def vectorize_snii_authors():
    """Paso 3: SNII Excel -> Qdrant 'snii_authors_vec' 
       Mencionado: Busca coincidencias en tiempo real contra local_authors y orcid_authors_vec.
    """
    print("\n🚀 Paso 3: Vectorizando autores SNII 2025 y buscando coincidencias semánticas...")
    from match_snii_orcid import SNII_PATH
    
    df = pd.read_excel(SNII_PATH)
    q_store = QdrantStore(collection_name="snii_authors_vec")
    
    # Stores para búsqueda
    local_store = QdrantStore(collection_name="local_authors")
    orcid_store = QdrantStore(collection_name="orcid_authors_vec")
    
    name_col = 'NOMBRE DEL INVESTIGADOR'
    inst_col = 'INSTITUCIÓN DE ACREDITACIÓN'
    dep_inst_col = 'DEPENDENCIA DE ACREDITACIÓN'
    sub_inst_col = 'SUBDEPENDENCIA DE ACREDITACIÓN'
    
    docs = []
    for _, row in df.iterrows():
        name = str(row[name_col]).strip()
        raw_inst = str(row[inst_col]).strip() if pd.notna(row[inst_col]) else ""
        raw_dep = str(row[dep_inst_col]).strip() if pd.notna(row[dep_inst_col]) else ""
        raw_sub = str(row[sub_inst_col]).strip() if pd.notna(row[sub_inst_col]) else ""
        
        if raw_inst.upper() in ["SIN INSTITUCIÓN", "SIN INSTITUCION"]:
            final_inst = "SIN INSTITUCIÓN"
            final_sub = "NO APLICA"
        elif raw_sub.upper() in ["SIN INFORMACION", "SIN INFORMACIÓN", ""]:
            final_inst = raw_inst
            final_sub = raw_dep if raw_dep else raw_sub
        else:
            final_inst = raw_inst
            final_sub = raw_sub
            
        # Limpieza semántica para Qdrant
        if final_inst == "SIN INSTITUCIÓN":
            text = name
        else:
            clean_sub = f", {final_sub}" if final_sub and final_sub != "NO APLICA" else ""
            text = f"{name} ({final_inst}{clean_sub})"
            
        docs.append({
            "text": text,
            "title": name,
            "name": name,
            "institution": final_inst,
            "subdependency": final_sub,
            "source": "SNII_2025"
        })
    
    if docs:
        print(f"   Procesando {len(docs)} investigadores SNII...")
        batch_size = 50 # Menor para ver logs de búsqueda
        for i in range(0, len(docs), batch_size):
            batch_docs = docs[i:i+batch_size]
            texts = [d["text"] for d in batch_docs]
            embs = get_embeddings(texts)
            
            # --- Búsqueda Semántica en Tiempo Real ---
            for idx, emb in enumerate(embs):
                snii_name = batch_docs[idx]["name"]
                
                # 1. Buscar en Local
                local_hits = local_store.search(emb, limit=1)
                if local_hits and local_hits[0]['score'] > 0.75:
                    hit = local_hits[0]
                    print(f"      [Match Local] {snii_name} ≈ {hit['name']} (ORCID: {hit.get('orcid')}) | Score: {hit['score']:.4f}")
                    batch_docs[idx]["match_local_orcid"] = hit.get('orcid')
                    batch_docs[idx]["match_local_score"] = hit['score']
                
                # 2. Buscar en ORCID
                orcid_hits = orcid_store.search(emb, limit=1)
                if orcid_hits and orcid_hits[0]['score'] > 0.75:
                    hit = orcid_hits[0]
                    # Solo imprimir si no hubo match local o si este es muy fuerte
                    if not batch_docs[idx].get("match_local_orcid"):
                        print(f"      [Match ORCID] {snii_name} ≈ {hit['name']} (ORCID: {hit.get('orcid')}) | Score: {hit['score']:.4f}")
                    batch_docs[idx]["match_orcid_id"] = hit.get('orcid')
                    batch_docs[idx]["match_orcid_score"] = hit['score']

            q_store.add_documents(batch_docs, embs)
            print(f"      - {i+len(batch_docs)}/{len(docs)} procesados.")

def search_openalex_authors(name: str, institution: str, limit: int = 5) -> list:
    """Busca candidatos en la tabla de autores de OpenAlex en ClickHouse local.
    Retorna hasta `limit` autores con nombre, orcid, last_known_institution y scopus ids.
    """
    try:
        ch = get_ch_client()
        # Tomamos la primera palabra del apellido (antes de la coma) como llave de búsqueda
        search_term = normalize_text(name.split(',')[0].split()[0]).replace("'", "").replace("'", "")
        if len(search_term) < 3:
            return []
        
        query = f"""
        SELECT
            id,
            display_name,
            orcid,
            last_known_institution_name,
            ids
        FROM openalex.authors
        WHERE lower(display_name) LIKE '%{search_term.lower()}%'
        LIMIT {limit * 5}
        """
        rows = ch.query(query).result_rows
        
        from Levenshtein import jaro_winkler
        sorted_seed = " ".join(sorted([t for t in normalize_text(name).replace(',', ' ').split() if len(t) > 1]))
        
        scored = []
        for r in rows:
            openalex_id, disp_name, orcid_val, inst_name, ids_json = r[0], r[1], r[2], r[3], r[4]
            cand_norm = " ".join(sorted([t for t in normalize_text(str(disp_name)).replace(',', ' ').split() if len(t) > 1]))
            ns = jaro_winkler(sorted_seed, cand_norm)
            if ns > 0.75:
                # Extraer Scopus IDs del campo ids (JSON) si están disponibles
                scopus_ids = []
                try:
                    ids_data = json.loads(ids_json) if isinstance(ids_json, str) else (ids_json or {})
                    scopus_raw = ids_data.get('scopus') or []
                    if isinstance(scopus_raw, str):
                        scopus_ids = [scopus_raw]
                    elif isinstance(scopus_raw, list):
                        scopus_ids = scopus_raw
                except Exception:
                    pass
                scored.append({
                    "openalex_id": openalex_id,
                    "name": disp_name,
                    "orcid": orcid_val or None,
                    "inst": inst_name or "",
                    "scopus_ids": scopus_ids,
                    "score": ns
                })
        
        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:limit]
    except Exception as e:
        print(f"      ⚠️ Error buscando en OpenAlex authors ClickHouse: {e}")
        return []

def vectorize_snii_with_llm(limit_test=None):
    """Paso 4: SNII -> Qdrant (Top 5 Local + Top 5 ORCID) -> LLM Verification"""
    print("\n🚀 Paso 4: Validando investigadores SNII con LLM (Reranking)...")
    from match_snii_orcid import SNII_PATH
    
    df = pd.read_excel(SNII_PATH)
    if limit_test:
        df = df.head(limit_test)
        print(f"   Modo prueba: procesando solo {limit_test} registros.")
    
    local_store = QdrantStore(collection_name="local_authors")
    orcid_store = QdrantStore(collection_name="orcid_authors_vec")
    
    name_col = 'NOMBRE DEL INVESTIGADOR'
    inst_col = 'INSTITUCIÓN DE ACREDITACIÓN'
    dep_inst_col = 'DEPENDENCIA DE ACREDITACIÓN'
    sub_inst_col = 'SUBDEPENDENCIA DE ACREDITACIÓN'
    
    output_path = os.path.join("data", "snii_llm_verified_matches.json")
    verified_results = []
    processed_names = set()
    
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                verified_results = json.load(f)
                # Solo mantener los ya confirmados (match: true). Los sin match se reintentan.
                processed_names = {
                    r["snii_author"] for r in verified_results
                    if r.get("match") is True
                }
                # Quitar de verified_results los que se van a reintentar
                verified_results = [
                    r for r in verified_results
                    if r["snii_author"] in processed_names
                ]
            print(f"   Continuando proceso: {len(processed_names)} investigadores ya validados.")
        except Exception as e:
            print(f"   ⚠️ No se pudo cargar progreso previo: {e}")

    for idx, row in df.iterrows():
        snii_name = str(row[name_col]).strip()
        if snii_name in processed_names:
            continue
            
        raw_inst = str(row[inst_col]).strip() if pd.notna(row[inst_col]) else ""
        raw_dep = str(row[dep_inst_col]).strip() if pd.notna(row[dep_inst_col]) else ""
        raw_sub = str(row[sub_inst_col]).strip() if pd.notna(row[sub_inst_col]) else ""
        
        if raw_inst.upper() in ["SIN INSTITUCIÓN", "SIN INSTITUCION"]:
            final_inst = "SIN INSTITUCIÓN"
            final_sub = "NO APLICA"
        elif raw_sub.upper() in ["SIN INFORMACION", "SIN INFORMACIÓN", ""]:
            final_inst = raw_inst
            final_sub = raw_dep if raw_dep else raw_sub
        else:
            final_inst = raw_inst
            final_sub = raw_sub
            
        snii_info = f"Nombre: {snii_name} | Institución: {final_inst} | Subdependencia: {final_sub}"
        
        print(f"   [{idx+1}/{len(df)}] Verificando: {snii_name}...")
        
        # Obtener embedding del autor SNII
        emb = get_embeddings([snii_info])[0]
        
        all_candidates = []
        is_unam = any(k in final_inst.lower() for k in ['unam', 'nacional autonoma de mexico', 'nacional autónoma de méxico'])

        # ── OpenAlex Authors (Prioridad Alta) ─────────────────────────────
        openalex_candidates = search_openalex_authors(snii_name, final_inst, limit=5)
        oa_scopus_map = {}  # openalex_id -> scopus_ids (para usar después si hay match)
        for c in openalex_candidates:
            oa_scopus_map[c['openalex_id']] = c.get('scopus_ids', [])
            all_candidates.append({
                "source": "OpenAlex DB Local",
                "openalex_id": c['openalex_id'],
                "name": c['name'],
                "orcid": c['orcid'],
                "affiliation": c['inst'],
                "scopus_ids": c.get('scopus_ids', []),
                "score_vec": c['score']
            })

        # Saltamos Qdrant si ya tenemos suficientes candidatos de calidad de OpenAlex
        high_quality_oa = [c for c in openalex_candidates if c['score'] >= 0.95]

        if is_unam and not high_quality_oa:
            # UNAM: Priorizar local via Qdrant (ahí está SIIA)
            local_candidates = local_store.search(emb, limit=5)
            orcid_candidates = orcid_store.search(emb, limit=2)
            for c in local_candidates:
                all_candidates.append({
                    "source": "Local (Neo4j/SIIA)",
                    "name": c.get("name"),
                    "orcid": c.get("orcid"),
                    "affiliation": c.get("affiliation"),
                    "score_vec": c.get("score")
                })
            for c in orcid_candidates:
                all_candidates.append({
                    "source": "ORCID Dump (Qdrant)",
                    "name": c.get("name"),
                    "orcid": c.get("orcid"),
                    "affiliation": c.get("affiliation"),
                    "score_vec": c.get("score")
                })
        elif not high_quality_oa:

            # Resto del país: ORCID Qdrant + ClickHouse SQL Directo
            orcid_candidates = orcid_store.search(emb, limit=5)
            for c in orcid_candidates:
                all_candidates.append({
                    "source": "ORCID Dump (Qdrant)",
                    "name": c.get("name"),
                    "orcid": c.get("orcid"),
                    "affiliation": c.get("affiliation"),
                    "score_vec": c.get("score")
                })
                
            # ClickHouse SQL Fuzzy Fallback
            try:
                ch_client = get_ch_client()
                parts = snii_name.replace(',', ' ').strip().split()
                if ',' in snii_name:
                    search_term = normalize_text(snii_name.split(',')[0].split()[0])
                elif not high_quality_oa:
                    search_term = parts[0]
                    common_names = ['juan', 'jose', 'maria', 'ana', 'luis', 'carlos', 'martha', 'rosa', 'pedro', 'jesus']
                    if search_term in common_names and len(parts) > 1:
                        search_term = parts[-1]
                        
                t_esc = search_term.strip().replace("'", "").lower().replace("'", "''")
                
                if len(t_esc) >= 3:
                    query = f"SELECT orcid, given_names, family_name, credit_name, last_affiliation FROM openalex.orcid_records WHERE (lower(family_name) LIKE '%{t_esc}%' OR lower(credit_name) LIKE '%{t_esc}%') LIMIT 20"
                    res = ch_client.query(query).result_rows
                    
                    from Levenshtein import jaro_winkler
                    sorted_seed = " ".join(sorted([t for t in normalize_text(snii_name).replace(',',' ').split() if len(t)>1]))
                    
                    scored_cands = []
                    for r in res:
                        fn, gn, cn, aff, orc = str(r[2] or ''), str(r[1] or ''), str(r[3] or ''), str(r[4] or ''), r[0]
                        sorted_ch = " ".join(sorted([t for t in normalize_text(f"{gn} {fn}").replace(',',' ').split() if len(t)>1]))
                        ns = jaro_winkler(sorted_seed, sorted_ch)
                        if cn:
                            ns = max(ns, jaro_winkler(sorted_seed, " ".join(sorted([t for t in normalize_text(cn).replace(',',' ').split() if len(t)>1]))))
                        if ns > 0.8:
                            scored_cands.append({"score": ns, "name": f"{gn} {fn}".strip() if not cn else cn, "orcid": orc, "aff": aff})
                    
                    scored_cands.sort(key=lambda x: x['score'], reverse=True)
                    for c in scored_cands[:4]:
                        if not any(a['orcid'] == c['orcid'] for a in all_candidates):
                            all_candidates.append({"source": "ClickHouse Text Search", "name": c['name'], "orcid": c['orcid'], "affiliation": c['aff'], "score_vec": c['score']})
            except Exception as e:
                print(f"      ⚠️ Error consultando ClickHouse text search: {e}")
            
        # Preparar Prompt para el LLM
        candidates_str = ""
        for i, cand in enumerate(all_candidates):
            candidates_str += f"{i+1}. [{cand['source']}] Nombre: {cand['name']} | ORCID: {cand['orcid']} | Afiliación: {cand['affiliation']}\n"
            
        prompt = f"""Eres un experto investigador bibliográfico. Tu tarea es identificar si alguno de los candidatos recuperados coincide exactamente con el investigador del SNII.

Investigador SNII buscado:
{snii_info}

Candidatos potenciales:
{candidates_str}

Instrucciones vitales:
1. Analiza el nombre (variaciones por apellidos compuestos, omisiones de nombre central, apodos, etc).
2. Analiza la afiliación desglosada en Nivel 1 (Institución) y Nivel 2 (Subdependencia).
3. ATENCIÓN: Si el investigador SNII indica 'Institución: SIN INSTITUCIÓN', DEBES IGNORAR por completo las afiliaciones de los candidatos y realizar el match 100% evaluando la compatibilidad de los nombres. ¡No penalices al candidato por tener una institución registrada en ORCID si al SNII le falta el dato!
4. Si crees que hay coincidencia segura, responde con el número del candidato y su ORCID.
5. Si ninguno coincide con seguridad, responde 'NINGUNO'.
6. Requisito de formato de salida estricto: JSON plano {"{"} "match": true/false, "candidate_index": int/null, "orcid": "...", "reason": "breve justificación" {"}"}. No agregues markdown de bloques de código.

Respuesta:"""

        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            res_text = response.content.strip()
            # Limpiar posibles bloques de código
            if "```json" in res_text:
                res_text = res_text.split("```json")[1].split("```")[0].strip()
            
            res_json = json.loads(res_text)
            
            result_entry = {
                "snii_author": snii_name,
                "snii_institution": final_inst,
                "snii_subdependency": final_sub,
                "match": False,
                "matched_author": None,
                "matched_orcid": None,
                "reason": res_json.get("reason", "No match"),
                "source": None
            }

            if res_json.get("match"):
                m_idx = res_json.get("candidate_index")
                if m_idx and 1 <= m_idx <= len(all_candidates):
                    final_match = all_candidates[m_idx-1]
                    confirmed_orcid = res_json.get("orcid") or final_match.get('orcid')
                    
                    # Extraer Scopus IDs: primero desde el candidato (de OpenAlex), luego desde ClickHouse ORCID
                    scopus_ids = final_match.get('scopus_ids') or []
                    if not scopus_ids and confirmed_orcid:
                        try:
                            ch = get_ch_client()
                            clean_orcid = str(confirmed_orcid).replace('https://orcid.org/', '').strip()
                            q = f"SELECT external_ids FROM openalex.authors WHERE orcid = '{clean_orcid}' LIMIT 1"
                            rows = ch.query(q).result_rows
                            if rows and rows[0][0]:
                                ext = json.loads(rows[0][0]) if isinstance(rows[0][0], str) else rows[0][0]
                                raw = ext.get('Scopus') or ext.get('scopus') or []
                                scopus_ids = [raw] if isinstance(raw, str) else raw
                        except Exception as se:
                            print(f"      ⚠️ No se pudieron extraer Scopus IDs: {se}")
                    
                    print(f"      ✅ MATCH CONFIRMADO por LLM: [SNII] {snii_name} ≈ [Match] {final_match['name']} ({confirmed_orcid})")
                    result_entry.update({
                        "match": True,
                        "matched_author": final_match['name'],
                        "matched_orcid": confirmed_orcid,
                        "matched_openalex_id": final_match.get('openalex_id'),
                        "scopus_ids": scopus_ids,
                        "source": final_match['source']
                    })
            else:
                print(f"      ❌ NINGUNO: No se encontró match para {snii_name}")
            
            verified_results.append(result_entry)

            # Guardado incremental cada 10 registros
            if (idx + 1) % 10 == 0:
                output_path = os.path.join("data", "snii_llm_verified_matches.json")
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(verified_results, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"      ⚠️ Error consultando LLM para {snii_name}: {e}")
            # Guardar el investigador como no procesado para no perderlo
            verified_results.append({
                "snii_author": snii_name,
                "snii_institution": final_inst,
                "snii_subdependency": final_sub,
                "match": False,
                "matched_author": None,
                "matched_orcid": None,
                "reason": f"Error en LLM: {e}",
                "source": None
            })
            # Guardado inmediato para no perder progreso ante interrupciones
            _output_path = os.path.join("data", "snii_llm_verified_matches.json")
            os.makedirs("data", exist_ok=True)
            with open(_output_path, "w", encoding="utf-8") as _f:
                json.dump(verified_results, _f, ensure_ascii=False, indent=2)

    # Guardar resultados específicos
    output_path = os.path.join("data", "snii_llm_verified_matches.json")
    os.makedirs("data", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(verified_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✨ Validación LLM completada. {len(verified_results)} matches guardados en {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, choices=[1, 2, 3, 4], help="Ejecutar solo un paso específico")
    parser.add_argument("--limit", type=int, help="Límite de registros para paso 4 (testing)")
    args = parser.parse_args()
    
    if not args.step or args.step == 1: vectorize_local_authors()
    if not args.step or args.step == 2: vectorize_orcid_authors()
    if not args.step or args.step == 3: vectorize_snii_authors()
    if args.step == 4: vectorize_snii_with_llm(limit_test=args.limit)
    
    print("\n✨ Triple vectorización completada.")
