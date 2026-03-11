import sys
import os
sys.path.append(os.path.abspath('.'))

from database.knowledge_graph import Neo4jGraphStore

db = Neo4jGraphStore()
with db.driver.session() as session:
    academic_name = "U'REN CORTES, ALFRED BARRY"
    
    query = """
    MATCH (a:Academic {name: $name})-[r:AUTHORED]->(p:Paper)
    WITH p, r, [(p)<-[:AUTHORED]-(other) | other] AS auths
    WHERE size(auths) = 1
    DETACH DELETE p
    RETURN count(p) as deleted
    """
    res = session.run(query, name=academic_name)
    print("Orphaned deleted:", res.single()['deleted'])

    query = """
    MATCH (a:Academic {name: $name})-[r:AUTHORED]->(p:Paper)
    DELETE r
    RETURN count(r) as deleted
    """
    res = session.run(query, name=academic_name)
    print("Rels deleted:", res.single()['deleted'])

db.close()
