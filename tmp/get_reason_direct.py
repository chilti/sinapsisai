from neo4j import GraphDatabase
import json

def get_reason():
    uri = "bolt://127.0.0.1:7687"
    user = "neo4j"
    password = "password123"
    driver = GraphDatabase.driver(uri, auth=(user, password))
    
    query = """
    MATCH (a:Academic)
    WHERE a.name CONTAINS 'BURILLO AMEZCUA'
    RETURN a.name AS name, a.orcid AS orcid, a.audit_verdict AS verdict, a.audit_reason AS reason, a.audit_confidence AS confidence
    """
    try:
        with driver.session() as session:
            result = session.run(query)
            record = result.single()
            if record:
                print(json.dumps(dict(record), indent=2, ensure_ascii=False))
            else:
                print("No se encontró el registro.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.close()

if __name__ == "__main__":
    get_reason()
