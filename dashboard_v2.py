import streamlit as st
import asyncio
import concurrent.futures
import os
import sys
import random
import threading
from PIL import Image
import json
from dotenv import load_dotenv

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

import pandas as pd
import plotly.express as px
from database.knowledge_graph import Neo4jGraphStore
from database.vector_store import QdrantStore
from agent.orchestrator import RAGOrchestrator
from dashboard_analytics import render_institucion_view, render_investigador_view, load_cached_data

load_dotenv()

# ---- Configuración de página ----
st.set_page_config(
    page_title="Sinapsis AI: Hub de Ciencia Abierta",
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

@st.cache_data(ttl=30)
def fetch_database_live_stats():
    """Obtiene los conteos globales de forma cacheada para no saturar las DBs."""
    try:
        neo = Neo4jGraphStore()
        graph_stats = neo.get_database_statistics()
        graph_sample = neo.get_sample_graph(limit=80)
        neo.close()
    except Exception as e:
        graph_stats = {"error": str(e), "nodes": {}, "relationships": 0}
        graph_sample = {"error": str(e)}
        
    try:
        qdrant = QdrantStore(collection_name="api_papers")
        qdrant_stats = qdrant.get_collection_stats()
        qdrant_schema = qdrant.get_schema_info()
    except Exception as e:
        qdrant_stats = {"total_vectors": 0, "error": str(e)}
        qdrant_schema = {"error": str(e)}
        
    return graph_stats, qdrant_stats, graph_sample, qdrant_schema


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
    
    st.selectbox("Modelo", ["openai/gpt-oss-20b"], index=0)


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

tab_inst, tab_inv, tab_chat, tab_council, tab_about = st.tabs([
    "🏢 Panorama Institucional",
    "👤 Perfil Académico",
    "🤖 Asistente",
    "🏛️ Consejo Estratégico",
    "ℹ️ Acerca de..."
])

# =======================================================
# TAB: Consejo Estratégico Virtual (Multi-Agente AutoGen)
# =======================================================
with tab_council:
    st.header("🏛️ Consejo Estratégico Virtual")
    st.markdown(
        "Sistema multi-agente que orquesta un **Rector**, un **Investigador Senior** y un "
        "**Consejero Universitario** para diseñar y ejecutar estudios bibliométricos de forma autónoma."
    )

    # ── Inicialización del estado de sesión del Consejo ──
    if "council_phase" not in st.session_state:
        st.session_state.council_phase = "idle"   # idle | running | done
    if "council_log" not in st.session_state:
        st.session_state.council_log = []          # [(agente, texto), ...]
    if "council_script" not in st.session_state:
        st.session_state.council_script = None
    if "council_script_path" not in st.session_state:
        st.session_state.council_script_path = None
    if "council_report" not in st.session_state:
        st.session_state.council_report = None

    # ── Panel de control ───────────────────────────────
    col_mode, col_entity = st.columns([2, 2])

    with col_mode:
        mode = st.radio(
            "Modo",
            ["🆕 Nueva sesión", "♻️ Re-ejecutar script existente"],
            horizontal=True,
        )

    with col_entity:
        council_entity = st.selectbox(
            "Entidad objetivo",
            entidades_disponibles,
            key="council_entity_select",
        )

    # ── Configuración según modo ───────────────────────
    council_objective = ""
    selected_script_path = None

    if mode == "🆕 Nueva sesión":
        council_objective = st.text_area(
            "Objetivo del estudio",
            placeholder="Ej: Analiza las redes de colaboración y los temas emergentes del ICN entre 2019-2024...",
            height=100,
        )
    else:
        # Cargar scripts guardados
        try:
            from agent.council.technical_mesa import list_saved_scripts
            saved_scripts = list_saved_scripts()
        except Exception:
            saved_scripts = []

        if saved_scripts:
            script_options = {s["filename"]: s["path"] for s in saved_scripts}
            selected_script_name = st.selectbox("Script guardado", list(script_options.keys()))
            selected_script_path = script_options[selected_script_name]
            st.caption(f"📁 `{selected_script_path}`")
        else:
            st.warning("No hay scripts guardados aún. Ejecuta una Nueva sesión primero.")

    # ── Botón de inicio ────────────────────────────────
    can_run = (
        (mode == "🆕 Nueva sesión" and council_objective.strip()) or
        (mode == "♻️ Re-ejecutar script existente" and selected_script_path)
    )

    if st.button("▶ Iniciar", disabled=not can_run, type="primary"):
        st.session_state.council_phase = "running"
        st.session_state.council_log = []
        st.session_state.council_script = None
        st.session_state.council_report = None
        st.rerun()

    # ── Ejecución ──────────────────────────────────────
    if st.session_state.council_phase == "running":
        try:
            from agent.council.strategic_council import run_strategic_council
            from agent.council.technical_mesa import run_technical_mesa, load_execution_script
            from agent.council.autonomous_executor import run_autonomous_executor

            log_container = st.container()

            def _on_message(agent_name: str, content: str):
                if content and content.strip():
                    st.session_state.council_log.append((agent_name, content))

            # ── Fase 1: Solo para nueva sesión ──
            consensus_plan = ""
            if mode == "🆕 Nueva sesión":
                with st.status("🎓 Fase 1: Deliberación del Consejo Estratégico...", expanded=True):
                    consensus_plan, plan_path = _run_async_in_thread(
                        asyncio.coroutine(lambda: run_strategic_council(
                            entity=council_entity,
                            objective=council_objective,
                            on_message=_on_message,
                        ))()
                    ) if False else run_strategic_council(
                        entity=council_entity,
                        objective=council_objective,
                        on_message=_on_message,
                    )
                    st.success(f"✅ Plan aprobado · guardado en `{plan_path.name}`")

            # ── Fase 2: Solo para nueva sesión ──
            execution_script = ""
            if mode == "🆕 Nueva sesión":
                with st.status("🏗️ Fase 2: Mesa Técnica...", expanded=True):
                    execution_script, script_path = run_technical_mesa(
                        entity=council_entity,
                        consensus_plan=consensus_plan,
                        on_message=_on_message,
                    )
                    st.session_state.council_script = execution_script
                    st.session_state.council_script_path = str(script_path)
                    st.success(f"💾 Script guardado: `{script_path.name}`")
            else:
                # Cargar script existente
                execution_script = load_execution_script(selected_script_path)
                st.session_state.council_script = execution_script

            # ── Fase 3: Ejecución autónoma ──
            with st.status("⚙️ Fase 3: Ejecución autónoma...", expanded=True):
                report_text, report_path = run_autonomous_executor(
                    entity=council_entity,
                    execution_script=execution_script,
                    on_message=_on_message,
                )
                st.session_state.council_report = report_text
                st.session_state.council_phase = "done"
                st.success(f"📊 Informe generado: `{report_path.name}`")
                st.rerun()

        except ImportError as e:
            st.error(f"❌ AutoGen no está instalado. Ejecuta: `pip install pyautogen`\n\n{e}")
            st.session_state.council_phase = "idle"
        except Exception as e:
            st.error(f"❌ Error durante la ejecución: {e}")
            import traceback
            st.code(traceback.format_exc())
            st.session_state.council_phase = "idle"

    # ── Log de la conversación ─────────────────────────
    if st.session_state.council_log:
        st.markdown("---")
        st.subheader("🗣️ Transcripción del Consejo")

        AGENT_ICONS = {
            "Rector": "🎓",
            "Investigador_Senior": "🔬",
            "Consejero_Universitario": "📋",
            "Arquitecto_de_Datos": "🏗️",
            "SINAPSIS_Técnico": "🤖",
            "SINAPSIS_Ejecutor": "⚙️",
            "Corrector_Python": "🐍",
            "Sistema": "💡",
        }

        for agent_name, content in st.session_state.council_log:
            icon = AGENT_ICONS.get(agent_name, "💬")
            with st.expander(f"{icon} **{agent_name}**", expanded=False):
                st.markdown(content)

    # ── Informe final ──────────────────────────────────
    if st.session_state.council_phase == "done" and st.session_state.council_report:
        st.markdown("---")
        st.subheader("📊 Informe Bibliométrico Final")
        st.markdown(st.session_state.council_report)

        col_dl, col_reset = st.columns([2, 1])
        with col_dl:
            st.download_button(
                label="📥 Descargar Informe (Markdown)",
                data=st.session_state.council_report.encode("utf-8"),
                file_name=f"informe_{council_entity.lower().replace(' ', '_')}.md",
                mime="text/markdown",
            )
        with col_reset:
            if st.button("🔄 Nueva Sesión"):
                for key in ["council_phase", "council_log", "council_script", "council_report"]:
                    st.session_state.pop(key, None)
                st.rerun()

        # Mostrar imágenes generadas si existen
        img_path = Path("interpreter_output.png")
        if img_path.exists():
            st.image(str(img_path), caption="Gráfica generada por el ejecutor")


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
                if message.get("reasoning"):
                    with st.expander("🧠 Ver Razonamiento", expanded=False):
                        for step in message["reasoning"]:
                            if step["type"] == "tool_call":
                                st.code(f"🛠️ {step['name']}({json.dumps(step['args'], ensure_ascii=False)})")
                            elif step["type"] == "tool_result":
                                st.caption(f"📥 Resultado de {step['name']}:")
                                st.code(step["content"], language="json" if any(x in step['name'] for x in ["Alex", "search", "query"]) else None)
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

                    response_data = _run_async_in_thread(ask_agent())
                    
                    if isinstance(response_data, dict):
                        response = response_data.get("answer", "")
                        intermediate_steps = response_data.get("intermediate_steps", [])
                        
                        # Mostrar razonamiento en un expansor antes de la respuesta final
                        if intermediate_steps:
                            with st.expander("🧠 Razonamiento del Asistente (Pasos Ejecutados)", expanded=False):
                                for step in intermediate_steps:
                                    if step["type"] == "tool_call":
                                        st.code(f"🛠️ Llamando a: {step['name']}\nArgumentos: {json.dumps(step['args'], indent=2, ensure_ascii=False)}")
                                    elif step["type"] == "tool_result":
                                        st.caption(f"📥 Resultado de {step['name']}:")
                                        st.code(step["content"], language="json" if any(x in step['name'] for x in ["Alex", "search", "query"]) else None)
                    else:
                        response = response_data
                    
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
                    "image": img_data,
                    "reasoning": intermediate_steps if 'intermediate_steps' in locals() else []
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
# TAB 4: Acerca de / Estado DB
# =======================================================
with tab_about:
    st.header("🗄️ Estado en Vivo de Bases de Datos")
    st.markdown("Métricas extraídas en tiempo real reflejando la ingesta actual de documentos semánticos y en el Grafo.")
    
    graph_stats, qdrant_stats, graph_sample, qdrant_schema = fetch_database_live_stats()
    
    col_q, col_n = st.columns([1, 1.5])
    
    with col_q:
        st.subheader("🔵 Vector Store (Qdrant)")
        if "error" in qdrant_stats and qdrant_stats["error"]:
            st.error(f"Error Qdrant: {qdrant_stats['error']}")
        else:
            st.metric(label="Embeddings Locales Puros (api_papers)", value=f"{qdrant_stats.get('total_vectors', 0):,}")
            
        if "error" not in qdrant_schema:
            with st.expander("Ver Esquema Vectorial y Payload", expanded=True):
                st.json(qdrant_schema)
                
    with col_n:
        st.subheader("🟢 Knowledge Graph (Neo4j)")
        if "error" in graph_stats and graph_stats["error"]:
            st.error(f"Error Neo4j: {graph_stats['error']}")
        else:
            st.metric(label="Total Relaciones (Aristas)", value=f"{graph_stats.get('relationships', 0):,}")
            
            nodes = graph_stats.get("nodes", {})
            if nodes:
                df_nodes = pd.DataFrame(list(nodes.items()), columns=["Etiqueta", "Nodos Creados"]).sort_values("Nodos Creados", ascending=True)
                fig_nodes = px.bar(df_nodes, x="Nodos Creados", y="Etiqueta", orientation='h', color="Nodos Creados", color_continuous_scale="Viridis")
                fig_nodes.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=320)
                st.plotly_chart(fig_nodes, width="stretch")
            else:
                st.warning("No hay nodos persistidos.")

    st.markdown("---")
    
    # --- Neo4j Schema ER Diagram ---
    st.markdown("#### Esquema Conceptual de Neo4j (Metamodelo)")
    st.markdown("Diagrama de Entidad-Relación que describe cómo se almacena la información estructurada de Sinapsis AI.")
    schema_mermaid = """
    erDiagram
        Author ||--o{ Paper : AUTHORED
        Author }o--|| Institution : AFFILIATED_WITH
        Paper ||--o{ Concept : HAS_CONCEPT
        Paper ||--o{ Topic : HAS_TOPIC
        Paper ||--o{ SDG : ADDRESSES
        
        Academic ||--|| Author : is_subclass_of
        Entity ||--|| Institution : is_subclass_of
        
        Author {
            string id
            string name
        }
        Institution {
            string name
        }
        Paper {
            string doi
            string title
            int year
            int citations
        }
        Topic {
            string id
            string name
        }
        SDG {
            string id
            string name
        }
    """
    
    html_schema = f"""
    <div class="mermaid">
    {schema_mermaid}
    </div>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
    """
    import streamlit.components.v1 as components
    components.html(html_schema, height=450, scrolling=True)
                
    # --- Sample Network Rendering ---
    if "error" not in graph_sample and "nodes" in graph_sample and graph_sample["nodes"]:
        st.markdown("#### Muestra Topológica (Grafo de Conocimiento)")
        st.caption("Visualización interactiva de una porción de las conexiones reales actuales en Neo4j.")
        from pyvis.network import Network
        import tempfile
        
        net = Network(height='500px', width='100%', bgcolor='#ffffff', font_color='#1e293b')
        net.force_atlas_2based()
        
        for node in graph_sample["nodes"]:
            color = "#3b82f6"
            if node["label"] == "Academic": color = "#d946ef"
            elif node["label"] == "Author": color = "#d946ef"
            elif node["label"] == "Paper": color = "#10b981"
            elif node["label"] == "Topic": color = "#f59e0b"
            elif node["label"] == "SDG": color = "#ef4444"
            elif node["label"] == "Entity": color = "#6366f1"
            elif node["label"] == "Institution": color = "#6366f1"
            
            # Sanitizar textos por caracteres raros
            title_text = str(node.get("title", ""))[:45]
            net.add_node(node["id"], label=title_text, color=color, title=f"{node['label']}: {title_text}")
            
        for edge in graph_sample["edges"]:
            net.add_edge(edge["source"], edge["target"], title=edge["label"])
            
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
            net.save_graph(tmp.name)
            with open(tmp.name, "r", encoding="utf-8") as f:
                html_string = f.read()
                
        import streamlit.components.v1 as components
        components.html(html_string, height=515)
        
    st.markdown("---")
    
    st.header("Arquitectura del Sistema Híbrido")
    st.markdown("Este diagrama describe el flujo de datos global de **Sinapsis AI**, desde la recolección de metadatos hasta la Inteligencia Híbrida del Agente RAG.")
    
    mermaid_code = """
    graph TD
        A[SIIA / Local DB] --> B[Ingesta Inicial]
        B --> C[APIs Globales]
        C --> D[OpenAlex]
        C --> E[Scopus]
        C --> F[ORCID]
        
        D --> G[Neo4j: Knowledge Graph]
        E --> G
        F --> G
        
        G -.-> H[Qdrant: Vector DB]
        
        G --> I[Archivos Parquet]
        I --> J[Local Cache]
        
        J --> K[Dashboard de Analitica]
        K --> L[Vistas]
        L --> M[Perfil Institucional]
        L --> N[Perfil Académico]
        
        H <--> O[Orquestador RAG]
        G <--> O
        
        O --> P[Local LLM]
        O --> Q[Cypher Tool]
        O --> R[Semantic Search Tool]
        O --> S[Open Interpreter]
        O --> T[Web Search: DuckDuckGo]
        O --> U[Wikipedia Tool]
        O --> V[Direct OpenAlex API]
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
        A[1. Web Scraping / Archivo Local] --> B[Lista Base de Académicos JSON]
        B --> C[Enriquecimiento Global APIs]
        C --> D[OpenAlex]
        C --> E[ORCID / Scopus]
        D --> F[Neo4j: Nodos Academic / Paper]
        E --> F
        
        F --> G[Extracción Temática]
        F --> H[Clasificación ODS]
        
        G --> I[Neo4j: Grafo de Conocimiento]
        H --> I
        
        I --> J[Motor de Cómputo Analítico]
        J --> K[Métricas Institucionales]
        J --> L[Métricas por Investigador]
        K --> M[Dataframe en Caché Parquet]
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
