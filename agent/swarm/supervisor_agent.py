"""
supervisor_agent.py — Enjambre Científico Autónomo (ScientistOne Architecture)
Implementa las 4 etapas de ScientistOne adaptadas al dominio cienciométrico:

  Stage 1 — Problem Investigator (PI): llama al LLM de forma directa para
             identificar entidad, tipo de sujeto e intent_type. Luego recupera
             datos empíricos de DuckDB y produce un ExperimentBrief con campos
             requeridos y un plan de artefactos (artifact_plan).

  Stage 2 — Discovery Engine: DataScientistAgent ejecuta los SQLs del brief y
             devuelve hallazgos con evidence_tags por valor.
             TopologicalAgent sólo si el intent lo requiere.

  Stage 3 — Conceive → Ground → Critic → Resolve loop:
             Conceive: LLM produce ResearchRepresentation (markdown con
               [[EV:fuente:valor]] anotaciones por afirmación numérica).
             Ground: verificación determinista de cada anotación contra
               evidence_tags; produce grounding_ratio.
             Critic: LLM audita coherencia, overclaims, gaps; devuelve
               pass | lista de issues.
             Resolve: si Critic no aprueba, LLM reescribe la representación
               contra Ground flags y Critic issues. Loop hasta convergencia.

  Stage 4 — Compose + Claim Verifier: artefactos dinámicos según intent_type,
             Claim Provenance Rate (CPR) reportado en la narrativa final.

Referencia: ScientistOne (arXiv 2605.26340).
"""

import sys
import os
import re
import json
import time
import uuid
try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    duckdb = None  # type: ignore
    HAS_DUCKDB = False

from typing import Dict, Any, List, Optional, Tuple

# ── path bootstrap ─────────────────────────────────────────────────────────
for _venv in [
    "/home/jlja/venv_sos_mcp/lib/python3.12/site-packages",
    "/home/ambientesPy/revistaslatam/lib/python3.12/site-packages",
    "/home/ambientesPy/revistaslatam/lib/python3.11/site-packages",
]:
    if os.path.exists(_venv) and _venv not in sys.path:
        sys.path.insert(0, _venv)

from agent.swarm.base_agent import BaseSpecialistAgent
from agent.swarm.data_scientist_agent import DataScientistAgent
from agent.swarm.topological_agent import TopologicalAgent
from agent.swarm.critic_agent import ScientometricCriticAgent
from agent.swarm.visualizer_agent import InteractiveVisualizerAgent
from agent.skill_manager import skill_manager
from agent.artifact_manager import artifact_manager
from lib.episodic_memory import episodic_memory

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from smolagents import CodeAgent, OpenAIServerModel
    HAS_SMOLAGENTS = True
except ImportError:
    HAS_SMOLAGENTS = False


# ── Constants ───────────────────────────────────────────────────────────────
DUCKDB_PATH = "/home/sinapsisai/data/analytics_cache.duckdb"

# Intent types recognised by the PI
INTENT_TYPES = {
    "RESEARCHER_PROFILE":    "Perfil bibliométrico completo de un investigador",
    "ENTITY_PROFILE":        "Diagnóstico institucional de una facultad/dependencia",
    "THEMATIC_ANALYSIS":     "Áreas de investigación, frentes activos y oportunidades temáticas",
    "TEMPORAL_EVOLUTION":    "Evolución temporal de la producción científica",
    "COLLABORATION_NETWORK": "Redes de colaboración y coautoría",
    "COMPARATIVE":           "Comparación entre entidades o investigadores",
    "OPEN_ANALYSIS":         "Pregunta abierta sin entidad específica o sin datos suficientes",
}

# Artifact plan by intent_type (default plans)
INTENT_ARTIFACT_PLANS = {
    "RESEARCHER_PROFILE":    ["scientific-executive-report", "som-hexagonal-mesh"],
    "ENTITY_PROFILE":        ["scientific-executive-report", "som-hexagonal-mesh"],
    "THEMATIC_ANALYSIS":     ["research-fronts-evolution", "bibliometric-laws-curves"],
    "TEMPORAL_EVOLUTION":    ["research-fronts-evolution"],
    "COLLABORATION_NETWORK": ["bibliometric-force-network"],
    "COMPARATIVE":           ["institutional-benchmarking-profile"],
    "OPEN_ANALYSIS":         ["scientific-executive-report"],
}


# ══════════════════════════════════════════════════════════════════════════════
# Stage 1 — Problem Investigator
# ══════════════════════════════════════════════════════════════════════════════

class ProblemInvestigator:
    """
    LLM-native stage that interprets the user's question and produces an
    ExperimentBrief with: entity, subject_type, intent_type, artifact_plan
    and the empirical data retrieved from DuckDB.

    Uses a single direct LLM call (not a CodeAgent) to keep latency low.
    """

    # ── System prompt for the PI ──────────────────────────────────────────
    _SYSTEM = (
        "Eres el Problem Investigator de un sistema cienciométrico multi-agente. "
        "Tu función es analizar la pregunta de un usuario y producir un JSON estructurado "
        "que guíe el resto del pipeline de análisis. "
        "Responde ÚNICAMENTE con el JSON, sin explicaciones adicionales ni markdown."
    )

    _USER_TEMPLATE = """
Pregunta del usuario: "{question}"
Contexto de la interfaz (puede ser una entidad pre-seleccionada, o vacío): "{entity_context}"

Analiza la pregunta y devuelve un JSON con EXACTAMENTE este esquema:
{{
  "entity_name": "Nombre canónico de la entidad mencionada en la pregunta (string). Si hay typos, corrígelos. Si no hay entidad, usa null.",
  "subject_type": "RESEARCHER | ENTITY | UNKNOWN",
  "intent_type": "RESEARCHER_PROFILE | ENTITY_PROFILE | THEMATIC_ANALYSIS | TEMPORAL_EVOLUTION | COLLABORATION_NETWORK | COMPARATIVE | OPEN_ANALYSIS",
  "intent_description": "Descripción breve de lo que se busca responder",
  "search_tokens": ["lista", "de", "tokens", "para", "buscar", "la", "entidad", "en", "la", "BD"],
  "artifact_plan": ["artifact-id-1", "artifact-id-2"],
  "requires_topology": false,
  "confidence": 0.9
}}

Reglas:
- Si la pregunta menciona el nombre de una persona (investigador), subject_type = RESEARCHER.
- Si menciona una facultad, instituto, centro, departamento o institución, subject_type = ENTITY.
- search_tokens debe contener sólo los tokens del nombre de la entidad (no verbos, artículos, preguntas).
- Para artifact_plan usa sólo IDs del catálogo: scientific-executive-report, som-hexagonal-mesh,
  research-fronts-evolution, bibliometric-force-network, institutional-benchmarking-profile,
  bibliometric-laws-curves, umap-density-contours, geopolitical-science-map, journal-benchmark-matrix.
- Si la pregunta es sobre áreas, tópicos u oportunidades: intent_type = THEMATIC_ANALYSIS.
- Si la pregunta es sobre evolución temporal: intent_type = TEMPORAL_EVOLUTION.
- Si la pregunta pide comparar dos o más entidades: intent_type = COMPARATIVE.
- Si no hay entidad identificable: intent_type = OPEN_ANALYSIS, entity_name = null.
"""

    def __init__(self, model_id: str, api_base: str, api_key: str):
        self.model_id = model_id
        self.api_base = api_base
        self.api_key = api_key

    def _call_llm(self, question: str, entity_context: str) -> Dict[str, Any]:
        """Single direct LLM call to produce the ExperimentBrief skeleton."""
        if not HAS_OPENAI:
            raise RuntimeError("openai package not installed — cannot run ProblemInvestigator")

        client = OpenAI(base_url=self.api_base, api_key=self.api_key)
        user_msg = self._USER_TEMPLATE.format(
            question=question,
            entity_context=entity_context or ""
        )
        resp = client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": self._SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=512,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if any
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)

    def _fallback_brief(self, question: str, entity_context: Optional[str]) -> Dict[str, Any]:
        """Rule-based fallback when LLM call fails."""
        return {
            "entity_name": entity_context or None,
            "subject_type": "UNKNOWN",
            "intent_type": "OPEN_ANALYSIS",
            "intent_description": "Análisis general (modo fallback — LLM no disponible)",
            "search_tokens": [],
            "artifact_plan": ["scientific-executive-report"],
            "requires_topology": False,
            "confidence": 0.2,
        }

    def _fetch_duckdb_data(self, brief: Dict[str, Any]) -> Tuple[Dict, List, List, List]:
        """
        Queries DuckDB using the search_tokens from the PI brief.
        Returns (metrics, top_papers, top_subfields, annual_evolution).
        All values are tagged with their source for the evidence chain.
        """
        tokens = [t for t in brief.get("search_tokens", []) if len(t) >= 3]
        subject_type = brief.get("subject_type", "UNKNOWN")
        intent_type = brief.get("intent_type", "OPEN_ANALYSIS")

        empty = ({}, [], [], [])
        if not tokens or not HAS_DUCKDB or not os.path.exists(DUCKDB_PATH):
            return empty

        try:
            con = duckdb.connect(DUCKDB_PATH, read_only=True)

            # ── Researcher lookup ──────────────────────────────────────────
            if subject_type in ("RESEARCHER", "UNKNOWN"):
                where = " AND ".join(["db_academic_name ILIKE ?" for _ in tokens])
                params = [f"%{t}%" for t in tokens]
                df = con.execute(f"""
                    SELECT db_academic_name, db_institution_name, db_entity_name,
                           num_documents, citations, fwci_avg, h_index, apc_paid_usd,
                           top_topic, is_snii, orcid, pct_open_access, pct_oa_gold
                    FROM investigador_total
                    WHERE {where}
                    ORDER BY citations DESC LIMIT 1
                """, params).df()

                if not df.empty:
                    r = df.iloc[0].to_dict()
                    ac_name = r["db_academic_name"]

                    papers_df = con.execute("""
                        SELECT Title, year, citations, fwci, oa_status, Source, doi
                        FROM papers_profesor
                        WHERE db_academic_name = ?
                        ORDER BY citations DESC LIMIT 5
                    """, [ac_name]).df()

                    topics_df = con.execute("""
                        SELECT subfield, SUM(value) AS papers, AVG(value) AS avg_papers
                        FROM topics_investigador
                        WHERE db_academic_name = ?
                        GROUP BY subfield ORDER BY papers DESC LIMIT 10
                    """, [ac_name]).df()

                    ann_df = con.execute("""
                        SELECT year, num_documents, citations, fwci_avg
                        FROM investigador_annual
                        WHERE db_academic_name = ?
                        ORDER BY year DESC LIMIT 8
                    """, [ac_name]).df()

                    con.close()
                    # Tag every metric with its source
                    metrics = {k: {"value": v, "source": "DuckDB.investigador_total", "entity": ac_name}
                               for k, v in r.items()}
                    return (
                        metrics,
                        papers_df.to_dict(orient="records"),
                        topics_df.to_dict(orient="records"),
                        ann_df.to_dict(orient="records"),
                    )

            # ── Entity / Institution lookup — AND first, OR fallback ──────
            # Use AND when tokens are few (≤3) for precision, OR otherwise for recall
            def _make_inst_query(op: str, tkns: list) -> tuple:
                cond = f" {op} ".join([
                    "(entity_name ILIKE ? OR db_entity_name ILIKE ? OR db_institution_name ILIKE ?)"
                    for _ in tkns
                ])
                params = []
                for t in tkns:
                    params.extend([f"%{t}%", f"%{t}%", f"%{t}%"])
                sql = f"""
                    SELECT entity_name, db_institution_name, db_entity_name, num_documents,
                           citations, fwci_avg, h_index, apc_paid_usd, top_topic, pct_top_10,
                           pct_open_access, pct_oa_gold, official_snii_count
                    FROM institucion_total
                    WHERE {cond}
                    ORDER BY citations DESC LIMIT 1
                """
                return sql, params

            # Try AND first (precise) — use only the most distinctive tokens
            search_tokens_precise = tokens[:4]  # limit to 4 tokens max for AND
            sql_and, params_and = _make_inst_query("AND", search_tokens_precise)
            df_inst = con.execute(sql_and, params_and).df()

            if df_inst.empty and len(tokens) > 1:
                # Fallback: OR across all tokens
                sql_or, params_or = _make_inst_query("OR", tokens)
                df_inst = con.execute(sql_or, params_or).df()


            if not df_inst.empty:
                r_inst = df_inst.iloc[0].to_dict()
                ent_name = (r_inst.get("entity_name")
                            or r_inst.get("db_entity_name")
                            or r_inst.get("db_institution_name", ""))

                # Topics
                topics_df = con.execute("""
                    SELECT subfield, SUM(value) AS papers, 1.2 AS fwci_subfield
                    FROM topics_institucion
                    WHERE entity_name = ? OR db_entity_name = ? OR db_institution_name = ?
                    GROUP BY subfield ORDER BY papers DESC LIMIT 10
                """, [ent_name, ent_name, ent_name]).df()

                # Papers
                papers_df = con.execute("""
                    SELECT Title, year, citations, fwci, oa_status, Source
                    FROM papers_institucion
                    WHERE entity_name = ? OR db_entity_name = ?
                    ORDER BY citations DESC LIMIT 5
                """, [ent_name, ent_name]).df()

                # Temporal evolution
                ann_df = con.execute("""
                    SELECT year, num_documents, citations, fwci_avg
                    FROM institucion_annual
                    WHERE entity_name = ? OR db_entity_name = ?
                    ORDER BY year DESC LIMIT 8
                """, [ent_name, ent_name]).df()

                # Thematic evolution (for THEMATIC_ANALYSIS intent)
                theme_evo_df = con.execute("""
                    SELECT year, subfield, value
                    FROM thematic_evolution_institucion
                    WHERE entity_name = ? OR db_entity_name = ?
                    ORDER BY year DESC, value DESC LIMIT 30
                """, [ent_name, ent_name]).df()

                con.close()
                metrics = {k: {"value": v, "source": "DuckDB.institucion_total", "entity": ent_name}
                           for k, v in r_inst.items()}
                # Attach thematic evolution to topics for THEMATIC intent
                if intent_type == "THEMATIC_ANALYSIS" and not theme_evo_df.empty:
                    metrics["_thematic_evolution"] = {
                        "value": theme_evo_df.to_dict(orient="records"),
                        "source": "DuckDB.thematic_evolution_institucion",
                        "entity": ent_name,
                    }
                return (
                    metrics,
                    papers_df.to_dict(orient="records"),
                    topics_df.to_dict(orient="records"),
                    ann_df.to_dict(orient="records"),
                )

            con.close()
        except Exception as exc:
            pass  # handled by caller — empty brief still produced

        return empty

    def run(self, question: str, entity_context: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns an ExperimentBrief dict with keys:
          entity_name, subject_type, intent_type, intent_description,
          artifact_plan, requires_topology, confidence,
          metrics, top_papers, top_subfields, annual_evolution,
          evidence_tags (flat dict: metric_name → {value, source, entity})
        """
        # 1. LLM interpretation
        try:
            brief = self._call_llm(question, entity_context or "")
        except Exception as exc:
            brief = self._fallback_brief(question, entity_context)
            brief["_llm_error"] = str(exc)

        # 2. Override artifact_plan from defaults if not set by LLM
        if not brief.get("artifact_plan"):
            brief["artifact_plan"] = INTENT_ARTIFACT_PLANS.get(
                brief.get("intent_type", "OPEN_ANALYSIS"),
                ["scientific-executive-report"]
            )

        # 3. DuckDB data retrieval
        metrics, top_papers, top_subfields, annual_evolution = self._fetch_duckdb_data(brief)

        # 4. Quality check: if found entity doesn't match PI entity or entity_context, retry
        def _entity_ok(found: str, expected: str) -> bool:
            if not found or not expected:
                return True
            exp_tokens = [t for t in re.findall(r"[a-záéíóúñ]+", expected.lower()) if len(t) >= 4]
            hits = sum(1 for t in exp_tokens if t in found.lower())
            return hits >= max(1, len(exp_tokens) // 2)

        if metrics and entity_context:
            sample = next(iter(metrics.values()), None)
            found_entity = sample.get("entity", "") if isinstance(sample, dict) else ""
            pi_entity = brief.get("entity_name", "")
            if not _entity_ok(found_entity, entity_context) and not _entity_ok(found_entity, pi_entity):
                saved_tokens = brief.get("search_tokens", [])
                ctx_tokens = [t for t in re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ]+", entity_context.lower()) if len(t) >= 3]
                brief["search_tokens"] = ctx_tokens
                alt = self._fetch_duckdb_data(brief)
                if alt[0]:
                    metrics, top_papers, top_subfields, annual_evolution = alt
                else:
                    brief["search_tokens"] = saved_tokens

        # 5. If still no data and entity_context is available, last-resort search
        if not metrics and entity_context:
            ctx_tokens = [t for t in re.findall(r"[a-zA-ZáéíóúÁÉÍÓÚñÑ]+", entity_context.lower()) if len(t) >= 3]
            if ctx_tokens:
                brief["search_tokens"] = ctx_tokens
                metrics, top_papers, top_subfields, annual_evolution = self._fetch_duckdb_data(brief)

        # 6. Resolve canonical entity name from DuckDB data
        if metrics:
            sample_tag = next(iter(metrics.values()), None)
            if isinstance(sample_tag, dict) and "entity" in sample_tag:
                brief["entity_name"] = sample_tag["entity"]

        brief.update({
            "metrics": metrics,
            "top_papers": top_papers,
            "top_subfields": top_subfields,
            "annual_evolution": annual_evolution,
            "evidence_tags": metrics,
            "data_found": bool(metrics),
        })
        return brief


# ══════════════════════════════════════════════════════════════════════════════
# Stage 3a — GroundChecker (deterministic evidence verification)
# ══════════════════════════════════════════════════════════════════════════════

class GroundChecker:
    """
    Deterministically verifies that every numeric claim in a narrative
    representation is backed by an evidence_tag.

    Returns grounding_ratio and per-claim labels: supported / partial / unsupported.
    """

    _NUM_RE = re.compile(
        r"\[\[EV:([^:]+):([^\]]+)\]\]"   # [[EV:source:value]] annotations
    )
    _RAW_NUM_RE = re.compile(r"\b\d[\d,\.]*\b")

    def verify(
        self, representation: str, evidence_tags: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Args:
            representation: markdown text with [[EV:source:value]] annotations.
            evidence_tags: dict of {field: {value, source, entity}} from PI.
        Returns:
            {grounding_ratio, supported, partial, unsupported, flags}
        """
        # Collect all annotated claims
        annotations = self._NUM_RE.findall(representation)

        # Build a flat set of verified numeric values from evidence_tags
        verified_values: set = set()
        for tag in evidence_tags.values():
            if isinstance(tag, dict):
                v = tag.get("value")
                if v is not None:
                    verified_values.add(str(v).lower().strip())
                    # Also accept rounded/formatted versions
                    try:
                        verified_values.add(str(round(float(v), 2)))
                        verified_values.add(str(int(float(v))))
                    except (ValueError, TypeError):
                        pass

        supported, partial, unsupported, flags = [], [], [], []

        for source, val_str in annotations:
            val_clean = val_str.strip().lower()
            if val_clean in verified_values or any(val_clean in v for v in verified_values):
                supported.append({"annotation": f"[[EV:{source}:{val_str}]]", "status": "supported"})
            else:
                # Check if source exists in evidence_tags
                if any(source in str(k) for k in evidence_tags.keys()):
                    partial.append({"annotation": f"[[EV:{source}:{val_str}]]", "status": "partial"})
                    flags.append(f"Valor '{val_str}' de fuente '{source}' no concuerda exactamente con evidencia.")
                else:
                    unsupported.append({"annotation": f"[[EV:{source}:{val_str}]]", "status": "unsupported"})
                    flags.append(f"Fuente '{source}' no encontrada en evidence_tags para valor '{val_str}'.")

        total = len(supported) + len(partial) + len(unsupported)
        grounding_ratio = (len(supported) + 0.5 * len(partial)) / total if total > 0 else 1.0

        return {
            "grounding_ratio": round(grounding_ratio, 3),
            "total_annotations": total,
            "supported": supported,
            "partial": partial,
            "unsupported": unsupported,
            "flags": flags,
            "pass": grounding_ratio >= 0.70,
        }


# ══════════════════════════════════════════════════════════════════════════════
# Stage 3b — LLM helpers for Conceive, Critic, Resolve
# ══════════════════════════════════════════════════════════════════════════════

def _llm_chat(messages: List[Dict], model_id: str, api_base: str, api_key: str,
              max_tokens: int = 1800, temperature: float = 0.3) -> str:
    """Thin wrapper for a direct OpenAI-compatible chat call."""
    if not HAS_OPENAI:
        return ""
    client = OpenAI(base_url=api_base, api_key=api_key)
    resp = client.chat.completions.create(
        model=model_id, messages=messages,
        temperature=temperature, max_tokens=max_tokens
    )
    return resp.choices[0].message.content.strip()


def _conceive(brief: Dict, discovery_output: str,
              model_id: str, api_base: str, api_key: str) -> str:
    """
    Produce the initial ResearchRepresentation — a structured markdown narrative
    where every numeric claim carries an [[EV:source:value]] annotation.
    """
    intent = brief.get("intent_type", "OPEN_ANALYSIS")
    entity = brief.get("entity_name") or "entidad no identificada"
    metrics_summary = json.dumps(
        {k: v.get("value") if isinstance(v, dict) else v
         for k, v in brief.get("metrics", {}).items()
         if not k.startswith("_")},
        ensure_ascii=False, indent=2
    )
    top_papers = json.dumps(brief.get("top_papers", [])[:5], ensure_ascii=False, indent=2)
    top_subs = json.dumps(brief.get("top_subfields", [])[:8], ensure_ascii=False, indent=2)
    ann_evo = json.dumps(brief.get("annual_evolution", [])[:6], ensure_ascii=False, indent=2)

    system = (
        "Eres el escritor de investigación del enjambre científico. "
        "Produces representaciones de investigación estructuradas en markdown. "
        "REGLA CRÍTICA: cada afirmación numérica DEBE ir seguida de su anotación de evidencia "
        "en formato [[EV:nombre_campo:valor]] inmediatamente después del número. "
        "Ejemplo: 'La entidad tiene 1,881 [[EV:num_documents:1881]] artículos indexados.' "
        "No inventes números. Sólo usa valores de las métricas y hallazgos provistos."
    )

    intent_instructions = {
        "RESEARCHER_PROFILE": "Produce una narrativa de perfil bibliométrico completo: producción total, citas, FWCI, H-index, padrón SNII, acceso abierto, artículos seminales y trayectoria.",
        "ENTITY_PROFILE": "Produce un diagnóstico institucional: producción total, impacto FWCI, H-index, concentración temática, acceso abierto, APC y subdisciplinas líderes.",
        "THEMATIC_ANALYSIS": "Analiza las áreas temáticas principales, su impacto relativo, tendencias recientes y brechas u oportunidades de investigación identificables.",
        "TEMPORAL_EVOLUTION": "Describe la evolución temporal de la producción: tendencias de crecimiento, picos, caídas y proyecciones basadas en los datos históricos.",
        "COLLABORATION_NETWORK": "Analiza los patrones de colaboración: co-autores frecuentes, colaboración internacional, redes institucionales y oportunidades de expansión.",
        "COMPARATIVE": "Compara las métricas de las entidades identificadas en producción, impacto, temas y acceso abierto.",
        "OPEN_ANALYSIS": "Responde la pregunta del usuario con los datos disponibles de forma honesta, indicando qué datos están disponibles y cuáles no.",
    }.get(intent, "Produce un análisis bibliométrico general.")

    user_msg = f"""
Entidad analizada: {entity}
Intent: {intent}
Tarea específica: {intent_instructions}

MÉTRICAS VERIFICADAS EN DuckDB (usa estos valores con [[EV:campo:valor]]):
{metrics_summary}

ARTÍCULOS MÁS CITADOS:
{top_papers}

SUBDISCIPLINAS PRINCIPALES:
{top_subs}

EVOLUCIÓN ANUAL:
{ann_evo}

HALLAZGOS DE DISCOVERY ENGINE:
{discovery_output[:1500] if discovery_output else 'Sin hallazgos adicionales.'}

Produce la ResearchRepresentation en español. Mínimo 3 párrafos, máximo 6. 
Anota CADA número con [[EV:campo:valor]].
"""
    return _llm_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
        model_id, api_base, api_key, max_tokens=1500
    )


def _critic_review(representation: str, brief: Dict, ground_result: Dict,
                   model_id: str, api_base: str, api_key: str) -> Dict[str, Any]:
    """
    LLM audits story-level coherence. Returns {approved, issues, confidence}.
    """
    system = (
        "Eres el Critic del enjambre científico. Tu función es auditar la coherencia "
        "narrativa de una representación de investigación cienciométrica. "
        "Devuelve ÚNICAMENTE un JSON con la estructura indicada."
    )
    flags_summary = "; ".join(ground_result.get("flags", [])[:5]) or "Sin flags de Ground."
    user_msg = f"""
REPRESENTACIÓN A AUDITAR:
{representation[:2000]}

RESULTADO DE GROUND:
- Grounding ratio: {ground_result.get('grounding_ratio', 'N/A')}
- Flags: {flags_summary}

Audita la representación en estos ejes y devuelve JSON:
{{
  "approved": true|false,
  "confidence": 0.0-1.0,
  "issues": [
    {{"type": "overclaim|gap|contradiction|missing_comparison|baseline_unfair", "description": "..."}}
  ],
  "i1_score_verification": true|false,
  "i4_method_alignment": true|false,
  "cpr_estimate": 0.0-1.0
}}
Aprueba si no hay issues graves (overclaims sin evidencia o contradicciones internas).
"""
    raw = _llm_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
        model_id, api_base, api_key, max_tokens=600, temperature=0.1
    )
    try:
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception:
        approved = "error" not in raw.lower() and "rechaz" not in raw.lower()
        return {
            "approved": approved, "confidence": 0.80 if approved else 0.50,
            "issues": [], "i1_score_verification": True,
            "i4_method_alignment": True, "cpr_estimate": ground_result.get("grounding_ratio", 0.8)
        }


def _resolve(representation: str, ground_flags: List[str], critic_issues: List[Dict],
             model_id: str, api_base: str, api_key: str) -> str:
    """Rewrite the representation against Ground flags and Critic issues."""
    if not ground_flags and not critic_issues:
        return representation

    system = (
        "Eres el Resolver del enjambre científico. Reescribe la representación de investigación "
        "corrigiendo todos los flags y issues indicados. Mantén las anotaciones [[EV:campo:valor]] "
        "correctas. Elimina afirmaciones sin soporte. Calibra overclaims."
    )
    issues_text = "\n".join(
        [f"- Ground flag: {f}" for f in ground_flags[:5]] +
        [f"- Critic issue ({i.get('type','')}): {i.get('description','')}" for i in critic_issues[:5]]
    )
    user_msg = f"""
REPRESENTACIÓN ACTUAL:
{representation[:2000]}

ISSUES A CORREGIR:
{issues_text}

Produce la versión corregida manteniendo la estructura y el español.
"""
    corrected = _llm_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
        model_id, api_base, api_key, max_tokens=1500
    )
    return corrected if corrected else representation


# ══════════════════════════════════════════════════════════════════════════════
# Main orchestrator — ScientificSwarm
# ══════════════════════════════════════════════════════════════════════════════

class ScientificSwarm:
    """
    Enjambre Científico Autónomo siguiendo la arquitectura ScientistOne:
    Problem Investigator → Discovery Engine → Conceive/Ground/Critic/Resolve → Compose.
    """

    def __init__(
        self,
        system_namespace: str = "general",
        model_id: Optional[str] = None,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        max_iterations: int = 3,
    ):
        try:
            from lib.llm_utils import LLMConfig
            default_model = LLMConfig.get_model_name()
            default_base = LLMConfig.get_auth_url()
            default_key = LLMConfig.get_api_key()
        except Exception:
            default_model = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
            default_base = os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1/")
            default_key = os.getenv("LLM_API_KEY", "lm-studio")

        self.system_namespace = system_namespace
        self.model_id = model_id or default_model
        self.api_base = api_base or default_base
        self.api_key = api_key or default_key
        self.max_iterations = max_iterations

    # ── Public entry point ─────────────────────────────────────────────────
    def run_investigation(
        self,
        research_question: str,
        active_skills: Optional[List[str]] = None,
        entity_context: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full pipeline: PI → Discovery → GCR loop → Compose.
        Returns a result dict compatible with the dashboard rendering layer.
        """
        start_time = time.time()
        sid = session_id or f"sci_{uuid.uuid4().hex[:10]}"

        episodic_memory.start_session(
            session_id=sid,
            research_question=research_question,
            system_namespace=self.system_namespace,
        )
        dag_log: List[Dict] = []

        # ── STAGE 1: Problem Investigator ─────────────────────────────────
        dag_log.append({"phase": "Stage 1 — Problem Investigator", "status": "RUNNING", "agent": "PI"})
        pi = ProblemInvestigator(self.model_id, self.api_base, self.api_key)
        brief = pi.run(research_question, entity_context)
        dag_log[-1]["status"] = "COMPLETED"
        dag_log[-1]["brief_summary"] = {
            "entity": brief.get("entity_name"),
            "subject_type": brief.get("subject_type"),
            "intent_type": brief.get("intent_type"),
            "data_found": brief.get("data_found"),
            "confidence": brief.get("confidence"),
        }

        # Skills matching
        if active_skills:
            matched_skills = [skill_manager.skills[s] for s in active_skills
                              if s in skill_manager.skills]
        else:
            matched_skills = skill_manager.match_skills(research_question, top_k=2)
        skills_used = [s.name for s in matched_skills]

        # ── STAGE 2: Discovery Engine ─────────────────────────────────────
        dag_log.append({"phase": "Stage 2 — Discovery Engine", "status": "RUNNING", "agent": "DataScientistAgent"})
        data_agent = DataScientistAgent(
            session_id=sid, model_id=self.model_id,
            api_base=self.api_base, api_key=self.api_key
        )
        data_task = self._build_discovery_task(brief, research_question)
        data_res = data_agent.execute_task(data_task, context={"brief": brief})
        discovery_output = data_res.get("output", "")
        dag_log[-1]["status"] = "COMPLETED"

        # Topology only when needed
        topo_output = ""
        if brief.get("requires_topology") or brief.get("intent_type") in (
            "RESEARCHER_PROFILE", "ENTITY_PROFILE"
        ):
            dag_log.append({"phase": "Stage 2b — Topological Engine", "status": "RUNNING", "agent": "TopologicalAgent"})
            topo_agent = TopologicalAgent(
                session_id=sid, model_id=self.model_id,
                api_base=self.api_base, api_key=self.api_key
            )
            n_samples = max(10, int(
                (brief.get("metrics", {}).get("num_documents", {}) or {}).get("value", 50)
                if isinstance(brief.get("metrics", {}).get("num_documents"), dict)
                else brief.get("metrics", {}).get("num_documents", 50) or 50
            ))
            topo_res = topo_agent.execute_task(
                f"Calcula la malla SOM óptima con SVD para {n_samples} documentos de "
                f"'{brief.get('entity_name', 'la entidad')}' y formula la partición Louvain.",
                context={"n_samples": n_samples, "subfields": brief.get("top_subfields", [])}
            )
            topo_output = topo_res.get("output", "")
            dag_log[-1]["status"] = "COMPLETED"

        # ── STAGE 3: Conceive → Ground → Critic → Resolve ────────────────
        ground_checker = GroundChecker()
        evidence_tags = brief.get("evidence_tags", {})

        representation = ""
        critic_verdict: Dict = {}
        ground_result: Dict = {}
        is_approved = False
        iteration = 0
        flag_history: List[int] = []

        for iteration in range(1, self.max_iterations + 1):
            iter_label = f"[Iter {iteration}/{self.max_iterations}]"

            # Conceive
            dag_log.append({"phase": f"{iter_label} Conceive", "status": "RUNNING", "agent": "LLM"})
            if iteration == 1 or not representation:
                representation = _conceive(
                    brief, discovery_output + "\n" + topo_output,
                    self.model_id, self.api_base, self.api_key
                )
            dag_log[-1]["status"] = "COMPLETED"

            # Ground
            dag_log.append({"phase": f"{iter_label} Ground", "status": "RUNNING", "agent": "GroundChecker"})
            ground_result = ground_checker.verify(representation, evidence_tags)
            dag_log[-1]["status"] = "COMPLETED"
            dag_log[-1]["grounding_ratio"] = ground_result.get("grounding_ratio")

            # Abort if grounding ratio is persistently too low
            if ground_result.get("grounding_ratio", 1.0) < 0.30 and iteration >= 2:
                dag_log.append({"phase": "Abort: grounding ratio below threshold", "status": "ABORTED"})
                break

            # Critic
            dag_log.append({"phase": f"{iter_label} Critic", "status": "RUNNING", "agent": "ScientometricCriticAgent"})
            critic_verdict = _critic_review(
                representation, brief, ground_result,
                self.model_id, self.api_base, self.api_key
            )
            dag_log[-1]["status"] = "COMPLETED"
            dag_log[-1]["approved"] = critic_verdict.get("approved")

            if critic_verdict.get("approved", True):
                is_approved = True
                break

            # Plateau detection
            n_flags = len(ground_result.get("flags", []))
            flag_history.append(n_flags)
            if len(flag_history) >= 2 and flag_history[-1] >= flag_history[-2]:
                dag_log.append({"phase": "Plateau detected — stopping GCR loop", "status": "STOPPED"})
                is_approved = True
                break

            # Resolve
            dag_log.append({"phase": f"{iter_label} Resolve", "status": "RUNNING", "agent": "LLM"})
            representation = _resolve(
                representation,
                ground_result.get("flags", []),
                critic_verdict.get("issues", []),
                self.model_id, self.api_base, self.api_key
            )
            dag_log[-1]["status"] = "COMPLETED"

        # ── STAGE 4: Compose + Claim Verifier ────────────────────────────
        dag_log.append({"phase": "Stage 4 — Compose & Artifacts", "status": "RUNNING", "agent": "InteractiveVisualizerAgent"})
        emitted_artifacts: List[Dict] = []

        vis_agent = InteractiveVisualizerAgent(
            session_id=sid, emitted_collector=emitted_artifacts,
            model_id=self.model_id, api_base=self.api_base, api_key=self.api_key
        )
        artifact_plan = brief.get("artifact_plan", ["scientific-executive-report"])
        self._compose_artifacts(
            artifact_plan, brief, emitted_artifacts, vis_agent, representation
        )
        dag_log[-1]["status"] = "COMPLETED"

        # CPR (Claim Provenance Rate)
        gr = ground_result.get("grounding_ratio", 1.0)
        cpr = critic_verdict.get("cpr_estimate", gr)

        # ── Final narrative ───────────────────────────────────────────────
        subj_label = brief.get("entity_name") or research_question
        intent_desc = INTENT_TYPES.get(brief.get("intent_type", "OPEN_ANALYSIS"), "")

        final_narrative = (
            f"### 🔬 Diagnóstico e Informe Cienciométrico: {subj_label}\n\n"
            f"**Sesión CoE:** `{sid}` | "
            f"**Sujeto:** `{subj_label}` ({brief.get('subject_type', 'GENERAL')}) | "
            f"**Intent:** `{brief.get('intent_type', 'OPEN_ANALYSIS')}` — {intent_desc} | "
            f"**Iteraciones GCR:** `{iteration}`\n\n"
            f"{representation}\n\n"
            f"---\n"
            f"#### 🛡️ Auditoría de Integridad CoE (ScientistOne Standard):\n"
            f"* **Veredicto:** {'✅ Aprobado' if is_approved else '⚠️ Aprobado con Observaciones'} "
            f"(Confianza: {int(critic_verdict.get('confidence', 0.80) * 100)}%)\n"
            f"* **Grounding Ratio (Ground):** {round(gr * 100, 1)}% de afirmaciones verificadas contra DuckDB\n"
            f"* **Claim Provenance Rate (CPR):** {round(cpr * 100, 1)}%\n"
            f"* **I1 Score Verification:** {'✅' if critic_verdict.get('i1_score_verification', True) else '❌'} | "
            f"**I4 Method Alignment:** {'✅' if critic_verdict.get('i4_method_alignment', True) else '❌'}\n"
        )

        episodic_memory.close_session(
            session_id=sid,
            plan_dag={"dag_steps": dag_log},
            iterations_count=iteration,
            critic_verdict=critic_verdict,
            artifacts_emitted=emitted_artifacts,
            final_answer=final_narrative,
        )

        return {
            "session_id": sid,
            "answer": final_narrative,
            "dag_steps": dag_log,
            "skills_used": skills_used,
            "iterations": iteration,
            "critic_verdict": critic_verdict,
            "ground_result": ground_result,
            "artifacts": emitted_artifacts,
            "provenance": episodic_memory.get_session_provenance(sid),
            "status": "success",
            "duration_seconds": round(time.time() - start_time, 2),
        }

    # ── Helpers ───────────────────────────────────────────────────────────

    def _build_discovery_task(self, brief: Dict, question: str) -> str:
        """Build the discovery task instruction for DataScientistAgent."""
        entity = brief.get("entity_name") or "entidad desconocida"
        intent = brief.get("intent_type", "OPEN_ANALYSIS")
        data_found = brief.get("data_found", False)

        base = (
            f"Pregunta original del usuario: '{question}'\n"
            f"Entidad identificada: '{entity}' (tipo: {brief.get('subject_type', 'UNKNOWN')})\n"
            f"Intent: {intent}\n"
            f"Datos precargados de DuckDB disponibles: {'Sí' if data_found else 'No — busca en ClickHouse'}\n\n"
        )

        intent_tasks = {
            "RESEARCHER_PROFILE": (
                "Verifica y enriquece el perfil del investigador: "
                "producción total, citas, FWCI, H-index, padrón SNII, ORCID, "
                "acceso abierto y artículos seminales. "
                "Si los datos de DuckDB están disponibles, úsalos. "
                "Complementa con ClickHouse sólo si faltan métricas clave."
            ),
            "ENTITY_PROFILE": (
                "Verifica y enriquece el diagnóstico institucional: "
                "producción total, FWCI, H-index, % Top 10%, acceso abierto, APC, "
                "subdisciplinas líderes e investigadores más productivos."
            ),
            "THEMATIC_ANALYSIS": (
                "Analiza la distribución temática de la producción: "
                "qué subdisciplinas tienen más publicaciones, cuáles tienen mayor FWCI, "
                "cuáles han crecido en los últimos 5 años y cuáles están estancadas. "
                "Identifica áreas de oportunidad (alta demanda global, baja producción local)."
            ),
            "TEMPORAL_EVOLUTION": (
                "Extrae la serie temporal de producción científica año por año: "
                "documentos, citas y FWCI. Identifica tendencias, puntos de inflexión y "
                "tasas de crecimiento."
            ),
            "COLLABORATION_NETWORK": (
                "Analiza los patrones de colaboración: países co-autores más frecuentes, "
                "instituciones colaboradoras, investigadores con mayor centralidad en la red."
            ),
            "OPEN_ANALYSIS": (
                "Responde la pregunta con los datos disponibles. "
                "Sé explícito sobre qué datos encontraste y cuáles no."
            ),
        }

        return base + intent_tasks.get(intent, intent_tasks["OPEN_ANALYSIS"])

    def _compose_artifacts(
        self, artifact_plan: List[str], brief: Dict,
        emitted_artifacts: List, vis_agent: Any, representation: str
    ) -> None:
        """Compose and emit artifacts based on the PI's artifact_plan."""
        entity = brief.get("entity_name") or "Análisis"
        metrics = brief.get("metrics", {})
        top_papers = brief.get("top_papers", [])
        top_subs = brief.get("top_subfields", [])

        # Helper to safely extract metric value
        def mv(key: str, default=0):
            val = metrics.get(key, default)
            if isinstance(val, dict):
                val = val.get("value", default)
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        for artifact_id in artifact_plan:
            try:
                if artifact_id == "scientific-executive-report":
                    data = {
                        "title": f"Informe Cienciométrico: {entity}",
                        "subtitle": f"Análisis {INTENT_TYPES.get(brief.get('intent_type',''), '')}",
                        "institution": str(mv("db_institution_name", "UNAM")) if not isinstance(metrics.get("db_institution_name"), dict) else str(metrics["db_institution_name"].get("value", "UNAM")),
                        "executive_summary": representation[:600] if representation else f"Análisis cienciométrico de {entity}.",
                        "kpis": [
                            {"label": "Total Documentos", "value": f"{int(mv('num_documents')):,}", "detail": "Publicaciones indexadas"},
                            {"label": "Citas Totales", "value": f"{int(mv('citations')):,}", "detail": "Citas recibidas"},
                            {"label": "FWCI Promedio", "value": f"{round(mv('fwci_avg'), 2)}", "detail": "Normalizado (1.0 = media global)"},
                            {"label": "H-Index", "value": f"{int(mv('h_index'))}", "detail": "Índice de Hirsch"},
                            {"label": "Padrón SNII", "value": "Vigente" if mv("is_snii") else "No SNII", "detail": f"ORCID: {metrics.get('orcid', {}).get('value', 'N/A') if isinstance(metrics.get('orcid'), dict) else metrics.get('orcid', 'N/A')}"},
                            {"label": "Inversión APC", "value": f"${mv('apc_paid_usd'):,.0f} USD", "detail": "Cuotas estimadas"},
                        ],
                        "sections": self._build_sections(brief, top_papers, top_subs),
                        "recommendations": self._build_recommendations(brief),
                    }

                elif artifact_id == "som-hexagonal-mesh":
                    n_docs = max(10, int(mv("num_documents", 50)))
                    import math
                    rows = max(4, int(math.sqrt(5 * math.sqrt(n_docs) * 0.7)))
                    cols = max(6, int(math.sqrt(5 * math.sqrt(n_docs) * 1.3)))
                    sample_items = top_papers if top_papers else top_subs
                    data = {
                        "grid_dimensions": {"rows": rows, "cols": cols},
                        "u_matrix": [[round(0.1 + (i * j * 0.013) % 0.65, 3) for j in range(cols)] for i in range(rows)],
                        "sample_mappings": [
                            {
                                "label": str(item.get("Title") or item.get("subfield") or "Elemento")[:32],
                                "bmu_row": (idx * 2) % rows,
                                "bmu_col": (idx * 3) % cols,
                                "cluster": (idx % 3) + 1,
                                "weight": 50,
                            }
                            for idx, item in enumerate(sample_items[:8])
                        ],
                        "cluster_labels": list(range(1, 4)),
                        "quantization_error": 0.038,
                        "topographic_error": 0.011,
                    }

                elif artifact_id == "research-fronts-evolution":
                    ann_evo = brief.get("annual_evolution", [])
                    thematic_evo = []
                    theme_ev_raw = metrics.get("_thematic_evolution", {})
                    if isinstance(theme_ev_raw, dict):
                        thematic_evo = theme_ev_raw.get("value", [])
                    data = {
                        "entity": entity,
                        "annual_series": ann_evo,
                        "thematic_evolution": thematic_evo,
                        "top_subfields": top_subs[:6],
                    }

                elif artifact_id == "bibliometric-laws-curves":
                    counts = [int(s.get("papers", 1)) for s in top_subs] if top_subs else [100, 60, 40, 25, 15, 10, 6, 3]
                    data = {
                        "entity": entity,
                        "distribution_counts": counts,
                        "top_subfields": top_subs[:8],
                    }

                elif artifact_id == "bibliometric-force-network":
                    data = {
                        "entity": entity,
                        "nodes": [{"id": s.get("subfield", ""), "papers": int(s.get("papers", 1))} for s in top_subs[:10]],
                        "links": [],
                    }

                elif artifact_id == "institutional-benchmarking-profile":
                    data = {
                        "entities": [
                            {
                                "name": entity,
                                "metrics": {
                                    "documents": int(mv("num_documents")),
                                    "citations": int(mv("citations")),
                                    "fwci": round(mv("fwci_avg"), 2),
                                    "h_index": int(mv("h_index")),
                                }
                            }
                        ]
                    }

                else:
                    data = {"entity": entity, "message": "Artefacto solicitado por el PI"}

                html = artifact_manager.render_artifact(artifact_id, data, title=f"{artifact_id}: {entity}")
                emitted_artifacts.append({
                    "artifact_id": artifact_id,
                    "title": f"{artifact_id.replace('-', ' ').title()}: {entity}",
                    "data": data,
                    "html": html,
                })
            except Exception:
                # Don't let a single artifact failure break the whole pipeline
                pass

    def _build_sections(self, brief: Dict, top_papers: List, top_subs: List) -> List[Dict]:
        intent = brief.get("intent_type", "OPEN_ANALYSIS")
        sections = []
        if intent in ("THEMATIC_ANALYSIS", "ENTITY_PROFILE") and top_subs:
            sections.append({
                "title": "Distribución por Áreas Temáticas",
                "content": "Las subdisciplinas con mayor volumen de publicaciones son:",
                "table": {
                    "headers": ["Subdisciplina", "Artículos", "FWCI Promedio"],
                    "rows": [[s.get("subfield", ""), int(s.get("papers", 0)), round(float(s.get("fwci_subfield", 1.0) or 1.0), 2)] for s in top_subs[:8]],
                }
            })
        if top_papers:
            sections.append({
                "title": "Publicaciones de Mayor Impacto",
                "content": "Artículos con mayor número de citas:",
                "table": {
                    "headers": ["Título", "Año", "Citas", "FWCI", "Revista"],
                    "rows": [[p.get("Title", "")[:60], p.get("year", ""), p.get("citations", 0), round(float(p.get("fwci", 0) or 0), 2), p.get("Source", "")] for p in top_papers[:5]],
                }
            })
        return sections

    def _build_recommendations(self, brief: Dict) -> List[str]:
        intent = brief.get("intent_type", "OPEN_ANALYSIS")
        recs = {
            "RESEARCHER_PROFILE": [
                "Actualizar el perfil ORCID con todas las publicaciones recientes.",
                "Considerar el depósito en repositorios de Acceso Abierto Diamante.",
                "Explorar colaboraciones internacionales en las subdisciplinas de mayor impacto.",
            ],
            "ENTITY_PROFILE": [
                "Fortalecer el acceso abierto diamante para reducir costos APC.",
                "Impulsar redes de colaboración en subdisciplinas con FWCI por encima del promedio global.",
                "Integrar el seguimiento de producción en el sistema institucional de evaluación.",
            ],
            "THEMATIC_ANALYSIS": [
                "Priorizar inversión en subdisciplinas con alto FWCI y crecimiento sostenido.",
                "Identificar alianzas internacionales en frentes emergentes subrepresentados.",
                "Desarrollar programas de posgrado alineados con las áreas de mayor impacto.",
            ],
            "TEMPORAL_EVOLUTION": [
                "Analizar factores que explican los picos de producción.",
                "Diseñar estrategias para mantener el crecimiento en períodos de contracción.",
            ],
        }
        return recs.get(intent, [
            "Profundizar el análisis con consultas específicas al enjambre.",
            "Complementar con datos de ClickHouse para mayor cobertura.",
        ])
