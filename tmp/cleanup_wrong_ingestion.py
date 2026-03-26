import json
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

def cleanup_server_data():
    # CONFIGURACIÓN DEL SERVIDOR
    HOST = "localhost"
    NEO4J_URI = f"bolt://{HOST}:7687"
    QDRANT_HOST = HOST
    QDRANT_PORT = 6333
    
    # Credenciales Neo4j (asumiendo las de .env o las proporcionadas)
    NEO4J_USER = "neo4j"
    NEO4J_PASS = "password123" # Cambiar si es otra
    
    print(f"🚀 Conectando a Neo4j en {NEO4J_URI}...")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        with driver.session() as session:
            # 1. Identificar Papers mal vinculados
            # Buscamos papers :IndexedOpenAlex que están vinculados a una Entity cuyo ROR NO aparece en su metadata original
            query = """
            MATCH (p:IndexedOpenAlex)-[r:AFFILIATED_TO]->(e:Entity)
            WHERE e.ror IS NOT NULL
            RETURN p.doi as doi, p.raw_metadata as meta, e.name as inst_name, e.ror as inst_ror, id(r) as rel_id
            """
            results = session.run(query)
            
            wrong_rels = []
            wrong_papers = set()
            total_verified = 0
            
            print("🔍 Verificando integridad de vínculos...")
            for rec in results:
                total_verified += 1
                meta = json.loads(rec['meta']) if isinstance(rec['meta'], str) else rec['meta']
                inst_ror = rec['inst_ror']
                
                # Extraer RORs legítimos del paper
                legit_rors = []
                for auth in meta.get('authorships', []):
                    for inst in auth.get('institutions', []):
                        if inst.get('ror'): legit_rors.append(inst['ror'])
                
                # Si el ROR de la relación no está en los RORs legítimos, es un error
                if inst_ror not in legit_rors:
                    wrong_rels.append(rec['rel_id'])
                    wrong_papers.add(rec['doi'])
                    if len(wrong_rels) % 100 == 0:
                        print(f"   ⚠️ Encontrados {len(wrong_rels)} errores de vinculación...")

            print(f"\n📊 Diagnóstico Final:")
            print(f"   Vínculos verificados: {total_verified}")
            print(f"   Vínculos incorrectos a eliminar: {len(wrong_rels)}")
            print(f"   Papers afectados (DOIs): {len(wrong_papers)}")

            if not wrong_rels:
                print("✅ No se encontraron inconsistencias. Nada que limpiar.")
                return

            # 2. Proceder a la eliminación en Neo4j (Relaciones)
            print(f"\n🗑️ Eliminando {len(wrong_rels)} relaciones incorrectas en Neo4j...")
            session.run("MATCH ()-[r]->() WHERE id(r) IN $ids DELETE r", ids=wrong_rels)
            
            # 3. Eliminar Papers aislados (opcional)
            # Si un paper ya no tiene vínculos :AFFILIATED_TO, probablemente fue un error total
            print("   🧹 Limpiando papers aislados...")
            session.run("""
                MATCH (p:IndexedOpenAlex)
                WHERE NOT (p)-[:AFFILIATED_TO]->(:Entity)
                DETACH DELETE p
            """)
            
        driver.close()
    except Exception as e:
        print(f"❌ Error Neo4j: {e}")
        return

    # 4. Limpieza en Qdrant
    print(f"\n🚀 Conectando a Qdrant en {QDRANT_HOST}:{QDRANT_PORT}...")
    try:
        q_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        # Solo eliminamos de Qdrant si el paper ya no existe en Neo4j (fue un paper totalmente erróneo)
        # Volvemos a consultar Neo4j para ver qué DOIs quedaron borrados
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        with driver.session() as session:
             # Papers que estaban en nuestra lista de "wrong" pero ya no existen en Neo4j
             # Nota: Esto es simplificado.
             print(f"🗑️ Eliminando {len(wrong_papers)} posibles puntos en Qdrant (api_papers)...")
             for doi in wrong_papers:
                 # Check if paper still exists in Neo4j (maybe it had a valid link too)
                 res = session.run("MATCH (p:Paper {doi: $doi}) RETURN count(p) as c", doi=doi)
                 if res.single()['c'] == 0:
                     try:
                         q_client.delete(
                             collection_name="api_papers",
                             points_selector=[doi] # Asumiendo que el ID es el DOI
                         )
                     except UnexpectedResponse: pass
        driver.close()
    except Exception as e:
        print(f"❌ Error Qdrant: {e}")

if __name__ == "__main__":
    cleanup_server_data()
