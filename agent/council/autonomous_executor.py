"""
autonomous_executor.py — Fase 3 del sistema multi-agente (AutoGen v0.4+)

Flujo en dos pasos:

  3a — SINAPSIS_Ejecutor recopila datos reales usando las herramientas.
       Para cada visualización Python, produce TAMBIÉN la tabla subyacente
       (df.to_markdown()) para que los LLMs puedan interpretarla.
       Señal de fin: DATA_COLLECTION_COMPLETE

  3b — El Consejo (Rector + Investigador_Senior + Consejero_Universitario)
       recibe los datos y redacta colaborativamente el informe final.
       Cada uno aporta su perspectiva e interpretación.
       Señal de fin: INFORME_COMPLETO

El PDF final incluye texto del informe + gráficas generadas incrustadas.
"""

import asyncio
import base64
import re
import glob
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
    RECTOR_APPROVAL,
    INVESTIG_APPROVAL,
    CONSEJERO_APPROVAL,
)

# ── Importar herramientas SINAPSIS ────────────────────────────────────────────
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

DATA_DONE_SIGNAL   = "DATA_COLLECTION_COMPLETE"
REPORT_DONE_SIGNAL = "INFORME_COMPLETO"


# ── Wrappers síncronos para FunctionTool ──────────────────────────────────────

def _cypher(query: str) -> str:
    """Ejecuta una query Cypher en Neo4j. Usa CONTAINS para nombres de personas."""
    return query_knowledge_graph_cypher.invoke({"cypher_query": query})

def _semantic(query: str, entity_context: Optional[str] = None, limit: int = 20) -> str:
    """Búsqueda semántica en Qdrant."""
    return search_scientific_papers_semantic.invoke(
        {"query": query, "entity_context": entity_context, "limit": limit}
    )

def _entity_stats(entity_name: str) -> str:
    """Estadísticas completas de una entidad UNAM."""
    return get_entity_statistics.invoke({"entity_name": entity_name})

def _researcher_profile(name_fragment: str) -> str:
    """Perfil de un investigador por nombre parcial."""
    return get_researcher_profile.invoke({"name_fragment": name_fragment})

def _trending_topics(entity_name: Optional[str] = None, start_year: int = 2018) -> str:
    """Tópicos emergentes desde un año dado."""
    return get_trending_topics.invoke({"entity_name": entity_name, "start_year": start_year})

def _coauthors(author_name: str) -> str:
    """Red de coautores de un investigador."""
    return get_author_coauthors_graph.invoke({"author_name": author_name})

def _openalex(doi: str, fields: Optional[str] = None) -> str:
    """Datos bibliométricos de OpenAlex por DOI."""
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
    """
    Ejecuta código Python. REGLAS OBLIGATORIAS:
    1. Antes de plt.savefig(), imprime siempre: print(df.to_markdown(index=False))
    2. Guarda gráficas con: plt.savefig('output_NOMBRE.png', dpi=150, bbox_inches='tight')
    3. Usa nombres descriptivos: output_temas.png, output_coautores.png, etc.
    """
    return execute_python_code(code)


def _make_tools() -> list:
    return [
        FunctionTool(_cypher,               name="query_knowledge_graph_cypher", description="Cypher en Neo4j"),
        FunctionTool(_semantic,             name="search_semantic",              description="Búsqueda semántica en Qdrant"),
        FunctionTool(_entity_stats,         name="get_entity_statistics",        description="Estadísticas de entidad UNAM"),
        FunctionTool(_researcher_profile,   name="get_researcher_profile",       description="Perfil de investigador"),
        FunctionTool(_trending_topics,      name="get_trending_topics",          description="Tópicos emergentes"),
        FunctionTool(_coauthors,            name="get_author_coauthors_graph",   description="Red de coautores"),
        FunctionTool(_openalex,             name="openalex_doi",                 description="Datos bibliométricos por DOI"),
        FunctionTool(_openalex_search_author, name="openalex_search_author",    description="Busca autor en OpenAlex"),
        FunctionTool(_openalex_author_works,  name="openalex_author_works",     description="Trabajos de autor en OpenAlex"),
        FunctionTool(_web,                  name="web_search",                   description="Búsqueda web"),
        FunctionTool(_wiki,                 name="wikipedia",                    description="Búsqueda Wikipedia"),
        FunctionTool(_python,               name="python_executor",              description="Ejecuta código Python"),
    ]


# ── Utilidades ────────────────────────────────────────────────────────────────

def _inject_entity(text: str, entity: str) -> str:
    return text.replace("{ENTITY}", entity).replace("{{ENTITY}}", entity)


def _content_to_str(content) -> str:
    """Normaliza content que puede ser str o lista de bloques."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif hasattr(block, "text"):
                parts.append(block.text)
            elif hasattr(block, "content"):
                parts.append(str(block.content))
            else:
                parts.append(str(block))
        return " ".join(parts)
    return str(content)


def _cleanup_outputs():
    """Limpia imágenes de ejecuciones previas para evitar confusión."""
    patterns = ["output_*.png", "interpreter_output.png", "output_*.jpg"]
    count = 0
    for p in patterns:
        for f in Path(".").glob(p):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
    if count > 0:
        print(f"🧹 Limpieza: {count} archivos temporales eliminados.")


def _find_generated_images() -> list[Path]:
    """Encuentra todas las imágenes generadas en el directorio actual."""
    patterns = ["output_*.png", "interpreter_output.png", "output_*.jpg"]
    images = []
    for p in patterns:
        images.extend(Path(".").glob(p))
    return sorted(set(images))


# ── Conversión a PDF ──────────────────────────────────────────────────────────

def _md_to_pdf(md_text: str, title: str, pdf_path: Path, images: list[Path]) -> bool:
    """
    Convierte Markdown + imágenes a PDF estilizado.
    Las imágenes se incrustan en base64 para que el PDF sea autocontenido.
    """
    import sys
    print(f"DEBUG PDF: Iniciando conversión. Python: {sys.version}")
    print(f"DEBUG PDF: sys.path: {sys.path[:5]}...")

    try:
        import markdown
        from weasyprint import HTML
        print("DEBUG PDF: weasyprint importado correctamente.")

        # Incrustar imágenes en el texto Markdown como base64 si se referencian
        # y añadir las imágenes al final del HTML
        html_body = markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code", "nl2br"],
        )

        # Insertar figuras al final del HTML
        fig_html = ""
        for img in images:
            if img.exists():
                data = base64.b64encode(img.read_bytes()).decode()
                ext = img.suffix.lstrip(".")
                caption = img.stem.replace("output_", "").replace("_", " ").title()
                fig_html += (
                    f'<figure style="page-break-inside:avoid; margin: 24px 0;">'
                    f'<img src="data:image/{ext};base64,{data}" '
                    f'style="max-width:100%; border:1px solid #ddd; border-radius:4px;">'
                    f'<figcaption style="font-size:9pt;color:#555;text-align:center;">'
                    f'Figura: {caption}</figcaption></figure>'
                )

        html = f"""<!DOCTYPE html><html><head>
        <meta charset="utf-8"><title>{title}</title>
        <style>
            @page {{ margin: 2cm; }}
            body {{ font-family: 'Helvetica Neue', Arial, sans-serif;
                   font-size: 11pt; color: #222; line-height: 1.6; }}
            h1 {{ color: #003366; border-bottom: 2px solid #003366; padding-bottom: 6px; }}
            h2 {{ color: #005299; margin-top: 28px; border-left: 4px solid #005299; padding-left: 10px; }}
            h3 {{ color: #0070cc; }}
            table {{ border-collapse: collapse; width: 100%; margin: 16px 0; font-size: 10pt; page-break-inside: avoid; }}
            th {{ background: #003366; color: white; padding: 6px 10px; text-align: left; }}
            td {{ border: 1px solid #ccc; padding: 5px 10px; }}
            tr:nth-child(even) {{ background: #f0f4fa; }}
            code {{ background: #f5f5f5; padding: 2px 5px; border-radius: 3px;
                    font-family: monospace; font-size: 9pt; }}
            pre {{ background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }}
            blockquote {{ border-left: 4px solid #0070cc; margin: 0;
                          padding: 8px 16px; background: #f0f7ff; color: #444; }}
            figure {{ text-align: center; }}
            figcaption {{ font-style: italic; }}
        </style></head><body>
        <h1>{title}</h1>
        {html_body}
        {"<h2>Visualizaciones</h2>" + fig_html if fig_html else ""}
        </body></html>"""

        HTML(string=html).write_pdf(str(pdf_path))
        return True

    except ImportError:
        print("DEBUG PDF: weasyprint no está instalado.")
    except Exception as e:
        import traceback
        print(f"DEBUG PDF: error en weasyprint: {e}")
        traceback.print_exc()

    # Fallback: fpdf2
    try:
        from fpdf import FPDF
        print("DEBUG PDF: fpdf2 importado correctamente. Usando fallback.")
        
        # Sanitizar texto para evitar errores de encoding en fpdf2 (latin-1)
        def _sanitize(txt: str) -> str:
            if not txt: return ""
            # Reemplazar caracteres comunes no-latin1
            replacements = {
                "\u2014": "-",  # em-dash
                "\u2013": "-",  # en-dash
                "\u201c": '"',  # smart quotes
                "\u201d": '"',
                "\u2018": "'",
                "\u2019": "'",
                "\u2022": "*",  # bullet
                "\u2026": "...", # ellipsis
            }
            for k, v in replacements.items():
                txt = txt.replace(k, v)
            return txt.encode("latin-1", "replace").decode("latin-1")

        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        
        safe_title = _sanitize(title[:80])
        pdf.cell(0, 10, safe_title, ln=True)
        pdf.set_font("Helvetica", size=10)
        pdf.ln(4)
        
        for line in md_text.split("\n"):
            clean = line.lstrip("#").lstrip("*").lstrip("-").strip()
            if clean:
                try:
                    safe_line = _sanitize(clean)
                    pdf.multi_cell(0, 5, safe_line)
                except Exception:
                    pass
        # Insertar imágenes
        for img in images:
            if img.exists() and img.suffix.lower() == ".png":
                try:
                    pdf.add_page()
                    pdf.image(str(img), x=15, y=30, w=180)
                except Exception as e:
                    print(f"DEBUG PDF: Error insertando imagen {img}: {e}")
        pdf.output(str(pdf_path))
        return True
    except Exception:
        import traceback
        traceback.print_exc()
        return False


def _save_report(entity: str, report: str) -> tuple[Path, "Path | None"]:
    slug = re.sub(r"[^\w\-]", "_", entity.lower())[:30]
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M")
    title = f"Informe Bibliométrico — {entity} ({date_str})"
    md_content = (
        f"# Informe Bibliométrico Final\n\n"
        f"**Entidad**: {entity}\n**Generado**: {date_str}\n\n---\n\n" + report
    )
    md_path = OUTPUT_DIR / f"informe_{slug}_{date_str}.md"
    md_path.write_text(md_content, encoding="utf-8")

    images = _find_generated_images()
    pdf_path = OUTPUT_DIR / f"informe_{slug}_{date_str}.pdf"
    ok = _md_to_pdf(md_content, title, pdf_path, images)
    return md_path, pdf_path if ok else None


# ── Fase 3a: Recopilación de datos ───────────────────────────────────────────

async def _run_data_collection(
    entity: str,
    script: str,
    on_message: Optional[Callable[[str, str], None]] = None,
) -> str:
    """SINAPSIS ejecuta el script y devuelve un resumen de datos en Markdown."""
    model_client = make_model_client()
    tools = _make_tools()

    executor = AssistantAgent(
        name="SINAPSIS_Ejecutor",
        model_client=model_client,
        tools=tools,
        system_message=(
            f"Eres SINAPSIS en modo recopilación de datos para **{entity}**.\n\n"
            f"MISIÓN: Ejecutar cada paso del script llamando herramientas reales y recopilar los DATOS REALES.\n\n"
            f"REGLAS ABSOLUTAS:\n"
            f"1. EJECUTA cada paso — llama a la herramienta correspondiente, no la planees.\n"
            f"2. Para Neo4j usa CONTAINS: WHERE toLower(a.name) CONTAINS toLower('termino')\n"
            f"3. Los tópicos en Neo4j están en inglés. Traduce siempre antes de buscar.\n"
            f"4. Si una búsqueda devuelve vacío, intenta con términos alternativos.\n"
            f"5. Para código Python CON visualizaciones:\n"
            f"   a) SIEMPRE imprime la tabla de datos: print(df.to_markdown(index=False))\n"
            f"   b) Guarda la gráfica: plt.savefig('output_NOMBRE.png', dpi=150, bbox_inches='tight')\n"
            f"   c) Usa nombres descriptivos: output_temas.png, output_coautores.png, etc.\n"
            f"6. Tras cada herramienta, escribe una línea: '**Resultado [PASO]:** [resumen breve]'\n"
            f"7. NUNCA escribas 'los resultados mostrarían...' — solo datos reales.\n\n"
            f"Al terminar TODOS los pasos, escribe '{DATA_DONE_SIGNAL}' seguido de:\n"
            f"## RESUMEN DE DATOS RECOPILADOS\n"
            f"[Todas las tablas, cifras y hallazgos en Markdown para que el Consejo los analice]"
        ),
    )

    termination = (
        TextMentionTermination(DATA_DONE_SIGNAL) |
        MaxMessageTermination(35)
    )
    team = RoundRobinGroupChat([executor], termination_condition=termination)

    collected_parts = []
    data_summary = []

    async for message in team.run_stream(
        task=f"Ejecuta el siguiente script de recopilación de datos para {entity}:\n\n{script}"
    ):
        if isinstance(message, TaskResult):
            break
        src = getattr(message, "source", "Sistema")
        content = _content_to_str(getattr(message, "content", ""))
        if content and content.strip():
            collected_parts.append(content)
            if DATA_DONE_SIGNAL in content:
                # Si el mensaje contiene el signal, extraemos el resumen 
                # (puede estar antes o después del signal)
                clean_content = content.replace(DATA_DONE_SIGNAL, "").strip()
                if clean_content:
                    data_summary.append(clean_content)
            if on_message:
                on_message(src, content)

    return "\n\n".join(data_summary) if data_summary else "\n\n".join(collected_parts[-8:])


# ── Fase 3b: Redacción del informe por el Consejo ─────────────────────────────

async def _run_report_writing(
    entity: str,
    data_summary: str,
    on_message: Optional[Callable[[str, str], None]] = None,
) -> str:
    """El Consejo lee los datos y redacta colaborativamente el informe final."""
    model_client = make_model_client()

    images = _find_generated_images()
    img_note = ""
    if images:
        img_list = ", ".join(f"`{img.name}`" for img in images)
        img_note = (
            f"\n\nNOTA: Se generaron las siguientes visualizaciones que se incluirán en el PDF: {img_list}. "
            f"Refiérete a ellas en el texto como 'Ver Figura: [nombre descriptivo]'."
        )

    context = (
        f"# Datos recopilados para {entity}\n\n{data_summary}{img_note}\n\n"
        f"---\n\n"
        f"Lean los datos anteriores y redacten juntos el informe bibliométrico final para {entity}.\n\n"
        f"Cada uno aporta su interpretación desde su rol. La estructura del informe es LIBRE: "
        f"déjense guiar por lo que los datos realmente revelaron. No completen secciones vacías. "
        f"Eviten usar frases genéricas.\n\n"
        f"Solo hay tres requisitos mínimos:\n"
        f"1. Una síntesis ejecutiva honesta con los hallazgos más relevantes.\n"
        f"2. Los datos reales presentados (tablas, cifras — tal como los recibieron).\n"
        f"3. Conclusiones accionables para la institución.\n\n"
        f"Cuando todos hayan aportado su visión, la Rectora redactará el informe final completo "
        f"y terminará su mensaje con el código: **TERMINAR_REPORTE** (esto cerrará la sesión)."
    )

    rectora = AssistantAgent(
        name="Rectora",
        model_client=model_client,
        system_message=(
            f"Eres la Rectora de la UNAM (mujer zapoteca, SNI III). Interpretas los datos de {entity} "
            f"desde visibilidad internacional, impacto comunitario y ODS. "
            f"Cuando todos hayan aportado su análisis, escribe el informe final completo en Markdown "
            f"integrando TODAS las perspectivas, y CUBRE el reporte cerrando con: 'TERMINAR_REPORTE'."
        ),
    )

    investigador = AssistantAgent(
        name="Investigador_Campo",
        model_client=model_client,
        system_message=(
            f"Eres Investigador del área de {entity} (hombre, primera generación universitaria). "
            f"Analizas calidad científica real: FWCI, h-index, redes, evolución temporal. "
            f"Señala también la producción que no aparece en las bases de datos. "
            f"NO escribas '{REPORT_DONE_SIGNAL}', eso solo lo hace la Rectora al final."
        ),
    )

    bibliometra = AssistantAgent(
        name="Bibliometra",
        model_client=model_client,
        system_message=(
            f"Eres Dra. en Ciencia de la Ciencia (mujer afromexicana). Analizas los datos con rigor "
            f"metodológico: sesgos de las bases de datos, limitaciones de los indicadores, "
            f"métodos alternativos. Propón indicadores complementarios al factor de impacto. "
            f"NO escribas '{REPORT_DONE_SIGNAL}', eso solo lo hace la Rectora al final."
        ),
    )

    politica = AssistantAgent(
        name="Politica_Cientifica",
        model_client=model_client,
        system_message=(
            f"Eres Dr. en Política Científica, ex asesor CONAHCYT (hombre árabe-mexicano). "
            f"Conecta los hallazgos con decisiones de financiamiento, SNI, presupuesto. "
            f"Alerta sobre el efecto Goodhart y propón recomendaciones de política concreta. "
            f"NO escribas '{REPORT_DONE_SIGNAL}', eso solo lo hace la Rectora al final."
        ),
    )

    evaluadora = AssistantAgent(
        name="Evaluadora_Ciencia",
        model_client=model_client,
        system_message=(
            f"Eres especialista en evaluación responsable de la ciencia (mujer, perspectiva post-colonial). "
            f"Aplicas los principios DORA y el Manifiesto de Leiden. "
            f"Evalúa si el análisis incluye ciencia ciudadana, diversidad lingüística y producción no indexada. "
            f"NO escribas '{REPORT_DONE_SIGNAL}', eso solo lo hace la Rectora al final."
        ),
    )

    consejera = AssistantAgent(
        name="Consejera_Social",
        model_client=model_client,
        system_message=(
            f"Eres Consejera de equidad y género (mujer de comunidad campesina). "
            f"Analiza los datos desagregados por género, área y nivel de carrera. "
            f"Visibiliza a quienes el sistema invisibiliza: técnicos, investigadoras con maternidad, etc. "
            f"NO escribas '{REPORT_DONE_SIGNAL}', eso solo lo hace la Rectora al final."
        ),
    )

    estudiante = AssistantAgent(
        name="Estudiante_Posgrado",
        model_client=model_client,
        system_message=(
            f"Eres estudiante de doctorado en {entity} con beca CONAHCYT (persona no binaria). "
            f"Representa la perspectiva de quienes construyen su carrera en condiciones precarias. "
            f"¿Este análisis visibiliza tesis y trabajos no publicados? ¿Promueve el acceso abierto? "
            f"NO escribas '{REPORT_DONE_SIGNAL}', eso solo lo hace la Rectora al final."
        ),
    )

    termination = (
        TextMentionTermination("TERMINAR_REPORTE") |
        MaxMessageTermination(21)   # 3 rondas × 7 agentes
    )
    team = RoundRobinGroupChat(
        [investigador, bibliometra, politica, evaluadora, consejera, estudiante, rectora],
        termination_condition=termination,
    )

    report_parts = []
    all_parts = []

    async for message in team.run_stream(task=context):
        if isinstance(message, TaskResult):
            break
        src = getattr(message, "source", "Sistema")
        content = _content_to_str(getattr(message, "content", ""))
        if content and content.strip():
            all_parts.append(f"### Perspectiva de {src}\n\n{content}")
            # Si contiene el signal de terminación (TERMINAR_REPORTE)
            if "TERMINAR_REPORTE" in content:
                # Extraemos el reporte (quitando el signal)
                clean_report = content.replace("TERMINAR_REPORTE", "").strip()
                if len(clean_report) > 500: # Exigimos más contenido para la síntesis
                    report_parts.append(clean_report)
            if on_message:
                on_message(src, content)

    if report_parts:
        return report_parts[-1]
    
    # Fallback robusto: Deliberación completa
    if all_parts:
        deliberation = "\n\n---\n\n".join(all_parts)
        return (
            f"## Resumen de Deliberación Colectiva\n\n"
            f"Debido a que no se emitió una síntesis final, se presenta la deliberación completa de los expertos:\n\n"
            f"{deliberation}"
        )
    return "No se pudo generar el informe. El Consejo no emitió comentarios."


# ── Función principal ─────────────────────────────────────────────────────────

async def _run_executor_async(
    entity: str,
    execution_script: str,
    on_message: Optional[Callable[[str, str], None]] = None,
) -> tuple[str, Path, "Path | None"]:
    _cleanup_outputs() # Limpiar antes de empezar
    script = _inject_entity(execution_script, entity)

    if on_message:
        on_message("Sistema", "📊 **Fase 3a**: SINAPSIS recopilando datos con herramientas reales...")

    data_summary = await _run_data_collection(entity, script, on_message)

    if on_message:
        on_message("Sistema", "✍️ **Fase 3b**: El Consejo interpreta los datos y redacta el informe...")

    report_text = await _run_report_writing(entity, data_summary, on_message)

    md_path, pdf_path = _save_report(entity, report_text)
    return report_text, md_path, pdf_path


def run_autonomous_executor(
    entity: str,
    execution_script: str,
    on_message: Optional[Callable[[str, str], None]] = None,
    on_step: Optional[Callable[[int, int], None]] = None,
) -> tuple[str, Path, "Path | None"]:
    """Punto de entrada síncrono para Streamlit. Returns (report_text, md_path, pdf_path)."""
    return asyncio.run(_run_executor_async(entity, execution_script, on_message))
