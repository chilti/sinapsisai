from database.knowledge_graph import Neo4jGraphStore

def validate_collaboration():
    store = Neo4jGraphStore()
    with store.driver.session() as session:
        # 1. Verificar Entidades
        res_e = session.run("MATCH (e:Entity) RETURN e.name")
        entities = [r['e.name'] for r in res_e]
        print(f"Entidades en DB: {entities}")
        
        # 2. Verificar Colaboraciones
        q = """
        MATCH (e1:Entity {name: 'Facultad de Ciencias'})<-[:AFFILIATED_TO]-(a1:Academic)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(a2:Academic)-[:AFFILIATED_TO]->(e2:Entity {name: 'Instituto de Ciencias Nucleares'}) 
        RETURN count(p) AS cp, count(DISTINCT a1) AS ca1, count(DISTINCT a2) AS ca2
        """
        res_c = session.run(q)
        row = res_c.single()
        if row:
            print(f"Colaboraciones encontradas:")
            print(f"  Artículos: {row['cp']}")
            print(f"  Autores FC: {row['ca1']}")
            print(f"  Autores ICN: {row['ca2']}")
        else:
            print("No se encontraron colaboraciones aún.")
            
        # 3. Verificar si hay papers cargados para FC aunque no sean colaboraciones
        res_p = session.run("MATCH (e:Entity {name: 'Facultad de Ciencias'})-[:HAS_PAPER]->(p:Paper) RETURN count(p) as c")
        print(f"Papers directamente vinculados a Facultad de Ciencias: {res_p.single()['c']}")
        
    store.close()

if __name__ == '__main__':
    validate_collaboration()
