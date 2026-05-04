import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.knowledge_graph import Neo4jGraphStore
gs = Neo4jGraphStore()

_HIER_QUERY = """
MATCH (i:Institution)<-[:PART_OF]-(dep:Entity)
OPTIONAL MATCH (dep)<-[:PART_OF]-(sub:Entity)
WHERE i.name =~ '(?i).*banco de mexico.*'
RETURN 
    i.name AS inst, i.ror AS inst_ror, i.id AS inst_id,
    dep.name AS dep, dep.id AS dep_id,
    sub.name AS sub, sub.id AS sub_id
"""

print("=== NEO4J QUERY RESULTS ===")
hier = {}
with gs.driver.session() as session:
    for r in session.run(_HIER_QUERY):
        print(dict(r))
        inst = r["inst"]
        inst_id = r["inst_id"]
        ror  = r["inst_ror"] or inst_id
        dep  = r["dep"]
        dep_id = r["dep_id"]
        sub  = r["sub"]
        sub_id = r["sub_id"]
        
        if not inst: continue
        if inst not in hier: 
            hier[inst] = {'ror': ror, 'id': inst_id, 'entities': {}}
        
        if dep:
            if dep not in hier[inst]['entities']:
                hier[inst]['entities'][dep] = {'id': dep_id, 'subs': {}}
            if sub:
                hier[inst]['entities'][dep]['subs'][sub] = sub_id

print("\n=== HIERARCHY BUILT ===")
import json
print(json.dumps(hier, indent=2))
