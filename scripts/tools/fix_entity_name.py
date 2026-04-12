import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import sys
import os
sys.path.append(os.path.abspath('.'))
from database.knowledge_graph import Neo4jGraphStore
import json

store = Neo4jGraphStore()
with store.driver.session() as session:
    print('Migrating relationships and deleting duplicate Entity...')
    
    # Merge academics
    session.run("""
    MATCH (bad:Entity {name: 'Instituto de Investigaciones Nucleares'})
    MATCH (good:Entity {name: 'Instituto de Ciencias Nucleares'})
    MATCH (a:Academic)-[r:AFFILIATED_TO]->(bad)
    MERGE (a)-[:AFFILIATED_TO]->(good)
    DELETE r
    """)
    
    # Merge papers if any
    session.run("""
    MATCH (bad:Entity {name: 'Instituto de Investigaciones Nucleares'})
    MATCH (good:Entity {name: 'Instituto de Ciencias Nucleares'})
    MATCH (bad)-[r:HAS_PAPER]->(p)
    MERGE (good)-[:HAS_PAPER]->(p)
    DELETE r
    """)
    
    # Delete bad node
    session.run("""
    MATCH (bad:Entity {name: 'Instituto de Investigaciones Nucleares'})
    DELETE bad
    """)
    
    res = session.run("MATCH (e:Entity) RETURN e.name AS name, count(e) as c")
    print('Entities in Neo4j AFTER:')
    for r in res: 
        print(f" - {r['name']}: {r['c']}")

store.close()

# 2. Update the JSON file
json_path = 'ingestion/profesores_Instituto_de_Ciencias_Nucleares.json'
if os.path.exists(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    changed = False
    for k, v in data.items():
        if v.get('entity') == 'Instituto de Investigaciones Nucleares':
            v['entity'] = 'Instituto de Ciencias Nucleares'
            changed = True
    if changed:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print("Updated JSON file references to 'Instituto de Ciencias Nucleares'")
