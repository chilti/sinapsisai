# Inventario de Controles: Módulo 3 - Mapas de la Ciencia (WebGL)
**Archivo Origen (Streamlit):** `dashboard_maps.py` y `dashboard_v2.py` (Líneas 1685–1780)  
**Archivo Destino (React):** `frontend/src/pages/ScienceMapsPage.jsx` y `frontend/src/components/WebGLCanvas.jsx`  
**Soporte Multilingüe:** 🇲🇽 ES &bull; 🇧🇷 PT &bull; 🇺🇸 EN  

---

## 1. Inventario Detallado de Controles

| # | ID de Control en Streamlit | Tipo de Control | Etiqueta / Propósito Original | Clave i18n Propuesta | Comportamiento Esperado en React | Estado QA |
| :-: | :--- | :--- | :--- | :--- | :--- | :-: |
| 1 | `emb_model_select` | Selectbox / Radio | Modelo de Embeddings (Nomic v1.5 vs SPECTER2) | `maps.select_embedding_model` | Carga asíncrona de teselas correspondientes (`public/tiles/...`). | [x] |
| 2 | `dimension_mode_toggle` | Segmented Control | Proyección Dimensional (2D vs 3D) | `maps.dimension_mode` | Transición de cámara ortográfica 2D a perspectiva 3D interactiva en WebGL. | [x] |
| 3 | `webgl_canvas_viewport` | WebGL Canvas | Lienzo de Partículas Acelerado por GPU | `maps.canvas_viewport` | Renderizado fluido a 60 FPS con soporte para cientos de miles de artículos. | [x] |
| 4 | `btn_zoom_in` | Button | Zoom + | `maps.btn_zoom_in` | Acerca la cámara centrado en el punto del cursor. | [x] |
| 5 | `btn_zoom_out` | Button | Zoom - | `maps.btn_zoom_out` | Aleja la cámara manteniendo el encuadre. | [x] |
| 6 | `btn_reset_view` | Button | Resetear Cámara / Centrar | `maps.btn_reset_camera` | Restablece la vista al encuadre óptimo de todos los clusters. | [x] |
| 7 | `search_paper_in_map` | Text Input | 🔍 Buscar artículo o autor en el mapa | `maps.search_in_map` | Resalta el nodo buscado con un anillo luminoso y enfoca la cámara. | [x] |
| 8 | `cluster_filter_multiselect` | Multi-select / Pills | Filtrar por Cluster Temático / Tópico | `maps.filter_clusters` | Oculta o atenúa las partículas fuera de los clusters seleccionados. | [x] |
| 9 | `toggle_cluster_labels` | Checkbox / Switch | Mostrar Etiquetas de Tópicos | `maps.toggle_labels` | Muestra/oculta los rótulos de texto en los centroides de clusters. | [x] |
| 10 | `slider_point_size` | Slider | Tamaño de Partículas | `maps.slider_point_size` | Control deslizante interactivo del radio de los nodos. | [x] |
| 11 | `hover_tooltip_card` | Floating Tooltip | Tarjeta de Previsualización al Hover | `maps.hover_tooltip` | Tooltip glassmórfico instantáneo (título, primer autor, año, citas). | [x] |
| 12 | `panel_selected_paper` | Drawer / Modal | Detalle del Artículo Seleccionado | `maps.selected_paper_detail` | Muestra abstract, coautores, revista, enlace OpenAlex y DOI. | [x] |
| 13 | `legend_cluster_colors` | Color Legend | Leyenda de Categorías Temáticas | `maps.legend_title` | Paleta de colores interactiva que permite filtrar al dar clic en la leyenda. | [x] |
| 14 | `btn_export_map_image` | Download Button | Exportar Captura en Alta Resolución | `maps.btn_export_image` | Descarga PNG/SVG del encuadre actual sin pérdida de nitidez. | [x] |

---

## 2. Textos Multilingües Clave Requeridos (i18n)

```javascript
// Claves a incluir en es.js, pt.js, en.js
maps: {
  title: "Mapas de la Ciencia",
  subtitle: "Cartografía semántica de la producción científica y frentes temáticos",
  select_embedding_model: "Modelo de Espacio Semántico",
  dimension_mode: "Modo de Proyección",
  search_in_map: "Localizar artículo o autor en el mapa...",
  filter_clusters: "Filtrar por Tópicos",
  toggle_labels: "Mostrar nombres de clusters",
  btn_reset_camera: "Centrar Vista",
  btn_export_image: "Exportar Imagen",
  paper_details: {
    citations: "Citas",
    year: "Año",
    journal: "Revista / Fuente",
    view_openalex: "Ver en OpenAlex"
  }
}
```
