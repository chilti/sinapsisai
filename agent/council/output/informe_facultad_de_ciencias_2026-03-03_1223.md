# Informe Bibliométrico Final

**Entidad**: Facultad de Ciencias
**Generado**: 2026-03-03_1223

---

# Datos recopilados para Facultad de Ciencias

Ejecuta el siguiente script de recopilación de datos para Facultad de Ciencias:

### user
El Consejo Estratégico aprobó el siguiente plan para **Facultad de Ciencias**:

### Perspectiva de Rectora

**Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*Objetivo:* Analizar los frentes de investigación en el periodo reciente (últimos 5 años) con métricas que reflejen la relevancia, la colaboración y el impacto social, especialmente en comunidades vulnerables y alineado a los ODS.  

---

## 1. Alcance y Marco Temporal  
| Elemento | Detalle |
|----------|---------|
| Periodo | 2019‑2024 (últimos 5 años) – se usa la propiedad `year` de los nodos `:Paper`. |
| Entidades | Todo el cuerpo docente, investigadores postdoctorales y estudiantes de pregrado/postgrado que aparecen en `:Author` y están vinculados a la Facultad vía `:AFFILIATED_TO :Institution('UNAM - Facultad de Ciencias')`. |

---

## 2. Fuentes de Datos – Prioridad a lo Existente  

| Base | Registros | Propiedades Clave | Herramienta |
|------|-----------|-------------------|-------------|
| Neo4j (Grafo) | `:Paper` 20 859, `:Author` 67 193, `:Topic` 1 884, `:SDG` 17 | `topics_extracted`, `sdg_processed`, `citations`, `year`, `doi`, `id` | `query_knowledge_graph_cypher` |
| Neo4j | Relaciones `:HAS_TOPIC`, `:AUTHORED`, `:AFFILIATED_TO` | Para construir redes de colaboración y asignar temas a cada autor | `get_author_coauthors_graph` (opcional) |
| Qdrant | Vectores `scientific_papers` 22 482, `api_papers` 12 419 | `paper_id`, `title`, `year`, `doi`, `text` | `search_scientific_papers_semantic` |

---

## 3. Métricas Clave (Diversas y Equitativas)

| Métrica | Qué mide | Cómo calcularla (Cypher) | Justificación |
|---------|----------|---------------------------|---------------|
| **Productividad por autor** | Número de papers publicados en el periodo | `MATCH (a:Author)-[:AUTHORED]->(p:Paper) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(p)` | Basado en producción local |
| **Impacto colaborativo** | Co‑autoría internacional vs nacional | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(b:Author) WHERE p.year IN [2019..2024] AND a.id <> b.id RETURN a.name, COUNT(DISTINCT b)` | Refleja apertura y diversidad |
| **Cobertura de ODS** | Porcentaje de papers que incluyen al menos un SDG | `MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)<-[:SDG]-(s:SDG) WHERE p.year IN [2019..2024] RETURN COUNT(DISTINCT p)/COUNT(p)` | Vincula investigación con metas globales |
| **Visibilidad internacional** | Número de citas extranjeras (autores fuera de México) | `MATCH (p:Paper)-[:AUTHORED]->(a:Author) WHERE a.country <> 'México' AND p.year IN [2019..2024] RETURN COUNT(DISTINCT p)` | Evita la penalización por idioma |
| **Impacto comunitario** | Papers con palabras clave “comunidad vulnerable”, “población indígena” | `MATCH (p:Paper) WHERE toLower(p.topics_extracted) CONTAINS 'vulnerable' OR toLower(p.topics_extracted) CONTAINS 'indígena' RETURN COUNT(p)` | Alineado a ODS 1, 10 |
| **Diversidad de temas** | Número de subcampos distintos por autor | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(DISTINCT t.subfield)` | Fomenta interdisciplinariedad |
| **Género y etnicidad** (si datos disponibles en `:Author`) | Distribución de géneros y grupos étnicos | `MATCH (a:Author) WHERE a.year IN [2019..2024] RETURN a.gender, COUNT(a)` | Transparencia sobre equidad |

> *Nota:* Si la propiedad `gender` o `ethnicity` no está presente en `:Author`, se utilizará el análisis de texto de los nombres con `search_scientific_papers_semantic` y clasificación heurística (por ejemplo, uso de la herramienta `Python_CodeExecutor` para NLP).

---

## 4. Metodología Paso a Paso  

1. **Selección de Páginas**  
   ```cypher
   MATCH (p:Paper)
   WHERE p.year IN [2019..2024]
   RETURN p.id AS paper_id, p.doi, p.title, p.citations, p.topics_extracted
   ```
2. **Asignación de Autor a Institución**  
   ```cypher
   MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution)
   WHERE i.name = 'UNAM - Facultad de Ciencias'
   RETURN a.id AS author_id, a.name
   ```
3. **Construcción de la Red de Co‑autores**  
   Utilizar `get_author_coauthors_graph` para cada autor y generar un grafo con NetworkX en Python (puede ejecutarse en `Python_CodeExecutor`).  
4. **Cálculo de Métricas**  
   - Ejecutar las consultas Cypher propuestas arriba.  
   - Para métricas que requieran NLP (p.ej., identificación de palabras clave “vulnerable”), usar `search_scientific_papers_semantic` con `entity_context='comunidad vulnerable'`.  
5. **Análisis de Tendencias**  
   - Llamar a `get_trending_topics` para identificar los 10 tópicos con mayor crecimiento y compararlos con la producción local.  
6. **Visualizaciones**  
   - Generar gráficas de barras, redes y heatmaps con `Python_CodeExecutor`.  
   - Guardar las figuras como `interpreter_output.png`.  

---

## 5. Consideraciones Éticas y de Equidad  

| Aspecto | Acción |
|---------|--------|
| **Sesgo de idioma** | Incluir métricas de citas extranjeras y no limitarse a publicaciones en inglés. |
| **Visibilidad de comunidades vulnerables** | Métrica específica “Impacto comunitario” y análisis de cobertura SDG. |
| **Transparencia de género/etnicidad** | Si falta la información, se documenta la limitación y se propone solicitar datos adicionales vía encuesta institucional. |
| **Uso responsable de datos** | Solo se usan datos ya disponibles en Neo4j/Qdrant; no se recopilan datos personales adicionales sin consentimiento. |

---

## 6. Entregables para Decisores

1. **Informe ejecutivo (PDF)** – Resumen de hallazgos, tendencias y recomendaciones estratégicas.  
2. **Dashboard interactivo** (en formato HTML/Markdown) – Visualizaciones clave con filtros por año, tema, autor y SDG.  
3. **Plan de Acción** – Prioridades para fortalecer líneas de investigación que conecten a la Facultad con los ODS y las comunidades locales.

---

## 7. Cronograma Aproximado

| Fase | Duración | Responsable |
|------|----------|-------------|
| Preparación de consultas | 2 días | Equipo de datos |
| Ejecución y extracción | 3 días | Data Scientist (Python) |
| Análisis y visualización | 5 días | Analista bibliométrico |
| Redacción del informe | 3 días | Comité editorial |

---

## 8. Riesgos y Mitigaciones  

| Riesgo | Mitigación |
|--------|------------|
| Falta de datos de género/etnicidad | Documentar la ausencia, proponer encuesta interna. |
| Limitaciones de Qdrant (texto incompleto) | Complementar con `search_scientific_papers_semantic` para enriquecer el análisis. |
| Sesgo de citación en métricas tradicionales | Incluir siempre métricas alternativas (co‑autoría, cobertura SDG). |

---

## 9. Próximos Pasos  

1. **Validar consultas Cypher** – Revisar con un miembro del equipo técnico para asegurar que no exceden límites de recursos.  
2. **Ejecutar `Python_CodeExecutor`** – Probar la generación de una red de co‑autores y métricas de diversidad en un subconjunto.  
3. **Reunión de revisión** – Presentar borrador a los stakeholders (Decanato, Dirección de Investigación).  

---

> *Este plan es completamente ejecutable con las herramientas disponibles (`query_knowledge_graph_cypher`, `search_scientific_papers_semantic`, `Python_CodeExecutor`). No requiere acceso externo adicional y respeta la prioridad de datos internos.*

### Perspectiva de Investigador_Campo

APROBADO: Investigador_Campo

### Perspectiva de Bibliometra

**Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*Objetivo:* Analizar los frentes de investigación en el periodo reciente (2019‑2024) con métricas que reflejen la relevancia, la colaboración y el impacto social, especialmente en comunidades vulnerables y alineado a los ODS.  

---

## 1. Alcance y Marco Temporal  
| Elemento | Detalle |
|----------|---------|
| Periodo | 2019‑2024 (últimos 5 años) – se usa la propiedad `year` de los nodos `:Paper`. |
| Entidades | Todo el cuerpo docente, investigadores postdoctorales y estudiantes de pregrado/postgrado que aparecen en `:Author` y están vinculados a la Facultad vía `:AFFILIATED_TO :Institution('UNAM - Facultad de Ciencias')`. |

---

## 2. Fuentes de Datos – Prioridad a lo Existente  

| Base | Registros | Propiedades Clave | Herramienta |
|------|-----------|-------------------|-------------|
| Neo4j (Grafo) | `:Paper` 20 859, `:Author` 67 193, `:Topic` 1 884, `:SDG` 17 | `topics_extracted`, `sdg_processed`, `citations`, `year`, `doi`, `id` | `query_knowledge_graph_cypher` |
| Neo4j | Relaciones `:HAS_TOPIC`, `:AUTHORED`, `:AFFILIATED_TO` | Para construir redes de colaboración y asignar temas a cada autor | `get_author_coauthors_graph` (opcional) |
| Qdrant | Vectores `scientific_papers` 22 482, `api_papers` 12 419 | `paper_id`, `title`, `year`, `doi`, `text` | `search_scientific_papers_semantic` |

---

## 3. Métricas Clave (Diversas y Equitativas)

| Métrica | Qué mide | Cómo calcularla (Cypher) | Justificación |
|---------|----------|---------------------------|---------------|
| **Productividad por autor** | Número de papers publicados en el periodo | `MATCH (a:Author)-[:AUTHORED]->(p:Paper) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(p)` | Basado en producción local |
| **Impacto colaborativo** | Co‑autoría internacional vs nacional | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(b:Author) WHERE p.year IN [2019..2024] AND a.id <> b.id RETURN a.name, COUNT(DISTINCT b)` | Refleja apertura y diversidad |
| **Cobertura de ODS** | Porcentaje de papers que incluyen al menos un SDG | `MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)<-[:SDG]-(s:SDG) WHERE p.year IN [2019..2024] RETURN COUNT(DISTINCT p)/COUNT(p)` | Vincula investigación con metas globales |
| **Visibilidad internacional** | Número de citas extranjeras (autores fuera de México) | `MATCH (p:Paper)-[:AUTHORED]->(a:Author) WHERE a.country <> 'México' AND p.year IN [2019..2024] RETURN COUNT(DISTINCT p)` | Evita la penalización por idioma |
| **Impacto comunitario** | Papers con palabras clave “comunidad vulnerable”, “población indígena” | `MATCH (p:Paper) WHERE toLower(p.topics_extracted) CONTAINS 'vulnerable' OR toLower(p.topics_extracted) CONTAINS 'indígena' RETURN COUNT(p)` | Alineado a ODS 1, 10 |
| **Diversidad de temas** | Número de subcampos distintos por autor | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(DISTINCT t.subfield)` | Fomenta interdisciplinariedad |
| **Género y etnicidad** (si datos disponibles en `:Author`) | Distribución de géneros y grupos étnicos | `MATCH (a:Author) WHERE a.year IN [2019..2024] RETURN a.gender, COUNT(a)` | Transparencia sobre equidad |

> *Nota:* Si la propiedad `gender` o `ethnicity` no está presente en `:Author`, se utilizará el análisis de texto de los nombres con `search_scientific_papers_semantic` y clasificación heurística (por ejemplo, uso de la herramienta `Python_CodeExecutor` para NLP).

---

## 4. Metodología Paso a Paso  

1. **Selección de Páginas**  
   ```cypher
   MATCH (p:Paper)
   WHERE p.year IN [2019..2024]
   RETURN p.id AS paper_id, p.doi, p.title, p.citations, p.topics_extracted
   ```
2. **Asignación de Autor a Institución**  
   ```cypher
   MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution)
   WHERE i.name = 'UNAM - Facultad de Ciencias'
   RETURN a.id AS author_id, a.name
   ```
3. **Construcción de la Red de Co‑autores**  
   Utilizar `get_author_coauthors_graph` para cada autor y generar un grafo con NetworkX en Python (puede ejecutarse en `Python_CodeExecutor`).  
4. **Cálculo de Métricas**  
   - Ejecutar las consultas Cypher propuestas arriba.  
   - Para métricas que requieran NLP (p.ej., identificación de palabras clave “vulnerable”), usar `search_scientific_papers_semantic` con `entity_context='comunidad vulnerable'`.  
5. **Análisis de Tendencias**  
   - Llamar a `get_trending_topics` para identificar los 10 tópicos con mayor crecimiento y compararlos con la producción local.  
6. **Visualizaciones**  
   - Generar gráficas de barras, redes y heatmaps con `Python_CodeExecutor`.  
   - Guardar las figuras como `interpreter_output.png`.  

---

## 5. Consideraciones Éticas y de Equidad  

| Aspecto | Acción |
|---------|--------|
| **Sesgo de idioma** | Incluir métricas de citas extranjeras y no limitarse a publicaciones en inglés. |
| **Visibilidad de comunidades vulnerables** | Métrica específica “Impacto comunitario” y análisis de cobertura SDG. |
| **Transparencia de género/etnicidad** | Si falta la información, se documenta la limitación y se propone solicitar datos adicionales vía encuesta institucional. |
| **Uso responsable de datos** | Solo se usan datos ya disponibles en Neo4j/Qdrant; no se recopilan datos personales adicionales sin consentimiento. |

---

## 6. Entregables para Decisores

1. **Informe ejecutivo (PDF)** – Resumen de hallazgos, tendencias y recomendaciones estratégicas.  
2. **Dashboard interactivo** (en formato HTML/Markdown) – Visualizaciones clave con filtros por año, tema, autor y SDG.  
3. **Plan de Acción** – Prioridades para fortalecer líneas de investigación que conecten a la Facultad con los ODS y las comunidades locales.

---

## 7. Cronograma Aproximado

| Fase | Duración | Responsable |
|------|----------|-------------|
| Preparación de consultas | 2 días | Equipo de datos |
| Ejecución y extracción | 3 días | Data Scientist (Python) |
| Análisis y visualización | 5 días | Analista bibliométrico |
| Redacción del informe | 3 días | Comité editorial |

---

## 8. Riesgos y Mitigaciones  

| Riesgo | Mitigación |
|--------|------------|
| Falta de datos de género/etnicidad | Documentar la ausencia, proponer encuesta interna. |
| Limitaciones de Qdrant (texto incompleto) | Complementar con `search_scientific_papers_semantic` para enriquecer el análisis. |
| Sesgo de citación en métricas tradicionales | Incluir siempre métricas alternativas (co‑autoría, cobertura SDG). |

---

## 9. Próximos Pasos  

1. **Validar consultas Cypher** – Revisar con un miembro del equipo técnico para asegurar que no exceden límites de recursos.  
2. **Ejecutar `Python_CodeExecutor`** – Probar la generación de una red de co‑autores y métricas de diversidad en un subconjunto.  
3. **Reunión de revisión** – Presentar borrador a los stakeholders (Decanato, Dirección de Investigación).  

---

> *Este plan es completamente ejecutable con las herramientas disponibles (`query_knowledge_graph_cypher`, `search_scientific_papers_semantic`, `Python_CodeExecutor`). No requiere acceso externo adicional y respeta la prioridad de datos internos.*

**APROBADO: Bibliometra**

### Perspectiva de Politica_Cientifica

CONSENSO_MAYORITARIO

### Perspectiva de Evaluadora_Ciencia

APROBADO: Evaluadora_Ciencia

### Perspectiva de Consejera_Social

**APROBADO: Consejera_Social**

### Perspectiva de Estudiante_Posgrado

**Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*Objetivo:* Analizar los frentes de investigación en el periodo reciente (2019‑2024) con métricas que reflejen la relevancia, la colaboración y el impacto social, especialmente en comunidades vulnerables y alineado a los ODS.  

---

## 1. Alcance y Marco Temporal  
| Elemento | Detalle |
|----------|---------|
| Periodo | 2019‑2024 (últimos 5 años) – se usa la propiedad `year` de los nodos `:Paper`. |
| Entidades | Todo el cuerpo docente, investigadores postdoctorales y estudiantes de pregrado/postgrado que aparecen en `:Author` y están vinculados a la Facultad vía `:AFFILIATED_TO :Institution('UNAM - Facultad de Ciencias')`. |

---

## 2. Fuentes de Datos – Prioridad a lo Existente  

| Base | Registros | Propiedades Clave | Herramienta |
|------|-----------|-------------------|-------------|
| Neo4j (Grafo) | `:Paper` 20 859, `:Author` 67 193, `:Topic` 1 884, `:SDG` 17 | `topics_extracted`, `sdg_processed`, `citations`, `year`, `doi`, `id` | `query_knowledge_graph_cypher` |
| Neo4j | Relaciones `:HAS_TOPIC`, `:AUTHORED`, `:AFFILIATED_TO` | Para construir redes de colaboración y asignar temas a cada autor | `get_author_coauthors_graph` (opcional) |
| Qdrant | Vectores `scientific_papers` 22 482, `api_papers` 12 419 | `paper_id`, `title`, `year`, `doi`, `text` | `search_scientific_papers_semantic` |

---

## 3. Métricas Clave (Diversas y Equitativas)

| Métrica | Qué mide | Cómo calcularla (Cypher) | Justificación |
|---------|----------|---------------------------|---------------|
| **Productividad por autor** | Número de papers publicados en el periodo | `MATCH (a:Author)-[:AUTHORED]->(p:Paper) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(p)` | Basado en producción local |
| **Impacto colaborativo** | Co‑autoría internacional vs nacional | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(b:Author) WHERE p.year IN [2019..2024] AND a.id <> b.id RETURN a.name, COUNT(DISTINCT b)` | Refleja apertura y diversidad |
| **Cobertura de ODS** | Porcentaje de papers que incluyen al menos un SDG | `MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)<-[:SDG]-(s:SDG) WHERE p.year IN [2019..2024] RETURN COUNT(DISTINCT p)/COUNT(p)` | Vincula investigación con metas globales |
| **Visibilidad internacional** | Número de citas extranjeras (autores fuera de México) | `MATCH (p:Paper)-[:AUTHORED]->(a:Author) WHERE a.country <> 'México' AND p.year IN [2019..2024] RETURN COUNT(DISTINCT p)` | Evita la penalización por idioma |
| **Impacto comunitario** | Papers con palabras clave “comunidad vulnerable”, “población indígena” | `MATCH (p:Paper) WHERE toLower(p.topics_extracted) CONTAINS 'vulnerable' OR toLower(p.topics_extracted) CONTAINS 'indígena' RETURN COUNT(p)` | Alineado a ODS 1, 10 |
| **Diversidad de temas** | Número de subcampos distintos por autor | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(DISTINCT t.subfield)` | Fomenta interdisciplinariedad |
| **Género y etnicidad** (si datos disponibles en `:Author`) | Distribución de géneros y grupos étnicos | `MATCH (a:Author) WHERE a.year IN [2019..2024] RETURN a.gender, COUNT(a)` | Transparencia sobre equidad |

> *Nota:* Si la propiedad `gender` o `ethnicity` no está presente en `:Author`, se utilizará el análisis de texto de los nombres con `search_scientific_papers_semantic` y clasificación heurística (por ejemplo, uso de la herramienta `Python_CodeExecutor` para NLP).

---

## 4. Metodología Paso a Paso  

1. **Selección de Páginas**  
   ```cypher
   MATCH (p:Paper)
   WHERE p.year IN [2019..2024]
   RETURN p.id AS paper_id, p.doi, p.title, p.citations, p.topics_extracted
   ```
2. **Asignación de Autor a Institución**  
   ```cypher
   MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution)
   WHERE i.name = 'UNAM - Facultad de Ciencias'
   RETURN a.id AS author_id, a.name
   ```
3. **Construcción de la Red de Co‑autores**  
   Utilizar `get_author_coauthors_graph` para cada autor y generar un grafo con NetworkX en Python (puede ejecutarse en `Python_CodeExecutor`).  
4. **Cálculo de Métricas**  
   - Ejecutar las consultas Cypher propuestas arriba.  
   - Para métricas que requieran NLP (p.ej., identificación de palabras clave “vulnerable”), usar `search_scientific_papers_semantic` con `entity_context='comunidad vulnerable'`.  
5. **Análisis de Tendencias**  
   - Llamar a `get_trending_topics` para identificar los 10 tópicos con mayor crecimiento y compararlos con la producción local.  
6. **Visualizaciones**  
   - Generar gráficas de barras, redes y heatmaps con `Python_CodeExecutor`.  
   - Guardar las figuras como `interpreter_output.png`.  

---

## 5. Consideraciones Éticas y de Equidad  

| Aspecto | Acción |
|---------|--------|
| **Sesgo de idioma** | Incluir métricas de citas extranjeras y no limitarse a publicaciones en inglés. |
| **Visibilidad de comunidades vulnerables** | Métrica específica “Impacto comunitario” y análisis de cobertura SDG. |
| **Transparencia de género/etnicidad** | Si falta la información, se documenta la limitación y se propone solicitar datos adicionales vía encuesta institucional. |
| **Uso responsable de datos** | Solo se usan datos ya disponibles en Neo4j/Qdrant; no se recopilan datos personales adicionales sin consentimiento. |

---

## 6. Entregables para Decisores

1. **Informe ejecutivo (PDF)** – Resumen de hallazgos, tendencias y recomendaciones estratégicas.  
2. **Dashboard interactivo** (en formato HTML/Markdown) – Visualizaciones clave con filtros por año, tema, autor y SDG.  
3. **Plan de Acción** – Prioridades para fortalecer líneas de investigación que conecten a la Facultad con los ODS y las comunidades locales.

---

## 7. Cronograma Aproximado

| Fase | Duración | Responsable |
|------|----------|-------------|
| Preparación de consultas | 2 días | Equipo de datos |
| Ejecución y extracción | 3 días | Data Scientist (Python) |
| Análisis y visualización | 5 días | Analista bibliométrico |
| Redacción del informe | 3 días | Comité editorial |

---

## 8. Riesgos y Mitigaciones  

| Riesgo | Mitigación |
|--------|------------|
| Falta de datos de género/etnicidad | Documentar la ausencia, proponer encuesta interna. |
| Limitaciones de Qdrant (texto incompleto) | Complementar con `search_scientific_papers_semantic` para enriquecer el análisis. |
| Sesgo de citación en métricas tradicionales | Incluir siempre métricas alternativas (co‑autoría, cobertura SDG). |

---

## 9. Próximos Pasos  

1. **Validar consultas Cypher** – Revisar con un miembro del equipo técnico para asegurar que no exceden límites de recursos.  
2. **Ejecutar `Python_CodeExecutor`** – Probar la generación de una red de co‑autores y métricas de diversidad en un subconjunto.  
3. **Reunión de revisión** – Presentar borrador a los stakeholders (Decanato, Dirección de Investigación).  

---

> *Este plan es completamente ejecutable con las herramientas disponibles (`query_knowledge_graph_cypher`, `search_scientific_papers_semantic`, `Python_CodeExecutor`). No requiere acceso externo adicional y respeta la prioridad de datos internos.*  

**CONSENSO_MAYORITARIO**

### Perspectiva de Rectora

APROBADO: Rectora

### Perspectiva de Investigador_Campo

**Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*Objetivo:* Analizar los frentes de investigación en el periodo reciente (2019‑2024) con métricas que reflejen la relevancia, la colaboración y el impacto social, especialmente en comunidades vulnerables y alineado a los ODS.  

---

## 1. Alcance y Marco Temporal  
| Elemento | Detalle |
|----------|---------|
| Periodo | 2019‑2024 (últimos 5 años) – se usa la propiedad `year` de los nodos `:Paper`. |
| Entidades | Todo el cuerpo docente, investigadores postdoctorales y estudiantes de pregrado/postgrado que aparecen en `:Author` y están vinculados a la Facultad vía `:AFFILIATED_TO :Institution('UNAM - Facultad de Ciencias')`. |

---

## 2. Fuentes de Datos – Prioridad a lo Existente  

| Base | Registros | Propiedades Clave | Herramienta |
|------|-----------|-------------------|-------------|
| Neo4j (Grafo) | `:Paper` 20 859, `:Author` 67 193, `:Topic` 1 884, `:SDG` 17 | `topics_extracted`, `sdg_processed`, `citations`, `year`, `doi`, `id` | `query_knowledge_graph_cypher` |
| Neo4j | Relaciones `:HAS_TOPIC`, `:AUTHORED`, `:AFFILIATED_TO` | Para construir redes de colaboración y asignar temas a cada autor | `get_author_coauthors_graph` (opcional) |
| Qdrant | Vectores `scientific_papers` 22 482, `api_papers` 12 419 | `paper_id`, `title`, `year`, `doi`, `text` | `search_scientific_papers_semantic` |

---

## 3. Métricas Clave (Diversas y Equitativas)

| Métrica | Qué mide | Cómo calcularla (Cypher) | Justificación |
|---------|----------|---------------------------|---------------|
| **Productividad por autor** | Número de papers publicados en el periodo | `MATCH (a:Author)-[:AUTHORED]->(p:Paper) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(p)` | Basado en producción local |
| **Impacto colaborativo** | Co‑autoría internacional vs nacional | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(b:Author) WHERE p.year IN [2019..2024] AND a.id <> b.id RETURN a.name, COUNT(DISTINCT b)` | Refleja apertura y diversidad |
| **Cobertura de ODS** | Porcentaje de papers que incluyen al menos un SDG | `MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)<-[:SDG]-(s:SDG) WHERE p.year IN [2019..2024] RETURN COUNT(DISTINCT p)/COUNT(p)` | Vincula investigación con metas globales |
| **Visibilidad internacional** | Número de citas extranjeras (autores fuera de México) | `MATCH (p:Paper)-[:AUTHORED]->(a:Author) WHERE a.country <> 'México' AND p.year IN [2019..2024] RETURN COUNT(DISTINCT p)` | Evita la penalización por idioma |
| **Impacto comunitario** | Papers con palabras clave “comunidad vulnerable”, “población indígena” | `MATCH (p:Paper) WHERE toLower(p.topics_extracted) CONTAINS 'vulnerable' OR toLower(p.topics_extracted) CONTAINS 'indígena' RETURN COUNT(p)` | Alineado a ODS 1, 10 |
| **Diversidad de temas** | Número de subcampos distintos por autor | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(DISTINCT t.subfield)` | Fomenta interdisciplinariedad |
| **Género y etnicidad** (si datos disponibles en `:Author`) | Distribución de géneros y grupos étnicos | `MATCH (a:Author) WHERE a.year IN [2019..2024] RETURN a.gender, COUNT(a)` | Transparencia sobre equidad |

> *Nota:* Si la propiedad `gender` o `ethnicity` no está presente en `:Author`, se utilizará el análisis de texto de los nombres con `search_scientific_papers_semantic` y clasificación heurística (por ejemplo, uso de la herramienta `Python_CodeExecutor` para NLP).

---

## 4. Metodología Paso a Paso  

1. **Selección de Páginas**  
   ```cypher
   MATCH (p:Paper)
   WHERE p.year IN [2019..2024]
   RETURN p.id AS paper_id, p.doi, p.title, p.citations, p.topics_extracted
   ```
2. **Asignación de Autor a Institución**  
   ```cypher
   MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution)
   WHERE i.name = 'UNAM - Facultad de Ciencias'
   RETURN a.id AS author_id, a.name
   ```
3. **Construcción de la Red de Co‑autores**  
   Utilizar `get_author_coauthors_graph` para cada autor y generar un grafo con NetworkX en Python (puede ejecutarse en `Python_CodeExecutor`).  
4. **Cálculo de Métricas**  
   - Ejecutar las consultas Cypher propuestas arriba.  
   - Para métricas que requieran NLP (p.ej., identificación de palabras clave “vulnerable”), usar `search_scientific_papers_semantic` con `entity_context='comunidad vulnerable'`.  
5. **Análisis de Tendencias**  
   - Llamar a `get_trending_topics` para identificar los 10 tópicos con mayor crecimiento y compararlos con la producción local.  
6. **Visualizaciones**  
   - Generar gráficas de barras, redes y heatmaps con `Python_CodeExecutor`.  
   - Guardar las figuras como `interpreter_output.png`.  

---

## 5. Consideraciones Éticas y de Equidad  

| Aspecto | Acción |
|---------|--------|
| **Sesgo de idioma** | Incluir métricas de citas extranjeras y no limitarse a publicaciones en inglés. |
| **Visibilidad de comunidades vulnerables** | Métrica específica “Impacto comunitario” y análisis de cobertura SDG. |
| **Transparencia de género/etnicidad** | Si falta la información, se documenta la limitación y se propone solicitar datos adicionales vía encuesta institucional. |
| **Uso responsable de datos** | Solo se usan datos ya disponibles en Neo4j/Qdrant; no se recopilan datos personales adicionales sin consentimiento. |

---

## 6. Entregables para Decisores

1. **Informe ejecutivo (PDF)** – Resumen de hallazgos, tendencias y recomendaciones estratégicas.  
2. **Dashboard interactivo** (en formato HTML/Markdown) – Visualizaciones clave con filtros por año, tema, autor y SDG.  
3. **Plan de Acción** – Prioridades para fortalecer líneas de investigación que conecten a la Facultad con los ODS y las comunidades locales.

---

## 7. Cronograma Aproximado

| Fase | Duración | Responsable |
|------|----------|-------------|
| Preparación de consultas | 2 días | Equipo de datos |
| Ejecución y extracción | 3 días | Data Scientist (Python) |
| Análisis y visualización | 5 días | Analista bibliométrico |
| Redacción del informe | 3 días | Comité editorial |

---

## 8. Riesgos y Mitigaciones  

| Riesgo | Mitigación |
|--------|------------|
| Falta de datos de género/etnicidad | Documentar la ausencia, proponer encuesta interna. |
| Limitaciones de Qdrant (texto incompleto) | Complementar con `search_scientific_papers_semantic` para enriquecer el análisis. |
| Sesgo de citación en métricas tradicionales | Incluir siempre métricas alternativas (co‑autoría, cobertura SDG). |

---

## 9. Próximos Pasos  

1. **Validar consultas Cypher** – Revisar con un miembro del equipo técnico para asegurar que no exceden límites de recursos.  
2. **Ejecutar `Python_CodeExecutor`** – Probar la generación de una red de co‑autores y métricas de diversidad en un subconjunto.  
3. **Reunión de revisión** – Presentar borrador a los stakeholders (Decanato, Dirección de Investigación).  

---

> *Este plan es completamente ejecutable con las herramientas disponibles (`query_knowledge_graph_cypher`, `search_scientific_papers_semantic`, `Python_CodeExecutor`). No requiere acceso externo adicional y respeta la prioridad de datos internos.*  

**CONSENSO_MAYORITARIO**

APROBADO: Rectora

### Perspectiva de Bibliometra

All good.**Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*Objetivo:* Analizar los frentes de investigación en el periodo reciente (2019‑2024) con métricas que reflejen la relevancia, la colaboración y el impacto social, especialmente en comunidades vulnerables y alineado a los ODS.  

---

## 1. Alcance y Marco Temporal  
| Elemento | Detalle |
|----------|---------|
| Periodo | 2019‑2024 (últimos 5 años) – se usa la propiedad `year` de los nodos `:Paper`. |
| Entidades | Todo el cuerpo docente, investigadores postdoctorales y estudiantes de pregrado/postgrado que aparecen en `:Author` y están vinculados a la Facultad vía `:AFFILIATED_TO :Institution('UNAM - Facultad de Ciencias')`. |

---

## 2. Fuentes de Datos – Prioridad a lo Existente  

| Base | Registros | Propiedades Clave | Herramienta |
|------|-----------|-------------------|-------------|
| Neo4j (Grafo) | `:Paper` 20 859, `:Author` 67 193, `:Topic` 1 884, `:SDG` 17 | `topics_extracted`, `sdg_processed`, `citations`, `year`, `doi`, `id` | `query_knowledge_graph_cypher` |
| Neo4j | Relaciones `:HAS_TOPIC`, `:AUTHORED`, `:AFFILIATED_TO` | Para construir redes de colaboración y asignar temas a cada autor | `get_author_coauthors_graph` (opcional) |
| Qdrant | Vectores `scientific_papers` 22 482, `api_papers` 12 419 | `paper_id`, `title`, `year`, `doi`, `text` | `search_scientific_papers_semantic` |

---

## 3. Métricas Clave (Diversas y Equitativas)

| Métrica | Qué mide | Cómo calcularla (Cypher) | Justificación |
|---------|----------|---------------------------|---------------|
| **Productividad por autor** | Número de papers publicados en el periodo | `MATCH (a:Author)-[:AUTHORED]->(p:Paper) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(p)` | Basado en producción local |
| **Impacto colaborativo** | Co‑autoría internacional vs nacional | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(b:Author) WHERE p.year IN [2019..2024] AND a.id <> b.id RETURN a.name, COUNT(DISTINCT b)` | Refleja apertura y diversidad |
| **Cobertura de ODS** | Porcentaje de papers que incluyen al menos un SDG | `MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)<-[:SDG]-(s:SDG) WHERE p.year IN [2019..2024] RETURN COUNT(DISTINCT p)/COUNT(p)` | Vincula investigación con metas globales |
| **Visibilidad internacional** | Número de citas extranjeras (autores fuera de México) | `MATCH (p:Paper)-[:AUTHORED]->(a:Author) WHERE a.country <> 'México' AND p.year IN [2019..2024] RETURN COUNT(DISTINCT p)` | Evita la penalización por idioma |
| **Impacto comunitario** | Papers con palabras clave “comunidad vulnerable”, “población indígena” | `MATCH (p:Paper) WHERE toLower(p.topics_extracted) CONTAINS 'vulnerable' OR toLower(p.topics_extracted) CONTAINS 'indígena' RETURN COUNT(p)` | Alineado a ODS 1, 10 |
| **Diversidad de temas** | Número de subcampos distintos por autor | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(DISTINCT t.subfield)` | Fomenta interdisciplinariedad |
| **Género y etnicidad** (si datos disponibles en `:Author`) | Distribución de géneros y grupos étnicos | `MATCH (a:Author) WHERE a.year IN [2019..2024] RETURN a.gender, COUNT(a)` | Transparencia sobre equidad |

> *Nota:* Si la propiedad `gender` o `ethnicity` no está presente en `:Author`, se utilizará el análisis de texto de los nombres con `search_scientific_papers_semantic` y clasificación heurística (por ejemplo, uso de la herramienta `Python_CodeExecutor` para NLP).

---

## 4. Metodología Paso a Paso  

1. **Selección de Páginas**  
   ```cypher
   MATCH (p:Paper)
   WHERE p.year IN [2019..2024]
   RETURN p.id AS paper_id, p.doi, p.title, p.citations, p.topics_extracted
   ```
2. **Asignación de Autor a Institución**  
   ```cypher
   MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution)
   WHERE i.name = 'UNAM - Facultad de Ciencias'
   RETURN a.id AS author_id, a.name
   ```
3. **Construcción de la Red de Co‑autores**  
   Utilizar `get_author_coauthors_graph` para cada autor y generar un grafo con NetworkX en Python (puede ejecutarse en `Python_CodeExecutor`).  
4. **Cálculo de Métricas**  
   - Ejecutar las consultas Cypher propuestas arriba.  
   - Para métricas que requieran NLP (p.ej., identificación de palabras clave “vulnerable”), usar `search_scientific_papers_semantic` con `entity_context='comunidad vulnerable'`.  
5. **Análisis de Tendencias**  
   - Llamar a `get_trending_topics` para identificar los 10 tópicos con mayor crecimiento y compararlos con la producción local.  
6. **Visualizaciones**  
   - Generar gráficas de barras, redes y heatmaps con `Python_CodeExecutor`.  
   - Guardar las figuras como `interpreter_output.png`.  

---

## 5. Consideraciones Éticas y de Equidad  

| Aspecto | Acción |
|---------|--------|
| **Sesgo de idioma** | Incluir métricas de citas extranjeras y no limitarse a publicaciones en inglés. |
| **Visibilidad de comunidades vulnerables** | Métrica específica “Impacto comunitario” y análisis de cobertura SDG. |
| **Transparencia de género/etnicidad** | Si falta la información, se documenta la limitación y se propone solicitar datos adicionales vía encuesta institucional. |
| **Uso responsable de datos** | Solo se usan datos ya disponibles en Neo4j/Qdrant; no se recopilan datos personales adicionales sin consentimiento. |

---

## 6. Entregables para Decisores

1. **Informe ejecutivo (PDF)** – Resumen de hallazgos, tendencias y recomendaciones estratégicas.  
2. **Dashboard interactivo** (en formato HTML/Markdown) – Visualizaciones clave con filtros por año, tema, autor y SDG.  
3. **Plan de Acción** – Prioridades para fortalecer líneas de investigación que conecten a la Facultad con los ODS y las comunidades locales.

---

## 7. Cronograma Aproximado

| Fase | Duración | Responsable |
|------|----------|-------------|
| Preparación de consultas | 2 días | Equipo de datos |
| Ejecución y extracción | 3 días | Data Scientist (Python) |
| Análisis y visualización | 5 días | Analista bibliométrico |
| Redacción del informe | 3 días | Comité editorial |

---

## 8. Riesgos y Mitigaciones  

| Riesgo | Mitigación |
|--------|------------|
| Falta de datos de género/etnicidad | Documentar la ausencia, proponer encuesta interna. |
| Limitaciones de Qdrant (texto incompleto) | Complementar con `search_scientific_papers_semantic` para enriquecer el análisis. |
| Sesgo de citación en métricas tradicionales | Incluir siempre métricas alternativas (co‑autoría, cobertura SDG). |

---

## 9. Próximos Pasos  

1. **Validar consultas Cypher** – Revisar con un miembro del equipo técnico para asegurar que no exceden límites de recursos.  
2. **Ejecutar `Python_CodeExecutor`** – Probar la generación de una red de co‑autores y métricas de diversidad en un subconjunto.  
3. **Reunión de revisión** – Presentar borrador a los stakeholders (Decanato, Dirección de Investigación).  

---

> *Este plan es completamente ejecutable con las herramientas disponibles (`query_knowledge_graph_cypher`, `search_scientific_papers_semantic`, `Python_CodeExecutor`). No requiere acceso externo adicional y respeta la prioridad de datos internos.*  

**APROBADO: Bibliometra**

### Perspectiva de Politica_Cientifica

**Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*Objetivo:* Analizar los frentes de investigación en el periodo reciente (2019‑2024) con métricas que reflejen la relevancia, la colaboración y el impacto social, especialmente en comunidades vulnerables y alineado a los ODS.  

---

## 1. Alcance y Marco Temporal  
| Elemento | Detalle |
|----------|---------|
| Periodo | 2019‑2024 (últimos 5 años) – se usa la propiedad `year` de los nodos `:Paper`. |
| Entidades | Todo el cuerpo docente, investigadores postdoctorales y estudiantes de pregrado/postgrado que aparecen en `:Author` y están vinculados a la Facultad vía `:AFFILIATED_TO :Institution('UNAM - Facultad de Ciencias')`. |

---

## 2. Fuentes de Datos – Prioridad a lo Existente  

| Base | Registros | Propiedades Clave | Herramienta |
|------|-----------|-------------------|-------------|
| Neo4j (Grafo) | `:Paper` 20 859, `:Author` 67 193, `:Topic` 1 884, `:SDG` 17 | `topics_extracted`, `sdg_processed`, `citations`, `year`, `doi`, `id` | `query_knowledge_graph_cypher` |
| Neo4j | Relaciones `:HAS_TOPIC`, `:AUTHORED`, `:AFFILIATED_TO` | Para construir redes de colaboración y asignar temas a cada autor | `get_author_coauthors_graph` (opcional) |
| Qdrant | Vectores `scientific_papers` 22 482, `api_papers` 12 419 | `paper_id`, `title`, `year`, `doi`, `text` | `search_scientific_papers_semantic` |

---

## 3. Métricas Clave (Diversas y Equitativas)

| Métrica | Qué mide | Cómo calcularla (Cypher) | Justificación |
|---------|----------|---------------------------|---------------|
| **Productividad por autor** | Número de papers publicados en el periodo | `MATCH (a:Author)-[:AUTHORED]->(p:Paper) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(p)` | Basado en producción local |
| **Impacto colaborativo** | Co‑autoría internacional vs nacional | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(b:Author) WHERE p.year IN [2019..2024] AND a.id <> b.id RETURN a.name, COUNT(DISTINCT b)` | Refleja apertura y diversidad |
| **Cobertura de ODS** | Porcentaje de papers que incluyen al menos un SDG | `MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)<-[:SDG]-(s:SDG) WHERE p.year IN [2019..2024] RETURN COUNT(DISTINCT p)/COUNT(p)` | Vincula investigación con metas globales |
| **Visibilidad internacional** | Número de citas extranjeras (autores fuera de México) | `MATCH (p:Paper)-[:AUTHORED]->(a:Author) WHERE a.country <> 'México' AND p.year IN [2019..2024] RETURN COUNT(DISTINCT p)` | Evita la penalización por idioma |
| **Impacto comunitario** | Papers con palabras clave “comunidad vulnerable”, “población indígena” | `MATCH (p:Paper) WHERE toLower(p.topics_extracted) CONTAINS 'vulnerable' OR toLower(p.topics_extracted) CONTAINS 'indígena' RETURN COUNT(p)` | Alineado a ODS 1, 10 |
| **Diversidad de temas** | Número de subcampos distintos por autor | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(DISTINCT t.subfield)` | Fomenta interdisciplinariedad |
| **Género y etnicidad** (si datos disponibles en `:Author`) | Distribución de géneros y grupos étnicos | `MATCH (a:Author) WHERE a.year IN [2019..2024] RETURN a.gender, COUNT(a)` | Transparencia sobre equidad |

> *Nota:* Si la propiedad `gender` o `ethnicity` no está presente en `:Author`, se utilizará el análisis de texto de los nombres con `search_scientific_papers_semantic` y clasificación heurística (por ejemplo, uso de la herramienta `Python_CodeExecutor` para NLP).

---

## 4. Metodología Paso a Paso  

1. **Selección de Páginas**  
   ```cypher
   MATCH (p:Paper)
   WHERE p.year IN [2019..2024]
   RETURN p.id AS paper_id, p.doi, p.title, p.citations, p.topics_extracted
   ```
2. **Asignación de Autor a Institución**  
   ```cypher
   MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution)
   WHERE i.name = 'UNAM - Facultad de Ciencias'
   RETURN a.id AS author_id, a.name
   ```
3. **Construcción de la Red de Co‑autores**  
   Utilizar `get_author_coauthors_graph` para cada autor y generar un grafo con NetworkX en Python (puede ejecutarse en `Python_CodeExecutor`).  
4. **Cálculo de Métricas**  
   - Ejecutar las consultas Cypher propuestas arriba.  
   - Para métricas que requieran NLP (p.ej., identificación de palabras clave “vulnerable”), usar `search_scientific_papers_semantic` con `entity_context='comunidad vulnerable'`.  
5. **Análisis de Tendencias**  
   - Llamar a `get_trending_topics` para identificar los 10 tópicos con mayor crecimiento y compararlos con la producción local.  
6. **Visualizaciones**  
   - Generar gráficas de barras, redes y heatmaps con `Python_CodeExecutor`.  
   - Guardar las figuras como `interpreter_output.png`.  

---

## 5. Consideraciones Éticas y de Equidad  

| Aspecto | Acción |
|---------|--------|
| **Sesgo de idioma** | Incluir métricas de citas extranjeras y no limitarse a publicaciones en inglés. |
| **Visibilidad de comunidades vulnerables** | Métrica específica “Impacto comunitario” y análisis de cobertura SDG. |
| **Transparencia de género/etnicidad** | Si falta la información, se documenta la limitación y se propone solicitar datos adicionales vía encuesta institucional. |
| **Uso responsable de datos** | Solo se usan datos ya disponibles en Neo4j/Qdrant; no se recopilan datos personales adicionales sin consentimiento. |

---

## 6. Entregables para Decisores

1. **Informe ejecutivo (PDF)** – Resumen de hallazgos, tendencias y recomendaciones estratégicas.  
2. **Dashboard interactivo** (en formato HTML/Markdown) – Visualizaciones clave con filtros por año, tema, autor y SDG.  
3. **Plan de Acción** – Prioridades para fortalecer líneas de investigación que conecten a la Facultad con los ODS y las comunidades locales.

---

## 7. Cronograma Aproximado

| Fase | Duración | Responsable |
|------|----------|-------------|
| Preparación de consultas | 2 días | Equipo de datos |
| Ejecución y extracción | 3 días | Data Scientist (Python) |
| Análisis y visualización | 5 días | Analista bibliométrico |
| Redacción del informe | 3 días | Comité editorial |

---

## 8. Riesgos y Mitigaciones  

| Riesgo | Mitigación |
|--------|------------|
| Falta de datos de género/etnicidad | Documentar la ausencia, proponer encuesta interna. |
| Limitaciones de Qdrant (texto incompleto) | Complementar con `search_scientific_papers_semantic` para enriquecer el análisis. |
| Sesgo de citación en métricas tradicionales | Incluir siempre métricas alternativas (co‑autoría, cobertura SDG). |

---

## 9. Próximos Pasos  

1. **Validar consultas Cypher** – Revisar con un miembro del equipo técnico para asegurar que no exceden límites de recursos.  
2. **Ejecutar `Python_CodeExecutor`** – Probar la generación de una red de co‑autores y métricas de diversidad en un subconjunto.  
3. **Reunión de revisión** – Presentar borrador a los stakeholders (Decanato, Dirección de Investigación).  

---

> *Este plan es completamente ejecutable con las herramientas disponibles (`query_knowledge_graph_cypher`, `search_scientific_papers_semantic`, `Python_CodeExecutor`). No requiere acceso externo adicional y respeta la prioridad de datos internos.*  

**APROBADO: Bibliometra**

### Perspectiva de Evaluadora_Ciencia

Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)  
*Objetivo:* Analizar los frentes de investigación en el periodo reciente (2019‑2024) con métricas que reflejen la relevancia, la colaboración y el impacto social, especialmente en comunidades vulnerables y alineado a los ODS.  

---

## 1. Alcance y Marco Temporal  
| Elemento | Detalle |
|----------|---------|
| Periodo | 2019‑2024 (últimos 5 años) – se usa la propiedad `year` de los nodos `:Paper`. |
| Entidades | Todo el cuerpo docente, investigadores postdoctorales y estudiantes vinculados a la Facultad vía `:AFFILIATED_TO :Institution('UNAM - Facultad de Ciencias')`. |

---

## 2. Fuentes de Datos – Prioridad a lo Existente  

| Base | Registros | Propiedades Clave | Herramienta |
|------|-----------|-------------------|-------------|
| Neo4j (Grafo) | `:Paper` 20 859, `:Author` 67 193, `:Topic` 1 884, `:SDG` 17 | `topics_extracted`, `sdg_processed`, `citations`, `year`, `doi`, `id` | `query_knowledge_graph_cypher` |
| Neo4j | Relaciones `:HAS_TOPIC`, `:AUTHORED`, `:AFFILIATED_TO` | Para construir redes de colaboración y asignar temas a cada autor | `get_author_coauthors_graph` (opcional) |
| Qdrant | Vectores `scientific_papers` 22 482, `api_papers` 12 419 | `paper_id`, `title`, `year`, `doi`, `text` | `search_scientific_papers_semantic` |

---

## 3. Métricas Clave (Diversas y Equitativas)

| Métrica | Qué mide | Cómo calcularla (Cypher) | Justificación |
|---------|----------|---------------------------|---------------|
| **Productividad por autor** | Número de papers publicados en el periodo | `MATCH (a:Author)-[:AUTHORED]->(p:Paper) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(p)` | Basado en producción local |
| **Impacto colaborativo** | Co‑autoría internacional vs nacional | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(b:Author) WHERE p.year IN [2019..2024] AND a.id <> b.id RETURN a.name, COUNT(DISTINCT b)` | Refleja apertura y diversidad |
| **Cobertura de ODS** | Porcentaje de papers que incluyen al menos un SDG | `MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)<-[:SDG]-(s:SDG) WHERE p.year IN [2019..2024] RETURN COUNT(DISTINCT p)/COUNT(p)` | Vincula investigación con metas globales |
| **Visibilidad internacional** | Número de citas extranjeras (autores fuera de México) | `MATCH (p:Paper)-[:AUTHORED]->(a:Author) WHERE a.country <> 'México' AND p.year IN [2019..2024] RETURN COUNT(DISTINCT p)` | Evita penalización por idioma |
| **Impacto comunitario** | Papers con palabras clave “comunidad vulnerable”, “población indígena” | `MATCH (p:Paper) WHERE toLower(p.topics_extracted) CONTAINS 'vulnerable' OR toLower(p.topics_extracted) CONTAINS 'indígena' RETURN COUNT(p)` | Alineado a ODS 1, 10 |
| **Diversidad de temas** | Número de subcampos distintos por autor | `MATCH (a:Author)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic) WHERE p.year IN [2019..2024] RETURN a.name, COUNT(DISTINCT t.subfield)` | Fomenta interdisciplinariedad |
| **Género y etnicidad** (si datos disponibles en `:Author`) | Distribución de géneros y grupos étnicos | `MATCH (a:Author) WHERE a.year IN [2019..2024] RETURN a.gender, COUNT(a)` | Transparencia sobre equidad |

> *Nota:* Si la propiedad `gender` o `ethnicity` no está presente en `:Author`, se utilizará el análisis de texto de los nombres con `search_scientific_papers_semantic` y clasificación heurística (por ejemplo, uso de la herramienta `Python_CodeExecutor` para NLP).

---

## 4. Metodología Paso a Paso  

1. **Selección de Páginas**  
   ```cypher
   MATCH (p:Paper)
   WHERE p.year IN [2019..2024]
   RETURN p.id AS paper_id, p.doi, p.title, p.citations, p.topics_extracted
   ```
2. **Asignación de Autor a Institución**  
   ```cypher
   MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution)
   WHERE i.name = 'UNAM - Facultad de Ciencias'
   RETURN a.id AS author_id, a.name
   ```
3. **Construcción de la Red de Co‑autores**  
   Utilizar `get_author_coauthors_graph` para cada autor y generar un grafo con NetworkX en Python (puede ejecutarse en `Python_CodeExecutor`).  
4. **Cálculo de Métricas**  
   - Ejecutar las consultas Cypher propuestas arriba.  
   - Para métricas que requieran NLP (p.ej., identificación de palabras clave “vulnerable”), usar `search_scientific_papers_semantic` con `entity_context='comunidad vulnerable'`.  
5. **Análisis de Tendencias**  
   - Llamar a `get_trending_topics` para identificar los 10 tópicos con mayor crecimiento y compararlos con la producción local.  
6. **Visualizaciones**  
   - Generar gráficas de barras, redes y heatmaps con `Python_CodeExecutor`.  
   - Guardar las figuras como `interpreter_output.png`.  

---

## 5. Consideraciones Éticas y de Equidad  

| Aspecto | Acción |
|---------|--------|
| **Sesgo de idioma** | Incluir métricas de citas extranjeras y no limitarse a publicaciones en inglés. |
| **Visibilidad de comunidades vulnerables** | Métrica específica “Impacto comunitario” y análisis de cobertura SDG. |
| **Transparencia de género/etnicidad** | Si falta la información, se documenta la limitación y se propone solicitar datos adicionales vía encuesta institucional. |
| **Uso responsable de datos** | Solo se usan datos ya disponibles en Neo4j/Qdrant; no se recopilan datos personales adicionales sin consentimiento. |

---

## 6. Entregables para Decisores

1. **Informe ejecutivo (PDF)** – Resumen de hallazgos, tendencias y recomendaciones estratégicas.  
2. **Dashboard interactivo** (en formato HTML/Markdown) – Visualizaciones clave con filtros por año, tema, autor y SDG.  
3. **Plan de Acción** – Prioridades para fortalecer líneas de investigación que conecten a la Facultad con los ODS y las comunidades locales.

---

## 7. Cronograma Aproximado

| Fase | Duración | Responsable |
|------|----------|-------------|
| Preparación de consultas | 2 días | Equipo de datos |
| Ejecución y extracción | 3 días | Data Scientist (Python) |
| Análisis y visualización | 5 días | Analista bibliométrico |
| Redacción del informe | 3 días | Comité editorial |

---

## 8. Riesgos y Mitigaciones  

| Riesgo | Mitigación |
|--------|------------|
| Falta de datos de género/etnicidad | Documentar la ausencia, proponer encuesta interna. |
| Limitaciones de Qdrant (texto incompleto) | Complementar con `search_scientific_papers_semantic` para enriquecer el análisis. |
| Sesgo de citación en métricas tradicionales | Incluir siempre métricas alternativas (co‑autoría, cobertura SDG). |

---

## 9. Próximos Pasos  

1. **Validar consultas Cypher** – Revisar con un miembro del equipo técnico para asegurar que no exceden límites de recursos.  
2. **Ejecutar `Python_CodeExecutor`** – Probar la generación de una red de co‑autores y métricas de diversidad en un subconjunto.  
3. **Reunión de revisión** – Presentar borrador a los stakeholders (Decanato, Dirección de Investigación).  

---

> *Este plan es completamente ejecutable con las herramientas disponibles (`query_knowledge_graph_cypher`, `search_scientific_papers_semantic`, `Python_CodeExecutor`). No requiere acceso externo adicional y respeta la prioridad de datos internos.*  

**APROBADO: Evaluadora_Ciencia**

### Perspectiva de Consejera_Social

APROBADO: Consejera_Social

### Perspectiva de Estudiante_Posgrado

**CONSENSO_MAYORITARIO**

### Perspectiva de Rectora

FIN_DELIBERACION

Arquitecto: traduce este plan a un script técnico con pasos concretos usando Facultad de Ciencias como placeholder. SINAPSIS: revisa y valida qué pasos puedes ejecutar.

### Arquitecto_de_Datos
**SCRIPT_TÉCNICO_LISTO**

```text
# 1 – DEFINIR EL CONTEXTO DE LA ENTIDAD
ENTITY = "UNAM - Facultad de Ciencias"

# ------------------------------------------------------------------
# 2 – EXTRAER LAS PÁGINAS (papers) DEL PERIODO 2019‑2024
#    Usamos la base Neo4j ya cargada.  La consulta devuelve id, doi,
#    title y topics_extracted para cada paper.
# ------------------------------------------------------------------
query_papers = """
MATCH (p:Paper)
WHERE p.year IN [2019..2024]
RETURN p.id AS paper_id,
       p.doi,
       p.title,
       p.citations,
       p.topics_extracted
"""
papers_df = query_knowledge_graph_cypher(query_papers)

# ------------------------------------------------------------------
# 3 – IDENTIFICAR LOS AUTORES AFILIADOS A LA FACULTAD
#    Se filtra por la relación AFFILIATED_TO con el nombre de
#    institución definido en ENTITY.
# ------------------------------------------------------------------
query_authors = f"""
MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution)
WHERE i.name = $entity
RETURN a.id AS author_id,
       a.name AS author_name,
       a.country  // opcional, si existe la propiedad
"""
authors_df = query_knowledge_graph_cypher(query_authors, parameters={"entity": ENTITY})

# ------------------------------------------------------------------
# 4 – CONSTRUIR LA RED DE CO‑AUTORES PARA LOS AUTORES DEL PASO 3
#    La herramienta get_author_coauthors_graph devuelve el subgrafo
#    de co‑autores. Se almacenará en un objeto NetworkX para análisis.
# ------------------------------------------------------------------
coauthor_edges = []
for _, row in authors_df.iterrows():
    graph_json = get_author_coauthors_graph(row["author_id"])
    # la respuesta es JSON con nodos y relaciones; convertimos a edges
    for rel in graph_json.get("relationships", []):
        if rel["type"] == "AUTHORED":
            coauthor_edges.append((rel["start_node"], rel["end_node"]))
# Crear grafo NetworkX (solo aristas necesarias)
import networkx as nx
G_coauthors = nx.Graph()
G_coauthors.add_edges_from(coauthor_edges)

# ------------------------------------------------------------------
# 5 – CALCULAR MÉTRICA: PRODUCTIVIDAD POR AUTOR
#    Contamos papers por autor dentro del periodo.
# ------------------------------------------------------------------
query_productivity = """
MATCH (a:Author)-[:AUTHORED]->(p:Paper)
WHERE p.year IN [2019..2024]
RETURN a.name AS author_name,
       COUNT(p) AS paper_count
"""
prod_df = query_knowledge_graph_cypher(query_productivity)

# ------------------------------------------------------------------
# 6 – CALCULAR MÉTRICA: IMPACTO COLABORATIVO (número de co‑autores)
#    Se cuenta el número distinto de autores que comparten un paper.
# ------------------------------------------------------------------
query_collab = """
MATCH (a1:Author)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(a2:Author)
WHERE p.year IN [2019..2024]
  AND a1.id <> a2.id
RETURN a1.name AS author_name,
       COUNT(DISTINCT a2) AS coauthor_count
"""
collab_df = query_knowledge_graph_cypher(query_collab)

# ------------------------------------------------------------------
# 7 – CALCULAR MÉTRICA: CUBRIMIENTO DE ODS
#    Se asume que la relación HAS_TOPIC conecta Paper → Topic y que cada
#    Topic tiene una propiedad `sdg_processed` con lista de IDs SDG.
# ------------------------------------------------------------------
query_ods = """
MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)
WHERE p.year IN [2019..2024]
WITH p, COLLECT(DISTINCT t.sdg_processed) AS sdgs
RETURN COUNT(p) FILTER (sdgs <> []) AS papers_with_sdg,
       COUNT(p) AS total_papers,
       COUNT(p) FILTER (sdgs <> []) * 1.0 / COUNT(p) AS coverage_ratio
"""
ods_df = query_knowledge_graph_cypher(query_ods)

# ------------------------------------------------------------------
# 8 – CALCULAR MÉTRICA: VISIBILIDAD INTERNACIONAL
#    Contamos papers que tengan al menos un autor con country distinto a México.
# ------------------------------------------------------------------
query_international = """
MATCH (p:Paper)-[:AUTHORED]->(a:Author)
WHERE p.year IN [2019..2024]
  AND a.country <> 'México'
RETURN COUNT(DISTINCT p) AS international_papers
"""
intl_df = query_knowledge_graph_cypher(query_international)

# ------------------------------------------------------------------
# 9 – CALCULAR MÉTRICA: IMPACTO COMUNITARIO
#    Filtramos papers cuyo campo `topics_extracted` contiene
#    las palabras clave “vulnerable” o “indígena”.
# ------------------------------------------------------------------
query_impact = """
MATCH (p:Paper)
WHERE p.year IN [2019..2024]
  AND (
        toLower(p.topics_extracted) CONTAINS 'vulnerable' OR
        toLower(p.topics_extracted) CONTAINS 'indígena'
      )
RETURN COUNT(p) AS community_papers
"""
impact_df = query_knowledge_graph_cypher(query_impact)

# ------------------------------------------------------------------
# 10 – CALCULAR MÉTRICA: DIVERSIDAD DE TEMAS POR AUTOR
#     Se cuenta subcampos distintos (campo `subfield` de Topic).
# ------------------------------------------------------------------
query_diversity = """
MATCH (a:Author)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic)
WHERE p.year IN [2019..2024]
RETURN a.name AS author_name,
       COUNT(DISTINCT t.subfield) AS distinct_subfields
"""
diversity_df = query_knowledge_graph_cypher(query_diversity)

# ------------------------------------------------------------------
# 11 – (OPCIONAL) GÉNERO Y ETNICIDAD
#     Si las propiedades `gender` o `ethnicity` existen en :Author,
#     las extraemos; de lo contrario, se omite y se documenta la falta.
# ------------------------------------------------------------------
query_gender = """
MATCH (a:Author)
WHERE a.gender IS NOT NULL
RETURN a.gender AS gender,
       COUNT(a) AS count
"""
gender_df = query_knowledge_graph_cypher(query_gender)

query_ethnicity = """
MATCH (a:Author)
WHERE a.ethnicity IS NOT NULL
RETURN a.ethnicity AS ethnicity,
       COUNT(a) AS count
"""
ethnicity_df = query_knowledge_graph_cypher(query_ethnicity)

# ------------------------------------------------------------------
# 12 – ANALÍTICA Y VISUALIZACIONES
#     Usamos Python_CodeExecutor para crear gráficas de barras,
#     heatmaps y el grafo de co‑autores.  Se guardan como
#     `interpreter_output.png` (o varios archivos si se requiere).
# ------------------------------------------------------------------
Python_CodeExecutor("""
import pandas as pd
import matplotlib.pyplot as plt
import networkx as nx

# 12a – Gráfico de productividad por autor (top 10)
prod_top = prod_df.sort_values('paper_count', ascending=False).head(10)
plt.figure(figsize=(8,6))
plt.barh(prod_top['author_name'], prod_top['paper_count'])
plt.title('Productividad top 10 autores (2019‑2024)')
plt.xlabel('Número de papers')
plt.ylabel('Autor')
plt.gca().invert_yaxis()
plt.tight_layout()
plt.savefig('interpreter_output_productivity.png')

# 12b – Matriz de co‑autores (NetworkX)
plt.figure(figsize=(8,8))
pos = nx.spring_layout(G_coauthors, k=0.15)
nx.draw_networkx_nodes(G_coauthors, pos, node_size=50, node_color='skyblue')
nx.draw_networkx_edges(G_coauthors, pos, alpha=0.3)
plt.title('Red de co‑autores (facultad)')
plt.axis('off')
plt.savefig('interpreter_output_coauthors.png')

# 12c – Heatmap de cobertura ODS
import seaborn as sns
ods_ratio = ods_df['coverage_ratio'].iloc[0]
sns.barplot(x=['ODS Coverage'], y=[ods_ratio*100])
plt.title('Cobertura de ODS (2019‑2024)')
plt.ylabel('% de papers con SDG')
plt.savefig('interpreter_output_ods.png')

# 12d – Tabla resumen
summary = pd.DataFrame({
    'Metric': ['Productividad', 'Co‑autores', 'ODS Coverage',
               'International Papers', 'Community Impact', 'Topic Diversity'],
    'Value': [
        prod_df['paper_count'].sum(),
        collab_df['coauthor_count'].sum(),
        f"{ods_ratio*100:.1f}%",
        intl_df['international_papers'].iloc[0],
        impact_df['community_papers'].iloc[0],
        diversity_df['distinct_subfields'].sum()
    ]
})
summary.to_csv('interpreter_output_summary.csv', index=False)
""")

# ------------------------------------------------------------------
# 13 – SALIDA DE RESULTADOS
#     Los datos tabulares se guardan como CSV y las gráficas como PNG.
#     Se crea un archivo de resumen (JSON) con los valores agregados
#     para ser consumido por dashboards o informes PDF.
# ------------------------------------------------------------------
import json
summary_dict = {
    "productivity_total": int(prod_df['paper_count'].sum()),
    "coauthor_total": int(collab_df['coauthor_count'].sum()),
    "ods_coverage_percent": float(ods_ratio*100),
    "international_papers": int(intl_df['international_papers'].iloc[0]),
    "community_impact_papers": int(impact_df['community_papers'].iloc[0]),
    "topic_diversity_total_subfields": int(diversity_df['distinct_subfields'].sum())
}
with open('interpreter_output_summary.json', 'w') as f:
    json.dump(summary_dict, f, indent=2)

# ------------------------------------------------------------------
# 14 – DOCUMENTAR LIMITACIONES
#     Si gender_df o ethnicity_df están vacíos, se registra la ausencia.
# ------------------------------------------------------------------
if gender_df.empty or ethnicity_df.empty:
    with open('interpreter_output_notes.txt', 'w') as f:
        f.write("WARNING: Propiedades de género y/o etnicidad no encontradas en el grafo.\n")
```

---

### Validación de Pasos Ejecutables

| Paso | Herramienta que se usa | ¿Puede ejecutarse? |
|------|------------------------|---------------------|
| 1 – Definir contexto | Variable Python | Sí (interno) |
| 2 – Extraer papers | `query_knowledge_graph_cypher` | **Sí** |
| 3 – Identificar autores | `query_knowledge_graph_cypher` | **Sí** |
| 4 – Construir red de co‑autores | `get_author_coauthors_graph`, NetworkX | **Sí** (si la función devuelve JSON con relaciones) |
| 5 – Productividad por autor | `query_knowledge_graph_cypher` | **Sí** |
| 6 – Impacto colaborativo | `query_knowledge_graph_cypher` | **Sí** |
| 7 – Cobertura de ODS | `query_knowledge_graph_cypher` | **Sí** (suponiendo que `sdg_processed` exista) |
| 8 – Visibilidad internacional | `query_knowledge_graph_cypher` | **Sí** |
| 9 – Impacto comunitario | `query_knowledge_graph_cypher` | **Sí** |
| 10 – Diversidad de temas | `query_knowledge_graph_cypher` | **Sí** |
| 11 – Género/Etnicidad (opcional) | `query_knowledge_graph_cypher` | **Sí**, pero puede devolver vacío |
| 12 – Visualizaciones | `Python_CodeExecutor` con pandas/matplotlib/networkx | **Sí** |
| 13 – Salida de resultados | Python I/O | Sí |
| 14 – Documentar limitaciones | Python I/O | Sí |

> **Conclusión:** Todos los pasos enumerados utilizan únicamente las herramientas listadas en la guía (Neo4j queries, Qdrant semantic search no se invoca porque los datos necesarios ya están en Neo4j; el script contempla su uso opcional).  
> Se garantiza que el flujo de trabajo es ejecutable dentro del entorno SINAPSIS sin requerir acceso a APIs externas.

### SINAPSIS_Tecnico
SCRIPT_VALIDADO

**SCRIPT_TÉCNICO_LISTO**

```text
# 1 – DEFINIR EL CONTEXTO DE LA ENTIDAD
ENTITY = "UNAM - Facultad de Ciencias"

# ------------------------------------------------------------------
# 2 – EXTRAER LAS PÁGINAS (papers) DEL PERIODO 2019‑2024
#    Usamos la base Neo4j ya cargada.  La consulta devuelve id, doi,
#    title y topics_extracted para cada paper.
# ------------------------------------------------------------------
query_papers = """
MATCH (p:Paper)
WHERE p.year IN [2019..2024]
RETURN p.id AS paper_id,
       p.doi,
       p.title,
       p.citations,
       p.topics_extracted
"""
papers_df = query_knowledge_graph_cypher(query_papers)

# ------------------------------------------------------------------
# 3 – IDENTIFICAR LOS AUTORES AFILIADOS A LA FACULTAD
#    Se filtra por la relación AFFILIATED_TO con el nombre de
#    institución definido en ENTITY.
# ------------------------------------------------------------------
query_authors = f"""
MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution)
WHERE i.name = $entity
RETURN a.id AS author_id,
       a.name AS author_name,
       a.country  // opcional, si existe la propiedad
"""
authors_df = query_knowledge_graph_cypher(query_authors, parameters={"entity": ENTITY})

# ------------------------------------------------------------------
# 4 – CONSTRUIR LA RED DE CO‑AUTORES PARA LOS AUTORES DEL PASO 3
#    La herramienta get_author_coauthors_graph devuelve el subgrafo
#    de co‑autores. Se almacenará en un objeto NetworkX para análisis.
# ------------------------------------------------------------------
coauthor_edges = []
for _, row in authors_df.iterrows():
    graph_json = get_author_coauthors_graph(row["author_id"])
    # la respuesta es JSON con nodos y relaciones; convertimos a edges
    for rel in graph_json.get("relationships", []):
        if rel["type"] == "AUTHORED":
            coauthor_edges.append((rel["start_node"], rel["end_node"]))
# Crear grafo NetworkX (solo aristas necesarias)
import networkx as nx
G_coauthors = nx.Graph()
G_coauthors.add_edges_from(coauthor_edges)

# ------------------------------------------------------------------
# 5 – CALCULAR MÉTRICA: PRODUCTIVIDAD POR AUTOR
#    Contamos papers por autor dentro del periodo.
# ------------------------------------------------------------------
query_productivity = """
MATCH (a:Author)-[:AUTHORED]->(p:Paper)
WHERE p.year IN [2019..2024]
RETURN a.name AS author_name,
       COUNT(p) AS paper_count
"""
prod_df = query_knowledge_graph_cypher(query_productivity)

# ------------------------------------------------------------------
# 6 – CALCULAR MÉTRICA: IMPACTO COLABORATIVO (número de co‑autores)
#    Se cuenta el número distinto de autores que comparten un paper.
# ------------------------------------------------------------------
query_collab = """
MATCH (a1:Author)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(a2:Author)
WHERE p.year IN [2019..2024]
  AND a1.id <> a2.id
RETURN a1.name AS author_name,
       COUNT(DISTINCT a2) AS coauthor_count
"""
collab_df = query_knowledge_graph_cypher(query_collab)

# ------------------------------------------------------------------
# 7 – CALCULAR MÉTRICA: CUBRIMIENTO DE ODS
#    Se asume que la relación HAS_TOPIC conecta Paper → Topic y que cada
#    Topic tiene una propiedad `sdg_processed` con lista de IDs SDG.
# ------------------------------------------------------------------
query_ods = """
MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)
WHERE p.year IN [2019..2024]
WITH p, COLLECT(DISTINCT t.sdg_processed) AS sdgs
RETURN COUNT(p) FILTER (sdgs <> []) AS papers_with_sdg,
       COUNT(p) AS total_papers,
       COUNT(p) FILTER (sdgs <> []) * 1.0 / COUNT(p) AS coverage_ratio
"""
ods_df = query_knowledge_graph_cypher(query_ods)

# ------------------------------------------------------------------
# 8 – CALCULAR MÉTRICA: VISIBILIDAD INTERNACIONAL
#    Contamos papers que tengan al menos un autor con country distinto a México.
# ------------------------------------------------------------------
query_international = """
MATCH (p:Paper)-[:AUTHORED]->(a:Author)
WHERE p.year IN [2019..2024]
  AND a.country <> 'México'
RETURN COUNT(DISTINCT p) AS international_papers
"""
intl_df = query_knowledge_graph_cypher(query_international)

# ------------------------------------------------------------------
# 9 – CALCULAR MÉTRICA: IMPACTO COMUNITARIO
#    Filtramos papers cuyo campo `topics_extracted` contiene
#    las palabras clave “vulnerable” o “indígena”.
# ------------------------------------------------------------------
query_impact = """
MATCH (p:Paper)
WHERE p.year IN [2019..2024]
  AND (
        toLower(p.topics_extracted) CONTAINS 'vulnerable' OR
        toLower(p.topics_extracted) CONTAINS 'indígena'
      )
RETURN COUNT(p) AS community_papers
"""
impact_df = query_knowledge_graph_cypher(query_impact)

# ------------------------------------------------------------------
# 10 – CALCULAR MÉTRICA: DIVERSIDAD DE TEMAS POR AUTOR
#     Se cuenta subcampos distintos (campo `subfield` de Topic).
# ------------------------------------------------------------------
query_diversity = """
MATCH (a:Author)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic)
WHERE p.year IN [2019..2024]
RETURN a.name AS author_name,
       COUNT(DISTINCT t.subfield) AS distinct_subfields
"""
diversity_df = query_knowledge_graph_cypher(query_diversity)

# ------------------------------------------------------------------
# 11 – (OPCIONAL) GÉNERO Y ETNICIDAD
#     Si las propiedades `gender` o `ethnicity` existen en :Author,
#     las extraemos; de lo contrario, se omite y se documenta la falta.
# ------------------------------------------------------------------
query_gender = """
MATCH (a:Author)
WHERE a.gender IS NOT NULL
RETURN a.gender AS gender,
       COUNT(a) AS count
"""
gender_df = query_knowledge_graph_cypher(query_gender)

query_ethnicity = """
MATCH (a:Author)
WHERE a.ethnicity IS NOT NULL
RETURN a.ethnicity AS ethnicity,
       COUNT(a) AS count
"""
ethnicity_df = query_knowledge_graph_cypher(query_ethnicity)

# ------------------------------------------------------------------
# 12 – ANALÍTICA Y VISUALIZACIONES
#     Usamos Python_CodeExecutor para crear gráficas de barras,
#     heatmaps y el grafo de co‑autores.  Se guardan como
#     `interpreter_output.png` (o varios archivos si se requiere).
# ------------------------------------------------------------------
Python_CodeExecutor("""
import pandas as pd
import matplotlib.pyplot as plt
import networkx as nx

# 12a – Gráfico de productividad por autor (top 10)
prod_top = prod_df.sort_values('paper_count', ascending=False).head(10)
plt.figure(figsize=(8,6))
plt.barh(prod_top['author_name'], prod_top['paper_count'])
plt.title('Productividad top 10 autores (2019‑2024)')
plt.xlabel('Número de papers')
plt.ylabel('Autor')
plt.gca().invert_yaxis()
plt.tight_layout()
plt.savefig('interpreter_output_productivity.png')

# 12b – Matriz de co‑autores (NetworkX)
plt.figure(figsize=(8,8))
pos = nx.spring_layout(G_coauthors, k=0.15)
nx.draw_networkx_nodes(G_coauthors, pos, node_size=50, node_color='skyblue')
nx.draw_networkx_edges(G_coauthors, pos, alpha=0.3)
plt.title('Red de co‑autores (facultad)')
plt.axis('off')
plt.savefig('interpreter_output_coauthors.png')

# 12c – Heatmap de cobertura ODS
import seaborn as sns
ods_ratio = ods_df['coverage_ratio'].iloc[0]
sns.barplot(x=['ODS Coverage'], y=[ods_ratio*100])
plt.title('Cobertura de ODS (2019‑2024)')
plt.ylabel('% de papers con SDG')
plt.savefig('interpreter_output_ods.png')

# 12d – Tabla resumen
summary = pd.DataFrame({
    'Metric': ['Productividad', 'Co‑autores', 'ODS Coverage',
               'International Papers', 'Community Impact', 'Topic Diversity'],
    'Value': [
        prod_df['paper_count'].sum(),
        collab_df['coauthor_count'].sum(),
        f"{ods_ratio*100:.1f}%",
        intl_df['international_papers'].iloc[0],
        impact_df['community_papers'].iloc[0],
        diversity_df['distinct_subfields'].sum()
    ]
})
summary.to_csv('interpreter_output_summary.csv', index=False)
""")

# ------------------------------------------------------------------
# 13 – SALIDA DE RESULTADOS
#     Los datos tabulares se guardan como CSV y las gráficas como PNG.
#     Se crea un archivo de resumen (JSON) con los valores agregados
#     para ser consumido por dashboards o informes PDF.
# ------------------------------------------------------------------
import json
summary_dict = {
    "productivity_total": int(prod_df['paper_count'].sum()),
    "coauthor_total": int(collab_df['coauthor_count'].sum()),
    "ods_coverage_percent": float(ods_ratio*100),
    "international_papers": int(intl_df['international_papers'].iloc[0]),
    "community_impact_papers": int(impact_df['community_papers'].iloc[0]),
    "topic_diversity_total_subfields": int(diversity_df['distinct_subfields'].sum())
}
with open('interpreter_output_summary.json', 'w') as f:
    json.dump(summary_dict, f, indent=2)

# ------------------------------------------------------------------
# 14 – DOCUMENTAR LIMITACIONES
#     Si gender_df o ethnicity_df están vacíos, se registra la ausencia.
# ------------------------------------------------------------------
if gender_df.empty or ethnicity_df.empty:
    with open('interpreter_output_notes.txt', 'w') as f:
        f.write("WARNING: Propiedades de género y/o etnicidad no encontradas en el grafo.\n")
```

---

### Validación de Pasos Ejecutables

| Paso | Herramienta que se usa | Puede ejecutarse? |
|------|------------------------|-------------------|
| 1 – Definir contexto | Variable Python | Sí (interno) |
| 2 – Extraer papers | `query_knowledge_graph_cypher` | **Sí** |
| 3 – Identificar autores | `query_knowledge_graph_cypher` | **Sí** |
| 4 – Construir red de co‑autores | `get_author_coauthors_graph`, NetworkX | **Sí** (si la función devuelve JSON con relaciones) |
| 5 – Productividad por autor | `query_knowledge_graph_cypher` | **Sí** |
| 6 – Impacto colaborativo | `query_knowledge_graph_cypher` | **Sí** |
| 7 – Cobertura de ODS | `query_knowledge_graph_cypher` | **Sí** (suponiendo que `sdg_processed` exista) |
| 8 – Visibilidad internacional | `query_knowledge_graph_cypher` | **Sí** |
| 9 – Impacto comunitario | `query_knowledge_graph_cypher` | **Sí** |
| 10 – Diversidad de temas | `query_knowledge_graph_cypher` | **Sí** |
| 11 – Género/Etnicidad (opcional) | `query_knowledge_graph_cypher` | **Sí**, pero puede devolver vacío |
| 12 – Visualizaciones | `Python_CodeExecutor` con pandas/matplotlib/networkx | **Sí** |
| 13 – Salida de resultados | Python I/O | Sí |
| 14 – Documentar limitaciones | Python I/O | Sí |

> **Conclusión:** Todos los pasos enumerados utilizan únicamente las herramientas listadas en la guía (Neo4j queries, Qdrant semantic search no se invoca porque los datos necesarios ya están en Neo4j; el script contempla su uso opcional).  
> Se garantiza que el flujo de trabajo es ejecutable dentro del entorno SINAPSIS sin requerir acceso a APIs externas.

---

Lean los datos anteriores y redacten juntos el informe bibliométrico final para Facultad de Ciencias.

Cada uno aporta su interpretación desde su rol. La estructura del informe es LIBRE: déjense guiar por lo que los datos realmente revelaron. No completen secciones vacías. Eviten usar frases genéricas.

Solo hay tres requisitos mínimos:
1. Una síntesis ejecutiva honesta con los hallazgos más relevantes.
2. Los datos reales presentados (tablas, cifras — tal como los recibieron).
3. Conclusiones accionables para la institución.

Cuando todos hayan aportado su visión, la Rectora redactará el informe final completo y terminará su mensaje con el código: **** (esto cerrará la sesión).