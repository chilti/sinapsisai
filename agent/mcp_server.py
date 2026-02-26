import json
import pyalex
from mcp.server.fastmcp import FastMCP
from cachetools import cached, TTLCache
from datetime import datetime
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_community.tools import DuckDuckGoSearchRun
from scidownl import scihub_download
import os

# Configuración inicial
pyalex.config.email = "jlja@ciencias.unam.mx"
api_cache = TTLCache(maxsize=500, ttl=3600)

try:
    search_ddg = DuckDuckGoSearchRun()
    wikipedia_api_wrapper = WikipediaAPIWrapper(top_k_results=1, doc_content_chars_max=4000)
except Exception as e:
    print(f"Advertencia: No se pudieron inicializar las herramientas de búsqueda web. {e}")

# Crear el servidor MCP
mcp = FastMCP("RAG_OpenAlex_Tools")

@mcp.tool()
@cached(api_cache)
def recover_from_openalex(doi: str) -> str:
    """Recupera por DOI el registro bibliográfico completo de OpenAlex."""
    try:
        work = pyalex.Works()[f"https://doi.org/{doi}"]
        return json.dumps(work, ensure_ascii=False)
    except Exception as e:
        return f"Error: No se encontró el DOI o error en OpenAlex: {e}"

@mcp.tool()
@cached(api_cache)
def search_author(fullname: str) -> str:
    """Busca un autor en OpenAlex por nombre. Devuelve hasta 3 perfiles."""
    try:
        autores = pyalex.Authors().search(fullname).get()
        resultados = [
            {
                "id": autor["id"],
                "nombre": autor["display_name"],
                "institucion": autor['affiliations'][0]['institution']['display_name'] if autor.get('affiliations') else 'N/A',
                "trabajos": autor.get("works_count"),
                "citaciones": autor.get("cited_by_count"),
                'orcid': autor.get("orcid")
            }
            for autor in autores[:3]
        ]
        return json.dumps(resultados, ensure_ascii=False)
    except Exception as e:
        return f"Error buscando autor: {e}"

@mcp.tool()
@cached(api_cache)
def get_author_works(author_id: str, n: int = 10, sort_by: str = "recency") -> str:
    """Obtiene trabajos de un autor con ordenamiento flexible Opciones de sort_by: recency o citations."""
    try:
        author_id = author_id.split("/")[-1]
        sort_field = "publication_date" if sort_by == "recency" else "cited_by_count"
        
        trabajos = (
            pyalex.Works()
            .filter(author={"id": author_id})
            .sort(**{sort_field: "desc"})
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
                pass 
        return json.dumps(resultados, ensure_ascii=False)
    except Exception as e:
        return f"Error obteniendo trabajos del autor: {e}"

@mcp.tool()
@cached(api_cache)
def get_author_top_works(author_id: str, n: int = 5, years: int = 5) -> str:
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
        return json.dumps([
            {
                "titulo": work.get("title"), "año": work.get("publication_year"),
                "citas": work.get("cited_by_count"),
                "revista": work.get("primary_location", {}).get("source", {}).get("display_name"),
                "DOI": work.get("doi")
            } for work in top_works
        ], ensure_ascii=False)
    except Exception as e:
        return f"Error obteniendo los trabajos más citados del autor: {e}"

@mcp.tool()
@cached(api_cache)
def search_institution(name: str) -> str:
    """Busca perfiles de instituciones por nombre."""
    try:
        institutions = pyalex.Institutions().search(name).get()
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
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        return f"Error buscando institución: {e}"

@mcp.tool()
@cached(api_cache)
def get_institution_works_by_year(institution_id: str) -> str:
    """Agrupa los trabajos de una institución por año de publicación."""
    try:
        norm_id = institution_id.split("/")[-1]
        grouped_by_year = pyalex.Works().filter(
            authorships={"institutions": {"id": norm_id}}
        ).group_by("publication_year").get()
        
        results = [{"year": group["key"], "works_count": group["count"]} for group in grouped_by_year]
        return json.dumps(sorted(results, key=lambda x: x['year'], reverse=True), ensure_ascii=False)
    except Exception as e:
        return f"Error en la agregación: {e}"

@mcp.tool()
@cached(api_cache)
def get_author_works_by_year(author_id: str) -> str:
    """Agrupa los trabajos de un autor por año de publicación."""
    try:
        norm_id = author_id.split("/")[-1]
        grouped_by_year = pyalex.Works().filter(
            author={"id": norm_id}
        ).group_by("publication_year").get()
        
        results = [{"year": group["key"], "works_count": group["count"]} for group in grouped_by_year if group.get("key") is not None]
        return json.dumps(sorted(results, key=lambda x: x['year'], reverse=True), ensure_ascii=False)
    except Exception as e:
        return f"Error en la agregación de trabajos del autor: {e}"

@mcp.tool()
def web_search(query: str) -> str:
    """Util para buscar información general y actualizada en internet a través de DuckDuckGo."""
    try:
        return json.dumps({"result": search_ddg.run(query)}, ensure_ascii=False)
    except Exception as e:
        return f"Error en la búsqueda web: {e}"

@mcp.tool()
def wikipedia_search(query: str) -> str:
    """Útil para buscar definiciones y descripciones de conceptos en Wikipedia."""
    try:
        return json.dumps({"result": wikipedia_api_wrapper.run(query)}, ensure_ascii=False)
    except Exception as e:
        return f"Error en la búsqueda de Wikipedia: {e}"

@mcp.tool()
def download_paper_by_doi(doi: str) -> str:
    """Descarga un PDF de Sci-Hub dado su DOI y lo guarda en la carpeta 'pdf/' con el nombre del DOI."""
    try:
        # Limpiar el DOI para usarlo como nombre de archivo
        safe_doi = doi.replace("/", "_").replace(":", "_")
        dest_path = f"pdf/{safe_doi}.pdf"
        
        # Asegurar que el directorio existe
        os.makedirs("pdf", exist_ok=True)
        
        print(f"📥 Descargando paper: {doi} -> {dest_path}")
        scihub_download(doi, paper_type='doi', out=dest_path)
        
        if os.path.exists(dest_path):
            return f"Éxito: El paper con DOI {doi} ha sido descargado en {dest_path}"
        else:
            return f"Error: No se pudo descargar el paper {doi}. Verifique si el DOI está disponible en Sci-Hub."
    except Exception as e:
        return f"Error durante la descarga de Sci-Hub: {e}"

if __name__ == "__main__":
    # Inicia el servidor MCP local para desarrollo o depuración
    mcp.run()
