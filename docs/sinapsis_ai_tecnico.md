# Descripción Técnica de Sinapsis AI

**Sinapsis AI (Hub de Ciencia Abierta)** representa un nuevo enfoque analítico para la evaluación institucional. Es un sistema híbrido de inteligencia bibliométrica y un orquestador de **Generación Aumentada por Recuperación (RAG)** diseñado específicamente para entidades académicas.

## Arquitectura del Sistema

Sinapsis AI integra un grafo de conocimiento con bases de datos vectoriales y Modelos de Lenguaje de Gran Escala (LLMs) localizados para automatizar la generación de analíticas complejas a nivel institucional.

### Núcleo de Inteligencia
- **Orquestador RAG**: Combina la precisión de las bases de datos estructuradas con la flexibilidad de los LLM (ej. GPT-4 o modelos locales vía **LM Studio**).
- **IA Generativa**: Se utiliza para la redacción de reportes analíticos tipo "Journal" mediante agentes inteligentes que resumen el impacto académico.

### Gestión de Datos (Arquitectura Híbrida)
- **Neo4j (Knowledge Graph)**: Gestiona la red de relaciones entre entidades, autores, publicaciones, citas y coautorías.
- **Qdrant (Vector Database)**: Almacena representaciones vectoriales (embeddings) de resúmenes y títulos para habilitar la búsqueda semántica y la recuperación de información.

### Ingesta y Enriquecimiento
- **Pipeline Automatizado**: Integra múltiples APIs globales:
    - **OpenAlex**: Principal fuente de metadatos de ciencia abierta.
    - **Crossref / Datacite**: Resolución de DOIs y metadatos de publicaciones.
    - **ORCID**: Identificación única de autores y sus obras.
- **Web Scraping**: Extracción de datos de perfiles institucionales (ej. **SIIA-UNAM**) para complementar la identificación de identificadores persistentes.

### Funcionalidades de IA Especializadas
- **Clasificación Automática de ODS**: Clasificación de publicaciones según los Objetivos de Desarrollo Sostenible de la ONU mediante análisis de resúmenes.
- **Inferencia de Género**: Estimación estadística basada en nombres para análisis de paridad en la producción científica.
- **Mapeo de Colaboración**: Visualización de redes de cooperación institucional y redes mundiales.

## Propósito Institucional
Esta herramienta ejemplifica la integración del desarrollo de **métricas asistidas por IA**, proporcionando a las instituciones mecanismos de reporte automatizados, transparentes y responsables para evaluar su impacto social y académico a largo plazo.
