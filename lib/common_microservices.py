import json
import pyalex
from fastapi import FastAPI, HTTPException,Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from pydantic import BaseModel
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.tools import DuckDuckGoSearchRun
import uvicorn
from cachetools import cached, TTLCache

# Crea un caché que guarda hasta 500 resultados durante 1 hora (3600 segundos)
# TTLCache (Time To Live Cache) elimina las entradas después de un tiempo.
api_cache = TTLCache(maxsize=500, ttl=3600)



# --- Inicialización de Clientes y Configuraciones ---
# Se realiza una sola vez al iniciar el servidor

# Configuración de PyAlex
try:
    pyalex.config.email = "jlja@ciencias.unam.mx"
except Exception as e:
    print(f"Advertencia: No se pudo configurar el email de PyAlex. {e}")


# Herramientas de búsqueda web
try:
    search_ddg = DuckDuckGoSearchRun()
    wikipedia_api_wrapper = WikipediaAPIWrapper(top_k_results=1, doc_content_chars_max=4000)
except Exception as e:
    print(f"Advertencia: No se pudieron inicializar las herramientas de búsqueda web. {e}")


# --- Inicialización de la Aplicación FastAPI ---
app = FastAPI(
    title="API de Herramientas para RAG Científico",
    description="Microservicios que exponen herramientas para consultar producción científica (OpenAlex) y conocimiento general (DuckDuckGo, Wikipedia).",
    version="1.0.0",
)

# 1. Crea una instancia del limitador
limiter = Limiter(key_func=get_remote_address)

# 2. Configura la app para usar el limitador
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Modelos de Datos (Pydantic) para validación de entradas ---

class AuthorWorksQuery(BaseModel):
    author_id: str
    n: int = 10
    sort_by: str = "recency" # Opciones: "recency" o "citations"


# --- Endpoints de la API ---



@app.get("/tools/recover_from_openalex", summary="Obtiene registro de OpenAlex por DOI")
@limiter.limit("10/second")
@cached(api_cache) # <-- ¡Añade este decorador!
def recover_from_openalex(request: Request, doi: str):
    """
    Recupera por DOI el registro bibliográfico completo de OpenAlex.
    """
    try:
        work = pyalex.Works()[f"https://doi.org/{doi}"]
        return work
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"No se encontró el DOI o error en OpenAlex: {e}")


@app.get("/tools/recover_author_from_openalex", summary="Busca un autor en OpenAlex por nombre")
@limiter.limit("10/second")
@cached(api_cache) # <-- ¡Añade este decorador!
def recover_author_from_openalex(request: Request, fullname: str):
    """
    Recupera de OpenAlex los tres perfiles de autor más parecidos al nombre proporcionado.
    """
    try:
        autores = pyalex.Authors().search(fullname).get()
        resultados = [
            {
                "id": autor["id"],
                "nombre": autor["display_name"],
                "institucion": autor['affiliations'][0]['institution']['display_name'] if autor.get('affiliations') else 'N/A',
                "trabajos": autor.get("works_count"),
                "citaciones": autor.get("cited_by_count"),
                'works_api_url': autor.get("works_api_url"),
                'orcid': autor.get("orcid")
            }
            for autor in autores[:3]
        ]
        return resultados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error buscando autor en OpenAlex: {e}")


@app.get("/tools/findAuthorWorks", summary="Obtiene trabajos de un autor con ordenamiento flexible Opciones: recency o citations")
@limiter.limit("10/second")
@cached(api_cache) 
def findAuthorWorks(request: Request, author_id: str='A5043129140', n: int = 10, sort_by: str = "recency" ):
    try:
        author_id = author_id.split("/")[-1]
        
        # Elige el campo por el cual ordenar
        sort_field = "publication_date" if sort_by == "recency" else "cited_by_count"

        trabajos = (
            pyalex.Works()
            .filter(author={"id": author_id})
            .sort(**{sort_field: "desc"}) # Ordenamiento dinámico
            .get(per_page=n)
        )
        resultados = []
        for w in trabajos[:n]:
            try:
                resultados.append({
                    "id": w["id"],
                    "titulo": w.get("title"),
                    "año": w.get("publication_year"),
                    "revista": w.get('primary_location').get('source').get('display_name'),
                    "citas": w.get("cited_by_count"),
                    "DOI": w.get("doi")
                })
            except:
                print('excepcion')
                pass 
        return resultados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo trabajos del autor: {e}")

@app.post("/tools/recover_author_works_from_openalex", summary="Obtiene trabajos de un autor en OpenAlex por id o por url")
@limiter.limit("10/second")
@cached(api_cache) 
def recover_author_works_from_openalex(request: Request, author_id: str, n: int = 5):
    """
    Recupera los 'n' trabajos más recientes de un autor en OpenAlex a partir de su ID.
    """
    try:
        author_id = author_id.split("/")[-1] # Normalizar ID
        trabajos = pyalex.Works().filter(**{"author.id": f"https://openalex.org/{author_id}"}).get(per_page=n)
        print(trabajos)
        resultados = []
        for w in trabajos[:n]:
            try:
                resultados.append({
                    "id": w["id"],
                    "titulo": w.get("title"),
                    "año": w.get("publication_year"),
                    "revista": w.get('primary_location').get('source').get('display_name'),
                    "citas": w.get("cited_by_count"),
                    "DOI": w.get("doi")
                })
            except:
                print('excepcion')
                pass 
        return resultados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo trabajos del autor: {e}")

from datetime import datetime

@app.get("/tools/get_author_top_works", summary="Obtiene los trabajos más citados de un autor en en los ultimos years años")
@limiter.limit("5/second")
@cached(api_cache)
def get_author_top_works(request: Request, author_id: str, n: int = 5, years: int = 5):
    """Recupera los 'n' trabajos más citados de un autor en los últimos 'years' años."""
    try:
        norm_id = author_id.split("/")[-1]
        start_year = datetime.now().year - years
        top_works = (
            pyalex.Works()
            .filter(author={"id": norm_id}, publication_year=f">{start_year}")
            .sort(cited_by_count="desc")
            .get(per_page=n)
        )
        return [
            {
                "titulo": work.get("title"), "año": work.get("publication_year"),
                "citas": work.get("cited_by_count"),
                "revista": work.get("primary_location", {}).get("source", {}).get("display_name"),
                "DOI": work.get("doi")
            } for work in top_works
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo los trabajos más citados del autor: {e}")


@app.get("/tools/search_institution", summary="Busca una institución en OpenAlex")
@limiter.limit("10/second")
@cached(api_cache) 
def search_institution(request: Request, name: str):
    """
    Busca perfiles de instituciones por nombre.
    """
    try:
        # Busca las 3 instituciones más relevantes con ese nombre
        institutions = pyalex.Institutions().search(name).get()
        print(institutions)
        results = [
            {
                "id": inst["id"],
                "display_name": inst.get("display_name"),
                "ror": inst.get("ror"),
                "country_code": inst.get("country_code"),
                "works_count": inst.get("works_count"),
                "cited_by_count": inst.get("cited_by_count")
            }
            for inst in institutions[:3]
        ]
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error buscando institución: {e}")
        
# En tools_as_microservices.py

@app.get("/tools/search_source", summary="Busca una fuente (revista, congreso) en OpenAlex")
@limiter.limit("10/second")
@cached(api_cache) 
def search_source(request: Request, name: str):
    """
    Busca fuentes (revistas, etc.) por su nombre.
    """
    try:
        sources = pyalex.Sources().search(name).get()
        results = [
            {
                "id": src["id"],
                "display_name": src.get("display_name"),
                "issn_l": src.get("issn_l"),
                "publisher": src.get("publisher"),
                "works_count": src.get("works_count"),
                "cited_by_count": src.get("cited_by_count"),
                "type": src.get("type")
            }
            for src in sources[:3]
        ]
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error buscando fuente: {e}")

# En tools_as_microservices.py

@app.get("/tools/search_concept", summary="Busca un concepto temático en OpenAlex")
@limiter.limit("10/second")
@cached(api_cache) 
def search_concept(request: Request, topic: str):
    """
    Busca conceptos y sus relaciones.
    """
    try:
        concepts = pyalex.Concepts().search(topic).get()
        results = [
            {
                "id": concept["id"],
                "display_name": concept.get("display_name"),
                "level": concept.get("level"),
                "description": concept.get("description"),
                "works_count": concept.get("works_count"),
                "related_concepts": [
                    {"display_name": rel.get("display_name"), "id": rel.get("id")}
                    for rel in concept.get("related_concepts", [])[:5]
                ]
            }
            for concept in concepts[:3]
        ]
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error buscando concepto: {e}")

# En tools_as_microservices.py

@app.get("/tools/get_institution_works_by_year", summary="Obtiene la producción anual de una institución")
@limiter.limit("5/second") # Menor límite para consultas más pesadas
@cached(api_cache) 
def get_institution_works_by_year(request: Request, institution_id: str):
    """
    Agrupa los trabajos de una institución por año de publicación.
    El institution_id puede ser el de OpenAlex (ej. I4210122328) o su ROR (ej. 01tmp8f40 para la UNAM).
    """
    try:
        # Asegurarnos que el ID es solo el código
        norm_id = institution_id.split("/")[-1]
        
        # Filtra trabajos por institución y agrupa por año
        grouped_by_year = pyalex.Works().filter(
            authorships={"institutions": {"id": norm_id}}
        ).group_by("publication_year").get()
        
        # Formatea para que sea más legible
        results = [
            {"year": group["key"], "works_count": group["count"]}
            for group in grouped_by_year
        ]
        return sorted(results, key=lambda x: x['year'], reverse=True)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la agregación: {e}")
        
# En tools_as_microservices.py

@app.get("/tools/get_author_works_by_year", summary="Obtiene la producción anual de un autor")
@limiter.limit("5/second") # Límite más restrictivo para consultas analíticas
@cached(api_cache) 
def get_author_works_by_year(request: Request, author_id: str):
    """
    Agrupa los trabajos de un autor por año de publicación.
    El author_id puede ser el de OpenAlex (ej. A5023867633) o la URL completa.
    """
    try:
        # 1. Normaliza el ID para asegurar que solo tenemos el código
        norm_id = author_id.split("/")[-1]
        
        # 2. Filtra los trabajos por el ID del autor y agrupa por año de publicación
        grouped_by_year = pyalex.Works().filter(
            author={"id": norm_id}
        ).group_by("publication_year").get()
        
        # 3. Formatea los resultados para que sean claros y fáciles de usar
        results = [
            {"year": group["key"], "works_count": group["count"]}
            for group in grouped_by_year if group.get("key") is not None
        ]
        
        # 4. Ordena los resultados por año, del más reciente al más antiguo
        return sorted(results, key=lambda x: x['year'], reverse=True)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la agregación de trabajos del autor: {e}")


@app.get("/tools/web_search", summary="Realiza una búsqueda en DuckDuckGo")
def web_search(query: str):
    """
    Util para buscar información general y actualizada en internet a través de DuckDuckGo.
    """
    try:
        return {"result": search_ddg.run(query)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la búsqueda web: {e}")


@app.get("/tools/wikipedia_search", summary="Realiza una búsqueda en Wikipedia")
def wikipedia_search(query: str):
    """
    Útil para buscar definiciones y descripciones de conceptos en Wikipedia.
    """
    try:
        return {"result": wikipedia_api_wrapper.run(query)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la búsqueda de Wikipedia: {e}")


# --- Ejecución del Servidor ---
if __name__ == "__main__":
    # Para ejecutar: uvicorn common_microservices:app --reload
    uvicorn.run(app, host="0.0.0.0", port=8001)
