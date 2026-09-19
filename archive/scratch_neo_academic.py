import os
from neo4j import GraphDatabase

uri = "bolt://localhost:7688"
user = "neo4j"
password = "password123"

driver = GraphDatabase.driver(uri, auth=(user, password))

query = """
MATCH (a:Academic)-[:AFFILIATED_TO]->(e:Entity {name: 'SECRETARIA GENERAL'})-[:PART_OF]->(i:Institution {name: 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)'})
RETURN a.name, a.institution, a.dependencia, a.subdependencia, a.affiliation, keys(a)
LIMIT 5
"""

with driver.session() as session:
    res = session.run(query)
    for r in res:
        print(r)

driver.close()
