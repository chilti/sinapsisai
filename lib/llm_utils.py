import os
import httpx
from dotenv import load_dotenv
from openai import OpenAI, AsyncOpenAI
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# Aseguramos carga de entorno
load_dotenv()

class LLMConfig:
    @staticmethod
    def get_auth_url():
        """Construye la URL con Basic Auth para LM Studio/Remote LLM."""
        user = os.getenv("LLM_USER")
        password = os.getenv("LLM_PASSWORD")
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
        
        if not base_url.endswith("/"):
            base_url += "/"
            
        if user and password:
            if "://" in base_url:
                proto, rest = base_url.split("://", 1)
                return f"{proto}://{user}:{password}@{rest}"
            else:
                return f"http://{user}:{password}@{base_url}"
        return base_url

    @staticmethod
    def get_model_name(default="openai/gpt-oss-20b"):
        return os.getenv("LLM_MODEL", default)

    @staticmethod
    def get_embedding_model_name(default="nomic-embed-text"):
        return os.getenv("EMBEDDING_MODEL", default)

    @staticmethod
    def get_api_key():
        return os.getenv("LLM_API_KEY", "lm-studio")

def get_http_client(async_mode=False, timeout=120):
    """Retorna un cliente httpx configurado para saltar validación SSL."""
    if async_mode:
        return httpx.AsyncClient(verify=False, timeout=timeout)
    return httpx.Client(verify=False, timeout=timeout)

def get_openai_client(async_mode=False):
    """Retorna un cliente de OpenAI (Sincrónico o Asincrónico) para LM Studio."""
    auth_url = LLMConfig.get_auth_url()
    api_key = LLMConfig.get_api_key()
    
    if async_mode:
        return AsyncOpenAI(
            base_url=auth_url,
            api_key=api_key,
            http_client=get_http_client(async_mode=True)
        )
    return OpenAI(
        base_url=auth_url,
        api_key=api_key,
        http_client=get_http_client(async_mode=False)
    )

def get_chat_model(temperature=0, **kwargs):
    """Retorna una instancia de ChatOpenAI (LangChain) configurada."""
    return ChatOpenAI(
        model=LLMConfig.get_model_name(),
        base_url=LLMConfig.get_auth_url(),
        api_key=LLMConfig.get_api_key(),
        http_async_client=get_http_client(async_mode=True),
        temperature=temperature,
        **kwargs
    )

def get_embeddings_model(**kwargs):
    """Retorna una instancia de OpenAIEmbeddings (LangChain) configurada."""
    return OpenAIEmbeddings(
        model=LLMConfig.get_embedding_model_name(),
        base_url=LLMConfig.get_auth_url(),
        api_key=LLMConfig.get_api_key(),
        http_client=get_http_client(async_mode=False),
        check_embedding_ctx_length=False,
        **kwargs
    )

def handle_llm_exception(e):
    """
    Analiza excepciones del LLM para detectar fallos críticos del servidor.
    Lanza ConnectionError si el servidor está caído o el modelo no está cargado.
    """
    err_msg = str(e).lower()
    
    # Patrones conocidos de fallos críticos en LM Studio / OpenAI API
    critical_patterns = [
        "connection error",
        "no models loaded", 
        "model not found",
        "server is not running",
        "the model has crashed" # Nuevo patrón detectado
    ]
    
    if any(pattern in err_msg for pattern in critical_patterns):
        raise ConnectionError(f"LLM Server Unavailable: {e}")
    
    # Otros errores se reportan pero no necesariamente detienen todo el pipeline
    return False

def wait_for_llm_recovery(client, max_attempts=5, delay_seconds=300):
    """
    Entra en un bucle de espera activa si el servidor LLM falla.
    Diseñado para ser llamado desde cualquier script de ingesta.
    """
    import time
    print(f"\n[!] INICIANDO MODO RECUPERACIÓN. El servidor LLM no responde o el modelo crasheó.")
    print(f"    Se realizarán hasta {max_attempts} intentos cada {delay_seconds//60} minutos.")
    
    for i in range(1, max_attempts + 1):
        print(f"\n[Intento {i}/{max_attempts}] Esperando {delay_seconds//60} minutos...")
        time.sleep(delay_seconds)
        
        try:
            print(f"    Verificando estado del servidor...")
            # PING: listado de modelos
            client.models.list()
            print(f"    [OK] El servidor LLM ha respondido. Reanudando proceso...")
            return True
        except Exception as e:
            print(f"    [ERROR] El servidor sigue caído: {e}")
            
    print("\n[CRITICAL] No se pudo recuperar la conexión con el LLM tras varios intentos.")
    return False
