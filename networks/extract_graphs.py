import os
import sys
import pandas as pd
from dotenv import load_dotenv

# Añadir path para importar desde la carpeta raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

# Cargar variables de entorno
load_dotenv()

OUTPUT_DIR = "data/networks"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def run_query(session, query, params=None):
    """Ejecuta una consulta Cypher y devuelve un DataFrame de Pandas."""
    result = session.run(query, params or {})
    records = [dict(record) for record in result]
    return pd.DataFrame(records)

def extract_coauthorship(session):
    print("🤖 Extrayendo Red de Coautoría...")
    
    # 1. Aristas de coautoría (Autor A, Autor B, número de papers)
    edges_query = """
    MATCH (p1:Person)-[:AUTHOR_OF]->(w:Paper)<-[:AUTHOR_OF]-(p2:Person)
    WHERE p1.id < p2.id
    RETURN p1.id AS source, p2.id AS target, count(w) AS weight
    """
    df_edges = run_query(session, edges_query)
    edges_path = os.path.join(OUTPUT_DIR, "coauthorship_edges.parquet")
    df_edges.to_parquet(edges_path, index=False)
    print(f"  -> Guardadas {len(df_edges)} aristas en {edges_path}")

    # 2. Metadatos de nodos (Autores) — solo personas con fullname definido
    nodes_query = """
    MATCH (p:Person)
    WHERE p.fullname IS NOT NULL AND trim(p.fullname) <> ''
    OPTIONAL MATCH (p)-[:AFFILIATED_TO]->(aff)
    OPTIONAL MATCH (aff)-[:PART_OF*0..2]->(inst:Institution)
    RETURN p.id AS id, 
           p.fullname AS fullname, 
           coalesce(p.is_snii, false) AS is_snii, 
           coalesce(p.snii_max_level, 'SIN NIVEL') AS snii_level, 
           coalesce(inst.name, aff.name, 'SIN AFILIACIÓN') AS institution
    """
    df_nodes = run_query(session, nodes_query)
    # Eliminar duplicados si un autor tiene múltiples afiliaciones (mantener una representativa)
    df_nodes = df_nodes.drop_duplicates(subset=["id"])
    nodes_path = os.path.join(OUTPUT_DIR, "coauthorship_nodes.parquet")
    df_nodes.to_parquet(nodes_path, index=False)
    print(f"  -> Guardados {len(df_nodes)} nodos de autores en {nodes_path}")



def extract_institutional(session):
    print("🤖 Extrayendo Red de Colaboración Institucional...")
    
    # 1. Aristas de colaboración institucional (Inst A, Inst B, número de coautorías)
    edges_query = """
    MATCH (p1:Person)-[:AUTHOR_OF]->(w:Paper)<-[:AUTHOR_OF]-(p2:Person)
    WHERE p1.id < p2.id
    MATCH (p1)-[:AFFILIATED_TO]->(aff1)
    OPTIONAL MATCH (aff1)-[:PART_OF*0..2]->(i1:Institution)
    WITH w, coalesce(i1.name, aff1.name) AS inst1, p2
    WHERE inst1 IS NOT NULL
    
    MATCH (p2)-[:AFFILIATED_TO]->(aff2)
    OPTIONAL MATCH (aff2)-[:PART_OF*0..2]->(i2:Institution)
    WITH w, inst1, coalesce(i2.name, aff2.name) AS inst2
    WHERE inst2 IS NOT NULL AND inst1 < inst2
    
    RETURN inst1 AS source, inst2 AS target, count(w) AS weight
    """
    df_edges = run_query(session, edges_query)
    edges_path = os.path.join(OUTPUT_DIR, "institutional_edges.parquet")
    df_edges.to_parquet(edges_path, index=False)
    print(f"  -> Guardadas {len(df_edges)} aristas institucionales en {edges_path}")

    # 2. Metadatos de nodos (Instituciones)
    # Extraemos todas las instituciones registradas
    nodes_query = """
    MATCH (i:Institution)
    RETURN i.name AS id, i.name AS name, coalesce(i.type, 'UNKNOWN') AS type, coalesce(i.country_code, 'MX') AS country_code
    """
    df_nodes = run_query(session, nodes_query)
    nodes_path = os.path.join(OUTPUT_DIR, "institutional_nodes.parquet")
    df_nodes.to_parquet(nodes_path, index=False)
    print(f"  -> Guardados {len(df_nodes)} nodos institucionales en {nodes_path}")


def extract_bipartite_topics(session):
    print("🤖 Extrayendo Red Bipartita Autor-Tópico...")
    
    # 1. Relaciones Autor - Tópico (OpenAlex Topic)
    topic_edges_query = """
    MATCH (p:Person)-[:AUTHOR_OF]->(w:Paper)-[:HAS_TOPIC]->(t:Topic)
    RETURN p.id AS source, t.id AS target, count(w) AS weight
    """
    df_topic_edges = run_query(session, topic_edges_query)
    topic_edges_path = os.path.join(OUTPUT_DIR, "topic_edges.parquet")
    df_topic_edges.to_parquet(topic_edges_path, index=False)
    print(f"  -> Guardadas {len(df_topic_edges)} aristas Autor-Tópico en {topic_edges_path}")

    # 2. Relaciones Autor - ODS (SDG)
    sdg_edges_query = """
    MATCH (p:Person)-[:AUTHOR_OF]->(w:Paper)-[:CONTRIBUTES_TO]->(s:SDG)
    RETURN p.id AS source, s.name AS target, count(w) AS weight
    """
    df_sdg_edges = run_query(session, sdg_edges_query)
    sdg_edges_path = os.path.join(OUTPUT_DIR, "sdg_edges.parquet")
    df_sdg_edges.to_parquet(sdg_edges_path, index=False)
    print(f"  -> Guardadas {len(df_sdg_edges)} aristas Autor-ODS en {sdg_edges_path}")

    # 3. Metadatos de nodos Tópicos
    topic_nodes_query = """
    MATCH (t:Topic)
    RETURN t.id AS id, t.name AS name, 'TOPIC' AS type
    """
    df_topic_nodes = run_query(session, topic_nodes_query)
    
    # 4. Metadatos de nodos ODS
    sdg_nodes_query = """
    MATCH (s:SDG)
    RETURN s.name AS id, s.name AS name, 'SDG' AS type
    """
    df_sdg_nodes = run_query(session, sdg_nodes_query)
    
    df_concept_nodes = pd.concat([df_topic_nodes, df_sdg_nodes], ignore_index=True)
    concepts_path = os.path.join(OUTPUT_DIR, "concept_nodes.parquet")
    df_concept_nodes.to_parquet(concepts_path, index=False)
    print(f"  -> Guardados {len(df_concept_nodes)} nodos de conceptos (Tópicos + ODS) en {concepts_path}")


def main():
    store = Neo4jGraphStore()
    try:
        with store.driver.session() as session:
            extract_coauthorship(session)
            print("-" * 50)
            extract_institutional(session)
            print("-" * 50)
            extract_bipartite_topics(session)
    finally:
        store.close()
    print("\n✅ Extracción completada exitosamente.")

if __name__ == "__main__":
    main()
