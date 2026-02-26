from pymilvus import utility, connections

# --- Configuración ---
# Asegúrate de que estos valores coincidan con tu configuración de Milvus
MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"

# IMPORTANTE: Escribe aquí el nombre exacto de la colección que quieres eliminar
COLLECTION_NAME = "Ciencias_08_25_InCitesRecords_Milvus_JSON" 

# 1. Conectarse a Milvus
print(f"🔌 Conectando a Milvus en {MILVUS_HOST}:{MILVUS_PORT}...")
connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)

# 2. Comprobar si la colección existe antes de intentar borrarla
if utility.has_collection(COLLECTION_NAME):
    print(f"✅ Colección '{COLLECTION_NAME}' encontrada. Procediendo a eliminarla...")
    
    # 3. Eliminar la colección
    utility.drop_collection(COLLECTION_NAME)
    
    print(f"💥 Colección '{COLLECTION_NAME}' ha sido eliminada exitosamente.")
else:
    print(f"🤷 La colección '{COLLECTION_NAME}' no existe. No se realizó ninguna acción.")

# 4. Desconectarse de Milvus
connections.disconnect("default")
