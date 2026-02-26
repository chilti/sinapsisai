from langchain_core.tools import Tool
from interpreter import interpreter
import sys
import io
import contextlib
import os
from dotenv import load_dotenv

load_dotenv()

def execute_open_interpreter_code(query: str) -> str:
    """
    Usa Open Interpreter (ejecución local de código Python/Bash) para resolver tareas.
    Ideal para análisis de datos matemáticos, creación de gráficas, manejo de archivos, 
    y otras tareas que requieran escribir y ejecutar scripts de forma dinámica.
    
    Args:
        query (str): Las instrucciones detalladas de lo que el código debe hacer.
    
    Returns:
        str: El resultado o salida de la ejecución del código.
    """
    print(f"👨‍💻 Ejecutando código dinámicamente para: '{query}'...")
    
    # Configuración de Open Interpreter para usar el servidor local/remoto
    user = os.getenv("LLM_USER")
    pwd = os.getenv("LLM_PASSWORD")
    base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
    model = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
    
    # Construir URL con auth si es necesario
    auth_url = base_url
    if user and pwd:
        if "://" in base_url:
            proto, rest = base_url.split("://", 1)
            auth_url = f"{proto}://{user}:{pwd}@{rest}"
        else:
            auth_url = f"http://{user}:{pwd}@{base_url}"

    # Configurar el intérprete para que no pida OpenAI si no es necesario
    interpreter.offline = True # Evita que intente contactar servicios externos innecesarios
    interpreter.llm.model = model
    interpreter.llm.api_base = auth_url
    interpreter.llm.api_key = "lm-studio"
    interpreter.llm.max_tokens = 1000
    interpreter.llm.context_window = 4096
    
    interpreter.auto_run = True # Permite ejecución de código sin intervención del usuario
    interpreter.system_message += """
    You are a helpful assistant integrated into a larger LangChain orchestration system.
    Your goal is to write and execute code to solve the user's specific sub-task.
    
    IMPORTANT: If you generate any plots or charts using matplotlib or seaborn, you MUST save them to a file named 'interpreter_output.png' in the current directory using:
    `plt.savefig('interpreter_output.png')`
    
    Return the final answer clearly.
    """

    try:
         # Captura la salida estándar para devolverla a LangChain
         f = io.StringIO()
         with contextlib.redirect_stdout(f):
             # open-interpreter devuelve una lista de mensajes
             messages = interpreter.chat(query)
         
         output = f.getvalue()
         
         if not output.strip():
             # Si no hay salida de stdout directa, buscamos la respuesta en el último mensaje de tipo asistente
             for msg in reversed(messages):
                 if msg['role'] == 'assistant' and 'message' in msg and msg['message']:
                      output = msg['message']
                      break
                       
         return output if output else "La ejecución fue exitosa pero no generó salida."
    
    except Exception as e:
        return f"Error ejecutando código con Open Interpreter: {str(e)}"

# Define la herramienta para LangChain
open_interpreter_tool = Tool(
    name="OpenInterpreter_CodeExecutor",
    func=execute_open_interpreter_code,
    description="Útil cuando necesitas crear o ejecutar scripts en Python/Bash para resolver un problema, generar una gráfica, o procesar datos. Proporciona instrucciones claras y detalladas sobre lo que el código debe hacer."
)
