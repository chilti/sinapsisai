# Procedimientos de Identificación y Enriquecimiento SNII 2025

Este documento describe la evolución y los métodos utilizados para identificar académicamente a los investigadores del SNII 2025, cruzando sus datos con fuentes locales (Neo4j), globales (ORCID/OpenAlex) y web.

## Estrategia General: "Triple Vectorización"

La identificación se basa en convertir nombres y afiliaciones en vectores (embeddings) para realizar búsquedas semánticas que toleren variaciones en la escritura.

### Fase 1: Preparación del Contexto (Reference Indexes)
Para que el sistema pueda encontrar coincidencias, primero poblamos nuestra base de datos vectorial (Qdrant) con dos fuentes de referencia:

1.  **Autores Locales (Local Authors)**:
    - Extraídos de **Neo4j**, filtrando investigadores que han publicado artículos con afiliación en México.
    - El script extrae el ORCID y el nombre tal cual aparece en los metadatos de los artículos.
2.  **Universo ORCID (ORCID Dump)**:
    - Extraídos de **ClickHouse**, utilizando una red de seguridad dinámica (`MEX_KEYWORDS`) que incluye todas las instituciones del SNII.
    - Se vectorizan nombres y afiliaciones para permitir búsquedas rápidas.

### Fase 2: Emparejamiento Semántico Directo
Una vez listas las referencias, procesamos el Excel del SNII:
- El sistema busca para cada investigador del SNII el "vecino más cercano" en la colección de autores locales y en la de ORCID global.
- Este método sirve como un filtro inicial de alta velocidad.

---

## Fase 3: Validación Avanzada (El Método Ganador) 🏆

A pesar de la potencia de los vectores, los nombres similares pueden causar confusión. Para resolver esto con precisión quirúrgica, implementamos el **Paso 4: Reranking con LLM**.

### ¿Cómo funciona el Paso 4?
1.  **Recuperación**: El sistema busca los **Top 5** candidatos más parecidos en Qdrant.
2.  **Juicio**: Se le presenta al LLM (vía LM Studio) la ficha completa del investigador buscado vs los 5 candidatos encontrados (con sus afiliaciones originales).
3.  **Veredicto**: El LLM actúa como un juez humano, ignorando errores ortográficos y centrando el match en la consistencia de la trayectoria y la institución.

> [!IMPORTANT]
> Esta fase identificó exitosamente a **20,333 investigadores**, demostrando ser el método más fiable hasta la fecha.

---

## Estrategias de "Rescate" y Auditoría

Para aquellos investigadores que no aparecen en las bases de datos locales o tienen perfiles ambiguos, contamos con dos herramientas adicionales:

### 4. Scraper Institucional (SIIA UNAM)
- **Uso**: Identificación de investigadores UNAM mediante el motor interno de la Universidad.
- **Logro**: Captura Scopus IDs y ORCIDs registrados administrativamente que a veces no son públicos en OpenAlex.

### 5. Buscador Web Activo (Web Finder)
- **Uso**: Búsqueda controlada en DuckDuckGo dirigida a perfiles de ORCID.
- **Validación**: Los snippets web son validados por el LLM para asegurar que el link de ORCID hallado corresponda realmente al académico.

### 6. Auditoría de Validez (Challenge Script)
- **Propósito**: Retar los matches ya encontrados para detectar falsos positivos.
- **Lógica**: Cruza el ORCID hallado con datos profundos en ClickHouse y evidencia web para confirmar la identidad con un puntaje de confianza.

---

## Resumen de Scripts en `/SNII`

- [vectorize_researchers.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/SNII/vectorize_researchers.py): Pipeline principal de vectorización (Pasos 1-4).
- [web_orcid_finder.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/SNII/web_orcid_finder.py): Buscador web activo.
- [challenge_orcid_validity.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/SNII/challenge_orcid_validity.py): Auditoría de integridad.
- [match_snii_orcid.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/SNII/match_snii_orcid.py): Utilidades de normalización y conexión.
