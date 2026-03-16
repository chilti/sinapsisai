from database.knowledge_graph import Neo4jGraphStore
import json

def check_hierarchy():
    store = Neo4jGraphStore()
    schema = {}
    
    with store.driver.session() as session:
        # Check node labels
        labels = session.run("CALL db.labels()").value()
        schema['labels'] = labels
        
        # Check relationships
        rels = session.run("CALL db.relationshipTypes()").value()
        schema['relationships'] = rels
        
        # Try to find relationships between Entity and Institution
        query = """
        MATCH (e:Entity)-[r]->(i:Institution)
        RETURN type(r) as rel_type, count(*) as count
        """
        result = session.run(query)
        schema['entity_to_institution'] = [dict(record) for record in result]
        
        # Try to find any hierarchy in Entity
        query = """
        MATCH (e1:Entity)-[r]->(e2:Entity)
        RETURN type(r) as rel_type, count(*) as count
        """
        result = session.run(query)
        schema['entity_hierarchy'] = [dict(record) for record in result]

        # Get top institutions
        query = """
        MATCH (i:Institution)
        RETURN i.name as name, count(*) as count LIMIT 10
        """
        # result = session.run(query) # This might be too slow if many institutions
        # schema['institutions_sample'] = [record['name'] for record in result]
        
        # Count Entities
        schema['entity_count'] = session.run("MATCH (e:Entity) RETURN count(e) as c").single()['c']
        
    store.close()
    print(json.dumps(schema, indent=2))

if __name__ == "__main__":
    check_hierarchy()
