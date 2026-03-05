import asyncio
import re
import os
import io
import json
from agent.memory_manager import SessionMemoryManager

try:
    from interpreter import interpreter
    import interpreter.core.core
except ImportError:
    interpreter = None

class InterpreterOrchestrator:
    def __init__(self, memory_manager: SessionMemoryManager):
        self.memory = memory_manager
        
        # Configure the open interpreter instance
        if interpreter:
            self.interpreter = interpreter.core.core.OpenInterpreter()
            
            # Cargamos configuración de LLM desde el entorno (igual que RAGOrchestrator)
            base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
            model_id = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
            api_key = os.getenv("OPENAI_API_KEY", "lm-studio")
            user = os.getenv("LLM_USER")
            password = os.getenv("LLM_PASSWORD")

            # Construir URL con Basic Auth si es necesario
            auth_url = base_url
            if user and password:
                if "://" in base_url:
                    protocol, rest = base_url.split("://", 1)
                    auth_url = f"{protocol}://{user}:{password}@{rest}"
                else:
                    auth_url = f"http://{user}:{password}@{base_url}"

            # Para que litellm (usado por OI) envíe EXACTAMENTE el model_id al servidor OpenAI-compatible,
            # debemos prefijar el proveedor. Si queremos enviar 'openai/gpt-oss-20b', 
            # litellm necesita 'openai/openai/gpt-oss-20b'.
            # Si el model_id no tiene slash, con una vez basta: 'openai/mi-modelo'.
            self.interpreter.llm.model = f"openai/{model_id}"
            self.interpreter.llm.api_base = auth_url
            self.interpreter.llm.api_key = api_key
            
            # Forzar a usar lenguaje natural y bloques de código (no Function Calling nativo)
            # Esto es más robusto para modelos locales/costomizados
            self.interpreter.llm.supports_functions = False
            
            # Disable confirmation to run autonomously
            self.interpreter.auto_run = True
            # Limit steps to prevent infinite loops
            self.interpreter.max_steps = 15
            self.interpreter.offline = False 
            self.interpreter.safe_mode = "off"
            
            # SOBRESCRIBIR mensaje del sistema para mayor control en modelos locales
            self.interpreter.system_message = """
            Eres un agente 'Plan-and-Execute' de Sinapsis AI, experto en análisis de datos científicos y cienciometría.
            Tu misión es analizar la producción científica escribiendo y ejecutando código Python de manera iterativa.

            REGLAS DE FORMATO (ESTRICTAS Y OBLIGATORIAS):
            1. UTILIZA ÚNICAMENTE Markdown estándar.
            2. PROHIBIDO: NO uses etiquetas como <|channel|>, <|thought|>, <|message|>, o similares. NUNCA.
            3. Para ejecutar código Python, utiliza bloques de código markdown: ```python [tu código] ```
            4. Para ver resultados, utiliza SIEMPRE print(). Los valores no impresos NO serán visibles.

            ESTRATEGIA DE DATOS:
            1. PRIORIDAD CACHE: Si el análisis es sobre una institución o un profesor, CARGA el archivo parquet correspondiente:
               - data/cache/papers_institucion.parquet (Columnas: entity_name, title, year, citations, etc.)
               - data/cache/papers_profesor.parquet (Si buscas un autor específico)
            2. GRAFO: Usa 'agent.tools_hybrid.query_knowledge_graph_cypher' para relaciones complejas.
            
            EJEMPLO DE EJECUCIÓN EXITOSA:
            Voy a filtrar los artículos de la facultad en los parquets.
            ```python
            import pandas as pd
            df = pd.read_parquet('data/cache/papers_institucion.parquet')
            # Análisis aquí...
            print(df.head())
            ```

            AVISO: Cualquier intento de usar <|channel|> resultará en un fallo del sistema. Escribe SOLO Python en bloques de código.
            """

    async def ask(self, session_id: str, prompt: str, mode: str = "plan_and_execute", entity_context: str = None):
        """
        Ejecuta open-interpreter de manera autónoma.
        mode: 
          - 'plan_and_execute': Resuelve el prompt iterando (escribe código, corre, repite).
          - 'plan_only': Instruye al intérprete a solo generar un plan.
          - 'execute_plan': Se asume que el prompt ya contiene el plan detallado a ejecutar.
        """
        if not interpreter:
            return {"answer": "Error: open-interpreter no está instalado. Ejecuta `pip install open-interpreter`.", "intermediate_steps": []}

        # Adjust prompt based on mode
        full_prompt = prompt
        if mode == "plan_only":
            full_prompt = f"POR FAVOR, SOLO GENERA UN PLAN DE ACCIÓN PASO A PASO PARA LO SIGUIENTE Y NO EJECUTES NINGÚN CÓDIGO TODAVÍA:\n\n{prompt}"
        elif mode == "execute_plan":
            full_prompt = f"EJECUTA ESTE PLAN PASO A PASO ESCRIBIENDO Y CORRIENDO CÓDIGO PYTHON:\n\n{prompt}"
            
        if entity_context:
            full_prompt = f"[Contexto actual: {entity_context}]\n" + full_prompt

        # Restore past messages for this session
        past_msgs = self.memory.get_history(session_id, limit=20)
        # OpenInterpreter format: [{"role": "user"/"assistant", "type": "message", "content": "..."}]
        interpreter_msgs = []
        for m in past_msgs:
            role = m.get("role", "user")
            content = m.get("content", "")
            
            # Sanitizar contenido: Si el historial tiene tags <|channel|>, convertirlos a bloques de código
            # para que el modelo no imite el formato incorrecto.
            if "<|channel|>" in content:
                # Intenta extraer la llamada si parece JSON
                try:
                    # Regex para capturar el tag y lo que parece ser el argumento
                    match = re.search(r"<\|channel\|>.*?code<\|message\|>(.*)", content, re.DOTALL)
                    if match:
                        code_cand = match.group(1).strip()
                        # Si parece JSON, lo convertimos a algo legible o simplemente bloque python
                        content = f"Análisis previo (sanitizado):\n```python\n# El modelo anterior usó formato incorrecto. \n# Contenido original: {code_cand}\n```"
                except:
                    content = content.replace("<|channel|>", "[TAG PROHIBIDO ELIMINADO]")

            # Convert roles if necessary
            if role == "human": role = "user"
            if role == "ai": role = "assistant"
            interpreter_msgs.append({"role": role, "type": "message", "content": content})
        
        self.interpreter.messages = interpreter_msgs

        # Capture output
        intermediate_steps = []
        final_answer = ""
        
        try:
            # We use generator to capture chunks
            for chunk in self.interpreter.chat(full_prompt, stream=True, display=False):
                # chunk format: {'role': 'assistant', 'type': 'message'/'code'/'console', 'content': '...', 'start': True, 'end': True}
                
                if "type" in chunk:
                    # Save intermediate steps for display
                    if chunk["type"] == "code" and "content" in chunk:
                        # Append or create code step
                        if not intermediate_steps or intermediate_steps[-1]["type"] != "tool_call":
                            intermediate_steps.append({
                                "type": "tool_call",
                                "name": "python_interpreter",
                                "args": {"code": str(chunk["content"])}
                            })
                        else:
                            intermediate_steps[-1]["args"]["code"] += str(chunk["content"])
                            
                    elif chunk["type"] == "console" and "content" in chunk:
                        if not intermediate_steps or intermediate_steps[-1]["type"] != "tool_result":
                            intermediate_steps.append({
                                "type": "tool_result",
                                "name": "python_interpreter_output",
                                "content": str(chunk["content"])
                            })
                        else:
                            intermediate_steps[-1]["content"] += str(chunk["content"])
                            
                    elif chunk["type"] == "message" and "content" in chunk:
                        final_answer += str(chunk["content"])
                        
        except Exception as e:
            final_answer += f"\n[Ha ocurrido un error durante la ejecución: {str(e)}]"

        # Save to memory
        self.memory.add_message(session_id, "user", prompt)
        self.memory.add_message(session_id, "assistant", final_answer)

        return {
            "answer": final_answer,
            "intermediate_steps": intermediate_steps
        }
