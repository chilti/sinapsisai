import streamlit as st
import streamlit.components.v1 as components

# --- Función para renderizar diagramas Mermaid usando componentes HTML ---
def mermaid_chart(code: str, height: int = 600):
    """
    Función para renderizar un diagrama de Mermaid en Streamlit usando un componente HTML.

    Args:
        code (str): Una cadena de texto con la sintaxis de Mermaid.
        height (int): La altura del componente HTML en píxeles.
    """
    components.html(
        f"""
        <div class="mermaid">
        {code}
        </div>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{ startOnLoad: true }});
        </script>
        """,
        height=height,
        scrolling=True,
    )


# --- Contenido de la Página ---

st.set_page_config(layout="wide", page_title="Arquitectura del RAG de Ciencias")

st.title("Visualización de la Arquitectura del Asistente RAG 🔬")
st.write(
    "Esta sección describe la arquitectura y el flujo de operación del asistente conversacional "
    "basado en el archivo `RAG_Ciencias.py`. Los siguientes diagramas ilustran los componentes clave, "
    "sus interacciones y cómo se comunican con los microservicios externos."
)

st.markdown("---")

# --- Diagrama 1: Arquitectura General ---

st.header("1. Diagrama de Arquitectura General")
st.write(
    "Este diagrama muestra los componentes principales del sistema y cómo se conectan entre sí. "
    "El flujo comienza con el usuario interactuando con la interfaz de Streamlit y termina con la "
    "respuesta generada por el agente, que es una combinación del poder del LLM y la información "
    "recuperada de fuentes de datos especializadas."
)
# --- CÓDIGO CORREGIDO ---
# Se separó la línea "E --> F & G" en dos líneas distintas para máxima compatibilidad.
arquitectura_general_code = """
graph TD
    subgraph "Usuario"
        A[Usuario Final]
    end

    subgraph "Frontend"
        B[Interfaz de Streamlit]
    end

    subgraph "Orquestador, LangChain/LangGraph"
        C{Agente ReAct}
        D[LLM, gpt-oss-20b]
        E[Herramientas, @tool]
    end

    subgraph "Capa de Microservicios, Backend"
        F[API de Búsqueda Vectorial]
        G[API de OpenAlex, Web y Wikipedia]
    end

    subgraph "Fuentes de Datos"
        H[(Base de Datos Vectorial - Milvus)]
        I[(APIs Externas)]
    end

    A -->|1. Ingresa pregunta| B
    B -->|2. Invoca al agente| C
    C -->|3. Piensa y decide herramienta| D
    D -->|4. Devuelve herramienta a usar| C
    C -->|5. Ejecuta la herramienta seleccionada| E
    E -->|6. Llama al microservicio apropiado| F
    E -->|6. Llama al microservicio apropiado| G
    F -->|7. Consulta datos| H
    G -->|8. Consulta datos| I
    H & I -->|9. Devuelven resultados| F & G
    F & G -->|10. Devuelven JSON a la herramienta| E
    E -->|11. Entrega resultado al agente| C
    C -->|12. Genera respuesta final con el LLM| D
    D -->|13. Devuelve respuesta final al Agente| C
    C -->|14. Envía respuesta a la interfaz| B
    B -->|15. Muestra respuesta| A
"""
# Aumentamos la altura para este diagrama más grande
mermaid_chart(arquitectura_general_code, height=750)


st.markdown("---")

# --- Diagrama 2: Diagrama de Secuencia ---

st.header("2. Diagrama de Secuencia de una Consulta")
st.write(
    "Este diagrama ilustra la secuencia de interacciones entre los componentes a lo largo del tiempo para "
    "responder a una sola pregunta del usuario. Muestra el 'diálogo' paso a paso entre la interfaz, el agente, "
    "las herramientas y el LLM."
)

diagrama_secuencia_code = """
sequenceDiagram
    participant User
    participant Streamlit_UI
    participant Agent_Executor
    participant Tool as Herramienta (e.g., buscar_articulos)
    participant Microservice
    participant LLM

    User->>+Streamlit_UI: Ingresa pregunta
    Streamlit_UI->>+Agent_Executor: invoke(pregunta)
    Agent_Executor->>+LLM: ¿Qué herramienta debo usar para esta pregunta?
    LLM-->>-Agent_Executor: Usa 'buscar_articulos' con el query 'X'
    Agent_Executor->>+Tool: Ejecutar('X')
    Tool->>+Microservice: POST /api/search/ (payload: {'query': 'X'})
    Microservice-->>-Tool: Devuelve resultados en JSON
    Tool-->>-Agent_Executor: Retorna resultados formateados como texto
    Agent_Executor->>+LLM: Con estos resultados, genera la respuesta final.
    LLM-->>-Agent_Executor: Respuesta final en lenguaje natural.
    Agent_Executor-->>-Streamlit_UI: Entrega respuesta final
    Streamlit_UI-->>-User: Muestra la respuesta en el chat
"""
mermaid_chart(diagrama_secuencia_code, height=550)


st.markdown("---")

# --- Diagrama 3: Flujo de Interacción con Microservicios ---

st.header("3. Diagrama de Flujo: Interacción con Microservicios (MCP)")
st.write(
    "Este diagrama detalla el proceso interno que ocurre cuando una herramienta es ejecutada por el agente. "
    "Se enfoca en cómo la herramienta actúa como un cliente HTTP para comunicarse con un microservicio, "
    "encapsulando la lógica de la llamada a la API y el manejo de la respuesta."
)

flujo_mcp_code = """
graph TD
    A[Agente decide usar una herramienta<br>e.g., buscar_articulos_por_autor] --> B{Se ejecuta la función de la herramienta<br>con los argumentos necesarios<br>e.g., author_name='J. Smith'};
    B --> C["La función construye la petición HTTP:<br>- URL del endpoint<br>- Payload (JSON con los argumentos)<br>- Headers"];
    C --> D{"Utiliza la librería `requests`<br>para enviar la petición al microservicio<br>requests.post(url, json=payload)"};
    D --> E("(Microservicio)");
    E --> F["El microservicio procesa la petición<br>(e.g., busca en la base de datos)"];
    F --> G[El microservicio retorna una respuesta<br>normalmente en formato JSON];
    G --> H{La función en Python recibe la respuesta};
    H --> I["Se parsea el JSON y se extrae<br>la información relevante (.json()['results'])"];
    I --> J{Se formatea la información<br>en una cadena de texto legible};
    J --> K[La función retorna la cadena de texto<br>al Agente ReAct];
  
"""
mermaid_chart(flujo_mcp_code, height=650)