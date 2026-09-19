from database.knowledge_graph import Neo4jGraphStore

neo = Neo4jGraphStore()
with neo.driver.session() as session:
    res = session.run("""
    MATCH (a:Person {fullname: 'JIMENEZ ANDRADE, JOSE LUIS'})-[:AFFILIATED_TO]->(node)
    OPTIONAL MATCH (node)-[:PART_OF*0..2]->(parent)
    RETURN labels(node) as node_labels, node.name as node_name, labels(parent) as parent_labels, parent.name as parent_name
    """)
    for r in res:
        print(r)
neo.close()
