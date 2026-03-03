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
    """Crea un cliente de modelo apuntando a LM Studio (modelo local no-OpenAI)."""
    return OpenAIChatCompletionClient(
        model=_model,
        base_url=_auth_url,
        api_key=os.getenv("LLM_API_KEY", "lm-studio"),
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": True,
            "family": "unknown",
            "structured_output": False,
        },
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


# ── Catálogo dinámico de herramientas de SINAPSIS ────────────────────────────

def get_tools_catalog() -> str:
    """
    Genera un catálogo formateado de las herramientas REALES disponibles en SINAPSIS,
    leyendo directamente desde hybrid_tools + tools_interpreter.
    Se inyecta en los prompts del Arquitecto y SINAPSIS_Técnico para que sepan
    exactamente qué pueden usar — sin inventar herramientas inexistentes.
    """
    import sys, os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

    try:
        from agent.tools_hybrid import hybrid_tools
        from agent.tools_interpreter import execute_python_code

        lines = ["## Herramientas disponibles en SINAPSIS (únicas válidas)\n"]

        for tool in hybrid_tools:
            name = getattr(tool, "name", None) or getattr(tool, "__name__", str(tool))
            doc  = (getattr(tool, "description", None) or
                    getattr(tool, "__doc__", "") or "")
            # Tomar solo la primera línea del docstring
            first_line = doc.strip().split("\n")[0].strip() if doc.strip() else "(sin descripción)"
            lines.append(f"- **`{name}`**: {first_line}")

        # Agregar el intérprete Python
        lines.append(
            "- **`Python_CodeExecutor`**: Ejecuta código Python. "
            "Guarda gráficas con `plt.savefig('interpreter_output.png')`. "
            "Tiene acceso a pandas, matplotlib, numpy, networkx."
        )

        lines.append(
            "\n> ⚠️ RESTRICCIONES ABSOLUTAS: Solo puedes proponer pasos que usen las herramientas "
            "listadas arriba. NO existe acceso a Scopus, Web of Science, Google Scholar, "
            "Unpaywall, repositorios institucionales, Docker, Airflow ni ninguna API externa "
            "no listada. Si un objetivo no puede cumplirse con estas herramientas, indícalo "
            "explícitamente y propón una alternativa real."
        )

        return "\n".join(lines)

    except Exception as e:
        return (
            "## Herramientas disponibles (catálogo básico)\n"
            "- `query_knowledge_graph_cypher`: Cypher en Neo4j\n"
            "- `search_scientific_papers_semantic`: Búsqueda semántica en Qdrant\n"
            "- `get_entity_statistics`: Estadísticas de entidad UNAM\n"
            "- `get_researcher_profile`: Perfil de investigador\n"
            "- `get_trending_topics`: Tópicos en tendencia\n"
            "- `get_author_coauthors_graph`: Red de coautores\n"
            "- `recoverFromOpenAlex`: Datos bibliométricos por DOI\n"
            "- `searchAuthorInOpenAlex`: Buscar autor en OpenAlex\n"
            "- `recoverAuthorWorksFromOpenAlex`: Trabajos de un autor\n"
            "- `web_search`: Búsqueda DuckDuckGo\n"
            "- `wikipedia_search`: Búsqueda Wikipedia\n"
            "- `Python_CodeExecutor`: Ejecuta código Python (pandas, matplotlib, networkx)\n"
            f"\n(Error al cargar catálogo dinámico: {e})"
        )
