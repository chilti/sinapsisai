# Plan de Consenso Bibliométrico

**Entidad**: Instituto de Ciencias Nucleares
**Fecha**: 2026-03-03

---

### user
Diseñen un **Plan de Estudio Bibliométrico** para **Instituto de Ciencias Nucleares** (UNAM).

**Objetivo del estudio**: Analizar los frentes de investigación en el periodo reciente

## Estado actual de las bases de datos

### Neo4j
> ⚠️ No se pudo conectar: No module named 'database.graph_store'
Esquema esperado: `:Paper`, `:Academic`, `:Topic`, `:Entity`, `:Journal`
Relaciones: `:AUTHORED`, `:HAS_TOPIC`, `:PUBLISHED_IN`, `:AFFILIATED_TO`, `:CITES`

### Qdrant (Búsqueda Semántica)
- **`scientific_papers`**: 22,482 vectores | payload: `paper_id`, `title`, `year`, `doi`, `text`
- **`api_papers`**: 12,419 vectores | payload: `academic_name`, `doi`, `title`, `year`, `source`, `text`

> ✅ Usa `search_scientific_papers_semantic` con `entity_context` para búsquedas por significado en Qdrant.

**Herramientas disponibles para el análisis**:
## Herramientas disponibles en SINAPSIS (únicas válidas)

- **`search_scientific_papers_semantic`**: Realiza una búsqueda semántica en la base de datos vectorial (Qdrant).
- **`get_author_coauthors_graph`**: Consulta el Grafo de Conocimiento (Neo4j) para encontrar coautores de un investigador.
- **`query_knowledge_graph_cypher`**: Ejecuta una consulta Cypher directa sobre el Grafo de Conocimiento (Neo4j).
- **`get_entity_statistics`**: Obtiene estadísticas completas de producción científica para una entidad UNAM.
- **`get_researcher_profile`**: Recupera el perfil académico completo de un investigador de la UNAM buscando
- **`get_trending_topics`**: Retorna los tópicos de investigación con mayor crecimiento en publicaciones
- **`web_search`**: Útil para buscar información en internet.
- **`wikipedia_search`**: Consulta Wikipedia para obtener resúmenes informativos sobre conceptos,
- **`recoverFromOpenAlex`**: Recupera el registro bibliográfico de un paper desde OpenAlex usando su DOI.
- **`searchAuthorInOpenAlex`**: Busca los n autores más parecidos en OpenAlex al nombre dado.
- **`recoverAuthorWorksFromOpenAlex`**: Recupera los primeros n trabajos de un autor en OpenAlex a partir de su author_id (ej. A5023888360).
- **`Python_CodeExecutor`**: Ejecuta código Python con acceso a:
  - **Análisis de datos**: pandas, numpy, scikit-learn
  - **Visualización**: matplotlib, plotly
  - **Redes**: networkx
  - **Bibliometría**: pyalex (OpenAlex API), pybliometrics (Scopus — requiere API key configurada)
  - **Machine Learning**: umap-learn, somoclu
  - Guarda gráficas con `plt.savefig('interpreter_output.png')` o `fig.write_image('interpreter_output.png')`

> ⚠️ RESTRICCIONES ABSOLUTAS: Solo puedes proponer pasos que usen las herramientas listadas arriba. NO existe acceso a Scopus, Web of Science, Google Scholar, Unpaywall, repositorios institucionales, Docker, Airflow ni ninguna API externa no listada. Si un objetivo no puede cumplirse con estas herramientas, indícalo explícitamente y propón una alternativa real.

Deliberen desde sus perspectivas únicas. El plan DEBE:
- Ser ejecutable con los datos y herramientas listados arriba
- Priorizar datos que YA EXISTEN en Neo4j/Qdrant
- Proponer métricas diversas (no solo factor de impacto)
- Considerar equidad, sesgos y diversidad en el análisis
- Ser útil para quienes toman decisiones de política científica

Cuando estés convencido/a del plan, escribe tu señal de aprobación. Cualquier miembro puede declarar 'CONSENSO_MAYORITARIO' si observa que 4 o más ya aprobaron.
