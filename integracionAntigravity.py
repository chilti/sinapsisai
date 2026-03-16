import os
import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from antigravity_automation import AntigravityClient

# 1. Cargar configuración desde tu .env 
load_dotenv()

# 2. Construir la URL con autenticación 
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL")

# Limpieza de URL
if not base_url.endswith("/"): 
    base_url += "/"

if user and password:
    proto, rest = base_url.split("://", 1)
    # Resultado: https://rag_user:plm+cuan... @dinamica1... 
    auth_url = f"{proto}://{user}:{password}@{rest}"
else:
    auth_url = base_url

# 3. Configurar el cliente HTTP (saltando verificación SSL si es necesario)
http_client = httpx.Client(verify=False, timeout=120)
llm_model_name = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")

# 4. Instanciar el modelo compatible con Antigravity
llm = ChatOpenAI(
    model=llm_model_name,
    base_url=auth_url,
    api_key="lm-studio",
    http_client=http_client,
    temperature=0
)
# --- 4. CONEXIÓN AL IDE ---
def iniciar_agente():
    """
    Configura y arranca el servidor de automatización para el IDE de Antigravity.
    """
    try:
        # Inicializamos el cliente. En algunas versiones se requiere pasar el LLM al constructor.
        client = AntigravityClient(llm=llm)
        
        # Intentamos registrar la herramienta de OpenAlex de forma explícita
        if hasattr(client, 'add_tool'):
            client.add_tool(buscar_openalex)
        
        print(f"✅ Modelo '{llm.model_name}' vinculado exitosamente.")
        print("🚀 Esperando comandos desde la interfaz de Antigravity (GUI)...")
        
        # El método estándar para iniciar el servicio es .run() o .start()
        client.run()

    except AttributeError as e:
        # Si los métodos fallan, el SDK podría estar usando una interfaz simplificada
        print(f"⚠️ Error de atributo: {e}. Intentando modo de escucha directa...")
        try:
            # Algunas versiones usan un método estático para levantar el servicio
            AntigravityClient.serve(model=llm, tools=[buscar_openalex])
        except Exception as final_e:
            print(f"❌ No se pudo iniciar el cliente: {final_e}")

if __name__ == "__main__":
    iniciar_agente()