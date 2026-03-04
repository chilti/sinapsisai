import os
import sys

# Asegurar que el directorio raíz del proyecto esté en el path para encontrar 'database'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.knowledge_graph import Neo4jGraphStore
from qdrant_client import QdrantClient
from qdrant_client.http import models

def cleanup_databases():
    """
    Limpia completamente las bases de datos Neo4j y Qdrant para iniciar una ingesta limpia.
    """
    print("⚠️  ADVERTENCIA: Se borrará toda la información de Neo4j y Qdrant.")
    confirm = input("¿Estás seguro de que deseas continuar? (s/n): ")
    if confirm.lower() != 's':
        print("Operación cancelada.")
        return

    # 1. Limpiar Neo4j
    print("🧹 Limpiando Neo4j...")
    try:
        graph = Neo4jGraphStore()
        with graph.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("✅ Neo4j limpiado exitosamente.")
    except Exception as e:
        print(f"❌ Error limpiando Neo4j: {e}")

    # 2. Limpiar Qdrant
    print("🧹 Limpiando colecciones de Qdrant...")
    try:
        # Asumiendo configuración estándar de Qdrant
        client = QdrantClient(host="localhost", port=6333)
        collections = ["scientific_papers", "api_papers"]  # Nombres reales de las colecciones

        for col in collections:
            try:
                client.delete_collection(collection_name=col)
                print(f"✅ Colección '{col}' eliminada.")
            except:
                print(f"ℹ️  La colección '{col}' no existía o ya fue eliminada.")
        print("✅ Qdrant limpiado.")
    except Exception as e:
        print(f"❌ Error limpiando Qdrant: {e}")

if __name__ == "__main__":
    cleanup_databases()
