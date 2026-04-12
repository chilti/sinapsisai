import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from database.knowledge_graph import Neo4jGraphStore

def run_migration():
    print("Starting Neo4j Schema Multi-Label Migration...")
    load_dotenv()
    neo4j = Neo4jGraphStore()

    queries = [
        "MATCH (n:APIPaper) SET n:Paper REMOVE n:APIPaper;",
        "MATCH (a:Academic) SET a:Author;",
        "MATCH (e:Entity) SET e:Institution;"
    ]

    with neo4j.driver.session() as session:
        for q in queries:
            print(f"Executing: {q}")
            try:
                res = session.run(q)
                counters = res.consume().counters
                print(f"  --> Labels Added: {counters.labels_added}, Labels Removed: {counters.labels_removed}")
            except Exception as e:
                print(f"Error during migration: {e}")

    print("Migration completed successfully!")
    neo4j.close()

if __name__ == "__main__":
    run_migration()
