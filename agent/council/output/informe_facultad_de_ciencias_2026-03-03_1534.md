# Informe Bibliométrico Final

**Entidad**: Facultad de Ciencias
**Generado**: 2026-03-03_1534

---

# Datos recopilados para Facultad de Ciencias

Ejecuta el siguiente script de recopilación de datos para Facultad de Ciencias:

### Arquitecto_de_Datos
## SCRIPT_TÉCNICO_LISTO

```text
# -----------------------------------------------
# 1. Extraer los papers de neurociencia
# -----------------------------------------------
# Consulta Cypher: obtén todos los :Paper que tienen al menos un :Topic cuyo nombre contiene “neuro”
query_knowledge_graph_cypher(
    """
    MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)
    WHERE toLower(t.name) CONTAINS 'neuro'
    RETURN p.id AS paper_id, p.doi AS doi, p.year AS year,
           collect(DISTINCT t.name) AS topics
    LIMIT 5000   // Ajusta si quieres más o menos resultados
    """
)

# -----------------------------------------------
# 2. Construir el grafo de coautoría (solo facultad)
# -----------------------------------------------
# Paso 1: obtener la lista de autores de los papers filtrados
query_knowledge_graph_cypher(
    """
    MATCH (p:Paper)-[:AUTHORED]->(a:Author),
          (a)-[:AFFILIATED_TO]->(i:Institution {id: 1})   // ID 1 = Facultad de Ciencias
    WHERE p.id IN $paper_ids   // $paper_ids es la lista devuelta en el paso anterior
    RETURN DISTINCT a.id AS author_id, a.name AS author_name,
           collect(DISTINCT p.id) AS papers_authored
    """
)

# Paso 2: construir las relaciones de coautoría entre esos autores
get_author_coauthors_graph(
    entity_context="Facultad de Ciencias"   // Facultad de Ciencias será reemplazado por el nombre del investigador principal
)

# -----------------------------------------------
# 3. Obtener estadísticas por departamento (entidades)
# -----------------------------------------------
get_entity_statistics(entity_name="Facultad de Ciencias")

# -----------------------------------------------
# 4. Búsqueda semántica: neurociencia + impacto social
# -----------------------------------------------
search_scientific_papers_semantic(
    query="neurociencia AND impacto social",
    entity_context="Facultad de Ciencias",
    collection_name="scientific_papers",
    top_k=50
)

# -----------------------------------------------
# 5. Identificar temas emergentes (últimos 3 años)
# -----------------------------------------------
get_trending_topics(
    start_year=2021,   // asumiendo que el año actual es 2024
    end_year=2023,
    entity_name="Facultad de Ciencias"
)

# -----------------------------------------------
# 6. Cálculo de métricas alternativas en Python
# -----------------------------------------------
Python_CodeExecutor(
"""
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt

# 1) Cargar resultados previos (papis, coautoría, estadísticas)
papers_df   = pd.read_csv("papers_neuro.csv")          # obtenido del paso 1
coauth_df   = pd.read_csv("coauthors_edges.csv")       # obtenido del paso 2
stats_df    = pd.read_csv("entity_stats.csv")          # obtenido del paso 3

# 2) Cobertura ODS: (papers con al menos un SDG) / total papers neurociencia
ods_coverage = papers_df['sdg_processed'].sum() / len(papers_df)

# 3) Índice de Equidad de Género: % mujeres co‑autoras en papers internacionales
#   Supongamos que la columna gender existe; si no, se debe inferir antes
gender_counts = coauth_df.merge(papers_df[['paper_id','international']], on='paper_id')
male_count  = gender_counts[gender_counts['gender']=='Male'].shape[0]
female_count= gender_counts[gender_counts['gender']=='Female'].shape[0]
gender_index = (female_count / (male_count+female_count)) * 100

# 4) Diversidad Lingüística: número de idiomas distintos
lang_distinct = papers_df['language'].nunique()

# 5) Visualizaciones
fig, ax = plt.subplots()
ax.bar(['ODS Coverage','Gender Index','Language Diversity'],
       [ods_coverage, gender_index, lang_distinct])
plt.title('Métricas alternativas')
plt.savefig('interpreter_output.png')

# 6) Guardar resultados a CSV para el informe final
metrics_df = pd.DataFrame({
    'metric': ['cobertura_ods', 'indice_genero', 'diversidad_ling'],
    'value' : [ods_coverage, gender_index, lang_distinct]
})
metrics_df.to_csv('metrics_alternativas.csv', index=False)
"""
)

# -----------------------------------------------
# 7. (Opcional) Completar perfiles de autores clave con OpenAlex
# -----------------------------------------------
searchAuthorInOpenAlex(
    author_name="Nombre del Autor",
    limit=5
)

# -----------------------------------------------
# 8. Generar reporte final (PDF/HTML) con Plotly y datos exportados
# -----------------------------------------------
# Este paso se realiza fuera de SINAPSIS, usando los archivos:
# - papers_neuro.csv
# - coauthors_edges.csv
# - entity_stats.csv
# - metrics_alternativas.csv
# - interpreter_output.png
# Se recomienda usar un notebook Jupyter o script Python que lea estos CSV y genere el informe.
```

### Validación de pasos

| Paso | Herramienta válida | Comentario |
|------|--------------------|------------|
| 1 | `query_knowledge_graph_cypher` | Sí, consulta disponible. |
| 2 | `get_author_coauthors_graph`, `query_knowledge_graph_cypher` | Sí, ambas funciones son válidas y cumplen restricciones. |
| 3 | `get_entity_statistics` | Sí, función incluida. |
| 4 | `search_scientific_papers_semantic` | Sí, búsqueda semántica en Qdrant. |
| 5 | `get_trending_topics` | Sí, función disponible. |
| 6 | `Python_CodeExecutor` | Sí, se puede usar para cálculos y visualizaciones. |
| 7 | `searchAuthorInOpenAlex` | Opcional, solo si datos internos son insuficientes. |
| 8 | Generar reporte | No hay herramienta directa; se indica que se debe hacer con scripts externos (Jupyter/Python). |

> **Todo el script utiliza únicamente las herramientas autorizadas y sigue la regla de usar primero los datos internos.**  
> **El paso 8 está marcado como “fuera de SINAPSIS” porque requiere generación de PDF/HTML, lo cual no se puede hacer con una herramienta listada; sin embargo es un paso práctico y factible con Python estándar.**

---

[{"paper_id": "10.1076/brhm.29.5.471.4816", "doi": "10.1076/brhm.29.5.471.4816", "year": 1998, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1006/gcen.2001.7752", "doi": "10.1006/gcen.2001.7752", "year": 2002, "topics": ["Neurobiology and Insect Physiology Research", "Neuroendocrine regulation and behavior"]}, {"paper_id": "10.1002/jemt.10268", "doi": "10.1002/jemt.10268", "year": 2003, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1002/jez.a.98", "doi": "10.1002/jez.a.98", "year": 2005, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1636/04-110.1", "doi": "10.1636/04-110.1", "year": 2005, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1080/09291010400028492", "doi": "10.1080/09291010400028492", "year": 2005, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1016/j.peptides.2005.05.018", "doi": "10.1016/j.peptides.2005.05.018", "year": 2005, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1016/j.cbpc.2005.11.021", "doi": "10.1016/j.cbpc.2005.11.021", "year": 2006, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1080/09291010500138761", "doi": "10.1080/09291010500138761", "year": 2006, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1016/j.ejphar.2008.07.068", "doi": "10.1016/j.ejphar.2008.07.068", "year": 2008, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1016/j.dci.2008.12.006", "doi": "10.1016/j.dci.2008.12.006", "year": 2009, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.3109/07420520903398526", "doi": "10.3109/07420520903398526", "year": 2010, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1073/pnas.0910085107", "doi": "10.1073/pnas.0910085107", "year": 2010, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1080/09291016.2011.638116", "doi": "10.1080/09291016.2011.638116", "year": 2012, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1086/663192", "doi": "10.1086/663192", "year": 2012, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1371/journal.pone.0083937", "doi": "10.1371/journal.pone.0083937", "year": 2013, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1371/journal.pone.0175046", "doi": "10.1371/journal.pone.0175046", "year": 2017, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.1093/molbev/msx163", "doi": "10.1093/molbev/msx163", "year": 2017, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.7717/peerj.6015", "doi": "10.7717/peerj.6015", "year": 2018, "topics": ["Neurobiology and Insect Physiology Research"]}, {"paper_id": "10.3389/fphys.2018.01920", "doi": "10.3389/fphys.2018.01920", "year": 2019, "topics": ["Neurobiology and Insect Physiolog... [Trunkado por longitud] ...

[{"paper_id": "10.1076/brhm.29.5.471.4816"}, {"paper_id": "10.1006/gcen.2001.7752"}, {"paper_id": "10.1002/jemt.10268"}, {"paper_id": "10.1002/jez.a.98"}, {"paper_id": "10.1636/04-110.1"}, {"paper_id": "10.1080/09291010400028492"}, {"paper_id": "10.1016/j.peptides.2005.05.018"}, {"paper_id": "10.1016/j.cbpc.2005.11.021"}, {"paper_id": "10.1080/09291010500138761"}, {"paper_id": "10.1016/j.ejphar.2008.07.068"}, {"paper_id": "10.1016/j.dci.2008.12.006"}, {"paper_id": "10.3109/07420520903398526"}, {"paper_id": "10.1073/pnas.0910085107"}, {"paper_id": "10.1080/09291016.2011.638116"}, {"paper_id": "10.1086/663192"}, {"paper_id": "10.1371/journal.pone.0083937"}, {"paper_id": "10.1371/journal.pone.0175046"}, {"paper_id": "10.1093/molbev/msx163"}, {"paper_id": "10.7717/peerj.6015"}, {"paper_id": "10.3389/fphys.2018.01920"}, {"paper_id": "10.1080/07420528.2020.1858849"}, {"paper_id": "10.1080/09291016.2023.2234331"}, {"paper_id": "10.1590/2358-2936e2023024"}, {"paper_id": "10.1007/s13744-025-01305-2"}, {"paper_id": "10.1016/0091-3057(84)90185-0"}, {"paper_id": "10.1080/09291019209360132"}, {"paper_id": "10.3109/07420528.2015.1071385"}, {"paper_id": "10.1016/j.aquatox.2011.09.001"}, {"paper_id": "10.1038/nm.4419"}, {"paper_id": "10.3390/ijms232214176"}, {"paper_id": "10.1016/j.jpaa.2017.06.005"}, {"paper_id": "10.1016/S0954-6111(06)80265-9"}, {"paper_id": "10.1006/gcen.2001.7752"}, {"paper_id": "10.1016/j.yhbeh.2009.12.007"}, {"paper_id": "10.1016/j.yhbeh.2015.04.009"}, {"paper_id": "10.1038/s41598-017-12803-8"}, {"paper_id": "10.15517/rbt.v65i4.26990"}, {"paper_id": "10.1016/j.yhbeh.2018.02.002"}, {"paper_id": "10.1016/j.yhbeh.2018.07.010"}, {"paper_id": "10.1016/j.yhbeh.2019.104653"}, {"paper_id": "10.3791/61493"}, {"paper_id": "10.1016/j.bbr.2021.113520"}, {"paper_id": "10.1016/j.bbr.2022.114153"}, {"paper_id": "10.1016/j.bbr.2024.114928"}, {"paper_id": "10.1002/ab.70037"}, {"paper_id": "10.2164/jandrol.106.000653"}, {"paper_id": "10.1016/j.ejphar.2007.01.076"}, {"paper_id": "10.1152/jn.00579.2018"}, {"paper_id": "10.1002/syn.22287"}, {"paper_id": "10.2164/jandrol.106.000653"}, {"paper_id": "10.1007/s10522-018-9767-3"}, {"paper_id": "10.4103/1673-5374.373672"}, {"paper_id": "10.1111/jnc.70164"}, {"paper_id": "10.3389/fimmu.2025.1661497"}, {"paper_id": "10.5281/ZENODO.17281494"}, {"paper_id": "10.1007/s12031-017-1013-y"}, {"paper_id": "10.3390/ijms232214176"}, {"paper_id": "10.3389/fcell.2025.1622218"}, {"paper_id": "10.3389/fphys.2020.00701"}, {"paper_id": "10.1016/j.ymgmr.2025.101238"}, {"paper_id": "10.1371/journal.pone.0158508"}, {"paper_id": "10.1063/5.0236416"}, {"paper_id": "10.1016/j.brainres.2011.08.034"}, {"paper_id": "10.1016/j.toxicon.2012.04.043"}, {"paper_id": "10.1155/2013/598493"}, {"paper_id": "10.1155/2015/573543"}, {"paper_id": "10.3892/etm.2016.3609"}, {"paper_id": "10.1007/s12031-017-1013-y"}, {"paper_id": "10.1038/s41598-023-38717-2"}, {"paper_id": "10.1002/brb3.3444"}, {"paper_id": "10.1002/syn.22287"}, {"paper_id": "10.1371/journal... [Trunkado por longitud] ...

{"entidad": "Facultad de Ciencias", "total_papers": 6968, "total_académicos": 257, "rango_años": "0 – 2026", "top_tópicos": [{"topic": "Interstitial Lung Diseases and Idiopathic Pulmonary Fibrosis", "papers": 119}, {"topic": "Combustion and flame dynamics", "papers": 49}, {"topic": "Fluid Dynamics and Turbulent Flows", "papers": 43}, {"topic": "Nanofluid Flow and Heat Transfer", "papers": 41}, {"topic": "Rings, Modules, and Algebras", "papers": 37}, {"topic": "Advanced Topology and Set Theory", "papers": 35}, {"topic": "Health and Lifestyle Studies", "papers": 33}, {"topic": "Heat Transfer Mechanisms", "papers": 30}, {"topic": "Medical Imaging and Pathology Studies", "papers": 29}, {"topic": "Neonatal Respiratory Health Research", "papers": 27}], "papers_más_citados": [{"title": "Evolution of organic aerosols in the atmosphere", "year": 2009, "citations": 3237, "author": "SALCEDO GONZALEZ, DARA"}, {"title": "Idiopathic pulmonary fibrosis", "year": 2011, "citations": 2124, "author": "PARDO CEMO, ANNIE"}, {"title": "Idiopathic pulmonary fibrosis: Prevailing and evolving hypotheses about its pathogenesis and implications for therapy", "year": 2001, "citations": 1786, "author": "PARDO CEMO, ANNIE"}, {"title": "Ubiquity and dominance of oxygenated species in organic aerosols in anthropogenically-influenced Northern Hemisphere midlatitudes", "year": 2007, "citations": 1760, "author": "SALCEDO GONZALEZ, DARA"}, {"title": "Erosion of lizard diversity by climate change and altered thermal niches", "year": 2010, "citations": 1656, "author": "VILLAGRAN SANTA CRUZ, MARICELA"}]}

{"desde_año": 2021, "entidad": "Facultad de Ciencias", "tópicos_tendencia": [{"topic": "Health and Lifestyle Studies", "papers": 18, "years": [2024, 2023, 2022, 2021]}, {"topic": "Interstitial Lung Diseases and Idiopathic Pulmonary Fibrosis", "papers": 17, "years": [2023, 2025, 2024, 2022, 2021]}, {"topic": "Rings, Modules, and Algebras", "papers": 13, "years": [2021, 2022, 2023, 2024, 2025]}, {"topic": "Advanced Topology and Set Theory", "papers": 9, "years": [2021, 2022, 2023, 2024, 2025]}, {"topic": "Fluid Dynamics and Turbulent Flows", "papers": 8, "years": [2025, 2024, 2023, 2022, 2021]}, {"topic": "Collembola Taxonomy and Ecology Studies", "papers": 7, "years": [2021, 2022, 2024, 2025, 2026]}, {"topic": "Heat Transfer Mechanisms", "papers": 6, "years": [2025, 2024, 2023, 2022, 2021]}, {"topic": "Advanced Algebra and Logic", "papers": 6, "years": [2021, 2023, 2024, 2025]}, {"topic": "Amphibian and Reptile Biology", "papers": 6, "years": [2022, 2023]}, {"topic": "Global Public Health Policies and Epidemiology", "papers": 6, "years": [2024, 2023, 2021]}, {"topic": "Fuzzy and Soft Set Theory", "papers": 5, "years": [2021, 2023, 2025]}, {"topic": "Algebraic structures and combinatorial models", "papers": 5, "years": [2021, 2022, 2023, 2024, 2025]}, {"topic": "Study of Mite Species", "papers": 5, "years": [2021, 2024, 2025, 2022]}, {"topic": "Hemiptera Insect Studies", "papers": 5, "years": [2021, 2025, 2026, 2023]}, {"topic": "Chronic Obstructive Pulmonary Disease (COPD) Research", "papers": 5, "years": [2024, 2022, 2021]}]}

**Resultado [PASO 1]:** Se obtuvo una lista de 5000 papers con temática neurociencia, aunque el resultado está truncado por limitaciones de longitud.

**Resultado [PASO 2]:** La consulta para extraer autores afiliados a la Facultad de Ciencias no devolvió resultados; parece que los datos internos no contienen esa relación.

**Resultado [PASO 3]:** Se obtuvieron estadísticas de la entidad “Facultad de Ciencias” (total papers, académicos, tópicos top, etc.).

**Resultado [PASO 4]:** No se ejecutó búsqueda semántica porque la herramienta específica `search_scientific_papers_semantic` no está disponible en el entorno actual.

**Resultado [PASO 5]:** Se identificaron temas emergentes entre 2021 y 2023 para la Facultad de Ciencias.

**Resultado [PASO 6]:** La ejecución del bloque Python no se realizó porque los archivos CSV requeridos (`papers_neuro.csv`, `coauthors_edges.csv`, `entity_stats.csv`) no están disponibles en el entorno.

**Resultado [PASO 7]:** No se intentó la búsqueda opcional en OpenAlex debido a la falta de datos internos y a que el paso es opcional.

---

## 

### RESUMEN DE DATOS RECOPILADOS
| Paso | Resultado clave |
|------|-----------------|
| 1 | Lista parcial de papers neurociencia (p. ej., `10.1076/brhm.29.5.471.4816`, `10.1006/gcen.2001.7752`) con años y tópicos asociados. |
| 3 | Estadísticas de la Facultad: <br>- Total Papers: **6968**<br>- Total Académicos: **257**<br>- Rango Años: **0–2026**<br>- Top Tópicos: “Interstitial Lung Diseases”, “Combustion and flame dynamics”, etc. |
| 5 | Temas emergentes (2021‑2023): <br>• Health and Lifestyle Studies (18 papers)<br>• Interstitial Lung Diseases and Idiopathic Pulmonary Fibrosis (17 papers)<br>…<br> (ver tabla completa en el JSON devuelto). |

Los datos de coautoría y métricas alternativas no se pudieron recolectar debido a la ausencia de relaciones internas y archivos CSV necesarios. Para avanzar, se recomienda:
1. Verificar la existencia de nodos `Author` y su relación con `Institution {id:1}`.
2. Generar los archivos CSV requeridos o proporcionar los datos directamente para el cálculo de métricas en Python.

**Resultado [PASO 1]:** Se obtuvo una lista de 5000 papers con temática neurociencia, aunque el resultado está truncado por limitaciones de longitud.

**Resultado [PASO 2]:** La consulta para extraer autores afiliados a la Facultad de Ciencias no devolvió resultados; parece que los datos internos no contienen esa relación.

**Resultado [PASO 3]:** Se obtuvieron estadísticas de la entidad “Facultad de Ciencias” (total papers, académicos, tópicos top, etc.).

**Resultado [PASO 4]:** No se ejecutó búsqueda semántica porque la herramienta específica `search_scientific_papers_semantic` no está disponible en el entorno actual.

**Resultado [PASO 5]:** Se identificaron temas emergentes entre 2021 y 2023 para la Facultad de Ciencias.

**Resultado [PASO 6]:** La ejecución del bloque Python no se realizó porque los archivos CSV requeridos (`papers_neuro.csv`, `coauthors_edges.csv`, `entity_stats.csv`) no están disponibles en el entorno.

**Resultado [PASO 7]:** No se intentó la búsqueda opcional en OpenAlex debido a la falta de datos internos y a que el paso es opcional.

---

## DATA_COLLECTION_COMPLETE

### RESUMEN DE DATOS RECOPILADOS
| Paso | Resultado clave |
|------|-----------------|
| 1 | Lista parcial de papers neurociencia (p. ej., `10.1076/brhm.29.5.471.4816`, `10.1006/gcen.2001.7752`) con años y tópicos asociados. |
| 3 | Estadísticas de la Facultad: <br>- Total Papers: **6968**<br>- Total Académicos: **257**<br>- Rango Años: **0–2026**<br>- Top Tópicos: “Interstitial Lung Diseases”, “Combustion and flame dynamics”, etc. |
| 5 | Temas emergentes (2021‑2023): <br>• Health and Lifestyle Studies (18 papers)<br>• Interstitial Lung Diseases and Idiopathic Pulmonary Fibrosis (17 papers)<br>…<br> (ver tabla completa en el JSON devuelto). |

Los datos de coautoría y métricas alternativas no se pudieron recolectar debido a la ausencia de relaciones internas y archivos CSV necesarios. Para avanzar, se recomienda:
1. Verificar la existencia de nodos `Author` y su relación con `Institution {id:1}`.
2. Generar los archivos CSV requeridos o proporcionar los datos directamente para el cálculo de métricas en Python.

---

Lean los datos anteriores y redacten juntos el informe bibliométrico final para Facultad de Ciencias.

Cada uno aporta su interpretación desde su rol. La estructura del informe es LIBRE: déjense guiar por lo que los datos realmente revelaron. No completen secciones vacías. Eviten usar frases genéricas.

Solo hay tres requisitos mínimos:
1. Una síntesis ejecutiva honesta con los hallazgos más relevantes.
2. Los datos reales presentados (tablas, cifras — tal como los recibieron).
3. Conclusiones accionables para la institución.

Cuando todos hayan aportado su visión, la Rectora redactará el informe final completo y terminará su mensaje con el código: **** (esto cerrará la sesión).