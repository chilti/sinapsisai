import os
import sys

# Ajustar el sys.path para poder importar el módulo de base de datos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.clickhouse_db import ch_client

query = """
SELECT institution, institution_ror, entity, entity_id, count() as count
FROM paper_author_map
WHERE institution ILIKE '%banco de mexico%' OR institution_ror ILIKE '%banco de mexico%'
GROUP BY institution, institution_ror, entity, entity_id
ORDER BY count DESC
"""

try:
    df = ch_client.query_df(query)
    print("=== PAPER AUTHOR MAP ===")
    print(df)
except Exception as e:
    print("Error querying ClickHouse:", e)

from database.knowledge_graph import Neo4jGraphStore
store = Neo4jGraphStore()

query_neo = """
MATCH (a:Academic)-[:AFFILIATED_TO]->(n)
WHERE n.name =~ '(?i).*banco de mexico.*' OR n.id =~ '(?i).*banco de mexico.*'
RETURN labels(n) as label, n.name as name, n.id as id, count(a) as academics
"""

try:
    with store.driver.session() as session:
        res = session.run(query_neo)
        print("\n=== NEO4J AFFILIATIONS TO BANCO DE MEXICO ===")
        for r in res:
            print(dict(r))
            
    query_neo_entities = """
    MATCH (i:Institution)<-[:PART_OF]-(e:Entity)
    WHERE i.name =~ '(?i).*banco de mexico.*'
    RETURN i.name as inst, e.name as dep, e.id as dep_id
    """
    with store.driver.session() as session:
        res = session.run(query_neo_entities)
        print("\n=== NEO4J ENTITIES OF BANCO DE MEXICO ===")
        for r in res:
            print(dict(r))
except Exception as e:
    print("Error querying Neo4j:", e)

