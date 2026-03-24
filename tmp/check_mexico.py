import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore
import json

g = Neo4jGraphStore()
with g.driver.session() as session:
    res = session.run("MATCH (n:Entity {name: 'Mexico'}) RETURN labels(n) as labels, n as node")
    record = res.single()
    if record:
        print(f"Labels for 'Mexico': {record['labels']}")
        # print(f"Properties: {record['node']}")
    else:
        print("'Mexico' node NOT found by name 'Mexico'")
        # Try finding by label Institution
        res = session.run("MATCH (n:Institution) WHERE n.name CONTAINS 'MEXICO' RETURN n.name as name LIMIT 5")
        print(f"Similar Institutions: {[r['name'] for r in res]}")

g.close()
