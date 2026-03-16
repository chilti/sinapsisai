import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.knowledge_graph import Neo4jGraphStore
import json

def get_reason():
    # Usar las credenciales por defecto del init de Neo4jGraphStore o pasar si son distintas
    try:
        graph = Neo4jGraphStore()
        query = """
        MATCH (a:Academic)
        WHERE a.name CONTAINS 'BURILLO AMEZCUA'
        RETURN a.name AS name, a.orcid AS orcid, a.audit_verdict AS verdict, a.audit_reason AS reason, a.audit_confidence AS confidence
        """
        with graph.driver.session() as session:
            result = session.run(query)
            record = result.single()
            if record:
                print(json.dumps(dict(record), indent=2, ensure_ascii=False))
            else:
                print("No se encontró el registro con CONTAINS.")
        graph.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_reason()
