from database.knowledge_graph import Neo4jGraphStore
import json

def check_inst():
    store = Neo4jGraphStore()
    results = {}
    with store.driver.session() as session:
        # Count institutions
        results['inst_count'] = session.run("MATCH (i:Institution) RETURN count(i) as c").single()['c']
        
        # Get sample institutions
        res = session.run("MATCH (i:Institution) RETURN i.name as name LIMIT 10")
        results['institutions'] = [r['name'] for r in res]
        
        # Check affiliation of academics to entities AND institutions
        query = """
        MATCH (a:Academic)
        OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity)
        OPTIONAL MATCH (a)-[:AFFILIATED_WITH]->(i:Institution)
        RETURN a.name as academic, e.name as entity, i.name as institution
        LIMIT 20
        """
        res = session.run(query)
        results['academic_affiliations'] = [dict(r) for r in res]
        
    store.close()
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    check_inst()
