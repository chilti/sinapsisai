"""
council_config.py
Configuración central de AutoGen v0.4+ para el Consejo Estratégico Virtual.
Conecta al mismo servidor LM Studio configurado en .env.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from autogen_ext.models.openai import OpenAIChatCompletionClient

load_dotenv()

# ── Conexión LM Studio ────────────────────────────────────────────────────────
_user     = os.getenv("LLM_USER")
_password = os.getenv("LLM_PASSWORD")
_base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
_model    = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")

if not _base_url.endswith("/"):
    _base_url += "/"

# Basic Auth en la URL si se proporcionó
if _user and _password:
    if "://" in _base_url:
        proto, rest = _base_url.split("://", 1)
        _auth_url = f"{proto}://{_user}:{_password}@{rest}"
    else:
        _auth_url = f"http://{_user}:{_password}@{_base_url}"
else:
    _auth_url = _base_url


def make_model_client() -> OpenAIChatCompletionClient:
    """Crea un cliente de modelo apuntando a LM Studio."""
    return OpenAIChatCompletionClient(
        model=_model,
        base_url=_auth_url,
        api_key=os.getenv("LLM_API_KEY", "lm-studio"),
    )


# ── Rutas de persistencia ─────────────────────────────────────────────────────
COUNCIL_DIR = Path(__file__).parent
SCRIPTS_DIR = COUNCIL_DIR / "scripts"
OUTPUT_DIR  = COUNCIL_DIR / "output"

SCRIPTS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Parámetros de deliberación ────────────────────────────────────────────────
MAX_COUNCIL_ROUNDS = 25     # Turnos máximos en el GroupChat del Consejo
MAX_TECH_ROUNDS    = 10     # Turnos máximos en la Mesa Técnica
MAX_EXEC_RETRIES   = 3      # Reintentos del corrector de Python

# Cada agente incluye esta frase para indicar aprobación
RECTOR_APPROVAL     = "APROBADO: Rector"
INVESTIG_APPROVAL   = "APROBADO: Investigador_Senior"
CONSEJERO_APPROVAL  = "APROBADO: Consejero_Universitario"
ALL_APPROVALS       = [RECTOR_APPROVAL, INVESTIG_APPROVAL, CONSEJERO_APPROVAL]
