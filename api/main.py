"""
api/main.py - Servidor FastAPI Principal para SinapsisAI / SNII Info TlachIA
"""
import os
import sys
from pathlib import Path
import re
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
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
    assistant,
    graph_explorer
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
    for prefix in ["/sinapsisai_dev", "/sinapsisai", "/infotlachia"]:
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
app.include_router(graph_explorer.router)

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
    """Información general de endpoints, snapshot y documentación de la API."""
    metadata_path = BASE_DIR / "data" / "pipeline_metadata.json"
    meta = {}
    if metadata_path.exists():
        try:
            import json
            with open(metadata_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            pass

    return {
        "status": "online",
        "app": "SNII Info TlachIA - Scientific Intelligence API",
        "version": meta.get("pipeline_version", "2.0.0"),
        "docs": "/docs",
        "endpoints": [
            "/api/hierarchy",
            "/api/academics",
            "/api/citations",
            "/api/auth",
            "/api/reports",
            "/api/maps",
            "/api/assistant",
            "/api/graph"
        ],
        **meta
    }

# Montar directorio de estáticos (CoAuthra, mapas, etc.)
STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static_dir")

# Servir producción de React (frontend/dist) si está disponible
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static")

    @app.get("/{full_path:path}")
    def serve_frontend(request: Request, full_path: str = ""):
        file_path = FRONTEND_DIST / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        index_file = FRONTEND_DIST / "index.html"
        try:
            html_content = index_file.read_text(encoding="utf-8")
        except Exception:
            return FileResponse(index_file)

        # Inyección dinámica de metadatos Open Graph / Twitter Cards según parámetros de permalink
        academic = request.query_params.get("academic")
        institution = request.query_params.get("institution")
        dependency = request.query_params.get("dependency")
        tab = request.query_params.get("tab")

        og_title = "Info TlachIA SNII | Inteligencia Científica y Producción Académica"
        og_desc = "Plataforma analítica avanzada para trayectoria de investigadores, métricas de citación zero-join y cartografía cienciométrica."

        if academic:
            try:
                from api.db import get_curation
                if get_curation().is_profile_hidden(name=academic):
                    og_title = "Perfil no encontrado o privado | Info TlachIA SNII"
                    og_desc = "El perfil solicitado no está disponible o ha sido configurado como privado por su titular."
                else:
                    og_title = f"Perfil de {academic} | Info TlachIA SNII"
                    og_desc = f"Trayectoria cienciométrica, producción científica e impacto de citas en el Sistema Nacional de Investigadoras e Investigadores (SNII)."
            except Exception:
                og_title = f"Perfil de {academic} | Info TlachIA SNII"
                og_desc = f"Trayectoria cienciométrica, producción científica e impacto de citas en el Sistema Nacional de Investigadoras e Investigadores (SNII)."
        elif institution:
            entity_lbl = f"{dependency} ({institution})" if dependency else institution
            og_title = f"Panorama Institucional: {entity_lbl} | Info TlachIA SNII"
            og_desc = f"Capacidad instalada, producción científica y cartografía analítica de {entity_lbl} registrada en OpenAlex y SNII."
        elif tab == "national":
            og_title = "Panorama Nacional de la Ciencia Mexicana | Info TlachIA SNII"
            og_desc = "Cartografía cienciométrica y producción de la República Mexicana registrada en OpenAlex y miembros vigentes del SNII."

        escaped_title = og_title.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        escaped_desc = og_desc.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
        req_url = str(request.url)

        html_content = re.sub(r'<title>.*?</title>', f'<title>{escaped_title}</title>', html_content, flags=re.DOTALL)
        html_content = re.sub(r'<meta name="description" content=".*?"\s*/?>', f'<meta name="description" content="{escaped_desc}" />', html_content, flags=re.DOTALL)

        og_tags = f"""    <!-- Metadatos Dinámicos Open Graph / Twitter Cards (Permalink Compartido) -->
    <meta property="og:type" content="website" />
    <meta property="og:title" content="{escaped_title}" />
    <meta property="og:description" content="{escaped_desc}" />
    <meta property="og:url" content="{req_url}" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{escaped_title}" />
    <meta name="twitter:description" content="{escaped_desc}" />
  </head>"""

        html_content = html_content.replace('</head>', og_tags)
        return HTMLResponse(content=html_content, media_type="text/html")
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
