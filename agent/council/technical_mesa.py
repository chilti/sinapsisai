"""
technical_mesa.py
Fase 2 del sistema multi-agente: Mesa Técnica.

Lee el plan_consenso.md generado por el Consejo y lo traduce a un script
de ejecución técnica concreto y parametrizable.

Los scripts se guardan en agent/council/scripts/ con nombre:
    {entity_slug}_{fecha}.md

Pueden ser re-ejecutados con cualquier entidad sin repetir la deliberación.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Union

from autogen import AssistantAgent, UserProxyAgent, ConversableAgent

from .council_config import (
    LLM_CONFIG,
    SCRIPTS_DIR,
    OUTPUT_DIR,
    MAX_TECH_ROUNDS,
)


# ── Agentes de la Mesa Técnica ─────────────────────────────────────────────────

def _build_arquitecto() -> AssistantAgent:
    return AssistantAgent(
        name="Arquitecto_de_Datos",
        system_message="""Eres un Arquitecto de Datos especializado en sistemas bibliométricos.

Tu trabajo es leer el Plan de Estudio Bibliométrico aprobado por el Consejo y
traducirlo a requerimientos técnicos concretos. Para cada objetivo del plan debes
especificar exactamente:

1. Si usa Neo4j (grafo): escribe la query Cypher necesaria.
   - Schema disponible: (Academic)-[:AUTHORED]->(Paper), (Academic)-[:AFFILIATED_TO]->(Entity),
     (Paper)-[:HAS_TOPIC]->(Topic), (Paper)-[:HAS_SDG]->(SDG_Goal)
   - IMPORTANTE: Los nombres de académicos están en formato 'APELLIDO, NOMBRE' en mayúsculas.
     Siempre usar CONTAINS para buscar personas.

2. Si usa Qdrant (semántica): especifica el query semántico y si necesita entity_context.

3. Si usa OpenAlex: especifica qué campos extraer (fwci, cited_by_count, topics, etc.)

4. Si necesita Python para cálculo/visualización: describe el análisis.

Formatea tu respuesta como un script de ejecución en secciones claras.
Usa la variable {{ENTITY}} como placeholder para la entidad, para que el script sea reutilizable.

Termina con: SCRIPT_TÉCNICO_COMPLETO""",
        llm_config=LLM_CONFIG,
    )


def _build_sinapsis_tecnico() -> AssistantAgent:
    return AssistantAgent(
        name="SINAPSIS_Técnico",
        system_message="""Eres SINAPSIS en modo técnico. Tu trabajo es revisar el script
propuesto por el Arquitecto y:

1. Confirmar qué pasos puedes ejecutar con tus herramientas actuales:
   - query_knowledge_graph_cypher (Neo4j)
   - search_scientific_papers_semantic (Qdrant)
   - get_entity_statistics, get_researcher_profile, get_trending_topics
   - recoverFromOpenAlex, searchAuthorInOpenAlex, recoverAuthorWorksFromOpenAlex
   - get_author_coauthors_graph
   - Python_CodeExecutor
   - web_search, wikipedia_search

2. Señalar qué pasos NO puedes ejecutar con las herramientas actuales y por qué.
   Registra las herramientas faltantes con detalle.

3. Sugerir alternativas para los pasos que no puedes cubrir directamente.

4. Aprobar el script final con: SCRIPT_VALIDADO_POR_SINAPSIS""",
        llm_config=LLM_CONFIG,
    )


# ── Persistencia del script ────────────────────────────────────────────────────

def _save_execution_script(entity: str, script_text: str) -> Path:
    """
    Guarda el script de ejecución como Markdown parametrizable.
    Nombre: {entity_slug}_{fecha}.md en scripts/
    """
    slug = re.sub(r"[^\w\-]", "_", entity.lower())[:30]
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = SCRIPTS_DIR / f"{slug}_{date_str}.md"

    # Asegurar que la entidad actual aparece como parámetro,
    # y que el placeholder {ENTITY} está en el script para re-uso
    content = (
        f"# Script de Ejecución Bibliométrica\n\n"
        f"**Entidad por defecto**: {entity}\n"
        f"**Fecha de creación**: {date_str}\n"
        f"**Re-ejecución**: Cambia la variable ENTITY al correr con otra entidad.\n\n"
        f"---\n\n"
        + script_text
    )
    filename.write_text(content, encoding="utf-8")
    return filename


def load_execution_script(script_path: Union[str, Path]) -> str:
    """Carga un script guardado previamente."""
    path = Path(script_path)
    if not path.exists():
        raise FileNotFoundError(f"Script no encontrado: {script_path}")
    return path.read_text(encoding="utf-8")


def list_saved_scripts() -> list[dict]:
    """Lista todos los scripts guardados con metadata."""
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


# ── Función principal ──────────────────────────────────────────────────────────

def run_technical_mesa(
    entity: str,
    consensus_plan: str,
    on_message: Optional[Callable[[str, str], None]] = None,
) -> tuple[str, Path]:
    """
    Ejecuta la Fase 2: Mesa Técnica.

    Args:
        entity: Nombre de la entidad UNAM
        consensus_plan: Texto del plan aprobado por el Consejo (Fase 1)
        on_message: Callback para streaming a la UI (nombre_agente, contenido)

    Returns:
        Tuple de (script_texto: str, archivo_guardado: Path)
    """
    arquitecto = _build_arquitecto()
    sinapsis = _build_sinapsis_tecnico()

    # Proxy moderador
    moderador = UserProxyAgent(
        name="Moderador_Técnico",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=0,
        code_execution_config=False,
        is_termination_msg=lambda msg: (
            "SCRIPT_VALIDADO_POR_SINAPSIS" in msg.get("content", "")
        ),
    )

    # Conversación dirigida: Arquitecto → SINAPSIS → Moderador valida
    messages_log = []

    def _capture(sender, message, recipient, silent):
        name = getattr(sender, "name", "Sistema")
        content = message if isinstance(message, str) else message.get("content", "")
        messages_log.append({"name": name, "content": content})
        if on_message and content:
            on_message(name, content)

    arquitecto.register_hook("process_message_before_send", _capture)
    sinapsis.register_hook("process_message_before_send", _capture)

    # El Arquitecto responde al plan del Consejo
    moderador.initiate_chat(
        arquitecto,
        message=(
            f"El Consejo Estratégico ha aprobado el siguiente plan para **{entity}**:\n\n"
            f"{consensus_plan}\n\n"
            f"Traduce este plan a un script técnico de ejecución usando el placeholder "
            f"{{ENTITY}} para el nombre de la entidad, de forma que sea reutilizable."
        ),
        max_turns=1,
    )

    arquitecto_output = arquitecto.last_message()["content"] if arquitecto.last_message() else ""

    # SINAPSIS revisa y valida el script del Arquitecto
    moderador.initiate_chat(
        sinapsis,
        message=(
            f"El Arquitecto de Datos ha propuesto el siguiente script técnico para **{entity}**:\n\n"
            f"{arquitecto_output}\n\n"
            f"Revisa qué pasos puedes ejecutar con tus herramientas actuales, identifica "
            f"herramientas faltantes, y aprueba el script final."
        ),
        max_turns=MAX_TECH_ROUNDS,
    )

    sinapsis_output = sinapsis.last_message()["content"] if sinapsis.last_message() else ""

    # Combinar los outputs para el script final
    script_text = (
        f"## Script del Arquitecto de Datos\n\n{arquitecto_output}\n\n"
        f"---\n\n"
        f"## Validación SINAPSIS\n\n{sinapsis_output}"
    )

    saved_path = _save_execution_script(entity, script_text)
    return script_text, saved_path
