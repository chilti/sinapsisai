from database.knowledge_graph import Neo4jGraphStore
import json
import os

def inspect_entities():
    store = Neo4jGraphStore()
    entities = []
    
    with store.driver.session() as session:
        query = """
        MATCH (e:Entity)
        RETURN e.name as name, properties(e) as props
        """
        result = session.run(query)
        for record in result:
            entities.append({
                "name": record["name"],
                "props": record["props"]
            })
            
    store.close()
    print(json.dumps(entities, indent=2))

if __name__ == "__main__":
    inspect_entities()
