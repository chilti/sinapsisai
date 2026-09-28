# Inventario de Controles: Módulo 1 - Panorama Institucional y Cartografía de Desempeño
**Archivo Origen (Streamlit):** `dashboard_v2.py` (Líneas 715–815, 2320–2345) y `dashboard_analytics.py` (`render_institucion_view`, Líneas 1264–1956)  
**Archivo Destino (React):** `frontend/src/components/modules/InstitutionalPanorama.jsx`  
**Soporte Multilingüe:** 🇲🇽 ES &bull; 🇧🇷 PT &bull; 🇺🇸 EN  
**Caché de Datos:** `analytics_cache.duckdb` & Parquets en `data/cache/` (52 columnas analíticas precalculadas, Zero-Join)

---

## 1. Inventario Detallado de Controles y Visualizadores

| # | ID de Control en Streamlit | Tipo de Elemento | Etiqueta / Propósito Original | Clave i18n Propuesta | Comportamiento Esperado en React | Estado QA |
| :-: | :--- | :--- | :--- | :--- | :--- | :-: |
| 1 | `selected_institution_sidebar` | Selectbox / Autocompletado | 🏛️ Institución (UNAM por defecto) | `institutional.select_institution` | Autocompletado reactivo desde `/api/hierarchy/institutions`. | [x] |
| 2 | `selected_dep_sidebar` | Selectbox | 🏢 Dependencia (filtrada por institución) | `institutional.select_dependency` | Se actualiza automáticamente al cambiar institución. Permite valor vacío (Toda la institución). | [x] |
| 3 | `selected_sub_sidebar` | Selectbox | 🎯 Subdependencia / Centro | `institutional.select_subdependency` | Se actualiza según la dependencia elegida. Opción "Todas las subdependencias". | [x] |
| 4 | `view_mode_perspective` | Radio / Segmented Toggle | Perspectiva Analítica: Capacidad Instalada vs Producción Institucional | `institutional.perspective_mode` | Conmuta entre producción de académicos adscritos vs papers con firma institucional directa. | [x] |
| 5 | `badge_institutional_ids` | UI Badges / External Links | Identificadores: ROR ID, OpenAlex ID, Tipo, País | `institutional.identifiers` | Píldoras con enlaces directos verificados a `https://ror.org/...` y `https://openalex.org/...`. | [x] |
| 6 | `kpis_academic_ids` | KPI Metric Cards (Grupo 1) | Identificadores de Académicos (4 métricas) | `institutional.kpi_group_ids` | `% Académicos con ORCID`, `% con algún ID`, `% SNII con ORCID`, `% SNII con algún ID`. | [x] |
| 7 | `kpis_general_metrics` | KPI Metric Cards (Grupo 2) | Métricas Generales (7 métricas) | `institutional.kpi_group_general` | `Producción Total` (Neo4j), `Indizada en OpenAlex`, `No. SNIIs 2025`, `Citas Acumuladas`, `Citas/artículo`, `FWCI Promedio`, `% Open Access`. | [x] |
| 8 | `kpis_excellence_metrics` | KPI Metric Cards (Grupo 3) | Métricas de Excelencia (3 métricas) | `institutional.kpi_group_excellence` | `Percentil Promedio`, `% Top 10%`, `% Top 1%` de citación mundial. | [x] |
| 9 | `kpis_velocity_collab` | KPI Metric Cards (Grupo 4) | Velocidad de Citas y Colaboración (5 métricas) | `institutional.kpi_group_velocity` | `Citas/año (avg)`, `Citas últ. 3 años`, `% Colaboración Internacional`, `Países/paper (avg)`, `Autores/paper (avg)`. | [x] |
| 10 | `kpis_apc_costs` | KPI Metric Cards (Grupo 5) | Acceso Abierto y Costos APC (3 métricas) | `institutional.kpi_group_apc` | `APC Total ($ USD estimado)`, `% Papers con APC`, `Vida Media Citas (años)`. | [x] |
| 11 | `chart_oa_donut` | Plotly Donut Chart | Distribución Open Access | `institutional.chart_oa_donut` | Desglose porcentual y numérico por vía: Gold, Green, Hybrid, Bronze y Closed. | [x] |
| 12 | `table_thematic_profile` | Summary Table / Grid | Perfil Temático y Concentración (Gini) | `institutional.table_thematic_profile` | `Índice de Gini temático`, `Dominios de investigación`, `Tópicos únicos` y `Dominio principal`. | [x] |
| 13 | `chart_document_types` | Plotly Donut Chart | Distribución por Tipos de Documentos | `institutional.chart_doc_types` | Proporción de artículos, capítulos de libro, revisiones y actas de congreso. | [x] |
| 14 | `expander_methodological_glossary`| Accordion / Collapsible | Glosario Metodológico Interactivo | `institutional.methodology_glossary` | Definiciones exhaustivas de los 14 indicadores cienciométricos oficiales. | [x] |
| 15 | `chart_annual_documents_area` | Plotly Area Chart | Documentos Publicados por Año (1950–2026) | `institutional.chart_annual_docs` | Gráfico de área interactivo con conteo histórico de publicaciones por año. | [x] |
| 16 | `chart_annual_fwci_line` | Plotly Line Chart | Evolución FWCI Promedio Institucional | `institutional.chart_annual_fwci` | Gráfico de línea con umbral horizontal en 1.0 (Promedio Mundial de referencia). | [x] |
| 17 | `chart_thematic_sunburst` | Plotly Sunburst 4-Levels | Temáticas de Investigación (Sunburst) | `institutional.chart_sunburst` | Desglose jerárquico interactivo: `domain` ➔ `field` ➔ `subfield` ➔ `topic` con escala de color Blues. | [x] |
| 18 | `chart_keywords_cloud` | Chips / Bar Grid | Vocabulario Científico Institucional (Keywords) | `institutional.keywords_vocab` | Términos científicos más representativos con sus frecuencias relativas. | [x] |
| 19 | `chart_intl_collab_evolution` | Plotly Line / Area Chart | Evolución % Colaboración Internacional | `institutional.chart_intl_collab` | Porcentaje anual de publicaciones con coautoría internacional (0–100%). | [x] |
| 20 | `chart_oa_annual_stacked` | Plotly Stacked Bar Chart | Evolución del Acceso Abierto por Año | `institutional.chart_oa_stacked` | Barras apiladas anuales por vía de OA (`Gold`, `Green`, `Hybrid`, `Bronze`, `Closed`). | [x] |
| 21 | `matrix_sdg_impact` | Interactive Grid (17 ODS) | Impacto Global en Sostenibilidad (ODS 1–17) | `institutional.matrix_sdg` | Matriz oficial con los 17 Objetivos de la ONU, códigos de color y conteo de obras asociadas. | [x] |
| 22 | `table_institutional_publications`| Interactive Data Table | Publicaciones de la Institución | `institutional.table_publications` | Tabla completa paginada con filtros por Año y por ODS, enlaces a DOI y OpenAlex. | [x] |

---

## 2. Textos Multilingües Clave Requeridos (i18n)

```javascript
institutional: {
  title: "Panorama Institucional",
  perspective_installed: "Capacidad Instalada",
  perspective_institutional: "Producción Institucional",
  select_institution: "Institución",
  select_dependency: "Dependencia",
  select_subdependency: "Subdependencia / Centro",
  identifiers: {
    ror: "ROR ID",
    openalex: "OpenAlex ID",
    type: "Tipo de Institución",
    country: "País"
  },
  kpi_groups: {
    academic_ids: "Identificadores de Académicos",
    general: "Métricas Generales",
    excellence: "Métricas de Excelencia",
    velocity: "Velocidad de Citas y Colaboración",
    costs: "Acceso Abierto y Costos (APC)"
  },
  charts: {
    oa_distribution: "Distribución Open Access",
    thematic_profile: "Perfil Temático (Gini)",
    document_types: "Tipos de Documentos",
    annual_production: "Documentos Publicados por Año",
    annual_fwci: "Evolución FWCI Promedio",
    sunburst_topics: "Temáticas de Investigación Institucional",
    keywords: "Vocabulario Científico (Keywords)",
    intl_collaboration: "Colaboración Internacional (%)",
    annual_oa_stacked: "Evolución de Acceso Abierto por Año",
    sdg_matrix: "Impacto Global en Sostenibilidad (ODS)",
    publications_table: "Publicaciones Científicas"
  }
}
```
