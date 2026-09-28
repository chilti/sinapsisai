# Inventario de Controles: Módulo 6 - Asistente Científico IA
**Archivo Origen (Streamlit):** `dashboard_v2.py` (Líneas 2010–2250, 2750–2882) y `agent/orchestrator.py`  
**Archivo Destino (React):** `frontend/src/pages/AssistantPage.jsx`  
**Soporte Multilingüe:** 🇲🇽 ES &bull; 🇧🇷 PT &bull; 🇺🇸 EN  

---

## 1. Inventario Detallado de Controles

| # | ID de Control en Streamlit | Tipo de Control | Etiqueta / Propósito Original | Clave i18n Propuesta | Comportamiento Esperado en React | Estado QA |
| :-: | :--- | :--- | :--- | :--- | :--- | :-: |
| 1 | `select_llm_model` | Selectbox | Modelo LLM (LM Studio / API) | `assistant.select_model` | Selección del motor (local GPU vs modelos en la nube). | [x] |
| 2 | `radio_assistant_mode` | Radio / Segmented | Modo: Consulta Directa vs Agente Swarm | `assistant.mode_selection` | Conmuta entre respuesta inmediata y razonamiento multi-paso. | [x] |
| 3 | `multiselect_agent_skills` | Multi-select / Chips | Habilidades Activas (ClickHouse, Neo4j, SNII) | `assistant.skills_filter` | Activa o desactiva herramientas cienciométricas para el agente. | [x] |
| 4 | `input_chat_message` | Chat Input / Textarea | Escribe tu pregunta sobre la ciencia... | `assistant.input_placeholder` | Campo expandible con soporte de atajos (`Enter` para enviar, `Shift+Enter` nueva línea). | [x] |
| 5 | `btn_send_message` | Button | Enviar Consulta | `assistant.btn_send` | Inicia streaming SSE (`text/event-stream`) de tokens en tiempo real. | [x] |
| 6 | `btn_clear_conversation` | Button | 🗑️ Limpiar Conversación | `assistant.btn_clear` | Reinicia la memoria de contexto de la sesión activa. | [x] |
| 7 | `display_streaming_response` | Live Markdown Stream | Flujo Continuo de Respuesta | `assistant.streaming_container` | Renderizado token a token con resaltado de sintaxis y tablas. | [x] |
| 8 | `accordion_agent_thoughts` | Expander / Collapsible | Pasos de Razonamiento (CoT & Tools) | `assistant.thinking_process` | Muestra qué consultas SQL/Cypher ejecutó el agente y sus resultados. | [x] |
| 9 | `btn_copy_response` | Button (Icon) | Copiar al Portapapeles | `assistant.btn_copy` | Copia la respuesta completa en formato Markdown con feedback visual. | [x] |
| 10 | `btn_retry_last_query` | Button (Icon) | Regenerar Respuesta | `assistant.btn_regenerate` | Vuelve a solicitar la respuesta con variabilidad estocástica. | [x] |
| 11 | `btn_export_chat_history` | Download Button | Exportar Conversación (.md) | `assistant.btn_export_chat` | Descarga la bitácora completa de la sesión para referencia académica. | [x] |

---

## 2. Textos Multilingües Clave Requeridos (i18n)

```javascript
// Claves a incluir en es.js, pt.js, en.js
assistant: {
  title: "Asistente de Inteligencia Científica",
  input_placeholder: "Pregunta sobre producción científica, redes de coautoría, citas o el padrón SNII...",
  btn_send: "Enviar",
  btn_clear: "Nueva Conversación",
  btn_copy: "Copiar",
  btn_regenerate: "Regenerar respuesta",
  thinking_process: "Proceso de razonamiento y herramientas ejecutadas",
  modes: {
    direct: "Chat Cienciométrico",
    agent: "Agente Autónomo Híbrido"
  }
}
```
