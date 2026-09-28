# Inventario de Controles: Módulo 1 - Panorama Institucional
**Archivo Origen (Streamlit):** `dashboard_v2.py` (Líneas 715–815, 2320–2345) y `dashboard_analytics.py`  
**Archivo Destino (React):** `frontend/src/pages/InstitutionalPage.jsx` y `frontend/src/components/Sidebar.jsx`  
**Soporte Multilingüe:** 🇲🇽 ES &bull; 🇧🇷 PT &bull; 🇺🇸 EN  

---

## 1. Inventario Detallado de Controles

| # | ID de Control en Streamlit | Tipo de Control | Etiqueta / Propósito Original | Clave i18n Propuesta | Comportamiento Esperado en React | Estado QA |
| :-: | :--- | :--- | :--- | :--- | :--- | :-: |
| 1 | `selected_institution_sidebar` | Selectbox / Autocompletado | 🏛️ Institución (UNAM por defecto) | `institutional.select_institution` | Autocompletado reactivo desde `/api/hierarchy/institutions` sin re-run. | [ ] |
| 2 | `selected_dep_sidebar` | Selectbox | 🏢 Dependencia (filtrada por institución) | `institutional.select_dependency` | Se actualiza automáticamente al cambiar institución. Permite valor vacío (Toda la institución). | [ ] |
| 3 | `selected_sub_sidebar` | Selectbox | 🎯 Subdependencia / Centro | `institutional.select_subdependency` | Se actualiza según la dependencia elegida. Opción "Todas las subdependencias". | [ ] |
| 4 | `breadcrumbs_inst` | Display UI | Migajas de pan (Inst ➔ Dep ➔ Sub) | `institutional.hierarchy_path` | Barra interactiva con enlaces para subir niveles en el árbol. | [ ] |
| 5 | `load_tab_inst` | Button | ▶️ Cargar Panorama Institucional | `institutional.btn_load_data` | En React se carga de forma inmediata y automática con *skeleton loader* (sin necesidad de botón forzado de carga perezosa). | [ ] |
| 6 | `view_mode_inst` | Radio / Segmented Control | Modo de Vista: General, Capacidad SNII, Producción & Citas, ODS | `institutional.view_mode` | Pestañas o tabs internos con transición animada instantánea. | [ ] |
| 7 | `kpi_total_researchers` | KPI Metric Card | Total de Investigadores en Padrón | `institutional.kpi_researchers` | Tarjeta con cifra formateada, icono y desglose rápido por género. | [ ] |
| 8 | `kpi_total_works` | KPI Metric Card | Total de Obras Científicas | `institutional.kpi_works` | Total de artículos indexados en ClickHouse OpenAlex. | [ ] |
| 9 | `kpi_total_citations` | KPI Metric Card | Total de Citas Recibidas | `institutional.kpi_citations` | Conteo acumulado de citas directas de la entidad. | [ ] |
| 10 | `kpi_avg_fwci` | KPI Metric Card | FWCI Promedio (Impacto Ponderado) | `institutional.kpi_fwci` | Indicador con semáforo de color (verde > 1.0, amarillo = 1.0, rojo < 1.0). | [ ] |
| 11 | `kpi_oa_percent` | KPI Metric Card | % en Acceso Abierto | `institutional.kpi_oa_rate` | Porcentaje global con desglose por vía (Gold, Green, Diamond, Hybrid). | [ ] |
| 12 | `chart_snii_levels` | Plotly Bar Chart | Capacidad Instalada por Nivel SNII | `institutional.chart_snii_distribution` | Gráfico interactivo de barras (Candidato, I, II, III, Emérito) con hover tooltip. | [ ] |
| 13 | `chart_knowledge_areas` | Plotly Donut / Bar | Distribución por Áreas del Conocimiento | `institutional.chart_areas_distribution` | Gráfico de dona o barras de las 9 áreas oficiales del SNII. | [ ] |
| 14 | `chart_temporal_evolution` | Plotly Multi-line / Area | Producción Anual y Citas Temporales | `institutional.chart_annual_evolution` | Gráfico combinado con filtro interactivo de rango de años (2010–2026). | [ ] |
| 15 | `chart_sdg_radar` | Plotly Radar Chart | Alineación con los 17 ODS de la ONU | `institutional.chart_sdg_radar` | Gráfico de radar con puntaje de afinidad por ODS (1 al 17). | [ ] |
| 16 | `network_inter_dependencies` | Force-directed Graph / WebGL | Red de Colaboración Interna | `institutional.chart_collaboration_network` | Visualizador de coautoría entre facultades/institutos de la misma universidad. | [ ] |
| 17 | `table_top_journals` | Data Table | Revistas de Mayor Publicación | `institutional.table_top_sources` | Tabla paginada con buscador, ISSN, cuartil SJR/JCR y conteo de artículos. | [ ] |
| 18 | `btn_export_institutional` | Download Button | Descargar Reporte Institucional (HTML/PDF) | `institutional.btn_export_report` | Genera y descarga el informe ejecutivo consolidado en 1 clic. | [ ] |

---

## 2. Textos Multilingües Clave Requeridos (i18n)

```javascript
// Claves a incluir en es.js, pt.js, en.js
institutional: {
  title: "Panorama Institucional",
  select_institution: "Institución",
  select_dependency: "Dependencia",
  select_subdependency: "Subdependencia / Centro",
  kpi_researchers: "Investigadores SNII",
  kpi_works: "Publicaciones Científicas",
  kpi_citations: "Citas Recibidas",
  kpi_fwci: "FWCI Promedio",
  kpi_oa_rate: "% Acceso Abierto",
  snii_levels: {
    candidate: "Candidato",
    level_1: "Nivel I",
    level_2: "Nivel II",
    level_3: "Nivel III",
    emeritus: "Emérito"
  }
}
```
