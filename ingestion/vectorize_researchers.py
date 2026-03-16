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
from langchain_openai import OpenAIEmbeddings

# Añadir path raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from SNII.match_snii_orcid import normalize_text, get_client as get_ch_client

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
    from SNII.match_snii_orcid import SNII_PATH
    
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
                if local_hits and local_hits[0]['score'] > 0.92:
                    hit = local_hits[0]
                    print(f"      [Match Local] {snii_name} ≈ {hit['name']} (ORCID: {hit.get('orcid')}) | Score: {hit['score']:.4f}")
                    batch_docs[idx]["match_local_orcid"] = hit.get('orcid')
                    batch_docs[idx]["match_local_score"] = hit['score']
                
                # 2. Buscar en ORCID
                orcid_hits = orcid_store.search(emb, limit=1)
                if orcid_hits and orcid_hits[0]['score'] > 0.92:
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

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, choices=[1, 2, 3], help="Ejecutar solo un paso específico")
    args = parser.parse_args()
    
    if not args.step or args.step == 1: vectorize_local_authors()
    if not args.step or args.step == 2: vectorize_snii_authors()
    if not args.step or args.step == 3: vectorize_orcid_authors()
    
    print("\n✨ Triple vectorización completada.")
