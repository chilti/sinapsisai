"""
strategic_council.py
Fase 1 del sistema multi-agente: Consejo Estratégico Virtual.

Orquesta un GroupChat de AutoGen con tres agentes de perspectivas distintas
(Rector, Investigador Senior, Consejero Universitario) para deliberar y llegar
a un consenso bibliométrico sobre una entidad UNAM.

El resultado se guarda como plan_consenso.md en agent/council/output/.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from autogen import (
    AssistantAgent,
    GroupChat,
    GroupChatManager,
    UserProxyAgent,
)

from .council_config import (
    LLM_CONFIG,
    OUTPUT_DIR,
    SCRIPTS_DIR,
    MAX_COUNCIL_ROUNDS,
    CONSENSUS_SIGNAL,
)


# ── Definición de los agentes del Consejo ─────────────────────────────────────

def _build_rector(entity: str) -> AssistantAgent:
    return AssistantAgent(
        name="Rector",
        system_message=f"""Eres el Rector de la UNAM, responsable de la visión estratégica y política universitaria.

Tu perspectiva al analizar la producción científica de "{entity}":
- Priorizas la VISIBILIDAD INTERNACIONAL y el IMPACTO SOCIAL de la investigación.
- Criticas propuestas que sean puramente técnicas y no resalten el PRESTIGIO INSTITUCIONAL.
- Te interesan los Objetivos de Desarrollo Sostenible (ODS), las colaboraciones internacionales
  y la presencia en rankings globales.
- Propones indicadores como: presencia en revistas de alto impacto, colaboraciones con
  universidades del top-100, publicaciones ligadas a ODS, cobertura de Open Access.

Cuando estés de acuerdo con un plan completo, incluye el texto "APROBADO: Rector" en tu mensaje.""",
        llm_config=LLM_CONFIG,
    )


def _build_investigador_senior(entity: str) -> AssistantAgent:
    return AssistantAgent(
        name="Investigador_Senior",
        system_message=f"""Eres un Investigador Senior nivel SNI III de "{entity}".

Tu perspectiva al diseñar un estudio bibliométrico:
- Priorizas la CALIDAD CIENTÍFICA: FWCI, percentil de citas, h-index, revistas arbitradas.
- Cuestionas indicadores SOLO cuantitativos (número de papers) que no reflejen profundidad.
- Te importa la coherencia disciplinar: que los tópicos medidos sean relevantes para el área.
- Defiendes el análisis de redes de coautoría porque revela colaboraciones estratégicas reales.
- Propones incluir comparativas históricas (evolución por quinquenios) y análisis temático.

Cuando estés de acuerdo con un plan completo, incluye el texto "APROBADO: Investigador_Senior" en tu mensaje.""",
        llm_config=LLM_CONFIG,
    )


def _build_consejero(entity: str) -> AssistantAgent:
    return AssistantAgent(
        name="Consejero_Universitario",
        system_message=f"""Eres el Consejero Universitario responsable de la ética y normativas de "{entity}".

Tu perspectiva en el diseño del estudio:
- Garantizas EQUIDAD entre investigadores de diferentes áreas, géneros y antigüedades.
- Verificas que el estudio cumpla con la política de datos abiertos de la UNAM y ORCID.
- Señalas si alguna métrica podría discriminar injustamente a investigadores emergentes o
  de áreas menos financiadas.
- Propones incluir métricas de diversidad (género, área temática, trayectoria) y transparencia.
- Te aseguras de que los datos usados sean éticamente obtenidos y estén correctamente atribuidos.

Cuando estés de acuerdo con un plan completo, incluye el texto "APROBADO: Consejero_Universitario" en tu mensaje.""",
        llm_config=LLM_CONFIG,
    )


# ── Lógica de consenso ────────────────────────────────────────────────────────

def _check_consensus(messages: list) -> bool:
    """Verifica si los tres agentes han dado su aprobación."""
    combined = " ".join(m.get("content", "") for m in messages)
    return all([
        "APROBADO: Rector" in combined,
        "APROBADO: Investigador_Senior" in combined,
        "APROBADO: Consejero_Universitario" in combined,
    ])


def _extract_plan(messages: list) -> str:
    """Extrae y sintetiza el plan de consenso de la conversación."""
    lines = []
    for msg in messages:
        name = msg.get("name", "")
        content = msg.get("content", "")
        if name and content:
            lines.append(f"### {name}\n{content}\n")
    return "\n".join(lines)


def _save_consensus_plan(entity: str, plan_text: str) -> Path:
    """Guarda el plan de consenso como Markdown en output/."""
    slug = re.sub(r"[^\w\-]", "_", entity.lower())[:30]
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = OUTPUT_DIR / f"plan_consenso_{slug}_{date_str}.md"
    filename.write_text(
        f"# Plan de Consenso Bibliométrico\n\n"
        f"**Entidad**: {entity}\n"
        f"**Fecha**: {date_str}\n\n---\n\n"
        + plan_text,
        encoding="utf-8"
    )
    return filename


# ── Función principal ─────────────────────────────────────────────────────────

def run_strategic_council(
    entity: str,
    objective: str,
    on_message: Optional[Callable[[str, str], None]] = None,
) -> tuple[str, Path]:
    """
    Ejecuta la Fase 1: Deliberación del Consejo Estratégico.

    Args:
        entity: Nombre de la entidad UNAM (ej. "Instituto de Ciencias Nucleares")
        objective: Objetivo del estudio que el usuario definió
        on_message: Callback opcional para streaming a la UI (nombre_agente, contenido)

    Returns:
        Tuple de (plan_texto: str, archivo_guardado: Path)
    """
    rector = _build_rector(entity)
    investigador = _build_investigador_senior(entity)
    consejero = _build_consejero(entity)

    # Proxy que inicia la conversación pero no interrumpe (human_input_mode=NEVER)
    initiator = UserProxyAgent(
        name="Moderador",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=0,
        code_execution_config=False,
    )

    # GroupChat con selección automática de turno
    group_chat = GroupChat(
        agents=[initiator, rector, investigador, consejero],
        messages=[],
        max_round=MAX_COUNCIL_ROUNDS,
        speaker_selection_method="auto",
    )

    manager = GroupChatManager(
        groupchat=group_chat,
        llm_config=LLM_CONFIG,
        is_termination_msg=lambda msg: _check_consensus(group_chat.messages),
    )

    # Hook de streaming hacia la UI
    if on_message:
        original_send = manager.send

        def patched_send(message, recipient, **kwargs):
            if isinstance(message, dict):
                name = message.get("name", "Sistema")
                content = message.get("content", "")
                on_message(name, content)
            return original_send(message, recipient, **kwargs)

        manager.send = patched_send

    # Mensaje inicial que lanza la deliberación
    initiator.initiate_chat(
        manager,
        message=(
            f"Necesitamos diseñar un **Plan de Estudio Bibliométrico** para la entidad "
            f"**{entity}** de la UNAM.\n\n"
            f"**Objetivo del estudio:** {objective}\n\n"
            f"Por favor deliberen desde sus perspectivas y lleguen a un plan consensuado "
            f"que incluya: (1) Objetivos específicos, (2) Métricas clave a medir, "
            f"(3) Justificación académica e institucional.\n\n"
            f"La conversación termina solo cuando los tres hayan aprobado el plan con "
            f"la señal 'APROBADO: [su nombre]'."
        ),
    )

    plan_text = _extract_plan(group_chat.messages)
    saved_path = _save_consensus_plan(entity, plan_text)

    return plan_text, saved_path
