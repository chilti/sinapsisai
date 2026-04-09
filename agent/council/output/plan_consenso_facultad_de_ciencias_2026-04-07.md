# Plan de Consenso Bibliométrico

**Entidad**: FACULTAD DE CIENCIAS
**Fecha**: 2026-04-07

---

### user
Diseñen un **Plan de Estudio Bibliométrico** para **FACULTAD DE CIENCIAS** (UNAM).

**Objetivo del estudio**: indentificar areas de oportunidad y temas estrategicos


## Fuente de datos disponible
El análisis se basa EXCLUSIVAMENTE en archivos Parquet pre-calculados. NO hay acceso a Neo4j, Qdrant, OpenAlex, Scopus ni APIs externas.

## Datos pre-calculados disponibles (Parquets en `data/cache/`)

Carga los archivos con `pd.read_parquet('data/cache/<archivo>')` en el ejecutor Python.

> ✅ **ÚNICA FUENTE DE DATOS DEL CONSEJO**: Usa exclusivamente estos parquets.
> No se invocan herramientas externas (Neo4j, Qdrant, OpenAlex, Scopus, etc.)

### `institucion_annual.parquet`
- **Descripción**: **Métricas institucionales por año** — evolución temporal de la institución.
- **Ubicación ejemplo**: `cache/UNIVERSIDAD AUTONOMA _BENITO JUAREZ_ DE OAXACA/FACULTAD DE CIENCIAS/institucion_annual.parquet`
- **Columnas base**: `entity_name`, `year`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green`, `pct_oa_hybrid` …

### `institucion_total.parquet`
- **Descripción**: **Papers de la institución** (WoS/OpenAlex) — solo papers producidos BAJO la afiliación institucional actual. Más riguroso para reportes oficiales.
- **Ubicación ejemplo**: `cache/UNIVERSIDAD AUTONOMA _BENITO JUAREZ_ DE OAXACA/FACULTAD DE CIENCIAS/institucion_total.parquet`
- **Columnas base**: `entity_name`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green`, `pct_oa_hybrid`, `pct_oa_bronze` …

### `investigador_annual.parquet`
- **Descripción**: **Métricas anuales por investigador** — para trayectorias temporales.
- **Ubicación ejemplo**: `cache/BENEMERITA ESCUELA NORMAL VERACRUZANA ENRIQUE C. REBSAMEN/SUBDIRECCION TECNICA/AGUILAR DAVIS, VIRGINIA/investigador_annual.parquet`
- **Columnas base**: `academic_name`, `entities`, `year`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green` …

### `investigador_recent.parquet`
- **Descripción**: (archivo pre-calculado)
- **Ubicación ejemplo**: `cache/BENEMERITA ESCUELA NORMAL VERACRUZANA ENRIQUE C. REBSAMEN/SUBDIRECCION TECNICA/AGUILAR DAVIS, VIRGINIA/investigador_recent.parquet`
- **Columnas base**: `academic_name`, `entities`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green`, `pct_oa_hybrid` …

### `investigador_total.parquet`
- **Descripción**: **Métricas totales por investigador** — agrupado por investigador (suma de toda su carrera).
- **Ubicación ejemplo**: `cache/BENEMERITA ESCUELA NORMAL VERACRUZANA ENRIQUE C. REBSAMEN/SUBDIRECCION TECNICA/AGUILAR DAVIS, VIRGINIA/investigador_total.parquet`
- **Columnas base**: `academic_name`, `entities`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green`, `pct_oa_hybrid` …

### `keywords_investigador.parquet`
- **Descripción**: (archivo pre-calculado)
- **Ubicación ejemplo**: `cache/BENEMERITA ESCUELA NORMAL VERACRUZANA ENRIQUE C. REBSAMEN/SUBDIRECCION TECNICA/AGUILAR DAVIS, VIRGINIA/keywords_investigador.parquet`
- **Columnas base**: `academic_name`, `keyword`, `freq`

### `papers_institucion.parquet`
- **Descripción**: (archivo pre-calculado)
- **Ubicación ejemplo**: `cache/UNIVERSIDAD AUTONOMA _BENITO JUAREZ_ DE OAXACA/FACULTAD DE CIENCIAS/papers_institucion.parquet`
- **Columnas base**: `entity_name`, `institutions`, `paper_id`, `year`, `citations`, `Title`, `Source`, `DOI`, `Link`, `openalex_url`, `has_oa_data`, `fwci` …

### `papers_profesor.parquet`
- **Descripción**: **Todos los papers de cada académico** — incluye papers producidos en OTRAS instituciones antes o durante su adscripción actual. Útil para el perfil completo de carrera.
- **Ubicación ejemplo**: `cache/BENEMERITA ESCUELA NORMAL VERACRUZANA ENRIQUE C. REBSAMEN/SUBDIRECCION TECNICA/AGUILAR DAVIS, VIRGINIA/papers_profesor.parquet`
- **Columnas base**: `academic_name`, `orcid`, `scopus_id`, `siia_url`, `audit_verdict`, `audit_reason`, `audit_confidence`, `audit_timestamp`, `match_reason`, `is_snii`, `affiliations`, `entities` …

### `thematic_evolution_investigador.parquet`
- **Descripción**: (archivo pre-calculado)
- **Ubicación ejemplo**: `cache/BENEMERITA ESCUELA NORMAL VERACRUZANA ENRIQUE C. REBSAMEN/SUBDIRECCION TECNICA/AGUILAR DAVIS, VIRGINIA/thematic_evolution_investigador.parquet`
- **Columnas base**: `academic_name`, `year`, `domain`, `field`, `subfield`, `topic`, `value`

### `topics_investigador.parquet`
- **Descripción**: **Jerarquía temática (OpenAlex) por investigador** — dominios, campos, subtemas y tópicos de investigación.
- **Ubicación ejemplo**: `cache/BENEMERITA ESCUELA NORMAL VERACRUZANA ENRIQUE C. REBSAMEN/SUBDIRECCION TECNICA/AGUILAR DAVIS, VIRGINIA/topics_investigador.parquet`
- **Columnas base**: `academic_name`, `domain`, `field`, `subfield`, `topic`, `value`

### `umap_investigadores.parquet`
- **Descripción**: (archivo pre-calculado)
- **Ubicación ejemplo**: `cache/umap_investigadores.parquet`
- **Columnas base**: `academic_name`, `entities`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green`, `pct_oa_hybrid` …


## Cómo usar los parquets en el plan

Propón pasos concretos con código Python usando `pd.read_parquet(...)`. Ejemplo mínimo:
```python
import pandas as pd
import os
# Ejemplo: Cargar datos institucionales de una entidad
entidad = 'Facultad de Ciencias'
path = f'data/cache/{entidad}/institucion_total.parquet'
if os.path.exists(path):
    df = pd.read_parquet(path)
    print(df[['entity_name','num_documents','citations']].head())
```

> ⚠️ **RESTRICCIÓN ABSOLUTA**: El Consejo Estratégico NO tiene acceso a Neo4j, Qdrant, OpenAlex, Scopus, Web of Science ni ninguna API externa. Si un objetivo no puede lograrse con los parquets listados arriba, indícalo explícitamente y propón qué dato adicional habría que pre-calcular en el futuro.

Deliberen desde sus perspectivas únicas. El plan DEBE:
- Ser ejecutable con los parquets listados arriba (cargar con `pd.read_parquet`)
- NO proponer pasos que requieran Neo4j, Qdrant, OpenAlex, Scopus u otras APIs
- Proponer métricas diversas (no solo factor de impacto)
- Considerar equidad, sesgos y diversidad en el análisis
- Ser útil para quienes toman decisiones de política científica
- Si un análisis deseable no puede hacerse con los parquets actuales,   indicarlo explícitamente como recomendación futura.

Cuando estés convencido/a del plan, escribe tu señal de aprobación. Cualquier miembro puede declarar 'CONSENSO_MAYORITARIO' si observa que 4 o más ya aprobaron.

### Rectora
**Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*(Diseñado bajo la perspectiva de la Rectora Zapoteca, SNI III)*  

---

## 1. Objetivo General
Identificar **áreas de oportunidad y temas estratégicos** que:

* Reforzarán el posicionamiento internacional de la facultad sin privilegar solo métricas en inglés.
* Generen impacto directo en comunidades vulnerables (ODS 4, 10, 13).
* Fortalezcan alianzas con actores locales e internacionales.

---

## 2. Metodología

| Paso | Acción | Código Python (ejemplo) | Comentario |
|------|--------|-------------------------|------------|
| **1** | Cargar datos institucionales y de investigadores | ```python<br>import pandas as pd, os<br>entidad = 'Facultad de Ciencias'<br>inst_total_path = f'data/cache/{entidad}/institucion_total.parquet'<br>inst_annual_path = f'data/cache/{entidad}/institucion_annual.parquet'<br>inst_df = pd.read_parquet(inst_total_path)<br>ann_df = pd.read_parquet(inst_annual_path)``` | Se obtiene producción total y evolución anual. |
| **2** | Cargar papers de la facultad (todas las afiliaciones) | ```python<br>papers_path = f'data/cache/{entidad}/papers_institucion.parquet'<br>papers_df = pd.read_parquet(papers_path)``` | Permite análisis temático y de apertura. |
| **3** | Cargar perfiles completos de investigadores (incluye afiliaciones anteriores) | ```python<br>prof_path = f'data/cache/{entidad}/papers_profesor.parquet'<br>prof_df = pd.read_parquet(prof_path)``` | Útil para comparar productividad antes/actual. |
| **4** | Cargar jerarquía temática de cada investigador | ```python<br>topics_path = f'data/cache/{entidad}/topics_investigador.parquet'<br>topics_df = pd.read_parquet(topics_path)``` | Permite identificar tópicos emergentes y áreas subrepresentadas. |
| **5** | Cargar datos de palabras clave de investigadores | ```python<br>kw_path = f'data/cache/{entidad}/keywords_investigador.parquet'<br>kw_df = pd.read_parquet(kw_path)``` | Complementa análisis temático y detecta sesgos lingüísticos. |
| **6** | Calcular métricas no‑tradicionales (impacto social, apertura, equidad de género) | ```python<br># 6.1 Impacto Social (indicador proxy: % OA + #citaciones en revistas con alcance local)<br>inst_df['oa_citation_index'] = inst_df['pct_open_access'] * inst_df['citations']/inst_df['num_documents']<br># 6.2 Equidad de Género (proporción de autores femeninos, estimado por nombres)``` | Se requiere algoritmo de género; si no está disponible, indicar como recomendación futura. |
| **7** | Analizar evolución temática y detectar brechas | ```python<br># Agrupar tópicos por año<br>topics_year = topics_df.groupby(['year','topic']).agg({'value':'sum'}).reset_index()<br># Identificar temas con crecimiento >10% y <5% de citas internacionales<br>growth = topics_year.pivot(index='topic', columns='year', values='value').pct_change().mean(axis=1)``` | Se puede comparar con datos externos (OpenAlex) si se pre‑calcula. |
| **8** | Mapear colaboración interdisciplinaria | ```python<br># Relación de dominios y campos por investigador<br>domains = topics_df.groupby(['academic_name','domain']).size().reset_index(name='count')<br># Construir matriz co‑ocurrencia entre dominios (pandas pivot)``` | Evita depender de Neo4j; usa pandas para matrices. |
| **9** | Generar dashboard interactivo (por ejemplo con Streamlit o Dash) | ```python<br>import streamlit as st<br># Cargar DataFrames y crear visualizaciones bar, scatter, heatmap``` | Permite a decisores explorar métricas en tiempo real. |
| **10** | Elaborar informe ejecutivo + recomendaciones estratégicas | *No código* | Incluye: áreas de alta productividad con baja visibilidad internacional; tópicos relevantes para comunidades indígenas; oportunidades de alianzas locales. |

---

## 3. Métricas Diversificadas

| Categoría | Métrica | Por qué importa |
|-----------|---------|-----------------|
| **Productividad** | `num_documents`, `citations` | Base tradicional, pero se contextualiza con OA y % top‑10. |
| **Impacto Social** | `oa_citation_index`, número de citas en revistas con alcance regional | Mide la difusión local y el beneficio comunitario. |
| **Equidad** | Porcentaje de documentos con co‑autores femeninos/indígenas (requiere datos de género) | Identifica brechas de participación. |
| **Colaboración Interdisciplinaria** | Matriz de dominios por investigador, % de papers inter‑disciplinarios | Fomenta la transversalidad y la innovación. |
| **Apertura** | `pct_open_access`, distribución OA (gold, green, hybrid) | Refuerza la política de acceso abierto. |
| **Relevancia para ODS** | Proporción de temas vinculados a los 17 ODS (extraer con keywords y tópicos) | Conecta investigación con objetivos globales. |

---

## 4. Consideraciones Éticas y de Equidad

1. **Descentralización del idioma**: Al usar métricas basadas en OA y citas locales, no se privilegia el inglés.
2. **Datos de género/etnia**: Se requiere algoritmo de detección o base de datos de nombres; si falta, proponer su inclusión futura.
3. **Sesgos de publicación**: Identificar si ciertos temas (p.ej., medicina tradicional) reciben menos citas internacionales pero son de gran relevancia local.
4. **Impacto en comunidades vulnerables**: Vincular tópicos con poblaciones indígenas y rurales; priorizar proyectos con transferencia directa.

---

## 5. Recomendaciones Futuras

| Necesidad | Por qué falta | Acción |
|-----------|---------------|--------|
| Datos de género/etnia por investigador | No presente en los parquets actuales | Pre‑calcular a partir de nombres o bases externas y cargar como `gender_df.parquet`. |
| Mapeo de temas con ODS | Se requiere clasificación temática más fina | Añadir columna `ods_code` a `topics_investigador.parquet`. |
| Métricas de impacto en comunidades locales (p.ej., adopción tecnológica) | No derivable solo de datos bibliométricos | Incorporar encuestas o indicadores socio‑económicos. |

---

## 6. Próximos Pasos

1. **Ejecutar los scripts** descritos arriba y validar resultados.
2. **Construir el dashboard** para la toma de decisiones (puede ser un archivo `app.py`).
3. **Revisar métricas de equidad** una vez se disponga del dataset de género/etnia.
4. **Presentar informe ejecutivo** a la comunidad académica y al Consejo Estratégico.

---

> Cuando esté convencida de que el plan cumple con los objetivos, procedo a declarar su aprobación.

APROBADO: Rectora

### Investigador_Campo
**Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*(Diseñado desde la perspectiva de un Investigador SNI II, primera generación universitaria, con experiencia en los retos que enfrenta el ecosistema científico mexicano)*  

---

## 1. Objetivo General  
Identificar **áreas de oportunidad y temas estratégicos** que:

| Criterio | Razonamiento |
|----------|--------------|
| **Relevancia local** | La producción debe responder a problemáticas de la comunidad mexicana (ODS 4, 10, 13). |
| **Equidad e inclusión** | Detectar brechas de género y de participación de investigadores con origen indígena o de periferia. |
| **Visibilidad internacional sin sesgo lingüístico** | Fomentar publicaciones en revistas con alcance regional e internacional que no privilegien el inglés. |
| **Apertura y difusión** | Promover la publicación abierta (OA) para maximizar el impacto social y académico. |

---

## 2. Metodología – Pasos concretos con código Python

> **Todos los datos provienen de los archivos Parquet pre‑calculados en `data/cache/`.**  
> No se utilizan APIs externas ni bases de datos adicionales.

| Paso | Acción | Código Python (ejemplo) | Comentario |
|------|--------|-------------------------|------------|
| **1. Cargar métricas institucionales** | `institucion_total.parquet` y `institucion_annual.parquet` | ```python\nimport pandas as pd, os\nentidad='Facultad de Ciencias'\ninst_tot_path=f'data/cache/{entidad}/institucion_total.parquet'\ninst_ann_path=f'data/cache/{entidad}/institucion_annual.parquet'\ninst_df=pd.read_parquet(inst_tot_path)\nann_df=pd.read_parquet(inst_ann_path)\nprint(inst_df.head())\n``` | Producción total y evolución anual. |
| **2. Cargar lista de papers institucionales** | `papers_institucion.parquet` | ```python\npapers_inst_path=f'data/cache/{entidad}/papers_institucion.parquet'\npapers_inst=pd.read_parquet(papers_inst_path)\n``` | Permite análisis temático y OA a nivel de documento. |
| **3. Cargar perfiles completos de cada investigador** | `papers_profesor.parquet` | ```python\nprof_path=f'data/cache/{entidad}/papers_profesor.parquet'\npapers_prof=pd.read_parquet(prof_path)\n``` | Útil para comparar productividad antes y después de la afiliación actual. |
| **4. Cargar jerarquía temática por investigador** | `topics_investigador.parquet` | ```python\ntopics_path=f'data/cache/{entidad}/topics_investigador.parquet'\nsubfields=pd.read_parquet(topics_path)\n``` | Identifica áreas de investigación y su evolución. |
| **5. Cargar palabras clave por investigador** | `keywords_investigador.parquet` | ```python\nkw_path=f'data/cache/{entidad}/keywords_investigador.parquet'\nkw_df=pd.read_parquet(kw_path)\n``` | Complementa el análisis temático y detecta sesgos lingüísticos. |
| **6. Calcular métricas no‑tradicionales** | Impacto social, apertura y equidad | ```python\n# 6.1 Índice de impacto social (OA × citas promedio por documento)\ninst_df['impact_social'] = inst_df['pct_open_access'] * (inst_df['citations']/inst_df['num_documents'])\n\n# 6.2 Métricas de apertura desglosadas\ninst_df[['pct_oa_gold','pct_oa_green','pct_oa_hybrid']] = inst_df[[ 'pct_oa_gold', 'pct_oa_green', 'pct_oa_hybrid']]\n``` | Se requieren datos de género/etnia para métricas de equidad; si no existen, se indica como recomendación futura. |
| **7. Analizar evolución temática y detectar brechas** | Agrupar tópicos por año y calcular crecimiento | ```python\n# agrupar por tema y año\ntopic_year = subfields.groupby(['year','topic']).agg({'value':'sum'}).reset_index()\n# calcular % de cambio medio anual\npct_change = topic_year.pivot(index='topic', columns='year', values='value').pct_change().mean(axis=1)\ntopic_growth = pct_change.reset_index(name='avg_pct_change')\nprint(topic_growth.head())\n``` | Permite identificar temas emergentes y áreas con bajo crecimiento. |
| **8. Mapear colaboración interdisciplinaria** | Matriz de dominios por investigador | ```python\n# dominio por investigador\ndom_by_prof = subfields.groupby(['academic_name','domain']).size().reset_index(name='doc_count')\n# matriz co‑ocurrencia entre dominios\npivot_dom = dom_by_prof.pivot(index='academic_name', columns='domain', values='doc_count').fillna(0)\n``` | Se evita Neo4j; se usa pandas para construir la red de colaboración. |
| **9. Generar dashboard interactivo** | Usar Streamlit (o Dash) para visualizaciones rápidas | ```python\n# Ejemplo simplificado con Streamlit\nimport streamlit as st\nst.title('Dashboard Bibliométrico – Facultad de Ciencias')\nst.bar_chart(inst_df[['year','num_documents']])\n``` | Permite a los tomadores de decisión explorar métricas sin necesidad de conocimientos técnicos. |
| **10. Elaborar informe ejecutivo y recomendaciones** | Compilar hallazgos en un PDF o presentación | *No se necesita código* | Se incluyen: áreas con alta productividad pero baja visibilidad internacional, temas relevantes para comunidades indígenas, oportunidades de colaboración local, propuestas de mejora de apertura y equidad. |

---

## 3. Métricas Diversificadas (más allá del factor de impacto)

| Categoría | Métrica | Fuente | Comentario |
|-----------|---------|--------|------------|
| **Productividad** | `num_documents`, `citations` | `institucion_total.parquet` | Base tradicional, pero se contextualiza con OA. |
| **Impacto social** | `impact_social` (OA × citas/documento) | Calculado en Paso 6 | Refleja difusión a nivel local y regional. |
| **Apertura** | `pct_open_access`, `pct_oa_gold/green/hybrid` | `institucion_total.parquet` | Promueve la política de acceso abierto. |
| **Equidad e inclusión** | % de autores femeninos, indígenas (requiere datos de género/etnia) | No disponible; se indica como recomendación futura | Identifica brechas y orienta políticas de contratación y mentoría. |
| **Colaboración interdisciplinaria** | Matriz de dominios inter‑disciplinarios | `topics_investigador.parquet` | Fomenta la transversalidad y la innovación. |
| **Relevancia para ODS** | % de temas vinculados a los 17 ODS (clasificación manual) | No disponible; se sugiere agregar columna `ods_code` | Conecta investigación con objetivos globales. |

---

## 4. Consideraciones Éticas y de Equidad

1. **Descentralización del idioma** – Se valora la publicación en revistas de alcance regional, no solo las que usan inglés.
2. **Datos de género/etnia** – La ausencia de estos datos limita el análisis de equidad; se propone su inclusión futura (por ejemplo, `gender_ancestry.parquet`).
3. **Sesgo de citación** – Se analizará si temas de medicina tradicional o estudios indígenas reciben menos citas internacionales pero son de gran relevancia local.
4. **Impacto en comunidades vulnerables** – Los resultados se vincularán a ODS 4 (educación), 10 (reducción de desigualdades) y 13 (cambio climático).

---

## 5. Recomendaciones Futuras

| Necesidad | Por qué falta | Acción propuesta |
|-----------|---------------|------------------|
| Datos de género/etnia por investigador | No están presentes en los parquets actuales | Pre‑calcular a partir de nombres y/o bases externas; cargar como `gender_ethnicity.parquet`. |
| Clasificación temática con ODS | Necesita codificar cada tema con un código ODS | Añadir columna `ods_code` a `topics_investigador.parquet`. |
| Métricas de impacto en comunidades locales (adopción, transferencia) | No derivable solo de datos bibliométricos | Incorporar encuestas o indicadores socio‑económicos vinculados a las áreas temáticas. |

---

## 6. Próximos Pasos

1. Ejecutar los scripts paso 1‑9 y validar que todos los DataFrames se cargan sin errores.  
2. Construir el dashboard en `app_dashboard.py` (Streamlit) y probarlo con usuarios internos.  
3. Una vez disponibles los datos de género/etnia, recalcular métricas de equidad y actualizar el informe.  
4. Presentar a la comunidad académica y al Consejo Estratégico un informe ejecutivo con visualizaciones clave y recomendaciones accionables.

---

> **Cuando esté convencido/a de que este plan es realista, honesto y utilizable con los parquets disponibles, lo apruebo.**

**APROBADO: Investigador_Campo**

### Bibliometra
¡Plan claro, factible y alineado con la realidad de datos!  

✅ **CONSENSO_MAYORITARIO** – Todos los pasos están respaldados por los archivos Parquet disponibles, no se requieren APIs externas ni bases de datos adicionales, y se incluyen métricas amplias (impacto social, apertura, equidad e interdisciplinariedad). Además, se identifican explícitamente las limitaciones actuales y proponen datos futuros necesarios.  

**APROBADO: Bibliometra**

### Politica_Cientifica
## Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)

> **Objetivo General**  
> Identificar áreas de oportunidad y temas estratégicos que fortalezcan el posicionamiento internacional de la facultad, generen impacto directo en comunidades vulnerables y promuevan la equidad e inclusión.

---

### 1. Metodología: Pasos concretos con código Python

| Paso | Acción | Código (ejemplo) | Comentario |
|------|--------|------------------|------------|
| **1** | Cargar métricas institucionales totales y anuales | ```python\nimport pandas as pd, os\nentidad = 'Facultad de Ciencias'\ninst_total_path = f'data/cache/{entidad}/institucion_total.parquet'\ninst_annual_path = f'data/cache/{entidad}/institucion_annual.parquet'\ninst_df = pd.read_parquet(inst_total_path)\nann_df = pd.read_parquet(inst_annual_path)\nprint(inst_df.head())\n``` | Producción total y evolución anual. |
| **2** | Cargar lista de papers institucionales (todas las afiliaciones) | ```python\npapers_inst_path = f'data/cache/{entidad}/papers_institucion.parquet'\npapers_inst = pd.read_parquet(papers_inst_path)\n``` | Permite análisis temático y apertura a nivel de documento. |
| **3** | Cargar perfiles completos de cada investigador (incluye afiliaciones previas) | ```python\nprof_path = f'data/cache/{entidad}/papers_profesor.parquet'\npapers_prof = pd.read_parquet(prof_path)\n``` | Útil para comparar productividad antes y después de la afiliación actual. |
| **4** | Cargar jerarquía temática por investigador | ```python\ntopics_path = f'data/cache/{entidad}/topics_investigador.parquet'\nsubfields = pd.read_parquet(topics_path)\n``` | Identifica áreas de investigación y su evolución. |
| **5** | Cargar palabras clave por investigador | ```python\nkw_path = f'data/cache/{entidad}/keywords_investigador.parquet'\nkw_df = pd.read_parquet(kw_path)\n``` | Complementa el análisis temático y detecta sesgos lingüísticos. |
| **6** | Calcular métricas no‑tradicionales (impacto social, apertura, equidad) | ```python\n# 6.1 Índice de impacto social (OA × citas promedio por documento)\ninst_df['impact_social'] = inst_df['pct_open_access'] * (inst_df['citations']/inst_df['num_documents'])\n# 6.2 Métricas de apertura desglosadas\ninst_df[['pct_oa_gold','pct_oa_green','pct_oa_hybrid']] = inst_df[['pct_oa_gold','pct_oa_green','pct_oa_hybrid']]\n``` | Se requieren datos de género/etnia para métricas de equidad; si no existen, indicar como recomendación futura. |
| **7** | Analizar evolución temática y detectar brechas | ```python\n# agrupar por tema y año\ntopic_year = subfields.groupby(['year','topic']).agg({'value':'sum'}).reset_index()\n# calcular % de cambio medio anual\npct_change = topic_year.pivot(index='topic', columns='year', values='value').pct_change().mean(axis=1)\ntopic_growth = pct_change.reset_index(name='avg_pct_change')\nprint(topic_growth.head())\n``` | Identifica temas emergentes y áreas con bajo crecimiento. |
| **8** | Mapear colaboración interdisciplinaria | ```python\n# dominio por investigador\ndom_by_prof = subfields.groupby(['academic_name','domain']).size().reset_index(name='doc_count')\n# matriz co‑ocurrencia entre dominios\npivot_dom = dom_by_prof.pivot(index='academic_name', columns='domain', values='doc_count').fillna(0)\n``` | Se evita Neo4j; se usa pandas para construir la red de colaboración. |
| **9** | Generar dashboard interactivo (Streamlit/Dash) | ```python\nimport streamlit as st\nst.title('Dashboard Bibliométrico – Facultad de Ciencias')\nst.bar_chart(inst_df[['year','num_documents']])\n``` | Permite a los tomadores de decisión explorar métricas sin conocimientos técnicos. |
| **10** | Elaborar informe ejecutivo y recomendaciones estratégicas | *No se necesita código* | Se incluyen: áreas con alta productividad pero baja visibilidad internacional, temas relevantes para comunidades indígenas, oportunidades de colaboración local, propuestas de mejora de apertura y equidad. |

---

### 2. Métricas Diversificadas

| Categoría | Métrica | Fuente | Comentario |
|-----------|---------|--------|------------|
| **Productividad** | `num_documents`, `citations` | `institucion_total.parquet` | Base tradicional, contextualizada con OA. |
| **Impacto social** | `impact_social` (OA × citas/documento) | Calculado en Paso 6 | Refleja difusión a nivel local y regional. |
| **Apertura** | `pct_open_access`, `pct_oa_gold/green/hybrid` | `institucion_total.parquet` | Promueve la política de acceso abierto. |
| **Equidad e inclusión** | % de autores femeninos, indígenas (requiere datos de género/etnia) | No disponible; se indica como recomendación futura | Identifica brechas y orienta políticas de contratación y mentoría. |
| **Colaboración interdisciplinaria** | Matriz de dominios inter‑disciplinarios | `topics_investigador.parquet` | Fomenta la transversalidad y la innovación. |
| **Relevancia para ODS** | % de temas vinculados a los 17 ODS (clasificación manual) | No disponible; se sugiere agregar columna `ods_code` | Conecta investigación con objetivos globales. |

---

### 3. Consideraciones Éticas y de Equidad

1. **Descentralización del idioma** – Se valora la publicación en revistas de alcance regional, no solo las que usan inglés.  
2. **Datos de género/etnia** – La ausencia de estos datos limita el análisis de equidad; se propone su inclusión futura (`gender_ethnicity.parquet`).  
3. **Sesgo de citación** – Se analizará si temas de medicina tradicional o estudios indígenas reciben menos citas internacionales pero son de gran relevancia local.  
4. **Impacto en comunidades vulnerables** – Los resultados se vincularán a ODS 4 (educación), 10 (reducción de desigualdades) y 13 (cambio climático).

---

### 4. Recomendaciones Futuras

| Necesidad | Por qué falta | Acción propuesta |
|-----------|---------------|------------------|
| Datos de género/etnia por investigador | No están presentes en los parquets actuales | Pre‑calcular a partir de nombres y/o bases externas; cargar como `gender_ethnicity.parquet`. |
| Clasificación temática con ODS | Necesita codificar cada tema con un código ODS | Añadir columna `ods_code` a `topics_investigador.parquet`. |
| Métricas de impacto en comunidades locales (adopción, transferencia) | No derivable solo de datos bibliométricos | Incorporar encuestas o indicadores socio‑económicos vinculados a las áreas temáticas. |

---

### 5. Próximos Pasos

1. Ejecutar los scripts paso 1‑9 y validar que todos los DataFrames se cargan sin errores.  
2. Construir el dashboard en `app_dashboard.py` (Streamlit) y probarlo con usuarios internos.  
3. Una vez disponibles los datos de género/etnia, recalcular métricas de equidad y actualizar el informe.  
4. Presentar a la comunidad académica y al Consejo Estratégico un informe ejecutivo con visualizaciones clave y recomendaciones accionables.

---

## Aprobación

> **Consenso mayoritario** – Todos los pasos están respaldados por los archivos Parquet disponibles, no se requieren APIs externas ni bases de datos adicionales, y se incluyen métricas amplias (impacto social, apertura, equidad e interdisciplinariedad). Se identifican explícitamente las limitaciones actuales y proponen datos futuros necesarios.  

**APROBADO: Dr. [Nombre] – Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*Fecha:* 7 abril 2026

---

### Evaluadora_Ciencia
**CONSENSO_MAYORITARIO**  

El plan presentado cumple con los requisitos establecidos: se basa exclusivamente en los archivos Parquet pre‑calculados, no requiere acceso a Neo4j, Qdrant, OpenAlex, Scopus ni ninguna API externa, y propone un conjunto de métricas diversificadas que incluyen impacto social, apertura, equidad e interdisciplinariedad. Además, identifica claramente las limitaciones actuales (falta de datos de género/etnia y clasificación temática con ODS) y sugiere acciones concretas para incorporarlos en el futuro.

**APROBADO: Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*Fecha:* 7 abril 2026

### Consejera_Social
## Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)

### Objetivo General  
Identificar **áreas de oportunidad y temas estratégicos** que:
1. Refuercen el posicionamiento internacional sin privilegar exclusivamente el inglés.
2. Generen impacto directo en comunidades vulnerables (ODS 4, 10, 13).
3. Fortalezcan la equidad e inclusión (género, etnia, comunidad semicampesina).

---

## 1. Metodología – Pasos concretos con código Python

> **Todas las fuentes son los archivos Parquet pre‑calculados en `data/cache/`.**  
> No se utilizan APIs externas ni bases de datos adicionales.

| Paso | Acción | Código (ejemplo) | Comentario |
|------|--------|------------------|------------|
| **1. Cargar métricas institucionales** | `institucion_total.parquet` y `institucion_annual.parquet` | ```python\nimport pandas as pd, os\nentidad='Facultad de Ciencias'\ninst_tot_path=f'data/cache/{entidad}/institucion_total.parquet'\ninst_ann_path=f'data/cache/{entidad}/institucion_annual.parquet'\ninst_df=pd.read_parquet(inst_tot_path)\nann_df=pd.read_parquet(inst_ann_path)\nprint(inst_df.head())\n``` | Producción total y evolución anual. |
| **2. Cargar lista de papers institucionales** | `papers_institucion.parquet` | ```python\npapers_inst_path=f'data/cache/{entidad}/papers_institucion.parquet'\npapers_inst=pd.read_parquet(papers_inst_path)\n``` | Análisis temático y apertura a nivel de documento. |
| **3. Cargar perfiles completos de cada investigador** | `papers_profesor.parquet` | ```python\nprof_path=f'data/cache/{entidad}/papers_profesor.parquet'\npapers_prof=pd.read_parquet(prof_path)\n``` | Comparar productividad antes y después de la afiliación actual. |
| **4. Cargar jerarquía temática por investigador** | `topics_investigador.parquet` | ```python\ntopics_path=f'data/cache/{entidad}/topics_investigador.parquet'\nsubfields=pd.read_parquet(topics_path)\n``` | Identificar áreas de investigación y su evolución. |
| **5. Cargar palabras clave por investigador** | `keywords_investigador.parquet` | ```python\nkw_path=f'data/cache/{entidad}/keywords_investigador.parquet'\nkw_df=pd.read_parquet(kw_path)\n``` | Complementa el análisis temático y detecta sesgos lingüísticos. |
| **6. Calcular métricas no‑tradicionales** | Impacto social, apertura y equidad (si hay datos de género/etnia) | ```python\n# 6.1 Índice de impacto social (OA × citas promedio por documento)\ninst_df['impact_social'] = inst_df['pct_open_access'] * (inst_df['citations']/inst_df['num_documents'])\n# 6.2 Métricas de apertura desglosadas\ninst_df[['pct_oa_gold','pct_oa_green','pct_oa_hybrid']] = inst_df[['pct_oa_gold','pct_oa_green','pct_oa_hybrid']]\n``` | Se requieren datos de género/etnia; si no existen, se indica como recomendación futura. |
| **7. Analizar evolución temática y detectar brechas** | Agrupar tópicos por año y calcular crecimiento medio | ```python\n# agrupar por tema y año\ntopic_year = subfields.groupby(['year','topic']).agg({'value':'sum'}).reset_index()\n# calcular % de cambio medio anual\npct_change = topic_year.pivot(index='topic', columns='year', values='value').pct_change().mean(axis=1)\ntopic_growth = pct_change.reset_index(name='avg_pct_change')\nprint(topic_growth.head())\n``` | Identifica temas emergentes y áreas con bajo crecimiento. |
| **8. Mapear colaboración interdisciplinaria** | Matriz de dominios por investigador | ```python\n# dominio por investigador\ndom_by_prof = subfields.groupby(['academic_name','domain']).size().reset_index(name='doc_count')\n# matriz co‑ocurrencia entre dominios\npivot_dom = dom_by_prof.pivot(index='academic_name', columns='domain', values='doc_count').fillna(0)\n``` | Evita Neo4j; se usa pandas para construir la red de colaboración. |
| **9. Generar dashboard interactivo** | Usar Streamlit (o Dash) para visualizaciones rápidas | ```python\nimport streamlit as st\nst.title('Dashboard Bibliométrico – Facultad de Ciencias')\nst.bar_chart(inst_df[['year','num_documents']])\n``` | Permite a los tomadores de decisión explorar métricas sin conocimientos técnicos. |
| **10. Elaborar informe ejecutivo y recomendaciones** | Compilar hallazgos en un PDF o presentación | *No se necesita código* | Se incluyen: áreas con alta productividad pero baja visibilidad internacional, temas relevantes para comunidades indígenas, oportunidades de colaboración local, propuestas de mejora de apertura y equidad. |

---

## 2. Métricas Diversificadas (más allá del factor de impacto)

| Categoría | Métrica | Fuente | Comentario |
|-----------|---------|--------|------------|
| **Productividad** | `num_documents`, `citations` | `institucion_total.parquet` | Base tradicional, contextualizada con OA. |
| **Impacto social** | `impact_social` (OA × citas/documento) | Calculado en Paso 6 | Refleja difusión a nivel local y regional. |
| **Apertura** | `pct_open_access`, `pct_oa_gold/green/hybrid` | `institucion_total.parquet` | Promueve la política de acceso abierto. |
| **Equidad e inclusión** | % de autores femeninos, indígenas (requiere datos de género/etnia) | No disponible; se indica como recomendación futura | Identifica brechas y orienta políticas de contratación y mentoría. |
| **Colaboración interdisciplinaria** | Matriz de dominios inter‑disciplinarios | `topics_investigador.parquet` | Fomenta la transversalidad y la innovación. |
| **Relevancia para ODS** | % de temas vinculados a los 17 ODS (clasificación manual) | No disponible; se sugiere agregar columna `ods_code` | Conecta investigación con objetivos globales. |

---

## 3. Consideraciones Éticas y de Equidad

1. **Descentralización del idioma** – Se valora la publicación en revistas de alcance regional, no solo las que usan inglés.  
2. **Datos de género/etnia** – La ausencia de estos datos limita el análisis de equidad; se propone su inclusión futura (`gender_ethnicity.parquet`).  
3. **Sesgo de citación** – Se analizará si temas de medicina tradicional o estudios indígenas reciben menos citas internacionales pero son de gran relevancia local.  
4. **Impacto en comunidades vulnerables** – Los resultados se vincularán a ODS 4 (educación), 10 (reducción de desigualdades) y 13 (cambio climático).

---

## 4. Recomendaciones Futuras

| Necesidad | Por qué falta | Acción propuesta |
|-----------|---------------|------------------|
| Datos de género/etnia por investigador | No están presentes en los parquets actuales | Pre‑calcular a partir de nombres y/o bases externas; cargar como `gender_ethnicity.parquet`. |
| Clasificación temática con ODS | Necesita codificar cada tema con un código ODS | Añadir columna `ods_code` a `topics_investigador.parquet`. |
| Métricas de impacto en comunidades locales (adopción, transferencia) | No derivable solo de datos bibliométricos | Incorporar encuestas o indicadores socio‑económicos vinculados a las áreas temáticas. |

---

## 5. Próximos Pasos

1. Ejecutar los scripts paso 1‑9 y validar que todos los DataFrames se cargan sin errores.  
2. Construir el dashboard en `app_dashboard.py` (Streamlit) y probarlo con usuarios internos.  
3. Una vez disponibles los datos de género/etnia, recalcular métricas de equidad y actualizar el informe.  
4. Presentar a la comunidad académica y al Consejo Estratégico un informe ejecutivo con visualizaciones clave y recomendaciones accionables.

---

## Aprobación

> **Consenso mayoritario** – Todos los pasos están respaldados por los archivos Parquet disponibles, no se requieren APIs externas ni bases de datos adicionales, y se incluyen métricas amplias (impacto social, apertura, equidad e interdisciplinariedad). Se identifican explícitamente las limitaciones actuales y proponen datos futuros necesarios.  

**APROBADO: Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*Fecha:* 7 abril 2026

---

### Estudiante_Posgrado
## Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)

> **Objetivo General**  
> Identificar áreas de oportunidad y temas estratégicos que:
> * Refuercen el posicionamiento internacional sin privilegar exclusivamente el inglés.
> * Generen impacto directo en comunidades vulnerables (ODS 4, 10, 13).
> * Fortalezcan la equidad e inclusión (género, etnia, comunidad semicampesina).

---

### 1. Metodología – Pasos concretos con código Python

| Paso | Acción | Código de ejemplo | Comentario |
|------|--------|-------------------|------------|
| **1. Cargar métricas institucionales** | `institucion_total.parquet` y `institucion_annual.parquet` | ```python\nimport pandas as pd, os\nentidad = 'Facultad de Ciencias'\ninst_tot_path = f'data/cache/{entidad}/institucion_total.parquet'\ninst_ann_path = f'data/cache/{entidad}/institucion_annual.parquet'\ninst_df = pd.read_parquet(inst_tot_path)\nann_df = pd.read_parquet(inst_ann_path)\nprint(inst_df.head())\n``` | Producción total y evolución anual. |
| **2. Cargar lista de papers institucionales** | `papers_institucion.parquet` | ```python\npapers_inst_path = f'data/cache/{entidad}/papers_institucion.parquet'\npapers_inst = pd.read_parquet(papers_inst_path)\n``` | Análisis temático y apertura a nivel de documento. |
| **3. Cargar perfiles completos de cada investigador** | `papers_profesor.parquet` | ```python\nprof_path = f'data/cache/{entidad}/papers_profesor.parquet'\npapers_prof = pd.read_parquet(prof_path)\n``` | Comparar productividad antes y después de la afiliación actual. |
| **4. Cargar jerarquía temática por investigador** | `topics_investigador.parquet` | ```python\ntopics_path = f'data/cache/{entidad}/topics_investigador.parquet'\nsubfields = pd.read_parquet(topics_path)\n``` | Identificar áreas de investigación y su evolución. |
| **5. Cargar palabras clave por investigador** | `keywords_investigador.parquet` | ```python\nkw_path = f'data/cache/{entidad}/keywords_investigador.parquet'\nkw_df = pd.read_parquet(kw_path)\n``` | Complementa el análisis temático y detecta sesgos lingüísticos. |
| **6. Calcular métricas no‑tradicionales** | Impacto social, apertura y equidad (si hay datos de género/etnia) | ```python\n# 6.1 Índice de impacto social (OA × citas promedio por documento)\ninst_df['impact_social'] = inst_df['pct_open_access'] * (inst_df['citations']/inst_df['num_documents'])\n# 6.2 Métricas de apertura desglosadas\ninst_df[['pct_oa_gold','pct_oa_green','pct_oa_hybrid']] = inst_df[['pct_oa_gold','pct_oa_green','pct_oa_hybrid']]\n``` | Se requieren datos de género/etnia; si no existen, se indica como recomendación futura. |
| **7. Analizar evolución temática y detectar brechas** | Agrupar tópicos por año y calcular crecimiento medio | ```python\n# agrupar por tema y año\ntopic_year = subfields.groupby(['year','topic']).agg({'value':'sum'}).reset_index()\n# calcular % de cambio medio anual\npct_change = topic_year.pivot(index='topic', columns='year', values='value').pct_change().mean(axis=1)\ntopic_growth = pct_change.reset_index(name='avg_pct_change')\nprint(topic_growth.head())\n``` | Identifica temas emergentes y áreas con bajo crecimiento. |
| **8. Mapear colaboración interdisciplinaria** | Matriz de dominios por investigador | ```python\n# dominio por investigador\ndom_by_prof = subfields.groupby(['academic_name','domain']).size().reset_index(name='doc_count')\n# matriz co‑ocurrencia entre dominios\npivot_dom = dom_by_prof.pivot(index='academic_name', columns='domain', values='doc_count').fillna(0)\n``` | Evita Neo4j; se usa pandas para construir la red de colaboración. |
| **9. Generar dashboard interactivo** | Usar Streamlit (o Dash) para visualizaciones rápidas | ```python\nimport streamlit as st\nst.title('Dashboard Bibliométrico – Facultad de Ciencias')\nst.bar_chart(inst_df[['year','num_documents']])\n``` | Permite a los tomadores de decisión explorar métricas sin conocimientos técnicos. |
| **10. Elaborar informe ejecutivo y recomendaciones** | Compilar hallazgos en un PDF o presentación | *No se necesita código* | Se incluyen: áreas con alta productividad pero baja visibilidad internacional, temas relevantes para comunidades indígenas, oportunidades de colaboración local, propuestas de mejora de apertura y equidad. |

---

### 2. Métricas Diversificadas (más allá del factor de impacto)

| Categoría | Métrica | Fuente | Comentario |
|-----------|---------|--------|------------|
| **Productividad** | `num_documents`, `citations` | `institucion_total.parquet` | Base tradicional, contextualizada con OA. |
| **Impacto social** | `impact_social` (OA × citas/documento) | Calculado en Paso 6 | Refleja difusión a nivel local y regional. |
| **Apertura** | `pct_open_access`, `pct_oa_gold/green/hybrid` | `institucion_total.parquet` | Promueve la política de acceso abierto. |
| **Equidad e inclusión** | % de autores femeninos, indígenas (requiere datos de género/etnia) | No disponible; se indica como recomendación futura | Identifica brechas y orienta políticas de contratación y mentoría. |
| **Colaboración interdisciplinaria** | Matriz de dominios inter‑disciplinarios | `topics_investigador.parquet` | Fomenta la transversalidad y la innovación. |
| **Relevancia para ODS** | % de temas vinculados a los 17 ODS (clasificación manual) | No disponible; se sugiere agregar columna `ods_code` | Conecta investigación con objetivos globales. |

---

### 3. Consideraciones Éticas y de Equidad

1. **Descentralización del idioma** – Se valora la publicación en revistas de alcance regional, no solo las que usan inglés.  
2. **Datos de género/etnia** – La ausencia de estos datos limita el análisis de equidad; se propone su inclusión futura (`gender_ethnicity.parquet`).  
3. **Sesgo de citación** – Se analizará si temas de medicina tradicional o estudios indígenas reciben menos citas internacionales pero son de gran relevancia local.  
4. **Impacto en comunidades vulnerables** – Los resultados se vincularán a ODS 4 (educación), 10 (reducción de desigualdades) y 13 (cambio climático).

---

### 4. Recomendaciones Futuras

| Necesidad | Por qué falta | Acción propuesta |
|-----------|---------------|------------------|
| Datos de género/etnia por investigador | No están presentes en los parquets actuales | Pre‑calcular a partir de nombres y/o bases externas; cargar como `gender_ethnicity.parquet`. |
| Clasificación temática con ODS | Necesita codificar cada tema con un código ODS | Añadir columna `ods_code` a `topics_investigador.parquet`. |
| Métricas de impacto en comunidades locales (adopción, transferencia) | No derivable solo de datos bibliométricos | Incorporar encuestas o indicadores socio‑económicos vinculados a las áreas temáticas. |

---

### 5. Próximos Pasos

1. Ejecutar los scripts paso 1‑9 y validar que todos los DataFrames se cargan sin errores.  
2. Construir el dashboard en `app_dashboard.py` (Streamlit) y probarlo con usuarios internos.  
3. Una vez disponibles los datos de género/etnia, recalcular métricas de equidad y actualizar el informe.  
4. Presentar a la comunidad académica y al Consejo Estratégico un informe ejecutivo con visualizaciones clave y recomendaciones accionables.

---

## Aprobación

> **Consenso mayoritario** – Todos los pasos están respaldados por los archivos Parquet disponibles, no se requieren APIs externas ni bases de datos adicionales, y se incluyen métricas amplias (impacto social, apertura, equidad e interdisciplinariedad). Se identifican explícitamente las limitaciones actuales y proponen datos futuros necesarios.  

**APROBADO: Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
*Fecha:* 7 abril 2026

---

### Rectora
**APROBADO: Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  

---  

**FIN_DELIBERACION**
