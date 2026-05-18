import os
import sys

# Asegurar que el directorio raíz del proyecto esté en el path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.append(project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

from database.knowledge_graph import Neo4jGraphStore

def reset_neo4j():
    """
    Realiza una limpieza total de Neo4j:
    1. Borra todos los nodos y relaciones en lotes.
    2. Borra todos los índices.
    3. Borra todas las restricciones (constraints).
    """
    print("⚠️  ADVERTENCIA: Se borrará TODO el contenido y el ESQUEMA (índices/constraints) de Neo4j.")
    confirm = input("¿Estás seguro de que deseas continuar? (s/n): ")
    if confirm.lower() != 's':
        print("Operación cancelada.")
        return

    graph = Neo4jGraphStore()
    
    with graph.driver.session() as session:
        # 1. Borrar Nodos y Relaciones en lotes
        print("🧹 Borrando nodos y relaciones en lotes (10,000 por lote)...")
        try:
            # Usamos auto-commit para IN TRANSACTIONS
            session.run("CALL { MATCH (n) DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS")
            print("✅ Nodos y relaciones eliminados.")
        except Exception as e:
            print(f"❌ Error en borrado por lotes: {e}")
            print("Intentando borrado simple (fallback)...")
            try:
                session.run("MATCH (n) DETACH DELETE n")
                print("✅ Nodos eliminados (fallback).")
            except Exception as e2:
                print(f"❌ Error en borrado simple: {e2}")

        # 2. Borrar Constraints
        print("🧹 Borrando restricciones (constraints)...")
        try:
            constraints = session.run("SHOW CONSTRAINTS YIELD name RETURN name")
            constraint_names = [record["name"] for record in constraints]
            for name in constraint_names:
                session.run(f"DROP CONSTRAINT {name}")
                print(f"   - Constraint '{name}' eliminada.")
            print(f"✅ {len(constraint_names)} restricciones eliminadas.")
        except Exception as e:
            print(f"❌ Error borrando restricciones: {e}")

        # 3. Borrar Índices
        print("🧹 Borrando índices...")
        try:
            indexes = session.run("SHOW INDEXES YIELD name RETURN name")
            index_names = [record["name"] for record in indexes]
            # Filtramos para no intentar borrar índices del sistema si los hay
            for name in index_names:
                try:
                    session.run(f"DROP INDEX {name}")
                    print(f"   - Índice '{name}' eliminado.")
                except:
                    pass 
            print(f"✅ Índices de usuario procesados.")
        except Exception as e:
            print(f"❌ Error borrando índices: {e}")

    graph.close()
    print("\n✨ Neo4j está ahora totalmente limpio (Datos + Esquema).")

if __name__ == "__main__":
    reset_neo4j()
