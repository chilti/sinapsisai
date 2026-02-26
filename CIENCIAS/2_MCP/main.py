# main.py (ACTUALIZADO)

from fastapi import FastAPI
from search_api import router as search_router
# CAMBIO: Se importan las nuevas funciones del conector
from milvus_connector import ensure_collection_loaded, close_milvus_connection

app = FastAPI(
    title="API de Búsqueda con MilvusClient",
    description="Un microservicio moderno para realizar búsquedas vectoriales.",
    version="3.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Al iniciar, asegura que la colección esté cargada."""
    print("🚀 Iniciando la aplicación...")
    ensure_collection_loaded()

@app.on_event("shutdown")
async def shutdown_event():
    """Al apagar, cierra la conexión del cliente."""
    print("🔌 Apagando la aplicación...")
    close_milvus_connection()

# El resto del archivo no cambia
app.include_router(search_router, prefix="/api")

@app.get("/", tags=["Health Check"])
async def root():
    """Endpoint principal para verificar que el servicio está activo."""
    return {"status": "ok", "message": "Servicio de Búsqueda Activo"}