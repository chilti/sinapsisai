"""
api/db.py - Capa de Conexiones y Acceso a Datos (Neo4j, ClickHouse, SQLite)
"""
import os
import threading
from typing import Optional, Dict, Any
from api.constants import (
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
)

# ClickHouse Client (Thread-Local Pool)
_ch_local = threading.local()

def get_clickhouse_client():
    """Retorna un cliente autenticado de ClickHouse aislado por hilo."""
    if not hasattr(_ch_local, "client"):
        from database.clickhouse_db import ch_client
        import clickhouse_connect
        _ch_local.client = clickhouse_connect.get_client(
            host=ch_client.host,
            port=ch_client.port,
            username=ch_client.user,
            password=ch_client.password,
            database=ch_client.database,
            connect_timeout=60,
            send_receive_timeout=ch_client.timeout,
            settings={'max_execution_time': ch_client.timeout}
        )
    return _ch_local.client

# Neo4j Graph Store
_neo4j_store = None
_neo4j_lock = threading.Lock()

def get_neo4j_store():
    """Retorna la instancia singleton de Neo4jGraphStore."""
    global _neo4j_store
    if _neo4j_store is None:
        with _neo4j_lock:
            if _neo4j_store is None:
                from database.knowledge_graph import Neo4jGraphStore
                _neo4j_store = Neo4jGraphStore(
                    uri=NEO4J_URI,
                    user=NEO4J_USER,
                    password=NEO4J_PASSWORD
                )
    return _neo4j_store

# Curation Service (SQLite)
def get_curation():
    """Retorna el servicio de curación y acreditación."""
    from lib.curation_service import get_curation_service
    return get_curation_service()

# Jerarquía en memoria
_hierarchy_cache: Optional[Dict[str, Any]] = None
_hierarchy_lock = threading.Lock()

def get_cached_hierarchy() -> Dict[str, Any]:
    """Retorna el árbol jerárquico cargado en memoria."""
    global _hierarchy_cache
    if _hierarchy_cache is None:
        with _hierarchy_lock:
            if _hierarchy_cache is None:
                from dashboard_analytics import get_institution_hierarchy
                _hierarchy_cache = get_institution_hierarchy()
    return _hierarchy_cache or {}
