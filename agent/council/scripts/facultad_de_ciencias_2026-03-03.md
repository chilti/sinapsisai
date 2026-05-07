# Script de Ejecución Bibliométrica

**Entidad por defecto**: Facultad de Ciencias
**Fecha**: 2026-03-03
**Re-uso**: reemplaza {ENTITY} con otra entidad al ejecutar.

---

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
    entity_context="{ENTITY}"
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