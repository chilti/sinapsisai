import os
import sys
import time
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path

# Agregar el directorio raíz al path para que Python encuentre 'database'
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))

# Database clients
from database.knowledge_graph import Neo4jGraphStore
from database.vector_store import QdrantStore
from database.clickhouse_db import ClickHouseClient

load_dotenv()

OUTPUT_DIR = "data/maps"

def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def extract_people_vectors_neo4j():
    """
    Ejecuta FastRP (si es necesario) y exporta los vectores de Person/Academic desde Neo4j.
    """
    output_path = os.path.join(OUTPUT_DIR, "people_vectors.parquet")
    if '--force' not in sys.argv and os.path.exists(output_path):
        print(f"  -> {output_path} ya existe. Saltando extracción...")
        return
        
    print("🧠 [Neo4j] Extrayendo vectores de Personas (FastRP)...")
    store = Neo4jGraphStore()
    
    try:
        # 1. Asegurar que FastRP exista en el grafo actual.
        # En Neo4j 7687 usaremos GDS para calcular 'embedding_fastrp' si no existe.
        with store.driver.session() as session:
            # Revisar si hay embeddings FastRP en Person
            res = session.run("MATCH (p:Person) WHERE p.embedding_fastrp IS NOT NULL RETURN count(p) as count").single()
            if res["count"] == 0:
                print("  -> No se encontraron embeddings FastRP en Person. Calculando (GDS)...")
                try:
                    session.run("CALL gds.graph.drop('person_paper_graph', false)")
                    session.run("""
                        CALL gds.graph.project(
                            'person_paper_graph',
                            ['Person', 'Institution', 'Paper'],
                            {
                                AUTHOR_OF: {orientation: 'UNDIRECTED'},
                                AFFILIATED_TO: {orientation: 'UNDIRECTED'}
                            }
                        )
                    """)
                    session.run("""
                        CALL gds.fastRP.write(
                          'person_paper_graph',
                          {
                            embeddingDimension: 128,
                            writeProperty: 'embedding_fastrp'
                          }
                        )
                    """)
                    print("  -> FastRP calculado exitosamente.")
                except Exception as e:
                    print(f"  -> ⚠️ Error calculando FastRP (¿GDS instalado?): {e}")
            else:
                print(f"  -> Encontrados {res['count']} nodos Person con FastRP pre-calculado.")

            # 2. Extraer datos
            print("  -> Exportando a pandas...")
            query = """
            MATCH (p:Person)
            WHERE p.embedding_fastrp IS NOT NULL
            OPTIONAL MATCH (p)-[:AFFILIATED_TO]->(dep:Dependency)-[:PART_OF]->(inst:Institution)
            RETURN p.id AS person_id, 
                   p.fullname AS fullname, 
                   p.is_snii AS is_snii, 
                   coalesce(p.snii_level, '') AS snii_level,
                   coalesce(inst.name, 'Sin Institución') AS institution,
                   p.embedding_fastrp AS embedding
            """
            records = list(session.run(query))
            if not records:
                print("  -> ⚠️ No se extrajeron registros de Personas.")
                return

            df = pd.DataFrame([r.data() for r in records])
            
            output_path = os.path.join(OUTPUT_DIR, "people_vectors.parquet")
            df.to_parquet(output_path, index=False)
            print(f"✅ [Neo4j] Guardado {len(df)} vectores en {output_path}")

    finally:
        store.close()

def extract_people_topics_vectors_neo4j():
    """
    Ejecuta FastRP y exporta los vectores de Person considerando Topics y SDGs.
    """
    output_path = os.path.join(OUTPUT_DIR, "people_topics_vectors.parquet")
    if '--force' not in sys.argv and os.path.exists(output_path):
        print(f"  -> {output_path} ya existe. Saltando extracción...")
        return

    print("🧠 [Neo4j] Extrayendo vectores de Personas (FastRP con Temas y ODS)...")
    store = Neo4jGraphStore()
    
    try:
        with store.driver.session() as session:
            # Revisar si hay embeddings FastRP Topics en Person
            res = session.run("MATCH (p:Person) WHERE p.embedding_fastrp_topics IS NOT NULL RETURN count(p) as count").single()
            if res["count"] == 0:
                print("  -> No se encontraron embeddings FastRP-Topics en Person. Calculando (GDS)...")
                try:
                    session.run("CALL gds.graph.drop('person_paper_topics_graph', false)")
                    session.run("""
                        CALL gds.graph.project(
                            'person_paper_topics_graph',
                            ['Person', 'Institution', 'Paper', 'IndexedOpenAlex', 'Topic', 'SDG'],
                            {
                                AUTHOR_OF: {orientation: 'UNDIRECTED'},
                                AFFILIATED_TO: {orientation: 'UNDIRECTED'},
                                HAS_TOPIC: {orientation: 'UNDIRECTED'},
                                CONTRIBUTES_TO: {orientation: 'UNDIRECTED'}
                            }
                        )
                    """)
                    session.run("""
                        CALL gds.fastRP.write(
                          'person_paper_topics_graph',
                          {
                            embeddingDimension: 128,
                            writeProperty: 'embedding_fastrp_topics'
                          }
                        )
                    """)
                    print("  -> FastRP-Topics calculado exitosamente.")
                except Exception as e:
                    print(f"  -> ⚠️ Error calculando FastRP-Topics (¿GDS instalado?): {e}")
            else:
                print(f"  -> Encontrados {res['count']} nodos Person con FastRP-Topics pre-calculado.")

            # Extraer datos
            print("  -> Exportando a pandas...")
            query = """
            MATCH (p:Person)
            WHERE p.embedding_fastrp_topics IS NOT NULL
            OPTIONAL MATCH (p)-[:AFFILIATED_TO]->(dep:Dependency)-[:PART_OF]->(inst:Institution)
            RETURN p.id AS person_id, 
                   p.fullname AS fullname, 
                   p.is_snii AS is_snii, 
                   coalesce(p.snii_level, '') AS snii_level,
                   coalesce(inst.name, 'Sin Institución') AS institution,
                   p.embedding_fastrp_topics AS embedding
            """
            records = list(session.run(query))
            if not records:
                print("  -> ⚠️ No se extrajeron registros de Personas (Topics/SDGs).")
                return

            df = pd.DataFrame([r.data() for r in records])
            
            output_path = os.path.join(OUTPUT_DIR, "people_topics_vectors.parquet")
            df.to_parquet(output_path, index=False)
            print(f"✅ [Neo4j] Guardado {len(df)} vectores en {output_path}")

    finally:
        store.close()

def extract_articles_vectors_qdrant():
    """
    Extrae los embeddings de artículos desde Qdrant.
    """
    output_path = os.path.join(OUTPUT_DIR, "articles_vectors.parquet")
    if '--force' not in sys.argv and os.path.exists(output_path):
        print(f"  -> {output_path} ya existe. Saltando extracción...")
        return

    print("📚 [Qdrant] Extrayendo vectores de Artículos...")
    store = QdrantStore()
    if not store.available:
        print("  -> ⚠️ Qdrant no disponible.")
        return

    client = store.client
    collection = store.collection_name
    
    try:
        count = client.count(collection_name=collection).count
        print(f"  -> Se estiman {count} vectores en Qdrant.")
    except Exception as e:
        print(f"  -> ⚠️ Error contando en Qdrant: {e}")
        return

    records = []
    offset = None
    
    try:
        # Re-instanciar el cliente nativo de qdrant para forzar un timeout largo
        from qdrant_client import QdrantClient
        long_client = QdrantClient(host=store.host, port=store.port, timeout=60.0)
        
        while True:
            results, offset = long_client.scroll(
                collection_name=collection,
                limit=1000, # Lote más pequeño para no saturar memoria/red
                offset=offset,
                with_payload=True,
                with_vectors=True
            )
            for point in results:
                payload = point.payload or {}
                # Manejar qdrant-client >= 1.7 vector
                vector = point.vector
                if isinstance(vector, dict): 
                    # Podría ser vector nombrado
                    vector = list(vector.values())[0]

                records.append({
                    "id": point.id,
                    "doi": payload.get("doi", ""),
                    "title": payload.get("title", ""),
                    "year": payload.get("year", 0),
                    "institution": payload.get("entity", "Desconocida"),
                    "embedding": vector
                })
            
            print(f"  -> {len(records)}/{count} procesados...", end="\r")
            if offset is None:
                break

        print()
        if not records:
            print("  -> ⚠️ No se encontraron registros en Qdrant.")
            return

        df = pd.DataFrame(records)
        output_path = os.path.join(OUTPUT_DIR, "articles_vectors.parquet")
        df.to_parquet(output_path, index=False)
        print(f"✅ [Qdrant] Guardado {len(df)} vectores en {output_path}")

    except Exception as e:
        print(f"  -> ⚠️ Error durante la extracción de Qdrant: {e}")


def extract_performance_vectors_clickhouse():
    """
    Extrae el vector de métricas de desempeño aprovechando los parquets
    ya generados por ingestion/compute_scholar_metrics_ch.py
    """
    output_path = os.path.join(OUTPUT_DIR, "performance_vectors.parquet")
    if '--force' not in sys.argv and os.path.exists(output_path):
        print(f"  -> {output_path} ya existe. Saltando extracción...")
        return

    print("📊 [Métricas] Construyendo vectores de Desempeño desde caché...")
    
    from pathlib import Path
    cache_dir = Path("data/cache_ch")
    inv_files = list(cache_dir.glob("**/investigador_total.parquet"))
    
    if not inv_files:
        print("  -> ⚠️ No se encontraron archivos de investigadores en caché. Ejecuta compute_scholar_metrics_ch.py primero.")
        return
        
    dfs = []
    for f in inv_files:
        try:
            dfs.append(pd.read_parquet(f))
        except Exception:
            pass
            
    if not dfs:
        return
        
    df = pd.concat(dfs, ignore_index=True).drop_duplicates(subset=['academic_name'])
    
    # Asegurar y filtrar académicos que no tengan artículos
    if 'num_documents' not in df.columns:
        df['num_documents'] = df.get('neo4j_total_papers', 0)
    df['num_documents'] = df['num_documents'].fillna(0).astype(int)
    df = df[df['num_documents'] > 0]
    
    # Asegurar que existan las métricas
    for c in ['pct_top_10', 'fwci_avg', 'pct_1', 'percentile_avg']:
        if c not in df.columns:
            df[c] = 0.0
            
    df.fillna({'pct_top_10': 0, 'fwci_avg': 0, 'pct_1': 0, 'percentile_avg': 0}, inplace=True)
    
    df['embedding'] = df.apply(lambda row: [
        float(row['pct_top_10']), 
        float(row['fwci_avg']), 
        float(row['pct_1']), 
        float(row['percentile_avg'])
    ], axis=1)

    out_df = pd.DataFrame({
        'person_id': df['academic_name'],
        'fullname': df['academic_name'],
        'institution': df.get('institutions', 'Desconocida'),
        'dependency': df.get('entities', 'Desconocida'),
        'country': 'MX',
        'pct_top_10': df['pct_top_10'].round(2),
        'fwci_avg': df['fwci_avg'].round(2),
        'pct_1': df['pct_1'].round(2),
        'percentile_avg': df['percentile_avg'].round(2),
        'num_documents': df['num_documents'],
        'embedding': df['embedding']
    })

    output_path = os.path.join(OUTPUT_DIR, "performance_vectors.parquet")
    out_df.to_parquet(output_path, index=False)
    print(f"✅ [Métricas] Guardado {len(out_df)} vectores en {output_path}")


def extract_articles_nomic_clickhouse():
    """
    Extrae los embeddings Nomic de artículos directamente desde ClickHouse.
    """
    output_path = os.path.join(OUTPUT_DIR, "articles_nomic_vectors.parquet")
    if '--force' not in sys.argv and os.path.exists(output_path):
        print(f"  -> {output_path} ya existe. Saltando extracción...")
        return

    print("📚 [ClickHouse] Extrayendo vectores de Artículos (Nomic)...")
    from database.clickhouse_db import ch_client
    try:
        df = ch_client.query_df("""
            SELECT 
                id, 
                doi, 
                title, 
                publication_year as year,
                if(empty(institution_names), 'Desconocida', institution_names[1]) as institution,
                embedding_nomic as embedding
            FROM works_academic_all
            WHERE length(embedding_nomic) > 0
        """)
        ensure_output_dir()
        output_path = os.path.join(OUTPUT_DIR, "articles_nomic_vectors.parquet")
        df.to_parquet(output_path, index=False)
        print(f"✅ [ClickHouse] Guardado {len(df)} vectores en {output_path}")
    except Exception as e:
        print(f"⚠️ Error al extraer artículos Nomic desde ClickHouse: {e}")


def extract_articles_specter_clickhouse():
    """
    Extrae los embeddings SPECTER2 de artículos directamente desde ClickHouse.
    """
    output_path = os.path.join(OUTPUT_DIR, "articles_specter_vectors.parquet")
    if '--force' not in sys.argv and os.path.exists(output_path):
        print(f"  -> {output_path} ya existe. Saltando extracción...")
        return

    print("📚 [ClickHouse] Extrayendo vectores de Artículos (SPECTER2)...")
    from database.clickhouse_db import ch_client
    try:
        df = ch_client.query_df("""
            SELECT 
                id, 
                doi, 
                title, 
                publication_year as year,
                if(empty(institution_names), 'Desconocida', institution_names[1]) as institution,
                embedding_specter as embedding
            FROM works_academic_all
            WHERE length(embedding_specter) > 0
        """)
        ensure_output_dir()
        output_path = os.path.join(OUTPUT_DIR, "articles_specter_vectors.parquet")
        df.to_parquet(output_path, index=False)
        print(f"✅ [ClickHouse] Guardado {len(df)} vectores en {output_path}")
    except Exception as e:
        print(f"⚠️ Error al extraer artículos SPECTER2 desde ClickHouse: {e}")


def extract_people_semantic_clickhouse():
    """
    Extrae los perfiles semánticos SPECTER2 de los académicos desde ClickHouse.
    """
    output_path = os.path.join(OUTPUT_DIR, "people_semantic_vectors.parquet")
    if '--force' not in sys.argv and os.path.exists(output_path):
        print(f"  -> {output_path} ya existe. Saltando extracción...")
        return

    print("🧠 [ClickHouse] Extrayendo vectores de Académicos (Semántica SPECTER2)...")
    from database.clickhouse_db import ch_client
    try:
        df = ch_client.query_df("""
            SELECT 
                a.id AS person_id,
                any(pm.academic_name) AS fullname,
                any(pm.is_snii) AS is_snii,
                a.snii_level AS snii_level,
                any(pm.institution) AS institution,
                any(pm.dependency) AS dependency,
                a.embedding_specter AS embedding
            FROM academics_all AS a
            JOIN paper_author_map AS pm ON a.id = pm.openalex_id
            WHERE length(a.embedding_specter) > 0 AND pm.openalex_id != ''
            GROUP BY a.id, a.snii_level, a.embedding_specter
        """)
        if df.empty:
            print("  -> ⚠️ No se encontraron académicos con perfiles semánticos en ClickHouse (0 registros).")
            return

        df['fullname'] = df['fullname'].fillna(df['person_id'])
        df['institution'] = df['institution'].fillna('Sin Institución')
        df['is_snii'] = df['is_snii'].fillna(0).astype(int)
        df['snii_level'] = df['snii_level'].fillna('')
        
        ensure_output_dir()
        output_path = os.path.join(OUTPUT_DIR, "people_semantic_vectors.parquet")
        df.to_parquet(output_path, index=False)
        print(f"✅ [ClickHouse] Guardado {len(df)} vectores en {output_path}")
    except Exception as e:
        print(f"⚠️ Error al extraer académicos SPECTER2 desde ClickHouse: {e}")


if __name__ == "__main__":
    start_time = time.time()
    ensure_output_dir()
    
    print("=== Iniciando Extracción de Vectores ===")
    extract_people_vectors_neo4j()
    extract_people_topics_vectors_neo4j()
    extract_articles_vectors_qdrant()
    extract_performance_vectors_clickhouse()
    
    # Nuevos mapas
    extract_articles_nomic_clickhouse()
    extract_articles_specter_clickhouse()
    extract_people_semantic_clickhouse()
    
    print(f"=== Extracción completada en {time.time() - start_time:.1f} segundos ===")

