# Inventario de Controles: Módulo 5 - Administración y Gobernanza
**Archivo Origen (Streamlit):** `components/admin_accreditation.py` y `dashboard_v2.py` (Líneas 1260–1860)  
**Archivo Destino (React):** `frontend/src/pages/AdminPage.jsx`  
**Soporte Multilingüe:** 🇲🇽 ES &bull; 🇧🇷 PT &bull; 🇺🇸 EN  

---

## 1. Inventario Detallado de Controles

| # | ID de Control en Streamlit | Tipo de Control | Etiqueta / Propósito Original | Clave i18n Propuesta | Comportamiento Esperado en React | Estado QA |
| :-: | :--- | :--- | :--- | :--- | :--- | :-: |
| 1 | `tab_accreditations_pend` | Tab Navigation | Solicitudes Pendientes de Acreditación | `admin.tab_pending_requests` | Bandeja de entrada con badge numérico de solicitudes pendientes. | [ ] |
| 2 | `tab_accreditations_active` | Tab Navigation | Administradores Institucionales Activos | `admin.tab_active_admins` | Listado de usuarios con facultades delegadas por entidad. | [ ] |
| 3 | `tab_aliases_manager` | Tab Navigation | Gestión de Alias Institucionales | `admin.tab_aliases` | Catálogo de variantes léxicas y normalización de nombres. | [ ] |
| 4 | `tab_pipelines_ops` | Tab Navigation | Operaciones & Pipelines de Ingesta | `admin.tab_pipelines` | Centro de comando de tareas de sincronización y cómputo. | [ ] |
| 5 | `btn_approve_accreditation` | Button (Primary) | ✅ Aprobar como Administrador | `admin.btn_approve` | Modal de confirmación y asignación de rol en SQLite. | [ ] |
| 6 | `btn_reject_accreditation` | Button (Danger) | ❌ Rechazar Solicitud | `admin.btn_reject` | Permite ingresar un motivo de rechazo que se notifica al usuario. | [ ] |
| 7 | `table_active_admins` | Data Table | Tabla de Administradores Acreditados | `admin.table_active_admins` | Columnas: Nombre, ORCID, Entidad asignada, Email institucional, Acciones. | [ ] |
| 8 | `btn_revoke_admin_role` | Button | 🚫 Revocar Permisos | `admin.btn_revoke_role` | Revoca las facultades de administración para esa entidad. | [ ] |
| 9 | `input_canonical_name` | Text Input | Nombre Canónico Oficial | `admin.input_canonical_name` | Nombre maestro unificado de la entidad. | [ ] |
| 10 | `input_alias_variant` | Text Input | Alias o Variante Léxica | `admin.input_alias_variant` | Forma alternativa encontrada en firmas o bases externas. | [ ] |
| 11 | `btn_save_alias` | Form Submit Button | Guardar Alias Institucional | `admin.btn_save_alias` | Persiste el nuevo mapeo en la base de tesauros/curación. | [ ] |
| 12 | `table_registered_aliases` | Data Table | Lista de Alias Registrados | `admin.table_aliases` | Tabla con buscador, fecha de creación y botón de eliminar alias. | [ ] |
| 13 | `btn_stop_running_task` | Button (Danger) | 🛑 Detener / Cancelar Proceso | `admin.btn_cancel_task` | Envía señal SIGTERM/cancelación a la tarea en segundo plano. | [ ] |
| 14 | `btn_refresh_task_log` | Button | 🔄 Actualizar Bitácora | `admin.btn_refresh_log` | Streaming automático vía SSE/WebSockets de los logs del backend. | [ ] |
| 15 | `btn_clear_task_history` | Button | 🗑️ Limpiar Notificación / Historial | `admin.btn_clear_history` | Limpia los logs visuales de procesos terminados. | [ ] |
| 16 | `input_e2e_academic_filter` | Text Input | 🎯 Filtrar por Académico específico | `admin.input_e2e_academic` | Filtro opcional para pruebas unitarias de pipeline. | [ ] |
| 17 | `input_e2e_inst_filter` | Text Input | 🏛️ Institución padre requerida | `admin.input_e2e_institution` | Entidad marco para el cálculo de métricas. | [ ] |
| 18 | `check_e2e_local_llm` | Checkbox | ⚡ Usar recursos locales / LM Studio | `admin.check_local_llm` | Conmuta entre inferencia local GPU y API en la nube. | [ ] |
| 19 | `btn_run_e2e_pipeline` | Button (Primary) | 🚀 Ejecutar Pipeline Completo E2E | `admin.btn_run_pipeline_e2e` | Lanza orquestación completa con barra de progreso reactiva. | [ ] |
| 20 | `btn_ror_step1` | Button | 📦 2.1 Extraer Catálogo ROR | `admin.btn_ror_extract` | Extracción y deduplicación de RORs de México. | [ ] |
| 21 | `btn_ror_step2` | Button | 🎯 2.2 Resolver SNII a ROR | `admin.btn_ror_resolve` | Mapeo determinista y difuso de instituciones del padrón. | [ ] |
| 22 | `btn_ror_step3` | Button | 🔄 2.3 Sincronizar y Fusionar Neo4j | `admin.btn_ror_neo4j_sync` | Actualización de nodos institucionales en el Grafo de Conocimiento. | [ ] |
| 23 | `btn_run_missing_orcids` | Button | 🔍 Iniciar Barrido sin ORCID | `admin.btn_run_missing_orcids` | Ejecuta cascada de búsqueda para investigadores sin identificador. | [ ] |
| 24 | `check_sync_academics` | Checkbox | 👤 Sincronizar por Académicos | `admin.check_sync_academics` | Flag para el proceso de cosecha `sync_works.py`. | [ ] |
| 25 | `check_sync_ch` | Checkbox | 📊 Sincronizar con ClickHouse (`--ch`) | `admin.check_sync_clickhouse` | Habilita inserción directa en el cluster OLAP. | [ ] |
| 26 | `btn_run_harvest_works` | Button | 🌐 Iniciar Cosecha de Obras | `admin.btn_harvest_works` | Inicia cosecha masiva desde OpenAlex. | [ ] |
| 27 | `select_sync_phase_opt` | Selectbox | 📌 Fase a ejecutar en ClickHouse | `admin.select_sync_phase` | Opciones: All, Maps (tablas intermedias) o Works. | [ ] |
| 28 | `btn_run_ch_sync_analytics` | Button | 🗄️ Iniciar Sincronización CH | `admin.btn_run_ch_sync` | Materializa vistas analíticas en ClickHouse. | [ ] |
| 29 | `btn_run_compute_metrics` | Button | 📊 Iniciar Cómputo de Métricas | `admin.btn_compute_metrics` | Recalcula indicadores para perfiles institucionales e investigadores. | [ ] |

---

## 2. Textos Multilingües Clave Requeridos (i18n)

```javascript
// Claves a incluir en es.js, pt.js, en.js
admin: {
  title: "Panel de Administración y Gobernanza",
  tab_pending_requests: "Solicitudes Pendientes",
  tab_active_admins: "Administradores Activos",
  tab_aliases: "Gestión de Alias",
  tab_pipelines: "Operaciones y Mantenimiento",
  btn_approve: "Aprobar",
  btn_reject: "Rechazar",
  btn_save_alias: "Guardar Alias",
  btn_cancel_task: "Detener Proceso",
  btn_run_pipeline_e2e: "Ejecutar Pipeline E2E",
  status: {
    pending: "Pendiente",
    approved: "Aprobado",
    rejected: "Rechazado"
  }
}
```
