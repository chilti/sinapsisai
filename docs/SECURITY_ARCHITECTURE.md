# 🛡️ Arquitectura de Seguridad y Protección Anti-Saturación (LLM & UI)

Este documento detalla las medidas de seguridad y protección por capas implementadas en **SNII Info TlachIA** para resguardar el servidor de modelos de lenguaje (LM Studio), los agentes de inteligencia artificial y los componentes interactivos de la interfaz gráfica contra ataques de denegación de servicio (DoS), saturación de VRAM/GPU, peticiones masivas y clics repetitivos en la interfaz.

---

## 📐 Estrategia de Defensa por Capas

```
+-----------------------------------------------------------------------+
|  Capa 1: Rate Limiting en Nginx (Límite por IP en Servidor Web)        |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|  Capa 2: Cooldown & Debouncing en UI (Streamlit - 3 segundos)         |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|  Capa 3: Caché Inteligente de Respuestas (MD5 Hash - 30 min TTL)       |
+-----------------------------------------------------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|  Capa 4: Timeouts de 60s, Sanitización & Límites de Tokens (Python)   |
+-----------------------------------------------------------------------+
```

---

## 1. Capa 1: Rate Limiting en Nginx (*Reverse Proxy*)

Para prevenir ataques automatizados de bots, ataques de fuerza bruta y saturación del ancho de banda:

- **Configuración de Zona de Memoria**: Registra la dirección IP remota del cliente (`$binary_remote_addr`).
- **Límite de Tasa**: Restringe las peticiones hacia la ruta `/v1/` a un máximo razonable por minuto por IP.
- **Respuesta Automática**: Si un cliente o script intenta saturar la API, Nginx rechaza inmediatamente la petición devolviendo un código **`HTTP 429 Too Many Requests`** antes de que la petición consuma recursos en Python o en la GPU.

---

## 2. Capa 2: Cooldown y Debouncing en la Interfaz de Usuario (*Streamlit*)

Para evitar que los usuarios o scripts automatizados hagan clic masivo en los botones de foco (💡) o envíen spam en la ventana flotante del asistente:

### A. Botones de Explicación 💡 (`utils/ui_components.py`)
- **Cooldown de 3 segundos**: Cada vez que un usuario presiona el foco 💡 de una gráfica o tabla, se registra la marca de tiempo (`st.session_state.last_bulb_click_time`).
- **Prevención de Clics Repetitivos**: Si se vuelve a presionar el foco en menos de 3 segundos, la interfaz ignora la solicitud y muestra una notificación discreta:
  ```python
  st.toast("⏳ Por favor espera un momento antes de solicitar otro análisis.", icon="⚠️")
  ```

### B. Chat del Asistente Flotante (`dashboard_v2.py`)
- **Límite de Longitud**: Toda entrada de texto ingresada por el usuario en la caja de chat se recorta a un máximo de **1,000 caracteres**.
- **Debouncing de Mensajes**: Aplica un cooldown de 3 segundos entre mensajes del chat para evitar envíos automatizados por teclado.

---

## 3. Capa 3: Caché Inteligente de Respuestas (*Evitar Recalcular en GPU*)

Muchos usuarios consultan explicaciones de las mismas gráficas o indicadores populares.

- **Hash MD5 de Contexto**: En [`agent/orchestrator.py`](file:///home/sinapsisai/agent/orchestrator.py), la función `ask_lightweight_stream_sync` calcula una huella digital MD5 del texto de la pregunta junto con el contexto visual de la pantalla.
- **TTL de 30 Minutos (1,800 segundos)**: Si se solicita el análisis de una gráfica cuyos datos no han cambiado en los últimos 30 minutos, el sistema devuelve la respuesta directamente desde la memoria RAM.
- **Beneficio**: Reduce drásticamente el uso de la tarjeta de video (GPU) y garantiza respuestas instantáneas.

---

## 4. Capa 4: Timeouts, Sanitización y Límites de Contexto en Python

Para proteger la memoria de contexto del modelo de lenguaje y evitar que peticiones colgadas bloqueen los hilos del servidor:

### A. Timeout de Conexión HTTP (`lib/llm_utils.py`)
- **Timeout estándar de 60 segundos**: El cliente HTTP (`httpx`) de `lib/llm_utils.py` utiliza un timeout por defecto de **60 segundos**. Si la respuesta del LLM excede este tiempo, la conexión se cancela de forma segura para liberar recursos.
- **Soporte para Procesos Pesados**: El parámetro `timeout` es configurable dinámicamente para dar flexibilidad a la generación de reportes extensos o procesos batch nocturnos si se requiere.

### B. Sanitización y Truncado de Prompts (`LLMConfig.sanitize_input`)
- Todos los textos enviados por el usuario son filtrados mediante `LLMConfig.sanitize_input(text, max_chars=1500)`.
- Evita ataques de *Desbordamiento de Contexto* (Context Overflow Attacks) y limita los tokens procesados.

### C. Recorte de Tablas de Datos (`utils/ui_components.py`)
- Al presionar el foco 💡 en un DataFrame o tabla, solo se envían al LLM las primeras **30 filas** formateadas en formato CSV plano, evitando colapsar el modelo con tablas gigantescas de miles de registros.

---

## 📝 Resumen de Archivos Modificados

- **[`lib/llm_utils.py`](file:///home/sinapsisai/lib/llm_utils.py)**: Implementa `sanitize_input()` y establece el timeout predeterminado en `60` segundos.
- **[`utils/ui_components.py`](file:///home/sinapsisai/utils/ui_components.py)**: Añade el cooldown de 3s en `render_explain_button()` y limita las tablas a 30 filas.
- **[`agent/orchestrator.py`](file:///home/sinapsisai/agent/orchestrator.py)**: Añade la sanitización de entradas y la memoria de caché MD5 de 30 min (`_response_cache`).
- **[`dashboard_v2.py`](file:///home/sinapsisai/dashboard_v2.py)**: Implementa el recorte a 1,000 caracteres y debouncing en el chat modal del asistente.
