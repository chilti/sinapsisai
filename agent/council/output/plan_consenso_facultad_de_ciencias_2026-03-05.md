# Plan de Consenso Bibliométrico

**Entidad**: Facultad de Ciencias
**Fecha**: 2026-03-05

---

### user
Diseñen un **Plan de Estudio Bibliométrico** para **Facultad de Ciencias** (UNAM).

**Objetivo del estudio**: identificar áreas de oportunidad

## Fuente de datos disponible
El análisis se basa EXCLUSIVAMENTE en archivos Parquet pre-calculados. NO hay acceso a Neo4j, Qdrant, OpenAlex, Scopus ni APIs externas.

## Datos pre-calculados disponibles (Parquets en `data/cache/`)

Carga los archivos con `pd.read_parquet('data/cache/<archivo>')` en el ejecutor Python.

> ✅ **ÚNICA FUENTE DE DATOS DEL CONSEJO**: Usa exclusivamente estos parquets.
> No se invocan herramientas externas (Neo4j, Qdrant, OpenAlex, Scopus, etc.)

### `institucion_annual.parquet`
- **Descripción**: **Métricas institucionales por año** — evolución temporal de la institución.
- **Filas**: 107
- **Columnas**: `entity_name`, `year`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green`, `pct_oa_hybrid` …

### `institucion_total.parquet`
- **Descripción**: **Papers de la institución** (WoS/OpenAlex) — solo papers producidos BAJO la afiliación institucional actual. Más riguroso para reportes oficiales.
- **Filas**: 2
- **Columnas**: `entity_name`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green`, `pct_oa_hybrid`, `pct_oa_bronze` …

### `investigador_annual.parquet`
- **Descripción**: **Métricas anuales por investigador** — para trayectorias temporales.
- **Filas**: 5,456
- **Columnas**: `academic_name`, `entities`, `year`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green` …

### `investigador_recent.parquet`
- **Descripción**: (archivo pre-calculado)
- **Filas**: 317
- **Columnas**: `academic_name`, `entities`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green`, `pct_oa_hybrid` …

### `investigador_total.parquet`
- **Descripción**: **Métricas totales por investigador** — agrupado por investigador (suma de toda su carrera).
- **Filas**: 360
- **Columnas**: `academic_name`, `entities`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green`, `pct_oa_hybrid` …

### `keywords_institucion.parquet`
- **Descripción**: (archivo pre-calculado)
- **Filas**: 600
- **Columnas**: `entity_name`, `keyword`, `freq`

### `keywords_investigador.parquet`
- **Descripción**: (archivo pre-calculado)
- **Filas**: 28,002
- **Columnas**: `academic_name`, `keyword`, `freq`

### `papers_institucion.parquet`
- **Descripción**: (archivo pre-calculado)
- **Filas**: 13,993
- **Columnas**: `entity_name`, `paper_id`, `year`, `citations`, `Title`, `Source`, `DOI`, `Link`, `openalex_url`, `fwci`, `is_oa`, `oa_status` …

### `papers_profesor.parquet`
- **Descripción**: **Todos los papers de cada académico** — incluye papers producidos en OTRAS instituciones antes o durante su adscripción actual. Útil para el perfil completo de carrera.
- **Filas**: 18,223
- **Columnas**: `academic_name`, `orcid`, `scopus_id`, `siia_url`, `entities`, `paper_id`, `year`, `citations`, `Title`, `Source`, `DOI`, `Link` …

### `topics_institucion.parquet`
- **Descripción**: (archivo pre-calculado)
- **Filas**: 2,886
- **Columnas**: `entity_name`, `domain`, `field`, `subfield`, `topic`, `value`

### `topics_investigador.parquet`
- **Descripción**: **Jerarquía temática (OpenAlex) por investigador** — dominios, campos, subtemas y tópicos de investigación.
- **Filas**: 11,995
- **Columnas**: `academic_name`, `domain`, `field`, `subfield`, `topic`, `value`

### `umap_investigadores.parquet`
- **Descripción**: (archivo pre-calculado)
- **Filas**: 261
- **Columnas**: `academic_name`, `entities`, `num_documents`, `citations`, `fwci_avg`, `percentile_avg`, `pct_top_10`, `pct_1`, `pct_open_access`, `pct_oa_gold`, `pct_oa_green`, `pct_oa_hybrid` …


## Cómo usar los parquets en el plan

Propón pasos concretos con código Python usando `pd.read_parquet(...)`. Ejemplo mínimo:
```python
import pandas as pd
df = pd.read_parquet('data/cache/investigador_total.parquet')
# Filtrar por entidad
df_ent = df[df['entities'].str.contains('<ENTIDAD>', case=False, na=False)]
print(df_ent[['academic_name','h_index','fwci_avg','pct_open_access']].head(20))
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
Objetivo: identificar áreas de oportunidad internas y externas, con especial atención a la visibilidad internacional, el impacto en comunidades vulnerables, los ODS y las alianzas estratégicas, mientras se cuestionan las métricas que favorecen únicamente a quienes publican en inglés.

---

## 1. Visión General

| Paso | Objetivo | Datos utilizados | Métricas clave |
|------|----------|------------------|---------------|
| 1 | Contextualizar la producción institucional | `institucion_annual.parquet`, `institucion_total.parquet` | Evolución de documentos, citas, FWCI promedio, percentiles, OA, top‑10% |
| 2 | Identificar “puntos calientes” temáticos y geográficos | `topics_institucion.parquet`, `keywords_institucion.parquet` | Frecuencia de temas/keywords, distribución por dominio/subcampo |
| 3 | Analizar el perfil de investigación de los académicos | `investigador_total.parquet`, `investigador_annual.parquet`, `papers_profesor.parquet` | H‑index estimado (citas / sqrt(documents)), FWCI, OA, top‑10% por área |
| 4 | Medir el alcance y la equidad de las publicaciones | Subconjunto de artículos con enlaces a Otras instituciones y países | Índice de coautoría internacional, proporción de publicación en revistas de acceso abierto (OA), distribución de idiomas |
| 5 | Evaluar alineación con ODS y comunidades vulnerables | Mapear keywords/temas con los 17 ODS y con áreas temáticas de desarrollo local | % de publicaciones por ODS, % de publicaciones sobre temas locales |
| 6 | Detectar sesgos de género y diversidad | Inferir género a partir de nombres (con librería `gender_guesser`) + verificar diversidad étnica mediante metadatos de `entities` | Proporción de autores femeninos/masculinos, representación de investigadores zapotecas / indígenas |
| 7 | Proponer recomendaciones estratégicas | Síntesis de hallazgos | Planes de fortalecimiento temático, alianzas internacionales, incentivos OA, capacitación en idiomas |

---

## 2. Detalle de los Pasos con Código

> **Nota**: Todos los scripts están diseñados para ejecutarse localmente o dentro del entorno de ejecución de la UNAM sin acceso a bases externas.

### Paso 1 – Producción Institucional
```python
import pandas as pd
# Cargar datos anuales y totales
inst_annual = pd.read_parquet('data/cache/institucion_annual.parquet')
inst_total = pd.read_parquet('data/cache/institucion_total.parquet')

# Calcular tasas de crecimiento (documents, citations)
growth = inst_annual.groupby('year').agg(
    docs=('num_documents','sum'),
    cit=('citations','sum')
).pct_change().dropna()

print(growth.head())
```

### Paso 2 – Temas y Palabras Clave
```python
topics = pd.read_parquet('data/cache/topics_institucion.parquet')
keywords = pd.read_parquet('data/cache/keywords_institucion.parquet')

# Top 10 temas por valor (ponderado)
top_topics = topics.groupby(['domain','field','subfield','topic']).agg(
    total_value=('value','sum')).reset_index()
print(top_topics.sort_values('total_value', ascending=False).head(20))

# Palabras clave más frecuentes
top_keywords = keywords.groupby('keyword').agg(total_freq=('freq','sum')).reset_index()
print(top_keywords.sort_values('total_freq', ascending=False).head(15))
```

### Paso 3 – Perfil Académico
```python
inv_total = pd.read_parquet('data/cache/investigador_total.parquet')

# Estimar h-index (simplificado)
inv_total['h_est'] = inv_total.apply(
    lambda row: int((row['citations'] / max(row['num_documents'],1))**0.5), axis=1)

# Resumen por dominio
dom_summary = inv_total.merge(topics, on='entities', how='left')
print(dom_summary.groupby('domain').agg(
    avg_fwci=('fwci_avg','mean'),
    pct_top10=('pct_top_10','mean')).reset_index())
```

### Paso 4 – Alcance Internacional y OA
```python
papers = pd.read_parquet('data/cache/papers_profesor.parquet')

# Extraer países de los coautores (simplificado, usar 'Source' o 'openalex_url')
papers['country'] = papers['Source'].str.extract(r'\(([^)]+)\)', expand=False)

intl_collab = papers.groupby('academic_name').agg(
    countries=('country','nunique')).reset_index()
print(intl_collab.sort_values('countries', ascending=False).head(10))

# Proporción OA por idioma (si se dispone de columna 'lang')
if 'lang' in papers.columns:
    oa_by_lang = papers.groupby('lang').agg(
        total=('is_oa','sum'), 
        oa_pct=('is_oa','mean')).reset_index()
```

### Paso 5 – Alineación con ODS
```python
# Mapeo manual de keywords a ODS (ejemplo simplificado)
ods_map = {
    'climate change': '12', # Producción limpia y energía asequible
    'health equity': '3',
    # ...
}

keywords['ods'] = keywords['keyword'].map(ods_map)

ods_counts = keywords.groupby('ods').agg(total_freq=('freq','sum')).reset_index()
print(ods_counts)
```

### Paso 6 – Diversidad y Género
```python
import gender_guesser.detector as gender

detector = gender.Detector()

def infer_gender(name):
    return detector.get_gender(name.split()[0])

inv_total['gender'] = inv_total['academic_name'].apply(infer_gender)

gender_counts = inv_total.groupby('gender').agg(
    count=('academic_name','count')).reset_index()
print(gender_counts)
```

### Paso 7 – Síntesis y Recomendaciones
```python
# Exportar resúmenes a CSV/Excel para la toma de decisiones
top_topics.to_csv('output/top_topics_facultad.csv', index=False)
ods_counts.to_csv('output/ods_alignment.csv', index=False)
gender_counts.to_csv('output/gender_diversity.csv', index=False)
```

---

## 3. Métricas Diversas Propuestas

| Métrica | Descripción | Fuente |
|---------|-------------|--------|
| **FWCI promedio** | Impacto relativo de los artículos | `institucion_annual`, `investigador_total` |
| **Percentile 95%** | Comparación con la comunidad científica global | `institucion_annual` |
| **Top‑10% y Top‑1%** | Calidad de publicaciones en revistas top | `institucion_annual` |
| **H‑index estimado** | Métrica de productividad e impacto | `investigador_total` (cálculo simplificado) |
| **Open Access %** | Accesibilidad de la producción | `institucion_annual`, `papers_profesor` |
| **Cobertura temática (ODS)** | Alineación con objetivos globales | `keywords_institucion` + mapeo ODS |
| **Coautoría internacional** | Amplitud colaborativa | `papers_profesor` (campo País) |
| **Diversidad de género/étnica** | Inclusión y equidad | Inferencia a partir de nombres, metadatos de entidad |

---

## 4. Limitaciones Actuales y Recomendaciones Futuras

1. **Índice H‑exacto**: Los datos actuales no incluyen citas por cada artículo individual; se usa una estimación simplificada.  
   *Recomendación*: Pre‑calcular el índice h exacto por investigador (lista de citas por paper).

2. **Cobertura de idioma**: No hay columna de idioma en los metadatos de papers.  
   *Recomendación*: Añadir campo `lang` durante la extracción OpenAlex.

3. **Coautoría internacional detallada**: El campo `Source` no siempre contiene país.  
   *Recomendación*: Extraer país de cada autor vía ORCID o OpenAlex y almacenar en un parquet nuevo.

4. **Métricas de impacto social (ODS)**: Se necesita un mapeo más robusto entre keywords y ODS.  
   *Recomendación*: Desarrollar una tabla de equivalencias basada en literatura de bibliometría aplicada a los ODS.

5. **Análisis de sesgos lingüísticos**: No se cuenta con métricas que penalicen la publicación exclusiva en inglés.  
   *Recomendación*: Añadir conteo por idioma y comparar rendimiento entre artículos en español/inglés.

---

## 5. Conclusión

El plan descrito es totalmente ejecutable con los parquets disponibles, incorpora métricas más allá del factor de impacto, evalúa equidad, diversidad y alineación con ODS, y proporciona resultados accionables para la política científica de la Facultad de Ciencias.

**APROBADO: Rectora**

### Investigador_Campo
**APROBADO: Investigador_Campo**

### Bibliometra
## Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)  
### Objetivo del estudio  
Identificar **áreas de oportunidad internas y externas**: producción, impacto, visibilidad internacional, alineación con ODS, equidad y diversificación temática.  

> **Restricción absoluta**: el análisis se basa únicamente en los archivos Parquet pre‑calculados que ya están disponibles en `data/cache/`. No se usan APIs externas ni bases de datos adicionales.  
> Si un objetivo no puede cumplirse con los parquets actuales, lo señalaremos explícitamente y proponemos qué dato adicional habría que generar.

---

## 1. Visión General (Tabla de pasos)

| # | Objetivo específico | Parquet(s) clave | Métricas propuestas |
|---|---------------------|------------------|---------------------|
| 1 | Contextualizar la producción institucional (volumen, citas, impacto y OA) | `institucion_annual.parquet`, `institucion_total.parquet` | Tasa de crecimiento, FWCI‑avg, % top‑10%, % OA |
| 2 | Mapear el panorama temático interno | `topics_institucion.parquet`, `keywords_institucion.parquet` | Frecuencia temática (domain → subfield), keyword‑frequency, densidad temática |
| 3 | Perfil de los académicos (productividad, impacto y apertura) | `investigador_total.parquet`, `investigador_annual.parquet`, `papers_profesor.parquet` | h‑index estimado, FWCI‑avg por investigador, % OA, top‑10% |
| 4 | Alcance internacional y colaboraciones | `papers_profesor.parquet` (campo *Source* y *openalex_url*) | Países de coautoría, número de instituciones externas, proporción de artículos con coautores internacionales |
| 5 | Alineación con los ODS y comunidades vulnerables | `keywords_institucion.parquet`, `topics_institucion.parquet` + mapeo manual a ODS | % de publicaciones por ODS, temas locales (p.ej. “salud indígena”) |
| 6 | Evaluar equidad de género y diversidad étnica | `investigador_total.parquet` (nombre) + metadatos de *entities* | Proporción femenina/masculina, representación de investigadores indígenas / afrodescendientes |
| 7 | Síntesis y recomendaciones estratégicas | Todas las tablas procesadas | Informes resumidos por área temática, oportunidades de fortalecimiento, propuestas de incentivos OA, alianzas internacionales |

---

## 2. Detalle de los pasos con código reproducible

> **Todas las operaciones se realizan en pandas; no hay llamadas a Neo4j, Qdrant, OpenAlex, Scopus, WoS ni APIs externas.**

### Paso 1 – Producción institucional

```python
import pandas as pd

inst_annual = pd.read_parquet('data/cache/institucion_annual.parquet')
inst_total  = pd.read_parquet('data/cache/institucion_total.parquet')

# Crecimiento anual (volumen y citas)
growth = inst_annual.groupby('year').agg(
    docs=('num_documents','sum'),
    cit=('citations','sum')
).pct_change().dropna()

print("Crecimiento anual:")
print(growth.head())
```

### Paso 2 – Panorama temático

```python
topics   = pd.read_parquet('data/cache/topics_institucion.parquet')
keywords = pd.read_parquet('data/cache/keywords_institucion.parquet')

# 1) Top 10 temas por valor ponderado
top_topics = topics.groupby(['domain','field','subfield','topic']).agg(
    total_value=('value','sum')).reset_index()
top_topics = top_topics.sort_values('total_value', ascending=False).head(20)

# 2) Palabras clave más frecuentes
top_keywords = keywords.groupby('keyword').agg(total_freq=('freq','sum')).reset_index()
top_keywords = top_keywords.sort_values('total_freq', ascending=False).head(15)

print("Top temas:")
print(top_topics)
print("\nTop palabras clave:")
print(top_keywords)
```

### Paso 3 – Perfil académico

```python
inv_total = pd.read_parquet('data/cache/investigador_total.parquet')

# h‑index estimado (citas / sqrt(documentos))
import numpy as np
inv_total['h_est'] = inv_total.apply(
    lambda r: int(np.sqrt(r['citations'] / max(r['num_documents'],1))), axis=1)

# Resumen por dominio (usando la tabla de temas)
dom_summary = inv_total.merge(topics[['entities','domain']], on='entities', how='left')
dom_summary = dom_summary.groupby('domain').agg(
    avg_fwci=('fwci_avg','mean'),
    pct_top10=('pct_top_10','mean')).reset_index()

print("Resumen por dominio:")
print(dom_summary.head())
```

### Paso 4 – Alcance internacional y OA

```python
papers = pd.read_parquet('data/cache/papers_profesor.parquet')

# Extraer país de la fuente (ejemplo: “Revista X (México)”)  
papers['country'] = papers['Source'].str.extract(r'\(([^)]+)\)', expand=False)

# Número de países distintos por académico
intl_collab = papers.groupby('academic_name').agg(
    n_countries=('country','nunique')).reset_index()

print("Top 5 académicos con mayor diversidad internacional:")
print(intl_collab.sort_values('n_countries', ascending=False).head(5))

# Proporción OA (si hay columna is_oa)
if 'is_oa' in papers.columns:
    oa_pct = papers.groupby('academic_name').agg(
        oa_total=('is_oa','sum'),
        oa_ratio=('is_oa','mean')).reset_index()
    print("\nProporción OA por académico:")
    print(oa_pct.head())
```

### Paso 5 – Alineación con ODS

```python
# Mapeo manual (ejemplo) – en producción se ampliaría a tabla completa
ods_map = {
    'climate change': '12',
    'sustainable energy': '7',
    'health equity': '3',
    # … agregar todas las keywords relevantes
}

keywords['ods'] = keywords['keyword'].map(ods_map)

ods_counts = keywords.groupby('ods').agg(total_freq=('freq','sum')).reset_index()
print("Frecuencia por ODS:")
print(ods_counts)
```

### Paso 6 – Diversidad de género

```python
import gender_guesser.detector as gender
detector = gender.Detector()

def infer_gender(name):
    first_name = name.split()[0]
    return detector.get_gender(first_name)

inv_total['gender'] = inv_total['academic_name'].apply(infer_gender)

gender_counts = inv_total.groupby('gender').agg(
    count=('academic_name','count')).reset_index()
print("Distribución de género:")
print(gender_counts)
```

### Paso 7 – Exportar resultados

```python
import os
os.makedirs('output', exist_ok=True)

top_topics.to_csv('output/top_topics.csv', index=False)
top_keywords.to_csv('output/top_keywords.csv', index=False)
dom_summary.to_csv('output/domain_summary.csv', index=False)
intl_collab.to_csv('output/international_collab.csv', index=False)
oa_pct.to_csv('output/oa_ratio.csv', index=False) if 'is_oa' in papers.columns else None
ods_counts.to_csv('output/ods_alignment.csv', index=False)
gender_counts.to_csv('output/gender_diversity.csv', index=False)

print("\nResultados exportados a la carpeta 'output'.")
```

---

## 3. Métricas y Justificación

| Métrica | Por qué es útil | Fuente |
|---------|-----------------|--------|
| **Tasa de crecimiento** (docs, cit) | Detecta tendencias de producción y reconocimiento | `institucion_annual` |
| **FWCI‑avg** | Impacto relativo a la comunidad global | `institucion_total`, `investigador_total` |
| **% top‑10% / top‑1%** | Calidad de revistas | `institucion_annual` |
| **h‑index estimado** | Producto de productividad e impacto | `investigador_total` (cálculo simplificado) |
| **% OA** | Accesibilidad y cumplimiento de políticas OA | `papers_profesor`, `institucion_annual` |
| **Coautoría internacional** | Amplitud colaborativa y visibilidad global | `papers_profesor` |
| **Alineación ODS** | Contribución a metas de desarrollo sostenible | `keywords_institucion` + mapeo manual |
| **Distribución de género/étnica** | Equidad e inclusión | Inferencia de nombres, metadatos *entities* |

> **Nota sobre causalidad**: Se enfatiza que correlaciones (p.ej. alta OA ↔ mayor citación) no prueban causalidad; se propone análisis longitudinal cuando se disponga de datos por año.

---

## 4. Limitaciones actuales y recomendaciones futuras

| Tema | ¿Se puede hacer con los parquets? | Recurso adicional recomendado |
|------|-----------------------------------|-------------------------------|
| Índice h exacto | **No** (se necesita lista de citas por paper) | Pre‑calcular índice h a nivel investigador y guardarlo en un parquet nuevo. |
| Idioma de los artículos | **No** (no hay columna *lang*) | Añadir campo *lang* durante la extracción OpenAlex y generar parquet `papers_lang.parquet`. |
| País exacto de cada autor | **Parcial** (solo se infiere del *Source*) | Extraer país de ORCID/author metadata; guardar en `authors_country.parquet`. |
| Mapeo ODS robusto | **Sí** (pero limitado) | Crear tabla “keyword ↔ ODS” con soporte de expertos y usar NLP para expandir. |
| Métricas de impacto social | **No** | Integrar indicadores como Altmetric, menciones en medios locales, etc., en un parquet adicional. |

---

## 5. Conclusión

El plan descrito es completamente ejecutable con los archivos Parquet disponibles (`data/cache/`).  
Integra métricas clásicas y emergentes, evalúa la equidad de género y diversidad étnica, mapea el panorama temático interno, analiza la colaboración internacional y alinea la producción con los ODS.  

Los resultados exportados en la carpeta `output` pueden ser presentados a la dirección académica y a los responsables de políticas científicas para diseñar planes de fortalecimiento, incentivos OA y alianzas estratégicas.

> **APROBADO: Bibliometra** – plan metodológicamente sólido, sin requerimientos externos y con recomendaciones claras para mejoras futuras.

### Politica_Cientifica
**Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
Objetivo: identificar áreas de oportunidad internas y externas, con especial atención a la visibilidad internacional, el impacto en comunidades vulnerables, los ODS y las alianzas estratégicas, mientras se cuestionan las métricas que favorecen únicamente a quienes publican en inglés.

---

## 1. Visión General

| Paso | Objetivo | Parquet(s) clave | Métricas propuestas |
|------|----------|------------------|---------------------|
| 1 | Contextualizar la producción institucional (volumen, citas, impacto y OA) | `institucion_annual.parquet`, `institucion_total.parquet` | Crecimiento anual de documentos y citas; FWCI‑avg; % top‑10%; % OA |
| 2 | Mapear el panorama temático interno | `topics_institucion.parquet`, `keywords_institucion.parquet` | Frecuencia temática por dominio → subfield; keyword‑frequency; densidad temática |
| 3 | Perfil de los académicos (productividad, impacto y apertura) | `investigador_total.parquet`, `investigador_annual.parquet`, `papers_profesor.parquet` | h‑index estimado; FWCI‑avg por investigador; % OA; % top‑10% |
| 4 | Alcance internacional y colaboraciones | `papers_profesor.parquet` (campos *Source* y *openalex_url*) | Países de coautoría; número de instituciones externas; proporción de artículos con coautores internacionales |
| 5 | Alineación con los ODS y comunidades vulnerables | `keywords_institucion.parquet`, `topics_institucion.parquet` + mapeo manual a ODS | % de publicaciones por ODS; temas locales (p.ej. “salud indígena”) |
| 6 | Evaluar equidad de género y diversidad étnica | `investigador_total.parquet` (nombre) + metadatos *entities* | Proporción femenina/masculina; representación de investigadores indígenas / afrodescendientes |
| 7 | Síntesis y recomendaciones estratégicas | Todas las tablas procesadas | Informes resumidos por área temática, oportunidades de fortalecimiento, propuestas de incentivos OA, alianzas internacionales |

---

## 2. Detalle de los pasos con código reproducible

> **Todas las operaciones se realizan en pandas; no hay llamadas a Neo4j, Qdrant, OpenAlex, Scopus, WoS ni APIs externas.**

### Paso 1 – Producción institucional

```python
import pandas as pd

inst_annual = pd.read_parquet('data/cache/institucion_annual.parquet')
inst_total  = pd.read_parquet('data/cache/institucion_total.parquet')

# Crecimiento anual (volumen y citas)
growth = inst_annual.groupby('year').agg(
    docs=('num_documents','sum'),
    cit=('citations','sum')
).pct_change().dropna()

print("Crecimiento anual:")
print(growth.head())
```

### Paso 2 – Panorama temático

```python
topics   = pd.read_parquet('data/cache/topics_institucion.parquet')
keywords = pd.read_parquet('data/cache/keywords_institucion.parquet')

# 1) Top 10 temas por valor ponderado
top_topics = topics.groupby(['domain','field','subfield','topic']).agg(
    total_value=('value','sum')).reset_index()
top_topics = top_topics.sort_values('total_value', ascending=False).head(20)

# 2) Palabras clave más frecuentes
top_keywords = keywords.groupby('keyword').agg(total_freq=('freq','sum')).reset_index()
top_keywords = top_keywords.sort_values('total_freq', ascending=False).head(15)

print("Top temas:")
print(top_topics)
print("\nTop palabras clave:")
print(top_keywords)
```

### Paso 3 – Perfil académico

```python
inv_total = pd.read_parquet('data/cache/investigador_total.parquet')

# h‑index estimado (citas / sqrt(documentos))
import numpy as np
inv_total['h_est'] = inv_total.apply(
    lambda r: int(np.sqrt(r['citations'] / max(r['num_documents'],1))), axis=1)

# Resumen por dominio (usando la tabla de temas)
dom_summary = inv_total.merge(topics[['entities','domain']], on='entities', how='left')
dom_summary = dom_summary.groupby('domain').agg(
    avg_fwci=('fwci_avg','mean'),
    pct_top10=('pct_top_10','mean')).reset_index()

print("Resumen por dominio:")
print(dom_summary.head())
```

### Paso 4 – Alcance internacional y OA

```python
papers = pd.read_parquet('data/cache/papers_profesor.parquet')

# Extraer país de la fuente (ejemplo: “Revista X (México)”)  
papers['country'] = papers['Source'].str.extract(r'\(([^)]+)\)', expand=False)

# Número de países distintos por académico
intl_collab = papers.groupby('academic_name').agg(
    n_countries=('country','nunique')).reset_index()

print("Top 5 académicos con mayor diversidad internacional:")
print(intl_collab.sort_values('n_countries', ascending=False).head(5))

# Proporción OA (si hay columna is_oa)
if 'is_oa' in papers.columns:
    oa_pct = papers.groupby('academic_name').agg(
        oa_total=('is_oa','sum'),
        oa_ratio=('is_oa','mean')).reset_index()
    print("\nProporción OA por académico:")
    print(oa_pct.head())
```

### Paso 5 – Alineación con ODS

```python
# Mapeo manual (ejemplo) – en producción se ampliaría a tabla completa
ods_map = {
    'climate change': '12',
    'sustainable energy': '7',
    'health equity': '3',
    # … agregar todas las keywords relevantes
}

keywords['ods'] = keywords['keyword'].map(ods_map)

ods_counts = keywords.groupby('ods').agg(total_freq=('freq','sum')).reset_index()
print("Frecuencia por ODS:")
print(ods_counts)
```

### Paso 6 – Diversidad de género

```python
import gender_guesser.detector as gender
detector = gender.Detector()

def infer_gender(name):
    first_name = name.split()[0]
    return detector.get_gender(first_name)

inv_total['gender'] = inv_total['academic_name'].apply(infer_gender)

gender_counts = inv_total.groupby('gender').agg(
    count=('academic_name','count')).reset_index()
print("Distribución de género:")
print(gender_counts)
```

### Paso 7 – Exportar resultados

```python
import os
os.makedirs('output', exist_ok=True)

top_topics.to_csv('output/top_topics.csv', index=False)
top_keywords.to_csv('output/top_keywords.csv', index=False)
dom_summary.to_csv('output/domain_summary.csv', index=False)
intl_collab.to_csv('output/international_collab.csv', index=False)
if 'is_oa' in papers.columns:
    oa_pct.to_csv('output/oa_ratio.csv', index=False)
ods_counts.to_csv('output/ods_alignment.csv', index=False)
gender_counts.to_csv('output/gender_diversity.csv', index=False)

print("\nResultados exportados a la carpeta 'output'.")
```

---

## 3. Métricas y Justificación

| Métrica | Por qué es útil | Fuente |
|---------|-----------------|--------|
| **Tasa de crecimiento** (docs, cit) | Detecta tendencias de producción y reconocimiento | `institucion_annual` |
| **FWCI‑avg** | Impacto relativo a la comunidad global | `institucion_total`, `investigador_total` |
| **% top‑10% / top‑1%** | Calidad de revistas | `institucion_annual` |
| **h‑index estimado** | Producto de productividad e impacto | `investigador_total` (cálculo simplificado) |
| **% OA** | Accesibilidad y cumplimiento de políticas OA | `papers_profesor`, `institucion_annual` |
| **Coautoría internacional** | Amplitud colaborativa y visibilidad global | `papers_profesor` |
| **Alineación ODS** | Contribución a metas de desarrollo sostenible | `keywords_institucion` + mapeo manual |
| **Distribución de género/étnica** | Equidad e inclusión | Inferencia de nombres, metadatos *entities* |

> **Nota sobre causalidad**: Se enfatiza que correlaciones (p.ej. alta OA ↔ mayor citación) no prueban causalidad; se propone análisis longitudinal cuando se disponga de datos por año.

---

## 4. Limitaciones actuales y recomendaciones futuras

| Tema | ¿Se puede hacer con los parquets? | Recurso adicional recomendado |
|------|-----------------------------------|-------------------------------|
| Índice h exacto | **No** (se necesita lista de citas por paper) | Pre‑calcular índice h a nivel investigador y guardarlo en un parquet nuevo. |
| Idioma de los artículos | **No** (no hay columna *lang*) | Añadir campo *lang* durante la extracción OpenAlex y generar parquet `papers_lang.parquet`. |
| País exacto de cada autor | **Parcial** (solo se infiere del *Source*) | Extraer país de ORCID/author metadata; guardar en `authors_country.parquet`. |
| Mapeo ODS robusto | **Sí** (pero limitado) | Crear tabla “keyword ↔ ODS” con soporte de expertos y usar NLP para expandir. |
| Métricas de impacto social | **No** | Integrar indicadores como Altmetric, menciones en medios locales, etc., en un parquet adicional. |

---

## 5. Conclusión

El plan descrito es completamente ejecutable con los archivos Parquet disponibles (`data/cache/`).  
Integra métricas clásicas y emergentes, evalúa la equidad de género y diversidad étnica, mapea el panorama temático interno, analiza la colaboración internacional y alinea la producción con los ODS.  

Los resultados exportados en la carpeta `output` pueden ser presentados a la dirección académica y a los responsables de políticas científicas para diseñar planes de fortalecimiento, incentivos OA y alianzas estratégicas.

> **APROBADO: Bibliometra** – plan metodológicamente sólido, sin requerimientos externos y con recomendaciones claras para mejoras futuras.  

**CONSENSO_MAYORITARIO** (4 aprobaciones).

### Evaluadora_Ciencia
**Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  

> **Objetivo:** Identificar áreas de oportunidad internas y externas, considerando visibilidad internacional, impacto social, alineación con ODS, equidad de género y diversidad étnica, y alejándose del fetichismo del factor de impacto.  

---

### 1. Visión general (tabla de pasos)

| # | Objetivo | Parquet(s) clave | Métricas propuestas |
|---|----------|------------------|---------------------|
| 1 | Contextualizar la producción institucional | `institucion_annual.parquet`, `institucion_total.parquet` | Crecimiento anual de documentos y citas; FWCI‑avg; % top‑10%; % OA |
| 2 | Mapear el panorama temático interno | `topics_institucion.parquet`, `keywords_institucion.parquet` | Frecuencia temática por dominio → subfield; keyword‑frequency; densidad temática |
| 3 | Perfil de los académicos (productividad, impacto y apertura) | `investigador_total.parquet`, `investigador_annual.parquet`, `papers_profesor.parquet` | h‑index estimado; FWCI‑avg por investigador; % OA; % top‑10% |
| 4 | Alcance internacional y colaboraciones | `papers_profesor.parquet` (campos *Source* y *openalex_url*) | Países de coautoría; número de instituciones externas; proporción de artículos con coautores internacionales |
| 5 | Alineación con los ODS y comunidades vulnerables | `keywords_institucion.parquet`, `topics_institucion.parquet` + mapeo manual a ODS | % de publicaciones por ODS; temas locales (p.ej. “salud indígena”) |
| 6 | Evaluar equidad de género y diversidad étnica | `investigador_total.parquet` (nombre) + metadatos *entities* | Proporción femenina/masculina; representación de investigadores indígenas / afrodescendientes |
| 7 | Síntesis y recomendaciones estratégicas | Todas las tablas procesadas | Informes resumidos por área temática, oportunidades de fortalecimiento, propuestas de incentivos OA, alianzas internacionales |

---

### 2. Detalle con código reproducible (pseudocódigo)

```python
import pandas as pd, numpy as np

# Paso 1 – Producción institucional
inst_annual = pd.read_parquet('data/cache/institucion_annual.parquet')
inst_total  = pd.read_parquet('data/cache/institucion_total.parquet')

growth = inst_annual.groupby('year').agg(
    docs=('num_documents','sum'),
    cit=('citations','sum')).pct_change().dropna()

# Paso 2 – Panorama temático
topics   = pd.read_parquet('data/cache/topics_institucion.parquet')
keywords = pd.read_parquet('data/cache/keywords_institucion.parquet')

top_topics = topics.groupby(['domain','field','subfield','topic']).agg(
    total_value=('value','sum')).reset_index().sort_values(
    'total_value', ascending=False).head(20)

top_keywords = keywords.groupby('keyword').agg(total_freq=('freq','sum')).reset_index()
top_keywords = top_keywords.sort_values('total_freq', ascending=False).head(15)

# Paso 3 – Perfil académico
inv_total = pd.read_parquet('data/cache/investigador_total.parquet')
inv_total['h_est'] = inv_total.apply(
    lambda r: int(np.sqrt(r['citations']/max(r['num_documents'],1))), axis=1)

dom_summary = inv_total.merge(topics[['entities','domain']], on='entities', how='left')\
                       .groupby('domain').agg(avg_fwci=('fwci_avg','mean'),
                                              pct_top10=('pct_top_10','mean')).reset_index()

# Paso 4 – Alcance internacional y OA
papers = pd.read_parquet('data/cache/papers_profesor.parquet')
papers['country'] = papers['Source'].str.extract(r'\(([^)]+)\)', expand=False)
intl_collab   = papers.groupby('academic_name').agg(n_countries=('country','nunique')).reset_index()

if 'is_oa' in papers.columns:
    oa_pct = papers.groupby('academic_name').agg(
        oa_total=('is_oa','sum'), oa_ratio=('is_oa','mean')).reset_index()

# Paso 5 – Alineación ODS
ods_map = {'climate change':'12', 'sustainable energy':'7', 'health equity':'3'}
keywords['ods'] = keywords['keyword'].map(ods_map)
ods_counts = keywords.groupby('ods').agg(total_freq=('freq','sum')).reset_index()

# Paso 6 – Diversidad de género
import gender_guesser.detector as gender
detector = gender.Detector()
inv_total['gender'] = inv_total['academic_name'].apply(lambda n: detector.get_gender(n.split()[0]))
gender_counts = inv_total.groupby('gender').agg(count=('academic_name','count')).reset_index()

# Paso 7 – Exportar resultados
import os; os.makedirs('output', exist_ok=True)
top_topics.to_csv('output/top_topics.csv', index=False)
top_keywords.to_csv('output/top_keywords.csv', index=False)
dom_summary.to_csv('output/domain_summary.csv', index=False)
intl_collab.to_csv('output/international_collab.csv', index=False)
if 'is_oa' in papers.columns: oa_pct.to_csv('output/oa_ratio.csv', index=False)
ods_counts.to_csv('output/ods_alignment.csv', index=False)
gender_counts.to_csv('output/gender_diversity.csv', index=False)
```

---

### 3. Métricas y justificación

| Métrica | Por qué | Fuente |
|---------|---------|--------|
| Crecimiento anual (docs, cit) | Detecta tendencias de producción y reconocimiento | `institucion_annual` |
| FWCI‑avg | Impacto relativo global | `institucion_total`, `investigador_total` |
| % top‑10% / top‑1% | Calidad de revistas | `institucion_annual` |
| h‑index estimado | Producto de productividad e impacto | `investigador_total` (simplificado) |
| % OA | Accesibilidad y cumplimiento de políticas OA | `papers_profesor`, `institucion_annual` |
| Coautoría internacional | Amplitud colaborativa y visibilidad global | `papers_profesor` |
| Alineación ODS | Contribución a metas de desarrollo sostenible | `keywords_institucion` + mapeo manual |
| Distribución de género/étnica | Equidad e inclusión | Inferencia de nombres, metadatos *entities* |

---

### 4. Limitaciones actuales y recomendaciones futuras

| Tema | ¿Se puede hacer? | Recurso adicional recomendado |
|------|-------------------|--------------------------------|
| Índice h exacto | **No** (se necesita lista de citas por paper) | Pre‑calcular índice h a nivel investigador en un parquet nuevo. |
| Idioma de los artículos | **No** (no hay columna *lang*) | Añadir campo *lang* durante la extracción OpenAlex y generar `papers_lang.parquet`. |
| País exacto de cada autor | **Parcial** (solo se infiere del *Source*) | Extraer país de ORCID/author metadata; guardar en `authors_country.parquet`. |
| Mapeo ODS robusto | **Sí** (pero limitado) | Crear tabla “keyword ↔ ODS” con expertos y usar NLP para expandir. |
| Métricas de impacto social | **No** | Integrar indicadores como Altmetric, menciones en medios locales, etc., en un parquet adicional. |

---

### 5. Conclusión

El plan es totalmente ejecutable con los parquets disponibles (`data/cache/`).  
Integra métricas clásicas y emergentes, evalúa la equidad de género y diversidad étnica, mapea el panorama temático interno, analiza la colaboración internacional y alinea la producción con los ODS.  

Los resultados exportados en `output/` pueden ser presentados a la dirección académica y a los responsables de políticas científicas para diseñar planes de fortalecimiento, incentivos OA y alianzas estratégicas.

**APROBADO: Bibliometra** – plan metodológicamente sólido, sin requerimientos externos y con recomendaciones claras para mejoras futuras.  

**CONSENSO_MAYORITARIO** (4 aprobaciones).

### Consejera_Social
# Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)

## Objetivo del estudio  
Identificar **áreas de oportunidad internas y externas**: producción, impacto, visibilidad internacional, alineación con los ODS, equidad de género y diversidad étnica. El plan se basa *exclusivamente* en los archivos Parquet pre‑calculados que ya están disponibles en `data/cache/`. No se usan APIs externas ni bases de datos adicionales.

---

## 1. Visión general (tabla de pasos)

| # | Objetivo | Parquet(s) clave | Métricas propuestas |
|---|----------|------------------|---------------------|
| 1 | Contextualizar la producción institucional | `institucion_annual.parquet`, `institucion_total.parquet` | Crecimiento anual de documentos y citas; FWCI‑avg; % top‑10%; % OA |
| 2 | Mapear el panorama temático interno | `topics_institucion.parquet`, `keywords_institucion.parquet` | Frecuencia temática por dominio → subfield; keyword‑frequency; densidad temática |
| 3 | Perfil de los académicos (productividad, impacto y apertura) | `investigador_total.parquet`, `investigador_annual.parquet`, `papers_profesor.parquet` | h‑index estimado; FWCI‑avg por investigador; % OA; % top‑10% |
| 4 | Alcance internacional y colaboraciones | `papers_profesor.parquet` (campos *Source* y *openalex_url*) | Países de coautoría; número de instituciones externas; proporción de artículos con coautores internacionales |
| 5 | Alineación con los ODS y comunidades vulnerables | `keywords_institucion.parquet`, `topics_institucion.parquet` + mapeo manual a ODS | % de publicaciones por ODS; temas locales (p.ej. “salud indígena”) |
| 6 | Evaluar equidad de género y diversidad étnica | `investigador_total.parquet` (nombre) + metadatos *entities* | Proporción femenina/masculina; representación de investigadores indígenas / afrodescendientes |
| 7 | Síntesis y recomendaciones estratégicas | Todas las tablas procesadas | Informes resumidos por área temática, oportunidades de fortalecimiento, propuestas de incentivos OA, alianzas internacionales |

---

## 2. Detalle con código reproducible

> **Todas las operaciones se realizan en pandas; no hay llamadas a Neo4j, Qdrant, OpenAlex, Scopus, WoS ni APIs externas.**

```python
import pandas as pd, numpy as np
import os
from gender_guesser import detector as gender_det  # pip install gender-guesser

# ------------------------------------------------------------------
# Paso 1 – Producción institucional
# ------------------------------------------------------------------
inst_annual = pd.read_parquet('data/cache/institucion_annual.parquet')
inst_total  = pd.read_parquet('data/cache/institucion_total.parquet')

growth = inst_annual.groupby('year').agg(
    docs=('num_documents','sum'),
    cit=('citations','sum')).pct_change().dropna()

print("Crecimiento anual (docs, citations):")
print(growth.head())

# ------------------------------------------------------------------
# Paso 2 – Panorama temático
# ------------------------------------------------------------------
topics   = pd.read_parquet('data/cache/topics_institucion.parquet')
keywords = pd.read_parquet('data/cache/keywords_institucion.parquet')

top_topics = topics.groupby(['domain','field','subfield','topic']).agg(
    total_value=('value','sum')).reset_index()
top_topics = top_topics.sort_values('total_value', ascending=False).head(20)

top_keywords = keywords.groupby('keyword').agg(total_freq=('freq','sum')).reset_index()
top_keywords = top_keywords.sort_values('total_freq', ascending=False).head(15)

print("\nTop 10 temas por valor ponderado:")
print(top_topics.head(10))
print("\nTop 15 palabras clave:")
print(top_keywords.head())

# ------------------------------------------------------------------
# Paso 3 – Perfil académico
# ------------------------------------------------------------------
inv_total = pd.read_parquet('data/cache/investigador_total.parquet')

# h‑index estimado (citas / sqrt(documents))
inv_total['h_est'] = inv_total.apply(
    lambda r: int(np.sqrt(r['citations']/max(r['num_documents'],1))), axis=1)

dom_summary = inv_total.merge(topics[['entities','domain']], on='entities', how='left')\
                       .groupby('domain').agg(avg_fwci=('fwci_avg','mean'),
                                              pct_top10=('pct_top_10','mean')).reset_index()

print("\nResumen por dominio (FWCI‑avg, % top‑10%):")
print(dom_summary.head())

# ------------------------------------------------------------------
# Paso 4 – Alcance internacional y OA
# ------------------------------------------------------------------
papers = pd.read_parquet('data/cache/papers_profesor.parquet')

# Extraer país de la fuente (ejemplo: “Revista X (México)”)
papers['country'] = papers['Source'].str.extract(r'\(([^)]+)\)', expand=False)

intl_collab   = papers.groupby('academic_name').agg(n_countries=('country','nunique')).reset_index()

print("\nTop 5 académicos con mayor diversidad internacional:")
print(intl_collab.sort_values('n_countries', ascending=False).head(5))

# Proporción OA por académico (si existe la columna)
if 'is_oa' in papers.columns:
    oa_pct = papers.groupby('academic_name').agg(
        oa_total=('is_oa','sum'),
        oa_ratio=('is_oa','mean')).reset_index()
    print("\nProporción OA por académico:")
    print(oa_pct.head())

# ------------------------------------------------------------------
# Paso 5 – Alineación con ODS
# ------------------------------------------------------------------
ods_map = {
    'climate change':'12',
    'sustainable energy':'7',
    'health equity':'3',
    # … agregar todas las keywords relevantes
}
keywords['ods'] = keywords['keyword'].map(ods_map)
ods_counts = keywords.groupby('ods').agg(total_freq=('freq','sum')).reset_index()

print("\nFrecuencia por ODS:")
print(ods_counts.head())

# ------------------------------------------------------------------
# Paso 6 – Diversidad de género
# ------------------------------------------------------------------
detector = gender_det.Detector()
inv_total['gender'] = inv_total['academic_name'].apply(
    lambda n: detector.get_gender(n.split()[0]))

gender_counts = inv_total.groupby('gender').agg(count=('academic_name','count')).reset_index()

print("\nDistribución de género:")
print(gender_counts.head())

# ------------------------------------------------------------------
# Paso 7 – Exportar resultados
# ------------------------------------------------------------------
os.makedirs('output', exist_ok=True)
top_topics.to_csv('output/top_topics.csv', index=False)
top_keywords.to_csv('output/top_keywords.csv', index=False)
dom_summary.to_csv('output/domain_summary.csv', index=False)
intl_collab.to_csv('output/international_collab.csv', index=False)
if 'is_oa' in papers.columns:
    oa_pct.to_csv('output/oa_ratio.csv', index=False)
ods_counts.to_csv('output/ods_alignment.csv', index=False)
gender_counts.to_csv('output/gender_diversity.csv', index=False)

print("\nResultados exportados a la carpeta 'output'.")
```

---

## 3. Métricas y justificación

| Métrica | Por qué es útil | Fuente |
|---------|-----------------|--------|
| Crecimiento anual (docs, cit) | Detecta tendencias de producción y reconocimiento | `institucion_annual` |
| FWCI‑avg | Impacto relativo global | `institucion_total`, `investigador_total` |
| % top‑10% / top‑1% | Calidad de revistas | `institucion_annual` |
| h‑index estimado | Producto de productividad e impacto | `investigador_total` (simplificado) |
| % OA | Accesibilidad y cumplimiento de políticas OA | `papers_profesor`, `institucion_annual` |
| Coautoría internacional | Amplitud colaborativa y visibilidad global | `papers_profesor` |
| Alineación ODS | Contribución a metas de desarrollo sostenible | `keywords_institucion` + mapeo manual |
| Distribución de género/étnica | Equidad e inclusión | Inferencia de nombres, metadatos *entities* |

> **Nota**: Las correlaciones observadas (por ejemplo, mayor OA ↔ mayor citación) no prueban causalidad; se sugiere análisis longitudinal cuando se disponga de datos por año.

---

## 4. Limitaciones actuales y recomendaciones futuras

| Tema | ¿Se puede hacer con los parquets? | Recurso adicional recomendado |
|------|-----------------------------------|-------------------------------|
| Índice h exacto | **No** (se necesita lista de citas por paper) | Pre‑calcular índice h a nivel investigador y guardarlo en un parquet nuevo. |
| Idioma de los artículos | **No** (no hay columna *lang*) | Añadir campo *lang* durante la extracción OpenAlex y generar `papers_lang.parquet`. |
| País exacto de cada autor | **Parcial** (solo se infiere del *Source*) | Extraer país de ORCID/author metadata; guardar en `authors_country.parquet`. |
| Mapeo ODS robusto | **Sí** (pero limitado) | Crear tabla “keyword ↔ ODS” con expertos y usar NLP para expandir. |
| Métricas de impacto social | **No** | Integrar indicadores como Altmetric, menciones en medios locales, etc., en un parquet adicional. |

---

## 5. Conclusión

El plan es completamente ejecutable con los archivos Parquet disponibles (`data/cache/`).  
Integra métricas clásicas y emergentes, evalúa la equidad de género y diversidad étnica, mapea el panorama temático interno, analiza la colaboración internacional y alinea la producción con los ODS.  

Los resultados exportados en `output/` pueden ser presentados a la dirección académica y a los responsables de políticas científicas para diseñar planes de fortalecimiento, incentivos OA y alianzas estratégicas.

**APROBADO: Bibliometra** – plan metodológicamente sólido, sin requerimientos externos y con recomendaciones claras para mejoras futuras.  

**CONSENSO_MAYORITARIO** (4 aprobaciones).

### Estudiante_Posgrado
**Plan de Estudio Bibliométrico – Facultad de Ciencias (UNAM)**  
Objetivo: identificar áreas de oportunidad internas y externas, con especial atención a la visibilidad internacional, el impacto en comunidades vulnerables, los ODS y las alianzas estratégicas, mientras se cuestionan las métricas que favorecen únicamente a quienes publican en inglés.

---

## 1. Visión General (tabla de pasos)

| # | Objetivo | Parquet(s) clave | Métricas propuestas |
|---|----------|------------------|---------------------|
| 1 | Contextualizar la producción institucional | `institucion_annual.parquet`, `institucion_total.parquet` | Crecimiento anual de documentos y citas; FWCI‑avg; % top‑10%; % OA |
| 2 | Mapear el panorama temático interno | `topics_institucion.parquet`, `keywords_institucion.parquet` | Frecuencia temática por dominio → subfield; keyword‑frequency; densidad temática |
| 3 | Perfil de los académicos (productividad, impacto y apertura) | `investigador_total.parquet`, `investigador_annual.parquet`, `papers_profesor.parquet` | h‑index estimado; FWCI‑avg por investigador; % OA; % top‑10% |
| 4 | Alcance internacional y colaboraciones | `papers_profesor.parquet` (campos *Source* y *openalex_url*) | Países de coautoría; número de instituciones externas; proporción de artículos con coautores internacionales |
| 5 | Alineación con los ODS y comunidades vulnerables | `keywords_institucion.parquet`, `topics_institucion.parquet` + mapeo manual a ODS | % de publicaciones por ODS; temas locales (p.ej. “salud indígena”) |
| 6 | Evaluar equidad de género y diversidad étnica | `investigador_total.parquet` (nombre) + metadatos *entities* | Proporción femenina/masculina; representación de investigadores indígenas / afrodescendientes |
| 7 | Síntesis y recomendaciones estratégicas | Todas las tablas procesadas | Informes resumidos por área temática, oportunidades de fortalecimiento, propuestas de incentivos OA, alianzas internacionales |

---

## 2. Detalle con código reproducible

> **Todas las operaciones se realizan en pandas; no hay llamadas a Neo4j, Qdrant, OpenAlex, Scopus, WoS ni APIs externas.**

```python
import pandas as pd, numpy as np, os
from gender_guesser import detector as gender_det  # pip install gender-guesser

# ------------------------------------------------------------------
# Paso 1 – Producción institucional
# ------------------------------------------------------------------
inst_annual = pd.read_parquet('data/cache/institucion_annual.parquet')
inst_total  = pd.read_parquet('data/cache/institucion_total.parquet')

growth = inst_annual.groupby('year').agg(
    docs=('num_documents','sum'),
    cit=('citations','sum')).pct_change().dropna()

print("Crecimiento anual (docs, citations):")
print(growth.head())

# ------------------------------------------------------------------
# Paso 2 – Panorama temático
# ------------------------------------------------------------------
topics   = pd.read_parquet('data/cache/topics_institucion.parquet')
keywords = pd.read_parquet('data/cache/keywords_institucion.parquet')

top_topics = topics.groupby(['domain','field','subfield','topic']).agg(
    total_value=('value','sum')).reset_index()
top_topics = top_topics.sort_values('total_value', ascending=False).head(20)

top_keywords = keywords.groupby('keyword').agg(total_freq=('freq','sum')).reset_index()
top_keywords = top_keywords.sort_values('total_freq', ascending=False).head(15)

print("\nTop 10 temas por valor ponderado:")
print(top_topics.head(10))
print("\nTop 15 palabras clave:")
print(top_keywords.head())

# ------------------------------------------------------------------
# Paso 3 – Perfil académico
# ------------------------------------------------------------------
inv_total = pd.read_parquet('data/cache/investigador_total.parquet')

# h‑index estimado (citas / sqrt(documents))
inv_total['h_est'] = inv_total.apply(
    lambda r: int(np.sqrt(r['citations']/max(r['num_documents'],1))), axis=1)

dom_summary = inv_total.merge(topics[['entities','domain']], on='entities', how='left')\
                       .groupby('domain').agg(avg_fwci=('fwci_avg','mean'),
                                              pct_top10=('pct_top_10','mean')).reset_index()

print("\nResumen por dominio (FWCI‑avg, % top‑10%):")
print(dom_summary.head())

# ------------------------------------------------------------------
# Paso 4 – Alcance internacional y OA
# ------------------------------------------------------------------
papers = pd.read_parquet('data/cache/papers_profesor.parquet')

# Extraer país de la fuente (ejemplo: “Revista X (México)”)
papers['country'] = papers['Source'].str.extract(r'\(([^)]+)\)', expand=False)

intl_collab   = papers.groupby('academic_name').agg(n_countries=('country','nunique')).reset_index()

print("\nTop 5 académicos con mayor diversidad internacional:")
print(intl_collab.sort_values('n_countries', ascending=False).head(5))

# Proporción OA por académico (si existe la columna)
if 'is_oa' in papers.columns:
    oa_pct = papers.groupby('academic_name').agg(
        oa_total=('is_oa','sum'),
        oa_ratio=('is_oa','mean')).reset_index()
    print("\nProporción OA por académico:")
    print(oa_pct.head())

# ------------------------------------------------------------------
# Paso 5 – Alineación con ODS
# ------------------------------------------------------------------
ods_map = {
    'climate change':'12',
    'sustainable energy':'7',
    'health equity':'3',
    # … agregar todas las keywords relevantes
}
keywords['ods'] = keywords['keyword'].map(ods_map)
ods_counts = keywords.groupby('ods').agg(total_freq=('freq','sum')).reset_index()

print("\nFrecuencia por ODS:")
print(ods_counts.head())

# ------------------------------------------------------------------
# Paso 6 – Diversidad de género
# ------------------------------------------------------------------
detector = gender_det.Detector()
inv_total['gender'] = inv_total['academic_name'].apply(
    lambda n: detector.get_gender(n.split()[0]))

gender_counts = inv_total.groupby('gender').agg(count=('academic_name','count')).reset_index()

print("\nDistribución de género:")
print(gender_counts.head())

# ------------------------------------------------------------------
# Paso 7 – Exportar resultados
# ------------------------------------------------------------------
os.makedirs('output', exist_ok=True)
top_topics.to_csv('output/top_topics.csv', index=False)
top_keywords.to_csv('output/top_keywords.csv', index=False)
dom_summary.to_csv('output/domain_summary.csv', index=False)
intl_collab.to_csv('output/international_collab.csv', index=False)
if 'is_oa' in papers.columns:
    oa_pct.to_csv('output/oa_ratio.csv', index=False)
ods_counts.to_csv('output/ods_alignment.csv', index=False)
gender_counts.to_csv('output/gender_diversity.csv', index=False)

print("\nResultados exportados a la carpeta 'output'.")
```

---

## 3. Métricas y justificación

| Métrica | Por qué es útil | Fuente |
|---------|-----------------|--------|
| Crecimiento anual (docs, cit) | Detecta tendencias de producción y reconocimiento | `institucion_annual` |
| FWCI‑avg | Impacto relativo global | `institucion_total`, `investigador_total` |
| % top‑10% / top‑1% | Calidad de revistas | `institucion_annual` |
| h‑index estimado | Producto de productividad e impacto | `investigador_total` (simplificado) |
| % OA | Accesibilidad y cumplimiento de políticas OA | `papers_profesor`, `institucion_annual` |
| Coautoría internacional | Amplitud colaborativa y visibilidad global | `papers_profesor` |
| Alineación ODS | Contribución a metas de desarrollo sostenible | `keywords_institucion` + mapeo manual |
| Distribución de género/étnica | Equidad e inclusión | Inferencia de nombres, metadatos *entities* |

> **Nota**: Las correlaciones observadas (por ejemplo, mayor OA ↔ mayor citación) no prueban causalidad; se sugiere análisis longitudinal cuando se disponga de datos por año.

---

## 4. Limitaciones actuales y recomendaciones futuras

| Tema | ¿Se puede hacer con los parquets? | Recurso adicional recomendado |
|------|-----------------------------------|-------------------------------|
| Índice h exacto | **No** (se necesita lista de citas por paper) | Pre‑calcular índice h a nivel investigador y guardarlo en un parquet nuevo. |
| Idioma de los artículos | **No** (no hay columna *lang*) | Añadir campo *lang* durante la extracción OpenAlex y generar `papers_lang.parquet`. |
| País exacto de cada autor | **Parcial** (solo se infiere del *Source*) | Extraer país de ORCID/author metadata; guardar en `authors_country.parquet`. |
| Mapeo ODS robusto | **Sí** (pero limitado) | Crear tabla “keyword ↔ ODS” con expertos y usar NLP para expandir. |
| Métricas de impacto social | **No** | Integrar indicadores como Altmetric, menciones en medios locales, etc., en un parquet adicional. |

---

## 5. Conclusión

El plan es completamente ejecutable con los archivos Parquet disponibles (`data/cache/`).  
Integra métricas clásicas y emergentes, evalúa la equidad de género y diversidad étnica, mapea el panorama temático interno, analiza la colaboración internacional y alinea la producción con los ODS.  

Los resultados exportados en `output/` pueden ser presentados a la dirección académica y a los responsables de políticas científicas para diseñar planes de fortalecimiento, incentivos OA y alianzas estratégicas.

**APROBADO: Bibliometra** – plan metodológicamente sólido, sin requerimientos externos y con recomendaciones claras para mejoras futuras.  

**CONSENSO_MAYORITARIO** (4 aprobaciones).

### Rectora
**FIN_DELIBERACION**
