import os
from dotenv import load_dotenv
from lib.llm_utils import get_chat_model
from antigravity_automation import AntigravityClient

# 1. Cargar configuración desde tu .env 
load_dotenv()

# 2. Instanciar el modelo compatible con Antigravity usando lib.llm_utils centralizado
llm = get_chat_model(temperature=0)
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