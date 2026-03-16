from database.knowledge_graph import Neo4jGraphStore
import os

def quick_check():
    store = Neo4jGraphStore()
    with store.driver.session() as session:
        # Get all Entity names and their labels
        result = session.run("MATCH (e:Entity) RETURN e.name as name, labels(e) as labels")
        for record in result:
            print(f"Entity: {record['name']}, Labels: {record['labels']}")
            
        # Check for Institution nodes
        result = session.run("MATCH (i:Institution) RETURN i.name as name LIMIT 5")
        print("\nInstitutions:")
        for record in result:
            print(f"- {record['name']}")
    store.close()

if __name__ == "__main__":
    quick_check()
