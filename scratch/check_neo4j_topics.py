import sys
import os
sys.path.append(os.getcwd())
from database.knowledge_graph import Neo4jGraphStore
import json

gs = Neo4jGraphStore()
with gs.driver.session() as session:
    res = session.run("MATCH (p:Paper) WHERE p.raw_metadata IS NOT NULL RETURN p.raw_metadata LIMIT 5")
    for r in res:
        meta = json.loads(r['p.raw_metadata'])
        print(f"DOI: {meta.get('doi')}")
        print(f"Primary Topic: {meta.get('primary_topic_name')}")
        print(f"OpenAlex_Topics: {len(meta.get('OpenAlex_Topics', []))} topics")
        print("-" * 20)
gs.close()
