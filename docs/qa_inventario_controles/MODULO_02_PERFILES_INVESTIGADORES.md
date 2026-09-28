# Inventario de Controles: Módulo 2 - Perfiles de Investigadores
**Archivo Origen (Streamlit):** `dashboard_v2.py` (Líneas 870–912, 2345–2480), `lib/citations_explorer.py`, `dashboard_analytics.py`  
**Archivo Destino (React):** `frontend/src/pages/ResearcherPage.jsx` y `frontend/src/components/Navbar.jsx`  
**Soporte Multilingüe:** 🇲🇽 ES &bull; 🇧🇷 PT &bull; 🇺🇸 EN  

---

## 1. Inventario Detallado de Controles

| # | ID de Control en Streamlit | Tipo de Control | Etiqueta / Propósito Original | Clave i18n Propuesta | Comportamiento Esperado en React | Estado QA |
| :-: | :--- | :--- | :--- | :--- | :--- | :-: |
| 1 | `search_academic_input` | Text Input / Autocompletado | 🔍 Búsqueda de Investigador | `researcher.search_placeholder` | Búsqueda predictiva instantánea con menú flotante (debounced 250ms). | [x] |
| 2 | `btn_select_academic` | Button / List Item | Ver Detalle de Investigador | `researcher.btn_view_profile` | Carga asíncrona del perfil sin refrescar la página. | [x] |
| 3 | `badge_snii_level` | UI Badge | Nivel SNII (C, 1, 2, 3, Emérito) | `researcher.snii_badge` | Píldora de color distintivo con tooltip del padrón oficial 2026. | [x] |
| 4 | `badge_orcid_verified` | UI Badge / Link | ORCID iD con link oficial | `researcher.orcid_verified` | Enlace externo a `https://orcid.org/{orcid}` con icono verificado verde. | [x] |
| 5 | `badge_affiliation` | UI Breadcrumb | Adscripción Jerárquica Completa | `researcher.affiliation` | Muestra Institución ➔ Dependencia ➔ Subdependencia con enlaces. | [x] |
| 6 | `kpi_inv_total_works` | KPI Metric Card | Producción Total de Obras | `researcher.kpi_works` | Cifra total con icono y tendencia. | [x] |
| 7 | `kpi_inv_total_citations` | KPI Metric Card | Total Citas Brutas | `researcher.kpi_citations` | Conteo total de citas indexadas en ClickHouse. | [x] |
| 8 | `kpi_inv_net_citations` | KPI Metric Card | Citas Netas (Sin Autocitas) | `researcher.kpi_net_citations` | Citas de terceros calculadas mediante motor Zero-Join. | [x] |
| 9 | `kpi_inv_self_citations` | KPI Metric Card | % Autocitas Directas | `researcher.kpi_self_citations` | Porcentaje de autocitas con desglose de citas exactas. | [x] |
| 10 | `kpi_inv_h_index` | KPI Metric Card | Índice H | `researcher.kpi_h_index` | Cálculo dinámico y confiable del índice de Hirsch. | [x] |
| 11 | `kpi_inv_fwci` | KPI Metric Card | FWCI Promedio del Autor | `researcher.kpi_fwci` | Impacto normalizado por campo y año. | [x] |
| 12 | `kpi_inv_top10` | KPI Metric Card | % Obras en Top 10% Global | `researcher.kpi_top10` | Porcentaje de publicaciones de excelencia mundial. | [x] |
| 13 | `input_filter_works` | Text Input | Filtrar obras por título, revista o año | `researcher.filter_works_placeholder` | Filtrado instantáneo en memoria sobre la tabla de obras. | [x] |
| 14 | `filter_quartile_select` | Multi-select / Pills | Filtrar por Cuartil (Q1, Q2, Q3, Q4) | `researcher.filter_quartiles` | Filtro por cuartiles de impacto con conteo de obras por cuartil. | [x] |
| 15 | `filter_oa_select` | Multi-select / Pills | Filtrar por Tipo de Acceso Abierto | `researcher.filter_oa` | Filtro por vías OA (Gold, Diamond, Green, Hybrid, Closed). | [x] |
| 16 | `table_publications` | Data Table | Tabla Interactiva de Publicaciones | `researcher.table_works` | Tabla paginada con título, año, revista, cuartil, citas recibidas y link DOI. | [x] |
| 17 | `btn_toggle_citations_explorer`| Tab / Button | Explorador de Citas & Autocitas (Zero-Join) | `researcher.tab_citations_explorer` | Pestaña analítica detallada de artículos citantes. | [x] |
| 18 | `note_self_citations_method` | Caption / Alert | Nota metodológica sobre autocitas | `researcher.self_citations_note` | Explicación clara de conteo exclusivo de autocitas directas con OpenAlex IDs. | [x] |
| 19 | `chart_citing_countries` | Plotly Bar Chart | Países Citantes (Distribución Global) | `researcher.chart_countries` | Gráfico de barras horizontales con banderas y conteo de citas. | [x] |
| 20 | `chart_citing_institutions` | Plotly Bar Chart | Instituciones que Citan al Autor | `researcher.chart_institutions` | Universidades e institutos internacionales citantes. | [x] |
| 21 | `table_citing_papers` | Data Table | Detalle de Trabajos Citantes | `researcher.table_citing_works` | Artículos citantes con título, primer autor, año, revista y si es autocita. | [x] |
| 22 | `btn_open_dossier_drawer` | Button | 📄 Generador de Reporte (1-Clic) | `researcher.btn_generate_report` | Abre el drawer deslizable lateral para preview y descarga de PDF/MD. | [x] |

---

## 2. Textos Multilingües Clave Requeridos (i18n)

```javascript
// Claves a incluir en es.js, pt.js, en.js
researcher: {
  title: "Perfil del Investigador",
  search_placeholder: "Buscar investigador por nombre, apellido o ORCID...",
  kpi_works: "Publicaciones",
  kpi_citations: "Citas Totales",
  kpi_net_citations: "Citas Netas",
  kpi_self_citations: "Autocitas Directas",
  kpi_h_index: "Índice H",
  kpi_fwci: "FWCI",
  kpi_top10: "En Top 10% Global",
  self_citations_note: "Se contabilizan exclusivamente las autocitas directas del autor evaluado mediante OpenAlex Author IDs.",
  btn_generate_report: "Generar Reporte de Trayectoria",
  filter_quartiles: "Cuartiles",
  filter_oa: "Acceso Abierto"
}
```
