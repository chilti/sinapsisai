"""Verifica el nodo de PARDO CEMO, ANNIE en Neo4j"""
import sys; sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()
from database.knowledge_graph import Neo4jGraphStore

gs = Neo4jGraphStore()
with gs.driver.session() as s:
    result = s.run("""
        MATCH (a:Academic {name: 'PARDO CEMO, ANNIE'})
        OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity)
        OPTIONAL MATCH (e)-[:PART_OF]->(inst:Institution)
        RETURN a.id, a.name, a.orcid, a.is_snii,
               collect(DISTINCT e.name) AS entities,
               collect(DISTINCT inst.name) AS institutions
    """)
    for r in result:
        print("ID:", r['a.id'])
        print("ORCID:", r['a.orcid'])
        print("Entidades:", r['entities'])
        print("Instituciones:", r['institutions'])

    # Ver cuantos papers tiene
    result2 = s.run("""
        MATCH (a:Academic {name: 'PARDO CEMO, ANNIE'})-[:AUTHORED]->(p:Paper)
        RETURN count(p) AS n_papers, collect(p.id)[..5] AS sample_ids
    """)
    for r in result2:
        print("Papers en Neo4j:", r['n_papers'])
        print("Muestra IDs:", r['sample_ids'])
