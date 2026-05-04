import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.knowledge_graph import Neo4jGraphStore
from dotenv import load_dotenv

load_dotenv()

def check_schema():
    db = Neo4jGraphStore()
    try:
        with db.driver.session() as session:
            print("--- Relaciones ---")
            res = session.run("CALL db.relationshipTypes()")
            for r in res:
                print(r[0])
            
            print("\n--- Labels ---")
            res = session.run("CALL db.labels()")
            for r in res:
                print(r[0])
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_schema()
