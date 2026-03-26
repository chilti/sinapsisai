import json
import os
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

def drastic_cleanup():
    # CONFIGURACIÓN
    HOST = "localhost" # Ajustar según necesidad
    NEO4J_URI = f"bolt://{HOST}:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASS = "password123"
    
    QDRANT_HOST = HOST
    QDRANT_PORT = 6333
    
    print(f"🚀 Iniciando LIMPIEZA DRÁSTICA en {NEO4J_URI}...")
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        with driver.session() as session:
            # 1. Contar antes de borrar
            total_papers = session.run("MATCH (p:Paper) RETURN count(p) as c").single()['c']
            wos_papers = session.run("MATCH (p:IndexedWoS) RETURN count(p) as c").single()['c']
            to_delete_count = total_papers - wos_papers
            
            print(f"📊 Estado actual:")
            print(f"   Total Papers: {total_papers}")
            print(f"   Papers WoS (a conservar): {wos_papers}")
            print(f"   Papers NO-WoS (a eliminar): {to_delete_count}")
            
            if to_delete_count <= 0:
                print("✅ No hay artículos no-WoS para eliminar.")
            else:
                input(f"⚠️ Se van a ELIMINAR {to_delete_count} artículos. Presiona Enter para confirmar...")
                
                # Obtener DOIs antes de borrar para limpiar Qdrant
                print("   🔍 Obteniendo DOIs para Qdrant...")
                res_dois = session.run("MATCH (p:Paper) WHERE NOT (p:IndexedWoS) RETURN p.doi as doi")
                dois_to_delete = [r['doi'] for r in res_dois if r['doi']]
                
                # Ejecutar borrado en Neo4j
                print(f"   🗑️ Borrando {to_delete_count} papers en Neo4j...")
                session.run("MATCH (p:Paper) WHERE NOT (p:IndexedWoS) DETACH DELETE p")
                print("   ✅ Neo4j: Papers eliminados.")

                # 2. Limpiar Qdrant
                if dois_to_delete:
                    print(f"   🚀 Sincronizando Qdrant ({len(dois_to_delete)} vectores)...")
                    try:
                        q_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
                        # Batching: Qdrant tiene un límite de tamaño de payload
                        batch_size = 5000
                        for i in range(0, len(dois_to_delete), batch_size):
                            batch = dois_to_delete[i:i+batch_size]
                            q_client.delete(
                                collection_name="api_papers",
                                points_selector=batch
                            )
                            if (i // batch_size) % 10 == 0:
                                print(f"      ✅ Procesados {i + len(batch)} / {len(dois_to_delete)}...")
                        print("   ✅ Qdrant: Todos los vectores eliminados.")
                    except Exception as qe:
                        print(f"   ⚠️ Qdrant Error: {qe}")

            # 3. Limpiar Autores Huérfanos
            print("\n👤 Analizando autores huérfanos...")
            orphan_count = session.run("""
                MATCH (a:Author) 
                WHERE NOT (a:Academic) AND NOT (a)-[:AUTHORED]->(:Paper) 
                RETURN count(a) as c
            """).single()['c']
            
            if orphan_count > 0:
                input(f"⚠️ Se van a ELIMINAR {orphan_count} autores huérfanos. Presiona Enter para confirmar...")
                session.run("""
                    MATCH (a:Author) 
                    WHERE NOT (a:Academic) AND NOT (a)-[:AUTHORED]->(:Paper) 
                    DETACH DELETE a
                """)
                print(f"   🗑️ {orphan_count} autores eliminados.")
            else:
                print("✅ No hay autores huérfanos para eliminar.")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if 'driver' in locals(): driver.close()
    
    print("\n✨ Limpieza drástica completada.")

if __name__ == "__main__":
    drastic_cleanup()
