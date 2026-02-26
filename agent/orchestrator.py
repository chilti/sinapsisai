import json
import os
import base64
import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

load_dotenv()
from .memory_manager import SessionMemoryManager
from .tools_interpreter import open_interpreter_tool
from .tools_hybrid import hybrid_tools

class RAGOrchestrator:
    def __init__(self, tools_list=[], model_name=None, base_url=None, api_key="lm-studio"):
        """
        Inicializa el orquestador que conecta LLMs, Herramientas, Memoria y Open Interpreter.
        """
        # Cargar valores por defecto de .env si no se proporcionan
        user = os.getenv("LLM_USER")
        password = os.getenv("LLM_PASSWORD")
        base_url = base_url or os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
        model_name = model_name or os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
        
        # Construimos la URL autenticada (Basic Auth en URL para evitar sobreescritura de OpenAI)
        auth_url = base_url
        if user and password:
             if "://" in base_url:
                  protocol, rest = base_url.split("://", 1)
                  auth_url = f"{protocol}://{user}:{password}@{rest}"
             else:
                  auth_url = f"http://{user}:{password}@{base_url}"

        # Clientes para saltar verificación SSL (como en el ejemplo del usuario)
        self.http_client = httpx.AsyncClient(verify=False)

        self.llm = ChatOpenAI(
            model=model_name,
            base_url=auth_url, 
            api_key=api_key,
            http_async_client=self.http_client,
            temperature=0
        )
        
        # Agregamos hybrid_tools y open_interpreter a las herramientas regulares
        # Verificación defensiva: aseguramos que tools_list sea una lista
        final_tools_list = []
        if isinstance(tools_list, list):
            final_tools_list = tools_list
        elif tools_list is not None:
            print(f"Advertencia: tools_list no es una lista ({type(tools_list)}). Ignorando.")
            
        self.tools = final_tools_list + hybrid_tools + [open_interpreter_tool]
        
        # Sistema de checkpointer (memoria a corto plazo de langgraph)
        self.checkpointer = MemorySaver()
        self.memory_manager = SessionMemoryManager() # Persistencia SQLite
        
        # Prompt por defecto
        self.system_prompt = """
        Eres un asistente experto e investigador científico avanzado. Tu objetivo es resolver las tareas del usuario, orquestando mútliples herramientas en paralelo.
        
        1. Utiliza las herramientas de búsqueda para extraer contexto científico y bibliométrico.
        2. Si el usuario te pide cálculos complejos, análisis de datos en CSVs o Excel, generar gráficas, o interactuar fuertemente con el sistema operativo de forma dinámica, UTILIZA LA HERRAMIENTA 'OpenInterpreter_CodeExecutor'. Escríbele instrucciones claras en lenguaje natural.
        3. Mantén el contexto entre mensajes.
        4. Si se te provee el contexto de una 'Entidad Seleccionada' (ej. una facultad o instituto de la UNAM), DEBES restringir y enfocar tus respuestas a los académicos o producción exclusiva de esa entidad.
        5. Siempre incluye en tus respuestas las fuentes de donde obtuviste la información. Por ejemplo, si mencionas un académico, incluye su nombre y la entidad a la que pertenece. Si mencionas una publicación, incluye su título, autores, año y DOI (con https://doi.org/...). 
        """
        
        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("placeholder", "{messages}")
        ])
        
        self.agent_executor = create_react_agent(
            self.llm, 
            self.tools, 
            checkpointer=self.checkpointer,
            prompt=self.prompt_template
        )

    async def ask(self, session_id: str, query: str, entity_context: str = None) -> str:
        """
        Envía un mensaje al agente, manteniendo el estado de la sesión.
        """
        contextualized_query = query
        if entity_context:
            contextualized_query = f"[Contexto del Sistema: El usuario actualmente está visualizando y consultando sobre la entidad '{entity_context}'].\n\n{query}"

        # Guardamos la pregunta del usuario en el historial
        self.memory_manager.add_message(session_id, "user", query) # Guardamos el original para la UI
        
        config = {"configurable": {"thread_id": session_id}}
        
        # Invocamos al agente
        try:
             results = await self.agent_executor.ainvoke(
                 {"messages": [{"role": "user", "content": contextualized_query}]},
                 config=config
             )
             response = results['messages'][-1].content
             
             # Guardamos respuesta en DB
             self.memory_manager.add_message(session_id, "assistant", response)
             return response
             
        except Exception as e:
             error_msg = f"Error en orquestación: {e}"
             print(error_msg)
             return error_msg
             
    def clear_session(self, session_id: str):
        self.memory_manager.clear_session(session_id)
        print(f"Sesión {session_id} limpiada.")
