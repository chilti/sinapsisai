# Informe Bibliométrico Final

**Entidad**: Facultad de Ciencias
**Generado**: 2026-03-03_1647

---

# Datos recopilados para Facultad de Ciencias

Ejecuta el siguiente script de recopilación de datos para Facultad de Ciencias:

### Arquitecto_de_Datos
**SCRIPT_TÉCNICO_LISTO**

```text
# 1. Extracción de frentes temáticos (2019‑2023)
# --------------------------------------------------
# Consulta Cypher que devuelve:
#   - Nombre del tema (topic)
#   - Número total de publicaciones en el rango de años
#   - Promedio de citas por publicación
#   - Campos (fields) asociados al tema
#
# NOTA: Los nombres de los temas están en inglés. Se traducirán después.
query_knowledge_graph_cypher("""
    MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)
    WHERE p.year >= 2019 AND p.year <= 2023
    RETURN t.name AS topic,
           count(p) AS publications,
           avg(p.citations) AS avg_citations,
           collect(DISTINCT t.field) AS fields
    ORDER BY publications DESC
    LIMIT 20;
""")

# 2. Vinculación a los ODS
# --------------------------------------------------
# Relaciona cada tema con el ODS relevante y calcula métricas de impacto.
query_knowledge_graph_cypher("""
    MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)<-[:RELEVANT_TO]-(s:SDG)
    WHERE p.year >= 2019 AND p.year <= 2023
    RETURN s.id AS SDG,
           count(p) AS publications,
           avg(p.citations) AS avg_citations;
""")

# 3. Co‑autoría y diversidad de género/etnia (para todos los autores)
# --------------------------------------------------
# La consulta asume que `:Author` puede tener propiedades `gender` y `ethnicity`.
# Si no existen, se marcarán como 'UNKNOWN'.
query_knowledge_graph_cypher("""
    MATCH (a:Author)-[:AUTHORED]->(p:Paper)
    WHERE p.year >= 2019 AND p.year <= 2023
    WITH a,
         collect(DISTINCT p) AS papers,
         size((a)-[:AUTHORED]->(:Paper)) AS total_papers
    RETURN a.name AS author_name,
           coalesce(a.gender, 'UNKNOWN') AS gender,
           coalesce(a.ethnicity, 'UNKNOWN') AS ethnicity,
           total_papers,
           avg(size( (a)-[:AUTHORED]->(:Paper) )) AS avg_collaborations;
""")

# 4. Métricas alternativas
# --------------------------------------------------
# Se ejecutarán en Python a partir de los CSV generados por las consultas anteriores.

Python_CodeExecutor("""
import pandas as pd

# 4.a Impacto Comunitario
df_papers = pd.read_csv('papers_citations.csv')   # resultado de la consulta 1
impacto_comunitario = df_papers[df_papers['sdg_processed'] == True].shape[0]
print(f'Impacto comunitario (papers con SDG procesado): {impacto_comunitario}')

# 4.b Visibilidad Internacional
df_dois = pd.read_csv('dois.csv')                 # resultado de la consulta 1 (solo doi y año)
int_dominios = df_dois['doi'].str.contains(r'\.org|\.net|\.edu', case=False, na=False).sum()
percent_int = int_dominios / len(df_dois) * 100
print(f'Visibilidad internacional: {percent_int:.2f}%')

# 4.c Índice de Simpson para género y etnia (autor principal)
df_authors = pd.read_csv('authors_diversity.csv')
simpson_genre = 1 - sum((df_authors['gender'].value_counts(normalize=True))**2)
simpson_ethnicity = 1 - sum((df_authors['ethnicity'].value_counts(normalize=True))**2)
print(f'Índice Simpson género: {simpson_genre:.3f}')
print(f'Índice Simpson etnia: {simpson_ethnicity:.3f}')

# Guardar resultados en CSV para reporte
metrics = pd.DataFrame({
    'Metric': ['Impacto Comunitario', 'Visibilidad Internacional',
               'Simpson Género', 'Simpson Etnia'],
    'Value': [impacto_comunitario, percent_int,
              simpson_genre, simpson_ethnicity]
})
metrics.to_csv('métricas_alternativas.csv', index=False)
""")

# 5. Análisis de tendencia (temas en crecimiento)
# --------------------------------------------------
query_knowledge_graph_cypher("""
    CALL get_trending_topics() YIELD topic, growth_rate
    RETURN topic, growth_rate
    ORDER BY growth_rate DESC
    LIMIT 10;
""")

# 6. Visualizaciones con Python
# --------------------------------------------------
Python_CodeExecutor("""
import pandas as pd
from matplotlib import pyplot as plt

# 6.a Distribución de publicaciones por ODS
ods_df = pd.read_csv('ods_publications.csv')
fig, ax = plt.subplots(figsize=(10,6))
ax.bar(ods_df['SDG'], ods_df['publications'])
ax.set_title('Publicaciones por Objetivo de Desarrollo Sostenible (2019‑2023)')
ax.set_xlabel('ODS')
ax.set_ylabel('Número de publicaciones')
plt.tight_layout()
fig.savefig('interpreter_output.png')

# 6.b Top 5 temas con mayor crecimiento
growth_df = pd.read_csv('top_growth_topics.csv')
fig2, ax2 = plt.subplots(figsize=(8,5))
ax2.barh(growth_df['topic'], growth_df['growth_rate'])
ax2.set_title('Top 5 Temas en Crecimiento (2019‑2023)')
ax2.set_xlabel('Tasa de crecimiento (%)')
plt.tight_layout()
fig2.savefig('top_growth_topics.png')
""")

# 7. Búsqueda semántica por entidad (ejemplo: Facultad de Ciencias)
# --------------------------------------------------
search_scientific_papers_semantic(
    query="investigación en biología celular",
    entity_context="Facultad de Ciencias"
)

# 8. Compilación del informe
# --------------------------------------------------
# Los archivos generados:
#   - top_topics.csv
#   - ods_publications.csv
#   - authors_diversity.csv
#   - metrics_alternativas.csv
#   - top_growth_topics.csv
#   - interpreter_output.png (principal)
#   - top_growth_topics.png
#
# Se recomienda crear un notebook Jupyter que incluya:
#   1. Descripción de la metodología (incluye las consultas Cypher y Python).
#   2. Resultados tabulares (CSV) con explicación.
#   3. Gráficos guardados como PNG.
#   4. Conclusiones estratégicas para la Facultad de Ciencias.

# Fin del script técnico
```

[{"topic": "Plant and animal studies", "publications": 104, "avg_citations": 9.932692307692308, "fields": ["Agricultural and Biological Sciences"]}, {"topic": "Species Distribution and Climate Change", "publications": 86, "avg_citations": 34.13953488372093, "fields": ["Environmental Science"]}, {"topic": "Amphibian and Reptile Biology", "publications": 78, "avg_citations": 21.948717948717952, "fields": ["Environmental Science"]}, {"topic": "Ecology and Vegetation Dynamics Studies", "publications": 58, "avg_citations": 11.120689655172411, "fields": ["Environmental Science"]}, {"topic": "Wildlife Ecology and Conservation", "publications": 56, "avg_citations": 17.857142857142858, "fields": ["Environmental Science"]}, {"topic": "Genetic diversity and population structure", "publications": 42, "avg_citations": 15.738095238095239, "fields": ["Biochemistry, Genetics and Molecular Biology"]}, {"topic": "Botanical Research and Applications", "publications": 41, "avg_citations": 5.146341463414634, "fields": ["Agricultural and Biological Sciences"]}, {"topic": "Animal Behavior and Reproduction", "publications": 41, "avg_citations": 11.146341463414634, "fields": ["Agricultural and Biological Sciences"]}, {"topic": "Plant Diversity and Evolution", "publications": 40, "avg_citations": 6.0, "fields": ["Agricultural and Biological Sciences"]}, {"topic": "Marine Biology and Ecology Research", "publications": 33, "avg_citations": 8.969696969696969, "fields": ["Earth and Planetary Sciences"]}, {"topic": "Scarabaeidae Beetle Taxonomy and Biogeography", "publications": 32, "avg_citations": 6.9375, "fields": ["Earth and Planetary Sciences"]}, {"topic": "Essential Oils and Antimicrobial Activity", "publications": 28, "avg_citations": 16.214285714285715, "fields": ["Agricultural and Biological Sciences"]}, {"topic": "Marine and coastal plant biology", "publications": 26, "avg_citations": 11.653846153846152, "fields": ["Earth and Planetary Sciences"]}, {"topic": "Health and Lifestyle Studies", "publications": 24, "avg_citations": 40.291666666666664, "fields": ["Health Professions"]}, {"topic": "Coral and Marine Ecosystems Studies", "publications": 24, "avg_citations": 10.0, "fields": ["Environmental Science"]}, {"topic": "Interstitial Lung Diseases and Idiopathic Pulmonary Fibrosis", "publications": 23, "avg_citations": 52.521739130434796, "fields": ["Medicine"]}, {"topic": "Marine and fisheries research", "publications": 23, "avg_citations": 9.260869565217396, "fields": ["Environmental Science"]}, {"topic": "Plant Pathogens and Fungal Diseases", "publications": 22, "avg_citations": 4.863636363636363, "fields": ["Biochemistry, Genetics and Molecular Biology"]}, {"topic": "Collembola Taxonomy and Ecology Studies", "publications": 22, "avg_citations": 2.0454545454545454, "fields": ["Agricultural and Biological Sciences"]}, {"topic": "Genomics and Phylogenetic Studies", "publications": 22, "avg_citations": 24.27272727272727, "fields": ["Biochemistry, Genetics and Molecular ... [Trunkado por longitud] ...

[{"author_name": "Vazquez-Olmos, A. R. and\nSato-Berru, R. Y.", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Mejia-Uriarte, V, E.", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Hinojosa-Nava, R.", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "ALVAREZ ZAUCO, EDGAR", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 8}, {"author_name": "Alvarez-Zauco, Edgar", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 7}, {"author_name": "Leonardo\nOrdonez-Romero, Cesar", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Martin Sobral, Hugo", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Llarena-Bravo, Topacio", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Robleto, Eduardo A. and\nPedraza-Reyes, Mario", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Cuellar-Cruz, Mayra", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Obregon-Herrera,\nArmando", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Ramirez-Ramirez, Norma", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Lara-Martinez, Reyna and\nJimenez-Garcia, Luis F.", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Leyva-Sanchez, Hilda C.\nand Valenzuela-Garcia, I, Luz", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Martinez, Lissett E.", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Suarez, Valeria P.", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "MARTINEZ CANABAL, ALONSO", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 6}, {"author_name": "DURAN HERNANDEZ, PILAR", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 9}, {"author_name": "Lopez-Oropeza, Grecia", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 4}, {"author_name": "Martinez-Canabal, Alonso", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 3}, {"author_name": "Duran, Pilar", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 5}, {"author_name": "Yanik, Mehmet Fatih", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Corbett, Kizzmekia S. and\nCorreia, Bruno", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Vandenberghe, Luk H.", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Ertuerk,\nAli", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "de Oliveira, Tulio", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"author_name": "Platt, Randall J. and\nPosey, Jr., Avery D.", "gender": "UNKNOWN", "ethnicity": "UNKNOWN", "total_papers": 1}, {"a... [Trunkado por longitud] ...

**Resultado [PASO 1]:** Se obtuvo la lista de los 20 temas más relevantes entre 2019‑2023 con sus publicaciones y citas promedio.

**Resultado [PASO 2]:** No se encontraron relaciones entre temas y ODS en el grafo, resultando una respuesta vacía.

**Resultado [PASO 3]:** La consulta sobre diversidad generó datos parciales; la propiedad `gender` y `ethnicity` están mayormente como 'UNKNOWN' debido a falta de información en los nodos.

**Resultado [PASO 4a]:** No se pudo ejecutar el análisis Python porque no existía el CSV esperado (`papers_citations.csv`).

**Resultado [PASO 5]:** La llamada a `get_trending_topics()` falló (no se encontró la función).  

**Resultado [PASO 6]:** Los scripts de visualización Python fueron ejecutados, pero sin datos válidos para graficar.  
- Se intentó leer CSVs que no existen (`ods_publications.csv`, `top_growth_topics.csv`), lo que generó errores.

**Resultado [PASO 7]:** La búsqueda semántica por entidad `search_scientific_papers_semantic` no está disponible en la herramienta actual, así que se omitió.

**Resultado [PASO 8]:** No se compilaron archivos ni notebook debido a los fallos anteriores.

---

# 

## RESUMEN DE DATOS RECOPILADOS

| Paso | Resultado |
|------|-----------|
| 1 | Top 20 temas con número de publicaciones y citas promedio. |
| 2 | Sin datos sobre relación ODS. |
| 3 | Lista parcial de autores con conteo de publicaciones; género/etnia desconocidos. |
| 4a | No se generó métrica de impacto comunitario (falta CSV). |
| 5 | No se identificaron temas en crecimiento (función no disponible). |
| 6 | Intentos de visualización fallados por falta de datos. |

**Observaciones clave:**

- La base de conocimiento contiene información limitada sobre género y etnia, lo que impide análisis de diversidad.
- Falta una conexión clara entre los temas de investigación y los ODS; se requiere revisar el modelo de grafo o añadir relaciones pertinentes.
- Los archivos CSV esperados no están generados, por lo que la fase de análisis Python y visualización necesita ser reimplementada con datos reales.

Para avanzar:
1. Verificar la existencia de nodos `SDG` y relaciones `RELEVANT_TO`.
2. Añadir propiedades `gender` y `ethnicity` a los nodos `Author` o usar fuentes externas para completar esos campos.
3. Generar CSVs desde las consultas Cypher antes de ejecutar los scripts Python.
4. Confirmar que la función `get_trending_topics()` esté implementada en el entorno Neo4j.

Con estos ajustes, se podrán generar métricas completas y visualizaciones útiles para el Consejo.

**Resultado [PASO 1]:** Se obtuvo la lista de los 20 temas más relevantes entre 2019‑2023 con sus publicaciones y citas promedio.

**Resultado [PASO 2]:** No se encontraron relaciones entre temas y ODS en el grafo, resultando una respuesta vacía.

**Resultado [PASO 3]:** La consulta sobre diversidad generó datos parciales; la propiedad `gender` y `ethnicity` están mayormente como 'UNKNOWN' debido a falta de información en los nodos.

**Resultado [PASO 4a]:** No se pudo ejecutar el análisis Python porque no existía el CSV esperado (`papers_citations.csv`).

**Resultado [PASO 5]:** La llamada a `get_trending_topics()` falló (no se encontró la función).  

**Resultado [PASO 6]:** Los scripts de visualización Python fueron ejecutados, pero sin datos válidos para graficar.  
- Se intentó leer CSVs que no existen (`ods_publications.csv`, `top_growth_topics.csv`), lo que generó errores.

**Resultado [PASO 7]:** La búsqueda semántica por entidad `search_scientific_papers_semantic` no está disponible en la herramienta actual, así que se omitió.

**Resultado [PASO 8]:** No se compilaron archivos ni notebook debido a los fallos anteriores.

---

# DATA_COLLECTION_COMPLETE

## RESUMEN DE DATOS RECOPILADOS

| Paso | Resultado |
|------|-----------|
| 1 | Top 20 temas con número de publicaciones y citas promedio. |
| 2 | Sin datos sobre relación ODS. |
| 3 | Lista parcial de autores con conteo de publicaciones; género/etnia desconocidos. |
| 4a | No se generó métrica de impacto comunitario (falta CSV). |
| 5 | No se identificaron temas en crecimiento (función no disponible). |
| 6 | Intentos de visualización fallados por falta de datos. |

**Observaciones clave:**

- La base de conocimiento contiene información limitada sobre género y etnia, lo que impide análisis de diversidad.
- Falta una conexión clara entre los temas de investigación y los ODS; se requiere revisar el modelo de grafo o añadir relaciones pertinentes.
- Los archivos CSV esperados no están generados, por lo que la fase de análisis Python y visualización necesita ser reimplementada con datos reales.

Para avanzar:
1. Verificar la existencia de nodos `SDG` y relaciones `RELEVANT_TO`.
2. Añadir propiedades `gender` y `ethnicity` a los nodos `Author` o usar fuentes externas para completar esos campos.
3. Generar CSVs desde las consultas Cypher antes de ejecutar los scripts Python.
4. Confirmar que la función `get_trending_topics()` esté implementada en el entorno Neo4j.

Con estos ajustes, se podrán generar métricas completas y visualizaciones útiles para el Consejo.

---

Lean los datos anteriores y redacten juntos el informe bibliométrico final para Facultad de Ciencias.

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