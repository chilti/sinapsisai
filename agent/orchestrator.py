import json
import os
import base64
import httpx
import time
import hashlib
from dotenv import load_dotenv

# Asegurar que el directorio raíz esté en el path para importar lib.llm_utils
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.llm_utils import get_chat_model, LLMConfig
from lib.service_availability import NEO4J_AVAILABLE, QDRANT_AVAILABLE
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

load_dotenv()
from .memory_manager import SessionMemoryManager
from .tools_interpreter import structured_analytics_tools
from .tools_hybrid import hybrid_tools

class RAGOrchestrator:
    def __init__(self, tools_list=None, model_name=None, base_url=None, api_key="lm-studio", use_defaults=True, system_prompt=None):
        """
        Inicializa el orquestador que conecta LLMs, Herramientas y Memoria (Tier 1 Seguro).
        """
        # Delegamos la creación del LLM y el cliente HTTP a la fábrica centralizada
        self.llm = get_chat_model(temperature=0)
        self._response_cache = {}  # Caché inteligente de respuestas para focos/consultas idénticas
        
        # Guardamos referencia del cliente http (opcional, para limpieza posterior si se requiere)
        self.http_client = self.llm.http_async_client
        
        # Agregamos hybrid_tools y structured_analytics_tools a las herramientas regulares
        final_tools_list = []
        if isinstance(tools_list, list):
            final_tools_list = tools_list
        elif tools_list is not None:
            print(f"Advertencia: tools_list no es una lista ({type(tools_list)}). Ignorando.")
            
        if use_defaults:
            self.tools = final_tools_list + hybrid_tools + structured_analytics_tools
        else:
            self.tools = final_tools_list
        
        # SQLite para historial limpio (solo mensajes humano/asistente, sin ruido de herramientas)
        self.memory_manager = SessionMemoryManager()
        
        # --- PROMPT ASISTENTE (adaptado a servicios disponibles) ---
        if system_prompt:
            self.system_prompt = system_prompt
        else:
            # Sección de herramientas locales según disponibilidad
            if NEO4J_AVAILABLE or QDRANT_AVAILABLE:
                _local_section = "**Paso 1 — Búsqueda Local (OBLIGATORIA Y PRIORITARIA)**\nAntes de consultar fuentes externas, busca siempre en los recursos locales:\n"
                if NEO4J_AVAILABLE:
                    _local_section += "- `query_knowledge_graph_cypher`: Grafo de Conocimiento (Neo4j) para relaciones, coautoría y afiliaciones.\n"
                if QDRANT_AVAILABLE:
                    _local_section += "- `search_scientific_papers_semantic`: Búsqueda semántica vectorial (Qdrant) por significado.\n"
                _local_section += "- `query_academic_cache`: Consulta segura de datos estructurados Parquet (institucion_annual, investigador_annual, papers_profesor).\n"
                _local_section += "- `query_clickhouse_safe_sql`: Consultas analíticas SQL masivas sobre producción y citas.\n"
                _local_section += "- `get_scientometric_summary`: Resumen cienciométrico integral de un académico.\n\n"
                _ext_section = "**Paso 2 — Enriquecimiento Externo (Fallback)**\nUsa OpenAlex o búsqueda web SOLO si los datos no existen localmente."
            else:
                _local_section = (
                    "**IMPORTANTE**: En este entorno las bases locales (Neo4j, Qdrant) no están disponibles.\n"
                    "NO uses `query_knowledge_graph_cypher` ni `search_scientific_papers_semantic`.\n"
                    "Usa `query_academic_cache` y `get_scientometric_summary` para datos locales.\n\n"
                )
                _ext_section = (
                    "**Estrategia Principal**: Usa herramientas de OpenAlex (`searchAuthorInOpenAlex`, "
                    "`recoverFromOpenAlex`, `recoverAuthorWorksFromOpenAlex`) y búsqueda web como fuentes primarias."
                )

            self.system_prompt = f"""Eres SNII Info TlachIA, un analista experto en bibliometría y cienciometría. Tu misión es proporcionar respuestas precisas sobre investigadores, publicaciones y métricas científicas de México.

## ECOSISTEMA DE DATOS
- Datos del Padrón SNII (Sistema Nacional de Investigadoras e Investigadores de SECIHTI).
- El sistema te proveerá la entidad o investigador actualmente seleccionado como contexto.

## ESTRATEGIA DE DECISIÓN

{_local_section}
{_ext_section}

## FORMATO DE RESPUESTA
1. Síntesis narrativa con los resultados principales.
2. Evidencia clara con tablas de datos estructurados.
3. Nota de origen: Indica la fuente de información utilizada.
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
        messages = [SystemMessage(content="Eres SNII Info TlachIA, un analista experto en bibliometría de la UNAM. "
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

    def ask_lightweight_stream_sync(self, session_id: str, query: str, ui_context: str = None):
        """
        Versión ligera del agente (Síncrona con Streaming). NO utiliza herramientas.
        Incluye sanitización de entrada y caché inteligente de 30 minutos.
        """
        # 1. Sanitizar entrada
        query = LLMConfig.sanitize_input(query, max_chars=1500)
        
        # 2. Verificar Caché para evitar consultas duplicadas
        cache_key = hashlib.md5(f"{query}:{ui_context}".encode('utf-8')).hexdigest()
        now = time.time()
        if cache_key in self._response_cache:
            ts, cached_resp = self._response_cache[cache_key]
            if now - ts < 1800: # 30 minutos de caché
                self.memory_manager.add_message(session_id, "user", query)
                self.memory_manager.add_message(session_id, "assistant", cached_resp)
                yield cached_resp
                return

        history = self.memory_manager.get_history(session_id, limit=6)

        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        messages = [SystemMessage(content="Eres SNII Info TlachIA, un analista experto en bibliometría de la UNAM. "
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
            full_response = ""
            for chunk in self.llm.stream(messages):
                if chunk.content:
                    full_response += chunk.content
                    yield chunk.content
            
            # Guardar en Caché
            self._response_cache[cache_key] = (now, full_response)
            self.memory_manager.add_message(session_id, "assistant", full_response)
        except Exception as e:
            print(f"Error en ask_lightweight_stream_sync: {e}")
            yield f"\n\nError: {e}"
