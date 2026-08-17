"""
sync_works.py
Sincroniza periódicamente los artículos desde las APIs (Scopus, ORCID, OpenAlex) 
tomando como punto de partida los nodos existentes en Neo4j:
- Nodos Person (Académicos)
- Nodos Institucionales (Institution, Dependency, Subdependency) que cuenten con un ROR validado.
"""

import sys
import os
import json
import time
import requests
import pyalex
import httpx
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client
from ingestion import openalex_utils
from lib.llm_utils import get_embeddings_model

# Configuración de APIs
try:
    import pybliometrics
    from pybliometrics.scopus import AuthorRetrieval
    pybliometrics.scopus.init()
except Exception:
    print("Nota: pybliometrics puede no estar completamente configurado.")

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

pyalex.config.email = os.getenv("EMAIL_ADDRESS", "sin_correo@ciencias.unam.mx")
if os.getenv("OPENALEX_API_KEY"):
    pyalex.config.api_key = os.getenv("OPENALEX_API_KEY")

embeddings_model = get_embeddings_model()
vector_store = QdrantStore(collection_name="api_papers")
graph_store = Neo4jGraphStore()

def get_embeddings(texts: list, batch_size: int = 32, force_local: bool = False) -> list:
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
                val = emb.embedding if hasattr(emb, "embedding") else emb.tolist() if hasattr(emb, "tolist") else list(emb)
                all_embeddings.append(val)
            return all_embeddings
        except Exception as e:
            print(f"⚠️ Error con lmstudio: {e}. Cayendo a LangChain...")

    for i in range(0, len(texts), batch_size):
        batch = [str(t) if t else " " for t in texts[i:i+batch_size]]
        embs = embeddings_model.embed_documents(batch)
        all_embeddings.extend(embs)
    return all_embeddings

def deconstruct_abstract(inverted_abstract):
    if not inverted_abstract: return None
    try:
        abstract_len = max(pos for val in inverted_abstract.values() for pos in val) + 1
        abstract_list = [""] * abstract_len
        for word, positions in inverted_abstract.items():
            for pos in positions: abstract_list[pos] = word
        return " ".join(filter(None, abstract_list))
    except:
        return None

# ----- LÓGICA PARA ACADÉMICOS -----
# Reutilizamos las funciones de ingest_snii_apis.py
from SNII.ingest_snii_apis import obtener_metadatos_de_scopus, obtener_metadatos_de_orcid, obtener_scopus_ids_de_orcid, obtener_metadatos_de_openalex_autor

def sync_academics(limit=None, target_name=None, force_local=False, save_to_ch=False, resolve_oa=True, skip=0):
    query = """
    MATCH (p:Person)
    """
    if target_name:
        query += " WHERE toLower(p.fullname) CONTAINS toLower($name) "
    query += """
    RETURN p.id as id, p.fullname as fullname, p.orcids as orcids, p.scopus_ids as scopus_ids, p.openalex_ids as openalex_ids, p.is_snii as is_snii
    """
    if limit:
        query += f" LIMIT {limit}"

    with graph_store.driver.session() as session:
        result = session.run(query, name=target_name)
        academics = [dict(record) for record in result]

    print(f"📊 Encontrados {len(academics)} académicos desde Neo4j...")
    if skip > 0:
        print(f"⏭️  Saltando los primeros {skip} registros...")
        academics = academics[skip:]
    
    # Importamos la lógica principal adaptada para diccionario individual de SNII/ingest_snii_apis
    from SNII.ingest_snii_apis import ingest_researcher_data
    
    count = skip
    total_to_process = skip + len(academics)
    for acad in academics:
        count += 1
        # Convertir al formato que espera ingest_researcher_data
        data = {
            'snii_author': acad['fullname'],
            'snii_cvu': acad['id'] if acad['id'] and acad['id'].isdigit() else None,
            'orcid': acad['orcids'][0] if acad['orcids'] else None,
            'scopus_ids': acad['scopus_ids'],
            'openalex_ids': acad['openalex_ids'],
            'match': True,
            # No sobreescribir la afiliación existente
            'already_in_db': False 
        }
        
        print(f"\n[{count}/{total_to_process}] Procesando a {acad['fullname']}")
        # Llamar a la lógica probada (se salta si no hay IDs válidos)
        ingest_researcher_data(data, force=True, force_local=force_local, current_idx=count, total=total_to_process, save_to_ch=save_to_ch, resolve_oa=resolve_oa)

# ----- LÓGICA PARA ENTIDADES (Instituciones, Dependencias) -----
def get_entities_with_ror(target_name=None, limit=None):
    query = """
    MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.ror IS NOT NULL
    """
    if target_name:
        query += " AND toLower(e.name) CONTAINS toLower($name) "
        
    query += """
    OPTIONAL MATCH (inst:Institution)<-[:PART_OF]-(e:Dependency)
    OPTIONAL MATCH (inst2:Institution)<-[:PART_OF]-(dep:Dependency)<-[:PART_OF]-(e:Subdependency)
    RETURN labels(e)[0] as type, e.ror as ror, e.name as name, 
           coalesce(inst.name, inst2.name, e.name) as inst_name,
           coalesce(dep.name, CASE WHEN e:Dependency THEN e.name ELSE "SIN INFORMACIÓN" END) as dep_name,
           CASE WHEN e:Subdependency THEN e.name ELSE "SIN INFORMACIÓN" END as sub_name
    """
    if limit:
        query += f" LIMIT {limit}"

    with graph_store.driver.session() as session:
        result = session.run(query, name=target_name)
        return [dict(r) for r in result]

def sync_entities(limit=None, target_name=None, force_local=False, save_to_ch=False, skip=0):
    entities = get_entities_with_ror(target_name, limit)
    print(f"📊 Sincronizando {len(entities)} entidades con ROR desde Neo4j...")
    
    if skip > 0:
        print(f"⏭️  Saltando las primeras {skip} entidades...")
        entities = entities[skip:]
        
    # Importamos herramientas del pipeline ROR para no duplicar código
    from ROR.ingest_ror_docs import RORIngestor
    from ROR.ingest_ror_docs2 import RORIngestorV2
    
    ingestor = RORIngestorV2()
    ingestor.save_to_ch = save_to_ch
    
    count = skip
    total_to_process = skip + len(entities)
    for ent in entities:
        count += 1
        print(f"\n🏛️ [{count}/{total_to_process}] Procesando Entidad: {ent['name']} (Tipo: {ent['type']}, ROR: {ent['ror']})")
        print(f"   Jerarquía: {ent['inst_name']} || {ent['dep_name']} || {ent['sub_name']}")
        
        # Obtener OpenAlex ID del ROR
        oa_id = ingestor._ror_to_openalex_id(ent['ror'])
        if not oa_id:
            # Fallback a la API de OpenAlex para obtener el ID
            try:
                # El ROR en Neo4j a menudo viene sin la url completa, ej 'https://ror.org/01tmp8f25'
                ror_str = ent['ror'] if ent['ror'].startswith('https://ror.org/') else f"https://ror.org/{ent['ror']}"
                r = requests.get(f"https://api.openalex.org/institutions/{ror_str}", timeout=10)
                if r.status_code == 200:
                    oa_id = r.json().get('id')
            except Exception as e:
                print(f"   ⚠️ Fallo recuperando OA ID para ROR {ent['ror']}: {e}")
                
        if not oa_id:
            print(f"   ❌ No se pudo determinar el OpenAlex ID para ROR {ent['ror']}. Saltando.")
            continue
            
        unit_data = {
            'inst': ent['inst_name'],
            'dep': ent['dep_name'],
            'sub': ent['sub_name'],
            'id': oa_id
        }
        
        # Ingestar usando la lógica de RORIngestorV2 (Deduplica, enlaza y vectoriza)
        ingestor._ingest_unit(unit_data, local_only=force_local)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sincronizador periódico desde Neo4j (Academics y Entities con ROR)")
    parser.add_argument("--sync-academics", action="store_true", help="Sincronizar artículos de Nodos Person")
    parser.add_argument("--sync-entities", action="store_true", help="Sincronizar artículos de Nodos Institucionales con ROR")
    parser.add_argument("--all", action="store_true", help="Sincronizar TODO (Academics y Entities)")
    parser.add_argument("--limit", type=int, help="Límite de registros a procesar por categoría")
    parser.add_argument("--skip", type=int, default=0, help="Saltar los primeros N registros (para reanudar)")
    parser.add_argument("--name", type=str, help="Filtrar por nombre (Académico o Entidad)")
    parser.add_argument("--local", action="store_true", help="Usar API local de OpenAlex y SDK nativa de LM Studio")
    parser.add_argument("--ch", action="store_true", help="Guardar mapeos secundarios en ClickHouse")
    parser.add_argument("--no-resolve-oa", action="store_true", help="No intentar resolver activamente los IDs de OpenAlex si no existen")
    parser.add_argument("--recompute-metrics", action="store_true", help="Recalcular automáticamente métricas y parquets al finalizar la ingesta")
    
    args = parser.parse_args()
    
    if not (args.sync_academics or args.sync_entities or args.all):
        parser.error("Debes especificar qué sincronizar: --sync-academics, --sync-entities, o --all")
        
    try:
        if args.sync_academics or args.all:
            print("\n" + "="*50)
            print("🚀 INICIANDO SINCRONIZACIÓN DE ACADÉMICOS")
            print("="*50)
            sync_academics(limit=args.limit, target_name=args.name, force_local=args.local, save_to_ch=args.ch, resolve_oa=not args.no_resolve_oa, skip=args.skip)
            
        if args.sync_entities or args.all:
            print("\n" + "="*50)
            print("🚀 INICIANDO SINCRONIZACIÓN DE ENTIDADES (ROR)")
            print("="*50)
            sync_entities(limit=args.limit, target_name=args.name, force_local=args.local, save_to_ch=args.ch, skip=args.skip)

        if args.recompute_metrics:
            print("\n" + "="*50)
            print("📊 RECALCULANDO MÉTRICAS Y PARQUETS DE CACHÉ DE ACADÉMICOS E INSTITUCIONES")
            print("="*50)
            import subprocess
            cmd = [sys.executable, "ingestion/compute_scholar_metrics_ch.py"]
            if args.name:
                cmd.extend(["--academic", args.name])
            subprocess.run(cmd, cwd=os.path.dirname(os.path.dirname(__file__)))
            
    except KeyboardInterrupt:
        print("\n🛑 Proceso interrumpido por el usuario.")
    finally:
        graph_store.close()
        print("\n🎉 Proceso de Sincronización completado.")
