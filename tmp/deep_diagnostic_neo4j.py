from neo4j import GraphDatabase

def deep_diagnostic():
    # Usamos localhost porque el usuario parece estar corriendo el script localmente con túnel/VPN
    uri = "bolt://localhost:7687"
    driver = GraphDatabase.driver(uri, auth=("neo4j", "password123"))
    
    with driver.session() as session:
        print("📊 Estadísticas Generales de Neo4j:")
        
        # 1. Conteo por Labels
        labels = session.run("CALL db.labels()")
        for label in labels:
            l_name = label[0]
            count = session.run(f"MATCH (n:{l_name}) RETURN count(n) as c").single()['c']
            print(f"   - Label :{l_name}: {count} nodos")
            
        # 2. Conteo de Relaciones
        rels = session.run("CALL db.relationshipTypes()")
        print("\n🔗 Estadísticas de Relaciones:")
        for rel in rels:
            r_type = rel[0]
            count = session.run(f"MATCH ()-[r:{r_type}]->() RETURN count(r) as c").single()['c']
            print(f"   - :{r_type}: {count} relaciones")

        # 3. Investigar Papers :IndexedOpenAlex sin ROR en la entidad
        print("\n🔍 Investigando papers :IndexedOpenAlex y sus vínculos:")
        query = """
        MATCH (p:IndexedOpenAlex)-[:AFFILIATED_TO]->(e:Entity)
        RETURN count(p) as total_links_oa, 
               count(DISTINCT p) as unique_papers_oa,
               count(DISTINCT e) as unique_entities_oa
        """
        res = session.run(query).single()
        print(f"   - Total vínculos OA -> Entity: {res['total_links_oa']}")
        print(f"   - Papers OA únicos vinculados: {res['unique_papers_oa']}")
        print(f"   - Entidades únicas vinculadas a OA: {res['unique_entities_oa']}")

        # 4. Ver si hay Entities SIN ROR pero vinculadas a OA
        query = """
        MATCH (p:IndexedOpenAlex)-[:AFFILIATED_TO]->(e:Entity)
        WHERE e.ror IS NULL
        RETURN count(DISTINCT e) as entities_without_ror
        """
        res = session.run(query).single()
        print(f"   - Entidades vinculadas a OA que NO tienen ROR: {res['entities_without_ror']}")

        # 5. Muestra de un paper :IndexedOpenAlex aleatorio para ver sus propiedades
        print("\n📝 Muestra de propiedades de un paper :IndexedOpenAlex:")
        sample = session.run("MATCH (p:IndexedOpenAlex) RETURN p LIMIT 1").single()
        if sample:
            print(json.dumps(dict(sample['p']), indent=2, ensure_ascii=False)[:500])
        else:
            print("   (No hay papers con label :IndexedOpenAlex)")

    driver.close()

if __name__ == "__main__":
    import json
    deep_diagnostic()
