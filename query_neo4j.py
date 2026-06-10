from database.knowledge_graph import Neo4jGraphStore
neo = Neo4jGraphStore()

def get_academic_affiliation_hierarchy(academic_name):
    query = """
    MATCH (a:Person)
    WHERE a.fullname = $name OR a.id = $name
    MATCH (a)-[:AFFILIATED_TO]->(bottom_node)
    
    // Obtener la jerarquía hacia arriba usando paths
    OPTIONAL MATCH path = (bottom_node)-[:PART_OF*0..2]->(top_node:Institution)
    
    RETURN 
        labels(bottom_node) as bottom_labels, bottom_node.name as bottom_name,
        nodes(path) as path_nodes
    LIMIT 1
    """
    with neo.driver.session() as session:
        result = session.run(query, name=academic_name)
        record = result.single()
        
        if record:
            path_nodes = record["path_nodes"]
            inst = None
            dep = None
            sub = None
            
            if path_nodes:
                for node in path_nodes:
                    labels = list(node.labels)
                    if "Institution" in labels:
                        inst = node.get("name")
                    elif "Dependency" in labels:
                        dep = node.get("name")
                    elif "Subdependency" in labels:
                        sub = node.get("name")
            else:
                # Fallback if no path (e.g. only affiliated to institution directly)
                labels = record["bottom_labels"]
                if "Institution" in labels:
                    inst = record["bottom_name"]
                elif "Dependency" in labels:
                    dep = record["bottom_name"]
                elif "Subdependency" in labels:
                    sub = record["bottom_name"]
            
            return {"institution": inst, "dependency": dep, "subdependency": sub}
    return None

print(get_academic_affiliation_hierarchy("JIMENEZ ANDRADE, JOSE LUIS"))
neo.close()
