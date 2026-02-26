# schemas.py

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Literal

class SearchRequest(BaseModel):
    """Modelo para la petición de búsqueda."""
    query: str = Field(..., description="El texto de búsqueda que se convertirá en vector.")
    top_k: int = Field(10, gt=0, le=100, description="Número de resultados a devolver.")

class SearchResult(BaseModel):
    """Modelo para un único resultado de búsqueda."""
    id: str
    distance: float
    metadata: Dict[str, Any]

class SearchResponse(BaseModel):
    """Modelo para la respuesta completa de la búsqueda."""
    results: List[SearchResult]

# --- NUEVOS ESQUEMAS PARA LA BÚSQUEDA AVANZADA DE AUTOR ---

class AuthorSearchRequest(BaseModel):
    """Modelo para la petición de búsqueda de autor."""
    author_name: str = Field(..., description="Nombre del autor a buscar, puede ser compuesto.")
    operator: str = Field("AND", description="Operador lógico para combinar las partes del nombre.")
    top_k: int = Field(10, gt=0, le=100, description="Número de resultados a devolver.")

class QueryResult(BaseModel):
    """Modelo para un único resultado de una consulta (query), sin distancia."""
    metadata: Dict[str, Any]

class QueryResponse(BaseModel):
    """Modelo para la respuesta de una consulta (query)."""
    results: List[QueryResult]