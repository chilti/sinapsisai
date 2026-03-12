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

# ── Señales de aprobación del Consejo (7 agentes) ────────────────────────────
# Cada agente escribe su señal para indicar que aprueba el plan.
# Terminación: cualquier agente puede declarar CONSENSO_MAYORITARIO cuando
# percibe que al menos 4/7 miembros han expresado aprobación.

RECTORA_APPROVAL       = "APROBADO: Rectora"
INVESTIGADOR_APPROVAL  = "APROBADO: Investigador_Campo"
BIBLIOMETRA_APPROVAL   = "APROBADO: Bibliometra"
POLITICA_APPROVAL      = "APROBADO: Politica_Cientifica"
EVALUADORA_APPROVAL    = "APROBADO: Evaluadora_Ciencia"
CONSEJERA_APPROVAL     = "APROBADO: Consejera_Social"
ESTUDIANTE_APPROVAL    = "APROBADO: Estudiante_Posgrado"

# Señal de fin: mayoría alcanzada (4/7)
CONSENSUS_SIGNAL = "CONSENSO_MAYORITARIO"

ALL_APPROVALS = [
    RECTORA_APPROVAL, INVESTIGADOR_APPROVAL, BIBLIOMETRA_APPROVAL,
    POLITICA_APPROVAL, EVALUADORA_APPROVAL, CONSEJERA_APPROVAL, ESTUDIANTE_APPROVAL,
]

# Compatibilidad hacia atrás (usado en autonomous_executor Fase 3b)
RECTOR_APPROVAL    = RECTORA_APPROVAL
INVESTIG_APPROVAL  = INVESTIGADOR_APPROVAL
CONSEJERO_APPROVAL = CONSEJERA_APPROVAL


# ── Esquema dinámico de las bases de datos ────────────────────────────────────

def get_db_schema() -> str:
    """
    Introspecciona Neo4j y Qdrant en tiempo real y devuelve un resumen del
    esquema/contenido de las bases de datos.

    Inyectar esto en los prompts permite que los agentes sepan:
    - Qué nodos y relaciones existen en Neo4j (no hay que importar lo que ya está)
    - Qué colecciones y campos payload tiene Qdrant
    - Cuántos registros hay (para estimar la cobertura)
    """
    import sys, os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

    lines = ["## Estado actual de las bases de datos\n"]

    # ── Neo4j ──────────────────────────────────────────────────────────────────
    try:
        from database.knowledge_graph import Neo4jGraphStore
        
        neo = Neo4jGraphStore()
        driver = neo.driver
        with driver.session() as session:
            # Contar nodos por etiqueta
            count_q = """
            CALL apoc.meta.stats() YIELD labels
            RETURN labels
            """
            try:
                result = session.run(count_q).single()
                label_counts = result["labels"] if result else {}
            except Exception:
                # APOC no disponible: fallback manual
                labels_res = session.run("CALL db.labels() YIELD label RETURN label").data()
                label_counts = {}
                for row in labels_res:
                    lbl = row["label"]
                    cnt = session.run(f"MATCH (n:{lbl}) RETURN count(n) AS c").single()["c"]
                    label_counts[lbl] = cnt

            # Tipos de relaciones
            rels_res = session.run(
                "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
            ).data()
            rel_types = [r["relationshipType"] for r in rels_res]

            # Propiedades clave (muestra de un nodo por etiqueta)
            sample_props = {}
            for lbl in list(label_counts.keys())[:8]:  # máx 8 etiquetas
                try:
                    row = session.run(f"MATCH (n:{lbl}) RETURN keys(n) AS k LIMIT 1").single()
                    if row:
                        sample_props[lbl] = row["k"]
                except Exception:
                    pass

        lines.append("### Neo4j (Grafo de Conocimiento)")
        lines.append("**Nodos disponibles** (ya no necesitan importarse desde APIs externas):")
        for lbl, cnt in sorted(label_counts.items(), key=lambda x: -x[1]):
            props = sample_props.get(lbl, [])
            props_str = ", ".join(props[:6]) + ("…" if len(props) > 6 else "")
            lines.append(f"- `:{lbl}` → **{cnt:,}** registros | propiedades: `{props_str}`")

        # Listar los nombres reales de las entidades (crucial para que los agentes no inventen nombres)
        try:
            entity_res = session.run(
                "MATCH (e:Entity) RETURN DISTINCT e.name AS name ORDER BY name LIMIT 20"
            ).data()
            entity_names = [r["name"] for r in entity_res if r.get("name")]
            if entity_names:
                names_str = ", ".join(f'"{n}"' for n in entity_names)
                lines.append(
                    f"\n**Entidades cargadas en el grafo** (usa EXACTAMENTE estos nombres en las queries):\n"
                    + "\n".join(f'  - `"{n}"`' for n in entity_names)
                )
        except Exception:
            pass

        lines.append(f"\n**Relaciones disponibles**: {', '.join(f'`:{r}`' for r in rel_types)}")
        lines.append(
            "\n> ✅ Usa `query_knowledge_graph_cypher` para consultar estos datos. "
            "**No es necesario llamar a OpenAlex/Scopus para datos que ya están aquí.**"
        )

    except Exception as e:
        lines.append(f"### Neo4j\n> ⚠️ No se pudo conectar: {e}")
        lines.append(
            "Esquema esperado: `:Paper`, `:Academic`, `:Topic`, `:Entity`, `:Journal`, `:SDG`\n"
            "Relaciones: `:AUTHORED`, `:HAS_TOPIC`, `:PUBLISHED_IN`, `:AFFILIATED_TO`, `:CITES`, "
            "`:ADDRESSES` (Paper→SDG — se llama ADDRESSES, no RELEVANT_TO)\n"
            "> ⚠️ No fue posible obtener los nombres exactos de las entidades disponibles. "
            "Usa `query_knowledge_graph_cypher` con `MATCH (e:Entity) RETURN e.name LIMIT 20` "
            "como PRIMER paso del script para conocer las entidades disponibles."
        )

    lines.append("")

    # ── Qdrant ─────────────────────────────────────────────────────────────────
    try:
        from qdrant_client import QdrantClient

        host  = os.getenv("QDRANT_HOST", "localhost")
        port  = int(os.getenv("QDRANT_PORT", "6333"))
        qclient = QdrantClient(host=host, port=port)

        collections = qclient.get_collections().collections
        lines.append("### Qdrant (Búsqueda Semántica)")
        for col in collections:
            info = qclient.get_collection(col.name)
            count = info.points_count
            # Obtener campos payload de muestra
            try:
                sample = qclient.scroll(col.name, limit=1, with_payload=True)[0]
                payload_keys = list(sample[0].payload.keys()) if sample else []
            except Exception:
                payload_keys = []
            keys_str = ", ".join(f"`{k}`" for k in payload_keys[:8])
            lines.append(
                f"- **`{col.name}`**: {count:,} vectores | "
                f"payload: {keys_str or '(desconocido)'}"
            )
        lines.append(
            "\n> ✅ Usa `search_scientific_papers_semantic` con `entity_context` "
            "para búsquedas por significado en Qdrant."
        )

    except Exception as e:
        lines.append(f"### Qdrant\n> ⚠️ No se pudo conectar: {e}")
        lines.append(
            "Colección esperada: `papers` con payload: "
            "`title`, `abstract`, `entity`, `year`, `doi`, `authors`"
        )

    return "\n".join(lines)


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

        # Agregar el intérprete Python con todas sus bibliotecas disponibles
        lines.append(
            "- **`Python_CodeExecutor`**: Ejecuta código Python con acceso a:\n"
            "  - **Análisis de datos**: pandas, numpy, scikit-learn\n"
            "  - **Visualización**: matplotlib, plotly\n"
            "  - **Redes**: networkx\n"
            "  - **Bibliometría**: pyalex (OpenAlex API), pybliometrics (Scopus — requiere API key configurada)\n"
            "  - **Machine Learning**: umap-learn, somoclu\n"
            "  - Guarda gráficas con `plt.savefig('interpreter_output.png')` o `fig.write_image('interpreter_output.png')`"
        )

        lines.append(
            "\n## Datos pre-calculados disponibles (Parquet jerárquicos en `data/cache/`)\n\n"
            "Puedes cargarlos directamente con `pd.read_parquet('data/cache/<E>/<a>/<archivo>')`.\n\n"
            "| Archivo | Alcance | Ubicación típica |\n"
            "|---|---|---|\n"
            "| `papers_profesor.parquet` | **Producción completa del académico** (toda su carrera). | `data/cache/<Entidad>/<Academico>/` |\n"
            "| `investigador_total.parquet` | **Métricas totales del investigador** (agregado). | `data/cache/<Entidad>/<Academico>/` |\n"
            "| `investigador_annual.parquet` | **Trayectoria anual del investigador**. | `data/cache/<Entidad>/<Academico>/` |\n"
            "| `papers_institucion.parquet` | **Producción institucional** (WoS/OpenAlex) bajo afiliación actual. | `data/cache/<Entidad>/` |\n"
            "| `institucion_total.parquet` | **Métricas totales de la institución**. | `data/cache/<Entidad>/` |\n"
            "| `institucion_annual.parquet` | **Evolución anual de la institución**. | `data/cache/<Entidad>/` |\n"
            "| `topics_investigador.parquet` | Tópicos y expertise por investigador. | `data/cache/<Entidad>/<Academico>/` |\n"
            "| `umap_investigadores.parquet` | Mapa 2D global de investigadores. | `data/cache/` |\n\n"
            "> ⚠️ **Nota**: Reemplaza `<Entidad>` y `<Academico>` por los nombres correspondientes (ej. 'Facultad de Ciencias' / 'ALCUBIERRE MOYA, MIGUEL')."
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
            "- `Python_CodeExecutor`: Ejecuta código Python (plotly, pandas, matplotlib, networkx, pyalex, pybliometrics, umap-learn, scikit-learn, somoclu)\n"
            f"\n(Error al cargar catálogo dinámico: {e})"
        )


# ── Catálogo EXCLUSIVO de parquets pre-calculados ────────────────────────────

def get_parquet_catalog() -> str:
    """
    Devuelve una descripción detallada de los archivos Parquet pre-calculados
    disponibles en data/cache/. Esta es la ÚNICA fuente de datos que el Consejo
    Estratégico debe usar: no requiere conexión a Neo4j, Qdrant ni APIs externas,
    por lo que sus consultas nunca fallan por problemas de conectividad.

    Carga dinámicamente el listado real de parquets disponibles y sus columnas.
    """
    import sys, os
    import pandas as pd

    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

    cache_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "cache")
    )

    # Descripción canónica de cada parquet conocido
    KNOWN_PARQUETS = {
        "papers_profesor.parquet": (
            "**Todos los papers de cada académico** — incluye papers producidos en "
            "OTRAS instituciones antes o durante su adscripción actual. "
            "Útil para el perfil completo de carrera."
        ),
        "investigador_total.parquet": (
            "**Métricas totales por investigador** — agrupado por investigador "
            "(suma de toda su carrera)."
        ),
        "investigador_annual.parquet": (
            "**Métricas anuales por investigador** — para trayectorias temporales."
        ),
        "institucion_total.parquet": (
            "**Papers de la institución** (WoS/OpenAlex) — solo papers producidos "
            "BAJO la afiliación institucional actual. Más riguroso para reportes oficiales."
        ),
        "institucion_annual.parquet": (
            "**Métricas institucionales por año** — evolución temporal de la institución."
        ),
        "topics_investigador.parquet": (
            "**Jerarquía temática (OpenAlex) por investigador** — dominios, campos, "
            "subtemas y tópicos de investigación."
        ),
    }

    lines = [
        "## Datos pre-calculados disponibles (Parquets en `data/cache/`)\n",
        "Carga los archivos con `pd.read_parquet('data/cache/<archivo>')` en el ejecutor Python.\n",
        "> ✅ **ÚNICA FUENTE DE DATOS DEL CONSEJO**: Usa exclusivamente estos parquets.",
        "> No se invocan herramientas externas (Neo4j, Qdrant, OpenAlex, Scopus, etc.)\n",
    ]

    # Intentar leer columnas reales de los parquets disponibles de forma jerárquica
    if os.path.isdir(cache_dir):
        from pathlib import Path
        available_files = list(Path(cache_dir).rglob("*.parquet"))
        
        # Agrupar por nombre de archivo para mostrar una descripción única
        file_samples = {}
        for p in available_files:
            if p.name not in file_samples:
                file_samples[p.name] = p
        
        for fname in sorted(file_samples.keys()):
            desc = KNOWN_PARQUETS.get(fname, "(archivo pre-calculado)")
            fpath = file_samples[fname]
            try:
                # Intentar inferir ubicación basándose en la estructura nueva
                rel_path = str(fpath.relative_to(Path(cache_dir).parent)).replace('\\', '/')
                df = pd.read_parquet(fpath, engine="pyarrow")
                cols = ", ".join(f"`{c}`" for c in df.columns[:12])
                extra = " …" if len(df.columns) > 12 else ""
                nrows = f"{len(df):,}"
                lines.append(
                    f"### `{fname}`\n"
                    f"- **Descripción**: {desc}\n"
                    f"- **Ubicación ejemplo**: `{rel_path}`\n"
                    f"- **Columnas base**: {cols}{extra}\n"
                )
            except Exception as ex:
                lines.append(
                    f"### `{fname}`\n"
                    f"- **Descripción**: {desc}\n"
                    f"- ⚠️ No se pudieron leer las columnas: {ex}\n"
                )
    else:
        # Directorio no encontrado: listar solo los conocidos
        lines.append(f"> ⚠️ No se encontró el directorio `{cache_dir}`. Listado estimado:\n")
        for fname, desc in KNOWN_PARQUETS.items():
            lines.append(f"- **`{fname}`**: {desc}")

    lines.append(
        "\n## Cómo usar los parquets en el plan\n\n"
        "Propón pasos concretos con código Python usando `pd.read_parquet(...)`. "
        "Ejemplo mínimo:\n"
        "```python\n"
        "import pandas as pd\n"
        "import os\n"
        "# Ejemplo: Cargar datos institucionales de una entidad\n"
        "entidad = 'Facultad de Ciencias'\n"
        "path = f'data/cache/{entidad}/institucion_total.parquet'\n"
        "if os.path.exists(path):\n"
        "    df = pd.read_parquet(path)\n"
        "    print(df[['entity_name','num_documents','citations']].head())\n"
        "```\n\n"
        "> ⚠️ **RESTRICCIÓN ABSOLUTA**: El Consejo Estratégico NO tiene acceso a Neo4j, "
        "Qdrant, OpenAlex, Scopus, Web of Science ni ninguna API externa. "
        "Si un objetivo no puede lograrse con los parquets listados arriba, indícalo "
        "explícitamente y propón qué dato adicional habría que pre-calcular en el futuro."
    )

    return "\n".join(lines)
