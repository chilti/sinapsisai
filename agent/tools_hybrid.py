from langchain_core.tools import tool
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from langchain_openai import OpenAIEmbeddings
from langdetect import detect, LangDetectException
import json
import os
import httpx
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
embeddings_model = OpenAIEmbeddings(
    model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
    base_url=auth_url,
    api_key="lm-studio",
    http_client=sync_client,
    http_async_client=async_client
)

@tool
def search_scientific_papers_semantic(query: str, limit: int = 5) -> str:
    """
    Realiza una búsqueda semántica en la base de datos vectorial (Qdrant).
    Útil para encontrar temas relacionados, conceptos abstractos o papers que hablen 
    de algo aunque no compartan palabras clave exactas.
    La query puede estar en español o inglés — se traducirá automáticamente.
    """
    # Traducir al inglés si es necesario (los papers están en inglés)
    query_en = translate_to_english(query)
    print(f"🔍 Búsqueda semántica en Qdrant (Híbrida) para: '{query_en}'")
    try:
        query_vector = embeddings_model.embed_query(query_en)
        
        # Consultar ambas colecciones
        results_docs = qdrant_docs.search(query_vector, limit=limit)
        results_apis = qdrant_apis.search(query_vector, limit=limit)
        
        # Combinar y ordenar por los de mayor relevancia
        all_results = sorted(results_docs + results_apis, key=lambda x: x.get("score", 0), reverse=True)
        top_results = all_results[:limit]
        
        if not top_results:
            return "No se encontraron resultados semánticos."
            
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
    
    REGLA: Usa esta herramienta solo si sabes construir la consulta Cypher sobre los nodos:
    Paper (id, title, doi, year, citations), Author (id, name), Concept (id, name), Institution (id, name).
    Las relaciones son: (Author)-[:AUTHORED]->(Paper), (Author)-[:AFFILIATED_WITH]->(Institution), (Paper)-[:HAS_CONCEPT]->(Concept).
    """
    print(f"🕸️ Ejecutando Cypher en Neo4j: {cypher_query}")
    try:
        with neo4j.driver.session() as session:
            result = session.run(cypher_query)
            data = [record.data() for record in result]
            return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return f"Error ejecutando Cypher: {str(e)}"

# Lista de herramientas híbridas para exportar
hybrid_tools = [
    search_scientific_papers_semantic,
    get_author_coauthors_graph,
    query_knowledge_graph_cypher
]
