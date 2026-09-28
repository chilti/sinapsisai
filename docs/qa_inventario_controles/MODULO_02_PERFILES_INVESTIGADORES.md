# Inventario de Controles: Módulo 2 - Perfiles de Investigadores y Producción Académica
**Archivo Origen (Streamlit):** `dashboard_v2.py` (Líneas 870–912, 2345–2480), `lib/citations_explorer.py`, `dashboard_analytics.py` (`render_investigador_view`, Líneas 1991–2942)  
**Archivo Destino (React):** `frontend/src/components/modules/ResearcherProfiles.jsx`  
**Soporte Multilingüe:** 🇲🇽 ES &bull; 🇧🇷 PT &bull; 🇺🇸 EN  
**Caché de Datos:** `investigador_total.parquet`, `investigador_annual.parquet`, `topics_investigador.parquet`, `keywords_investigador.parquet`, `papers_profesor.parquet`, `thematic_evolution_investigador.parquet` en `data/cache_ch/` (52 columnas analíticas precalculadas, Zero-Join)

---

## 1. Inventario Detallado de Controles y Visualizadores

| # | ID de Control en Streamlit | Tipo de Elemento | Etiqueta / Propósito Original | Clave i18n Propuesta | Comportamiento Esperado en React | Estado QA |
| :-: | :--- | :--- | :--- | :--- | :--- | :--- | :-: |
| 1 | `search_academic_input` | Text Input / Autocompletado | 🔍 Búsqueda de Investigador | `researcher.search_placeholder` | Búsqueda predictiva instantánea con menú flotante (debounced 250ms), botón de limpiar y selección de perfil. | [x] |
| 2 | `header_identity_badges` | UI Badges / External Links | Padrón SNII, Adscripción Jerárquica e Identificadores Externos | `researcher.identity_header` | Badge oficial SNII (Candidato, 1, 2, 3, Emérito), Breadcrumb (Institución ➔ Dependencia ➔ Subdependencia), enlaces verificados a ORCID, CVU, SIIA, Scopus y OpenAlex. | [x] |
| 3 | `dossier_download_buttons` | Button Group | Descargar Reporte (Markdown y Dossier PDF) | `researcher.download_dossier` | Descarga directa de expediente en formato Markdown o PDF en un clic. | [x] |
| 4 | `subtabs_navigation` | Tabs / Navigation | Subpestañas: Producción Académica vs Citas y Autocitas | `researcher.subtabs` | Conmutador interactivo entre la visión de producción del investigador y el explorador de citas y autocitas de toda la carrera. | [x] |
| 5 | `kpis_general_metrics` | KPI Metric Cards (Grupo 1) | Métricas Generales (5 métricas) | `researcher.kpi_group_general` | `Producción Total` (Censo Neo4j), `Indizada en OpenAlex` (Analítica), `Índice H`, `Total Citas`, `% Open Access`. | [x] |
| 6 | `kpis_excellence_metrics` | KPI Metric Cards (Grupo 2) | Métricas de Excelencia (5 métricas) | `researcher.kpi_group_excellence` | `Citas/artículo`, `FWCI Promedio` (vs 1.0 mundial), `Percentil Promedio`, `% Top 10%`, `% Top 1%` de citación mundial. | [x] |
| 7 | `kpis_velocity_collab` | KPI Metric Cards (Grupo 3) | Velocidad de Citas y Colaboración (5 métricas) | `researcher.kpi_group_velocity` | `Citas/año (prom.)`, `Citas últ. 3 años`, `% Colaboración Internacional`, `Países/paper (prom.)`, `Autores/paper (prom.)`. | [x] |
| 8 | `kpis_apc_costs` | KPI Metric Cards (Grupo 4) | Acceso Abierto y Costos APC (3 métricas) | `researcher.kpi_group_apc` | `APC Total ($ USD estimado)`, `% Papers con APC`, `Vida Media Citas (años)`. | [x] |
| 9 | `chart_oa_donut` | Plotly Donut Chart | Distribución Open Access | `researcher.chart_oa_donut` | Desglose porcentual y numérico por vía: Gold, Green, Hybrid, Bronze y Closed. | [x] |
| 10 | `table_thematic_profile` | Summary Table / Grid | Perfil Temático y Concentración (Gini) | `researcher.table_thematic_profile` | `Índice de Gini temático`, `Dominios cubiertos`, `Tópicos únicos` y `Dominio principal`. | [x] |
| 11 | `chart_document_types` | Plotly Donut Chart | Distribución por Tipos de Documentos | `researcher.chart_doc_types` | Proporción de artículos, capítulos de libro, datasets, reportes y preprints según OpenAlex. | [x] |
| 12 | `expander_methodological_glossary`| Accordion / Collapsible | Glosario Metodológico Interactivo | `researcher.methodology_glossary` | Definiciones exhaustivas de los indicadores (FWCI, percentil, APC, Gini, autocitas). | [x] |
| 13 | `chart_annual_trajectory_bar` | Plotly Bar Chart | Trayectoria Histórica (Docs por Año) | `researcher.chart_annual_docs` | Gráfico de barras interactivo con conteo histórico de publicaciones por año (1950–2026). | [x] |
| 14 | `chart_thematic_focus_bar` | Plotly Horizontal Bar Chart | Foco Temático (Top 10 OpenAlex Topics) | `researcher.chart_top_topics` | Barras horizontales ordenadas por volumen de publicaciones en áreas de especialidad. | [x] |
| 15 | `chart_thematic_sunburst` | Plotly Sunburst 4-Levels | Concentración Temática (Sunburst) | `researcher.chart_sunburst` | Desglose jerárquico interactivo: `domain` ➔ `field` ➔ `subfield` ➔ `topic` con escala Blues. | [x] |
| 16 | `chart_keywords_cloud` | Chips / Bar Grid | Vocabulario Científico (Keywords) | `researcher.keywords_vocab` | Términos científicos más representativos con sus frecuencias relativas. | [x] |
| 17 | `matrix_sdg_impact` | Interactive Grid (17 ODS) | Panorama General de Sostenibilidad (ODS 1–17) | `researcher.matrix_sdg` | Matriz oficial con los 17 Objetivos de la ONU, códigos de color y conteo de obras asociadas. | [x] |
| 18 | `table_publications_catalog` | Interactive Data Table | Catálogo de Publicaciones del Investigador | `researcher.table_publications` | Tabla paginada de 10 en 10 con filtros por Año (por defecto año actual 2026), por Vía OA, búsqueda por texto, nombre real de revista, citas, FWCI y enlaces DOI / OpenAlex. | [x] |
| 19 | `kpis_citations_career` | KPI Metric Cards | Métricas de Citas y Autocitas de la Carrera (6 métricas) | `researcher.kpi_citations_career` | `Citas Totales (Carrera)`, `Citas Netas`, `Autocitas Directas`, `Tasa Autocitas %`, `En Top 10% Global`, `Países Citantes` con nota de autocitas directas (del autor). | [x] |
| 20 | `chart_citations_donut` | Plotly Donut Chart | Distribución Citas Netas vs Autocitas Directas | `researcher.chart_citations_donut` | Gráfica de dona con proporción de citas netas vs autocitas directas extendidas a toda la carrera. | [x] |
| 21 | `chart_citing_geopolitics` | Plotly Horizontal Bar Charts | Geopolítica e Instituciones Citantes | `researcher.chart_geopolitics` | Top 10 Países Citantes y Top 10 Instituciones Internacionales que citan al autor. | [x] |
| 22 | `table_citing_works` | Interactive Data Table | Detalle de Trabajos Citantes Indexados | `researcher.table_citing_works` | Lista de publicaciones citantes con título, primer autor, año, revista, badge de autocita directa y citas recibidas. | [x] |

---

## 2. Textos Multilingües Clave Requeridos (i18n)

```javascript
researcher: {
  title: "Perfil del Investigador",
  search_placeholder: "Buscar por nombre de investigador o identificador ORCID...",
  btn_view_profile: "Ver Perfil",
  clear_search: "Limpiar búsqueda",
  identity_header: {
    snii_registered: "Miembro del SNII (SECIHTI)",
    snii_level: "Nivel SNII",
    snii_area: "Área del Conocimiento",
    affiliation: "Adscripción Institucional",
    cvu: "CVU SECIHTI",
    siia: "SIIA UNAM",
    scopus: "Scopus ID",
    openalex: "OpenAlex ID",
    orcid: "ORCID iD"
  },
  download_markdown: "Descargar Reporte (Markdown)",
  download_pdf: "Descargar Dossier (PDF)",
  subtabs: {
    production: "Producción Académica",
    citations: "Análisis de Citas (Zero-Join)"
  },
  kpi_groups: {
    general: "Métricas Generales",
    excellence: "Métricas de Excelencia",
    velocity: "Velocidad de Citas y Colaboración",
    costs: "Acceso Abierto y Costos (APC)",
    zero_join: "Métricas de Impacto y Autocitas"
  },
  charts: {
    oa_distribution: "Distribución Open Access",
    thematic_profile: "Perfil Temático (Gini)",
    document_types: "Tipos de Documentos",
    annual_production: "Trayectoria Histórica (Docs)",
    top_topics: "Foco Temático (Top 10 OpenAlex Topics)",
    sunburst_topics: "Concentración Temática (Sunburst)",
    keywords: "Vocabulario Científico (Keywords)",
    sdg_matrix: "Panorama General de Sostenibilidad (ODS)",
    publications_table: "Catálogo de Publicaciones",
    citations_net_vs_self: "Citas Netas vs Autocitas",
    citing_countries: "Países Citantes",
    citing_institutions: "Instituciones Citantes",
    citing_works_table: "Detalle de Artículos Citantes"
  }
}
```
