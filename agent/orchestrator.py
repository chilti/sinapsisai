import json
import os
import base64
import httpx
from dotenv import load_dotenv

# Asegurar que el directorio raíz esté en el path para importar lib.llm_utils
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.llm_utils import get_chat_model
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

load_dotenv()
from .memory_manager import SessionMemoryManager
from .tools_interpreter import open_interpreter_tool
from .tools_hybrid import hybrid_tools

class RAGOrchestrator:
    def __init__(self, tools_list=None, model_name=None, base_url=None, api_key="lm-studio", use_defaults=True, system_prompt=None):
        """
        Inicializa el orquestador que conecta LLMs, Herramientas, Memoria y Open Interpreter.
        """
        # Delegamos la creación del LLM y el cliente HTTP a la fábrica centralizada
        self.llm = get_chat_model(temperature=0)
        
        # Guardamos referencia del cliente http (opcional, para limpieza posterior si se requiere)
        self.http_client = self.llm.http_async_client
        
        # Agregamos hybrid_tools y open_interpreter a las herramientas regulares
        # Verificación defensiva: aseguramos que tools_list sea una lista
        final_tools_list = []
        if isinstance(tools_list, list):
            final_tools_list = tools_list
        elif tools_list is not None:
            print(f"Advertencia: tools_list no es una lista ({type(tools_list)}). Ignorando.")
            
        if use_defaults:
            self.tools = final_tools_list + hybrid_tools + [open_interpreter_tool]
        else:
            self.tools = final_tools_list
        
        # SQLite para historial limpio (solo mensajes humano/asistente, sin ruido de herramientas)
        self.memory_manager = SessionMemoryManager()
        
        # --- PROMPT ASISTENTE ---
        if system_prompt:
            self.system_prompt = system_prompt
        else:
            self.system_prompt = """
Eres SINAPSIS, un analista experto en bibliometría de la UNAM. Tu misión es proporcionar respuestas precisas sobre investigadores, publicaciones y métricas utilizando una estrategia de datos híbrida donde **EL ACCESO LOCAL ES PRIORITARIO**.

## CONTEXTO DEL ECOSISTEMA DE DATOS
- **Producción Científica Mexicana**: Los datos en nuestro Grafo de Conocimiento (Neo4j) contienen predominantemente producción científica mexicana.
- **Jerarquía Institucional (Padrón SNII)**: La estructura jerárquica de las entidades e instituciones en nuestra base de datos está modelada a partir del Padrón del SNII (Sistema Nacional de Investigadoras e Investigadores), el cual representa la estructura académica de todo México.
- **Flexibilidad de Búsqueda**: El sistema te proveerá la entidad o investigador actualmente seleccionado en la interfaz. Usa ese contexto si la instrucción del usuario está directamente relacionada. Sin embargo, si la pregunta es más amplia o no está relacionada con la selección actual, **sé flexible y amplía tus búsquedas a todo el conjunto de datos nacional disponible**, sin limitarte a la entidad seleccionada.

## ESTRATEGIA DE DECISIÓN PRIORITARIA

**Paso 1 — Búsqueda Local (OBLIGATORIA Y PRIORITARIA)**
Antes de consultar cualquier fuente externa, busca siempre en los recursos locales:
- `query_knowledge_graph_cypher`: Consulta el Grafo de Conocimiento (Neo4j) para relaciones, coautoría y estructuras institucionales.
- `search_scientific_papers_semantic`: Búsqueda semántica en la base vectorial (Qdrant) para encontrar papers por significado.
- `Python_CodeExecutor`: Úsalo para cargar archivos Parquet en `data/cache/` (jerarquía Entidad/Academico) para cálculos de métricas precisas.

**Paso 2 — Enriquecimiento Externo (Secundario/Fallback)**
Usa las herramientas de OpenAlex (`recoverFromOpenAlex`, `searchAuthorInOpenAlex`) o búsqueda web SOLO SI:
1. Los datos no existen en la base local.
2. Necesitas métricas globales muy recientes que aún no han sido procesadas localmente.

**Paso 3 — Reglas Críticas**
- **Sincronía**: Local = Veracidad institucional UNAM e instituciones mexicanas. Externo = Contexto global.
- **Nombres**: En Cypher usa siempre `CONTAINS` (ej. `WHERE toLower(a.name) CONTAINS toLower('alcubierre')`).

## FORMATO DE RESPUESTA
1. Síntesis narrativa: Resultados principales priorizando la base de datos local.
2. Evidencia: Tablas o gráficas (vía Python) basadas en los datos internos.
3. Nota de origen: Si usas datos externos, aclara que es información de respaldo de OpenAlex/Web.
        """
        
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("placeholder", "{messages}")
        ])
        
        # SIN MemorySaver: el agente es stateless por invocación.
        # La continuidad se gestiona manualmente inyectando el historial limpio.
        self.agent_executor = create_react_agent(
            self.llm, 
            self.tools,
            prompt=self.prompt_template
        )

    async def ask(self, session_id: str, query: str, entity_context: str = None) -> str:
        """
        Envía un mensaje al agente.
        Construye el contexto de conversación inyectando únicamente el historial
        limpio (mensajes humano/asistente), sin los resultados de herramientas de
        turnos anteriores, evitando así contaminación de contexto.
        """
        # Historial limpio (últimos 6 mensajes = 3 turnos)
        history = self.memory_manager.get_history(session_id, limit=6)
        
        # Armar lista de mensajes para el agente
        messages = []
        for msg in history:
            role = "human" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})
        
        # Añadir la pregunta actual (con contexto de entidad si aplica)
        current_query = query
        if entity_context:
            current_query = f"[Contexto del Sistema: El usuario actualmente está visualizando y consultando sobre la entidad '{entity_context}'].\\n\\n{query}"
        messages.append({"role": "human", "content": current_query})
        
        # Guardar la pregunta del usuario en el historial
        self.memory_manager.add_message(session_id, "user", query)
        
        # Config sin thread_id (el agente es stateless, no usa checkpointer)
        config = {"configurable": {"thread_id": session_id}}
        
        try:
            results = await self.agent_executor.ainvoke(
                {"messages": messages},
                config=config
            )
            
            all_messages = results['messages']
            response = all_messages[-1].content
            
            # Extraer traza de razonamiento (solo del turno actual)
            intermediate_steps = []
            for msg in all_messages:
                if msg.type == "ai" and msg.tool_calls:
                    for tc in msg.tool_calls:
                        intermediate_steps.append({
                            "type": "tool_call",
                            "name": tc["name"],
                            "args": tc["args"]
                        })
                elif msg.type == "tool":
                    intermediate_steps.append({
                        "type": "tool_result",
                        "name": msg.name,
                        "content": str(msg.content)[:10000]
                    })

            # Guardar respuesta en el historial limpio
            self.memory_manager.add_message(session_id, "assistant", response)
            
            return {
                "answer": response,
                "intermediate_steps": intermediate_steps
            }
            
        except Exception as e:
            error_msg = f"Error en orquestación: {e}"
            print(error_msg)
            return error_msg
            
    async def ask_lightweight(self, session_id: str, query: str, ui_context: str = None) -> str:
        """
        Versión ligera del agente. NO utiliza herramientas.
        Solo usa el historial y el contexto de la UI para responder.
        """
        history = self.memory_manager.get_history(session_id, limit=6)
        
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        messages = [SystemMessage(content="Eres SINAPSIS, un analista experto en bibliometría de la UNAM. "
                                          "El usuario te hará preguntas sobre la interfaz que está viendo. "
                                          "Usa el contexto proporcionado para responder de manera concisa y directa.")]
        
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
                
        current_query = query
        if ui_context:
            current_query = f"[Contexto de Interfaz Actual:\n{ui_context}]\n\nPregunta del usuario: {query}"
            
        messages.append(HumanMessage(content=current_query))
        self.memory_manager.add_message(session_id, "user", query)
        
        try:
            result = await self.llm.ainvoke(messages)
            response = result.content
            self.memory_manager.add_message(session_id, "assistant", response)
            return response
        except Exception as e:
            print(f"Error en ask_lightweight: {e}")
            return f"Error: {e}"
             
    def clear_session(self, session_id: str):
        self.memory_manager.clear_session(session_id)
        print(f"Sesión {session_id} limpiada.")
