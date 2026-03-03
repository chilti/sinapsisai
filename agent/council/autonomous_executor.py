"""
autonomous_executor.py
Fase 3: Ejecución Autónoma con autocorrección — AutoGen v0.4+

Toma el script técnico validado (Fase 2) e invoca directamente las
herramientas reales de SINAPSIS usando un AssistantAgent con tools.
Incluye un agente corrector de Python para el bucle de autocorrección.

La entidad se inyecta como parámetro para reutilizar scripts existentes.
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core.tools import FunctionTool

from .council_config import (
    make_model_client,
    OUTPUT_DIR,
    MAX_EXEC_RETRIES,
)

# ── Importar herramientas reales de SINAPSIS ──────────────────────────────────
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from agent.tools_hybrid import (
    search_scientific_papers_semantic,
    query_knowledge_graph_cypher,
    get_entity_statistics,
    get_researcher_profile,
    get_trending_topics,
    get_author_coauthors_graph,
    recoverFromOpenAlex,
    searchAuthorInOpenAlex,
    recoverAuthorWorksFromOpenAlex,
    web_search,
    wikipedia_search,
)
from agent.tools_interpreter import execute_python_code

REPORT_DONE_SIGNAL = "INFORME_COMPLETO"

# ── Envolturas síncronas para FunctionTool ────────────────────────────────────

def _cypher(query: str) -> str:
    """Ejecuta una query Cypher en Neo4j."""
    return query_knowledge_graph_cypher.invoke({"cypher_query": query})

def _semantic(query: str, entity_context: Optional[str] = None, limit: int = 20) -> str:
    """Búsqueda semántica en Qdrant."""
    return search_scientific_papers_semantic.invoke(
        {"query": query, "entity_context": entity_context, "limit": limit}
    )

def _entity_stats(entity_name: str) -> str:
    """Estadísticas de una entidad UNAM."""
    return get_entity_statistics.invoke({"entity_name": entity_name})

def _researcher_profile(name_fragment: str) -> str:
    """Perfil completo de un investigador por nombre parcial."""
    return get_researcher_profile.invoke({"name_fragment": name_fragment})

def _trending_topics(entity_name: Optional[str] = None, start_year: int = 2018) -> str:
    """Tópicos en tendencia desde un año dado."""
    return get_trending_topics.invoke({"entity_name": entity_name, "start_year": start_year})

def _coauthors(author_name: str) -> str:
    """Red de coautores de un investigador."""
    return get_author_coauthors_graph.invoke({"author_name": author_name})

def _openalex(doi: str, fields: Optional[str] = None) -> str:
    """Registro bibliométrico de OpenAlex por DOI."""
    return recoverFromOpenAlex.invoke({"doi": doi, "fields": fields})

def _openalex_search_author(fullname: str, n: int = 5) -> str:
    """Busca un autor en OpenAlex."""
    return searchAuthorInOpenAlex.invoke({"fullname": fullname, "n": n})

def _openalex_author_works(author_id: str, n: int = 10) -> str:
    """Trabajos de un autor en OpenAlex."""
    return recoverAuthorWorksFromOpenAlex.invoke({"author_id": author_id, "n": n})

def _web(query: str) -> str:
    """Búsqueda web (DuckDuckGo)."""
    return web_search.invoke({"query": query})

def _wiki(query: str) -> str:
    """Búsqueda en Wikipedia."""
    return wikipedia_search.invoke({"query": query})

def _python(code: str) -> str:
    """Ejecuta código Python. Guarda gráficas con plt.savefig('interpreter_output.png')."""
    return execute_python_code(code)


# ── Mapa de FunctionTool para AutoGen v0.4+ ───────────────────────────────────

def _make_tools() -> list:
    return [
        FunctionTool(_cypher,              name="query_knowledge_graph_cypher",      description="Ejecuta Cypher en Neo4j"),
        FunctionTool(_semantic,            name="search_semantic",                   description="Búsqueda semántica en Qdrant"),
        FunctionTool(_entity_stats,        name="get_entity_statistics",             description="Estadísticas de una entidad UNAM"),
        FunctionTool(_researcher_profile,  name="get_researcher_profile",            description="Perfil completo de un investigador"),
        FunctionTool(_trending_topics,     name="get_trending_topics",               description="Tópicos en tendencia"),
        FunctionTool(_coauthors,           name="get_author_coauthors",              description="Red de coautores"),
        FunctionTool(_openalex,            name="openalex_doi",                      description="Datos bibliométricos por DOI"),
        FunctionTool(_openalex_search_author, name="openalex_search_author",         description="Busca autor en OpenAlex"),
        FunctionTool(_openalex_author_works,  name="openalex_author_works",          description="Trabajos de un autor en OpenAlex"),
        FunctionTool(_web,                 name="web_search",                         description="Búsqueda web"),
        FunctionTool(_wiki,                name="wikipedia",                          description="Búsqueda en Wikipedia"),
        FunctionTool(_python,              name="python_executor",                    description="Ejecuta código Python"),
    ]


# ── Utilidades ────────────────────────────────────────────────────────────────

def _inject_entity(text: str, entity: str) -> str:
    return text.replace("{ENTITY}", entity).replace("{{ENTITY}}", entity)


def _save_report(entity: str, report: str) -> Path:
    slug = re.sub(r"[^\w\-]", "_", entity.lower())[:30]
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    path = OUTPUT_DIR / f"informe_{slug}_{date_str}.md"
    path.write_text(
        f"# Informe Bibliométrico Final\n\n**Entidad**: {entity}\n**Generado**: {date_str}\n\n---\n\n"
        + report,
        encoding="utf-8"
    )
    return path


# ── Ejecución asíncrona ───────────────────────────────────────────────────────

async def _run_executor_async(
    entity: str,
    execution_script: str,
    on_message: Optional[Callable[[str, str], None]] = None,
) -> tuple[str, Path]:
    script = _inject_entity(execution_script, entity)
    model_client = make_model_client()
    tools = _make_tools()

    executor = AssistantAgent(
        name="SINAPSIS_Ejecutor",
        model_client=model_client,
        tools=tools,
        system_message=(
            f"Eres SINAPSIS en modo ejecución para la entidad **{entity}**. "
            f"Ejecuta paso a paso el script bibliométrico usando tus herramientas. "
            f"Para nombres de personas usa siempre búsqueda parcial (CONTAINS). "
            f"Para tópicos tradúcelos al inglés y usa variantes con OR. "
            f"Para gráficas siempre guarda con plt.savefig('interpreter_output.png'). "
            f"Al terminar TODOS los pasos, escribe '{REPORT_DONE_SIGNAL}' seguido "
            f"del informe final en Markdown con: síntesis ejecutiva, tablas de datos, "
            f"interpretación de Rector/Investigador/Consejero y conclusiones."
        ),
    )

    termination = (
        TextMentionTermination(REPORT_DONE_SIGNAL) |
        MaxMessageTermination(30)
    )
    team = RoundRobinGroupChat([executor], termination_condition=termination)

    report_parts = []
    all_parts = []

    async for message in team.run_stream(task=f"Ejecuta el siguiente script para {entity}:\n\n{script}"):
        if isinstance(message, TaskResult):
            break
        src = getattr(message, "source", "Sistema")
        content = getattr(message, "content", "")
        if content and content.strip():
            all_parts.append(f"**{src}**: {content}")
            if REPORT_DONE_SIGNAL in content:
                idx = content.find(REPORT_DONE_SIGNAL)
                report_parts.append(content[idx + len(REPORT_DONE_SIGNAL):].strip())
            if on_message:
                on_message(src, content)

    report_text = "\n\n".join(report_parts) if report_parts else "\n\n".join(all_parts[-5:])
    saved_path = _save_report(entity, report_text)
    return report_text, saved_path


def run_autonomous_executor(
    entity: str,
    execution_script: str,
    on_message: Optional[Callable[[str, str], None]] = None,
    on_step: Optional[Callable[[int, int], None]] = None,
) -> tuple[str, Path]:
    """Punto de entrada síncrono para Streamlit."""
    return asyncio.run(_run_executor_async(entity, execution_script, on_message))
