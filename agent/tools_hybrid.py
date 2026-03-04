import json
import os
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
def search_scientific_papers_semantic(query: str, limit: int = 20, entity_context: Optional[str] = None) -> str:
    """
    Realiza una búsqueda semántica en la base de datos vectorial (Qdrant).
    Útil para encontrar temas relacionados, conceptos abstractos o papers que hablen
    de algo aunque no compartan palabras clave exactas.

    Las colecciones disponibles en Qdrant son EXACTAMENTE dos:
    - `scientific_papers`: papers académicos (la principal).
    - `api_papers`: papers obtenidos de APIs externas.
    NO existe ninguna otra colección. Esta herramienta busca en ambas automáticamente.

    IMPORTANTE: La query debe contener ÚNICAMENTE el tema científico o concepto buscado.
    NUNCA incluyas el nombre de la institución en la query semántica — eso degrada los resultados.
    - CORRECTO: query="diabetes"
    - INCORRECTO: query="Instituto de Investigaciones Nucleares diabetes"

    Usa el parámetro entity_context para filtrar por institución de forma nativa y eficiente.
    Ejemplo: entity_context="Instituto de Investigaciones Nucleares"

    La query puede estar en español o inglés — se traducirá automáticamente al inglés.
    """
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
        return json.dumps(output, ensure_ascii=False)
    except Exception as e:
        return f"Error en búsqueda semántica: {str(e)}"

@tool
def get_author_coauthors_graph(author_name: str) -> str:
    """
    Consulta el Grafo de Conocimiento (Neo4j) para encontrar coautores de un investigador.
    Ústil para mapear redes de colaboración y líneas de investigación compartidas.
    Usa búsqueda parcial: proporciona solo el apellido o parte del nombre.
    """
    print(f"✨️ Consultando grafo de coautoría para: '{author_name}'")
    with neo4j.driver.session() as session:
        result = session.run(
            "MATCH (a1:Author)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(a2:Author) "
            "WHERE toLower(a1.name) CONTAINS toLower($name) AND a1 <> a2 "
            "RETURN DISTINCT a2.name AS coauthor, count(p) AS shared_papers "
            "ORDER BY shared_papers DESC LIMIT 20",
            name=author_name
        )
        coauthors = [{"coauthor": r["coauthor"], "shared_papers": r["shared_papers"]} for r in result]
    
    if not coauthors:
        return f"No se encontró información de coautores para '{author_name}'. Verifica que el apellido esté correcto."
        
    return json.dumps({"author_query": author_name, "coauthors": coauthors}, ensure_ascii=False)

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
    - Filtrar por entidad y tópico exacto: `MATCH (e:Entity {name: 'Instituto de Investigaciones Nucleares'})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic) WHERE toLower(t.name) CONTAINS 'microscopy' RETURN p.title, a.name, p.year ORDER BY p.year DESC LIMIT 20`
    - Filtrar papers por entidad (sin tópico): `MATCH (e:Entity)<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper) WHERE toLower(e.name) CONTAINS 'ciencias' AND p.year >= 2018 RETURN p.doi, p.title, p.year, p.citations ORDER BY p.year DESC LIMIT 20`
    - Filtrar por tópico AMPLIO (usa OR para cubrir variantes): `WHERE toLower(t.name) CONTAINS 'diabetes' OR toLower(t.name) CONTAINS 'insulin' OR toLower(t.name) CONTAINS 'metabolic'`
    - Búsqueda por nombre de persona (usa CONTAINS, NUNCA match exacto):
      `MATCH (a:Author)-[:AUTHORED]->(p:Paper) WHERE toLower(a.name) CONTAINS toLower('alcubierre') RETURN p.title, a.name, p.year ORDER BY p.year DESC LIMIT 20`
      RAZÓN: Los nombres están almacenados en formato 'APELLIDO PATERNO, NOMBRE' en MAYÚSCULAS (ej. 'ALCUBIERRE MOYA, MIGUEL'). Un match exacto con el nombre coloquial SIEMPRE fallará.
    
    ❌ ERRORES PROHIBIDOS — NUNCA hagas esto:
    - NO uses parámetros Cypher ($variable). Esta herramienta NO acepta un dict de params separado. Incrusta los valores directamente en el string de la query. INCORRECTO: `WHERE a.id IN $ids`. CORRECTO: `WHERE a.id IN ['id1','id2']`
    - NO uses `(p:Paper)-[:AFFILIATED_TO]->(:Institution)`. Los Papers NO tienen relación AFFILIATED_TO. La afiliación es SIEMPRE a través del académico: `(a:Academic)-[:AFFILIATED_TO]->(e:Entity)`.
    - NO uses `EXISTS()` con patrones complejos. Usa `MATCH` directos.
    - Para SDGs usa `(p:Paper)-[:ADDRESSES]->(s:SDG)`. La relación se llama :ADDRESSES, no :RELEVANT_TO.
      Ejemplo: `MATCH (p:Paper)-[:ADDRESSES]->(s:SDG) RETURN s.id, s.name, count(p) AS papers ORDER BY papers DESC`

    
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


# --- Herramientas de Propósito General (Fase 2) ---

@tool
def get_entity_statistics(entity_name: str) -> str:
    """
    Obtiene estadísticas completas de producción científica para una entidad UNAM.
    Retorna: total de papers, total de académicos, top 10 tópicos más frecuentes,
    rango de años de publicación y los 5 papers más citados.
    Usar cuando el usuario pregunte por el perfil o productividad de una institución.
    """
    print(f"📊 Calculando estadísticas para entidad: '{entity_name}'")
    try:
        with neo4j.driver.session() as session:
            # Total papers y académicos
            counts = session.run("""
                MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)
                RETURN count(DISTINCT p) AS total_papers, count(DISTINCT a) AS total_academics,
                       min(p.year) AS year_min, max(p.year) AS year_max
            """, entity=entity_name).single()

            # Top tópicos
            topics = session.run("""
                MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic)
                RETURN t.name AS topic, count(p) AS papers
                ORDER BY papers DESC LIMIT 10
            """, entity=entity_name).data()

            # Top 5 más citados
            top_cited = session.run("""
                MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)
                WHERE p.citations IS NOT NULL AND p.citations > 0
                RETURN p.title AS title, p.year AS year, p.citations AS citations, a.name AS author
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


@tool
def get_researcher_profile(name_fragment: str) -> str:
    """
    Recupera el perfil académico completo de un investigador de la UNAM buscando 
    por nombre parcial (apellido o parte del nombre es suficiente).
    Retorna: entidad afiliada, total de papers, top 5 tópicos, coautores principales,
    ORCID, Scopus ID y enlace SIIA.
    Usar cuando el usuario pregunte por un investigador específico.
    """
    print(f"👤 Buscando perfil del investigador: '{name_fragment}'")
    try:
        with neo4j.driver.session() as session:
            # Datos básicos del investigador
            profile = session.run("""
                MATCH (a:Academic)-[:AFFILIATED_TO]->(e:Entity)
                WHERE toLower(a.name) CONTAINS toLower($name)
                RETURN a.name AS name, a.orcid AS orcid, a.scopus_id AS scopus_id,
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
                    MATCH (a:Academic {name: $name})-[:AUTHORED]->(p:Paper)
                    RETURN count(p) AS total, min(p.year) AS year_min, max(p.year) AS year_max,
                           sum(p.citations) AS total_citations
                """, name=academic_name).single()

                # Top tópicos
                topics = session.run("""
                    MATCH (a:Academic {name: $name})-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic)
                    RETURN t.name AS topic, count(p) AS papers ORDER BY papers DESC LIMIT 5
                """, name=academic_name).data()

                # Top coautores
                coauthors = session.run("""
                    MATCH (a1:Author)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(a2:Author)
                    WHERE a1.name = $name AND a1 <> a2
                    RETURN a2.name AS coauthor, count(p) AS shared ORDER BY shared DESC LIMIT 5
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


@tool
def get_trending_topics(entity_name: Optional[str] = None, start_year: int = 2018) -> str:
    """
    Retorna los tópicos de investigación con mayor crecimiento en publicaciones
    desde start_year. Opcionalmente filtrado por entidad UNAM.
    Útil para identificar áreas emergentes o tendencias en producción científica.
    """
    print(f"📈 Calculando tópicos con tendencia desde {start_year}" + (f" para '{entity_name}'" if entity_name else ""))
    try:
        with neo4j.driver.session() as session:
            if entity_name:
                query = """
                    MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic)
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



@tool
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
    try:
        with neo4j.driver.session() as session:
            # Nodos: autores internos de la entidad con sus papers
            nodes_q = """
            MATCH (e:Entity)<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)
            WHERE toLower(e.name) CONTAINS toLower($entity) AND p.year >= $year
            RETURN a.name AS name, count(DISTINCT p) AS papers_count
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
            MATCH (e:Entity)<-[:AFFILIATED_TO]-(a1:Academic)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(a2:Author)
            WHERE toLower(e.name) CONTAINS toLower($entity) AND p.year >= $year
              AND id(a1) < id(a2)
            RETURN a1.name AS source, a2.name AS target,
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


@tool
def get_topic_evolution(entity_name: str, start_year: int = 2018, end_year: int = 2024) -> str:
    """
    Retorna la evolución año-a-año de los temas de investigación de una entidad.
    Útil para detectar qué temas están creciendo, estabilizándose o declinando.

    Devuelve tabla con: topic_name, year, paper_count, avg_citations.
    Incluye un campo `trend` con variación porcentual respecto al año anterior.

    Usa entity_name con el nombre EXACTO de la entidad en el grafo.
    """
    print(f"📊 Calculando evolución temática para '{entity_name}' ({start_year}-{end_year})")
    try:
        with neo4j.driver.session() as session:
            query = """
            MATCH (e:Entity)<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic)
            WHERE toLower(e.name) CONTAINS toLower($entity)
              AND p.year >= $start_year AND p.year <= $end_year
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


@tool
def get_sdg_distribution(
    entity_name: str,
    start_year: int = 2018,
    end_year: int = 2026
) -> str:
    """
    Distribución de publicaciones por Objetivo de Desarrollo Sostenible (ODS/SDG) para
    una entidad UNAM. Requiere que los nodos :SDG y la relación :ADDRESSES estén
    materializados en Neo4j (usar ingest_sdg.py o materialize_sdg_relations.py).

    Retorna:
    - Conteo de papers por SDG
    - Evolución temporal (papers por SDG por año)
    - Top 5 investigadores más activos en cada SDG
    - Temas (topics) dominantes por SDG
    """
    try:
        graph = Neo4jGraphStore()

        # 1. Distribución global por SDG
        dist_query = """
        MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)
              -[:ADDRESSES]->(s:SDG)
        WHERE p.year >= $start AND p.year <= $end
        RETURN s.id AS sdg_id,
               s.name AS sdg_name,
               count(DISTINCT p) AS papers,
               count(DISTINCT a) AS researchers,
               avg(COALESCE(toFloat(p.citations), 0)) AS avg_citations
        ORDER BY papers DESC
        """

        # 2. Evolución temporal
        evol_query = """
        MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)
              -[:ADDRESSES]->(s:SDG)
        WHERE p.year >= $start AND p.year <= $end
        RETURN s.id AS sdg_id, s.name AS sdg_name, p.year AS year,
               count(DISTINCT p) AS papers
        ORDER BY s.id, p.year
        """

        # 3. Top investigadores por SDG
        top_query = """
        MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)
              -[:ADDRESSES]->(s:SDG)
        WHERE p.year >= $start AND p.year <= $end
        RETURN s.id AS sdg_id, a.name AS researcher, count(DISTINCT p) AS papers
        ORDER BY s.id, papers DESC
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
                "mensaje": "No se encontraron relaciones :ADDRESSES con nodos :SDG. "
                           "Ejecuta ingest_sdg.py o materialize_sdg_relations.py primero.",
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


# Lista de herramientas híbridas para exportar
hybrid_tools = [
    search_scientific_papers_semantic,
    get_author_coauthors_graph,
    get_coauthorship_network_for_entity,
    query_knowledge_graph_cypher,
    get_entity_statistics,
    get_researcher_profile,
    get_trending_topics,
    get_topic_evolution,
    get_sdg_distribution,
    web_search,
    wikipedia_search,
    recoverFromOpenAlex,        # Consolida recoverFromOpenAlex + recoverFieldFromRecordFromOpenAlex
    searchAuthorInOpenAlex,
    recoverAuthorWorksFromOpenAlex
]
