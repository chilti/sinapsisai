"""
sync_neo4j_embeddings.py
Sincroniza los artículos existentes en Neo4j con Qdrant.
Lee todos los papers en Neo4j, verifica si existen en Qdrant y, de no existir,
genera sus embeddings usando el modelo local (LM Studio / LangChain) y los guarda.
"""

import sys
import os
import json
import time
import argparse
import ast
import httpx
from dotenv import load_dotenv

# Configuración de rutas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'SNII')))

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

from SNII.match_snii_orcid import NEO4J_URI, NEO4J_USER, NEO4J_PASS
from database.knowledge_graph import Neo4jGraphStore
from database.vector_store import QdrantStore
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

def _parse_raw_meta(raw_meta_json):
    if isinstance(raw_meta_json, dict): return raw_meta_json
    if not raw_meta_json: return {}
    try:
        return json.loads(raw_meta_json)
    except:
        try: return ast.literal_eval(raw_meta_json)
        except: return {}

def sync_embeddings(limit=None, chunk_size=5000, batch_size=32):
    graph_store = Neo4jGraphStore(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASS)
    vector_store = QdrantStore(collection_name="api_papers")

    # Contar total de trabajos a procesar
    with graph_store.driver.session() as session:
        total_papers = session.run("MATCH (p:Paper) RETURN count(p) AS total").single()['total']

    if limit: total_papers = min(total_papers, limit)
    print(f"🚀 Iniciando sincronización de embeddings para {total_papers} papers...")

    processed = 0
    updated = 0
    skipped = 0
    errors = 0

    for skip in range(0, total_papers, chunk_size):
        remaining_in_chunk = min(chunk_size, total_papers - skip)
        print(f"\n📦 Procesando chunk {skip} a {skip + remaining_in_chunk}...")
        
        chunk_papers = []
        with graph_store.driver.session() as session:
            # Traer papers de manera paginada
            query = """
            MATCH (p:Paper)
            RETURN p.doi AS doi, p.title AS title, p.year AS year, p.raw_metadata AS meta
            SKIP $skip LIMIT $limit
            """
            result = session.run(query, skip=skip, limit=remaining_in_chunk)
            for row in result:
                chunk_papers.append(row)

        # Procesar lote en memoria
        for i in range(0, len(chunk_papers), batch_size):
            batch = chunk_papers[i:i+batch_size]
            
            payloads_qdrant = []
            texts_para_vectorizar = []
            
            for p in batch:
                doi = str(p['doi'] or "").replace("https://doi.org/", "").strip()
                title = p['title'] or ""
                
                if not doi and not title:
                    skipped += 1
                    continue
                    
                # 1. Verificar si ya existe en Qdrant
                qdrant_exists = False
                if hasattr(vector_store, 'check_document_exists'):
                    qdrant_exists = vector_store.check_document_exists(doi=doi, title=title)
                    
                if qdrant_exists:
                    skipped += 1
                    continue
                
                # 2. Preparar texto a vectorizar
                meta = _parse_raw_meta(p['meta'])
                text_for_embedding = f"Title: {title}\n"
                
                abstract = meta.get('Abstract') or meta.get('Abstract_oa')
                if abstract:
                    text_for_embedding += f"Abstract: {abstract}"
                    
                year = p['year'] or meta.get('Year') or meta.get('publication_year') or 0
                source_str = meta.get("Source", "Sync Script")
                
                payload = {
                    "academic_name": "Synchronized Paper",
                    "doi":           doi,
                    "title":         title,
                    "year":          year,
                    "source":        source_str,
                    "entity":        "SYNC",
                    "text":          text_for_embedding
                }
                
                texts_para_vectorizar.append(text_for_embedding)
                payloads_qdrant.append(payload)

            if not payloads_qdrant:
                processed += len(batch)
                continue

            try:
                # Truncar textos demasiado largos (ej. > 8000 caracteres ~= 1500 tokens)
                # para evitar que el modelo exceda su ventana de contexto y el servidor aborte la conexión
                clean_batch = [str(t)[:8000] if t else " " for t in texts_para_vectorizar]
                embs = embeddings_model.embed_documents(clean_batch)
                
                # Guardar en Qdrant
                vector_store.add_documents(payloads_qdrant, embs)
                updated += len(payloads_qdrant)
                
            except Exception as e:
                # Fallback: Si el lote entero falla (ej. Connection reset by peer), intentamos de uno en uno
                print(f"\n  ⚠️ Lote falló ({e}). Reintentando uno por uno para aislar el problemático...")
                for t, p in zip(texts_para_vectorizar, payloads_qdrant):
                    try:
                        single_t = str(t)[:8000] if t else " "
                        single_emb = embeddings_model.embed_documents([single_t])
                        vector_store.add_documents([p], single_emb)
                        updated += 1
                        print("    ✅ Recuperado 1", end="\r")
                    except Exception as e_single:
                        print(f"\n    ❌ Texto descartado completamente: {e_single}")
                        errors += 1

            processed += len(batch)
            print(f"  📊 {processed}/{total_papers} | Vectorizados: {updated} | Ya en Qdrant/Skipped: {skipped} | Err: {errors}", end="\r")

    print(f"\n\n✨ Sincronización Finalizada. {updated} nuevos en Qdrant, {skipped} omitidos (ya existían / inválidos), {errors} errores.")
    graph_store.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sincroniza papers en Neo4j con los vectores de Qdrant.")
    parser.add_argument("--limit", type=int, default=None, help="Límite máximo de documentos a procesar (para testing).")
    parser.add_argument("--chunk", type=int, default=5000, help="Tamaño de chunk al consultar Neo4j.")
    parser.add_argument("--batch", type=int, default=32, help="Tamaño de lote para el Embedder (ej. 32 para evitar VRAM/RAM OOM).")
    args = parser.parse_args()

    sync_embeddings(limit=args.limit, chunk_size=args.chunk, batch_size=args.batch)
