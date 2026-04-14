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
    Analiza una excepción de LLM y determina si es un fallo crítico del servidor.
    Lanza ConnectionError si el modelo no está cargado o crasheó.
    """
    err_msg = str(e)
    # Patrones comunes de error en LM Studio cuando falla el modelo
    critical_patterns = [
        "No models loaded",
        "model has crashed",
        "invalid_request_error", # A veces devuelve esto cuando el model param no coincide con nada cargado
        "Connection refused",
        "RemoteProtocolError"
    ]
    
    if any(pattern in err_msg for pattern in critical_patterns):
        print(f"\n[CRITICAL] FALLO EN LLM SERVER: {err_msg}")
        raise ConnectionError(f"LLM Server Unavailable: {err_msg}")
    
    return err_msg
