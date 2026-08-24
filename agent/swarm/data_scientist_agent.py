"""
data_scientist_agent.py — Agente Especialista en Datos Científicos Masivos y GraphRAG
Discovery Engine del enjambre ScientistOne: ejecuta los SQLs del ExperimentBrief
y devuelve hallazgos con evidence_tags por valor numérico.
"""
import sys
import os
import json
from typing import Dict, Any, List, Optional

from agent.swarm.base_agent import BaseSpecialistAgent
from agent.episodic_memory import episodic_memory

try:
    from smolagents import tool
except ImportError:
    def tool(fn): return fn


# ── Tools ──────────────────────────────────────────────────────────────────

@tool
def query_clickhouse_analytics(sql_query: str, purpose: str = "") -> str:
    """
    Ejecuta consultas analíticas SQL en ClickHouse sobre 569M de papers de OpenAlex
    y tablas pre-materializadas (works_academic_all, works_flat).
    Args:
        sql_query: Consulta SQL que inicie con SELECT.
        purpose: Justificación o propósito del dato solicitado.
    """
    from agent.tools_interpreter import query_clickhouse_safe_sql
    return query_clickhouse_safe_sql.invoke({"sql_query": sql_query})


@tool
def query_duckdb_analytics(sql_query: str, purpose: str = "") -> str:
    """
    Ejecuta consultas analíticas SQL ultrarrápidas (<5ms) sobre DuckDB
    (analytics_cache.duckdb). Tablas disponibles:
    'investigador_total', 'investigador_annual', 'investigador_recent',
    'institucion_total', 'institucion_annual',
    'papers_profesor', 'papers_institucion',
    'topics_investigador', 'topics_institucion',
    'keywords_investigador', 'keywords_institucion',
    'thematic_evolution_investigador', 'thematic_evolution_institucion',
    'umap_investigadores'.
    Args:
        sql_query: Consulta SQL que inicie con SELECT.
        purpose: Justificación o propósito del dato solicitado.
    """
    from agent.tools_interpreter import query_duckdb_safe_sql
    return query_duckdb_safe_sql.invoke({"sql_query": sql_query})


@tool
def query_parquet_academic_cache(
    table_type: str, institution: str = "", academic: str = "", top_n: int = 10
) -> str:
    """
    Consulta tablas Parquet de métricas anuales de instituciones y académicos
    (FWCI, documentos, citas).
    Args:
        table_type: 'institucion_annual', 'investigador_annual', 'papers_profesor',
                    'topics', 'umap_investigadores'.
        institution: Nombre de la institución.
        academic: Nombre del investigador.
        top_n: Número de filas.
    """
    from agent.tools_interpreter import query_academic_cache
    return query_academic_cache.invoke({
        "table_type": table_type,
        "institution": institution or None,
        "academic": academic or None,
        "sort_by": None,
        "top_n": top_n,
    })


@tool
def get_consolidated_scholar_summary(academic_name: str, institution_name: str = "") -> str:
    """
    Obtiene el resumen consolidado de impacto de un investigador cruzando
    Neo4j, SNII y ClickHouse.
    Args:
        academic_name: Nombre completo del investigador.
        institution_name: Institución de filiación.
    """
    from agent.tools_interpreter import get_scientometric_summary
    return get_scientometric_summary.invoke({
        "academic_name": academic_name,
        "institution_name": institution_name or None,
    })


@tool
def get_entity_bibliometric_profile(entity_name: str) -> str:
    """
    Extrae el perfil cienciométrico de una institución, facultad o dependencia
    desde ClickHouse (total_papers, FWCI, citas, % Top 10%, % OA Diamante, APC).
    Args:
        entity_name: Nombre de la entidad (ej. 'Facultad de Ciencias').
    """
    try:
        from database.clickhouse_db import ch_client
        client = ch_client.get_client()
        clean = entity_name.upper().strip()
        kw = next(
            (w for w in ["CIENCIAS", "FISICA", "BIOLOGIA", "MATEMATICAS", "QUIMICA"]
             if w in clean),
            clean.split()[-1] if clean else clean
        )
        df = client.query_df(f"""
            SELECT count() AS total_papers,
                   round(avg(fwci), 2) AS avg_fwci,
                   sum(cited_by_count) AS total_citations,
                   round(countIf(is_top_10 = 1) * 100.0 / count(), 1) AS pct_top10,
                   round(countIf(oa_status = 'diamond') * 100.0 / count(), 1) AS pct_diamond,
                   round(sum(apc_paid_usd), 0) AS total_apc_usd
            FROM works_academic_all
            WHERE arrayExists(x -> x ILIKE '%{kw}%', institution_names)
               OR arrayExists(x -> x ILIKE '%{clean}%', institution_names)
        """)
        df_topics = client.query_df(f"""
            SELECT subfield, count() AS papers, round(avg(fwci), 2) AS fwci_subfield
            FROM works_academic_all
            WHERE (arrayExists(x -> x ILIKE '%{kw}%', institution_names)
               OR arrayExists(x -> x ILIKE '%{clean}%', institution_names))
              AND subfield != ''
            GROUP BY subfield ORDER BY papers DESC LIMIT 8
        """)
        metrics = df.iloc[0].to_dict() if not df.empty else {}
        return json.dumps({
            "entity": entity_name,
            "metrics": metrics,
            "top_subfields": df_topics.to_dict(orient="records") if not df_topics.empty else [],
            "_source": "ClickHouse.works_academic_all",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"entity": entity_name, "error": str(e)}, ensure_ascii=False)


class DataScientistAgent(BaseSpecialistAgent):
    """
    Discovery Engine del enjambre ScientistOne.
    Recibe el ExperimentBrief del PI y ejecuta las consultas necesarias
    devolviendo hallazgos con evidence_tags por valor.
    """

    def __init__(self, session_id: Optional[str] = None, **kwargs):
        self.session_id = session_id
        tools = [
            query_duckdb_analytics,
            query_clickhouse_analytics,
            query_parquet_academic_cache,
            get_consolidated_scholar_summary,
            get_entity_bibliometric_profile,
        ]
        role = (
            "Eres el Discovery Engine del enjambre científico ScientistOne. "
            "Recibes un ExperimentBrief con la entidad identificada, el intent_type y los datos "
            "precargados de DuckDB. Tu función es VERIFICAR y ENRIQUECER esos datos usando tus "
            "herramientas (DuckDB, ClickHouse, Parquet). "
            "REGLA CRÍTICA: Nunca inventes números. "
            "Si los datos de DuckDB ya están disponibles en el brief, úsalos directamente. "
            "Solo consulta ClickHouse si faltan métricas clave o si el brief no encontró datos. "
            "Cada valor que reportes debe indicar su fuente: DuckDB.tabla o ClickHouse.tabla."
        )
        super().__init__(name="DataScientistAgent", role_description=role, tools=tools, **kwargs)
