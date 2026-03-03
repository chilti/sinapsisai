"""
strategic_council.py
Fase 1: Consejo Estratégico Virtual — AutoGen v0.4+

Consejo de 7 agentes con diversidad de expertise, género, etnia y nivel social.
Mecanismo de terminación: mayoría (4/7) declarada mediante CONSENSO_MAYORITARIO.
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
    RECTORA_APPROVAL,
    INVESTIGADOR_APPROVAL,
    BIBLIOMETRA_APPROVAL,
    POLITICA_APPROVAL,
    EVALUADORA_APPROVAL,
    CONSEJERA_APPROVAL,
    ESTUDIANTE_APPROVAL,
    CONSENSUS_SIGNAL,
    get_tools_catalog,
    get_db_schema,
)

ALL_APPROVAL_SIGNALS = [
    RECTORA_APPROVAL, INVESTIGADOR_APPROVAL, BIBLIOMETRA_APPROVAL,
    POLITICA_APPROVAL, EVALUADORA_APPROVAL, CONSEJERA_APPROVAL, ESTUDIANTE_APPROVAL,
]


def _save_consensus_plan(entity: str, messages: list) -> Path:
    slug = re.sub(r"[^\w\-]", "_", entity.lower())[:30]
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = OUTPUT_DIR / f"plan_consenso_{slug}_{date_str}.md"

    lines = [f"# Plan de Consenso Bibliométrico\n\n**Entidad**: {entity}\n**Fecha**: {date_str}\n\n---\n"]
    for msg in messages:
        src = getattr(msg, "source", "Sistema")
        raw = getattr(msg, "content", "")
        content = raw if isinstance(raw, str) else " ".join(
            b.text if hasattr(b, "text") else str(b) for b in raw
        ) if isinstance(raw, list) else str(raw)
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
    tools_catalog = get_tools_catalog()
    db_schema = get_db_schema()

    # ── 7 agentes del Consejo ──────────────────────────────────────────────────

    rectora = AssistantAgent(
        name="Rectora",
        model_client=model_client,
        system_message=(
            f"Eres la Rectora de la UNAM. Eres mujer zapoteca, la primera indígena en ocupar este cargo, "
            f"SNI III. Priorizas visibilidad internacional, impacto en comunidades vulnerables, ODS y "
            f"alianzas estratégicas. Cuestionas métricas que benefician solo a quienes publican en inglés. "
            f"Cuando el plan te convenza, escribe exactamente: '{RECTORA_APPROVAL}'. "
            f"Si ves que 4 o más colegas ya aprobaron, puedes declarar: '{CONSENSUS_SIGNAL}'."
        ),
    )

    investigador = AssistantAgent(
        name="Investigador_Campo",
        model_client=model_client,
        system_message=(
            f"Eres Investigador SNI II especialista en el área de {entity}. "
            f"Eres hombre, primera generación universitaria de familia obrera. "
            f"Conoces los retos reales de publicar desde México: falta de financiamiento, "
            f"sesgo de revistas internacionales, sobrecarga docente. "
            f"Priorizas representar fielmente la producción real del instituto, no solo la 'visible'. "
            f"Cuando el plan sea realista y honesto, escribe: '{INVESTIGADOR_APPROVAL}'."
        ),
    )

    bibliometra = AssistantAgent(
        name="Bibliometra",
        model_client=model_client,
        system_message=(
            f"Eres Dra. en Ciencia de la Ciencia y bibliometría. Eres mujer afromexicana. "
            f"Dominas indicadores: FWCI, h-index, indicadores de co-citación, mapas de ciencia, "
            f"análisis de redes de conocimiento y altmetrics. "
            f"Señalas cuando se confunde correlación con causalidad en métricas, cuando las bases "
            f"de datos tienen sesgos (Scopus solo indexa ciertos idiomas/regiones), y propones "
            f"métodos alternativos. Cuando el plan sea metodológicamente sólido: '{BIBLIOMETRA_APPROVAL}'."
        ),
    )

    politica = AssistantAgent(
        name="Politica_Cientifica",
        model_client=model_client,
        system_message=(
            f"Eres Dr. en Política Científica, ex asesor de CONAHCYT y la OCDE. "
            f"Eres hombre de origen árabe-mexicano. "
            f"Analizas cómo los resultados bibliométricos se usan (o mal usan) para tomar decisiones "
            f"de financiamiento, evaluación del SNI, presupuesto universitario y rendición de cuentas. "
            f"Alertas sobre el efecto Goodhart: cuando una métrica se convierte en objetivo, deja de "
            f"ser buena métrica. Propones conectar los hallazgos con políticas concretas. "
            f"Cuando el plan tenga relevancia política real: '{POLITICA_APPROVAL}'."
        ),
    )

    evaluadora = AssistantAgent(
        name="Evaluadora_Ciencia",
        model_client=model_client,
        system_message=(
            f"Eres especialista en evaluación de la ciencia desde perspectivas críticas y post-coloniales. "
            f"Eres mujer latinoamericana. Conoces DORA (San Francisco Declaration on Research Assessment), "
            f"el Manifiesto de Leiden y la Declaración de Madrid sobre evaluación responsable. "
            f"Cuestionas el fetichismo del factor de impacto y propones evaluaciones que incluyan ciencia "
            f"ciudadana, impacto social, diversidad lingüística y producción no indexada. "
            f"Cuando el plan evalúe la ciencia de forma responsable: '{EVALUADORA_APPROVAL}'."
        ),
    )

    consejera = AssistantAgent(
        name="Consejera_Social",
        model_client=model_client,
        system_message=(
            f"Eres Consejera universitaria especializada en equidad, género y justicia social. "
            f"Eres mujer joven de una comunidad semicampesina que llegó a la universidad con beca. "
            f"Representas a quienes la ciencia a menudo invisibiliza: investigadoras que pausaron "
            f"carreras por maternidad, personal técnico que no aparece en publicaciones, comunidades "
            f"que son objeto de estudio pero no co-autoras. "
            f"Propones desagregar todas las métricas por género, área y nivel de carrera. "
            f"Cuando el plan garantice equidad real: '{CONSEJERA_APPROVAL}'."
        ),
    )

    estudiante = AssistantAgent(
        name="Estudiante_Posgrado",
        model_client=model_client,
        system_message=(
            f"Eres estudiante de doctorado en {entity}, con beca CONAHCYT. "
            f"Eres persona no binaria. Représentas la perspectiva de quienes están construyendo "
            f"su carrera científica en condiciones precarias: becas insuficientes, contratos temporales, "
            f"presión de publicar o perecer. "
            f"Preguntas: ¿este análisis bibliométrico ayudará a los estudiantes? ¿reconoce las tesis "
            f"y trabajos no publicados? ¿promueve el acceso abierto? "
            f"Cuando el plan sea justo para las nuevas generaciones: '{ESTUDIANTE_APPROVAL}'."
        ),
    )

    # ── Terminación: mayoría (4/7) o tope de mensajes ─────────────────────────
    termination = (
        TextMentionTermination(CONSENSUS_SIGNAL) |
        MaxMessageTermination(MAX_COUNCIL_ROUNDS)
    )

    team = RoundRobinGroupChat(
        [rectora, investigador, bibliometra, politica, evaluadora, consejera, estudiante],
        termination_condition=termination,
    )

    # ── Tarea inicial ──────────────────────────────────────────────────────────
    db_schema_text = db_schema
    tools_text = tools_catalog

    approval_instructions = (
        f"Cuando estés convencido/a del plan, escribe tu señal de aprobación. "
        f"Cualquier miembro puede declarar '{CONSENSUS_SIGNAL}' si observa que 4 o más ya aprobaron."
    )

    task = (
        f"Diseñen un **Plan de Estudio Bibliométrico** para **{entity}** (UNAM).\n\n"
        f"**Objetivo del estudio**: {objective}\n\n"
        f"{db_schema_text}\n\n"
        f"**Herramientas disponibles para el análisis**:\n{tools_text}\n\n"
        f"Deliberen desde sus perspectivas únicas. El plan DEBE:\n"
        f"- Ser ejecutable con los datos y herramientas listados arriba\n"
        f"- Priorizar datos que YA EXISTEN en Neo4j/Qdrant\n"
        f"- Proponer métricas diversas (no solo factor de impacto)\n"
        f"- Considerar equidad, sesgos y diversidad en el análisis\n"
        f"- Ser útil para quienes toman decisiones de política científica\n\n"
        f"{approval_instructions}"
    )

    all_messages = []
    plan_text_parts = []

    async for message in team.run_stream(task=task):
        if isinstance(message, TaskResult):
            break
        src = getattr(message, "source", "Sistema")
        raw = getattr(message, "content", "")
        content = raw if isinstance(raw, str) else " ".join(
            b.text if hasattr(b, "text") else str(b) for b in raw
        ) if isinstance(raw, list) else str(raw)
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
