"""
service_availability.py
=======================
Detecta en tiempo de inicio la disponibilidad de los servicios externos
(Neo4j, Qdrant) y expone flags booleanos para que el resto de la app
pueda deshabilitar funcionalidades de forma limpia sin errores de conexión.

Uso:
    from lib.service_availability import NEO4J_AVAILABLE, QDRANT_AVAILABLE
"""

import os
import socket
import logging

logger = logging.getLogger(__name__)


def _probe_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    """Intenta abrir un socket TCP. Devuelve True si el puerto responde."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------
_NEO4J_URI  = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
_NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
_NEO4J_PASS = os.getenv("NEO4J_PASS") or os.getenv("NEO4J_PASSWORD", "password")

def _check_neo4j() -> bool:
    # Extraer host y puerto del URI bolt://host:port
    try:
        uri_body = _NEO4J_URI.split("//", 1)[-1]          # "127.0.0.1:7687"
        host, port_str = uri_body.rsplit(":", 1)
        port = int(port_str.split("/")[0])
        if not _probe_tcp(host, port):
            return False
        # Conexión real para validar credenciales
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(_NEO4J_URI, auth=(_NEO4J_USER, _NEO4J_PASS))
        with driver.session() as s:
            s.run("RETURN 1").single()
        driver.close()
        return True
    except Exception as e:
        logger.info(f"Neo4j no disponible: {e}")
        return False


# ---------------------------------------------------------------------------
# Qdrant
# ---------------------------------------------------------------------------
_QDRANT_HOST = os.getenv("QDRANT_HOST", "127.0.0.1")
_QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

def _check_qdrant() -> bool:
    if not _probe_tcp(_QDRANT_HOST, _QDRANT_PORT):
        return False
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(host=_QDRANT_HOST, port=_QDRANT_PORT, timeout=3)
        client.get_collections()
        return True
    except Exception as e:
        logger.info(f"Qdrant no disponible: {e}")
        return False


# ---------------------------------------------------------------------------
# Evaluación en tiempo de importación (una sola vez por proceso Streamlit)
# ---------------------------------------------------------------------------
NEO4J_AVAILABLE: bool = _check_neo4j()
QDRANT_AVAILABLE: bool = _check_qdrant()

if not NEO4J_AVAILABLE:
    logger.warning("⚠️  Neo4j no detectado — búsqueda en grafo y Mi Espacio deshabilitados.")
if not QDRANT_AVAILABLE:
    logger.warning("⚠️  Qdrant no detectado — búsqueda semántica del asistente deshabilitada.")
