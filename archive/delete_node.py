import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
from database.knowledge_graph import Neo4jGraphStore

def delete_node():
    graph_store = Neo4jGraphStore()
    try:
        with graph_store.driver.session() as session:
            # We use elementId or id to match and delete. 
            # The user provided id: '9967' and fullname: 'MIRAMONTES VIDAL, PEDRO EDUARDO'
            result = session.run("MATCH (a:Person {id: '9967'}) DETACH DELETE a RETURN count(a) as deleted")
            record = result.single()
            print(f"Nodes deleted: {record['deleted']}")
    finally:
        graph_store.close()

if __name__ == "__main__":
    delete_node()
