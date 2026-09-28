import os
import httpx
from dotenv import load_dotenv
from openai import OpenAI, AsyncOpenAI
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# Aseguramos carga de entorno forzando lectura actualizada
load_dotenv(override=True)

# --- Parche de compatibilidad Google Gemini Thinking / Tool Calling ---
# Google Gemini 3.5 adjunta 'thought_signature' dentro de 'extra_content' en cada tool_call.
# LangChain por defecto descarta 'extra_content', provocando error 400 en llamadas multi-turno de herramientas.
# Preservamos 'extra_content' tanto en la deserialización como en la serialización hacia la API.
import langchain_openai.chat_models.base as _lc_openai_base
from langchain_core.messages import AIMessage as _AIMessage

_orig_convert_dict_to_message = _lc_openai_base._convert_dict_to_message
_orig_lc_tool_call_to_openai = _lc_openai_base._lc_tool_call_to_openai_tool_call

def _patched_convert_dict_to_message(_dict):
    msg = _orig_convert_dict_to_message(_dict)
    if isinstance(msg, _AIMessage) and _dict.get("tool_calls"):
        for i, tc in enumerate(msg.tool_calls):
            if i < len(_dict["tool_calls"]):
                raw_tc = _dict["tool_calls"][i]
                if isinstance(raw_tc, dict) and "extra_content" in raw_tc:
                    tc["extra_content"] = raw_tc["extra_content"]
    return msg

def _patched_lc_tool_call_to_openai_tool_call(tool_call):
    res = _orig_lc_tool_call_to_openai(tool_call)
    if isinstance(tool_call, dict) and "extra_content" in tool_call:
        res["extra_content"] = tool_call["extra_content"]
    return res

_lc_openai_base._convert_dict_to_message = _patched_convert_dict_to_message
_lc_openai_base._lc_tool_call_to_openai_tool_call = _patched_lc_tool_call_to_openai_tool_call

class LLMConfig:
    @staticmethod
    def get_provider(model_name: str = None) -> str:
        """
        Determina el proveedor según el nombre del modelo:
        - 'c3': Si contiene 'kimi' o 'c3'.
        - 'openrouter': Si contiene 'openrouter', ':free' o prefijo de openrouter.
        - 'gemini': Si contiene 'gemini' (excepto si viene vía openrouter).
        - 'local': LM Studio local (default/fallback).
        """
        m = (model_name or LLMConfig.get_model_name() or "").lower().strip()
        if "kimi" in m or "c3" in m:
            return "c3"
        if "openrouter" in m or ":free" in m:
            return "openrouter"
        if "gemini" in m:
            return "gemini"
        return "local"

    @staticmethod
    def is_c3(model_name: str = None) -> bool:
        return LLMConfig.get_provider(model_name) == "c3"

    @staticmethod
    def is_gemini(model_name: str = None) -> bool:
        return LLMConfig.get_provider(model_name) == "gemini"

    @staticmethod
    def is_openrouter(model_name: str = None) -> bool:
        return LLMConfig.get_provider(model_name) == "openrouter"

    @staticmethod
    def is_local(model_name: str = None) -> bool:
        return LLMConfig.get_provider(model_name) == "local"

    @staticmethod
    def get_clean_model_name(model_name: str = None) -> str:
        """Limpia etiquetas visuales de UI y prefijos de enrutamiento."""
        m = (model_name or LLMConfig.get_model_name() or "").strip()
        if " " in m:
            m = m.split(" ")[0]
        if m.startswith("openrouter/"):
            m = m[len("openrouter/"):]
        if m.startswith("c3/"):
            m = m[len("c3/"):]
        if m in ("default", "openai/default"):
            return "openai/default"
        return m

    @staticmethod
    def get_auth_url(model: str = None):
        """Construye la URL base para LM Studio, Google Gemini, OpenRouter o C3 UNAM."""
        provider = LLMConfig.get_provider(model)
        if provider == "c3":
            base_url = os.getenv("C3_LLM_BASE_URL", "https://10.90.0.114/v1/")
            if not base_url.endswith("/"):
                base_url += "/"
            return base_url
        elif provider == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/openai/"
        elif provider == "openrouter":
            base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/")
            if not base_url.endswith("/"):
                base_url += "/"
            return base_url
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
        if not base_url.endswith("/"):
            base_url += "/"
        return base_url

    @staticmethod
    def get_model_name(default="openai/default"):
        return os.getenv("LLM_MODEL", default)

    @staticmethod
    def get_fallback_model_name(default="openai/default"):
        return os.getenv("FALLBACK_LLM_MODEL", default)

    @staticmethod
    def get_embedding_model_name(default="nomic-embed-text"):
        return os.getenv("EMBEDDING_MODEL", default)

    @staticmethod
    def get_api_key(model: str = None):
        provider = LLMConfig.get_provider(model)
        if provider == "c3":
            return os.getenv("C3_LLM_API_KEY", "")
        elif provider == "gemini":
            return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        elif provider == "openrouter":
            return os.getenv("OPENROUTER_API_KEY", "")
        return os.getenv("LLM_API_KEY") or os.getenv("LLM_APYKEY") or "lm-studio"

    @staticmethod
    def sanitize_input(text: str, max_chars: int = 1500) -> str:
        """Recorta y sanitiza las entradas de usuario para evitar desbordamiento de contexto."""
        if not text:
            return ""
        text = str(text).strip()
        if len(text) > max_chars:
            return text[:max_chars] + "... [Texto recortado por seguridad]"
        return text

def get_http_client(async_mode=False, timeout=60):
    """Retorna un cliente httpx configurado para saltar validación SSL (timeout por defecto 60s)."""
    if async_mode:
        return httpx.AsyncClient(verify=False, timeout=timeout)
    return httpx.Client(verify=False, timeout=timeout)

def get_openai_client(async_mode=False, model=None):
    """Retorna un cliente de OpenAI (Sincrónico o Asincrónico) para LM Studio, Gemini, OpenRouter o C3 UNAM."""
    auth_url = LLMConfig.get_auth_url(model)
    api_key = LLMConfig.get_api_key(model)
    default_headers = {}
    if LLMConfig.is_openrouter(model):
        default_headers = {
            "HTTP-Referer": "https://sinapsisai.unam.mx",
            "X-Title": "SNII Info TlachIA"
        }
    elif LLMConfig.is_c3(model):
        host_hdr = os.getenv("C3_LLM_HOST_HEADER", "kimi.c3.unam.mx")
        if host_hdr:
            default_headers = {"Host": host_hdr}
    
    if async_mode:
        return AsyncOpenAI(
            base_url=auth_url,
            api_key=api_key,
            default_headers=default_headers if default_headers else None,
            http_client=get_http_client(async_mode=True)
        )
    return OpenAI(
        base_url=auth_url,
        api_key=api_key,
        default_headers=default_headers if default_headers else None,
        http_client=get_http_client(async_mode=False)
    )

def create_structured_completion(
    client: OpenAI,
    messages: list,
    json_schema: dict,
    model: str = None,
    temperature: float = 0.0,
    max_tokens: int = 2500,
    timeout: float = 90.0
) -> dict:
    """Ejecuta una llamada con Structured Outputs (json_schema) garantizado gramaticalmente por LM Studio o Gemini."""
    import json
    raw_model = model or LLMConfig.get_model_name()
    model_name = LLMConfig.get_clean_model_name(raw_model)
    if not model_name or model_name in ("default", "openai/default"):
        model_name = "openai/default"
        
    resp = client.chat.completions.create(
        model=model_name,
        messages=messages,
        response_format={"type": "json_schema", "json_schema": json_schema},
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout
    )
    raw = resp.choices[0].message.content.strip()
    return json.loads(raw)

def get_gemini_native_model(model_name: str = "gemini-3.5-flash-lite", **kwargs):
    """Retorna una instancia nativa de GenerativeModel usando el SDK google-generativeai."""
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name=model_name, **kwargs)

def get_chat_model(temperature=0, model=None, **kwargs):
    """Retorna una instancia de ChatOpenAI (LangChain) configurada para LM Studio, Gemini, OpenRouter o C3 UNAM."""
    raw_model = model or LLMConfig.get_model_name()
    target_model = LLMConfig.get_clean_model_name(raw_model)
    auth_url = LLMConfig.get_auth_url(raw_model)
    api_key = LLMConfig.get_api_key(raw_model)
    
    headers = kwargs.pop("default_headers", {}) or {}
    if LLMConfig.is_openrouter(raw_model):
        headers.update({
            "HTTP-Referer": "https://sinapsisai.unam.mx",
            "X-Title": "SNII Info TlachIA"
        })
    elif LLMConfig.is_c3(raw_model):
        host_hdr = os.getenv("C3_LLM_HOST_HEADER", "kimi.c3.unam.mx")
        if host_hdr:
            headers.update({"Host": host_hdr})

    return ChatOpenAI(
        model=target_model,
        base_url=auth_url,
        api_key=api_key,
        http_client=get_http_client(async_mode=False),
        http_async_client=get_http_client(async_mode=True),
        temperature=temperature,
        default_headers=headers if headers else None,
        **kwargs
    )

def is_quota_exceeded_error(e: Exception) -> bool:
    """
    Detecta si una excepción corresponde a cuota agotada o rate limit (HTTP 429, RESOURCE_EXHAUSTED).
    Aplica para Google Gemini, OpenRouter y otros proveedores en la nube.
    """
    if e is None:
        return False
    try:
        from openai import RateLimitError
        if isinstance(e, RateLimitError):
            return True
    except ImportError:
        pass
        
    status_code = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    if status_code in [429, 502, 503, 504]:
        return True

    err_msg = str(e).lower()
    quota_patterns = [
        "429",
        "resource_exhausted",
        "quota",
        "rate limit",
        "ratelimit",
        "too many requests",
        "exceeded your current quota",
        "insufficient_quota",
        "out of credits",
        "credits",
        "502 bad gateway",
        "bad gateway",
        "503 service unavailable",
        "service unavailable",
        "gateway timeout"
    ]
    return any(p in err_msg for p in quota_patterns)

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
