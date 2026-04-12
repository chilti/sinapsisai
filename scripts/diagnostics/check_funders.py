import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from database.knowledge_graph import Neo4jGraphStore

def check_funders():
    store = Neo4jGraphStore()
    
    print("--- Estadísticas de Nodos ---")
    stats = store.get_database_statistics()
    nodes = stats.get('nodes', {})
    for label, count in nodes.items():
        print(f"  {label}: {count}")
        
    print("\n--- Buscando Funder nodes ---")
    query = """
    MATCH (f:Funder)
    RETURN count(f) as count
    """
    with store.driver.session() as session:
        result = session.run(query)
        count = result.single()["count"]
        print(f"Total Nodos Funder: {count}")

    print("\n--- Buscando relaciones Paper -> Funder ---")
    query_rel = """
    MATCH (p:Paper)-[r:FUNDED_BY]->(f:Funder)
    RETURN count(r) as count
    """
    with store.driver.session() as session:
        result = session.run(query_rel)
        count_rel = result.single()["count"]
        print(f"Total Relaciones FUNDED_BY: {count_rel}")

    print("\n--- Muestra de red de Funder ---")
    entity_name = "Facultad de Ciencias"
    print(f"Ejecutando get_funder_sample_graph para '{entity_name}'...")
    sample = store.get_funder_sample_graph(entity_name, limit=15)
    
    if "error" in sample:
        print(f"Error en get_funder_sample_graph: {sample['error']}")
    else:
        print(f"Nodes retornados: {len(sample.get('nodes', []))}")
        print(f"Edges retornadas: {len(sample.get('edges', []))}")
        for n in sample.get('nodes', []):
            if n['label'] in ('Funder', 'Award'):
                print(f"  Encontrado {n['label']}: {n['title']}")

    store.close()

if __name__ == '__main__':
    check_funders()
