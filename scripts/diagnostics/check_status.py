import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from database.knowledge_graph import Neo4jGraphStore
import json

graph = Neo4jGraphStore()
q = """
MATCH (e:Entity {name: 'Mexico'})-[:HAS_PAPER]->(p:Paper)
RETURN p.raw_metadata AS meta
"""

with graph.driver.session() as session:
    res = list(session.run(q))
    
    total = len(res)
    enriched = 0
    valid_json = 0
    
    for r in res:
        raw = r['meta']
        if not raw: continue
        try:
            meta = json.loads(raw)
            valid_json += 1
            if 'coauthor_institutions' in meta:
                enriched += 1
        except:
            pass

    print(f"Total papers: {total}")
    print(f"Valid JSON in meta: {valid_json}")
    print(f"Enriched (OpenAlex): {enriched}")

graph.close()
