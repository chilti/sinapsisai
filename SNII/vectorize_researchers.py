"""
vectorize_researchers.py
────────────────────────
Implementa la estrategia de triple vectorización semántica en Qdrant:
1. Autores locales (Neo4j Mexico) -> coleccion 'local_authors'
2. Autores SNII 2025 (Excel) -> coleccion 'snii_authors_vec'
3. Autores ORCID (ClickHouse) -> coleccion 'orcid_authors_vec'
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
from match_snii_orcid import normalize_text, get_client as get_ch_client

# Cargar .env
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

# --- Config Embeddings (Copia de ingest_apis.py para consistencia) ---
MEX_KEYWORDS = [
    "mexico", "mexic", "unam", "ipn", "cinvestav", "tecnologico", "autonoma", "itamb", "colmex", 
    "buap", "uaslp", "udem", "itesm", "uam", "politecnico",
    "guadalajara", "monterrey", "puebla", "queretaro", "yucatan", "chiapas", "veracruz", 
    "jalisco", "michoacan", "hidalgo", "zacatecas", "tabasco", "sinaloa", "sonora"
]

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
        embs = embeddings_model.embed_documents(batch)
        all_embeddings.extend(embs)
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
        text = f"{d['name']} ({main_aff})"
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

def vectorize_snii_authors():
    """Paso 2: SNII Excel -> Qdrant 'snii_authors_vec' 
       Mencionado: Busca coincidencias en tiempo real contra local_authors y orcid_authors_vec.
    """
    print("\n🚀 Paso 2: Vectorizando autores SNII 2025 y buscando coincidencias semánticas...")
    from match_snii_orcid import SNII_PATH
    
    df = pd.read_excel(SNII_PATH)
    q_store = QdrantStore(collection_name="snii_authors_vec")
    
    # Stores para búsqueda
    local_store = QdrantStore(collection_name="local_authors")
    orcid_store = QdrantStore(collection_name="orcid_authors_vec")
    
    name_col = 'NOMBRE DEL INVESTIGADOR'
    inst_col = 'INSTITUCIÓN DE ACREDITACIÓN'
    sub_inst_col = 'SUBDEPENDENCIA DE ACREDITACIÓN'
    
    docs = []
    for _, row in df.iterrows():
        name = str(row[name_col])
        inst = str(row[inst_col]) if pd.notna(row[inst_col]) else ""
        sub = str(row[sub_inst_col]) if pd.notna(row[sub_inst_col]) else ""
        
        text = f"{name} {inst} {sub}".strip()
        docs.append({
            "text": text,
            "title": name,
            "name": name,
            "institution": inst,
            "subdependency": sub,
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

def vectorize_orcid_authors():
    """Paso 3: ORCID ClickHouse -> Qdrant 'orcid_authors_vec'"""
    print("\n🚀 Paso 3: Vectorizando autores ORCID (ClickHouse)...")
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
    sub_inst_col = 'SUBDEPENDENCIA DE ACREDITACIÓN'
    
    verified_results = []
    
    for idx, row in df.iterrows():
        snii_name = str(row[name_col])
        sub_inst = str(row[sub_inst_col]) if pd.notna(row[sub_inst_col]) else ""
        snii_info = f"Nombre: {snii_name} | Institución: {row[inst_col]} | Subdependencia: {sub_inst}"
        
        print(f"   [{idx+1}/{len(df)}] Verificando: {snii_name}...")
        
        # Obtener embedding del autor SNII
        emb = get_embeddings([snii_info])[0]
        
        # Recuperar candidatos
        local_candidates = local_store.search(emb, limit=5)
        orcid_candidates = orcid_store.search(emb, limit=5)
        
        all_candidates = []
        for c in local_candidates:
            all_candidates.append({
                "source": "Local (Neo4j)",
                "name": c.get("name"),
                "orcid": c.get("orcid"),
                "affiliation": c.get("affiliation"),
                "score_vec": c.get("score")
            })
        for c in orcid_candidates:
            all_candidates.append({
                "source": "ORCID Dump",
                "name": c.get("name"),
                "orcid": c.get("orcid"),
                "affiliation": c.get("affiliation"),
                "score_vec": c.get("score")
            })
            
        # Preparar Prompt para el LLM
        candidates_str = ""
        for i, cand in enumerate(all_candidates):
            candidates_str += f"{i+1}. [{cand['source']}] Nombre: {cand['name']} | ORCID: {cand['orcid']} | Afiliación: {cand['affiliation']}\n"
            
        prompt = f"""Eres un experto investigador bibliográfico. Tu tarea es identificar si alguno de los candidatos recuperados por una búsqueda semántica coincide exactamente con el investigador del SNII.

Investigador SNII buscado:
{snii_info}

Candidatos potenciales:
{candidates_str}

Instrucciones:
1. Compara cuidadosamente el nombre (considera variaciones como 'Juan Perez' vs 'Perez, Juan') y la institución.
2. Si crees que hay una coincidencia clara, responde con el número del candidato y el ORCID.
3. Si ninguno coincide con seguridad, responde 'NINGUNO'.
4. Formato de respuesta: JSON plano con las llaves: "match" (bool), "candidate_index" (int o null), "orcid" (str o null), "reason" (str breve).

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
                "snii_institution": row[inst_col],
                "snii_subdependency": sub_inst,
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
                    print(f"      ✅ MATCH CONFIRMADO por LLM: [SNII] {snii_name} ≈ [Match] {final_match['name']} ({final_match['orcid']})")
                    result_entry.update({
                        "match": True,
                        "matched_author": final_match['name'],
                        "matched_orcid": final_match['orcid'],
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
    if not args.step or args.step == 2: vectorize_snii_authors()
    if not args.step or args.step == 3: vectorize_orcid_authors()
    if args.step == 4: vectorize_snii_with_llm(limit_test=args.limit)
    
    print("\n✨ Triple vectorización completada.")
