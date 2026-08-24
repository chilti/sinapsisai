"""
base_agent.py - Clase base para agentes especialistas del enjambre científico
"""
import os
import sys
import json
import time
from typing import Dict, Any, List, Optional

# Add site-packages
VENV_SITE_PACKAGES = "/home/jlja/venv_sos_mcp/lib/python3.12/site-packages"
if os.path.exists(VENV_SITE_PACKAGES) and VENV_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, VENV_SITE_PACKAGES)

try:
    from smolagents import CodeAgent, OpenAIServerModel, tool
    HAS_SMOLAGENTS = True
except ImportError:
    HAS_SMOLAGENTS = False


class BaseSpecialistAgent:
    """Clase base para cualquier agente especialista del Enjambre Científico."""
    def __init__(
        self,
        name: str,
        role_description: str,
        tools: List[Any],
        model_id: str = "local-model",
        api_base: str = "http://127.0.0.1:1234/v1/",
        api_key: str = "lm-studio",
        max_steps: int = 6
    ):
        self.name = name
        self.role_description = role_description
        self.tools = tools
        self.max_steps = max_steps
        self.model_id = model_id
        self.api_base = api_base
        self.api_key = api_key
        
        self.model = None
        if HAS_SMOLAGENTS:
            self.model = OpenAIServerModel(
                model_id=self.model_id,
                api_base=self.api_base,
                api_key=self.api_key
            )

    def execute_task(self, task_instruction: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ejecuta una subtarea especializada dentro del sandbox de código AST."""
        start_time = time.time()
        if not HAS_SMOLAGENTS or self.model is None:
            return {
                "agent": self.name,
                "status": "error",
                "output": "Error: smolagents no está disponible en el entorno.",
                "duration": round(time.time() - start_time, 2)
            }

        prompt = f"""Eres el agente especialista: {self.name}.
ROL: {self.role_description}

CONTEXTO DISPONIBLE:
{json.dumps(context, indent=2, ensure_ascii=False) if context else 'Sin contexto previo.'}

INSTRUCCIÓN ESPECÍFICA:
{task_instruction}

REGLA DE FORMATO OBLIGATORIA:
Para ejecutar herramientas o dar tu respuesta final, escribe código Python dentro de bloques <code>...</code>.
Cuando tengas tu respuesta lista, utiliza:
<code>
final_answer("Tu informe y síntesis técnica aquí...")
</code>
"""
        try:
            agent = CodeAgent(
                tools=self.tools,
                model=self.model,
                additional_authorized_imports=['pandas', 'numpy', 'scipy', 'networkx', 'math', 'json', 're', 'datetime'],
                max_steps=self.max_steps
            )
            result = agent.run(prompt)
            return {
                "agent": self.name,
                "status": "success",
                "output": str(result),
                "duration": round(time.time() - start_time, 2)
            }
        except Exception as e:
            return {
                "agent": self.name,
                "status": "error",
                "output": f"Error en ejecución de {self.name}: {str(e)}",
                "duration": round(time.time() - start_time, 2)
            }
