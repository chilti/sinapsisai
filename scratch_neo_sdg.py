from database.knowledge_graph import Neo4jGraphStore
import os

# Override Neo4j URI to use the port the user mentioned
os.environ["NEO4J_URI_MEXICO"] = "bolt://localhost:7687"

gs = Neo4jGraphStore()
with gs.driver.session() as session:
    res = session.run("MATCH (p:Paper)-[:RELATES_TO]->(s:SDG) RETURN count(p) as num_papers, s.id as sdg LIMIT 5")
    for r in res:
        print(r)
