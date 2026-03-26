import json
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

def recover_from_wrong_ingestion():
    # CONFIGURACIÓN
    HOST = "localhost" # El usuario debe ajustar esto si no es localhost
    NEO4J_URI = f"bolt://{HOST}:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASS = "password123"
    
    QDRANT_HOST = HOST
    QDRANT_PORT = 6333
    
    mapping_file = 'ROR/snii_ror_mapping.json'
    if not os.path.exists(mapping_file):
        print(f"❌ No se encontró {mapping_file}")
        return
    
    with open(mapping_file, 'r', encoding='utf-8') as f:
        mapping = json.load(f)
    
    # Invertimos el mapeo para saber qué ROR le toca a cada Institución (Entity Name)
    # Formato: { "Nombre Institucion": "https://ror.org/..." }
    name_to_ror = {}
    for key, data in mapping.items():
        inst_name = key.split(' || ')[0]
        ror = data.get('best_match_ror')
        if ror:
            name_to_ror[inst_name] = ror

    print(f"🚀 Conectando a Neo4j en {NEO4J_URI}...")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        with driver.session() as session:
            # 1. Obtener TODOS los papers de OpenAlex y sus vínculos
            query = """
            MATCH (p:IndexedOpenAlex)-[r:AFFILIATED_TO]->(e:Entity)
            RETURN p.doi as doi, p.raw_metadata as meta, e.name as inst_name, id(r) as rel_id
            """
            print("🔍 Analizando TODOS los artículos de OpenAlex en el grafo...")
            results = session.run(query)
            
            wrong_rels = []
            dois_to_delete_qdrant = set()
            total_checked = 0
            
            for rec in results:
                total_checked += 1
                doi = rec['doi']
                inst_name = rec['inst_name']
                rel_id = rec['rel_id']
                
                # Metadata real del artículo
                meta = json.loads(rec['meta']) if isinstance(rec['meta'], str) else rec['meta']
                legit_rors = []
                for auth in meta.get('authorships', []):
                    for inst in auth.get('institutions', []):
                        if inst.get('ror'): legit_rors.append(inst['ror'])
                
                # ROR que DEBERÍA tener esta institución según nuestro mapeo
                expected_ror = name_to_ror.get(inst_name)
                
                # SI el artículo NO tiene el ROR esperado para esta institución, la relación es falsa
                if expected_ror and expected_ror not in legit_rors:
                    wrong_rels.append(rel_id)
                    dois_to_delete_qdrant.add(doi)
                
                if total_checked % 500 == 0:
                    print(f"   ... verificados {total_checked} vínculos. Errores encontrados: {len(wrong_rels)}")

            print(f"\n📊 Diagnóstico:")
            print(f"   Vínculos revisados: {total_checked}")
            print(f"   Vínculos INCORRECTOS: {len(wrong_rels)}")
            
            if not wrong_rels:
                print("✅ Todo parece estar en orden. No se detectaron vínculos falsos.")
            else:
                input(f"⚠️ Se van a ELIMINAR {len(wrong_rels)} vínculos. Presiona Enter para continuar o Ctrl+C para abortar...")
                # Eliminar relaciones
                session.run("MATCH ()-[r]->() WHERE id(r) IN $ids DELETE r", ids=wrong_rels)
                print("   🗑️ Relaciones eliminadas en Neo4j.")
                
                # Eliminar papers que se quedaron solos (totalmente erróneos)
                print("   🧹 Buscando papers huérfanos para borrar...")
                res_del = session.run("""
                    MATCH (p:IndexedOpenAlex)
                    WHERE NOT (p)-[:AFFILIATED_TO]->(:Entity)
                    WITH p, p.doi as doi
                    DETACH DELETE p
                    RETURN doi
                """)
                deleted_dois = [r['doi'] for r in res_del]
                print(f"   🗑️ {len(deleted_dois)} papers huérfanos eliminados de Neo4j.")
                
                # Limpieza en Qdrant
                if deleted_dois:
                    print(f"\n🚀 Conectando a Qdrant para limpiar {len(deleted_dois)} vectores...")
                    try:
                        q_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
                        q_client.delete(
                            collection_name="api_papers",
                            points_selector=deleted_dois
                        )
                        print("   ✅ Qdrant sincronizado.")
                    except Exception as qe:
                        print(f"   ⚠️ Error en Qdrant: {qe}")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'driver' in locals(): driver.close()

if __name__ == "__main__":
    import os
    recover_from_wrong_ingestion()
