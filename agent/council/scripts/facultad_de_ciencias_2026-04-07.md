# Script de Ejecución Bibliométrica

**Entidad por defecto**: FACULTAD DE CIENCIAS
**Fecha**: 2026-04-07
**Re-uso**: reemplaza {ENTITY} con otra entidad al ejecutar.

---

### Arquitecto_de_Datos
**SCRIPT TÉCNICO – FACULTAD DE CIENCIAS (UNAM)**  
*(Placeholder `{ENTITY}` = “Facultad de Ciencias”)*  

El siguiente guion describe los pasos concretos que se pueden ejecutar con las herramientas disponibles en SINAPSIS, siguiendo la lógica del plan aprobado.  Cada bloque incluye la llamada a la herramienta correspondiente y el fragmento de código Python que debe colocarse dentro de un notebook o script `.py`.  

> **Nota:** Todos los datos utilizados provienen de los archivos Parquet pre‑calculados (`data/cache/<ENTITY>/…`) o de las bases de conocimiento ya cargadas (Neo4j / Qdrant).  No se hace ninguna llamada a APIs externas.  

---

## 1. Cargar métricas institucionales

```python
# Paso 1 – Instala pandas si aún no lo tienes
import pandas as pd, os, json, matplotlib.pyplot as plt

ENTITY = 'Facultad de Ciencias'
inst_tot_path   = f'data/cache/{ENTITY}/institucion_total.parquet'
inst_ann_path   = f'data/cache/{ENTITY}/institucion_annual.parquet'

inst_df  = pd.read_parquet(inst_tot_path)
ann_df   = pd.read_parquet(inst_ann_path)

print('Producción total:', inst_df.head())
print('Evolución anual:', ann_df.head())
```

---

## 2. Cargar lista de papers institucionales

```python
# Paso 2 – Papers con todas las afiliaciones (incluye OA, citas, etc.)
papers_inst_path = f'data/cache/{ENTITY}/papers_institucion.parquet'
papers_inst     = pd.read_parquet(papers_inst_path)

print('Número de papers:', len(papers_inst))
```

---

## 3. Cargar perfiles completos de cada investigador

```python
# Paso 3 – Perfil completo (incluye trabajos anteriores)
prof_path   = f'data/cache/{ENTITY}/papers_profesor.parquet'
prof_df     = pd.read_parquet(prof_path)

print('Perfil de un académico:', prof_df.head())
```

---

## 4. Cargar jerarquía temática por investigador

```python
# Paso 4 – Tópicos extraídos (en inglés)
topics_path   = f'data/cache/{ENTITY}/topics_investigador.parquet'
topics_df     = pd.read_parquet(topics_path)

print('Ejemplo de tópicos:', topics_df.head())
```

---

## 5. Cargar palabras clave por investigador

```python
# Paso 5 – Palabras clave (para análisis de sesgo lingüístico)
kw_path   = f'data/cache/{ENTITY}/keywords_investigador.parquet'
kw_df     = pd.read_parquet(kw_path)

print('Ejemplo de keywords:', kw_df.head())
```

---

## 6. Calcular métricas no‑tradicionales

```python
# Paso 6 – Impacto social (OA × citas/documento)
inst_df['impact_social'] = inst_df['pct_open_access'] * (
                            inst_df['citations'] / inst_df['num_documents'])

# Métricas de apertura desglosadas
# (Si los campos no existen, se crean con NaN)
for col in ['pct_oa_gold','pct_oa_green','pct_oa_hybrid']:
    if col not in inst_df.columns:
        inst_df[col] = pd.NA

print('Métricas de apertura:', inst_df[['pct_open_access',
                                        'pct_oa_gold','pct_oa_green',
                                        'pct_oa_hybrid']].head())
```

---

## 7. Analizar evolución temática y detectar brechas

```python
# Paso 7 – Agrupar tópicos por año y calcular crecimiento medio anual
topic_year = topics_df.groupby(['year','topic']).agg(
                value_sum=('value','sum')).reset_index()

pivot_vals = topic_year.pivot(index='topic',
                              columns='year',
                              values='value_sum').fillna(0)

pct_change = pivot_vals.pct_change().mean(axis=1).rename('avg_pct_change')
topic_growth = pct_change.reset_index()
topic_growth.sort_values('avg_pct_change', ascending=False, inplace=True)

print('Top 10 temas con mayor crecimiento:', topic_growth.head(10))
```

---

## 8. Mapear colaboración interdisciplinaria

```python
# Paso 8 – Matriz de dominios por investigador
dom_by_prof = topics_df.groupby(['academic_name','domain']).size()\
                       .reset_index(name='doc_count')

pivot_dom = dom_by_prof.pivot(index='academic_name',
                              columns='domain',
                              values='doc_count').fillna(0)

print('Matriz de colaboración interdisciplinaria (ejemplo):')
print(pivot_dom.head())
```

---

## 9. Generar dashboard interactivo (Streamlit)

```python
# Paso 9 – Ejemplo mínimo de Streamlit (guardar en app_dashboard.py)
import streamlit as st

st.title(f'Dashboard Bibliométrico – {ENTITY}')

st.subheader('Producción anual')
st.bar_chart(ann_df[['year','num_documents']])

st.subheader('Impacto social por año')
st.line_chart(inst_df[['year','impact_social']])
```

> Ejecutar con:  
> ```bash
> streamlit run app_dashboard.py
> ```

---

## 10. Consultas en Neo4j (si se requiere)

### a) Red de coautoría de un investigador

```python
# Paso 10a – Obtener grafico de coautores de “ALCUBIERRE MOYA, MIGUEL”
author_name = 'ALCUBIERRE MOYA, MIGUEL'
cypher_query = f"""
MATCH (a:Author {{name: $name}})-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(co:Author)
RETURN co.name AS collaborator,
       count(p) AS papers_together
ORDER BY papers_together DESC
LIMIT 10
"""
# Ejecutar con la herramienta
result = query_knowledge_graph_cypher(cypher_query, parameters={'name':author_name})
print(result.head())
```

### b) Red de coautoría para todos los académicos de la facultad

```python
# Paso 10b – Obtener red completa de coautores dentro de la entidad
cypher_all = """
MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution {name: $entity})
MERGE (a)-[r:COAUTHORED_WITH]-(co:Author)
RETURN a.name AS author, co.name AS collaborator, count(r) AS weight
"""
result_all = query_knowledge_graph_cypher(cypher_all, parameters={'entity':ENTITY})
print(result_all.head())
```

> **Importante:** Los resultados de `query_knowledge_graph_cypher` deben ser exportados como JSON/CSV y cargados en pandas antes de cualquier análisis posterior.

---

## 11. Búsqueda semántica en Qdrant (si se necesita)

```python
# Paso 11 – Buscar papers sobre “cambio climático” con contexto institucional
search_query = {
    "vector": None,          # dejar que la herramienta lo calcule internamente
    "limit": 5,
    "payload_filter": {"entity_context": ENTITY},
    "text": "climate change"
}
results = search_scientific_papers_semantic(search_query)
print(results)   # lista de dicts con id, title, year, etc.
```

---

## 12. Exportar resultados a archivos (para informe)

```python
# Paso 12 – Guardar los DataFrames clave en CSV para el informe ejecutivo
inst_df.to_csv('output/institution_total.csv', index=False)
ann_df.to_csv('output/institution_annual.csv', index=False)
topic_growth.to_csv('output/topic_growth.csv', index=False)
pivot_dom.to_csv('output/interdisciplinary_matrix.csv')
```

---

## 13. Próximos pasos y recomendaciones

1. **Revisar la calidad de los campos OA** (gold, green, hybrid) – si están vacíos, considerar recuperarlos desde OpenAlex con `recoverFromOpenAlex` para los DOIs que faltan.  
2. **Agregar datos de género/etnia**: usar `searchAuthorInOpenAlex` y `recoverAuthorWorksFromOpenAlex` para construir un DataFrame `gender_ethnicity.parquet`.  
3. **Asignar códigos ODS a cada tópico**: crear una tabla mapeo `topic_to_sdg.csv` (manual) y unirla con `topics_df`.  
4. **Visualizaciones finales**: generar gráficos de barras, heatmaps y redes con `matplotlib`, `seaborn` o `plotly`.  
5. **Informe ejecutivo**: combinar los CSV exportados en un documento PDF/PowerPoint usando `Python_CodeExecutor` (pandas + matplotlib).  

---

### SCRIPT_TÉCNICO_LISTO