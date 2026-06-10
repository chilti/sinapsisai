from neo4j import GraphDatabase
uri = 'neo4j://localhost:7687'
driver = GraphDatabase.driver(uri, auth=('neo4j', 'password'))
query = '''
MATCH (i:Institution {name: 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)'})
MATCH (d:Dependency {name: 'SECRETARIA GENERAL'})-[:PART_OF]->(i)
MATCH (s:Subdependency {name: 'FACULTAD DE CIENCIAS'})-[:PART_OF]->(d)
MATCH (p:Person)-[:AFFILIATED_TO]->(s)
WITH toLower(trim(replace(p.fullname, ',', ''))) AS nameNorm, collect(DISTINCT p) AS persons
WHERE size(persons) > 1
RETURN nameNorm, size(persons) as dups, persons
'''
with driver.session() as session:
    result = session.run(query)
    for record in result:
        print(record['nameNorm'])
        for node in record['persons']:
            print("  ", dict(node.items()))
