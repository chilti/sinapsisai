import json
import os
import httpx
import pyalex
from pyalex import Works, Authors
from langchain_community.tools import DuckDuckGoSearchRun, WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain_core.tools import tool
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from langdetect import detect, LangDetectException
from dotenv import load_dotenv

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

# Inicialización de las conexiones
qdrant_docs = QdrantStore(collection_name="scientific_papers")
qdrant_apis = QdrantStore(collection_name="api_papers")
neo4j = Neo4jGraphStore()

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

@tool
def search_scientific_papers_semantic(query: str, limit: int = 20) -> str:
    """
    Realiza una búsqueda semántica en la base de datos vectorial (Qdrant).
    Útil para encontrar temas relacionados, conceptos abstractos o papers que hablen 
    de algo aunque no compartan palabras clave exactas.
    La query puede estar en español o inglés — se traducirá automáticamente.
    """
    # Traducir al inglés si es necesario (los papers están en inglés)
    query_en = translate_to_english(query)
    
    if not query_en or not query_en.strip():
        return "La consulta está vacía o no pudo ser procesada."

    print(f"🔍 Búsqueda semántica en Qdrant (Híbrida) para: '{query_en}'")
    try:
        # Llamada manual al embedding para control total del payload
        query_vector = get_embedding(query_en)
        
        if not query_vector:
            return "Error: No se pudo generar el vector de búsqueda (resultado vacío)."
        
        # Consultar ambas colecciones
        results_docs = qdrant_docs.search(query_vector, limit=limit)
        results_apis = qdrant_apis.search(query_vector, limit=limit)
        
        # Combinar y ordenar por los de mayor relevancia
        all_results = sorted(results_docs + results_apis, key=lambda x: x.get("score", 0), reverse=True)
        top_results = all_results[:limit]
        
        # Enriquecer con afiliación si falta (para que el orquestador pueda filtrar)
        for res in top_results:
            if 'entity' not in res:
                author_name = res.get('academic_name')
                if author_name:
                    try:
                        with neo4j.driver.session() as session:
                            aff_query = "MATCH (a:Author)-[:AFFILIATED_TO]->(e:Entity) WHERE toLower(a.name) CONTAINS toLower($name) RETURN e.name LIMIT 1"
                            aff_result = session.run(aff_query, name=author_name).single()
                            if aff_result:
                                res['entity'] = aff_result["e.name"]
                    except:
                        pass
        
        if not top_results:
            return f"No se encontraron resultados semánticos para '{query_en}'."
            
        return json.dumps(top_results, ensure_ascii=False)
    except Exception as e:
        return f"Error en búsqueda semántica: {str(e)}"

@tool
def get_author_coauthors_graph(author_name: str) -> str:
    """
    Consulta el Grafo de Conocimiento (Neo4j) para encontrar coautores de un investigador.
    Útil para mapear redes de colaboración y líneas de investigación compartidas.
    """
    print(f"🕸️ Consultando grafo de coautoría para: '{author_name}'")
    coauthors = neo4j.get_author_coauthors(author_name)
    
    if not coauthors:
        return f"No se encontró información de coautores para {author_name} en el grafo."
        
    return json.dumps({"author": author_name, "coauthors": coauthors}, ensure_ascii=False)

@tool
def query_knowledge_graph_cypher(cypher_query: str) -> str:
    """
    Ejecuta una consulta Cypher directa sobre el Grafo de Conocimiento (Neo4j).
    Útil para preguntas complejas sobre relaciones, como: '¿Qué autores han colaborado 
    con X y también han publicado sobre el concepto Y?', o '¿Cuál es la evolución de citas de este grupo?'.
    
    REGLA: El esquema real de la base de datos usa etiquetas universales:
    - Autores externos: etiqueta `(a:Author)`. Atributos: `id`, `name`.
    - Académicos UNAM: etiqueta múltiple `(a:Academic:Author)`. Atributos: `id`, `name`, `orcid`, `scopus_id`, `siia_url`.
    - Artículos: etiqueta genérica `(p:Paper)`. Atributos: `doi`, `title`, `year`, `citations`.
    - Entidades UNAM: etiqueta múltiple `(e:Entity:Institution)`. Atributos: `name`.
    - Tópicos Temáticos: `(t:Topic)`. Atributos: `id` (slug en inglés), `name` (nombre en inglés).
    
    RELACIONES IMPORTANTES PRECISAS:
    - Publicación: `(a:Author)-[:AUTHORED]->(p:Paper)`
    - Afiliación: `(a:Academic)-[:AFFILIATED_TO]->(e:Entity)`
    - Tópicos: `(p:Paper)-[:HAS_TOPIC]->(t:Topic)`. **IMPORTANTE: Los tópicos están en INGLÉS**. Traduce siempre los términos de búsqueda (ej. de "microscopía" a "microscopy") antes de filtrar `t.name`.
    
    PATRONES DE CONSULTA RECOMENDADOS (SINTAXIS CORRECTA):
    - Filtrar por entidad y tópico exacto: `MATCH (e:Entity {name: 'Instituto de Ciencias Nucleares'})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic) WHERE toLower(t.name) CONTAINS 'microscopy' RETURN p.title, a.name, p.year ORDER BY p.year DESC LIMIT 20`
    - Filtrar por tópico AMPLIO (usa OR para cubrir variantes): `WHERE toLower(t.name) CONTAINS 'diabetes' OR toLower(t.name) CONTAINS 'insulin' OR toLower(t.name) CONTAINS 'metabolic'`
    - Búsqueda parcial de nombres: `WHERE toLower(a.name) CONTAINS toLower('Bucio Carrillo')`
    
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

@tool
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

@tool
def wikipedia_search(query: str) -> str:
    """
    Consulta Wikipedia para obtener resúmenes informativos sobre conceptos, 
    instituciones o personajes científicos.
    """
    return wikipedia_tool_instance.run(query)

# --- Herramientas OpenAlex (Recuperación Directa) ---

@tool
def recoverFromOpenAlex(doi: str) -> str:
    """Recupera por DOI el registro bibliográfico completo y algunos indicadores del documento desde OpenAlex."""
    try:
        # Normalizar DOI
        clean_doi = doi.replace("https://doi.org/", "").strip()
        work = Works()[f"https://doi.org/{clean_doi}"]
        return json.dumps(work, ensure_ascii=False)
    except Exception as e:
        return f"Error recuperando DOI {doi}: {str(e)}"

@tool
def recoverFieldFromRecordFromOpenAlex(doi: str, key: str) -> str:
    """
    Recupera un campo específico de un registro de OpenAlex usando el DOI.
    Keys útiles: 'fwci', 'cited_by_count', 'topics', 'concepts', 'sustainable_development_goals', 'abstract_inverted_index'.
    """
    try:
        clean_doi = doi.replace("https://doi.org/", "").strip()
        work = Works()[f"https://doi.org/{clean_doi}"]
        if key in work:
            return json.dumps(work.get(key), ensure_ascii=False)
        return f"Campo '{key}' no encontrado en el registro."
    except Exception as e:
        return f"Error: {str(e)}"

@tool
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

@tool
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

# Lista de herramientas híbridas para exportar
hybrid_tools = [
    search_scientific_papers_semantic,
    get_author_coauthors_graph,
    query_knowledge_graph_cypher,
    web_search,
    wikipedia_search,
    recoverFromOpenAlex,
    recoverFieldFromRecordFromOpenAlex,
    searchAuthorInOpenAlex,
    recoverAuthorWorksFromOpenAlex
]
