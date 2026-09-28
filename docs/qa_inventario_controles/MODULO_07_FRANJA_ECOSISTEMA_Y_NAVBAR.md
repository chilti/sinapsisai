# Inventario de Controles: Módulo 7 - Franja del Ecosistema, Navbar & i18n
**Archivo Origen (Streamlit):** `dashboard_v2.py` (Líneas 580–700, 840–880) y `src/components/Navbar.jsx` (Revistas LATAM)  
**Archivo Destino (React):** `packages/ecosystem-bar/TlachiaSuiteBar.jsx` y `frontend/src/components/Navbar.jsx`  
**Soporte Multilingüe:** 🇲🇽 ES &bull; 🇧🇷 PT &bull; 🇺🇸 EN  

---

## 1. Inventario Detallado de Controles

| # | ID de Control | Tipo de Control | Etiqueta / Propósito | Clave i18n Propuesta | Comportamiento Esperado en React / Web Component | Estado QA |
| :-: | :--- | :--- | :--- | :--- | :--- | :-: |
| 1 | `suite_tab_infotlachia` | Ecosystem Tab | 🏛️ SNII Info TlachIA | `suite.app_infotlachia` | Pestaña activa (resaltado Zafiro `#0284c7`, glow sutil, monograma IT en `Outfit`). | [x] |
| 2 | `suite_tab_revistaslatam` | Ecosystem Tab | 📖 Revistas LATAM | `suite.app_revistaslatam` | Enlace a `/revistaslatam/` con tooltip glassmórfico y monograma RL. | [x] |
| 3 | `suite_tab_knomap` | Ecosystem Tab | 🗺️ KnoMap | `suite.app_knomap` | Enlace a `/knomap/` con isotipo hexagonal SOM y monograma KM. | [x] |
| 4 | `suite_tab_metrics` | Ecosystem Tab | 🔬 TlachIA Metrics | `suite.app_metrics` | Enlace a `/tlachiametrics/` con monograma TM y acento Esmeralda. | [x] |
| 5 | `suite_brand_link` | Link / Logo | 🌐 Ecosistema TlachIA | `suite.brand_title` | Isotipo de red neuronal a la derecha con enlace al portal principal. | [x] |
| 6 | `navbar_lang_selector` | Dropdown Select | 🌐 Selector de Idioma (ES/PT/EN) | `navbar.language_select` | Conmuta instantáneamente todos los textos entre 🇲🇽 ES, 🇧🇷 PT y 🇺🇸 EN. | [x] |
| 7 | `navbar_theme_toggle` | Toggle / Dropdown | 🎨 Selector de Tema | `navbar.theme_select` | Alterna dinámicamente entre temas **Oscuro**, **Navy** y **Claro**. | [x] |
| 8 | `navbar_global_search` | Text Input (Kbd shortcut) | 🔍 Buscador Global (`Ctrl+K` / `/`) | `navbar.search_placeholder` | Búsqueda unificada en tiempo real de investigadores, facultades e institutos. | [x] |
| 9 | `navbar_user_auth_button` | Button / User Pill | 👤 Iniciar Sesión / Perfil ORCID | `navbar.user_profile` | Despliega modal de login ORCID o menú de usuario autenticado. | [x] |
| 10 | `navbar_sidebar_collapse` | Button (Icon) | ☰ Toggle de Barra Lateral | `navbar.toggle_sidebar` | Expande o colapsa el menú lateral en pantallas de escritorio y móviles. | [x] |
| 11 | `navbar_dossier_trigger` | Button (Accent) | 📄 Generador de Reporte Rápido | `navbar.quick_dossier` | Dispara el drawer de reporte sin abandonar la vista actual. | [x] |
| 12 | `navbar_status_indicator` | Status Dot / Badge | Estado de Servicios (CH, Neo4j, LLM) | `navbar.system_status` | Indicador verde pulsante si la API está respondiendo con normalidad. | [x] |

---

## 2. Textos Multilingües Clave Requeridos (i18n)

```javascript
// Claves a incluir en es.js, pt.js, en.js
suite: {
  brand_title: "Ecosistema TlachIA",
  app_infotlachia: "SNII Info TlachIA",
  app_infotlachia_desc: "Inteligencia Científica Institucional, Investigadores y Padrón SNII",
  app_revistaslatam: "Revistas LATAM",
  app_revistaslatam_desc: "Catálogo y Evaluación Editorial de Revistas Iberoamericanas",
  app_knomap: "KnoMap",
  app_knomap_desc: "Cartografía Topológica y Redes Neuronales Kohonen (SOM)",
  app_metrics: "TlachIA Metrics",
  app_metrics_desc: "Conformador de Corpus y Motor de 48 Indicadores Analíticos"
},
navbar: {
  search_placeholder: "Buscar investigadores, instituciones o dependencias (Presiona /)",
  language_select: "Idioma",
  theme_select: "Tema",
  user_profile: "Mi Perfil",
  quick_dossier: "Reporte 1-Clic"
}
```
