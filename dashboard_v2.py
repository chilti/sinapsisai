import streamlit as st
import streamlit.components.v1 as components
import asyncio
import concurrent.futures
import os
import sys
import random
import threading
from pathlib import Path
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
from agent.interpreter_agent import InterpreterOrchestrator
from dashboard_analytics import render_institucion_view, render_investigador_view, load_cached_data, get_institution_hierarchy
from lib.coauthra_integration import render_coauthra
from agent.tools_mcp import get_mcp_tools_sync

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
def fetch_database_live_stats(entity_name=None):
    """Obtiene los conteos globales de forma cacheada para no saturar las DBs."""
    try:
        neo = Neo4jGraphStore()
        graph_stats = neo.get_database_statistics()
        
        if entity_name == "FACULTAD DE CIENCIAS":
            # Caso especial: Colaboración FC - ICN
            graph_sample = neo.get_collaboration_sample_graph("FACULTAD DE CIENCIAS", "INSTITUTO DE CIENCIAS NUCLEARES", limit=150)
        elif entity_name:
            graph_sample = neo.get_funder_sample_graph(entity_name, limit=150)
        else:
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


@st.cache_data(ttl=3600)
def fetch_snii_ror_stats():
    """Lee las estadísticas del pipeline de SNII y ROR desde los archivos de mapeo y caché."""
    import os, json
    from pathlib import Path
    BASE = Path(os.path.dirname(os.path.abspath(__file__)))
    stats = {
        "snii_total": 0, "snii_with_ror": 0, "snii_with_orcid": 0,
        "snii_with_oa": 0, "institutions_total": 0, "institutions_with_ror": 0,
        "ror_high_confidence": 0, "ror_coverage_pct": 0.0,
        "last_error": None
    }
    try:
        # 1. Estadísticas de ROR (Mapeo de Instituciones)
        mapping_path = BASE / 'ROR' / 'snii_ror_mapping.json'
        if mapping_path.exists():
            with open(mapping_path, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            stats["institutions_total"] = len(mapping)
            stats["institutions_with_ror"] = sum(
                1 for v in mapping.values() if v.get('best_match_ror')
            )
            stats["ror_high_confidence"] = sum(
                1 for v in mapping.values()
                if v.get('best_match_ror') and (v.get('confidence', 0) or 0) >= 70
            )
            if stats["institutions_total"] > 0:
                stats["ror_coverage_pct"] = 100.0 * stats["institutions_with_ror"] / stats["institutions_total"]
    except Exception as e:
        stats["last_error"] = f"Error ROR: {str(e)}"

    try:
        # 2. Estadísticas de Investigadores SNII (Mapeo a OpenAlex/ORCID)
        # Nota: El archivo real está en data/ no en ingestion/
        verified_path = BASE / 'data' / 'snii_llm_verified_matches.json'
        if verified_path.exists():
            with open(verified_path, 'r', encoding='utf-8') as f:
                verified = json.load(f)
            
            # El archivo es una LISTA de dicts
            stats["snii_total"] = len(verified)
            # Contamos los que tienen orcid (en matched_orcid o dentro de snii.orcid)
            stats["snii_with_orcid"] = sum(
                1 for x in verified 
                if isinstance(x, dict) and (x.get('matched_orcid') or x.get('snii', {}).get('orcid'))
            )
            # Contamos los que tienen OpenAlex ID
            stats["snii_with_oa"] = sum(
                1 for x in verified 
                if isinstance(x, dict) and x.get('matched_openalex_id')
            )
    except Exception as e:
        if stats["last_error"]:
            stats["last_error"] += f" | Error SNII: {str(e)}"
        else:
            stats["last_error"] = f"Error SNII: {str(e)}"

    return stats


# ---- Inicialización del Orquestador ----
if "orchestrator" not in st.session_state:
    with st.spinner("Inicializando el Cerebro del Sistema..."):
        try:
            # El orquestador se crea en el hilo principal (es síncrono)
            # Solo el método .ask() es async y se ejecuta en el hilo dedicado
            st.session_state.orchestrator = RAGOrchestrator(tools_list=[])
            st.session_state.interpreter_orchestrator = InterpreterOrchestrator(st.session_state.orchestrator.memory_manager)
            st.session_state.session_id = f"st-{random.randint(1000, 9999)}"
        except Exception as e:
            st.error(f"Error inicializando el orquestador: {e}")
            import traceback
            st.code(traceback.format_exc())
            st.stop()

# ---- Inicialización del Asistente de Prueba (MCP Solo) ----
if "test_orchestrator" not in st.session_state:
    with st.spinner("Inicializando Asistente de Prueba (MCP)..."):
        try:
            # Cargamos herramientas desde el servidor MCP
            mcp_tools = get_mcp_tools_sync("http://localhost:8005/sse")
            
            test_sys_prompt = """
Eres SINAPSIS-PRUEBA, un asistente especializado exclusivamente en consultar el Grafo de Conocimiento de México a través de un servidor MCP.
Tu única fuente de información son las herramientas proporcionadas por el servidor MCP. 
Si el usuario pregunta algo que no puedes responder con las herramientas MCP, indícalo claramente.
"""
            st.session_state.test_orchestrator = RAGOrchestrator(
                tools_list=mcp_tools, 
                use_defaults=False,
                system_prompt=test_sys_prompt
            )
            st.session_state.test_chat_history = []
        except Exception as e:
            st.warning(f"No se pudo conectar al servidor MCP de prueba: {e}")
            st.session_state.test_orchestrator = RAGOrchestrator(tools_list=[], use_defaults=False)
            st.session_state.test_chat_history = []

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

    st.session_state.pending_plan = None
    st.session_state.pending_prompt = None

if "coauthra_author_id" not in st.session_state:
    st.session_state.coauthra_author_id = None

if "switch_to_coauthra" not in st.session_state:
    st.session_state.switch_to_coauthra = False


# ---- Sidebar ----
with st.sidebar:
    st.markdown("""
    <style>
    [data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background-color: rgba(28, 131, 225, 0.1) !important;
    }
    [data-testid="stSidebar"] div[data-baseweb="select"] * {
        color: white !important;
    }
    [data-testid="stSidebar"] [data-testid="stSelectbox"] div[role="button"] {
        background-color: rgba(28, 131, 225, 0.2) !important;
        color: white !important;
    }
    [data-testid="stSidebar"] [data-testid="stSelectbox"] div[role="button"] * {
        color: white !important;
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
    
    # --- Jerarquía de Navegación Nacional ---
    st.markdown("### 🗺️ Jerarquía de Navegación")
    hierarchy = get_institution_hierarchy()
    instituciones = sorted(list(hierarchy.keys()))
    
    # Selector 1: Institución
    default_inst_idx = 0
    unam_name = "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)"
    if unam_name in instituciones:
        default_inst_idx = instituciones.index(unam_name)
        
    selected_institution = st.selectbox(
        "Institución de Acreditación",
        instituciones,
        index=default_inst_idx,
        key="selected_institution_sidebar"
    )
    
    # Selector 2: Dependencia
    dependencias = sorted(list(hierarchy.get(selected_institution, {}).keys()))
    if not dependencias:
        dependencias = [selected_institution] # Fallback si no hay dependencias
    
    # Default a SECRETARIA GENERAL si es UNAM
    default_dep_idx = 0
    if selected_institution == unam_name and "SECRETARIA GENERAL" in dependencias:
        default_dep_idx = dependencias.index("SECRETARIA GENERAL")
        
    selected_dep = st.selectbox(
        "Dependencia de Acreditación",
        dependencias,
        index=default_dep_idx,
        key="selected_dep_sidebar"
    )
    
    # Selector 3: Subdependencia (Dinamico)
    subdependencias = hierarchy.get(selected_institution, {}).get(selected_dep, [])
    
    if subdependencias:
        # Si hay subdependencias, mostramos el selector
        default_sub_idx = 0
        if "FACULTAD DE CIENCIAS" in subdependencias:
            default_sub_idx = subdependencias.index("FACULTAD DE CIENCIAS")
            
        selected_sub = st.selectbox(
            "Subdependencia de Acreditación",
            subdependencias,
            index=default_sub_idx,
            key="selected_sub_sidebar"
        )
        # La entidad final para filtros es la subdependencia
        selected_entity = selected_sub
    else:
        # Si no hay subdependencias, la entidad es la dependencia
        selected_entity = selected_dep
    
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
st.info("🚀 **Nota:** El sistema se encuentra en fase de desarrollo. Los datos se están cargando y procesando.")
st.markdown("Inteligencia Bibliométrica Híbrida")

tab_inst, tab_inv, tab_chat, tab_test, tab_council, tab_about = st.tabs([
    "🏢 Panorama Institucional",
    "👤 Perfil Académico",
    "🤖 Asistente",
    "🧪 Asistente-Prueba (MCP)",
    "🏛️ Consejo Estratégico",
    "ℹ️ Acerca de..."
])

# =======================================================
# TAB: Consejo Estratégico Virtual
# =======================================================
with tab_council:
    st.header("🏛️ Consejo Estratégico Virtual")
    st.markdown(
        "Sistema multi-agente que orquesta un comité plural y diverso para diseñar estudios bibliométricos de forma autónoma."
    )

    # ── Inicialización del estado de sesión del Consejo ──
    if "council_phase" not in st.session_state:
        st.session_state.council_phase = "idle"   # idle | running | done
    if "council_log" not in st.session_state:
        st.session_state.council_log = []          # [(agente, texto), ...] — log completo
    
    # Logs por fase para mostrar resultados persistentes organizados
    for _ph in ["ph1", "ph2", "ph3", "ph4"]:
        if f"council_log_{_ph}" not in st.session_state:
            st.session_state[f"council_log_{_ph}"] = []
            
    if "council_plan" not in st.session_state:
        st.session_state.council_plan = None
    if "council_plan_path" not in st.session_state:
        st.session_state.council_plan_path = None

    # ── Panel de control ───────────────────────────────
    col_entity, col_info = st.columns([2, 2])

    with col_entity:
        council_entity = st.selectbox(
            "Entidad objetivo",
            entidades_filtradas,
            index=default_ent_idx,
            key="council_entity_select",
        )

    with col_info:
        st.info("🎯 El Consejo Estratégico diseñará un plan de estudio bibliométrico detallado para la entidad seleccionada.")

    # ── Configuración ──────────────────────────────────
    council_objective = st.text_area(
        "Objetivo del estudio bibliométrico",
        placeholder="Ej: Diseña un estudio para analizar las redes de colaboración y los temas emergentes del ICN entre 2019-2024...",
        height=100,
    )

    # ── Botón de inicio ────────────────────────────────
    can_run = bool(council_objective.strip())

    if st.button("▶ Diseñar Plan de Estudio", disabled=not can_run, type="primary"):
        st.session_state.council_phase = "running"
        st.session_state.council_log = []
        for _ph in ["ph1", "ph2", "ph3", "ph4"]:
            st.session_state[f"council_log_{_ph}"] = []
        st.session_state.council_plan = None
        st.session_state.council_plan_path = None
        st.rerun()

    # ── Ejecución ──────────────────────────────────────
    if st.session_state.council_phase == "running":
        try:
            from agent.council.strategic_council import run_strategic_council

            def _on_message(agent_name: str, content: str):
                if not content or not content.strip():
                    return
                st.session_state.council_log.append((agent_name, content))
                # Todo se clasifica en el log de la fase 1 (Diseño)
                st.session_state.council_log_ph1.append((agent_name, content))

            # ── Fase 1: Deliberación y Diseño ──
            with st.status("🎓 Generando Plan de Estudio Bibliométrico...", expanded=True):
                consensus_plan, plan_path = run_strategic_council(
                    entity=council_entity,
                    objective=council_objective,
                    on_message=_on_message,
                )
                st.session_state.council_plan = consensus_plan
                st.session_state.council_plan_path = str(plan_path)
                st.session_state.council_phase = "done"
                st.success(f"✅ Plan de estudio diseñado y guardado en `{plan_path.name}`")
            
            st.rerun()

        except Exception as e:
            st.error(f"❌ Error durante la deliberación: {e}")
            import traceback
            st.code(traceback.format_exc())
            st.session_state.council_phase = "idle"

    # ── Vista de resultados por fase (persistente) ───────────────────────────────
    AGENT_ICONS = {
        "Rectora": "👩🏾‍🎓",
        "Investigador_Campo": "🔬",
        "Bibliometra": "📊",
        "Politica_Cientifica": "🏛️",
        "Evaluadora_Ciencia": "⚖️",
        "Consejera_Social": "🤝",
        "Estudiante_Posgrado": "🎓",
        "Arquitecto_de_Datos": "🏗️",
        "SINAPSIS_Tecnico": "🤖",
        "SINAPSIS_Ejecutor": "⚙️",
        "Corrector_Python": "🐍",
        "Sistema": "💡",
    }

    if st.session_state.council_log_ph1:
        with st.expander("🏛️ Fase 1 — Deliberación y Diseño del Estudio", expanded=True):
            for agent_name, content in st.session_state.council_log_ph1:
                icon = AGENT_ICONS.get(agent_name, "💬")
                st.markdown(f"**{icon} {agent_name}**")
                st.markdown(content)
                st.divider()

    # ── Plan final y Descarga ────────────────
    if st.session_state.council_phase == "done" and st.session_state.council_plan:
        st.markdown("---")
        st.subheader("📑 Plan de Estudio Bibliométrico Generado")
        st.markdown(st.session_state.council_plan)

        col_plan, col_reset = st.columns([4, 1])
        with col_plan:
            plan_path_str = st.session_state.council_plan_path
            if plan_path_str and os.path.exists(plan_path_str):
                with open(plan_path_str, "rb") as f:
                    st.download_button(
                        label="📥 Descargar Plan de Estudio (Markdown)",
                        data=f.read(),
                        file_name=os.path.basename(plan_path_str),
                        mime="text/markdown",
                        type="primary",
                    )
        with col_reset:
            if st.button("🗑️ Nueva Sesión"):
                for k in ["council_phase", "council_log", "council_plan", "council_plan_path", "council_log_ph1", "council_log_ph2", "council_log_ph3", "council_log_ph4"]:
                    if k in st.session_state: del st.session_state[k]
                st.rerun()




# =======================================================
# TAB 1: Chat RAG Orquestador & Interpreter
# =======================================================
with tab_chat:
    
    st.markdown("### Selecciona el Modo del Asistente")
    assistant_type = st.radio(
        "Tipo de Asistente",
        ["⚡ Reactivo (Respuestas Rápidas)", "🧠 Analítico (Planificador & Ejecutor)"],
        horizontal=True,
        label_visibility="collapsed"
    )
    
    plan_mode_internal = "plan_and_execute"
    if "Analítico" in assistant_type:
        st.info("💡 **Aviso**: El asistente generará primero un plan y solicitará tu aprobación antes de ejecutar cualquier código.")
        plan_mode_internal = "plan_only"
        
    st.markdown("---")

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

    # ---- Botón de Confirmación de Plan ----
    if st.session_state.pending_plan:
        with st.chat_message("assistant"):
            st.warning("⚠️ **Plan detectado**. ¿Deseas proceder con la ejecución del código Python?")
            col_conf1, col_conf2 = st.columns([1,1])
            with col_conf1:
                if st.button("🚀 Aprobar y Ejecutar Código", use_container_width=True, type="primary"):
                    # Ejecutar el plan
                    current_plan = st.session_state.pending_plan
                    st.session_state.pending_plan = None # Limpiar para evitar recursión
                    
                    with st.chat_message("assistant"):
                        placeholder = st.empty()
                        placeholder.markdown("⚙️ *Ejecutando el plan aprobado...*")
                        try:
                            # Capturar de nuevo los objetos
                            interpreter_orch = st.session_state.interpreter_orchestrator
                            session_id = st.session_state.session_id
                            
                            async def run_plan():
                                return await interpreter_orch.ask(
                                    session_id, current_plan, mode="execute_plan", entity_context=selected_entity
                                )
                            
                            response_data = _run_async_in_thread(run_plan())
                            
                            # Mostrar respuesta
                            response = response_data.get("answer", "") if isinstance(response_data, dict) else response_data
                            placeholder.markdown(response)
                            
                            # Manejar imagen
                            img_data = None
                            if os.path.exists("interpreter_output.png"):
                                with open("interpreter_output.png", "rb") as f:
                                    img_data = f.read()
                                st.image(img_data)
                                os.remove("interpreter_output.png")
                                
                            # Guardar en historial
                            st.session_state.chat_history.append({
                                "role": "assistant",
                                "content": response,
                                "image": img_data,
                                "reasoning": response_data.get("intermediate_steps", []) if isinstance(response_data, dict) else []
                            })
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error en ejecución: {e}")
            with col_conf2:
                if st.button("❌ Cancelar", use_container_width=True):
                    st.session_state.pending_plan = None
                    st.session_state.pending_prompt = None
                    st.rerun()

    # ---- Input del usuario ----
    if prompt := st.chat_input("Escribe tu consulta científica aquí..."):
        # Si hay un plan pendiente, avisar o ignorar
        if st.session_state.pending_plan:
            st.info("Por favor, aprueba o cancela el plan actual antes de enviar una nueva consulta.")
        else:
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
                        session_id = st.session_state.session_id
                        orchestrator = st.session_state.orchestrator
                        interpreter_orch = st.session_state.interpreter_orchestrator

                        async def ask_agent():
                            if "Analítico" in assistant_type:
                                # Forzamos PLAN_ONLY para el nuevo flujo
                                return await interpreter_orch.ask(
                                    session_id, prompt, mode="plan_only", entity_context=selected_entity
                                )
                            else:
                                return await orchestrator.ask(session_id, prompt, entity_context=selected_entity)

                        response_data = _run_async_in_thread(ask_agent())
                        
                        if isinstance(response_data, dict):
                            response = response_data.get("answer", "")
                            intermediate_steps = response_data.get("intermediate_steps", [])
                            
                            if intermediate_steps:
                                with st.expander("🧠 Razonamiento del Asistente", expanded=False):
                                    for step in intermediate_steps:
                                        if step["type"] == "tool_call":
                                            st.code(f"🛠️ Llamando a: {step['name']}")
                                        elif step["type"] == "tool_result":
                                            st.caption(f"📥 Resultado de {step['name']}:")
                                            st.code(step["content"][:200] + "...", language="json")
                        else:
                            response = response_data
                        
                        placeholder.markdown(response)

                        # Si era modo analítico, guardamos el plan para ejecución posterior
                        if "Analítico" in assistant_type:
                            st.session_state.pending_plan = response
                            st.session_state.pending_prompt = prompt

                    except Exception as e:
                        import traceback
                        placeholder.error(f"Error en orquestación: {e}")
                        response = f"Error: {e}"

                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": response,
                        "reasoning": intermediate_steps if 'intermediate_steps' in locals() else []
                    })
                    st.rerun()

# =======================================================
# TAB: Asistente-Prueba (MCP Neo4j Solo)
# =======================================================
with tab_test:
    st.header("🧪 Asistente de Prueba (MCP-Only)")
    st.info("Este asistente utiliza exclusivamente el servidor MCP del nuevo Neo4j como herramienta.")
    
    col_clear_test, _ = st.columns([1, 4])
    with col_clear_test:
        if st.button("🗑️ Limpiar Conversación Prueba"):
            st.session_state.test_chat_history = []
            st.session_state.test_orchestrator.clear_session(st.session_state.session_id + "-test")
            st.rerun()

    test_chat_container = st.container()

    with test_chat_container:
        for message in st.session_state.test_chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if message.get("reasoning"):
                    with st.expander("🧠 Ver Razonamiento", expanded=False):
                        for step in message["reasoning"]:
                            if step["type"] == "tool_call":
                                st.code(f"🛠️ {step['name']}({json.dumps(step['args'], ensure_ascii=False)})")
                            elif step["type"] == "tool_result":
                                st.caption(f"📥 Resultado de {step['name']}:")
                                st.code(step["content"][:2000], language="json")

    # ---- Input del usuario ----
    if test_prompt := st.chat_input("Consulta al grafo de México via MCP...", key="test_chat_input"):
        st.session_state.test_chat_history.append({"role": "user", "content": test_prompt})
        with test_chat_container:
            with st.chat_message("user"):
                st.markdown(test_prompt)

        with test_chat_container:
            with st.chat_message("assistant"):
                placeholder = st.empty()
                placeholder.markdown("🔍 *Consultando servidor MCP...*")

                try:
                    session_id = st.session_state.session_id + "-test"
                    orchestrator = st.session_state.test_orchestrator

                    async def ask_test_agent():
                        return await orchestrator.ask(session_id, test_prompt)

                    response_data = _run_async_in_thread(ask_test_agent())
                    
                    if isinstance(response_data, dict):
                        response = response_data.get("answer", "")
                        intermediate_steps = response_data.get("intermediate_steps", [])
                    else:
                        response = response_data
                        intermediate_steps = []
                    
                    placeholder.markdown(response)

                except Exception as e:
                    placeholder.error(f"Error en orquestación MCP: {e}")
                    response = f"Error: {e}"
                    intermediate_steps = []

                st.session_state.test_chat_history.append({
                    "role": "assistant",
                    "content": response,
                    "reasoning": intermediate_steps
                })
                st.rerun()

# =======================================================
# TAB 2: Vista de la Institución
# =======================================================
with tab_inst:
    render_institucion_view(selected_entity, institution_name=selected_institution)

# =======================================================
# TAB 3: Vista por Investigador
# =======================================================
with tab_inv:
    render_investigador_view(selected_entity, institution_name=selected_institution)

# =======================================================

# =======================================================
# TAB 6: Acerca de / Estado DB
# =======================================================
with tab_about:
    st.info("""
        **🛡️ Aviso de Privacidad y Fuentes de Datos**
        
        La información bibliométrica y de producción científica contenida en **Sinapsis AI** procede exclusivamente de fuentes de datos públicas y repositorios institucionales de acceso libre, incluyendo: **OpenAlex, Scopus, ORCID, SNII (CONAHCYT), SIIA (UNAM)** y otros catálogos académicos globales.
        
        **Privacidad y Datos Personales:** Este sistema no almacena ni procesa datos personales sensibles. La plataforma se limita exclusivamente al análisis de metadatos de carácter público relacionados con la trayectoria científica y académica, con el objetivo de fomentar la Ciencia Abierta y la transparencia en la investigación nacional.
    """)
    
    st.header("📂 Código Fuente y Acceso")
    col_repo1, col_repo2 = st.columns(2)
    with col_repo1:
        st.markdown("**Repositorio en GitHub:**")
        st.markdown("[github.com/chilti/sinapsisai](https://github.com/chilti/sinapsisai)")
    
    st.header("👥 Equipo de Trabajo")
    
    col_team1, col_team2 = st.columns(2)
    
    with col_team1:
        st.markdown("#### FACULTAD DE CIENCIAS")
        st.markdown("- Dr. Humberto Andrés Carrillo Calvet")
        st.markdown("- Dr. José Luis Jiménez Andrade")
        st.markdown("- Dra. María Victoria Guzmán Sánchez")
        
        st.markdown("#### Centro de Ciencias de la Complejidad")
        st.markdown("- Dr. Ricardo Arencibia Jorge")
        st.markdown("- M. en C. Romel Calero Ramos")
        st.markdown("- M. en C. Lorena Delago Quiroz")

    with col_team2:
        st.markdown("")
        st.markdown("")

        st.markdown("#### Estudiantes de la FACULTAD DE CIENCIAS")
        st.markdown("- **Ana Valeria Deloya Andrade**: Ingeniería de Prompts para describir y analizar gráficas.")
        st.markdown("- **Rodrigo Aldair Ortega Venegas**: Visualización de los Objetivos de Desarrollo Sostenible.")
        st.markdown("- **Leonardo Vázquez Rodríguez**: Visualización de Trayectorias.")
    
    st.markdown("---")
    # ─── Estadísticas del Pipeline SNII y ROR ─────────────────────────
    st.header("📊 Cobertura de Datos: SNII y ROR")
    st.markdown("Estadísticas sobre el mapeo de investigadores del Sistema Nacional de Investigadoras e Investigadores y su vinculación con instituciones vía Research Organization Registry (ROR).")
    snii_ror = fetch_snii_ror_stats()
    if snii_ror.get("last_error"):
        st.warning(f"Advertencia al cargar estadísticas: {snii_ror['last_error']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "🔬 Investigadores SNII",
        f"{snii_ror.get('snii_total', 0):,}",
        help="Total de académicos del SNII cargados en el sistema."
    )
    c2.metric(
        "🆔 Con ORCID",
        f"{snii_ror.get('snii_with_orcid', 0):,}",
        help="Número de investigadores con ORCID verificado."
    )
    c3.metric(
        "🌐 Con OpenAlex ID",
        f"{snii_ror.get('snii_with_oa', 0):,}",
        help="Investigadores vinculados exitosamente a un ID de OpenAlex."
    )
    c4.metric(
        "🏛️ Entidades",
        f"{snii_ror.get('institutions_total', 0):,}",
        help="Combinaciones Institución|Subdependencia en el mapeo SNII-ROR."
    )
    c5, c6, c7 = st.columns(3)
    c5.metric(
        "✅ Con ROR asignado",
        f"{snii_ror.get('institutions_with_ror', 0):,}",
        help="Entidades con un ROR ID identificado (cualquier confianza)."
    )
    c6.metric(
        "🎯 ROR Confianza ≥ 70%",
        f"{snii_ror.get('ror_high_confidence', 0):,}",
        help="Entidades con ROR validado con nivel de confianza ≥ 70."
    )
    c7.metric(
        "📈 Cobertura ROR (%)",
        f"{snii_ror.get('ror_coverage_pct', 0.0):.1f}%",
        help="Porcentaje de entidades institucionales con al menos un ROR asignado."
    )
    st.markdown("---")
    st.header("🗄️ Estado en Vivo de Bases de Datos")
    st.markdown("Métricas extraídas en tiempo real reflejando la ingesta actual de documentos semánticos y en el Grafo.")
    
    graph_stats, qdrant_stats, graph_sample, qdrant_schema = fetch_database_live_stats(selected_entity)
    
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
        Institution }o--|| State : LOCATED_IN
        State }o--|| Country : PART_OF
        
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
            elif node["label"] == "Funder": color = "#eab308"
            elif node["label"] == "Award": color = "#fbbf24"
            elif node["label"] == "State": color = "#94a3b8"  # Gris pizarra
            elif node["label"] == "Country": color = "#1e293b" # Azul muy oscuro (casi negro)
            
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
        G[Neo4j: Knowledge Graph]-->I[Archivos Parquet]
        
        G -.-> H[Qdrant: Vector DB]
        
        
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

    st.markdown("---")
    st.header("Flujo Detallado de Extracción de Producción Científica")
    st.markdown("Este diagrama profundiza en la lógica de recolección desde identificadores de autoría hasta la consolidación en el caché analítico.")
    
    mermaid_detailed = """
    graph LR
    subgraph "Fase 1: Identificación y Perfilado (SIIA Scraper)"
        A[Excel: Lista de Investigadores] --> B["siia_scraper.py"]
        B --> C{¿Existe en Neo4j?}
        C -- Sí --> D[Saltar Scraper / Usar Cache]
        C -- No --> E[Búsqueda Interna SIIA UNAM]
        E --> F[Navegación Selenium Headless]
        F --> G[Cerrar Modales / Validar Nombre]
        G --> H[Extraer IDs: Scopus, ORCID, Áreas]
        H --> I["profesores_Entidad.json"]
    end

    subgraph "Fase 2: Extracción de Producción Científica (APIs)"
        I --> J["ingest_apis.py"]
        J --> K["Scopus API (pybliometrics)"]
        J --> L["ORCID API (Public V3)"]
        K -- Documentos --> M[Unificación por DOI]
        L -- Trabajos --> M
        M --> N["OpenAlex Enrichment (pyalex)"]
        N --> O["Fallback por Título Exacto (si no hay DOI)"]
        O --> P[Metadatos Completos: Citas, FWCI, ODS, APC]
    end

    subgraph "Fase 3: Materialización y Almacenamiento"
        P --> Q["Embeddings (Nomic / LM Studio)"]
        Q --> R[(Qdrant: api_papers)]
        P --> S[(Neo4j: APIPaper)]
        S --> T[Relación :AUTHORED con :Academic]
        T --> U[Relación :AFFILIATED_TO con :Entity]
    end

    subgraph "Fase 4: Consolidación Analítica"
        U --> V["compute_scholar_metrics.py"]
        V --> W["Caché Jerárquica: Parquets"]
        W --> X[Dashboard Analytics / Agentes AI]
    end

    style I fill:#f96,stroke:#333,stroke-width:2px
    style R fill:#0000FF,stroke:#fff,stroke-width:1px,color:#fff
    style S fill:#00d9ff,stroke:#fff,stroke-width:1px
    style W fill:#f9f,stroke:#333,stroke-dasharray: 5 5
    """

    html_mermaid_detailed = f"""
    <div class="mermaid">
    {mermaid_detailed}
    </div>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
    </script>
    """
    components.html(html_mermaid_detailed, height=1200, scrolling=True)

# ---- Footer ----
st.markdown("""
    <div class="footer">
        📊 Sinapsis AI - UNAM
    </div>
""", unsafe_allow_html=True)
