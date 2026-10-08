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

from lib.llm_utils import get_chat_model, LLMConfig, is_quota_exceeded_error
from lib.service_availability import NEO4J_AVAILABLE, QDRANT_AVAILABLE
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

load_dotenv()
from .memory_manager import SessionMemoryManager
from .tools_interpreter import structured_analytics_tools
from .tools_hybrid import hybrid_tools

def wrap_safe_tool(base_tool, max_chars: int = 12000):
    """
    Envuelve una herramienta LangChain para asegurar que su salida nunca exceda `max_chars`.
    Evita desbordar la ventana de contexto del LLM (ej. Kimi 64k o modelos locales 16k/32k).
    """
    orig_func = getattr(base_tool, "func", None)
    orig_coroutine = getattr(base_tool, "coroutine", None)

    if orig_func and not getattr(base_tool, "_is_context_safe", False):
        def safe_func(*args, **kwargs):
            res = orig_func(*args, **kwargs)
            if isinstance(res, str) and len(res) > max_chars:
                return res[:max_chars] + f"\n... [Respuesta truncada automáticamente a {max_chars} caracteres para preservar la ventana de contexto del LLM]"
            return res
        base_tool.func = safe_func
        base_tool._is_context_safe = True

    if orig_coroutine and not getattr(base_tool, "_is_async_context_safe", False):
        async def safe_coro(*args, **kwargs):
            res = await orig_coroutine(*args, **kwargs)
            if isinstance(res, str) and len(res) > max_chars:
                return res[:max_chars] + f"\n... [Respuesta truncada automáticamente a {max_chars} caracteres para preservar la ventana de contexto del LLM]"
            return res
        base_tool.coroutine = safe_coro
        base_tool._is_async_context_safe = True

    return base_tool

class RAGOrchestrator:
    def __init__(self, tools_list=None, model_name=None, base_url=None, api_key="lm-studio", use_defaults=True, system_prompt=None):
        """
        Inicializa el orquestador que conecta LLMs, Herramientas y Memoria (Tier 1 Seguro).
        """
        # Modelo activo inicial y estado de failover
        self._current_model = LLMConfig.get_clean_model_name(model_name or LLMConfig.get_model_name())
        self.fallback_info = None
        self.llm = get_chat_model(temperature=0, model=self._current_model)
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
            raw_tools = final_tools_list + hybrid_tools + structured_analytics_tools
        else:
            raw_tools = final_tools_list
            
        self.tools = [wrap_safe_tool(t) for t in raw_tools]
        
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

    def update_model(self, model_name: str):
        """Actualiza dinámicamente el modelo LLM subyacente (ej. Gemini, OpenRouter o LM Studio)."""
        if model_name:
            clean_name = LLMConfig.get_clean_model_name(model_name)
            if getattr(self, '_current_model', None) != clean_name:
                self._current_model = clean_name
                self.llm = get_chat_model(temperature=0, model=clean_name)
                self.http_client = self.llm.http_async_client
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
            current_query = f"[Contexto del Sistema: El usuario actualmente está visualizando y consultando sobre la entidad '{entity_context}'].\n\n{query}"
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
                "intermediate_steps": intermediate_steps,
                "fallback_triggered": False
            }
            
        except Exception as e:
            if is_quota_exceeded_error(e) and not LLMConfig.is_local(self._current_model):
                prev_model = self._current_model
                fallback_model = LLMConfig.get_fallback_model_name()
                print(f"[FAILOVER] Cuota agotada en '{prev_model}'. Conmutando automáticamente a '{fallback_model}'...")
                self.fallback_info = {
                    "from_model": prev_model,
                    "to_model": fallback_model,
                    "reason": str(e),
                    "timestamp": time.time()
                }
                self.update_model(fallback_model)
                try:
                    results = await self.agent_executor.ainvoke(
                        {"messages": messages},
                        config=config
                    )
                    all_messages = results['messages']
                    response = all_messages[-1].content
                    
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
                    self.memory_manager.add_message(session_id, "assistant", response)
                    return {
                        "answer": response,
                        "intermediate_steps": intermediate_steps,
                        "fallback_triggered": True,
                        "fallback_info": self.fallback_info
                    }
                except Exception as e2:
                    error_msg = f"Error en orquestación tras conmutar al modelo local ({fallback_model}): {e2}"
                    print(error_msg)
                    return error_msg
            else:
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
            if is_quota_exceeded_error(e) and not LLMConfig.is_local(self._current_model):
                prev_model = self._current_model
                fallback_model = LLMConfig.get_fallback_model_name()
                print(f"[FAILOVER LIGHTWEIGHT] Cuota agotada en '{prev_model}'. Conmutando a '{fallback_model}'...")
                self.fallback_info = {
                    "from_model": prev_model,
                    "to_model": fallback_model,
                    "reason": str(e),
                    "timestamp": time.time()
                }
                self.update_model(fallback_model)
                try:
                    result = await self.llm.ainvoke(messages)
                    response = result.content
                    self.memory_manager.add_message(session_id, "assistant", response)
                    return response
                except Exception as e2:
                    return f"Error tras conmutar a {fallback_model}: {e2}"
            print(f"Error en ask_lightweight: {e}")
    async def ask_stream(self, session_id: str, query: str, ui_context: str = None):
        """
        Transmite en tiempo real el proceso de razonamiento del agente ReAct (Tier 1):
        - Emite eventos de herramientas (tool_start, tool_end) con sus parámetros y resultados.
        - Emite tokens de texto de la respuesta final.
        - Mantiene la memoria de sesión limpia y sin contaminación de herramientas.
        """
        query = LLMConfig.sanitize_input(query, max_chars=1500)
        
        # Historial limpio (últimos 6 mensajes = 3 turnos)
        history = self.memory_manager.get_history(session_id, limit=6)
        messages = []
        for msg in history:
            role = "human" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["content"]})
            
        current_query = query
        if ui_context:
            current_query = f"[Contexto de Interfaz Actual:\n{ui_context}]\n\nPregunta del usuario: {query}"
        messages.append({"role": "human", "content": current_query})
        
        self.memory_manager.add_message(session_id, "user", query)
        config = {"configurable": {"thread_id": session_id}}
        
        full_response = ""
        try:
            async for event in self.agent_executor.astream_events(
                {"messages": messages}, 
                config=config, 
                version="v2"
            ):
                kind = event.get("event")
                name = event.get("name", "")
                
                if kind == "on_tool_start":
                    tool_input = event.get("data", {}).get("input", {})
                    yield {
                        "type": "tool_start",
                        "tool": name,
                        "input": tool_input
                    }
                elif kind == "on_tool_end":
                    tool_output = event.get("data", {}).get("output", "")
                    out_str = str(tool_output)
                    snippet = out_str[:800] + ("..." if len(out_str) > 800 else "")
                    yield {
                        "type": "tool_end",
                        "tool": name,
                        "output": snippet
                    }
                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk", None)
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        # Si contiene fragmentos de llamada a herramientas, no emitir como texto
                        if getattr(chunk, "tool_call_chunks", None):
                            continue
                        full_response += chunk.content
                        yield {
                            "type": "token",
                            "token": chunk.content,
                            "chunk": chunk.content
                        }
                        
            if full_response:
                self.memory_manager.add_message(session_id, "assistant", full_response)
        except Exception as e:
            err_str = str(e)
            print(f"Error en ask_stream: {err_str}")
            yield {
                "type": "error",
                "error": err_str
            }

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
        
        # 2. Verificar Caché para evitar consultas duplicadas (caché por sesión)
        cache_key = hashlib.md5(f"{session_id}:{query}:{ui_context}".encode('utf-8')).hexdigest()
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
            if is_quota_exceeded_error(e) and not LLMConfig.is_local(self._current_model):
                prev_model = self._current_model
                err_str = str(e).lower()
                is_server_down = any(x in err_str for x in ["502", "503", "504", "bad gateway", "service unavailable", "connection error"])
                reason_txt = "Servidor remoto no disponible o caído (502 Bad Gateway)" if is_server_down else "Límite de cuota alcanzado"
                print(f"[FAILOVER STREAM] {reason_txt} en '{prev_model}'. Conmutando a '{fallback_model}'...")
                self.fallback_info = {
                    "from_model": prev_model,
                    "to_model": fallback_model,
                    "reason": str(e),
                    "timestamp": time.time()
                }
                self.update_model(fallback_model)
                yield f"> 🔄 **Aviso de conmutación:** {reason_txt} en `{prev_model}`. Continuando la respuesta con el modelo local de respaldo `{fallback_model}`...\n\n"
                try:
                    full_response = ""
                    for chunk in self.llm.stream(messages):
                        if chunk.content:
                            full_response += chunk.content
                            yield chunk.content
                    self._response_cache[cache_key] = (now, full_response)
                    self.memory_manager.add_message(session_id, "assistant", full_response)
                except Exception as e2:
                    yield f"\n\nError tras conmutar a {fallback_model}: {e2}"
            else:
                print(f"Error en ask_lightweight_stream_sync: {e}")
                yield f"\n\nError: {e}"
