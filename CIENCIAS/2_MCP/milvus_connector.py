# milvus_connector.py (ACTUALIZADO)

from pymilvus import MilvusClient
import os

# --- Configuración ---
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
COLLECTION_NAME = "Ciencias_08_25_InCitesRecords_Milvus_JSON_COS"

# --- CAMBIO: Inicialización del Cliente Unificado ---
# Esta única instancia gestionará la conexión y todas las operaciones.
client = MilvusClient(
    uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}"
)

def ensure_collection_loaded():
    """Verifica que la colección exista y la carga en memoria."""
    try:
        if not client.has_collection(collection_name=COLLECTION_NAME):
            print(f"❌ Error: La colección '{COLLECTION_NAME}' no existe.")
            # En un entorno real, podrías querer lanzar una excepción aquí
            return
        
        print(f"⏳ Cargando colección '[bold green]{COLLECTION_NAME}[/bold green]' en memoria...")
        client.load_collection(collection_name=COLLECTION_NAME)
        print("✅ Colección cargada.")
    except Exception as e:
        print(f"❌ Error al cargar la colección de Milvus: {e}")
        raise

def close_milvus_connection():
    """Cierra la conexión del cliente Milvus."""
    print("🔌 Cerrando conexión con Milvus...")
    client.close()