from neo4j import GraphDatabase
import json

def investigate_neo4j():
    uri = "bolt://127.0.0.1:7687"
    driver = GraphDatabase.driver(uri, auth=("neo4j", "password123"))
    
    with driver.session() as session:
        # 1. Contar cuántos papers tienen el label :IndexedOpenAlex
        count_res = session.run("MATCH (p:IndexedOpenAlex) RETURN count(p) as count")
        print(f"Total papers con label :IndexedOpenAlex: {count_res.single()['count']}")
        
        # 2. Buscar papers que podrían estar duplicados o mal vinculados
        # Un paper "erróneo" probablemente está vinculado a muchas instituciones si el script falló en bucle
        query = """
        MATCH (p:IndexedOpenAlex)-[:AFFILIATED_TO]->(e:Entity)
        WITH p, count(e) as inst_count
        WHERE inst_count > 5
        RETURN p.doi as doi, p.title as title, inst_count
        LIMIT 10
        """
        duplicates = session.run(query)
        print("\nEjemplos de papers vinculados a muchas instituciones (>5):")
        for rec in duplicates:
            print(f"- {rec['doi']} | ({rec['inst_count']} insts) | {rec['title'][:50]}")

        # 3. Verificar metadatos de un caso sospechoso
        # Ver si el ROR de la institución coincide con lo que dice el paper en su metadata real
        query = """
        MATCH (p:IndexedOpenAlex)-[:AFFILIATED_TO]->(e:Entity)
        WHERE e.ror IS NOT NULL
        RETURN p.doi as doi, p.raw_metadata as meta, e.name as inst_name, e.ror as inst_ror
        LIMIT 5
        """
        verification = session.run(query)
        print("\nVerificación de metadatos vs relaciones:")
        for rec in verification:
            meta = json.loads(rec['meta']) if isinstance(rec['meta'], str) else rec['meta']
            # Extraer RORs reales del paper desde el JSON de OpenAlex
            real_rors = []
            for auth in meta.get('authorships', []):
                for inst in auth.get('institutions', []):
                    if inst.get('ror'): real_rors.append(inst['ror'])
            
            match = rec['inst_ror'] in real_rors
            print(f"Paper {rec['doi']} -> Inst '{rec['inst_name']}' (ROR {rec['inst_ror']})")
            print(f"   RORs reales en el paper: {real_rors}")
            print(f"   ¿Coincide?: {'✅ SI' if match else '❌ NO (¡ERROR DE VINCULACIÓN!)'}")

    driver.close()

if __name__ == "__main__":
    investigate_neo4j()
