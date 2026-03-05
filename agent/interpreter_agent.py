import os
import io
import json
import asyncio
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
            # Disable confirmation to run autonomously
            self.interpreter.auto_run = True
            # Limit steps to prevent infinite loops
            self.interpreter.max_steps = 15
            # Use local Python
            self.interpreter.local = True
            
            # Inject context
            self.interpreter.system_message += """
            Eres un agente 'Plan-and-Execute' de Sinapsis AI, experto en análisis de datos bibliométricos y cienciometría.
            Tu misión principal es analizar datos científicos escribiendo y ejecutando código Python de manera iterativa.

            HERRAMIENTAS NATIVAS RECOMENDADAS:
            Puedes importar y usar libremente las herramientas pre-existentes del proyecto para facilitar tu trabajo:
            ```python
            # Para consultar la base de grafos Neo4j (siempre retorna diccionarios con la respuesta)
            from agent.tools_hybrid import query_knowledge_graph_cypher
            data = query_knowledge_graph_cypher("MATCH (p:Paper) RETURN p.title LIMIT 5")
            
            # Para extraer de OpenAlex
            from agent.tools_hybrid import search_scientific_papers
            papers = search_scientific_papers("inteligencia artificial")
            
            # Para trabajar con DataFrames desde los parquets cacheados:
            import pandas as pd
            df_inst = pd.read_parquet('data/cache/papers_institucion.parquet')
            ```
            
            REGLAS:
            1. Siempre utiliza `print()` en tus scripts para que el resultado sea visible en tu contexto.
            2. Si el usuario te pide un "Plan", elabora una lista paso a paso sin ejecutar código aún.
            3. Si el usuario te pide ejecutar, haz un script para el primer paso, mira el resultado, y continúa iterativamente hasta resolver todo el plan.
            4. Cuando termines todo, lanza un mensaje de resumen final claro en lenguaje natural.
            5. Tienes permiso absoluto para correr código Python.
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
            # Convert roles if necessary
            if role == "human": role = "user"
            if role == "ai": role = "assistant"
            interpreter_msgs.append({"role": role, "type": "message", "content": m.get("content", "")})
        
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
                                "args": {"code": chunk["content"]}
                            })
                        else:
                            intermediate_steps[-1]["args"]["code"] += chunk["content"]
                            
                    elif chunk["type"] == "console" and "content" in chunk:
                        if not intermediate_steps or intermediate_steps[-1]["type"] != "tool_result":
                            intermediate_steps.append({
                                "type": "tool_result",
                                "name": "python_interpreter_output",
                                "content": chunk["content"]
                            })
                        else:
                            intermediate_steps[-1]["content"] += chunk["content"]
                            
                    elif chunk["type"] == "message" and "content" in chunk:
                        final_answer += chunk["content"]
                        
        except Exception as e:
            final_answer += f"\n[Ha ocurrido un error durante la ejecución: {str(e)}]"

        # Save to memory
        self.memory.add_message(session_id, "user", prompt)
        self.memory.add_message(session_id, "assistant", final_answer)

        return {
            "answer": final_answer,
            "intermediate_steps": intermediate_steps
        }
