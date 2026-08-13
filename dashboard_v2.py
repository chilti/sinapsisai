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
load_dotenv()

# Asegurar que el directorio raíz está en el path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

import pandas as pd
import plotly.express as px

# Detectar servicios externos antes de importarlos
from lib.service_availability import NEO4J_AVAILABLE, QDRANT_AVAILABLE

if NEO4J_AVAILABLE:
    from database.knowledge_graph import Neo4jGraphStore
if QDRANT_AVAILABLE:
    from database.vector_store import QdrantStore

from agent.orchestrator import RAGOrchestrator
from agent.interpreter_agent import InterpreterOrchestrator
from dashboard_analytics import render_institucion_view, render_investigador_view, load_cached_data, get_institution_hierarchy
from lib.coauthra_integration import render_coauthra
from agent.tools_mcp import get_mcp_tools_sync
from lib import auth


# ---- Configuración de página ----
st.set_page_config(
    page_title="SNII Info TlachIA: Hub de la Ciencia Mexicana",
    page_icon="assets/microscopio.png",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---- CSS ----
st.markdown("""
    <style>
    .stApp { background-color: #f4f4f5; color: #1e293b; }
    
    /* Ocultar la decoración del header pero conservar funcionalidad */
    header[data-testid="stHeader"] {
        background-color: transparent !important;
        box-shadow: none !important;
    }
    header[data-testid="stHeader"]::before {
        display: none !important;
    }
    /* Ocultar la caja de "Deploy" y menú derecho específicamente */
    .stAppDeployButton, [data-testid="stHeaderActionElements"] {
        display: none !important;
    }
    /* El botón del sidebar debe estar visible y por encima */
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        z-index: 100000 !important;
    }
    
    /* Eliminar el espacio en blanco gigante arriba del título */
    div.block-container {
        padding-top: 1rem !important;
    }
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Montserrat', sans-serif;
    }
    /* Proteger la fuente de los iconos de Material Design de Streamlit */
    .st-emotion-cache-1n76uvr, .stIconMaterial, [data-testid="stIconMaterial"], .material-symbols-rounded {
        font-family: 'Material Symbols Rounded', sans-serif !important;
    }
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
    h1, h2, h3 { color: #003D64 !important; font-family: 'Montserrat', sans-serif; font-weight: 700; }
    .sidebar-title-custom {
        text-align: center;
        margin-top: 5px;
        font-size: 36px !important;
        font-weight: 700;
        font-family: 'Montserrat', sans-serif;
        color: #f1f5f9 !important;
    }
    .footer {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: #003D64; color: #EAEDEF;
        text-align: center; padding: 8px; font-size: 12px;
        border-top: 4px solid #E39918;
        font-weight: 600;
        z-index: 9999;
    }
    .stButton>button {
        background-color: #E39918; color: #003D64;
        border: 1px solid #b6932b;
        border-radius: 6px; padding: 0.5rem 1rem; font-weight: 600;
        font-family: 'Montserrat', sans-serif;
    }
    .stButton>button:hover {
        background-color: #E8442A;
        border-color: #E8442A;
        color: #ffffff !important;
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
    graph_stats = {"nodes": {}, "relationships": 0}
    graph_sample = {}
    qdrant_stats = {"total_vectors": 0}
    qdrant_schema = {}

    if NEO4J_AVAILABLE:
        try:
            neo = Neo4jGraphStore()
            graph_stats = neo.get_database_statistics()
            if entity_name == "FACULTAD DE CIENCIAS":
                graph_sample = neo.get_collaboration_sample_graph("FACULTAD DE CIENCIAS", "INSTITUTO DE CIENCIAS NUCLEARES", limit=150)
            elif entity_name:
                graph_sample = neo.get_funder_sample_graph(entity_name, limit=150)
            else:
                graph_sample = neo.get_sample_graph(limit=80)
            neo.close()
        except Exception as e:
            graph_stats = {"error": str(e), "nodes": {}, "relationships": 0}
            graph_sample = {"error": str(e)}

    if QDRANT_AVAILABLE:
        try:
            qdrant = QdrantStore(collection_name="api_papers")
            qdrant_stats = qdrant.get_collection_stats()
            qdrant_schema = qdrant.get_schema_info()
        except Exception as e:
            qdrant_stats = {"total_vectors": 0, "error": str(e)}
            qdrant_schema = {"error": str(e)}

    return graph_stats, qdrant_stats, graph_sample, qdrant_schema


def trigger_background_processing(academic_name, orcid=None):
    """Lanza los procesos de ingesta y métricas en segundo plano."""
    import subprocess
    import os
    
    # Ruta base
    base_dir = os.path.abspath(os.path.dirname(__file__))
    
    # 1. Ingesta
    cmd_ingest = [
        sys.executable, 
        os.path.join(base_dir, "SNII", "ingest_snii_apis.py"),
        "--name", academic_name,
        "--ch"
    ]
    if orcid:
        cmd_ingest.extend(["--orcid", orcid])
    
    # 2. Métricas
    cmd_metrics = [
        sys.executable,
        os.path.join(base_dir, "ingestion", "compute_scholar_metrics_ch.py"),
        "--academic", academic_name
    ]
    
    # Ejecutar sin esperar (background)
    try:
        # Usamos setsid para que el proceso sobreviva al cierre del dashboard si es necesario
        subprocess.Popen(cmd_ingest, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        subprocess.Popen(cmd_metrics, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except Exception as e:
        st.error(f"Error al lanzar procesos de segundo plano: {e}")
        return False

def select_academic_in_ui(academic_name):
    from database.knowledge_graph import Neo4jGraphStore
    from dashboard_analytics import get_institution_hierarchy
    
    hierarchy = get_institution_hierarchy()
    instituciones = list(hierarchy.keys())
    
    neo = Neo4jGraphStore()
    query = """
    MATCH (a:Person)
    WHERE a.fullname = $name OR a.id = $name
    MATCH (a)-[:AFFILIATED_TO]->(node)
    OPTIONAL MATCH (node)-[:PART_OF*0..2]->(parent)
    RETURN labels(node) as node_labels, node.name as node_name, labels(parent) as parent_labels, parent.name as parent_name
    """
    inst, dep, sub = None, None, None
    with neo.driver.session() as session:
        result = session.run(query, name=academic_name)
        for record in result:
            n_labels = record["node_labels"]
            n_name = record["node_name"]
            p_labels = record["parent_labels"]
            p_name = record["parent_name"]
            
            if n_labels and "Institution" in n_labels: inst = n_name
            if n_labels and "Dependency" in n_labels: dep = n_name
            if n_labels and "Subdependency" in n_labels: sub = n_name
            
            if p_labels and "Institution" in p_labels: inst = p_name
            if p_labels and "Dependency" in p_labels: dep = p_name
            if p_labels and "Subdependency" in p_labels: sub = p_name
    neo.close()
    
    # Guardar afiliación real en session state para el desacoplamiento
    st.session_state.selected_academic_real_inst = inst
    st.session_state.selected_academic_real_dep = dep
    st.session_state.selected_academic_real_sub = sub
    
    # Resolver nombres exactos con la jerarquía
    valid_inst = None
    if inst:
        if inst in instituciones: valid_inst = inst
        else:
            for h_inst in instituciones:
                if inst in h_inst or h_inst in inst:
                    valid_inst = h_inst
                    break
    
    if valid_inst:
        st.session_state.selected_institution_sidebar = valid_inst
        dep_data = hierarchy.get(valid_inst, {})
        deps = list(dep_data.keys()) if isinstance(dep_data, dict) else list(dep_data)
        
        valid_dep = None
        if dep:
            if dep in deps: valid_dep = dep
            else:
                for h_dep in deps:
                    if dep in h_dep or h_dep in dep:
                        valid_dep = h_dep
                        break
        
        if valid_dep:
            st.session_state.selected_dep_sidebar = valid_dep
            subs = dep_data.get(valid_dep, []) if isinstance(dep_data, dict) else []
            
            valid_sub = None
            if sub:
                if sub in subs: valid_sub = sub
                else:
                    for h_sub in subs:
                        if sub in h_sub or h_sub in sub:
                            valid_sub = h_sub
                            break
            if valid_sub:
                st.session_state.selected_sub_sidebar = valid_sub
        
    st.session_state.selected_academic_search = academic_name
    st.session_state.switch_tab = "Perfiles de Investigadores"
    st.query_params["academic"] = academic_name
    st.query_params.pop("entity_id", None)
    st.query_params.pop("entity_name", None)
    st.session_state['tab_inv_loaded'] = True  # Auto-cargar la pestaña
    st.session_state.global_search_executed = True


def select_entity_in_ui(entity_id, entity_name, entity_type=None):
    from dashboard_analytics import get_institution_hierarchy
    
    # 1. Obtener la jerarquía estructurada de la UI
    hierarchy = get_institution_hierarchy()
    instituciones = list(hierarchy.keys())
    
    # 2. Descomponer el ID jerárquico (ej: "UNIVERSIDAD...||FACULTAD DE CIENCIAS")
    inst, dep, sub = None, None, None
    if entity_id:
        parts = str(entity_id).split("||")
        if len(parts) >= 1: inst = parts[0]
        if len(parts) >= 2: dep = parts[1]
        if len(parts) >= 3: sub = parts[2]
    else:
        # Fallback al nombre si no hay ID jerárquico
        inst = entity_name
        
    # 3. Resolver el nombre exacto de la institución en la UI
    valid_inst = None
    if inst:
        if inst in instituciones:
            valid_inst = inst
        else:
            for h_inst in instituciones:
                if inst in h_inst or h_inst in inst:
                    valid_inst = h_inst
                    break
                    
    # 4. Si encontramos la institución, resolver dependencia y subdependencia en la UI
    if valid_inst:
        st.session_state.selected_institution_sidebar = valid_inst
        dep_data = hierarchy.get(valid_inst, {})
        deps = list(dep_data.keys()) if isinstance(dep_data, dict) else list(dep_data)
        
        valid_dep = None
        if dep:
            if dep in deps:
                valid_dep = dep
            else:
                for h_dep in deps:
                    if dep in h_dep or h_dep in dep:
                        valid_dep = h_dep
                        break
        
        if valid_dep:
            st.session_state.selected_dep_sidebar = valid_dep
            subs = dep_data.get(valid_dep, []) if isinstance(dep_data, dict) else []
            
            valid_sub = None
            if sub:
                if sub in subs:
                    valid_sub = sub
                else:
                    for h_sub in subs:
                        if sub in h_sub or h_sub in sub:
                            valid_sub = h_sub
                            break
            if valid_sub:
                st.session_state.selected_sub_sidebar = valid_sub
            else:
                if "selected_sub_sidebar" in st.session_state:
                    del st.session_state["selected_sub_sidebar"]
        else:
            if "selected_dep_sidebar" in st.session_state:
                del st.session_state["selected_dep_sidebar"]
            if "selected_sub_sidebar" in st.session_state:
                del st.session_state["selected_sub_sidebar"]
    else:
        # Fallback de búsqueda global en todo el árbol jerárquico si no se resolvió por ID
        for h_inst, dep_data in hierarchy.items():
            if entity_name == h_inst:
                st.session_state.selected_institution_sidebar = h_inst
                if "selected_dep_sidebar" in st.session_state:
                    del st.session_state["selected_dep_sidebar"]
                if "selected_sub_sidebar" in st.session_state:
                    del st.session_state["selected_sub_sidebar"]
                valid_inst = h_inst
                break
                
            deps = list(dep_data.keys()) if isinstance(dep_data, dict) else list(dep_data)
            for h_dep in deps:
                if entity_name == h_dep:
                    st.session_state.selected_institution_sidebar = h_inst
                    st.session_state.selected_dep_sidebar = h_dep
                    if isinstance(dep_data, dict):
                        subs = dep_data.get(h_dep, [])
                        if subs:
                            st.session_state.selected_sub_sidebar = subs[0]
                    valid_inst = h_inst
                    break
                    
                if isinstance(dep_data, dict):
                    subs = dep_data.get(h_dep, [])
                    for h_sub in subs:
                        if entity_name == h_sub:
                            st.session_state.selected_institution_sidebar = h_inst
                            st.session_state.selected_dep_sidebar = h_dep
                            st.session_state.selected_sub_sidebar = h_sub
                            valid_inst = h_inst
                            break
                if valid_inst:
                    break
            if valid_inst:
                break
                
    st.session_state.switch_tab = "Panorama Institucional"
    st.query_params["entity_id"] = entity_id
    st.query_params["entity_name"] = entity_name
    st.query_params.pop("academic", None)
    st.session_state['tab_inst_loaded'] = True  # Auto-cargar la pestaña
    st.session_state.global_search_executed = True


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
        # Intentamos cargar la versión V2 primero, y si no existe el mapeo original
        mapping_path = BASE / 'data' / 'snii_ror_verified_matches_v2.json'
        old_mapping_path = BASE / 'ROR' / 'snii_ror_mapping.json'
        
        if mapping_path.exists():
            with open(mapping_path, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            total_entities = 0
            with_ror = 0
            high_conf = 0
            
            for inst_name, inst_data in mapping.items():
                total_entities += 1
                root = inst_data.get('root_info', {})
                if root.get('root_ror'):
                    with_ror += 1
                    if (root.get('confidence') or 0) >= 70:
                        high_conf += 1
                        
                units = inst_data.get('units', {})
                for unit_name, unit_data in units.items():
                    total_entities += 1
                    if unit_data.get('unit_ror'):
                        with_ror += 1
                        if (unit_data.get('confidence') or 0) >= 70:
                            high_conf += 1
                            
            stats["institutions_total"] = total_entities
            stats["institutions_with_ror"] = with_ror
            stats["ror_high_confidence"] = high_conf
            if total_entities > 0:
                stats["ror_coverage_pct"] = 100.0 * with_ror / total_entities

        elif old_mapping_path.exists():
            with open(old_mapping_path, 'r', encoding='utf-8') as f:
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
        # 2. Estadísticas de Investigadores SNII (Directo desde Neo4j Graph)
        try:
            from database.knowledge_graph import Neo4jGraphStore
            neo = Neo4jGraphStore()
            query = """
            MATCH (p:Person) WHERE p.is_snii = true
            WITH count(p) AS snii_total,
                 sum(CASE WHEN size(p.orcids) > 0 THEN 1 ELSE 0 END) AS snii_with_orcid,
                 sum(CASE WHEN size(p.openalex_ids) > 0 THEN 1 ELSE 0 END) AS snii_with_oa
            RETURN snii_total, snii_with_orcid, snii_with_oa
            """
            with neo.driver.session() as session:
                result = session.run(query)
                record = result.single()
                if record:
                    stats["snii_total"] = record["snii_total"]
                    stats["snii_with_orcid"] = record["snii_with_orcid"]
                    stats["snii_with_oa"] = record["snii_with_oa"]
        except ImportError:
            # Fallback en caso de problemas con la librería
            pass
    except Exception as e:
        if stats["last_error"]:
            stats["last_error"] += f" | Error SNII: {str(e)}"
        else:
            stats["last_error"] = f"Error SNII: {str(e)}"

    return stats


# ---- Inicialización de Autenticación ----
auth.init_auth_session()
auth.handle_orcid_callback()

# ---- Gestión de URL (Permalink) ----
if "url_parsed" not in st.session_state:
    st.session_state.url_parsed = True
    if "academic" in st.query_params and NEO4J_AVAILABLE:
        select_academic_in_ui(st.query_params["academic"])
    elif "entity_id" in st.query_params and "entity_name" in st.query_params:
        select_entity_in_ui(st.query_params["entity_id"], st.query_params["entity_name"])

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
    import os
    logo_path = os.path.join(os.path.dirname(__file__), "assets", "microscopio.png")
    if os.path.exists(logo_path):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image(logo_path, use_container_width=True)
        st.markdown("<div class='sidebar-title-custom'>SNII Info TlachIA</div>", unsafe_allow_html=True)
    else:
        st.title("🔬 SNII Info TlachIA")
    st.markdown("---")

    # --- Sección de Usuario / ORCID ---
    if NEO4J_AVAILABLE:
        st.markdown("---")
        st.subheader("👤 Mi Perfil")
        user = st.session_state.authenticated_user
        if user:
            st.write(f"**Hola, {user.get('name', 'Investigador')}**")
            st.caption(f"ORCID: {user.get('orcid')}")
            
            # Consultar si ya está vinculado en Neo4j
            neo = Neo4jGraphStore()
            profile = neo.get_user_profile(user.get('orcid'))
            neo.close()
            
            if profile and profile.get('academic_id'):
                st.success(f"✅ Perfil Verificado: {profile.get('academic_name')}")
            else:
                st.warning("⚠️ Perfil no vinculado")
                if st.button("🔗 Vincular mi Perfil"):
                    st.session_state.show_claim_profile = True
            
            if st.button("Log out"):
                st.session_state.authenticated_user = None
                st.rerun()
        else:
            login_url = auth.get_orcid_login_url()
            if login_url:
                st.link_button("🆔 Identifícate con ORCID", login_url, type="primary", use_container_width=True)
            else:
                st.error("Error en configuración de ORCID")
    st.markdown("---")
    st.subheader("Configuración")
    
    # --- Jerarquía de Navegación Nacional ---
    st.markdown("### 🗺️ Jerarquía de Navegación")
    hierarchy = get_institution_hierarchy()
    instituciones = sorted(list(hierarchy.keys()))
    if not instituciones:
        instituciones = ["(No hay datos de instituciones disponibles)"]
    
    # Selector 1: Institución
    default_inst_idx = 0
    unam_name = "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)"
    if unam_name in instituciones:
        default_inst_idx = instituciones.index(unam_name)
        
    if "selected_institution_sidebar" not in st.session_state:
        st.session_state.selected_institution_sidebar = instituciones[default_inst_idx]
        
    selected_institution = st.selectbox(
        "Institución de Acreditación",
        instituciones,
        key="selected_institution_sidebar"
    )
    
    # Selector 2: Dependencia
    dep_data = hierarchy.get(selected_institution, {})
    if isinstance(dep_data, dict):
        dependencias = sorted(list(dep_data.keys()))
    else:
        dependencias = sorted(list(dep_data))
        
    if not dependencias:
        dependencias = [selected_institution] # Fallback si no hay dependencias
    elif selected_institution not in dependencias:
        dependencias = [selected_institution] + dependencias # Agregar institución como opción agregada
    
    # Default a SECRETARIA GENERAL si es UNAM
    default_dep_idx = 0
    if selected_institution == unam_name and "SECRETARIA GENERAL" in dependencias:
        default_dep_idx = dependencias.index("SECRETARIA GENERAL")
        
    if "selected_dep_sidebar" not in st.session_state or st.session_state.selected_dep_sidebar not in dependencias:
        st.session_state.selected_dep_sidebar = dependencias[default_dep_idx]
        
    selected_dep = st.selectbox(
        "Dependencia de Acreditación",
        dependencias,
        key="selected_dep_sidebar"
    )
    
    # Selector 3: Subdependencia (Dinamico)
    if isinstance(dep_data, dict):
        subdependencias = dep_data.get(selected_dep, [])
    else:
        subdependencias = [] # En el formato antiguo no había subdependencias estructuradas así
    
    if subdependencias:
        if isinstance(subdependencias, list):
            subdependencias = list(subdependencias) # Copia por si es la referencia original
            
            agg_option = f"{selected_dep} (Toda la Dependencia)"
            
            modified_subs = []
            for sub in subdependencias:
                if sub == selected_dep:
                    modified_subs.append(f"{sub} (Subdependencia)")
                else:
                    modified_subs.append(sub)
            
            opciones_mostrar = [agg_option] + modified_subs
                
        # Si hay subdependencias, mostramos el selector
        default_sub_idx = 0
        if "FACULTAD DE CIENCIAS" in opciones_mostrar:
            default_sub_idx = opciones_mostrar.index("FACULTAD DE CIENCIAS")
            
        if "selected_sub_sidebar" not in st.session_state or st.session_state.selected_sub_sidebar not in opciones_mostrar:
            st.session_state.selected_sub_sidebar = opciones_mostrar[default_sub_idx]
            
        selected_sub = st.selectbox(
            "Subdependencia de Acreditación",
            opciones_mostrar,
            key="selected_sub_sidebar"
        )
        
        # La entidad final para filtros es la subdependencia o la dependencia agregada
        if selected_sub == agg_option:
            selected_entity = selected_dep
        else:
            selected_entity = selected_sub
    else:
        # Si no hay subdependencias, la entidad es la dependencia
        selected_entity = selected_dep
        selected_sub = None
    
    st.selectbox("Modelo", ["openai/gpt-oss-20b"], index=0)




# ---- Interfaz Principal ----
st.title("SNII Info TlachIA: Hub de la Ciencia Mexicana")
st.info("🚀 **Nota:** El sistema se encuentra en fase de desarrollo. Los datos se están cargando y procesando.")

# ---- Buscador Global (Neo4j Full-Text) ----
with st.container():
    col_search, col_stats = st.columns([3, 1])
    with col_search:
        global_query = st.text_input("🔍 Búsqueda Global", placeholder="Encuentra investigadores, facultades, institutos...", label_visibility="collapsed", disabled=not NEO4J_AVAILABLE)
    with col_stats:
        if NEO4J_AVAILABLE:
            st.caption("⚡ Búsqueda en Grafo Nacional")
        else:
            st.caption("🔌 Grafo no disponible")

    if NEO4J_AVAILABLE and global_query and len(global_query) >= 3:
        if st.session_state.get("last_global_query") != global_query:
            st.session_state.global_search_executed = False
            st.session_state.last_global_query = global_query

        neo = Neo4jGraphStore()
        search_results = neo.global_search(global_query)
        neo.close()
        
        if search_results:
            expanded_state = not st.session_state.get("global_search_executed", False)
            with st.expander(f"🎯 Resultados para '{global_query}'", expanded=expanded_state):
                for idx, res in enumerate(search_results):
                    c1, c2, c3 = st.columns([1, 4, 2])
                    with c1:
                        icon = "👤" if res['type'] == "Academic" else "🏢"
                        st.markdown(f"### {icon}")
                    with c2:
                        st.write(f"**{res['name']}**")
                        if res.get('parents'):
                            # Los nodos vienen del nivel inferior al superior. Invertimos para mostrar Institución ➔ Dependencia
                            breadcrumbs = " ➔ ".join(reversed(res['parents']))
                            st.caption(f"📍 {breadcrumbs}")
                        st.caption(f"Tipo: {res['type']} | Labels: {', '.join(res['labels'])}")
                    with c3:
                        if res['type'] == "Academic":
                            if st.button("Ver Detalle", key=f"global_res_{res['type']}_{res['id']}_{idx}", on_click=select_academic_in_ui, args=(res['name'],)):
                                st.success(f"✅ Seleccionado. Ve a la pestaña 'Perfil Académico'")
                        else:
                            if st.button("Ver Detalle", key=f"global_res_{res['type']}_{res['id']}_{idx}", on_click=select_entity_in_ui, args=(res['id'], res['name'], res['type'])):
                                st.success(f"✅ Seleccionado. Ve a la pestaña 'Panorama Institucional'")
        else:
            st.warning("No se encontraron coincidencias exactas. Intenta con un nombre más corto o apellidos.")

tab_labels = [
    "🌌 Inicio",
    "🏢 Panorama Institucional",
    "👤 Perfiles de Investigadores",
    "🗺️ Mapas de la Ciencia",
    "🤖 Asistente",
    # "🧪 Asistente-Prueba (MCP)",   # Oculta temporalmente
    # "🏛️ Consejo Estratégico",      # Oculta temporalmente
    "ℹ️ Acerca de..."
]

user_auth = st.session_state.get("authenticated_user")
if user_auth:
    tab_labels.insert(0, "👤 Mi Espacio")

all_tabs = st.tabs(tab_labels)
if user_auth:
    tab_me, tab_home, tab_inst, tab_inv, tab_maps, tab_chat, tab_about = all_tabs
else:
    tab_home, tab_inst, tab_inv, tab_maps, tab_chat, tab_about = all_tabs

# Pestañas ocultas temporalmente — se definen como None para evitar NameError
tab_test = None
tab_council = None

# --- Inyección de comportamiento de Sidebar según la Pestaña ---
import streamlit.components.v1 as components
components.html("""
<script>
    const parentDoc = window.parent.document;
    if (!parentDoc.window.__sidebarTabListenerAdded) {
        parentDoc.window.__sidebarTabListenerAdded = true;
        parentDoc.addEventListener('click', function(e) {
            let tab = e.target.closest('button[data-baseweb="tab"], div[role="tab"], button[role="tab"]');
            if (tab) {
                let tabText = tab.innerText || tab.textContent || "";
                let sidebar = parentDoc.querySelector('[data-testid="stSidebar"]');
                if (sidebar) {
                    let isExpanded = sidebar.getAttribute('aria-expanded') === 'true';
                    let openBtn = parentDoc.querySelector('[data-testid="collapsedControl"]');
                    
                    // En Streamlit moderno, el botón de cerrar tiene una clase SVG específica o data-testid
                    let closeBtn = sidebar.querySelector('[data-testid="baseButton-header"]') || 
                                   sidebar.querySelector('button'); 
                    
                    if (tabText.includes("Inicio") && isExpanded) {
                        if (closeBtn) closeBtn.click();
                    } else if (!tabText.includes("Inicio") && tabText.trim().length > 0 && !isExpanded) {
                        if (openBtn) openBtn.click();
                    }
                }
            }
        });
           const observer = new MutationObserver(() => {
            const activeTab = parentDoc.querySelector('button[data-baseweb="tab"]');
            if (!activeTab) return;
            const tabText = activeTab.innerText || activeTab.textContent || "";
            const sidebar = parentDoc.querySelector('[data-testid="stSidebar"]');
            if (!sidebar) return;
            const openBtn = parentDoc.querySelector('[data-testid="collapsedControl"]');
            const closeBtn = sidebar.querySelector('[data-testid="baseButton-header"]') || sidebar.querySelector('button');
            if (tabText.includes("Inicio")) {
                if (closeBtn) closeBtn.click();
            } else if (tabText.trim().length > 0) {
                if (openBtn) openBtn.click();
            }
        });
        observer.observe(parentDoc, { subtree: true, childList: true });
    }
</script>
""", height=0, width=0)

if "switch_tab" in st.session_state and st.session_state.switch_tab:
    import streamlit.components.v1 as components
    js_code = f"""
    <script>
    setTimeout(() => {{
        const tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"] p');
        for (let i = 0; i < tabs.length; i++) {{
            if (tabs[i].innerText.includes("{st.session_state.switch_tab}")) {{
                tabs[i].parentElement.click();
                break;
            }}
        }}
    }}, 500);
    </script>
    """
    components.html(js_code, height=0, width=0)
    st.session_state.switch_tab = None


# =======================================================
# TAB: Mi Espacio (Solo autenticados)
# =======================================================
if user_auth:
    with tab_me:
        st.header(f"Bienvenido, {user_auth.get('name', 'Investigador')}")
        st.markdown(f"**ORCID iD:** [{user_auth.get('orcid')}](https://orcid.org/{user_auth.get('orcid')})")
        
        neo = Neo4jGraphStore()
        profile = neo.get_user_profile(user_auth.get('orcid'))
        
        if profile and profile.get('academic_id'):
            neo.close()
            st.success(f"✅ Tu cuenta está vinculada al perfil académico: **{profile.get('academic_name')}**")
            
            if "queue_message" in st.session_state:
                st.info(st.session_state.queue_message)
                del st.session_state.queue_message
            else:
                st.info("💡 Ahora puedes ver tus métricas personalizadas y reportes de autoría.")
            
            # Botón de acceso directo a su vista
            if st.button("📊 Ver mi Producción y Métricas", on_click=select_academic_in_ui, args=(profile.get('academic_name'),)):
                st.success(f"✅ Seleccionado. Ve a la pestaña 'Perfil Académico'")
        else:
            if st.session_state.get('pending_claim_profile'):
                pending = st.session_state.pending_claim_profile
                res = pending['res']
                other_orcids_str = ", ".join(pending['other_orcids'])
                
                st.warning(f"⚠️ **Conflicto de ORCID Detectado**")
                st.write(f"Estás reclamando el perfil **{res['name']}** (ID: {res['id']}).")
                st.write(f"Nuestros datos previos (identificados mediante algoritmos de vinculación) asocian a esta persona con el/los ORCID: **{other_orcids_str}**.")
                st.write("¿Qué deseas hacer con el ORCID previo?")
                
                choice = st.radio(
                    "Selecciona una opción:",
                    [
                        f"El ORCID ({other_orcids_str}) es incorrecto y debe ser eliminado.",
                        f"Es otro ORCID mío y deseo conservarlo.",
                    ],
                    key="orcid_conflict_choice"
                )
                
                c_btn1, c_btn2 = st.columns([1, 1])
                with c_btn1:
                    if st.button("Confirmar Vinculación", type="primary"):
                        action = 'remove' if "incorrecto" in choice else 'keep'
                        
                        neo = Neo4jGraphStore()
                        neo.resolve_orcid_conflict_and_link(
                            new_orcid=user_auth['orcid'],
                            academic_id=res['id'],
                            conflict_orcids=pending['other_orcids'],
                            action=action,
                            user_name=user_auth.get('name')
                        )
                        neo.close()
                        
                        trigger_background_processing(res['name'], user_auth['orcid'])
                        
                        del st.session_state.pending_claim_profile
                        st.session_state.queue_message = "⏳ Hemos iniciado la descarga de tu producción y el cálculo de tus métricas en segundo plano. Esto puede tardar un par de minutos en verse reflejado en tu dashboard."
                        st.rerun()
                with c_btn2:
                    if st.button("Cancelar"):
                        del st.session_state.pending_claim_profile
                        st.rerun()
            else:
                # FLUJO DE AUTO-DETECCIÓN: ¿Ya tenemos este ORCID en el padrón?
                suggested_match = neo.find_academic_by_orcid(user_auth['orcid'])
                neo.close()
                
                if suggested_match:
                    st.info(f"✨ **¡Te hemos identificado!** Encontramos un perfil en el padrón que coincide con tu ORCID.")
                    col_m1, col_m2 = st.columns([3, 1])
                    with col_m1:
                        st.write(f"**{suggested_match['name']}**")
                        st.caption(f"ID: {suggested_match['id']}")
                    with col_m2:
                        if st.button("Sí, soy yo", key="confirm_auto_match"):
                            neo_local = Neo4jGraphStore()
                            neo_local.upsert_user(user_auth['orcid'], user_auth['name'])
                            neo_local.link_user_to_academic(user_auth['orcid'], suggested_match['id'])
                            neo_local.close()
                            
                            # Disparar procesamiento en tiempo real
                            trigger_background_processing(suggested_match['name'], user_auth['orcid'])
                            
                            st.session_state.queue_message = "⏳ Perfil vinculado con éxito. Hemos iniciado la descarga de tu producción y el cálculo de tus métricas en segundo plano. Esto puede tardar unos minutos en verse reflejado."
                            st.rerun()
                    st.write("---")
                    st.write("¿No eres tú? Puedes buscar tu perfil manualmente a continuación:")
                else:
                    st.warning("⚠️ Tu cuenta aún no está vinculada a un perfil del padrón institucional.")
                    st.write("Vincular tu perfil nos permite ofrecerte análisis precisos de tu producción científica.")
                
                with st.expander("🔍 Vincular mi Identidad Digital (Manual)", expanded=not suggested_match):
                    st.write("Busca tu nombre en el padrón para vincular tu ORCID verificado.")
                    search_query_me = st.text_input("Buscar mi nombre en el padrón:", placeholder="Ej: Carrillo Calvet", key="search_me")
                    
                    if search_query_me:
                        neo = Neo4jGraphStore()
                        with neo.driver.session() as session:
                            q_search = """
                            MATCH (a:Person)
                            WHERE a.fullname CONTAINS $q OR a.id CONTAINS $q
                            RETURN a.id as id, a.fullname as name, a.orcid as existing_orcid, a.orcids as existing_orcids
                            LIMIT 5
                            """
                            results = session.run(q_search, q=search_query_me.upper()).data()
                        neo.close()
                        
                        if results:
                            for res in results:
                                col1, col2 = st.columns([3, 1])
                                
                                # Extraer lista de ORCIDs existentes
                                existing_orcids_list = res.get('existing_orcids') or []
                                if isinstance(existing_orcids_list, str):
                                    existing_orcids_list = [existing_orcids_list]
                                elif not isinstance(existing_orcids_list, list):
                                    existing_orcids_list = []
                                
                                if res.get('existing_orcid') and res.get('existing_orcid') not in existing_orcids_list:
                                    existing_orcids_list.append(res['existing_orcid'])
                                    
                                orcid_display = ", ".join(existing_orcids_list) if existing_orcids_list else 'Ninguno'
                                
                                with col1:
                                    st.write(f"**{res['name']}**")
                                    st.caption(f"ID: {res['id']} | ORCID previo: {orcid_display}")
                                with col2:
                                    if st.button("Este soy yo", key=f"claim_me_{res['id']}"):
                                        # Determinar si hay conflicto
                                        other_orcids = [o for o in existing_orcids_list if o and o != user_auth['orcid']]
                                        
                                        if other_orcids:
                                            st.session_state.pending_claim_profile = {
                                                'res': res,
                                                'other_orcids': other_orcids
                                            }
                                            st.rerun()
                                        else:
                                            neo = Neo4jGraphStore()
                                            neo.upsert_user(user_auth['orcid'], user_auth['name'])
                                            neo.link_user_to_academic(user_auth['orcid'], res['id'])
                                            neo.close()
                                            
                                            # Disparar procesamiento en tiempo real
                                            trigger_background_processing(res['name'], user_auth['orcid'])
                                            
                                            st.session_state.queue_message = "⏳ Hemos iniciado la descarga de tu producción y el cálculo de tus métricas en segundo plano. Esto puede tardar un par de minutos en verse reflejado en tu dashboard."
                                            st.rerun()
                        else:
                            st.info("No te encontramos? Prueba buscando solo tu primer apellido o ID de OpenAlex.")
                            if st.button("Solicitar nuevo registro"):
                                st.write("Formulario de registro en desarrollo...")


# =======================================================
# TAB: Consejo Estratégico Virtual
# =======================================================
if tab_council is not None:
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
        # Usamos la entidad seleccionada en el sidebar como opción principal
        council_entity = st.selectbox(
            "Entidad objetivo",
            [selected_entity],
            index=0,
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
# TAB: Mapas de la Ciencia (Deepscatter)
# =======================================================
if tab_maps is not None:
    with tab_maps:
        from dashboard_maps import render_maps_view
        render_maps_view()




# =======================================================
# TAB 1: Chat RAG Orquestador & Interpreter
# =======================================================
with tab_chat:
    
    st.markdown("### Asistente Científico")
    # Oculto temporalmente: st.radio para elegir entre Reactivo y Analítico
    assistant_type = "⚡ Reactivo (Respuestas Rápidas)"
    
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
if tab_test is not None:
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
with tab_home:
    # El mapa se mostrará sin título ni textos superiores
    
    # Renderizamos el mapa de artículos como iframe a pantalla completa
    # Usamos components.html con JS que calcula la altura dinámica del viewport
    import streamlit.components.v1 as components
    iframe_url = "https://dinamica1.fciencias.unam.mx/tiles/map.html?v=26&demo=true&data=https://dinamica1.fciencias.unam.mx/tiles/articles_data.json?v=26"
    
    # HTML + JS que calcula la altura disponible restando la posición del iframe
    map_html = f"""
    <div id="map-container" style="width:100%; overflow:hidden;">
        <iframe id="map-iframe" src="{iframe_url}" 
                style="width:100%; border:none; display:block;" 
                scrolling="no">
        </iframe>
    </div>
    <script>
        function resizeMap() {{
            var iframe = document.getElementById('map-iframe');
            var container = document.getElementById('map-container');
            // Altura del viewport menos la posición vertical del iframe menos un pequeño margen para el footer
            var rect = container.getBoundingClientRect();
            var availableHeight = window.innerHeight - rect.top - 10;
            if (availableHeight < 400) availableHeight = 400; // mínimo razonable
            iframe.style.height = availableHeight + 'px';
        }}
        resizeMap();
        window.addEventListener('resize', resizeMap);
        // Reintentar tras un breve delay por si Streamlit aún no terminó de renderizar
        setTimeout(resizeMap, 300);
        setTimeout(resizeMap, 1000);
    </script>
    """
    with st.spinner("Cargando la galaxia del conocimiento..."):
        components.html(map_html, height=1080, scrolling=False)


with tab_inst:
    if not st.session_state.get('tab_inst_loaded', False):
        st.markdown("### 🏢 Panorama Institucional")
        st.info("📊 Esta vista analiza la producción de la entidad seleccionada. Haz clic en **Cargar** para comenzar.")
        if st.button("▶️ Cargar Panorama Institucional", use_container_width=True, key="load_tab_inst"):
            st.session_state['tab_inst_loaded'] = True
            st.rerun()
    else:
        st.markdown("### 📊 Perspectiva Analítica")
        view_mode_inst = st.radio(
            "Vista",
            ["Capacidad Instalada", "Producción Institucional"],
            index=0,
            horizontal=True,
            help="Capacidad Instalada: Suma de la producción de los académicos adscritos a la institución.\nProducción Institucional: Papers cargados manualmente o identificados via openalex id o ROR.",
            key="view_mode_inst_tab"
        )
        v_mode_inst_code = "capacidad_instalada" if view_mode_inst == "Capacidad Instalada" else "produccion_institucional"
        # Determinar el padre (Dependencia) si estamos viendo una Subdependencia
        parent = selected_dep if selected_sub and selected_entity == selected_sub else None
        
        render_institucion_view(selected_entity, institution_name=selected_institution, view_mode=v_mode_inst_code, parent_name=parent)

# =======================================================
# TAB 3: Vista por Investigador
# =======================================================
with tab_inv:
    if not st.session_state.get('tab_inv_loaded', False):
        st.markdown("### 👤 Perfiles de Investigadores")
        st.info("🔍 Esta vista carga el perfil completo del investigador seleccionado. Haz clic en **Cargar** para comenzar.")
        if st.button("▶️ Cargar Perfil de Investigador", use_container_width=True, key="load_tab_inv"):
            st.session_state['tab_inv_loaded'] = True
            st.rerun()
    else:
        # La vista de investigador siempre es por Capacidad Instalada (sus propios papers)
        v_mode_inv_code = "capacidad_instalada"
        render_investigador_view(selected_entity, institution_name=selected_institution, view_mode=v_mode_inv_code)

# =======================================================

# =======================================================
# TAB 6: Acerca de / Estado DB
# =======================================================
with tab_about:
    st.info("""
        **Aviso de Privacidad y Fuentes de Datos**
        
        La información bibliométrica y de producción científica contenida en **SNII Info TlachIA** procede exclusivamente de fuentes de datos públicas y repositorios institucionales de acceso libre, incluyendo: **OpenAlex, Scopus, ORCID, SNII (CONAHCYT), SIIA (UNAM)** y otros catálogos académicos globales.
        
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
        st.markdown("#### FACULTAD DE CIENCIAS y CENTRO DE CIENCIAS DE LA COMPLEJIDAD (UNAM)")
        st.markdown("- Dr. Humberto Andrés Carrillo Calvet")
        st.markdown("- Dr. José Luis Jiménez Andrade")
        st.markdown("#### FACULTAD DE CIENCIAS")
        st.markdown("- Dra. María Victoria Guzmán Sánchez")
        
        st.markdown("####  CENTRO DE CIENCIAS DE LA COMPLEJIDAD")
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
        "✅ Con ROR identificado",
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
    st.markdown("Diagrama de Entidad-Relación que describe cómo se almacena la información estructurada de SNII Info TlachIA.")
    schema_mermaid = """
    erDiagram
        %% Entidades Principales
        Person ||--o{ Paper : ""
        Person }o--|| Subdependency : ""
        Person }o--|| Dependency : ""
        Person }o--|| Institution : ""
        
        %% Estructura Institucional
        Subdependency }o--|| Dependency : ""
        Dependency }o--|| Institution : ""
        Institution }o--|| State : ""
        Institution }o--|| Country : ""
        
        %% Vínculos Institucionales del Paper
        Paper }o--|| Institution : ""
        Institution ||--o{ Paper : ""
        Dependency ||--o{ Paper : ""
        
        %% Sistema Nacional de Investigadores (SNII)
        Person }o--|| Specialty : ""
        Specialty }o--|| Subdiscipline : ""
        Subdiscipline }o--|| Discipline : ""
        Discipline }o--|| KnowledgeArea : ""
        
        %% Taxonomía OpenAlex
        Paper }o--|| Topic : ""
        Topic }o--|| TopicSubfield : ""
        TopicSubfield }o--|| TopicField : ""
        TopicField }o--|| TopicDomain : ""
        
        %% Metadatos Extendidos
        Paper }o--|| SDG : ""
        Paper }o--|| Funder : ""
        Paper }o--|| Award : ""
        Paper }o--|| Concept : ""
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
    st.markdown("Este diagrama describe el flujo de datos global de **SNII Info TlachIA**, desde la recolección de metadatos hasta la Inteligencia Híbrida del Agente RAG.")
    
    mermaid_code = """
    graph TD
        A[Fuentes: OpenAlex, ORCID, SNII] --> B[Pipeline de Ingesta]
        
        B --> G[Neo4j: Knowledge Graph]
        B --> CH[ClickHouse: Motor Analítico OLAP]
        B -.-> H[Qdrant: Vector DB]
        
        CH --> I[Caché Local Parquet]
        I --> J[Dashboard de Analítica]
        
        J --> K[Vistas Institucional y Académico]
        
        H <--> O[Orquestador RAG]
        G <--> O
        CH <--> O
        
        O --> P[Local LLM]
        O --> Q[Neo4j Graph Tool]
        O --> R[Semantic Search Tool]
        O --> S[ClickHouse Analytics Tool]
        
        J --> O
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
        A[1. Padrón Oficial SNII / Excel] --> B[Lista Base Investigadores]
        B --> C[Enriquecimiento APIs]
        C --> D[OpenAlex]
        C --> E[ORCID / Scopus]
        
        D --> F[Procesamiento y Limpieza]
        E --> F
        
        F --> G[Neo4j: Grafos Relacionales]
        F --> CH[ClickHouse: Datos Tabulares]
        F --> Q[Qdrant: Embeddings Densos]
        
        CH --> Z[Cálculo de Métricas]
        Z --> Y[Exportación a Parquets para Dashboard]
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
        📊 SNII Info TlachIA - C1ε(η)C1α∫x - UNAM
    </div>
""", unsafe_allow_html=True)

# =======================================================
# WIDGET FLOTANTE: ASISTENTE CONTEXTUAL
# =======================================================
from utils.ui_context_collector import get_current_ui_context

st.markdown("""
<style>
/* El modal ya se centra solo. Puedes inyectar algo extra aquí si quieres */
</style>
""", unsafe_allow_html=True)

@st.dialog("💬 Asistente SNII Info TlachIA", width="large")
def explain_chart_dialog():
    c_title, c_clear = st.columns([0.8, 0.2])
    with c_title:
        st.markdown("#### Análisis en vivo")
        st.caption("Puedo leer las gráficas que ves y donde haces clic.")
    with c_clear:
        if st.button("🗑️ Limpiar", help="Borrar historial del asistente", type="tertiary"):
            if "chat_history" in st.session_state:
                st.session_state.chat_history = []
    
    # Indicador de selección activa
    active_selection = ""
    docs_sel = st.session_state.get("inst_annual_docs", {}) or st.session_state.get("inv_annual_docs", {})
    if docs_sel and docs_sel.get("selection", {}).get("points"):
        active_selection = "🎯 **Gráfica seleccionada:** Producción Histórica"
    fwci_sel = st.session_state.get("inst_annual_fwci", {})
    if fwci_sel and fwci_sel.get("selection", {}).get("points"):
        active_selection = "🎯 **Gráfica seleccionada:** Evolución FWCI"
    sunburst_sel = st.session_state.get("inst_sunburst", {}) or st.session_state.get("inv_sunburst", {})
    if sunburst_sel and sunburst_sel.get("selection", {}).get("points"):
        active_selection = "🎯 **Gráfica seleccionada:** Sunburst Temático"
        
    if active_selection:
        st.info(active_selection)
    
    float_container = st.container(height=350)
    
    # Mostrar historial (compartido con la pestaña principal)
    with float_container:
        if "chat_history" in st.session_state:
            for msg in st.session_state.chat_history[-6:]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    
    if float_prompt := st.chat_input("¿Qué quieres saber de esta vista?", key="dialog_chat_input"):
        import time
        now = time.time()
        last_msg = st.session_state.get("last_assistant_msg_time", 0)
        if now - last_msg < 3:
            st.toast("⏳ Por favor espera un momento antes de enviar otra consulta.", icon="⚠️")
        else:
            st.session_state.last_assistant_msg_time = now
            float_prompt = float_prompt[:1000]  # Limitar a máximo 1,000 caracteres
            if "chat_history" not in st.session_state:
                st.session_state.chat_history = []
            st.session_state.chat_history.append({"role": "user", "content": float_prompt})
            st.session_state.auto_run_float_assistant = float_prompt
        
    if st.session_state.get("auto_run_float_assistant"):
        current_prompt = st.session_state.auto_run_float_assistant
        st.session_state.auto_run_float_assistant = None
        
        with float_container:
            with st.chat_message("assistant"):
                placeholder = st.empty()
                placeholder.markdown("🔍 *Analizando pantalla...*")
                
                try:
                    ui_ctx = get_current_ui_context()
                    orchestrator = st.session_state.orchestrator
                    session_id = st.session_state.session_id
                    
                    placeholder.empty()
                    response = st.write_stream(orchestrator.ask_lightweight_stream_sync(session_id, current_prompt, ui_ctx))
                    
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": response
                    })
                except Exception as e:
                    placeholder.error(f"Error: {e}")

# === AUTO-TRIGGER EXPLICAR GRÁFICA / INDICADOR ===
if "trigger_explain_chart" in st.session_state and st.session_state.trigger_explain_chart:
    chart_name = st.session_state.trigger_explain_chart
    chart_data = st.session_state.get("trigger_explain_data", None)
    
    st.session_state.trigger_explain_chart = None
    st.session_state.trigger_explain_data = None
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
        
    msg = f"💡 Por favor dame un análisis breve e interpretación de este elemento: **{chart_name}**."
    if chart_data:
        msg += f"\n\nLos datos actuales en pantalla son:\n```\n{chart_data}\n```\n\nExplícame contextualmente qué significan estas tendencias o valores."
    else:
        msg += "\n\nExplícame contextualmente qué significa y por qué es relevante."
        
    st.session_state.chat_history.append({"role": "user", "content": msg})
    st.session_state.auto_run_float_assistant = msg
    
    explain_chart_dialog()
