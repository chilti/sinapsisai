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

# Add sos-mcp-services extra site-packages if available
VENV_SITE_PACKAGES = "/home/jlja/venv_sos_mcp/lib/python3.12/site-packages"
if os.path.exists(VENV_SITE_PACKAGES) and VENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_SITE_PACKAGES)

from lib.llm_utils import LLMConfig
from agent.skill_manager import skill_manager
from agent.tools_interpreter import structured_analytics_tools
from agent.tools_hybrid import hybrid_tools

# Smolagents import
try:
    from smolagents import CodeAgent, ToolCallingAgent, OpenAIServerModel, tool as smol_tool, Tool as SmolTool
    HAS_SMOLAGENTS = True
except ImportError:
    HAS_SMOLAGENTS = False


# ============================================================================
# Wrapped Tools for Smolagents
# ============================================================================
def create_smol_tools() -> List[Any]:
    """Converts local tools into smolagents-compatible tools."""
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
        
        # 1. Match and inject relevant skills
        if active_skills:
            skill_prompt = self.skill_mgr.get_skill_instructions(active_skills)
            matched_skills = [self.skill_mgr.skills[s] for s in active_skills if s in self.skill_mgr.skills]
        else:
            matched_skills = self.skill_mgr.match_skills(research_question, top_k=2)
            skill_prompt = self.skill_mgr.get_skill_instructions([s.name for s in matched_skills])
            
        skills_used = [s.name for s in matched_skills]
        
        # 2. Build system instructions
        base_system_prompt = f"""Eres el Agente Científico Autónomo de Info TlachIA y del Ecosistema de Inteligencia Científica (SECIHTI/SNII).
Tu objetivo es resolver investigaciones cienciométricas complejas mediante un enfoque riguroso, multi-paso y fundamentado en evidencia.

{skill_prompt}

DIRECTRICES:
1. Formula un plan de análisis claro antes de consultar datos.
2. Utiliza las herramientas analíticas para obtener datos empíricos de ClickHouse, Parquet y Grafos.
3. Procesa y resume los resultados con métricas bibliométricas normalizadas (FWCI, H-index, Leyes de Bradford/Lotka, etc.).
4. Si se te proporciona un contexto de entidad o investigador, úsalo prioritariamente: {entity_context if entity_context else 'Nacional / Global'}.
5. Genera un reporte final estructurado con síntesis ejecutiva, tablas y conclusiones cienciométricas.
"""
        
        if not HAS_SMOLAGENTS or self.model is None:
            return {
                "answer": "Error: smolagents no está disponible. Usa el Asistente Público (Tier 1).",
                "steps": [],
                "skills_used": skills_used,
                "duration_seconds": round(time.time() - start_time, 2)
            }
            
        try:
            # Build CodeAgent with authorized scientific imports
            agent = CodeAgent(
                tools=self.tools,
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

            return {
                "answer": str(result),
                "steps": reasoning_steps,
                "skills_used": skills_used,
                "status": "success",
                "duration_seconds": round(time.time() - start_time, 2)
            }
        except Exception as e:
            return {
                "answer": f"Ocurrió un error durante la investigación autónoma: {str(e)}",
                "steps": [],
                "skills_used": skills_used,
                "status": "error",
                "duration_seconds": round(time.time() - start_time, 2)
            }
