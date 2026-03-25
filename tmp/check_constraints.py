import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore
g = Neo4jGraphStore()
with g.driver.session() as session:
    res = session.run("SHOW CONSTRAINTS")
    for r in res:
        print(f"Name: {r['name']}, Type: {r['type']}, Entity: {r['entityType']}, Labels: {r['labelsOrTypes']}, Props: {r['properties']}")
g.close()
