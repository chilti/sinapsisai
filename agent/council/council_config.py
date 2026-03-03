"""
council_config.py
Configuración central de AutoGen para el Consejo Estratégico Virtual.
Se conecta al mismo servidor LM Studio configurado en .env.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Conexión LM Studio ────────────────────────────────────────────────────────
_user = os.getenv("LLM_USER")
_password = os.getenv("LLM_PASSWORD")
_base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
_model = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")

# Construir URL con auth básica si se proporcionó
if _user and _password:
    if "://" in _base_url:
        proto, rest = _base_url.split("://", 1)
        _auth_url = f"{proto}://{_user}:{_password}@{rest}"
    else:
        _auth_url = f"http://{_user}:{_password}@{_base_url}"
else:
    _auth_url = _base_url

# Config list para AutoGen
CONFIG_LIST = [{
    "model": _model,
    "base_url": _auth_url,
    "api_key": os.getenv("LLM_API_KEY", "lm-studio"),
}]

LLM_CONFIG = {
    "config_list": CONFIG_LIST,
    "temperature": 0.4,
    "timeout": 300,
    "cache_seed": None,  # Desactivar caché para respuestas siempre frescas
}

# ── Rutas de persistencia ─────────────────────────────────────────────────────
COUNCIL_DIR = Path(__file__).parent
SCRIPTS_DIR = COUNCIL_DIR / "scripts"
OUTPUT_DIR  = COUNCIL_DIR / "output"

SCRIPTS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Parámetros de deliberación ────────────────────────────────────────────────
MAX_COUNCIL_ROUNDS = 25       # Máximo de turnos en el GroupChat del Consejo
MAX_TECH_ROUNDS    = 10       # Máximo de turnos en la Mesa Técnica
MAX_EXEC_RETRIES   = 3        # Reintentos del bucle de autocorrección de código

# Señal de consenso que el GroupChatManager busca en los mensajes
CONSENSUS_SIGNAL   = "PLAN APROBADO"
