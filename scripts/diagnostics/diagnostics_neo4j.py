import os
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import json
from database.knowledge_graph import Neo4jGraphStore

def run_diagnostics():
    graph = Neo4jGraphStore()
    
    # 1. Total papers
    q1 = "MATCH (p:Paper) RETURN count(p) as n"
    # 2. Papers with DOI
    q2 = "MATCH (p:Paper) WHERE p.doi IS NOT NULL AND p.doi <> '' RETURN count(p) as n"
    # 3. Papers with raw_metadata
    q3 = "MATCH (p:Paper) WHERE p.raw_metadata IS NOT NULL RETURN count(p) as n"
    # 4. Papers linked to 'Mexico'
    q4 = "MATCH (e:Entity {name: 'Mexico'})-[:HAS_PAPER]->(p:Paper) RETURN count(p) as n"
    # 5. Papers linked to 'Mexico' WITH DOI
    q5 = "MATCH (e:Entity {name: 'Mexico'})-[:HAS_PAPER]->(p:Paper) WHERE p.doi IS NOT NULL AND p.doi <> '' RETURN count(p) as n"
    # 6. Sample raw_metadata from a 'Mexico' paper
    q6 = "MATCH (e:Entity {name: 'Mexico'})-[:HAS_PAPER]->(p:Paper) WHERE p.raw_metadata IS NOT NULL RETURN p.id as id, p.doi as doi, p.raw_metadata as meta LIMIT 1"

    with graph.driver.session() as session:
        print(f"Total Papers: {session.run(q1).single()['n']}")
        print(f"Papers with DOI: {session.run(q2).single()['n']}")
        print(f"Papers with raw_metadata: {session.run(q3).single()['n']}")
        print(f"Papers linked to 'Mexico': {session.run(q4).single()['n']}")
        print(f"Papers linked to 'Mexico' with DOI: {session.run(q5).single()['n']}")
        
        sample = session.run(q6).single()
        if sample:
            print(f"Sample ID: {sample['id']}")
            print(f"Sample DOI: {sample['doi']}")
            print(f"Sample Meta: {sample['meta'][:200]}")
        else:
            print("No papers with raw_metadata found for 'Mexico'")

    graph.close()

if __name__ == "__main__":
    run_diagnostics()
