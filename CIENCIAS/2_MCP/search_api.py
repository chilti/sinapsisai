# search_api.py (ACTUALIZADO)

from fastapi import APIRouter, HTTPException, Body
from schemas import SearchRequest, SearchResponse, SearchResult, QueryResponse, AuthorSearchRequest, QueryResult
# CAMBIO: Importamos el 'client' en lugar de la 'collection'
from milvus_connector import client, COLLECTION_NAME
from typing import Literal
import openai
import re
from unidecode import unidecode


router = APIRouter()

# Cliente para LM Studio (sin cambios)
lmstudio_client = openai.OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="not-needed"
)

# Campos de búsqueda válidos (sin cambios)
ValidSearchFields = Literal[
    "title",
    "authors",
    "abstract",
    "research_area"
]

def get_embedding(text: str):
    """Obtiene el embedding desde LM Studio (sin cambios)."""
    response = lmstudio_client.embeddings.create(model="paraphrase-multilingual-mpnet-base-v2", input=[text])
    return response.data[0].embedding

@router.post("/search/{field}", response_model=SearchResponse, tags=["Search"])
async def search_in_milvus(
    field: ValidSearchFields,
    request: SearchRequest = Body(...)
):
    """Realiza la búsqueda usando el MilvusClient."""
    try:
        print("embedding start")
        query_vector = get_embedding(request.query)
        print("embedding done")
        vector_field_name = f"{field}_vector"
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        print(vector_field_name)

        # --- CAMBIO: Se utiliza client.search() ---
        results = client.search(
            collection_name=COLLECTION_NAME,
            data=[query_vector],
            anns_field=vector_field_name,
            search_params=search_params,
            limit=request.top_k,
            output_fields=["row_data"]
        )
        print('Termino busqueda  '+str(len(results[0])))
        
        # --- CAMBIO: Ajuste al nuevo formato de resultados ---
        response_results = []
        for hit in results[0]: # Iteramos sobre los resultados de la primera consulta
            response_results.append(
                SearchResult(
                    id=hit['accession_number'],                    
                    distance=hit['distance'],                  
                    metadata=hit['entity'].get("row_data", {})                 
                )
            )
        print('Regresando resultados')
        return SearchResponse(results=response_results)

    except Exception as e:
        print(f"Error durante la búsqueda en el campo '{field}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 1. Funciones auxiliares para procesar el nombre
def parse_author_name(raw_name: str) -> list:
    """Divide un nombre compuesto por espacios, guiones o comas."""
    normalized_string = re.sub(r'[-,\.]', ' ', raw_name)
    parts = normalized_string.split()
    return parts

def build_filter_expression(name_parts: list, operator: str) -> str:
    """Construye una expresión de filtro de Milvus con AND u OR."""
    if not name_parts:
        return ""
    clauses = [f"(authors like '%{part}%')" for part in name_parts]
    return f" {operator} ".join(clauses)

def normalizar_apellido(apellido: str) -> str:
    """Convierte a minúsculas y elimina acentos."""
    return unidecode(apellido.lower())
    
# 2. Nuevo endpoint
@router.post("/author/search", response_model=QueryResponse, tags=["Search"])
async def search_by_author_advanced(request: AuthorSearchRequest = Body(...)):
    """
    Realiza una búsqueda exacta y avanzada por autor, dividiendo el nombre
    y combinando las partes con un operador lógico (AND/OR).
    """
    try:
        name_parts = normalizar_apellido(request.author_name)
        name_parts = parse_author_name(name_parts)
        
        print('entró')
        if not name_parts:
            # Si el nombre está vacío o es inválido, devuelve una lista vacía
            return QueryResponse(results=[])

        # Construye la expresión de filtro
        expr = build_filter_expression(name_parts, request.operator)
        print(f"Executing filter: {expr}") # Para depuración

        # Usa client.query para búsquedas basadas en filtros
        results = client.query(
            collection_name=COLLECTION_NAME,
            filter=expr,
            # Pide los campos que quieres devolver
            limit=request.top_k,
            output_fields=["row_data", "authors"]
        )

        # Formatea la respuesta para que coincida con el modelo Pydantic
        response_results = [
            QueryResult(metadata=hit) for hit in results
        ]
        print(response_results)
        return QueryResponse(results=response_results)

    except Exception as e:
        print(f"Error durante la búsqueda de autor: {e}")
        raise HTTPException(status_code=500, detail=str(e))