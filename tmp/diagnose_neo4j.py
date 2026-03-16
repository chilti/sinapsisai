
from neo4j import GraphDatabase
import os
import sys

# Añadir path raíz para importar configuración
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

def run_count():
    graph = Neo4jGraphStore()
    
    query = """
    MATCH (e:Entity {name: 'Mexico'})-[:HAS_PAPER]->(p:Paper)<-[:AUTHORED]-(a:Author)
    WHERE a.orcid IS NOT NULL
    RETURN count(DISTINCT a) AS total_authors
    """
    
    print(f"--- Ejecutando Conteo Específico ---")
    with graph.driver.session() as session:
        result = session.run(query)
        record = result.single()
        count = record["total_authors"] if record else 0
        print(f"Resultado de la query (DISTINCT a): {count:,}")

    graph.close()

if __name__ == "__main__":
    run_count()
