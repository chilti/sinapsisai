from database.knowledge_graph import Neo4jGraphStore
store = Neo4jGraphStore()
with store.driver.session() as session:
    query = """
    MATCH (i:Institution)
    OPTIONAL MATCH (i)<-[:PART_OF]-(dep:Dependency)
    OPTIONAL MATCH (dep)<-[:PART_OF]-(sub:Subdependency)
    RETURN i.name AS inst, dep.name AS dep, collect(DISTINCT sub.name) AS subs LIMIT 10
    """
    result = session.run(query)
    for record in result:
        print(record)
store.close()
