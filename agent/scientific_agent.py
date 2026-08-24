"""
scientific_agent.py - Autonomous Scientific Research Agent (Tier 2 Admin)
Powered by Smolagents (Hugging Face) with AST Sandboxed Code Execution,
Dynamic Skill Injection from sos-mcp-services, and deterministic analytical tools.
"""
import os
import sys
import json
import time
from typing import Dict, Any, List, Optional

# Add parent path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, BASE_DIR)

# Add sos-mcp-services extra site-packages and agent path if available
VENV_SITE_PACKAGES = "/home/jlja/venv_sos_mcp/lib/python3.12/site-packages"
if os.path.exists(VENV_SITE_PACKAGES) and VENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_SITE_PACKAGES)

SOS_MCP_PATH = "/mnt/expansion/desplegados/sos-mcp-services"
if os.path.exists(SOS_MCP_PATH) and SOS_MCP_PATH not in sys.path:
    sys.path.insert(0, SOS_MCP_PATH)

from lib.llm_utils import LLMConfig
from agent.skill_manager import skill_manager
from agent.artifact_manager import artifact_manager
from agent.tools_interpreter import structured_analytics_tools
from agent.tools_hybrid import hybrid_tools

# Smolagents & Swarm import
try:
    from smolagents import CodeAgent, ToolCallingAgent, OpenAIServerModel, tool as smol_tool, Tool as SmolTool
    HAS_SMOLAGENTS = True
except ImportError:
    HAS_SMOLAGENTS = False

try:
    from agent.swarm import ScientificSwarm
    HAS_SWARM = True
except ImportError:
    HAS_SWARM = False


# ============================================================================
# Wrapped Tools for Smolagents
# ============================================================================
def create_smol_tools(emitted_artifacts_list: Optional[List[Dict[str, Any]]] = None) -> List[Any]:
    """Converts local tools into smolagents-compatible tools with artifact emission support."""
    tools = []
    
    # 1. Query Academic Cache
    @smol_tool
    def query_academic_data(table_type: str, institution: str = "", academic: str = "", sort_by: str = "", top_n: int = 10) -> str:
        """
        Consulta tablas estructuradas de métricas científicas locales (Parquet).
        Args:
            table_type: Tipo de tabla ('institucion_annual', 'investigador_annual', 'papers_profesor', 'topics', 'umap_investigadores').
            institution: Nombre de la institución (ej. 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO').
            academic: Nombre del académico o investigador.
            sort_by: Columna para ordenar (ej. 'fwci', 'num_documents', 'citations').
            top_n: Máximo número de filas a devolver (default: 10).
        """
        from agent.tools_interpreter import query_academic_cache
        inst = institution if institution else None
        ac = academic if academic else None
        sb = sort_by if sort_by else None
        return query_academic_cache.invoke({
            'table_type': table_type,
            'institution': inst,
            'academic': ac,
            'sort_by': sb,
            'top_n': top_n
        })
    tools.append(query_academic_data)

    # 2. ClickHouse SQL Analytics
    @smol_tool
    def query_clickhouse_sql(sql_query: str) -> str:
        """
        Ejecuta consultas analíticas SQL en ClickHouse sobre producción científica y citas.
        Args:
            sql_query: Consulta SQL que comience con SELECT (solo lectura).
        """
        from agent.tools_interpreter import query_clickhouse_safe_sql
        return query_clickhouse_safe_sql.invoke({'sql_query': sql_query})
    tools.append(query_clickhouse_sql)

    # 3. Scientometric Summary
    @smol_tool
    def get_researcher_profile(academic_name: str, institution_name: str = "") -> str:
        """
        Obtiene el resumen consolidado de impacto de un investigador (FWCI, H-index, Citas, % OA Diamante).
        Args:
            academic_name: Nombre completo del investigador.
            institution_name: Institución de filiación (opcional).
        """
        from agent.tools_interpreter import get_scientometric_summary
        inst = institution_name if institution_name else None
        return get_scientometric_summary.invoke({'academic_name': academic_name, 'institution_name': inst})
    tools.append(get_researcher_profile)

    # 4. Emit Scientific Visual Artifact
    @smol_tool
    def emit_scientific_artifact(artifact_id: str, title: str, data: dict) -> str:
        """
        Renderiza un artefacto visual interactivo para el usuario (mallas SOM, redes Louvain, mapas UMAP, frentes de investigación, diplomacia científica, leyes bibliométricas, reportes ejecutivos).
        Args:
            artifact_id: Identificador del artefacto ('som-hexagonal-mesh', 'bibliometric-force-network', 'umap-density-contours', 'research-fronts-evolution', 'geopolitical-science-map', 'bibliometric-laws-curves', 'journal-benchmark-matrix', 'institutional-benchmarking-profile', 'graphrag-entity-subgraph', 'scientific-executive-report').
            title: Título descriptivo de la visualización.
            data: Diccionario con la estructura de datos requerida por el artefacto.
        """
        rendered_html = artifact_manager.render_artifact(artifact_id, data, title=title)
        if rendered_html:
            if emitted_artifacts_list is not None:
                emitted_artifacts_list.append({
                    "artifact_id": artifact_id,
                    "title": title,
                    "data": data,
                    "html": rendered_html
                })
            return f"✅ Artefacto visual interactivo '{title}' ({artifact_id}) generado y renderizado exitosamente para el usuario."
        return f"❌ Error: Artefacto '{artifact_id}' no encontrado en el catálogo de artefactos."
    tools.append(emit_scientific_artifact)

    return tools


# ============================================================================
# Autonomous Scientific Agent Class
# ============================================================================
class AutonomousScientificAgent:
    def __init__(self, mode: str = "code_agent"):
        """
        Initializes the Autonomous Scientific Research Agent.
        mode: 'code_agent' (writes & runs Python in AST sandbox) or 'tool_agent' (pure tool calling).
        """
        self.mode = mode
        self.auth_url = LLMConfig.get_auth_url()
        self.model_id = LLMConfig.get_model_name()
        self.api_key = LLMConfig.get_api_key()
        self.skill_mgr = skill_manager
        
        if not HAS_SMOLAGENTS:
            print("Notice: smolagents is not installed. Agent will run in fallback mode.")
            self.agent = None
            return

        # Model configuration
        self.model = OpenAIServerModel(
            model_id=self.model_id,
            api_base=self.auth_url,
            api_key=self.api_key
        )
        self.tools = create_smol_tools()

    def run_investigation(
        self,
        research_question: str,
        active_skills: Optional[List[str]] = None,
        entity_context: Optional[str] = None,
        max_steps: int = 10
    ) -> Dict[str, Any]:
        """
        Executes an autonomous multi-step scientific investigation.
        """
        start_time = time.time()

        # Enjambre Multi-Agente Científico (Scientific Swarm) si está disponible
        if HAS_SWARM:
            swarm = ScientificSwarm(
                system_namespace="infotlachia",
                model_id=self.model_id,
                api_base=self.auth_url,
                api_key=self.api_key
            )
            swarm_res = swarm.run_investigation(
                research_question=research_question,
                active_skills=active_skills,
                entity_context=entity_context
            )
            reasoning_steps = []
            for d in swarm_res.get("dag_steps", []):
                reasoning_steps.append({
                    "type": "thought",
                    "name": f"🏛️ {d.get('agent', 'Swarm')}: {d.get('phase', 'Fase')}",
                    "content": f"Estado: {d.get('status', 'OK')} | {d.get('details', d.get('verdict', ''))}"
                })
            
            return {
                "answer": swarm_res.get("answer", ""),
                "steps": reasoning_steps,
                "skills_used": swarm_res.get("skills_used", []),
                "artifacts": swarm_res.get("artifacts", []),
                "critic_verdict": swarm_res.get("critic_verdict", {}),
                "iterations": swarm_res.get("iterations", 1),
                "provenance": swarm_res.get("provenance", []),
                "status": swarm_res.get("status", "success"),
                "duration_seconds": swarm_res.get("duration_seconds", round(time.time() - start_time, 2))
            }
        
        # Modo fallback CodeAgent standalone
        # 1. Match and inject relevant skills
        if active_skills:
            skill_prompt = self.skill_mgr.get_skill_instructions(active_skills)
            matched_skills = [self.skill_mgr.skills[s] for s in active_skills if s in self.skill_mgr.skills]
        else:
            matched_skills = self.skill_mgr.match_skills(research_question, top_k=2)
            skill_prompt = self.skill_mgr.get_skill_instructions([s.name for s in matched_skills])
            
        skills_used = [s.name for s in matched_skills]
        
        # 2. Build system instructions with skills and artifacts catalog
        artifacts_prompt = artifact_manager.get_artifacts_prompt()
        base_system_prompt = f"""Eres el Agente Científico Autónomo de Info TlachIA y del Ecosistema de Inteligencia Científica (SECIHTI/SNII).
Tu objetivo es resolver investigaciones cienciométricas complejas mediante un enfoque riguroso, multi-paso y fundamentado en evidencia.

{skill_prompt}

{artifacts_prompt}

DIRECTRICES:
1. Formula un plan de análisis claro antes de consultar datos.
2. Utiliza las herramientas analíticas para obtener datos empíricos de ClickHouse, Parquet y Grafos.
3. Procesa y resume los resultados con métricas bibliométricas normalizadas (FWCI, H-index, Leyes de Bradford/Lotka, etc.).
4. Si se te proporciona un contexto de entidad o investigador, úsalo prioritariamente: {entity_context if entity_context else 'Nacional / Global'}.
5. Si la consulta involucra topología SOM, redes de coautoría, densidades UMAP, frentes de investigación, geopolítica o leyes bibliométricas, GENERA EL ARTEFACTO VISUAL correspondiente usando `emit_scientific_artifact`.
6. Genera un reporte final estructurado con síntesis ejecutiva, tablas y conclusiones cienciométricas.
"""
        
        if not HAS_SMOLAGENTS or self.model is None:
            return {
                "answer": "Error: smolagents no está disponible. Usa el Asistente Público (Tier 1).",
                "steps": [],
                "skills_used": skills_used,
                "artifacts": [],
                "duration_seconds": round(time.time() - start_time, 2)
            }
            
        try:
            # Emitted artifacts collector for this run
            emitted_artifacts = []
            run_tools = create_smol_tools(emitted_artifacts)

            # Build CodeAgent with authorized scientific imports
            agent = CodeAgent(
                tools=run_tools,
                model=self.model,
                additional_authorized_imports=['pandas', 'numpy', 'scipy', 'networkx', 'math', 'json', 're', 'datetime'],
                max_steps=max_steps
            )
            
            full_prompt = f"{base_system_prompt}\n\nPREGUNTA DE INVESTIGACIÓN:\n{research_question}"
            result = agent.run(full_prompt)
            
            # Extraer pasos estructurados de razonamiento y herramientas ejecutadas
            reasoning_steps = []
            if hasattr(agent, 'memory') and hasattr(agent.memory, 'steps'):
                for step in agent.memory.steps:
                    if step.__class__.__name__ == 'ActionStep':
                        step_num = getattr(step, 'step_number', 1)
                        
                        # 1. Pensamiento del modelo
                        thought = getattr(step, 'model_output', None)
                        if thought:
                            reasoning_steps.append({
                                'type': 'thought',
                                'name': f'Paso {step_num}',
                                'content': str(thought)
                            })
                        
                        # 2. Llamadas a herramientas o ejecución de código Python
                        code = getattr(step, 'code_action', None)
                        tool_calls = getattr(step, 'tool_calls', None)
                        if tool_calls:
                            for tc in tool_calls:
                                reasoning_steps.append({
                                    'type': 'tool_call',
                                    'name': getattr(tc, 'name', 'tool'),
                                    'args': getattr(tc, 'arguments', {})
                                })
                        elif code:
                            reasoning_steps.append({
                                'type': 'tool_call',
                                'name': f'Python Sandbox [Paso {step_num}]',
                                'args': {'code': str(code)}
                            })
                            
                        # 3. Observaciones y resultados
                        obs = getattr(step, 'observations', None)
                        if obs:
                            reasoning_steps.append({
                                'type': 'tool_result',
                                'name': f'Salida [Paso {step_num}]',
                                'content': str(obs)
                            })

            # Si no se emitieron artefactos vía herramienta, auto-detectar desde el texto de respuesta
            if not emitted_artifacts and result:
                detected_artifacts = artifact_manager.detect_and_render_artifacts_from_text(str(result))
                if detected_artifacts:
                    emitted_artifacts.extend(detected_artifacts)

            return {
                "answer": str(result),
                "steps": reasoning_steps,
                "skills_used": skills_used,
                "artifacts": emitted_artifacts,
                "status": "success",
                "duration_seconds": round(time.time() - start_time, 2)
            }
        except Exception as e:
            return {
                "answer": f"Ocurrió un error durante la investigación autónoma: {str(e)}",
                "steps": [],
                "skills_used": skills_used,
                "artifacts": [],
                "status": "error",
                "duration_seconds": round(time.time() - start_time, 2)
            }
