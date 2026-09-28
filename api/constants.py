"""
api/constants.py - Constantes y Configuración de SinapsisAI API
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

API_PORT = int(os.getenv("FASTAPI_PORT", "5016"))
API_HOST = os.getenv("FASTAPI_HOST", "0.0.0.0")

# Bases de datos y servicios
CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DB", "default")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASS") or os.getenv("NEO4J_PASSWORD", "password123")

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1")

# Rutas de datos
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache_ch"
TILES_DIR = BASE_DIR / "public" / "tiles"
REPORTS_DIR = BASE_DIR / "reports"
CURATION_DB_PATH = DATA_DIR / "curation_hub.db"

# Orígenes CORS permitidos
CORS_ORIGINS = [
    "*",
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3006",
    "http://localhost:5005",
    "http://localhost:5006",
    "http://localhost:5011",
    "http://localhost:5014",
    "https://dinamica1.fciencias.unam.mx",
]
