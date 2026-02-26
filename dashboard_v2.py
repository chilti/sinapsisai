import streamlit as st
import asyncio
import concurrent.futures
import os
import sys
import random
import threading
from PIL import Image
from dotenv import load_dotenv

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from agent.orchestrator import RAGOrchestrator
from dashboard_analytics import render_institucion_view, render_investigador_view, load_cached_data

load_dotenv()

# ---- Configuración de página ----
st.set_page_config(
    page_title="Bitácora: Ecosistema de Ciencia e Investigación",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- CSS ----
st.markdown("""
    <style>
    .stApp { background-color: #f4f4f5; color: #1e293b; }
    .stChatMessage {
        background-color: #ffffff;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        margin-bottom: 8px;
    }
    section[data-testid="stSidebar"] {
        background-color: #002B5C;
        border-right: 1px solid #001a38;
    }
    section[data-testid="stSidebar"] * {
        color: #f1f5f9 !important;
    }
    h1, h2, h3 { color: #002B5C !important; font-family: 'Inter', sans-serif; font-weight: 600; }
    .footer {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: #002B5C; color: #D4AF37;
        text-align: center; padding: 5px; font-size: 11px;
        border-top: 1px solid #D4AF37;
    }
    .stButton>button {
        background-color: #D4AF37; color: #002B5C;
        border: 1px solid #b6932b;
        border-radius: 6px; padding: 0.5rem 1rem; font-weight: 600;
    }
    .stButton>button:hover {
        background-color: #b6932b;
        border-color: #8c7121;
        color: #002B5C;
    }
    </style>
""", unsafe_allow_html=True)


# ---- Motor Async: hilo dedicado con su propio event loop ----
# Solución definitiva para la incompatibilidad de anyio con Streamlit:
# Todas las operaciones async corren en un hilo dedicado con un loop propio.
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

def _run_async_in_thread(coro):
    """Ejecuta una corrutina en un hilo dedicado con su propio event loop."""
    def _worker():
        return asyncio.run(coro)
    future = _executor.submit(_worker)
    return future.result()


# ---- Inicialización del Orquestador ----
if "orchestrator" not in st.session_state:
    with st.spinner("Inicializando el Cerebro del Sistema..."):
        try:
            # El orquestador se crea en el hilo principal (es síncrono)
            # Solo el método .ask() es async y se ejecuta en el hilo dedicado
            st.session_state.orchestrator = RAGOrchestrator(tools_list=[])
            st.session_state.session_id = f"st-{random.randint(1000, 9999)}"
        except Exception as e:
            st.error(f"Error inicializando el orquestador: {e}")
            import traceback
            st.code(traceback.format_exc())
            st.stop()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


# ---- Sidebar ----
with st.sidebar:
    st.markdown("""
    <style>
    [data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background-color: rgba(28, 131, 225, 0.1) !important;
    }
    [data-testid="stSidebar"] div[data-baseweb="select"] * {
        color: black !important;
    }
    [data-testid="stSidebar"] [data-testid="stSelectbox"] div[role="button"] {
        background-color: rgba(28, 131, 225, 0.1) !important;
        color: black !important;
    }
    [data-testid="stSidebar"] [data-testid="stSelectbox"] div[role="button"] * {
        color: black !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.title("🔬 Sinapsis AI")
    st.markdown("---")
    st.subheader("Estado del Sistema")
    st.success("✅ Orquestador: Activo")
    st.info(f"ID Sesión: {st.session_state.session_id}")

    st.markdown("---")
    st.subheader("Configuración")
    
    # Extraer entidades direcamente desde Neo4j (grafo local)
    try:
        from database.knowledge_graph import Neo4jGraphStore
        store = Neo4jGraphStore()
        with store.driver.session() as session:
            result = session.run("MATCH (e:Entity) RETURN DISTINCT e.name AS name")
            entidades_neo4j = [record["name"] for record in result]
        store.close()
    except Exception as e:
        entidades_neo4j = []

    if entidades_neo4j:
        entidades_disponibles = sorted(entidades_neo4j)
    else:
        # Fallback a data cache o de prueba
        df_institucion = load_cached_data("institucion_total.parquet")
        if df_institucion is not None and not df_institucion.empty:
            entidades_disponibles = sorted(df_institucion['entity_name'].unique())
        else:
            entidades_disponibles = ["Facultad de Ciencias", "Centro de Ciencias de la Complejidad", "UNAM Global"]
            
    selected_entity = st.selectbox("Entidad UNAM", entidades_disponibles)
    
    st.selectbox("Modelo", ["openai/gpt-oss-20b", "mistral-7b", "llama-3"], index=0)


    st.markdown("---")
    st.markdown("### Capas de Datos Activas")
    st.markdown("- ✅ **Neo4j** (Grafos Local)")
    st.markdown("- ✅ **Qdrant** (Semántica Local)")    
    st.markdown("- ✅ **OpenAlex** (Global)")
    st.markdown("- ✅ **OpenInterpreter** (Código)")
    #st.markdown("- ✅ **Sci-Hub** (Descargas)")


# ---- Interfaz Principal ----
st.title("Sinapsis AI: Hub de Ciencia Abierta")
st.markdown("Inteligencia Bibliométrica Híbrida")

tab_inst, tab_inv, tab_chat, tab_about = st.tabs(["🏢 Panorama Institucional", "👤 Perfil Académico", "🤖 Asistente", "ℹ️ Acerca de..."])

# =======================================================
# TAB 1: Chat RAG Orquestador
# =======================================================
with tab_chat:
    col_clear, _ = st.columns([1, 4])
    with col_clear:
        if st.button("🗑️ Limpiar Conversación"):
            st.session_state.chat_history = []
            st.session_state.orchestrator.clear_session(st.session_state.session_id)
            st.rerun()

    chat_container = st.container()

    with chat_container:
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message.get("image"):
                    st.image(message["image"])

    # ---- Input del usuario ----
    if prompt := st.chat_input("Escribe tu consulta científica aquí..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(prompt)

        with chat_container:
            with st.chat_message("assistant"):
                placeholder = st.empty()
                placeholder.markdown("🔍 *Consultando fuentes y analizando datos...*")

                response = ""
                try:
                    # Capturamos session_id y orchestrator antes de entrar al hilo
                    session_id = st.session_state.session_id
                    orchestrator = st.session_state.orchestrator

                    async def ask_agent():
                        return await orchestrator.ask(session_id, prompt, entity_context=selected_entity)

                    response = _run_async_in_thread(ask_agent())
                    placeholder.markdown(response)

                except Exception as e:
                    import traceback
                    err = traceback.format_exc()
                    print(err)
                    placeholder.error(f"Error en orquestación: {e}")
                    response = f"Error: {e}"

                # Detectar imagen generada por el intérprete
                img_data = None
                if os.path.exists("interpreter_output.png"):
                    with open("interpreter_output.png", "rb") as f:
                        img_data = f.read()
                    st.image(img_data)
                    os.remove("interpreter_output.png")

                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": response,
                    "image": img_data
                })

                # Inyectar JS para auto-scroll
                import streamlit.components.v1 as components
                components.html(
                    """
                    <script>
                        var body = window.parent.document.querySelector(".main");
                        body.scrollTop = body.scrollHeight;
                    </script>
                    """,
                    height=0,
                )

# =======================================================
# TAB 2: Vista de la Institución
# =======================================================
with tab_inst:
    render_institucion_view(selected_entity)

# =======================================================
# TAB 3: Vista por Investigador
# =======================================================
with tab_inv:
    render_investigador_view(selected_entity)

# =======================================================
# TAB 4: Acerca de...
# =======================================================
with tab_about:
    st.header("Arquitectura del Sistema Híbrido")
    st.markdown("Este diagrama describe el flujo de datos global de **Sinapsis AI**, desde la recolección de metadatos hasta la Inteligencia Híbrida del Agente RAG.")
    
    mermaid_code = """
    graph TD
        %% Ingestion Layer
        subgraph Data Ingestion
            A[SIIA / Local DB] --> B(Ingesta Inicial)
            B --> C{APIs Globales}
            C --> D[OpenAlex]
            C --> E[Scopus]
            C --> F[ORCID]
        end

        %% Database Layer
        subgraph Hybrid Knowledge Base
            D -->|Metadata & Abstract| G[(Neo4j: Knowledge Graph)]
            E -->|Citations| G
            F -->|Authored DOIs| G
            
            G -.-> |Vectorize texts| H[(Qdrant: Vector DB)]
            
            subgraph Graph Nodes
              G1((Academic)) -.- G
              G2((Entity)) -.- G
              G3((APIPaper)) -.- G
              G4((Topic)) -.- G
              G5((SDG)) -.- G
            end
        end

        %% Pre-computation Layer
        subgraph Analytical Caching
            G -->|ETL offline| I[Archivos Parquet]
            I -->|papers_profesor| J[Local Cache]
            I -->|institucion_annual| J
        end

        %% App Layer
        subgraph Streamlit Interface
            J --> K[Dashboard de Analítica]
            K --> L{Vistas}
            L --> M[Perfil Institucional]
            L --> N[Perfil Académico]
            
            H <--> O[Orquestador RAG]
            G <--> O
        end

        %% Agent Tools
        subgraph Local AI Agent
            O --> P(Local LLM)
            O -.-> Q[Cypher Tool]
            O -.-> R[Semantic Search Tool]
            O -.-> S[Open Interpreter <br/> Code execution]
        end
    """
    
    # Renderizamos Mermaid JS usando inyección segura de componentes de Streamlit
    import streamlit.components.v1 as components
    html_mermaid = f"""
    <div class="mermaid">
    {mermaid_code}
    </div>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
    """
    components.html(html_mermaid, height=950, scrolling=True)

    st.markdown("---")
    st.header("Pipeline Secuencial de Ingesta de Datos")
    st.markdown("El proceso de extracción, enriquecimiento y vectorización ocurre en las siguientes fases *offline* antes de ser expuesto al Dashboard:")
    
    mermaid_ingestion = """
    graph TD
        A([1. Web Scraping / Archivo Local]) -->|siia_scraper.py| B[Lista Base de Académicos JSON]
        B -->|ingest_apis.py| C{Enriquecimiento Global APIs}
        C -->|Fetch| D[OpenAlex]
        C -->|Fetch| E[ORCID / Scopus]
        D --> F[(Neo4j: Nodos Academic / APIPaper)]
        E --> F
        
        F -->|extract_topics.py| G["Extracción Temática <br/> Nodos Topic"]
        F -->|"ingest_sdg.py <br/> Local LLM"| H["Clasificación ODS <br/> Nodos SDG"]
        
        G --> I[(Neo4j: Grafo de Conocimiento)]
        H --> I
        
        I -->|compute_scholar_metrics.py| J{Motor de Cómputo Analítico}
        J --> K[Métricas Institucionales]
        J --> L[Métricas por Investigador]
        K --> M[(Dataframe en Caché Parquet)]
        L --> M
    """

    html_mermaid_ingestion = f"""
    <div class="mermaid">
    {mermaid_ingestion}
    </div>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
    """
    components.html(html_mermaid_ingestion, height=850, scrolling=True)


# ---- Footer ----
st.markdown("""
    <div class="footer">
        📊 Sinapsis AI - UNAM
    </div>
""", unsafe_allow_html=True)
