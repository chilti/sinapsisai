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
    query: str
    session_id: Optional[str] = "default_session"
    ui_context: Optional[str] = None
    model: Optional[str] = None

@router.post("/chat")
def stream_assistant_chat(req: ChatMessageRequest):
    """
    Endpoint SSE (Server-Sent Events) que transmite la respuesta del asistente token a token.
    Formato de salida: data: {"token": "..."}\n\n
    """
    orch = get_orchestrator()
    if req.model:
        orch.update_model(req.model)

    def event_generator():
        try:
            for chunk in orch.ask_lightweight_stream_sync(
                session_id=req.session_id,
                query=req.query,
                ui_context=req.ui_context
            ):
                payload = json.dumps({"token": chunk})
                yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            err_payload = json.dumps({"error": str(e)})
            yield f"data: {err_payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/clear")
def clear_chat_session(session_id: str = "default_session") -> Dict[str, Any]:
    """Limpia el historial y la memoria de contexto de la sesión."""
    orch = get_orchestrator()
    orch.clear_session(session_id)
    return {"status": "success", "session_id": session_id}
