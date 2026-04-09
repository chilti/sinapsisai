# Informe Bibliométrico Final

**Entidad**: FACULTAD DE CIENCIAS
**Generado**: 2026-04-07_1637

---

# Datos recopilados para FACULTAD DE CIENCIAS

[{"name": "Facultad de Ciencias", "num_documents": null, "citations": null, "pct_open_access": null}]

| name                 | num_documents   | citations   | pct_open_access   |
|:---------------------|:----------------|:------------|:------------------|
| Facultad de Ciencias |                 |             |                   |


**Resultado [PASO 1]:** Intenté cargar los archivos Parquet de métricas institucionales, pero los ficheros no existen en el entorno actual (`data/cache/FACULTAD DE CIENCIAS/institucion_total.parquet` y `institucion_annual.parquet`).  

Pasaré al siguiente bloque disponible.

---

## 2. Cargar lista de papers institucionales

```python
# Paso 2 – Papers con todas las afiliaciones (incluye OA, citas, etc.)
papers_inst_path = f'data/cache/FACULTAD DE CIENCIAS/papers_institucion.parquet'
```

**Resultado [PASO 2]:** El archivo `data/cache/FACULTAD DE CIENCIAS/papers_institucion.parquet` tampoco está presente. No se puede continuar con la carga de papers.

---

## 3. Cargar perfiles completos de cada investigador

```python
# Paso 3 – Perfil completo (incluye trabajos anteriores)
prof_path   = f'data/cache/FACULTAD DE CIENCIAS/papers_profesor.parquet'
```

**Resultado [PASO 3]:** El archivo `data/cache/FACULTAD DE CIENCIAS/papers_profesor.parquet` no existe.  

---

## 4. Cargar jerarquía temática por investigador

```python
# Paso 4 – Tópicos extraídos (en inglés)
topics_path   = f'data/cache/FACULTAD DE CIENCIAS/topics_investigador.parquet'
```

**Resultado [PASO 4]:** El archivo `data/cache/FACULTAD DE CIENCIAS/topics_investigador.parquet` no está disponible.

---

## 5. Cargar palabras clave por investigador

```python
# Paso 5 – Palabras clave (para análisis de sesgo lingüístico)
kw_path   = f'data/cache/FACULTAD DE CIENCIAS/keywords_investigador.parquet'
```

**Resultado [PASO 5]:** El archivo `data/cache/FACULTAD DE CIENCIAS/keywords_investigador.parquet` no existe.

---

## 6. Calcular métricas no‑tradicionales

Sin los DataFrames de pasos anteriores, este cálculo es imposible.

---

## 7. Analizar evolución temática y detectar brechas

Requiere `topics_df`, que tampoco está disponible.

---

## 8. Mapear colaboración interdisciplinaria

Requiere `topics_df` o datos de autores.

---

## 9. Generar dashboard interactivo (Streamlit)

Sin los DataFrames anteriores, no se puede crear el dashboard.

---

## 10. Consultas en Neo4j

### a) Red de coautoría de un investigador

```python
author_name = 'ALCUBIERRE MOYA, MIGUEL'
cypher_query = f"""
MATCH (a:Author {{name: $name}})-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(co:Author)
RETURN co.name AS collaborator,
       count(p) AS papers_together
ORDER BY papers_together DESC
LIMIT 10
"""
result = query_knowledge_graph_cypher(cypher_query, parameters={'name':author_name})
```

**Resultado [PASO 10a]:**  
La consulta devolvió un resultado vacío. No hay nodos `Author` con el nombre exacto o la relación no está cargada.

### b) Red de coautoría para todos los académicos de la facultad

```python
cypher_all = """
MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution {name: $entity})
MERGE (a)-[r:COAUTHORED_WITH]-(co:Author)
RETURN a.name AS author, co.name AS collaborator, count(r) AS weight
"""
result_all = query_knowledge_graph_cypher(cypher_all, parameters={'entity':ENTITY})
```

**Resultado [PASO 10b]:**  
La consulta devolvió un conjunto vacío. No hay relaciones `AFFILIATED_TO` entre autores y la institución nombrada.

---

## 11. Búsqueda semántica en Qdrant

```python
results = search_semantic(
    query="climate change",
    entity_context={"name": "Facultad de Ciencias"},
    limit=5
)
```

**Resultado [PASO 11]:**  
La herramienta `search_semantic` no está disponible en este entorno, por lo que la llamada falló.

---

## 12. Exportar resultados a archivos (para informe)

Sin datos recopilados, esta etapa no se puede ejecutar.

---

### Resumen de los hallazgos

| Paso | Acción | Resultado |
|------|--------|-----------|
| 1 | Cargar métricas institucionales | Archivo no encontrado |
| 2 | Cargar papers institucionales | Archivo no encontrado |
| 3 | Cargar perfiles de investigadores | Archivo no encontrado |
| 4 | Cargar jerarquía temática | Archivo no encontrado |
| 5 | Cargar palabras clave | Archivo no encontrado |
| 6 | Calcular métricas no‑tradicionales | No disponible |
| 7 | Analizar evolución temática | No disponible |
| 8 | Mapear colaboración interdisciplinaria | No disponible |
| 9 | Generar dashboard | No disponible |
| 10a | Red de coautoría individual | Consulta vacía |
| 10b | Red de coautoría institucional | Consulta vacía |
| 11 | Búsqueda semántica Qdrant | Herramienta no accesible |
| 12 | Exportar resultados | No disponible |

**Conclusión:** En el entorno actual no existen los archivos Parquet ni las relaciones en Neo4j necesarias para ejecutar el script completo. Se recomienda verificar la disponibilidad de los datos pre‑calculados y asegurarse de que la base de conocimiento (Neo4j) esté correctamente poblada antes de reintentar la ejecución.

****

**Resultado [PASO 1]:** Intenté cargar los archivos Parquet de métricas institucionales, pero los ficheros no existen en el entorno actual (`data/cache/FACULTAD DE CIENCIAS/institucion_total.parquet` y `institucion_annual.parquet`).  

Pasaré al siguiente bloque disponible.

---

## 2. Cargar lista de papers institucionales

```python
# Paso 2 – Papers con todas las afiliaciones (incluye OA, citas, etc.)
papers_inst_path = f'data/cache/FACULTAD DE CIENCIAS/papers_institucion.parquet'
```

**Resultado [PASO 2]:** El archivo `data/cache/FACULTAD DE CIENCIAS/papers_institucion.parquet` tampoco está presente. No se puede continuar con la carga de papers.

---

## 3. Cargar perfiles completos de cada investigador

```python
# Paso 3 – Perfil completo (incluye trabajos anteriores)
prof_path   = f'data/cache/FACULTAD DE CIENCIAS/papers_profesor.parquet'
```

**Resultado [PASO 3]:** El archivo `data/cache/FACULTAD DE CIENCIAS/papers_profesor.parquet` no existe.  

---

## 4. Cargar jerarquía temática por investigador

```python
# Paso 4 – Tópicos extraídos (en inglés)
topics_path   = f'data/cache/FACULTAD DE CIENCIAS/topics_investigador.parquet'
```

**Resultado [PASO 4]:** El archivo `data/cache/FACULTAD DE CIENCIAS/topics_investigador.parquet` no está disponible.

---

## 5. Cargar palabras clave por investigador

```python
# Paso 5 – Palabras clave (para análisis de sesgo lingüístico)
kw_path   = f'data/cache/FACULTAD DE CIENCIAS/keywords_investigador.parquet'
```

**Resultado [PASO 5]:** El archivo `data/cache/FACULTAD DE CIENCIAS/keywords_investigador.parquet` no existe.

---

## 6. Calcular métricas no‑tradicionales

Sin los DataFrames de pasos anteriores, este cálculo es imposible.

---

## 7. Analizar evolución temática y detectar brechas

Requiere `topics_df`, que tampoco está disponible.

---

## 8. Mapear colaboración interdisciplinaria

Requiere `topics_df` o datos de autores.

---

## 9. Generar dashboard interactivo (Streamlit)

Sin los DataFrames anteriores, no se puede crear el dashboard.

---

## 10. Consultas en Neo4j

### a) Red de coautoría de un investigador

```python
author_name = 'ALCUBIERRE MOYA, MIGUEL'
cypher_query = f"""
MATCH (a:Author {{name: $name}})-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(co:Author)
RETURN co.name AS collaborator,
       count(p) AS papers_together
ORDER BY papers_together DESC
LIMIT 10
"""
result = query_knowledge_graph_cypher(cypher_query, parameters={'name':author_name})
```

**Resultado [PASO 10a]:**  
La consulta devolvió un resultado vacío. No hay nodos `Author` con el nombre exacto o la relación no está cargada.

### b) Red de coautoría para todos los académicos de la facultad

```python
cypher_all = """
MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution {name: $entity})
MERGE (a)-[r:COAUTHORED_WITH]-(co:Author)
RETURN a.name AS author, co.name AS collaborator, count(r) AS weight
"""
result_all = query_knowledge_graph_cypher(cypher_all, parameters={'entity':ENTITY})
```

**Resultado [PASO 10b]:**  
La consulta devolvió un conjunto vacío. No hay relaciones `AFFILIATED_TO` entre autores y la institución nombrada.

---

## 11. Búsqueda semántica en Qdrant

```python
results = search_semantic(
    query="climate change",
    entity_context={"name": "Facultad de Ciencias"},
    limit=5
)
```

**Resultado [PASO 11]:**  
La herramienta `search_semantic` no está disponible en este entorno, por lo que la llamada falló.

---

## 12. Exportar resultados a archivos (para informe)

Sin datos recopilados, esta etapa no se puede ejecutar.

---

### Resumen de los hallazgos

| Paso | Acción | Resultado |
|------|--------|-----------|
| 1 | Cargar métricas institucionales | Archivo no encontrado |
| 2 | Cargar papers institucionales | Archivo no encontrado |
| 3 | Cargar perfiles de investigadores | Archivo no encontrado |
| 4 | Cargar jerarquía temática | Archivo no encontrado |
| 5 | Cargar palabras clave | Archivo no encontrado |
| 6 | Calcular métricas no‑tradicionales | No disponible |
| 7 | Analizar evolución temática | No disponible |
| 8 | Mapear colaboración interdisciplinaria | No disponible |
| 9 | Generar dashboard | No disponible |
| 10a | Red de coautoría individual | Consulta vacía |
| 10b | Red de coautoría institucional | Consulta vacía |
| 11 | Búsqueda semántica Qdrant | Herramienta no accesible |
| 12 | Exportar resultados | No disponible |

**Conclusión:** En el entorno actual no existen los archivos Parquet ni las relaciones en Neo4j necesarias para ejecutar el script completo. Se recomienda verificar la disponibilidad de los datos pre‑calculados y asegurarse de que la base de conocimiento (Neo4j) esté correctamente poblada antes de reintentar la ejecución.

**DATA_COLLECTION_COMPLETE**

---

Lean los datos anteriores y redacten juntos el informe bibliométrico final para FACULTAD DE CIENCIAS.

Cada experto aporta su interpretación desde su rol. La estructura del informe es LIBRE: déjense guiar por lo que los datos realmente revelaron. No completen secciones vacías. Eviten frases genéricas y abstractas; citen cifras y resultados concretos.

REGLAS DE FORMATO DEL INFORME FINAL (obligatorias para la Rectora):
1. El informe debe tener una REDACCIÓN NARRATIVA y lógica. No es una lista de datos.
2. Cada sección debe INTERPRETAR los hallazgos, no solo listarlos.    ¿Qué significa este dato para la institución? ¿Qué patrón revela?
3. Las TABLAS y FIGURAS se ANALIZAN en el texto:    describe lo que muestra cada figura, sus tendencias y su implicación.
4. El CÓDIGO Python, las consultas Cypher y cualquier instrucción técnica    van EXCLUSIVAMENTE en un 'Anexo Técnico' al final del documento,    NUNCA en el cuerpo principal del informe.
5. Requisitos mínimos de contenido:
   a) Síntesis ejecutiva honesta (máximo 3 párrafos).
   b) Análisis temático o de producción con datos reales (tablas, cifras).
   c) Interpretación de las figuras generadas (si las hay).
   d) Conclusiones accionables para la institución.
   e) Anexo Técnico (opcional, con el código al final).

Cuando todos hayan aportado su visión, la Rectora redactará el informe final completo en Markdown, siguiendo las reglas de formato anteriores, y terminará su mensaje con el código: **** (esto cerrará la sesión).