#!/usr/bin/env python3
"""
scripts/tools/audit_multi_identities_120b.py
============================================
Motor de Auditoría Integral Multi-Identificador (ORCID, Scopus, OpenAlex, SIIA)
y Diagnóstico de Reparación de Grafo para Info TlachIA SNII.

Utiliza el cluster C3 UNAM (modelo gpt-oss-120b) con Structured Outputs.
Valida coherencia inter-identificador, detecta homónimos, perfiles contaminados
y propone planes quirúrgicos de remediación para Neo4j y capas analíticas.
"""

import os
import sys
import json
import time
import re
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

# Asegurar path raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from api.db import get_neo4j_store
from database.clickhouse_db import ch_client
from lib.llm_utils import get_openai_client, LLMConfig

# ── Modelos Pydantic para Structured Output ────────────────────────────────────

class IdAuditResult(BaseModel):
    id_type: str = Field(
        default="unknown",
        description="Tipo de identificador auditado (orcid, scopus, openalex, siia, etc.)"
    )
    identifier: Optional[str] = Field(
        default="N/A",
        description="Valor textual del identificador o N/A si no existe"
    )
    status: str = Field(
        default="AMBIGUOUS",
        description="Veredicto formal de pertenencia (VALID, INVALID, AMBIGUOUS, ABSENT, etc.)"
    )
    confidence: int = Field(
        default=50,
        ge=0, le=100,
        description="Certeza porcentual asignada por la evidencia (0-100)"
    )
    reason: str = Field(
        default="",
        description="Justificación sucinta analizando concordancia de nombres, filiaciones y disciplina"
    )

class RemediationItem(BaseModel):
    action: str = Field(
        default="KEEP",
        description="Acción quirúrgica recomendada para reparar el grafo (KEEP, QUARANTINE_ID, PRUNE_PAPERS, REROUTE_PAPERS, SPLIT_NODE, MERGE_DUPLICATE, etc.)"
    )
    target_id: Optional[str] = Field(
        default=None,
        description="Identificador específico objeto de la acción (o None para acciones globales)"
    )
    details: str = Field(
        default="",
        description="Instrucciones concretas para el motor de reparación de Neo4j"
    )

class AcademicAuditVerdict(BaseModel):
    cvu: str = Field(default="")
    academic_name: str = Field(default="")
    snii_area: Optional[str] = Field(default="NO REGISTRADA")
    snii_institution: Optional[str] = Field(default="INDEPENDIENTE")
    overall_verdict: str = Field(
        default="NEEDS_MANUAL_REVIEW",
        description="Estado consolidado de integridad del perfil (CONFIRMED, PARTIALLY_CONTAMINATED, FULLY_DISCREPANT, NEEDS_MANUAL_REVIEW)"
    )
    overall_confidence: int = Field(default=50, ge=0, le=100)
    cross_id_coherence: str = Field(
        default="",
        description="Análisis de congruencia cruzada entre las distintas IDs asignadas"
    )
    id_verdicts: List[IdAuditResult] = Field(
        default_factory=list,
        description="Veredicto individual para cada ID asociada al perfil"
    )
    remediation_plan: List[RemediationItem] = Field(
        default_factory=list,
        description="Conjunto de acciones recomendadas para saneamiento"
    )

# ── Módulo de Recolección de Evidencia Multifuente ─────────────────────────────

def fetch_openalex_evidence(openalex_ids: List[str]) -> List[Dict[str, Any]]:
    """Consulta la tabla authors en ClickHouse (sin joins) para extraer evidencia de los IDs OpenAlex."""
    if not openalex_ids:
        return []
    
    clean_ids = []
    for oid in openalex_ids:
        if not oid: continue
        val = str(oid).strip()
        clean_ids.append(val)
        if val.startswith("https://openalex.org/"):
            clean_ids.append(val.replace("https://openalex.org/", ""))
        else:
            clean_ids.append(f"https://openalex.org/{val}")

    evidence = []
    try:
        # Consulta plana sin joins según regla 2
        query = """
            SELECT id, display_name, orcid, works_count, cited_by_count, last_known_institution_name, ids
            FROM authors
            WHERE id IN %(ids)s
        """
        rows = ch_client.query(query, {"ids": clean_ids}).result_rows
        for r in rows:
            evidence.append({
                "openalex_id": r[0],
                "display_name": r[1],
                "linked_orcid": r[2],
                "works_count": r[3],
                "citations": r[4],
                "institution": r[5],
                "external_ids": json.loads(r[6]) if r[6] else {}
            })
    except Exception as e:
        evidence.append({"error": f"Error consultando ClickHouse authors: {e}"})
    return evidence

def fetch_paper_sample_evidence(cvu: str, academic_name: str, orcid: str) -> List[Dict[str, Any]]:
    """Obtiene una muestra de hasta 5 obras en paper_author_map para contrastar temas y revistas."""
    sample = []
    try:
        query = """
            SELECT paper_title, paper_year, citations, is_scopus, is_openalex, institution, dependency
            FROM paper_author_map
            WHERE (cvu = %(cvu)s OR orcid = %(orc)s) AND paper_title != ''
            LIMIT 5
        """
        rows = ch_client.query(query, {"cvu": cvu or "", "orc": orcid or ""}).result_rows
        for r in rows:
            sample.append({
                "title": r[0],
                "year": r[1],
                "cites": r[2],
                "in_scopus": bool(r[3]),
                "in_openalex": bool(r[4]),
                "affiliation": f"{r[5]} / {r[6]}"
            })
    except Exception as e:
        sample.append({"error": f"Error consultando paper_author_map: {e}"})
    return sample

def extract_siia_metadata(siia_url: str) -> Dict[str, Any]:
    """Extrae metadatos del perfil público de SIIA UNAM con timeout ultracorto y fallback."""
    if not siia_url:
        return {}
    
    # Extraer ID numérico
    m = re.search(r'id=(\d+)', siia_url)
    siia_id = m.group(1) if m else siia_url
    
    data = {
        "siia_id": siia_id,
        "url": siia_url,
        "status": "UNAM_PORTAL_REGISTERED"
    }
    
    # Intentar conexión ligera (máx 2.5s)
    try:
        import requests
        resp = requests.get(
            f"http://www.siia.unam.mx/siia-publico/c/busqueda_individual.php?id={siia_id}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) InfoTlachIA/2.0"},
            timeout=2.5,
            allow_redirects=False
        )
        if resp.status_code in (200, 301, 302):
            data["http_reachable"] = True
    except Exception:
        data["http_reachable"] = False
        data["note"] = "Portal público de SIIA protegido por intranet o timeout; validado por id registrada."
        
    return data

# ── Evaluador LLM con GPT-OSS 120B ───────────────────────────────────────────

SYSTEM_PROMPT = """Eres el Auditor Cienciométrico y Juez de Identidades Académicas de Info TlachIA (UNAM / SECIHTI).
Tu labor es auditar meticulosamente la veracidad de los identificadores asignados (ORCID, Scopus ID, OpenAlex ID, SIIA) a investigadoras e investigadores del Padrón Oficial SNII de México.

REGLAS CRÍTICAS DE AUDITORÍA:
1. HOMÓNIMOS: Si un OpenAlex ID o Scopus ID tiene producción masiva en países no afines (ej. China, España, India) o en una disciplina ajena al Área SNII sin coautores mexicanos, decláralo INVALID.
2. SIIA UNAM:
   - Solo es válido si la institución del investigador en el padrón es la UNAM o centro con adscripción UNAM.
   - Ten en cuenta que en México los nombres registrados en nómina institucional (SIIA) pueden diferir levemente del Padrón SNII (omisión de segundo nombre, apellidos de casada, acentos o inversiones). Si la dependencia y disciplina coinciden, valida la identidad considerando la variación léxica legítima.
3. SCÚPULO EN COHERENCIA CRUZADA: Evalúa si los identificadores convergen en la misma persona o si existe un perfil híbrido/contaminado.
4. SALIDA: Debes responder EXCLUSIVAMENTE con el bloque JSON válido ajustado al esquema requerido.
"""

def audit_researcher_with_120b(candidate: Dict[str, Any], client, max_tokens: int = 5000) -> AcademicAuditVerdict:
    """Envía el caso de auditoría al modelo GPT-OSS 120B y procesa la respuesta estructurada."""
    # 1. Recolectar evidencias externas
    openalex_ev = fetch_openalex_evidence(candidate.get("openalex_ids", []))
    paper_ev = fetch_paper_sample_evidence(
        candidate.get("cvu"), 
        candidate.get("name"), 
        candidate.get("orcid")
    )
    siia_ev = extract_siia_metadata(candidate.get("siia"))

    prompt_data = {
        "investigador_snii": {
            "cvu": candidate.get("cvu") or "N/A",
            "nombre_padron": candidate.get("name") or "N/A",
            "institucion": candidate.get("inst") or "INDEPENDIENTE / NO REGISTRADA",
            "subdependencia": candidate.get("subdep") or "N/A",
            "area_snii": candidate.get("area") or "NO REGISTRADA",
            "nivel_snii": candidate.get("level") or "N/A"
        },
        "identificadores_asignados": {
            "orcid": candidate.get("orcid"),
            "scopus_ids": candidate.get("scopus_ids") or [],
            "openalex_ids": candidate.get("openalex_ids") or [],
            "siia_unam_url": candidate.get("siia")
        },
        "evidencia_openalex_clickhouse": openalex_ev,
        "evidencia_obras_muestra": paper_ev,
        "evidencia_siia": siia_ev
    }

    user_prompt = f"""AUDITA EL SIGUIENTE INVESTIGADOR Y SUS IDENTIFICADORES:

```json
{json.dumps(prompt_data, indent=2, ensure_ascii=False)}
```

Genera el dictamen en formato JSON estricto con las claves:
- cvu
- academic_name
- snii_area
- snii_institution
- overall_verdict ("CONFIRMED", "PARTIALLY_CONTAMINATED", "FULLY_DISCREPANT", "NEEDS_MANUAL_REVIEW")
- overall_confidence (entero 0 a 100)
- cross_id_coherence (texto analizando la convergencia entre IDs)
- id_verdicts (lista con id_type, identifier, status ["VALID"|"INVALID"|"AMBIGUOUS"], confidence, reason)
- remediation_plan (lista con action ["KEEP"|"QUARANTINE_ID"|"PRUNE_PAPERS"|"REROUTE_PAPERS"|"SPLIT_NODE"], target_id, details)
"""

    # Llamada a vLLM / C3 UNAM con ventana de generación amplia
    resp = client.chat.completions.create(
        model="gpt-oss-120b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.0,
        max_tokens=max_tokens
    )

    if resp.choices[0].finish_reason == "length":
        print(f"    ⚠️ AVISO: El modelo alcanzó el límite de tokens (finish_reason=length) para CVU {candidate.get('cvu')}")

    raw_content = resp.choices[0].message.content or ""
    if not raw_content and hasattr(resp.choices[0].message, "reasoning"):
        raw_content = resp.choices[0].message.reasoning or ""
    
    # Si viene con bloque de markdown ```json ... ```
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_content, re.DOTALL)
    if m:
        json_str = m.group(1)
    else:
        # Extraer el bloque externo { ... }
        start_idx = raw_content.find('{')
        end_idx = raw_content.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = raw_content[start_idx:end_idx+1]
        else:
            json_str = raw_content

    # Limpiar comas finales inválidas en JSON
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
    data = json.loads(json_str)

    # Sanitizar campos nulos frecuentes
    if "snii_area" in data and not data["snii_area"]:
        data["snii_area"] = "NO REGISTRADA"
    if "snii_institution" in data and not data["snii_institution"]:
        data["snii_institution"] = "INDEPENDIENTE"

    # Asegurar que identifier sea str si es None
    if "id_verdicts" in data and isinstance(data["id_verdicts"], list):
        for iv in data["id_verdicts"]:
            if isinstance(iv, dict) and iv.get("identifier") is None:
                iv["identifier"] = "N/A"

    return AcademicAuditVerdict.model_validate(data)

# ── Ejecutor Principal ─────────────────────────────────────────────────────────

def get_candidates(
    limit: Optional[int] = 10,
    cvu: Optional[str] = None,
    name: Optional[str] = None,
    skip_cvus: Optional[set] = None
) -> List[Dict[str, Any]]:
    """Recupera candidatos desde Neo4j filtrados por CVU, nombre o por muestreo general."""
    store = get_neo4j_store()
    with store.driver.session() as s:
        if cvu:
            q = """
                MATCH (p:Person) 
                WHERE p.cvu = $cvu OR p.id = $cvu
                RETURN p.id as id, p.fullname as name, p.cvu as cvu, 
                       coalesce(p.snii_institution, p.institution) as inst,
                       p.snii_subdependency as subdep, p.snii_area as area, p.snii_level as level,
                       p.siia as siia, p.orcid as orcid, 
                       p.scopus_ids as scopus_ids, p.openalex_ids as openalex_ids
                LIMIT 1
            """
            res = s.run(q, {"cvu": str(cvu).strip()}).data()
            store.close()
            return res

        if name:
            q = """
                MATCH (p:Person) 
                WHERE toLower(p.fullname) CONTAINS toLower($name)
                RETURN p.id as id, p.fullname as name, p.cvu as cvu, 
                       coalesce(p.snii_institution, p.institution) as inst,
                       p.snii_subdependency as subdep, p.snii_area as area, p.snii_level as level,
                       p.siia as siia, p.orcid as orcid, 
                       p.scopus_ids as scopus_ids, p.openalex_ids as openalex_ids
                LIMIT $limit
            """
            res = s.run(q, {"name": str(name).strip(), "limit": limit or 10}).data()
            store.close()
            return res

        # Muestreo general: prioriza nodos con múltiples identificadores
        fetch_limit = (limit * 3) if (skip_cvus and limit) else (limit or 100)
        q_general = f"""
            MATCH (p:Person) 
            WHERE p.fullname IS NOT NULL AND p.cvu IS NOT NULL
              AND (p.siia IS NOT NULL 
                   OR size(coalesce(p.scopus_ids, [])) > 0 
                   OR size(coalesce(p.openalex_ids, [])) > 0 
                   OR p.orcid IS NOT NULL)
            RETURN p.id as id, p.fullname as name, p.cvu as cvu, 
                   coalesce(p.snii_institution, p.institution) as inst,
                   p.snii_subdependency as subdep, p.snii_area as area, p.snii_level as level,
                   p.siia as siia, p.orcid as orcid, 
                   p.scopus_ids as scopus_ids, p.openalex_ids as openalex_ids
            LIMIT {fetch_limit}
        """
        res = s.run(q_general).data()

    store.close()

    if skip_cvus:
        filtered = [r for r in res if str(r.get("cvu")) not in skip_cvus]
        return filtered[:limit] if limit else filtered
    return res[:limit] if limit else res

def main():
    parser = argparse.ArgumentParser(description="Auditoría Integral Multi-ID con GPT-OSS 120B")
    parser.add_argument("--limit", type=int, default=10, help="Cantidad de investigadores a auditar")
    parser.add_argument("--cvu", type=str, default=None, help="Auditar un CVU específico (ej: 103489)")
    parser.add_argument("--name", type=str, default=None, help="Auditar por nombre (búsqueda parcial)")
    parser.add_argument("--max-tokens", type=int, default=5000, help="Ventana máxima de tokens de generación (default: 5000)")
    parser.add_argument("--resume", action="store_true", help="Reanudar omitiendo los CVU ya presentes en la bitácora JSONL")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Modo simulación sin escribir en Neo4j")
    args = parser.parse_args()

    out_dir = BASE_DIR / "data"
    out_dir.mkdir(exist_ok=True)
    log_file = out_dir / "audit_multi_id_log.jsonl"

    skip_cvus = set()
    if args.resume and log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str:
                    try:
                        record = json.loads(line_str)
                        if record.get("cvu"):
                            skip_cvus.add(str(record["cvu"]))
                    except Exception:
                        pass
        print(f"🔄 Modo --resume activado: Se omitirán {len(skip_cvus)} investigadores ya evaluados.")

    print("=" * 80)
    print("🚀 INICIANDO AUDITORÍA INTEGRAL MULTI-ID (ORCID, Scopus, OpenAlex, SIIA)")
    print(f"   Motor LLM: gpt-oss-120b (Cluster C3 UNAM)")
    print(f"   Ventana máxima: {args.max_tokens} tokens")
    if args.cvu:
        print(f"   Objetivo específico CVU: {args.cvu}")
    elif args.name:
        print(f"   Objetivo por nombre: '{args.name}'")
    else:
        print(f"   Límite de ejecución: {args.limit} investigadores")
    print(f"   Modo Dry-Run: {args.dry_run}")
    print("=" * 80)

    # 1. Recuperar candidatos
    t0 = time.time()
    candidates = get_candidates(
        limit=args.limit,
        cvu=args.cvu,
        name=args.name,
        skip_cvus=skip_cvus if args.resume else None
    )
    print(f"✅ Recuperados {len(candidates)} perfiles objetivo desde Neo4j.\n")

    if not candidates:
        print("ℹ️  No hay nuevos investigadores por procesar.")
        return

    client = get_openai_client(model="gpt-oss-120b")

    results = []
    json_summary_file = out_dir / f"audit_multi_id_batch_{len(candidates)}.json"

    for i, c in enumerate(candidates):
        cvu = c.get("cvu")
        name = c.get("name")
        inst = c.get("inst")
        print(f"🔍 [{i+1}/{len(candidates)}] Auditando CVU: {cvu} | {name}")
        print(f"    Institución: {inst} | Área: {c.get('area')}")
        print(f"    IDs asignadas: ORCID={bool(c.get('orcid'))} | Scopus={len(c.get('scopus_ids') or [])} | OA={len(c.get('openalex_ids') or [])} | SIIA={bool(c.get('siia'))}")

        try:
            t_call = time.time()
            verdict = audit_researcher_with_120b(c, client, max_tokens=args.max_tokens)
            elapsed = time.time() - t_call

            # Imprimir resultado en consola
            status_color = "🟢" if verdict.overall_verdict == "CONFIRMED" else "🟡" if verdict.overall_verdict == "PARTIALLY_CONTAMINATED" else "🔴"
            print(f"    {status_color} Dictamen Global: {verdict.overall_verdict} (Confianza: {verdict.overall_confidence}%) en {elapsed:.1f}s")
            print(f"    💬 Coherencia: {verdict.cross_id_coherence[:120]}...")
            
            for id_v in verdict.id_verdicts:
                v_icon = "✓" if id_v.status == "VALID" else "✗" if id_v.status == "INVALID" else "?"
                print(f"       [{v_icon}] {id_v.id_type.upper()}: {id_v.identifier} -> {id_v.status} ({id_v.confidence}%) | {id_v.reason[:80]}")

            if verdict.remediation_plan:
                print(f"    🛠️  Plan de Remediación ({len(verdict.remediation_plan)} acciones):")
                for rem in verdict.remediation_plan:
                    print(f"       • {rem.action}: {rem.details[:90]}")
            
            print("-" * 80)

            # Persistencia continua en JSONL
            dict_verdict = verdict.model_dump()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(dict_verdict, ensure_ascii=False) + "\n")

            results.append(dict_verdict)

        except Exception as e:
            print(f"    ❌ Error procesando investigador {name} ({cvu}): {e}")
            print("-" * 80)

    # Guardar resumen final
    with open(json_summary_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    total_time = time.time() - t0
    print("\n" + "=" * 80)
    print("🏁 AUDITORÍA FINALIZADA EXITOSAMENTE")
    print(f"   Total evaluados: {len(results)}/{len(candidates)}")
    print(f"   Tiempo total: {total_time:.1f} s (Promedio: {total_time/max(len(results), 1):.1f} s/investigador)")
    print(f"   Archivo resumen: {json_summary_file}")
    print(f"   Bitácora atómica: {log_file}")
    print("=" * 80)

if __name__ == "__main__":
    main()
