import json
import os
import sys
import httpx
import pyalex
from pyalex import Works, Authors
from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import tool
from typing import Optional
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from langdetect import detect, LangDetectException
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from lib.service_availability import NEO4J_AVAILABLE, QDRANT_AVAILABLE

load_dotenv()

# Configuración de Autenticación Básica
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")

if not base_url.endswith("/"):
    base_url += "/"

# Construimos la URL autenticada (Basic Auth en URL para evitar sobreescritura de OpenAI)
auth_url = base_url
if user and password:
    if "://" in base_url:
        protocol, rest = base_url.split("://", 1)
        auth_url = f"{protocol}://{user}:{password}@{rest}"
    else:
        auth_url = f"http://{user}:{password}@{base_url}"

# Clientes para saltar verificación SSL
sync_client = httpx.Client(verify=False)
async_client = httpx.AsyncClient(verify=False)

# URL del servicio LLM para traducciones (mismo que el principal)
LLM_URL = auth_url.rstrip('/') + '/chat/completions'
LLM_MODEL = os.getenv('LLM_MODEL', 'openai/gpt-oss-20b')

# Inicialización condicional de conexiones externas
qdrant_docs = QdrantStore(collection_name="scientific_papers") if QDRANT_AVAILABLE else None
qdrant_apis = QdrantStore(collection_name="api_papers") if QDRANT_AVAILABLE else None
neo4j = Neo4jGraphStore() if NEO4J_AVAILABLE else None

def translate_to_english(text: str) -> str:
    """
    Detecta el idioma del texto y lo traduce al inglés si es necesario.
    Usa el LLM local directamente para no agregar dependencias externas.
    """
    try:
        lang = detect(text)
    except LangDetectException:
        lang = 'en'

    if lang == 'en':
        return text  # Ya está en inglés, no hacer nada

    print(f"  🌐 Query detectada en '{lang}', traduciendo al inglés...")
    try:
        resp = sync_client.post(
            LLM_URL,
            json={
                'model': LLM_MODEL,
                'messages': [
                    {'role': 'system', 'content': 'You are a scientific translator. Translate the user text to English. Return ONLY the translation, no explanations.'},
                    {'role': 'user', 'content': text}
                ],
                'temperature': 0,
                'max_tokens': 256
            },
            timeout=20
        )
        resp.raise_for_status()
        translated = resp.json()['choices'][0]['message']['content'].strip()
        print(f"  🌐 Traducción: '{translated}'")
        return translated
    except Exception as e:
        print(f"  ⚠️  Error en traducción: {e}. Usando query original.")
        return text

def get_embedding(text: str) -> list:
    """
    Obtiene el vector (embedding) de un texto usando directamente la API (httpx).
    Evita problemas de compatibilidad de librerías con servidores locales.
    """
    url = auth_url.rstrip('/') + '/embeddings'
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-nomic-ai-nomic-embed-text-v2-moe")
    
    # Intentar primero con input como lista (más estándar en OpenAI v1)
    payload = {
        "model": model,
        "input": [text]
    }
    
    try:
        resp = sync_client.post(url, json=payload, timeout=30)
        if resp.status_code != 200:
            # Si falla como lista, intentar como string (algunos modelos locales lo prefieren así)
            payload["input"] = text
            resp = sync_client.post(url, json=payload, timeout=30)
            
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]
    except Exception as e:
        raise Exception(f"Fallo en servidor de Embeddings ({url}): {str(e)}")

def search_scientific_papers_semantic(query: str, limit: int = 20, entity_context: Optional[str] = None) -> dict:
    """
    Realiza una búsqueda semántica en la base de datos vectorial (Qdrant).
    Busca papers por significado semántico, no solo por palabras clave.
    Retorna títulos, resumen, autores, año, doi, y puntaje de relevancia.
    Las colecciones disponibles en Qdrant son EXACTAMENTE dos:
    - scientific_papers: papers de Scopus (abstract completo, fuente confiable para métricas).
    - api_papers: papers del pipeline local de ClickHouse (abstract, métricas básicas).
    Busca en AMBAS y combina los resultados deduplicados (por DOI).

    Args:
        query: El texto de la búsqueda semántica.
        limit: Número máximo de resultados por colección.
        entity_context: Nombre de la entidad para filtrar resultados por 'entity' del payload.
    """
    if not QDRANT_AVAILABLE:
        return {"error": "Búsqueda semántica no disponible: Qdrant no está conectado en este entorno.",
                "results": []}

    # Traducir al inglés si es necesario (los papers están en inglés)
    query_en = translate_to_english(query)
    
    if not query_en or not query_en.strip():
        return "La consulta está vacía o no pudo ser procesada."

    print(f"🔍 Búsqueda semántica en Qdrant para: '{query_en}'" + (f" [Entidad: {entity_context}]" if entity_context else ""))
    try:
        # Llamada manual al embedding para control total del payload
        query_vector = get_embedding(query_en)
        
        if not query_vector:
            return "Error: No se pudo generar el vector de búsqueda (resultado vacío)."
        
        # Consultar ambas colecciones con filtro nativo por entidad si se proporciona
        results_docs = qdrant_docs.search(query_vector, limit=limit, entity_filter=entity_context)
        results_apis = qdrant_apis.search(query_vector, limit=limit, entity_filter=entity_context)
        
        # Combinar y ordenar por los de mayor relevancia
        all_results = sorted(results_docs + results_apis, key=lambda x: x.get("score", 0), reverse=True)
        top_results = all_results[:limit]
        
        # Fallback: si el filtro por entidad retornó 0, buscar sin filtro
        fallback_used = False
        if not top_results and entity_context:
            print(f"⚠️ Filtro por entidad '{entity_context}' sin resultados. Reintentando sin filtro...")
            results_docs = qdrant_docs.search(query_vector, limit=limit)
            results_apis = qdrant_apis.search(query_vector, limit=limit)
            all_results = sorted(results_docs + results_apis, key=lambda x: x.get("score", 0), reverse=True)
            top_results = all_results[:limit]
            fallback_used = True
        
        if not top_results:
            return f"No se encontraron resultados semánticos para '{query_en}'" + (f" en la entidad '{entity_context}'." if entity_context else ".")
        
        # Incluir el query traducido en el resultado para trazabilidad en el dashboard
        output = {
            "_query_enviado_a_qdrant": query_en,
            "_entity_filter": entity_context or "ninguno",
        }
        if fallback_used:
            output["_advertencia"] = f"El campo 'entity' no está poblado en Qdrant para '{entity_context}'. Se muestran resultados globales. Re-ingesta necesaria."
        output["resultados"] = top_results
        return output
    except Exception as e:
        return f"Error en búsqueda semántica: {str(e)}"

# Alias para compatibilidad con el prompt del agente
search_scientific_papers = search_scientific_papers_semantic

def get_author_coauthors_graph(author_name: str) -> str:
    """
    Consulta el Grafo de Conocimiento (Neo4j) para encontrar coautores de un investigador.
    Retorna los 15 coautores más frecuentes del investigador dado.
    """
    if not NEO4J_AVAILABLE:
        return "Grafo de conocimiento no disponible: Neo4j no está conectado en este entorno."
    print(f"✨️ Consultando grafo de coautoría para: '{author_name}'")
    with neo4j.driver.session() as session:
        result = session.run(
            "MATCH (a1:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)<-[:AUTHOR_OF|AUTHORED]-(a2:Person) "
            "WHERE (toLower(a1.fullname) CONTAINS toLower($name) OR toLower(a1.name) CONTAINS toLower($name)) AND a1 <> a2 "
            "RETURN DISTINCT coalesce(a2.fullname, a2.name) AS coauthor, count(p) AS shared_papers "
            "ORDER BY shared_papers DESC LIMIT 20",
            name=author_name
        )
        coauthors = [{"coauthor": r["coauthor"], "shared_papers": r["shared_papers"]} for r in result]
    
    if not coauthors:
        return f"No se encontró información de coautores para '{author_name}'. Verifica que el apellido esté correcto."
        
    return json.dumps({"author_query": author_name, "coauthors": coauthors}, ensure_ascii=False)

def query_knowledge_graph_cypher(cypher_query: str) -> str:
    """
    Ejecuta una consulta Cypher directa sobre el Grafo de Conocimiento (Neo4j).
    - Artículos: etiqueta genérica `(p:Paper)`. Atributos: `doi`, `title`, `year`, `citations`.
    - Entidades UNAM/Instituciones: etiquetas `(i:Institution)`, `(d:Dependency)`, `(s:Subdependency)`. Atributos: `id`, `name`.
    - Tópicos Temáticos: `(t:Topic)`. Atributos: `id` (slug compuesto en inglés), `name` (nombre en inglés).
    - Objetivos de Desarrollo Sostenible (ODS): `(s:SDG)`. Atributos: `name`.
    
    RELACIONES IMPORTANTES PRECISAS:
    - Publicación: `(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)`
    - Afiliación: `(a:Person)-[:AFFILIATED_TO]->(entity)` donde `entity` puede ser `:Institution`, `:Dependency` o `:Subdependency`.
    - Tópicos: `(p:Paper)-[:HAS_TOPIC]->(t:Topic)`. **IMPORTANTE: Los tópicos están en INGLÉS**. Traduce siempre los términos de búsqueda (ej. de "microscopía" a "microscopy") antes de filtrar `t.name`.
    - SDGs: `(p:Paper)-[:CONTRIBUTES_TO]->(s:SDG)`.
    
    PATRONES DE CONSULTA RECOMENDADOS (SINTAXIS CORRECTA):
    - Filtrar por dependencia y tópico exacto: `MATCH (d:Dependency {name: 'FACULTAD DE CIENCIAS'})<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic) WHERE toLower(t.name) CONTAINS 'microscopy' RETURN p.title, coalesce(a.fullname, a.name) AS name, p.year ORDER BY p.year DESC LIMIT 20`
    - Filtrar papers por dependencia (sin tópico): `MATCH (d:Dependency)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper) WHERE toLower(d.name) CONTAINS 'ciencias' AND p.year >= 2018 RETURN p.doi, p.title, p.year, p.citations ORDER BY p.year DESC LIMIT 20`
    - Filtrar por tópico AMPLIO (usa OR para cubrir variantes): `WHERE toLower(t.name) CONTAINS 'diabetes' OR toLower(t.name) CONTAINS 'insulin' OR toLower(t.name) CONTAINS 'metabolic'`
    - Búsqueda por nombre de persona (usa CONTAINS con fullname o name, NUNCA match exacto):
      `MATCH (a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper) WHERE toLower(coalesce(a.fullname, a.name)) CONTAINS toLower('alcubierre') RETURN p.title, coalesce(a.fullname, a.name) AS name, p.year ORDER BY p.year DESC LIMIT 20`
      RAZÓN: Los nombres están almacenados en formato 'APELLIDO PATERNO, NOMBRE' en MAYÚSCULAS (ej. 'ALCUBIERRE MOYA, MIGUEL'). Un match exacto con el nombre coloquial SIEMPRE fallará.
    
    ❌ ERRORES PROHIBIDOS — NUNCA hagas esto:
    - NO uses parámetros Cypher ($variable). Esta herramienta NO acepta un dict de params separado. Incrusta los valores directamente en el string de la query. INCORRECTO: `WHERE a.id IN $ids`. CORRECTO: `WHERE a.id IN ['id1','id2']`
    - NO uses `(p:Paper)-[:AFFILIATED_TO]->(:Institution)`. Los Papers NO tienen relación AFFILIATED_TO. La afiliación es SIEMPRE a través del académico: `(a:Person)-[:AFFILIATED_TO]->(e)`.
    - NO uses `EXISTS()` con patrones complejos. Usa `MATCH` directos.
    - Para SDGs usa `(p:Paper)-[:CONTRIBUTES_TO]->(s:SDG)`. La relación se llama :CONTRIBUTES_TO, no :ADDRESSES ni :RELEVANT_TO.
      Ejemplo: `MATCH (p:Paper)-[:CONTRIBUTES_TO]->(s:SDG) RETURN s.name, count(p) AS papers ORDER BY papers DESC`
    
    IMPORTANTE: Esta herramienta solo encuentra trabajos con tópicos etiquetados explícitamente. Usa SIEMPRE en paralelo con `search_scientific_papers_semantic` para encontrar trabajos cuyo tópico no coincide textualmente. SIEMPRE usa `LIMIT 20` por defecto en tus consultas Cypher.
    """
    print(f"🕸️ Ejecutando Cypher en Neo4j: {cypher_query}")
    try:
        with neo4j.driver.session() as session:
            result = session.run(cypher_query)
            data = [record.data() for record in result]
            return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return f"Error ejecutando Cypher: {str(e)}"

# --- Nuevas Herramientas de Búsqueda Externa ---

# DuckDuckGo Search
search_ddg = DuckDuckGoSearchRun()

def web_search(query: str) -> str:
    """
    Útil para buscar información en internet. 
    Usar cuando necesites encontrar información actualizada o temas generales 
    que no estén en la base de datos local.
    """
    return search_ddg.run(query)

# Wikipedia
wikipedia_api_wrapper = WikipediaAPIWrapper(top_k_results=1, doc_content_chars_max=4000)
wikipedia_tool_instance = WikipediaQueryRun(api_wrapper=wikipedia_api_wrapper)

def wikipedia_search(query: str) -> str:
    """
    Consulta Wikipedia para obtener resúmenes informativos sobre conceptos, 
    instituciones o personajes científicos.
    """
    return wikipedia_tool_instance.run(query)

# --- Herramientas OpenAlex (Recuperación Directa) ---

def recoverFromOpenAlex(doi: str, fields: Optional[str] = None) -> str:
    """Recupera el registro bibliográfico de un paper desde OpenAlex usando su DOI.
    
    Args:
        doi: El DOI del paper (con o sin prefijo https://doi.org/).
        fields: Opcional. Campo específico a extraer. 
                Keys útiles: 'fwci', 'cited_by_count', 'topics', 'concepts', 
                'sustainable_development_goals', 'abstract_inverted_index', 'open_access'.
                Si no se especifica, retorna el registro completo.
    """
    try:
        clean_doi = doi.replace("https://doi.org/", "").strip()
        work = Works()[f"https://doi.org/{clean_doi}"]
        if fields:
            if fields in work:
                return json.dumps(work.get(fields), ensure_ascii=False)
            return f"Campo '{fields}' no encontrado. Campos disponibles: {list(work.keys())}"
        return json.dumps(work, ensure_ascii=False)
    except Exception as e:
        return f"Error recuperando DOI {doi}: {str(e)}"

def searchAuthorInOpenAlex(fullname: str, n: int = 5) -> str:
    """
    Busca los n autores más parecidos en OpenAlex al nombre dado.
    Útil para encontrar IDs de OpenAlex (Axxxx) de investigadores.
    """
    try:
        autores = Authors().search(fullname).get()
        resultados = []
        for autor in autores[:n]:
            aff = autor.get('affiliations', [{}])[0].get('institution', {}).get('display_name', 'N/A')
            resultados.append({
                "id": autor["id"],
                "nombre": autor["display_name"],
                "institucion": aff,
                "trabajos": autor.get("works_count"),
                "citaciones": autor.get("cited_by_count"),
                'orcid': autor.get("orcid")
            })
        return json.dumps(resultados, ensure_ascii=False)
    except Exception as e:
        return f"Error buscando autor: {str(e)}"

def recoverAuthorWorksFromOpenAlex(author_id: str, n: int = 10) -> str:
    """
    Recupera los primeros n trabajos de un autor en OpenAlex a partir de su author_id (ej. A5023888360).
    """
    try:
        if author_id.startswith("http"):
            author_id = author_id.split("/")[-1]
        
        # Filtrar trabajos por author.id
        trabajos = Works().filter(**{"author.id": f"https://openalex.org/{author_id}"}).get()

        resultados = []
        for w in trabajos[:n]:
            source = w.get('primary_location', {}).get('source', {})
            revista = source.get('display_name', 'N/A') if source else 'N/A'
            resultados.append({
                "id": w["id"],
                "titulo": w.get("title"),
                "año": w.get("publication_year"),
                "revista": revista,
                "citas": w.get("cited_by_count"),
                "DOI": w.get("doi")
            })
        return json.dumps(resultados, ensure_ascii=False)
    except Exception as e:
        return f"Error recuperando trabajos: {str(e)}"

def getAuthorTopWorksFromOpenAlex(author_id: str, n: int = 5, years: int = 5) -> str:
    """Recupera los 'n' trabajos más citados de un autor en OpenAlex en los últimos 'years' años."""
    try:
        from datetime import datetime
        norm_id = author_id.split("/")[-1]
        start_year = datetime.now().year - years
        top_works = (
            pyalex.Works()
            .filter(author={"id": f"https://openalex.org/{norm_id}"}, publication_year=f">{start_year}")
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
        return f"Error obteniendo trabajos top: {e}"

def searchInstitutionInOpenAlex(name: str) -> str:
    """Busca perfiles de instituciones por nombre en OpenAlex. Devuelve hasta 3 perfiles."""
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

def getInstitutionWorksByYear(institution_id: str) -> str:
    """Agrupa los trabajos de una institución por año de publicación en OpenAlex."""
    try:
        norm_id = institution_id.split("/")[-1]
        grouped_by_year = pyalex.Works().filter(
            authorships={"institutions": {"id": norm_id}}
        ).group_by("publication_year").get()
        
        results = [{"year": group["key"], "works_count": group["count"]} for group in grouped_by_year]
        return json.dumps(sorted(results, key=lambda x: x['year'], reverse=True), ensure_ascii=False)
    except Exception as e:
        return f"Error en la agregación: {e}"

def getAuthorWorksByYear(author_id: str) -> str:
    """Agrupa los trabajos de un autor por año de publicación en OpenAlex."""
    try:
        norm_id = author_id.split("/")[-1]
        grouped_by_year = pyalex.Works().filter(
            author={"id": norm_id}
        ).group_by("publication_year").get()
        
        results = [{"year": group["key"], "works_count": group["count"]} for group in grouped_by_year if group.get("key") is not None]
        return json.dumps(sorted(results, key=lambda x: x['year'], reverse=True), ensure_ascii=False)
    except Exception as e:
        return f"Error en la agregación de trabajos del autor: {e}"

def downloadPaperByDOI(doi: str) -> str:
    """Descarga un PDF de Sci-Hub dado su DOI y lo guarda en la carpeta 'pdf/'. Útil para acceder al texto completo."""
    try:
        from scidownl import scihub_download
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
            return f"Error: No se pudo descargar el paper {doi}."
    except Exception as e:
        return f"Error durante la descarga de Sci-Hub: {e}"


# --- Herramientas de Propósito General (Fase 2) ---

def get_entity_statistics(entity_name: str) -> str:
    """
    Obtiene estadísticas completas de producción científica para una entidad UNAM.
    Retorna: total de papers, total de académicos, top 10 tópicos más frecuentes,
    rango de años de publicación y los 5 papers más citados.
    Usar cuando el usuario pregunte por el perfil o productividad de una institución.
    """
    print(f"📊 Calculando estadísticas para entidad: '{entity_name}'")
    if not NEO4J_AVAILABLE:
        return "Estadísticas de grafo no disponibles: Neo4j no está conectado en este entorno."
    try:
        with neo4j.driver.session() as session:
            # Total papers y académicos
            counts = session.run("""
                MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
                MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
                RETURN count(DISTINCT p) AS total_papers, count(DISTINCT a) AS total_academics,
                       min(p.year) AS year_min, max(p.year) AS year_max
            """, entity=entity_name).single()

            # Top tópicos
            topics = session.run("""
                MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
                MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic)
                RETURN t.name AS topic, count(p) AS papers
                ORDER BY papers DESC LIMIT 10
            """, entity=entity_name).data()

            # Top 5 más citados
            top_cited = session.run("""
                MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
                MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
                WHERE p.citations IS NOT NULL AND p.citations > 0
                RETURN p.title AS title, p.year AS year, p.citations AS citations, coalesce(a.fullname, a.name) AS author
                ORDER BY citations DESC LIMIT 5
            """, entity=entity_name).data()

        if not counts or counts["total_papers"] == 0:
            return f"No se encontraron datos para la entidad '{entity_name}'."

        result = {
            "entidad": entity_name,
            "total_papers": counts["total_papers"],
            "total_académicos": counts["total_academics"],
            "rango_años": f"{counts['year_min']} – {counts['year_max']}",
            "top_tópicos": topics,
            "papers_más_citados": top_cited
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return f"Error calculando estadísticas: {str(e)}"


def get_researcher_profile(name_fragment: str) -> str:
    """
    Recupera el perfil académico completo de un investigador de la UNAM buscando 
    por nombre parcial (apellido o parte del nombre es suficiente).
    Retorna: entidad afiliada, total de papers, top 5 tópicos, coautores principales,
    ORCID, Scopus ID y enlace SIIA.
    Usar cuando el usuario pregunte por un investigador específico.
    """
    print(f"👤 Buscando perfil del investigador: '{name_fragment}'")
    if not NEO4J_AVAILABLE:
        return "Perfil de grafo no disponible: Neo4j no está conectado en este entorno."
    try:
        with neo4j.driver.session() as session:
            # Datos básicos del investigador
            profile = session.run("""
                MATCH (a:Person)-[:AFFILIATED_TO]->(e)
                WHERE (e:Institution OR e:Dependency OR e:Subdependency)
                  AND (toLower(a.fullname) CONTAINS toLower($name) OR toLower(a.name) CONTAINS toLower($name))
                RETURN coalesce(a.fullname, a.name) AS name, a.orcid AS orcid, a.scopus_id AS scopus_id,
                       a.siia_url AS siia_url, e.name AS entity
                LIMIT 3
            """, name=name_fragment).data()

            if not profile:
                return f"No se encontró ningún investigador con '{name_fragment}'. Intenta con el apellido paterno."

            results = []
            for p in profile:
                academic_name = p["name"]

                # Total papers y rango de años
                paper_stats = session.run("""
                    MATCH (a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
                    WHERE coalesce(a.fullname, a.name) = $name
                    RETURN count(p) AS total, min(p.year) AS year_min, max(p.year) AS year_max,
                           sum(p.citations) AS total_citations
                """, name=academic_name).single()

                # Top tópicos
                topics = session.run("""
                    MATCH (a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic)
                    WHERE coalesce(a.fullname, a.name) = $name
                    RETURN t.name AS topic, count(p) AS papers ORDER BY papers DESC LIMIT 5
                """, name=academic_name).data()

                # Top coautores
                coauthors = session.run("""
                    MATCH (a1:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)<-[:AUTHOR_OF|AUTHORED]-(a2:Person)
                    WHERE coalesce(a1.fullname, a1.name) = $name AND a1 <> a2
                    RETURN coalesce(a2.fullname, a2.name) AS coauthor, count(p) AS shared ORDER BY shared DESC LIMIT 5
                """, name=academic_name).data()

                results.append({
                    "nombre": p["name"],
                    "entidad": p["entity"],
                    "orcid": p.get("orcid"),
                    "scopus_id": p.get("scopus_id"),
                    "siia_url": p.get("siia_url"),
                    "total_papers": paper_stats["total"] if paper_stats else 0,
                    "rango_años": f"{paper_stats['year_min']} – {paper_stats['year_max']}" if paper_stats and paper_stats["year_min"] else "N/A",
                    "citas_totales": paper_stats["total_citations"] if paper_stats else 0,
                    "top_tópicos": topics,
                    "coautores_principales": coauthors
                })

        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        return f"Error recuperando perfil: {str(e)}"


def get_trending_topics(entity_name: Optional[str] = None, start_year: int = 2018) -> str:
    """
    Retorna los tópicos de investigación con mayor crecimiento en publicaciones
    desde start_year. Opcionalmente filtrado por entidad UNAM.
    Útil para identificar áreas emergentes o tendencias en producción científica.
    """
    print(f"📈 Calculando tópicos con tendencia desde {start_year}" + (f" para '{entity_name}'" if entity_name else ""))
    if not NEO4J_AVAILABLE:
        return "Tópicos de grafo no disponibles: Neo4j no está conectado en este entorno."
    try:
        with neo4j.driver.session() as session:
            if entity_name:
                query = """
                    MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
                    MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic)
                    WHERE p.year >= $year
                    RETURN t.name AS topic, count(p) AS papers, collect(DISTINCT p.year) AS years
                    ORDER BY papers DESC LIMIT 15
                """
                data = session.run(query, entity=entity_name, year=start_year).data()
            else:
                query = """
                    MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)
                    WHERE p.year >= $year
                    RETURN t.name AS topic, count(p) AS papers, collect(DISTINCT p.year) AS years
                    ORDER BY papers DESC LIMIT 15
                """
                data = session.run(query, year=start_year).data()

        if not data:
            return "No se encontraron datos de tópicos para los filtros indicados."

        return json.dumps({
            "desde_año": start_year,
            "entidad": entity_name or "Todas las entidades",
            "tópicos_tendencia": data
        }, ensure_ascii=False)
    except Exception as e:
        return f"Error calculando tendencias: {str(e)}"



def get_coauthorship_network_for_entity(entity_name: str, start_year: int = 2015, limit_nodes: int = 50) -> str:
    """
    Construye la red de coautoría de TODOS los investigadores de una entidad UNAM.
    Devuelve JSON con `nodes` (autores) y `edges` (colaboraciones) listo para usar con networkx.

    Usa entity_name con el nombre EXACTO de la entidad en el grafo (ej. "Facultad de Ciencias").
    El análisis incluye colaboraciones tanto con otros académicos de la misma entidad como con autores externos.

    Retorna:
    - nodes: lista de {id, name, papers_count, is_internal}
    - edges: lista de {source, target, shared_papers, topics}
    """
    print(f"🕸️ Construyendo red de coautoría para: {entity_name}")
    if not NEO4J_AVAILABLE:
        return "Red de coautoría no disponible: Neo4j no está conectado en este entorno."
    try:
        with neo4j.driver.session() as session:
            # Nodos: autores internos de la entidad con sus papers
            nodes_q = """
            MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND toLower(e.name) CONTAINS toLower($entity)
            MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
            WHERE p.year >= $year
            RETURN coalesce(a.fullname, a.name) AS name, count(DISTINCT p) AS papers_count
            ORDER BY papers_count DESC
            LIMIT $limit
            """
            nodes_raw = session.run(nodes_q, entity=entity_name, year=start_year, limit=limit_nodes).data()
            if not nodes_raw:
                return f"No se encontraron autores para '{entity_name}' desde {start_year}."

            internal_names = {r["name"] for r in nodes_raw}
            nodes = [{"id": r["name"], "name": r["name"], "papers_count": r["papers_count"], "is_internal": True}
                     for r in nodes_raw]

            # Aristas: pares de autores que comparten papers
            edges_q = """
            MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND toLower(e.name) CONTAINS toLower($entity)
            MATCH (e)<-[:AFFILIATED_TO]-(a1:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)<-[:AUTHOR_OF|AUTHORED]-(a2:Person)
            WHERE p.year >= $year AND id(a1) < id(a2)
            RETURN coalesce(a1.fullname, a1.name) AS source, coalesce(a2.fullname, a2.name) AS target,
                   count(DISTINCT p) AS shared_papers,
                   collect(DISTINCT p.year)[..3] AS sample_years
            ORDER BY shared_papers DESC
            LIMIT 200
            """
            edges_raw = session.run(edges_q, entity=entity_name, year=start_year).data()

            # Añadir autores externos como nodos adicionales
            external = {e["target"] for e in edges_raw if e["target"] not in internal_names}
            for ext_name in list(external)[:20]:  # Máx 20 externos para no saturar
                nodes.append({"id": ext_name, "name": ext_name, "papers_count": 0, "is_internal": False})

            result = {
                "entity": entity_name,
                "desde_año": start_year,
                "nodes_count": len(nodes),
                "edges_count": len(edges_raw),
                "nodes": nodes,
                "edges": edges_raw,
            }
            return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        return f"Error construyendo red de coautoría: {str(e)}"


def get_topic_evolution(entity_name: str, start_year: int = 2018, end_year: int = 2024) -> str:
    """
    Retorna la evolución año-a-año de los temas de investigación de una entidad.
    Útil para detectar qué temas están creciendo, estabilizándose o declinando.

    Devuelve tabla con: topic_name, year, paper_count, avg_citations.
    Incluye un campo `trend` con variación porcentual respecto al año anterior.

    Usa entity_name con el nombre EXACTO de la entidad en el grafo.
    """
    print(f"📊 Calculando evolución temática para '{entity_name}' ({start_year}-{end_year})")
    if not NEO4J_AVAILABLE:
        return "Evolución temática no disponible: Neo4j no está conectado en este entorno."
    try:
        with neo4j.driver.session() as session:
            query = """
            MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND toLower(e.name) CONTAINS toLower($entity)
            MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic)
            WHERE p.year >= $start_year AND p.year <= $end_year
            RETURN t.name AS topic, p.year AS year,
                   count(DISTINCT p) AS paper_count,
                   round(avg(coalesce(p.citations, 0)), 2) AS avg_citations
            ORDER BY topic, year
            """
            data = session.run(
                query, entity=entity_name, start_year=start_year, end_year=end_year
            ).data()

        if not data:
            return f"No se encontraron datos temáticos para '{entity_name}' en el rango {start_year}-{end_year}."

        # Calcular tendencia: variación vs año anterior por topic
        from collections import defaultdict
        by_topic = defaultdict(dict)
        for row in data:
            by_topic[row["topic"]][row["year"]] = row["paper_count"]

        enriched = []
        for row in data:
            topic = row["topic"]
            year = row["year"]
            prev = by_topic[topic].get(year - 1)
            if prev and prev > 0:
                trend = round((row["paper_count"] - prev) / prev * 100, 1)
            else:
                trend = None
            enriched.append({**row, "trend_pct_vs_prev_year": trend})

        return json.dumps({
            "entity": entity_name,
            "rango": f"{start_year}-{end_year}",
            "total_registros": len(enriched),
            "data": enriched,
        }, ensure_ascii=False)

    except Exception as e:
        return f"Error calculando evolución temática: {str(e)}"


def get_sdg_distribution(
    entity_name: str,
    start_year: int = 2018,
    end_year: int = 2026
) -> str:
    """
    Distribución de publicaciones por Objetivo de Desarrollo Sostenible (ODS/SDG) para
    una entidad UNAM. Requiere que los nodos :SDG y la relación :CONTRIBUTES_TO estén
    materializados en Neo4j.

    Retorna:
    - Conteo de papers por SDG
    - Evolución temporal (papers por SDG por año)
    - Top 5 investigadores más activos en cada SDG
    - Temas (topics) dominantes por SDG
    """
    if not NEO4J_AVAILABLE:
        return "Distribución SDG no disponible: Neo4j no está conectado en este entorno."
    try:
        graph = Neo4jGraphStore()

        # 1. Distribución global por SDG
        dist_query = """
        MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
        MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)-[:CONTRIBUTES_TO]->(s:SDG)
        WHERE p.year >= $start AND p.year <= $end
        RETURN s.name AS sdg_id,
               s.name AS sdg_name,
               count(DISTINCT p) AS papers,
               count(DISTINCT a) AS researchers,
               avg(COALESCE(toFloat(p.citations), 0)) AS avg_citations
        ORDER BY papers DESC
        """

        # 2. Evolución temporal
        evol_query = """
        MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
        MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)-[:CONTRIBUTES_TO]->(s:SDG)
        WHERE p.year >= $start AND p.year <= $end
        RETURN s.name AS sdg_id, s.name AS sdg_name, p.year AS year,
               count(DISTINCT p) AS papers
        ORDER BY s.name, p.year
        """

        # 3. Top investigadores por SDG
        top_query = """
        MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
        MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)-[:CONTRIBUTES_TO]->(s:SDG)
        WHERE p.year >= $start AND p.year <= $end
        RETURN s.name AS sdg_id, coalesce(a.fullname, a.name) AS researcher, count(DISTINCT p) AS papers
        ORDER BY s.name, papers DESC
        """

        params = {"entity": entity_name, "start": start_year, "end": end_year}

        with graph.driver.session() as session:
            dist_rows   = [dict(r) for r in session.run(dist_query,   **params)]
            evol_rows   = [dict(r) for r in session.run(evol_query,   **params)]
            top_rows    = [dict(r) for r in session.run(top_query,    **params)]

        graph.close()

        if not dist_rows:
            return json.dumps({
                "entity": entity_name,
                "mensaje": "No se encontraron relaciones :CONTRIBUTES_TO con nodos :SDG.",
                "distribucion": []
            }, ensure_ascii=False)

        # Agrupar top investigadores por SDG
        from collections import defaultdict
        top_by_sdg: dict = defaultdict(list)
        for r in top_rows:
            if len(top_by_sdg[r["sdg_id"]]) < 5:
                top_by_sdg[r["sdg_id"]].append(
                    {"researcher": r["researcher"], "papers": r["papers"]}
                )

        # Agrupar evolución por SDG
        evol_by_sdg: dict = defaultdict(list)
        for r in evol_rows:
            evol_by_sdg[r["sdg_id"]].append({"year": r["year"], "papers": r["papers"]})

        # Ensamblar resultado
        distribucion = []
        for row in dist_rows:
            sid = row["sdg_id"]
            distribucion.append({
                "sdg_id":        sid,
                "sdg_name":      row["sdg_name"],
                "papers":        row["papers"],
                "researchers":   row["researchers"],
                "avg_citations": round(float(row["avg_citations"] or 0), 2),
                "top_researchers": top_by_sdg.get(sid, []),
                "evolucion":       evol_by_sdg.get(sid, []),
            })

        return json.dumps({
            "entity":   entity_name,
            "rango":    f"{start_year}-{end_year}",
            "total_sdgs_con_papers": len(distribucion),
            "distribucion": distribucion,
        }, ensure_ascii=False)

    except Exception as e:
        return f"Error en get_sdg_distribution: {str(e)}"


def get_international_collaboration_stats(
    entity_name: str,
    start_year: int = 2015,
    end_year: int = 2026,
) -> str:
    """
    Estadísticas de colaboración internacional de una entidad UNAM.

    Retorna:
    - Top 30 países colaboradores (papers conjuntos, número de coautores)
    - Evolución temporal de la colaboración internacional (papers por año)
    - % papers con colaboración internacional
    - Top investigadores más activos en colaboración internacional

    Funciona en dos modos:
    1. Modo grafo: usa nodos :Person con country_code
    2. Modo fallback: lee campo `countries` de raw_metadata al nivel del paper
    """
    if not NEO4J_AVAILABLE:
        return "Colaboración internacional no disponible: Neo4j no está conectado en este entorno."
    try:
        graph = Neo4jGraphStore()
        params = {"entity": entity_name, "start": start_year, "end": end_year}

        with graph.driver.session() as session:
            # Detectar si los :Person externos tienen country_code
            probe = session.run(
                "MATCH (a:Person) WHERE a.country_code IS NOT NULL AND NOT (a)-[:AFFILIATED_TO]->(:Institution|Dependency|Subdependency) "
                "RETURN count(a) AS n LIMIT 1"
            )
            has_country_code = (probe.single()["n"] > 0)

        if has_country_code:
            # ── Modo grafo (datos de :Person enriquecidos) ──────────────────────
            top_q = """
            MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
            MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)<-[:AUTHOR_OF|AUTHORED]-(ext:Person)
            WHERE ext.country_code IS NOT NULL
              AND NOT (ext)-[:AFFILIATED_TO]->(:Institution|Dependency|Subdependency)
              AND p.year >= $start AND p.year <= $end
            RETURN ext.country_code AS country,
                   count(DISTINCT p) AS papers,
                   count(DISTINCT ext) AS coauthors,
                   collect(DISTINCT coalesce(a.fullname, a.name))[..5] AS researchers
            ORDER BY papers DESC LIMIT 30
            """
            evol_q = """
            MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
            MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)<-[:AUTHOR_OF|AUTHORED]-(ext:Person)
            WHERE ext.country_code IS NOT NULL
              AND NOT (ext)-[:AFFILIATED_TO]->(:Institution|Dependency|Subdependency)
              AND p.year >= $start AND p.year <= $end
            RETURN p.year AS year, count(DISTINCT p) AS intl_papers
            ORDER BY year
            """
            total_q = """
            MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
            MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
            WHERE p.year >= $start AND p.year <= $end
            RETURN count(DISTINCT p) AS total
            """
            intl_q = """
            MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
            MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)<-[:AUTHOR_OF|AUTHORED]-(ext:Person)
            WHERE ext.country_code IS NOT NULL
              AND NOT (ext)-[:AFFILIATED_TO]->(:Institution|Dependency|Subdependency)
              AND p.year >= $start AND p.year <= $end
            RETURN count(DISTINCT p) AS intl_papers
            """
            with graph.driver.session() as session:
                top_rows  = [dict(r) for r in session.run(top_q,  **params)]
                evol_rows = [dict(r) for r in session.run(evol_q, **params)]
                total     = session.run(total_q, **params).single()["total"]
                intl      = session.run(intl_q,  **params).single()["intl_papers"]
            mode = "graph"

        else:
            # ── Modo fallback (campo 'countries' en raw_metadata del paper) ─────
            raw_q = """
            MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity
            MATCH (e)<-[:AFFILIATED_TO]-(a:Person)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
            WHERE p.raw_metadata IS NOT NULL
              AND p.year >= $start AND p.year <= $end
            RETURN p.id AS doi, p.year AS year, coalesce(a.fullname, a.name) AS researcher,
                   p.raw_metadata AS meta
            """
            import json, ast
            from collections import Counter

            with graph.driver.session() as session:
                raw_rows = [dict(r) for r in session.run(raw_q, **params)]

            country_papers: dict  = {}   # country → set of dois
            country_researchers: dict = {}  # country → set of researchers
            evol_map: dict = {}           # year → set of intl dois
            total = len({r["doi"] for r in raw_rows})
            intl_dois: set = set()

            for r in raw_rows:
                try:
                    meta = json.loads(r["meta"]) if isinstance(r["meta"], str) else r["meta"]
                except Exception:
                    try:
                        meta = ast.literal_eval(r["meta"])
                    except Exception:
                        meta = {}
                countries = meta.get("countries", []) or []
                if len(countries) >= 2 or (countries and "MX" not in countries):
                    intl_dois.add(r["doi"])
                    y = int(r["year"])
                    evol_map.setdefault(y, set()).add(r["doi"])
                    for c in countries:
                        if c and c != "MX":
                            country_papers.setdefault(c, set()).add(r["doi"])
                            country_researchers.setdefault(c, set()).add(r["researcher"])

            top_rows = sorted(
                [{"country": c, "papers": len(dois),
                  "coauthors": len(country_researchers.get(c, set())),
                  "researchers": list(country_researchers.get(c, set()))[:5]}
                 for c, dois in country_papers.items()],
                key=lambda x: -x["papers"]
            )[:30]
            evol_rows = [{"year": y, "intl_papers": len(dois)}
                         for y, dois in sorted(evol_map.items())]
            intl = len(intl_dois)
            mode = "fallback (paper-level countries)"

        graph.close()

        pct_intl = round(intl / max(total, 1) * 100, 1)

        return json.dumps({
            "entity":          entity_name,
            "rango":           f"{start_year}-{end_year}",
            "modo":            mode,
            "total_papers":    total,
            "intl_papers":     intl,
            "pct_internacional": pct_intl,
            "top_paises":      top_rows,
            "evolucion_temporal": evol_rows,
        }, ensure_ascii=False)

    except Exception as e:
        return f"Error en get_international_collaboration_stats: {str(e)}"


# --- Dualidad: Funciones Callables y Herramientas LangChain ---

class CallableTool:
    """
    Envoltorio que permite que un objeto se comporte como una función normal
    (para el Interpreter Agent) pero también tenga los métodos de LangChain
    como .invoke() y .run() (para el Multi-Agente).
    """
    def __init__(self, langchain_tool, original_func):
        self.tool = langchain_tool
        self.original_func = original_func
        self.__doc__ = original_func.__doc__
        self.__name__ = original_func.__name__

    def __call__(self, *args, **kwargs):
        return self.original_func(*args, **kwargs)

    def invoke(self, *args, **kwargs):
        # LangChain tools .invoke suele recibir un dict o args
        return self.tool.invoke(*args, **kwargs)

    def run(self, *args, **kwargs):
        return self.tool.run(*args, **kwargs)
        
    @property
    def args(self):
        return self.tool.args

# Envolvemos las funciones para que funcionen en ambos mundos
search_scientific_papers_semantic = CallableTool(tool(search_scientific_papers_semantic), search_scientific_papers_semantic)
get_author_coauthors_graph = CallableTool(tool(get_author_coauthors_graph), get_author_coauthors_graph)
get_coauthorship_network_for_entity = CallableTool(tool(get_coauthorship_network_for_entity), get_coauthorship_network_for_entity)
query_knowledge_graph_cypher = CallableTool(tool(query_knowledge_graph_cypher), query_knowledge_graph_cypher)
get_entity_statistics = CallableTool(tool(get_entity_statistics), get_entity_statistics)
get_researcher_profile = CallableTool(tool(get_researcher_profile), get_researcher_profile)
get_trending_topics = CallableTool(tool(get_trending_topics), get_trending_topics)
get_topic_evolution = CallableTool(tool(get_topic_evolution), get_topic_evolution)
get_sdg_distribution = CallableTool(tool(get_sdg_distribution), get_sdg_distribution)
get_international_collaboration_stats = CallableTool(tool(get_international_collaboration_stats), get_international_collaboration_stats)
web_search = CallableTool(tool(web_search), web_search)
wikipedia_search = CallableTool(tool(wikipedia_search), wikipedia_search)
recoverFromOpenAlex = CallableTool(tool(recoverFromOpenAlex), recoverFromOpenAlex)
searchAuthorInOpenAlex = CallableTool(tool(searchAuthorInOpenAlex), searchAuthorInOpenAlex)
recoverAuthorWorksFromOpenAlex = CallableTool(tool(recoverAuthorWorksFromOpenAlex), recoverAuthorWorksFromOpenAlex)
getAuthorTopWorksFromOpenAlex = CallableTool(tool(getAuthorTopWorksFromOpenAlex), getAuthorTopWorksFromOpenAlex)
searchInstitutionInOpenAlex = CallableTool(tool(searchInstitutionInOpenAlex), searchInstitutionInOpenAlex)
getInstitutionWorksByYear = CallableTool(tool(getInstitutionWorksByYear), getInstitutionWorksByYear)
getAuthorWorksByYear = CallableTool(tool(getAuthorWorksByYear), getAuthorWorksByYear)
downloadPaperByDOI = CallableTool(tool(downloadPaperByDOI), downloadPaperByDOI)

# Alias para compatibilidad con el prompt del agente
search_scientific_papers = search_scientific_papers_semantic

# Lista de herramientas híbridas para exportar (RAGOrchestrator)
# Las herramientas de Neo4j y Qdrant solo se incluyen si sus servicios están disponibles
_neo4j_tools = [
    get_author_coauthors_graph.tool,
    get_coauthorship_network_for_entity.tool,
    query_knowledge_graph_cypher.tool,
    get_entity_statistics.tool,
    get_researcher_profile.tool,
    get_trending_topics.tool,
    get_topic_evolution.tool,
    get_sdg_distribution.tool,
    get_international_collaboration_stats.tool,
] if NEO4J_AVAILABLE else []

_qdrant_tools = [
    search_scientific_papers_semantic.tool,
] if QDRANT_AVAILABLE else []

_base_tools = [
    web_search.tool,
    wikipedia_search.tool,
    recoverFromOpenAlex.tool,
    searchAuthorInOpenAlex.tool,
    recoverAuthorWorksFromOpenAlex.tool,
    getAuthorTopWorksFromOpenAlex.tool,
    searchInstitutionInOpenAlex.tool,
    getInstitutionWorksByYear.tool,
    getAuthorWorksByYear.tool,
    downloadPaperByDOI.tool
]

hybrid_tools = _neo4j_tools + _qdrant_tools + _base_tools

# Herramientas estrictamente MCP (solo Web/Wikipedia/OpenAlex/SciHub)
# Estas se usarán para el Agente Reactivo
mcp_tools = [
    web_search.tool,
    wikipedia_search.tool,
    recoverFromOpenAlex.tool,
    searchAuthorInOpenAlex.tool,
    recoverAuthorWorksFromOpenAlex.tool,
    getAuthorTopWorksFromOpenAlex.tool,
    searchInstitutionInOpenAlex.tool,
    getInstitutionWorksByYear.tool,
    getAuthorWorksByYear.tool,
    downloadPaperByDOI.tool
]
