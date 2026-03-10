from database.knowledge_graph import Neo4jGraphStore
import json

graph = Neo4jGraphStore()
q = """
MATCH (e:Entity {name: 'Mexico'})-[:HAS_PAPER]->(p:Paper)
RETURN 
    count(p) as total, 
    count(p.doi) as with_doi,
    sum(case when p.raw_metadata IS NOT NULL then 1 else 0 end) as with_raw_meta
"""

with graph.driver.session() as session:
    res = session.run(q).single()
    print(f"Total papers (Mexico): {res['total']}")
    print(f"With DOI: {res['with_doi']}")
    print(f"With raw_metadata: {res['with_raw_meta']}")

    # Ver si ya tienen campos OA
    q2 = """
    MATCH (e:Entity {name: 'Mexico'})-[:HAS_PAPER]->(p:Paper)
    RETURN p.raw_metadata LIMIT 5
    """
    rows = session.run(q2)
    for r in rows:
        meta = json.loads(r['p.raw_metadata']) if r['p.raw_metadata'] else {}
        print(f"- Keys in meta: {list(meta.keys())[:10]}")

graph.close()
