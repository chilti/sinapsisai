"""
autonomous_executor.py
Fase 3 del sistema multi-agente: Ejecución Autónoma con autocorrección.

Toma el script técnico validado (Fase 2) y lo ejecuta paso a paso usando
las herramientas reales de SINAPSIS (Neo4j, Qdrant, OpenAlex, Python).

Incluye:
- Inyección de la entidad como parámetro (re-uso del script con otra entidad)
- Bucle de autocorrección para errores en código Python
- Generación del informe final en Markdown
"""

import re
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, AsyncGenerator

from autogen import AssistantAgent, UserProxyAgent

from .council_config import (
    LLM_CONFIG,
    OUTPUT_DIR,
    MAX_EXEC_RETRIES,
)

# Las herramientas reales de SINAPSIS (mismo módulo que el orquestador)
import sys
import os
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


# ── Mapa de herramientas disponibles ──────────────────────────────────────────

TOOL_MAP = {
    "query_knowledge_graph_cypher":      lambda args: query_knowledge_graph_cypher.invoke(args),
    "search_scientific_papers_semantic": lambda args: search_scientific_papers_semantic.invoke(args),
    "get_entity_statistics":             lambda args: get_entity_statistics.invoke(args),
    "get_researcher_profile":            lambda args: get_researcher_profile.invoke(args),
    "get_trending_topics":               lambda args: get_trending_topics.invoke(args),
    "get_author_coauthors_graph":        lambda args: get_author_coauthors_graph.invoke(args),
    "recoverFromOpenAlex":               lambda args: recoverFromOpenAlex.invoke(args),
    "searchAuthorInOpenAlex":            lambda args: searchAuthorInOpenAlex.invoke(args),
    "recoverAuthorWorksFromOpenAlex":    lambda args: recoverAuthorWorksFromOpenAlex.invoke(args),
    "web_search":                        lambda args: web_search.invoke(args),
    "wikipedia_search":                  lambda args: wikipedia_search.invoke(args),
    "Python_CodeExecutor":               lambda args: execute_python_code(args.get("query", "")),
}


# ── Agente Ejecutor ────────────────────────────────────────────────────────────

def _build_executor(entity: str) -> AssistantAgent:
    tools_list = "\n".join([f"  - {k}" for k in TOOL_MAP.keys()])
    return AssistantAgent(
        name="SINAPSIS_Ejecutor",
        system_message=f"""Eres SINAPSIS en modo ejecución autónoma. Tu objetivo es generar un
informe bibliométrico completo para la entidad **{entity}**.

Tienes acceso a las siguientes herramientas (úsalas indicándolas con JSON):
{tools_list}

Para usar una herramienta, escribe exactamente:
```json
{{"tool": "nombre_herramienta", "args": {{"param1": "valor1"}}}}
```

REGLAS CRÍTICAS:
- Para nombres de académicos: SIEMPRE usa búsqueda parcial con el apellido.
- Para tópicos: tradúcelos al inglés y usa variantes con OR en Cypher.
- Para gráficas de Python: SIEMPRE guarda con plt.savefig('interpreter_output.png').
- Si un paso falla, analiza el error e intenta una alternativa antes de reportar fallo.
- Al terminar escribe: INFORME_COMPLETO seguido del informe final en Markdown.

El informe final debe contener:
1. Síntesis ejecutiva (2-3 párrafos)
2. Tablas de datos con los resultados más relevantes
3. Interpretación desde la perspectiva del Rector, Investigador y Consejero
4. Conclusiones y recomendaciones""",
        llm_config=LLM_CONFIG,
    )


def _build_corrector() -> AssistantAgent:
    return AssistantAgent(
        name="Corrector_Python",
        system_message="""Eres un experto en Python que corrige código con errores.
Cuando recibas un fragmento de código con su error, devuelve SOLO el código corregido
en un bloque ```python ... ``` sin explicaciones adicionales.
Asegúrate de que el código importa todo lo que necesita y no tiene dependencias externas
que no estén disponibles en un entorno Python estándar con pandas, matplotlib y numpy.""",
        llm_config=LLM_CONFIG,
    )


# ── Ejecución de herramientas ──────────────────────────────────────────────────

def _inject_entity(script_text: str, entity: str) -> str:
    """Reemplaza el placeholder {ENTITY} con la entidad real."""
    return script_text.replace("{ENTITY}", entity).replace("{{ENTITY}}", entity)


def _extract_tool_call(text: str) -> Optional[dict]:
    """Extrae la primera llamada a herramienta del texto del agente."""
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


def _execute_tool_with_retry(tool_call: dict, corrector: AssistantAgent, moderador: UserProxyAgent) -> str:
    """Ejecuta una herramienta con bucle de autocorrección para Python."""
    tool_name = tool_call.get("tool", "")
    args = tool_call.get("args", {})

    if tool_name not in TOOL_MAP:
        return f"❌ Herramienta '{tool_name}' no disponible."

    # Herramientas Python tienen autocorrección
    if tool_name == "Python_CodeExecutor":
        code = args.get("query", "")
        for attempt in range(MAX_EXEC_RETRIES):
            result = execute_python_code(code)
            if "Error" not in result and "Traceback" not in result:
                return result
            if attempt < MAX_EXEC_RETRIES - 1:
                # Pedir corrección al agente corrector
                moderador.initiate_chat(
                    corrector,
                    message=f"Corrige este código Python que generó el siguiente error:\n\n"
                            f"```python\n{code}\n```\n\nError:\n{result}",
                    max_turns=1,
                )
                corrected_msg = corrector.last_message()
                if corrected_msg:
                    code_match = re.search(r"```python\s*(.*?)\s*```", corrected_msg["content"], re.DOTALL)
                    if code_match:
                        code = code_match.group(1)
        return result  # Devuelve el último resultado aunque tenga error
    else:
        try:
            return TOOL_MAP[tool_name](args)
        except Exception as e:
            return f"❌ Error en {tool_name}: {str(e)}"


# ── Guardado del informe ──────────────────────────────────────────────────────

def _save_final_report(entity: str, report_text: str) -> Path:
    slug = re.sub(r"[^\w\-]", "_", entity.lower())[:30]
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = OUTPUT_DIR / f"informe_{slug}_{date_str}.md"
    filename.write_text(
        f"# Informe Bibliométrico Final\n\n"
        f"**Entidad**: {entity}\n"
        f"**Generado**: {date_str}\n\n---\n\n"
        + report_text,
        encoding="utf-8"
    )
    return filename


# ── Función principal ──────────────────────────────────────────────────────────

def run_autonomous_executor(
    entity: str,
    execution_script: str,
    on_message: Optional[Callable[[str, str], None]] = None,
    on_step: Optional[Callable[[int, int], None]] = None,
) -> tuple[str, Path]:
    """
    Ejecuta la Fase 3: Ejecución Autónoma con autocorrección.

    Args:
        entity: Entidad objetivo (puede diferir de la que generó el script)
        execution_script: Script validado por la Mesa Técnica (Fase 2)
        on_message: Callback de streaming para la UI (nombre_agente, contenido)
        on_step: Callback de progreso (paso_actual, total_pasos)

    Returns:
        Tuple de (informe_texto: str, archivo_guardado: Path)
    """
    # Inyectar la entidad actual en el script (re-uso paramétrico)
    script_with_entity = _inject_entity(execution_script, entity)

    executor = _build_executor(entity)
    corrector = _build_corrector()

    moderador = UserProxyAgent(
        name="Supervisor_Ejecución",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=0,
        code_execution_config=False,
    )

    # Buffer de resultados de herramientas para comprimir el contexto
    tool_results = []
    step_count = [0]
    report_text = [""]

    def _process_agent_message(content: str) -> str:
        """Detecta llamadas a herramientas en el mensaje y las ejecuta."""
        tool_call = _extract_tool_call(content)
        if not tool_call:
            return content

        step_count[0] += 1
        tool_name = tool_call.get("tool", "")
        if on_message:
            on_message("Sistema", f"⚙️ Ejecutando herramienta: `{tool_name}`...")

        result = _execute_tool_with_retry(tool_call, corrector, moderador)
        tool_results.append({"tool": tool_name, "result": str(result)[:2000]})

        if on_message:
            on_message("Sistema", f"✅ `{tool_name}` completado.")

        return content + f"\n\n**Resultado de {tool_name}:**\n```\n{str(result)[:2000]}\n```"

    # Conversación principal con el ejecutor
    step_messages = []

    def _reply_handler(sender, message, recipient, **kwargs):
        """Intercepta respuestas del ejecutor para procesar tool calls."""
        content = message if isinstance(message, str) else message.get("content", "")
        name = getattr(sender, "name", "Sistema")

        if on_message and content:
            on_message(name, content)

        # Si contiene llamada a herramienta, ejecutar y devolver resultado
        if "```json" in content and '"tool"' in content:
            enriched = _process_agent_message(content)
            step_messages.append(enriched)
            return True, enriched

        # Si contiene INFORME_COMPLETO, extraer y terminar
        if "INFORME_COMPLETO" in content:
            idx = content.find("INFORME_COMPLETO")
            report_text[0] = content[idx + len("INFORME_COMPLETO"):].strip()
            return True, None  # Terminar conversación

        step_messages.append(content)
        return False, None

    moderador.register_reply(
        trigger=executor.__class__,
        reply_func=_reply_handler,
        position=0,
    )

    moderador.initiate_chat(
        executor,
        message=(
            f"Ejecuta el siguiente script bibliométrico para **{entity}**. "
            f"Para cada paso, usa la herramienta correspondiente en formato JSON.\n\n"
            f"{script_with_entity}\n\n"
            f"Al terminar todos los pasos, genera el INFORME_COMPLETO."
        ),
        max_turns=30,
    )

    # Si el informe no se generó explícitamente, usar el último mensaje
    if not report_text[0] and step_messages:
        report_text[0] = "\n\n".join(step_messages[-3:])

    saved_path = _save_final_report(entity, report_text[0])
    return report_text[0], saved_path
