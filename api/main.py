"""
api/main.py - Servidor FastAPI Principal para SinapsisAI / SNII Info TlachIA
"""
import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Asegurar carga del paquete api y dependencias locales
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
PACKAGES_DIR = BASE_DIR / "python_packages"
if PACKAGES_DIR.exists() and str(PACKAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PACKAGES_DIR))

from api.constants import CORS_ORIGINS, API_PORT, API_HOST
from api.routers import (
    hierarchy,
    academics,
    citations,
    auth_curation,
    reports,
    maps,
    assistant
)

app = FastAPI(
    title="SNII Info TlachIA - Scientific Intelligence API",
    description="Motor analítico de alto rendimiento para el padrón SNII, producción académica y cartografía cienciométrica.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Middleware de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware para reescritura de subrutas en proxy inverso (/sinapsisai/ o /infotlachia/)
@app.middleware("http")
async def rewrite_proxy_path(request: Request, call_next):
    path = request.scope.get("path", "")
    for prefix in ["/sinapsisai", "/infotlachia"]:
        if path.startswith(prefix + "/") or path == prefix:
            request.scope["path"] = path.replace(prefix, "", 1) or "/"
            break
    response = await call_next(request)
    return response

# Compresión GZip para optimizar transferencia de JSONs grandes (coordenadas UMAP, árboles)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Inclusión de Routers Modulares
app.include_router(hierarchy.router)
app.include_router(academics.router)
app.include_router(citations.router)
app.include_router(auth_curation.router)
app.include_router(reports.router)
app.include_router(maps.router)
app.include_router(assistant.router)

@app.get("/api/health")
def health_check():
    """Endpoint de comprobación de salud del servicio."""
    return {
        "status": "healthy",
        "service": "SNII Info TlachIA API",
        "version": "2.0.0"
    }

@app.get("/api/info")
def api_info():
    """Información general de endpoints y documentación de la API."""
    return {
        "status": "online",
        "app": "SNII Info TlachIA - Scientific Intelligence API",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": [
            "/api/hierarchy",
            "/api/academics",
            "/api/citations",
            "/api/auth",
            "/api/reports",
            "/api/maps",
            "/api/assistant"
        ]
    }

# Servir producción de React (frontend/dist) si está disponible
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        file_path = FRONTEND_DIST / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    def root():
        return {
            "status": "online",
            "message": "SNII Info TlachIA API Backend está listo. Frontend React en construcción.",
            "docs": "/docs",
            "info": "/api/info"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=True)
