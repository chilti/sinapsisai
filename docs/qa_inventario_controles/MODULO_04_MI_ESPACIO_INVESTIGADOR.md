# Inventario de Controles: Módulo 4 - Mi Espacio del Investigador
**Archivo Origen (Streamlit):** `components/researcher_space.py` y `dashboard_v2.py` (Líneas 924–1220)  
**Archivo Destino (React):** `frontend/src/pages/ResearcherSpacePage.jsx`, `frontend/src/components/DossierDrawer.jsx` y `frontend/src/components/OrcidLoginModal.jsx`  
**Soporte Multilingüe:** 🇲🇽 ES &bull; 🇧🇷 PT &bull; 🇺🇸 EN  

---

## 1. Inventario Detallado de Controles

| # | ID de Control en Streamlit | Tipo de Control | Etiqueta / Propósito Original | Clave i18n Propuesta | Comportamiento Esperado en React | Estado QA |
| :-: | :--- | :--- | :--- | :--- | :--- | :-: |
| 1 | `btn_orcid_oauth_login` | Button | 🔐 Iniciar Sesión con ORCID | `user_space.btn_orcid_login` | Dispara el flujo OAuth de ORCID en modal o redirección limpia. | [ ] |
| 2 | `btn_user_logout` | Button | 🚪 Cerrar Sesión | `user_space.btn_logout` | Cierra la sesión en Zustand y limpia el token de `localStorage`. | [ ] |
| 3 | `radio_claim_match` | Radio Button | Confirmación de identidad en Padrón | `user_space.radio_identity_match` | Opciones "Sí, soy yo" o "Buscar mi nombre". | [ ] |
| 4 | `input_search_me_padron` | Text Input | Buscar mi nombre en el padrón | `user_space.search_padron_placeholder` | Búsqueda predictiva si el match automático falló. | [ ] |
| 5 | `btn_claim_me_confirm` | Button | Este soy yo (Vincular perfil) | `user_space.btn_confirm_profile` | Asocia el ORCID autenticado con el nodo `:Person` en Neo4j. | [ ] |
| 6 | `form_register_profile` | Form Submit | Registrar y Sincronizar mi Perfil | `user_space.form_register_submit` | Registra el perfil inicial con nombre y área de conocimiento. | [ ] |
| 7 | `subtab_nav_space` | Tabs Navigation | Pestañas de Mi Espacio (1 al 5) | `user_space.subtabs_nav` | Pestañas superiores fluidas: Resumen, Acreditación, Citas, Reporte, Curación. | [ ] |
| 8 | `btn_view_my_metrics_dash` | Button | 📊 Ver mi Producción en Dashboard | `user_space.btn_view_in_dashboard` | Navega instantáneamente al Perfil en Dashboard sin recarga. | [ ] |
| 9 | `btn_sync_production_bg` | Button | 🔄 Sincronizar Producción (Background) | `user_space.btn_sync_apis` | Inicia cosecha asíncrona de obras desde OpenAlex/Scopus/ORCID. | [ ] |
| 10 | `badge_identity_status` | UI Badge | Identidad Digital Verificada con ORCID | `user_space.badge_verified_orcid` | Distintivo visual con palomita verde y fecha de verificación. | [ ] |
| 11 | `breadcrumbs_accreditation` | Display UI | Jerarquía Institucional de Adscripción | `user_space.accreditation_hierarchy` | Muestra la ruta completa (UNAM ➔ Dependencia ➔ Subdependencia). | [ ] |
| 12 | `input_target_entity_locked` | Text Input (Disabled) | 🔒 Entidad / Dependencia a administrar | `user_space.input_locked_entity` | **Bloqueado estrictamente** al nivel jerárquico más específico. | [ ] |
| 13 | `input_inst_email` | Text Input | Correo electrónico institucional | `user_space.input_institutional_email` | Validación de formato `@unam.mx` o institucional. | [ ] |
| 14 | `input_inst_position` | Text Input | Puesto o Cargo Oficial | `user_space.input_position` | Campo para registrar función en la biblioteca o coordinación. | [ ] |
| 15 | `textarea_accreditation_notes` | Text Area | Justificación o notas adicionales | `user_space.input_justification` | Comentarios dirigidos al superadministrador del sistema. | [ ] |
| 16 | `submit_accreditation_request` | Form Submit Button | Enviar Solicitud de Acreditación | `user_space.btn_submit_accreditation` | Guarda la solicitud en SQLite `curation_hub.db` en estado `pending`. | [ ] |
| 17 | `kpi_space_net_citations` | KPI Metric Card | Citas Netas (Sin Autocitas) | `user_space.kpi_net_citations` | Métrica central calculada con OpenAlex Author IDs. | [ ] |
| 18 | `kpi_space_self_cite_rate` | KPI Metric Card | % Autocitas Directas | `user_space.kpi_self_rate` | Porcentaje de citas donde el autor figura en la obra citante. | [ ] |
| 19 | `table_space_citing_works` | Data Table | Artículos Citantes del Investigador | `user_space.table_citing_works` | Listado paginado con DOIs y filtro de autocitas. | [ ] |
| 20 | `dossier_period_select` | Selectbox / Slider | Periodo a Evaluar para el Dossier | `user_space.dossier_period` | Rango de años para la convocatoria SNII o evaluación docente. | [ ] |
| 21 | `dossier_preview_panel` | Rich Display / Preview | Vista Previa de Trayectoria Académica | `user_space.dossier_preview` | Previsualización formal con tablas de cuartiles y liderazgo. | [ ] |
| 22 | `btn_download_dossier_pdf` | Download Button | 📄 Descargar Reporte en PDF | `user_space.btn_download_pdf` | Genera y descarga el PDF formal ("Reporte_Trayectoria_{Nombre}.pdf"). | [ ] |
| 23 | `btn_download_dossier_md` | Download Button | 📝 Descargar Reporte en Markdown | `user_space.btn_download_md` | Descarga el documento `.md` estructurado y listo para edición. | [ ] |
| 24 | `filter_claim_works` | Text Input | Filtrar obras por título o año | `user_space.filter_claim_placeholder` | Búsqueda rápida sobre las obras asociadas al usuario. | [ ] |
| 25 | `btn_disclaim_work` | Button | ❌ No es mía (Desvincular obra) | `user_space.btn_disclaim_work` | Mueve el artículo a la lista de exclusión en SQLite. | [ ] |
| 26 | `btn_restore_work` | Button | ↩️ Reclamar (Restaurar obra) | `user_space.btn_restore_work` | Restaura una obra previamente excluida hacia el perfil activo. | [ ] |

---

## 2. Textos Multilingües Clave Requeridos (i18n)

```javascript
// Claves a incluir en es.js, pt.js, en.js
user_space: {
  title: "Mi Espacio",
  btn_orcid_login: "Iniciar Sesión con ORCID",
  btn_logout: "Cerrar Sesión",
  btn_view_in_dashboard: "Ver mi Producción en el Dashboard",
  btn_submit_accreditation: "Enviar Solicitud de Acreditación",
  locked_entity_caption: "Por políticas de gobernanza, la acreditación solo puede solicitarse para tu entidad de adscripción directa.",
  btn_download_pdf: "Descargar Reporte en PDF",
  btn_download_md: "Descargar Reporte en Markdown (.md)",
  btn_disclaim_work: "No es mía",
  btn_restore_work: "Restaurar obra",
  subtabs: {
    identity: "Resumen de Identidad",
    accreditation: "Acreditación Institucional",
    citations: "Citas & Autocitas",
    dossier: "Generador de Reporte",
    curation: "Curación de Publicaciones"
  }
}
```
