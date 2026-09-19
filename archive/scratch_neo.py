import os
from neo4j import GraphDatabase

uri = "bolt://localhost:7688"
user = "neo4j"
password = "password123"

driver = GraphDatabase.driver(uri, auth=(user, password))

query = """
MATCH (i:Institution {name: 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)'})<-[:PART_OF*..3]-(e:Entity)
RETURN e.name as entity, labels(e) as lbl, [(e)-[:PART_OF]->(parent) | parent.name][0] as parent
LIMIT 15
"""

with driver.session() as session:
    res = session.run(query)
    for r in res:
        print(r)

driver.close()
