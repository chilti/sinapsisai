"""
api/routers/assistant.py - Router para el asistente conversacional con streaming SSE
"""
import json
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from agent.orchestrator import RAGOrchestrator

router = APIRouter(prefix="/api/assistant", tags=["Asistente IA"])

# Singleton del orquestador
_orchestrator = None

def get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = RAGOrchestrator()
    return _orchestrator

class ChatMessageRequest(BaseModel):
    query: Optional[str] = None
    question: Optional[str] = None
    session_id: Optional[str] = "default_session"
    ui_context: Optional[str] = None
    model: Optional[str] = None
    model_type: Optional[str] = None

@router.post("/chat")
@router.post("/ask")
async def stream_assistant_chat(req: ChatMessageRequest):
    """
    Endpoint SSE (Server-Sent Events) que transmite en vivo el proceso de razonamiento:
    - Eventos de herramientas ejecutadas (tool_start, tool_end con Cypher, SQL, o Web).
    - Respuesta analítica del asistente token a token.
    Formato de salida: data: {"type": "...", ...}\n\n
    """
    user_query = req.query or req.question or ""
    if not user_query:
        raise HTTPException(status_code=400, detail="Debe proporcionar un texto de consulta (query o question)")

    orch = get_orchestrator()
    model_name = req.model or req.model_type
    if model_name:
        orch.update_model(model_name)

    async def event_generator():
        try:
            async for item in orch.ask_stream(
                session_id=req.session_id,
                query=user_query,
                ui_context=req.ui_context
            ):
                payload = json.dumps(item)
                yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            err_payload = json.dumps({"type": "error", "error": str(e)})
            yield f"data: {err_payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/clear")
def clear_chat_session(session_id: str = "default_session") -> Dict[str, Any]:
    """Limpia el historial y la memoria de contexto de la sesión."""
    orch = get_orchestrator()
    orch.clear_session(session_id)
    return {"status": "success", "session_id": session_id}

class TestModelRequest(BaseModel):
    model: str = "gpt-oss-120b"

@router.get("/models")
def list_available_models() -> Dict[str, Any]:
    """Retorna los modelos disponibles configurados en el sistema."""
    import os
    has_c3_gpt = bool(os.getenv("C3_LLM_API_KEY_GPT"))
    has_c3_kimi = bool(os.getenv("C3_LLM_API_KEY"))
    has_gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    
    models = []
    if has_c3_gpt:
        models.append({
            "id": "gpt-oss-120b",
            "name": "C3 UNAM - GPT-OSS 120B (120 Billones)",
            "provider": "c3_gpt",
            "description": "Modelo de pesos abiertos OpenAI GPT-OSS (120 Billones) alojado en cluster vLLM del C3 UNAM con 131k de contexto.",
            "is_admin_only": True,
            "badge": "C3 vLLM 120B"
        })
    if has_c3_kimi:
        models.append({
            "id": "Kimi-K2.6",
            "name": "C3 UNAM - Kimi K2.6",
            "provider": "c3",
            "description": "Servidor vLLM del C3 UNAM (Kimi K2.6).",
            "is_admin_only": True,
            "badge": "C3 vLLM"
        })
    models.append({
        "id": "openai/default",
        "name": "LM Studio Local (gpt-oss-20b)",
        "provider": "local",
        "description": "Instancia local en servidor (LM Studio).",
        "is_admin_only": False,
        "badge": "Local"
    })
    if has_gemini:
        models.append({
            "id": "gemini-3.5-flash-lite",
            "name": "Google Gemini 3.5 Flash",
            "provider": "gemini",
            "description": "API en la nube de Google Gemini.",
            "is_admin_only": False,
            "badge": "Google Cloud"
        })
    return {"status": "success", "models": models}

@router.post("/test-model")
def test_model_connection(req: TestModelRequest) -> Dict[str, Any]:
    """Prueba la conectividad y latencia con un modelo específico (ej. C3 vLLM gpt-oss-120b)."""
    import time
    from lib.llm_utils import LLMConfig, get_openai_client
    t0 = time.time()
    try:
        client = get_openai_client(model=req.model)
        target_name = LLMConfig.get_clean_model_name(req.model)
        res = client.chat.completions.create(
            model=target_name,
            messages=[{"role": "user", "content": "Ping test: responde solo con la palabra 'OK'"}],
            max_tokens=250,
            timeout=15.0
        )
        latency = round((time.time() - t0) * 1000)
        content = res.choices[0].message.content or "OK"
        return {
            "status": "success",
            "model": req.model,
            "resolved_model": target_name,
            "latency_ms": latency,
            "reply": content.strip()
        }
    except Exception as e:
        latency = round((time.time() - t0) * 1000)
        return {
            "status": "error",
            "model": req.model,
            "latency_ms": latency,
            "error": str(e)
        }

