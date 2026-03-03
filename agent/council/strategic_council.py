"""
strategic_council.py
Fase 1: Consejo Estratégico Virtual — AutoGen v0.4+

Usa RoundRobinGroupChat con tres agentes de perspectivas distintas y una
condición de terminación basada en detección de texto de aprobación.
La función es síncrona (usa asyncio.run internamente) para compatibilidad con Streamlit.
"""

import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat

from .council_config import (
    make_model_client,
    OUTPUT_DIR,
    MAX_COUNCIL_ROUNDS,
    RECTOR_APPROVAL,
    INVESTIG_APPROVAL,
    CONSEJERO_APPROVAL,
)


def _save_consensus_plan(entity: str, messages: list) -> Path:
    slug = re.sub(r"[^\w\-]", "_", entity.lower())[:30]
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = OUTPUT_DIR / f"plan_consenso_{slug}_{date_str}.md"
    
    lines = [f"# Plan de Consenso Bibliométrico\n\n**Entidad**: {entity}\n**Fecha**: {date_str}\n\n---\n"]
    for msg in messages:
        src = getattr(msg, "source", "Sistema")
        raw_content = getattr(msg, "content", "")
        content = raw_content if isinstance(raw_content, str) else " ".join(
            b.text if hasattr(b, "text") else str(b) for b in raw_content
        ) if isinstance(raw_content, list) else str(raw_content)
        if content and content.strip():
            lines.append(f"### {src}\n{content}\n")
    
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


async def _run_council_async(
    entity: str,
    objective: str,
    on_message: Optional[Callable[[str, str], None]] = None,
) -> tuple[str, Path]:
    model_client = make_model_client()

    rector = AssistantAgent(
        name="Rector",
        model_client=model_client,
        system_message=(
            f"Eres el Rector de la UNAM. Priorizas VISIBILIDAD INTERNACIONAL e IMPACTO SOCIAL "
            f"de la investigación en {entity}. Criticas propuestas puramente técnicas sin impacto "
            f"institucional. Te interesan: colaboraciones internacionales, ODS, presencia en rankings, "
            f"Open Access. Cuando estés convencido del plan completo, escribe exactamente: '{RECTOR_APPROVAL}'."
        ),
    )

    investigador = AssistantAgent(
        name="Investigador_Senior",
        model_client=model_client,
        system_message=(
            f"Eres un Investigador SNI III de {entity}. Priorizas CALIDAD CIENTÍFICA: "
            f"FWCI, h-index, percentil de citas, revistas arbitradas. Cuestionas indicadores "
            f"solo cuantitativos. Defiendes el análisis de redes de coautoría y evolución histórica. "
            f"Cuando estés convencido del plan, escribe exactamente: '{INVESTIG_APPROVAL}'."
        ),
    )

    consejero = AssistantAgent(
        name="Consejero_Universitario",
        model_client=model_client,
        system_message=(
            f"Eres el Consejero responsable de ética y normativas en {entity}. "
            f"Garantizas equidad entre investigadores de distintas áreas, géneros y antigüedades. "
            f"Verificas cumplimiento de políticas de datos abiertos UNAM y ORCID. "
            f"Señalas sesgos y propones métricas de diversidad. "
            f"Cuando estés convencido del plan, escribe exactamente: '{CONSEJERO_APPROVAL}'."
        ),
    )

    # Terminar cuando los 3 han aprobado (detectamos el último en aparecer)
    termination = (
        TextMentionTermination(RECTOR_APPROVAL) &
        TextMentionTermination(INVESTIG_APPROVAL) &
        TextMentionTermination(CONSEJERO_APPROVAL)
    ) | MaxMessageTermination(MAX_COUNCIL_ROUNDS)

    team = RoundRobinGroupChat(
        [rector, investigador, consejero],
        termination_condition=termination,
    )

    task = (
        f"Diseñen un **Plan de Estudio Bibliométrico** para **{entity}** (UNAM).\n\n"
        f"**Objetivo del estudio**: {objective}\n\n"
        f"Deliberen desde sus perspectivas. El plan debe incluir:\n"
        f"1. Objetivos específicos del estudio\n"
        f"2. Métricas clave a medir (con justificación)\n"
        f"3. Fuentes de datos recomendadas\n\n"
        f"Cada uno debe aprobar explícitamente el plan final con su señal de aprobación."
    )

    all_messages = []
    plan_text_parts = []

    async for message in team.run_stream(task=task):
        if isinstance(message, TaskResult):
            break
        src = getattr(message, "source", "Sistema")
        content = getattr(message, "content", "")
        all_messages.append(message)
        if content and content.strip():
            plan_text_parts.append(f"**{src}**: {content}")
            if on_message:
                on_message(src, content)

    plan_text = "\n\n".join(plan_text_parts)
    saved_path = _save_consensus_plan(entity, all_messages)
    return plan_text, saved_path


def run_strategic_council(
    entity: str,
    objective: str,
    on_message: Optional[Callable[[str, str], None]] = None,
) -> tuple[str, Path]:
    """Punto de entrada síncrono para Streamlit."""
    return asyncio.run(_run_council_async(entity, objective, on_message))
