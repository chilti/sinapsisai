from database.knowledge_graph import Neo4jGraphStore
graph = Neo4jGraphStore()
q = "MATCH (e:Entity {name: 'Mexico'})-[:HAS_PAPER]->(p:Paper) RETURN p.doi LIMIT 20"
with graph.driver.session() as session:
    results = session.run(q)
    dois = [r['p.doi'] for r in results]
    print(dois)
graph.close()
