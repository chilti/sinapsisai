"""
technical_mesa.py
Fase 2: Mesa Técnica — AutoGen v0.4+

Dos agentes en conversación secuencial:
1. Arquitecto_de_Datos: traduce el plan a requerimientos técnicos concretos con Cypher/Qdrant/Python.
2. SINAPSIS_Técnico: valida qué pasos puede ejecutar con sus herramientas actuales.

El script resultante se guarda en scripts/ de forma parametrizable ({ENTITY}).
"""

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Union

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat

from .council_config import (
    make_model_client,
    SCRIPTS_DIR,
    MAX_TECH_ROUNDS,
    get_tools_catalog,
    get_db_schema,
)

SCRIPT_DONE_SIGNAL = "SCRIPT_VALIDADO"


def _save_execution_script(entity: str, script_text: str) -> Path:
    slug = re.sub(r"[^\w\-]", "_", entity.lower())[:30]
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = SCRIPTS_DIR / f"{slug}_{date_str}.md"
    path.write_text(
        f"# Script de Ejecución Bibliométrica\n\n"
        f"**Entidad por defecto**: {entity}\n"
        f"**Fecha**: {date_str}\n"
        f"**Re-uso**: reemplaza {{ENTITY}} con otra entidad al ejecutar.\n\n---\n\n"
        + script_text,
        encoding="utf-8"
    )
    return path


def load_execution_script(script_path: Union[str, Path]) -> str:
    path = Path(script_path)
    if not path.exists():
        raise FileNotFoundError(f"Script no encontrado: {script_path}")
    return path.read_text(encoding="utf-8")


def list_saved_scripts() -> list:
    scripts = []
    for f in sorted(SCRIPTS_DIR.glob("*.md"), reverse=True):
        parts = f.stem.rsplit("_", 1)
        scripts.append({
            "filename": f.name,
            "path": str(f),
            "entity_slug": parts[0] if len(parts) > 1 else f.stem,
            "date": parts[1] if len(parts) > 1 else "desconocida",
        })
    return scripts


async def _run_mesa_async(
    entity: str,
    consensus_plan: str,
    on_message: Optional[Callable[[str, str], None]] = None,
) -> tuple[str, Path]:
    model_client = make_model_client()
    tools_catalog = get_tools_catalog()  # Catálogo REAL de herramientas
    db_schema = get_db_schema()          # Esquema real de Neo4j + Qdrant

    arquitecto = AssistantAgent(
        name="Arquitecto_de_Datos",
        model_client=model_client,
        system_message=(
            f"Eres un Arquitecto de Datos especializado en bibliometría para la entidad {entity}.\n\n"
            f"{db_schema}\n\n"
            f"{tools_catalog}\n\n"
            f"REGLAS DE DISEÑO DEL SCRIPT:\n"
            f"- Usa PRIMERO los datos que ya existen en Neo4j/Qdrant (ver esquema arriba).\n"
            f"- Solo llama a OpenAlex/Scopus/web para datos que NO estén en las bases.\n"
            f"- Solo propón pasos que usen las herramientas listadas. NUNCA inventes otras.\n"
            f"- Para Neo4j usa CONTAINS para nombres de personas:\n"
            f"  WHERE toLower(a.name) CONTAINS toLower('apellido')\n"
            f"- Los tópicos en Neo4j están en inglés. Traduce siempre.\n"
            f"- Para búsqueda semántica usa search_scientific_papers_semantic con entity_context=\"{{ENTITY}}\".\n"
            f"- La herramienta get_author_coauthors_graph RÉQUIERE el nombre de un INVESTIGADOR (persona), NO el nombre de una institución.\n"
            f"- REGLA CRÍTICA: El Python_CodeExecutor NO puede llamar a otras herramientas como query_knowledge_graph_cypher. "
            f"  Debes extraer los datos primero con la herramienta de Cypher, y luego pasar los resultados al bloque Python."
            f"- Cuando termines el script completo, escribe: SCRIPT_TÉCNICO_LISTO"
        ),
    )

    sinapsis = AssistantAgent(
        name="SINAPSIS_Tecnico",
        model_client=model_client,
        system_message=(
            f"Eres SINAPSIS en modo revision tecnica.\n\n"
            f"{tools_catalog}\n\n"
            f"Revisa el script propuesto por el Arquitecto:\n"
            f"- Para cada paso: indica ✅ si puedes ejecutarlo o ❌ si no puedes (con motivo claro).\n"
            f"- Si un paso usa herramientas inexistentes, corrígelo con la alternativa real.\n"
            f"- Asegúrate de que TODOS los pasos usan SOLO herramientas del catálogo.\n"
            f"- Cuando el script sea ejecutable al 100%, escribe exactamente: {SCRIPT_DONE_SIGNAL}"
        ),
    )

    termination = (
        TextMentionTermination(SCRIPT_DONE_SIGNAL) |
        MaxMessageTermination(MAX_TECH_ROUNDS)
    )

    team = RoundRobinGroupChat(
        [arquitecto, sinapsis],
        termination_condition=termination,
    )

    task = (
        f"El Consejo Estratégico aprobó el siguiente plan para **{entity}**:\n\n"
        f"{consensus_plan}\n\n"
        f"Arquitecto: traduce este plan a un script técnico con pasos concretos usando {{ENTITY}} "
        f"como placeholder. SINAPSIS: revisa y valida qué pasos puedes ejecutar."
    )

    parts = []
    async for message in team.run_stream(task=task):
        if isinstance(message, TaskResult):
            break
        src = getattr(message, "source", "Sistema")
        raw_content = getattr(message, "content", "")
        content = raw_content if isinstance(raw_content, str) else " ".join(
            b.text if hasattr(b, "text") else str(b) for b in raw_content
        ) if isinstance(raw_content, list) else str(raw_content)
        if content and content.strip():
            parts.append(f"### {src}\n{content}")
            if on_message:
                on_message(src, content)

    # Extraemos el último mensaje del Arquitecto (que contiene el script final corregido)
    # o el bloque de código principal del script.
    final_script = ""
    for part in reversed(parts):
        if "Arquitecto_de_Datos" in part and "###" in part:
            final_script = part
            break
    
    if not final_script:
        final_script = "\n\n".join(parts[-4:]) # Al menos los últimos mensajes si no se detecta el rol

    saved_path = _save_execution_script(entity, final_script)
    return final_script, saved_path


def run_technical_mesa(
    entity: str,
    consensus_plan: str,
    on_message: Optional[Callable[[str, str], None]] = None,
) -> tuple[str, Path]:
    """Punto de entrada síncrono para Streamlit."""
    return asyncio.run(_run_mesa_async(entity, consensus_plan, on_message))
