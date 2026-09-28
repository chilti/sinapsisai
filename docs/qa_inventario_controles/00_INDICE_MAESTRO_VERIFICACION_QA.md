# Índice Maestro de Verificación QA (1-a-1) de Controles de Interfaz
**Plataforma:** SNII Info TlachIA / SinapsisAI  
**Objetivo:** Matriz de auditoría para garantizar paridad del 100% en controles, botones, filtros y visualizadores durante la migración de Streamlit hacia FastAPI + React 19 / Vite.  
**Soporte Multilingüe Requerido:** 🇲🇽 Español (ES) &bull; 🇧🇷 Português (PT) &bull; 🇺🇸 English (EN).  
**Fecha:** 28 de Septiembre de 2026  

---

## 1. Resumen Ejecutivo del Inventario

Para evitar cualquier pérdida de funcionalidad o regresión en la experiencia de usuario, cada control existente en el código de Streamlit ha sido catalogado con su identificador, tipo de elemento, comportamiento esperado y estado de paridad en la nueva arquitectura.

| Módulo Funcional | Archivo Auxiliar de Detalle | Total de Controles | Estado QA |
| :--- | :--- | :---: | :---: |
| **00. Franja del Ecosistema, Navbar & i18n** | [`MODULO_07_FRANJA_ECOSISTEMA_Y_NAVBAR.md`](./MODULO_07_FRANJA_ECOSISTEMA_Y_NAVBAR.md) | 12 | ⏳ Pendiente |
| **01. Panorama Institucional** | [`MODULO_01_PANORAMA_INSTITUCIONAL.md`](./MODULO_01_PANORAMA_INSTITUCIONAL.md) | 18 | ⏳ Pendiente |
| **02. Perfiles de Investigadores** | [`MODULO_02_PERFILES_INVESTIGADORES.md`](./MODULO_02_PERFILES_INVESTIGADORES.md) | 22 | ⏳ Pendiente |
| **03. Mapas de la Ciencia (WebGL)** | [`MODULO_03_MAPAS_CIENCIA.md`](./MODULO_03_MAPAS_CIENCIA.md) | 14 | ⏳ Pendiente |
| **04. Mi Espacio del Investigador** | [`MODULO_04_MI_ESPACIO_INVESTIGADOR.md`](./MODULO_04_MI_ESPACIO_INVESTIGADOR.md) | 26 | ⏳ Pendiente |
| **05. Administración y Gobernanza** | [`MODULO_05_ADMINISTRACION_GOBERNANZA.md`](./MODULO_05_ADMINISTRACION_GOBERNANZA.md) | 29 | ⏳ Pendiente |
| **06. Asistente Científico IA** | [`MODULO_06_ASISTENTE_IA.md`](./MODULO_06_ASISTENTE_IA.md) | 11 | ⏳ Pendiente |
| **TOTAL ECOSISTEMA** | **7 Módulos de Verificación** | **132 Controles** | **0 / 132 (0%)** |

---

## 2. Requerimiento Transversal: Soporte Multilingüe (i18n)

Todos los módulos deben implementar la arquitectura trilingüe probada en Revistas LATAM (`src/i18n/index.js`), con diccionarios completos en:
- `frontend/src/i18n/es.js` (Español - Idioma base de referencia)
- `frontend/src/i18n/pt.js` (Português - Traducción completa de etiquetas cienciométricas)
- `frontend/src/i18n/en.js` (English - Estándar internacional)

### Criterios de Aceptación para i18n en cada Control:
1. **Etiquetas e Placeholders:** Todos los `label`, `placeholder`, `aria-label` y `help` deben consumirse vía `t('modulo.control_key')`.
2. **Tooltips y Badges:** Cuartiles (Q1-Q4), tipos de acceso abierto (Gold, Green, Hybrid, Diamond, Closed) y roles de autoría traducidos con glosario uniforme.
3. **Persistencia de Preferencia:** El idioma seleccionado se preserva en `localStorage` y en el Zustand store (`useAppStore`).
4. **Interpolación de Variables:** Soporte para parámetros dinámicos (ej: `t('researcher.works_count', { count: total })`).

---

## 3. Protocolo de Verificación Post-Implementación

Para cada control implementado en React:
1. Validar que la llamada a la API (`api/routers/...`) devuelve los datos equivalentes a la consulta original en Streamlit.
2. Comprobar reactividad inmediata (sin recargas de página completas).
3. Verificar el cambio dinámico entre los 3 idiomas (ES, PT, EN) sin romper el layout ni truncar textos.
4. Probar en los 3 temas (Claro, Oscuro, Navy).
5. Marcar la casilla `[x]` en el archivo auxiliar correspondiente y registrar la fecha de validación.
