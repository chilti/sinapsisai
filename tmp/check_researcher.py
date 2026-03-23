
from neo4j import GraphDatabase
import os

uri = 'bolt://127.0.0.1:7687'
user = 'neo4j'
password = 'password123'

driver = GraphDatabase.driver(uri, auth=(user, password))
try:
    with driver.session() as session:
        print("Searching for ALFARO MONTUFAR...")
        query = "MATCH (a:Academic) WHERE a.name CONTAINS 'ALFARO' AND a.name CONTAINS 'CARLOS' RETURN a.name, a.orcid, a.audit_verdict, a.is_snii"
        res = session.run(query)
        found = False
        for r in res:
            found = True
            name = r['a.name']
            print(f"  Found: {name}")
            print(f"    ORCID: {r['a.orcid']}")
            print(f"    Audit: {r['a.audit_verdict']}")
            print(f"    is_snii: {r['a.is_snii']}")
            
            # Count papers
            res2 = session.run("MATCH (a:Academic {name: $name})-[:AUTHORED]->(p:Paper) RETURN count(p) as count", name=name)
            print(f"    Papers linked: {res2.single()['count']}")
            
            # Check affiliations
            res3 = session.run("MATCH (a:Academic {name: $name})-[:AFFILIATED_TO]->(e:Entity) RETURN e.name as entity", name=name)
            entities = [rec['entity'] for rec in res3]
            print(f"    Affiliations: {entities}")

        if not found:
            print("  No researchers found matching the query.")
            # Check if any Academic exists at all
            res_any = session.run("MATCH (a:Academic) RETURN count(a) as count")
            print(f"Total Academic nodes in DB: {res_any.single()['count']}")
finally:
    driver.close()
