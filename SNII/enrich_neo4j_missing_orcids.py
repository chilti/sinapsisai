#!/usr/bin/env python3
"""
enrich_neo4j_missing_orcids.py

Motor de enriquecimiento y resolución masiva de ORCIDs faltantes en el
Grafo de Conocimiento Neo4j (UNAM / SNII).

Capacidades:
1. Extrae directamente desde Neo4j los nodos (:Person) que carecen de ORCID,
   junto con sus relaciones contextuales (:Institution, :Dependency, :KnowledgeArea).
2. Cascada de búsqueda de candidatos:
   - Fase 1: Caché histórico local (data/snii_llm_verified_matches.json)
   - Fase 2: Dump local de ORCID en ClickHouse (orcid.orcid_records, puerto 8123)
   - Fase 3: ClickHouse OpenAlex (rag.authors_seed_mexico, puerto 8124)
   - Fase 4: Fallback Web (ORCID Public API expanded-search + DuckDuckGo)
3. Reranking y verificación con LLM local (LM Studio / C3 Kimi) con esquema JSON
   sin bucles de tokens (mapeo directo en memoria).
4. Escritura y persistencia dual:
   - Actualización directa en Neo4j vía Cypher (p.orcids, p.orcid, p.orcid_source, etc.)
   - Sincronización en data/snii_llm_verified_matches.json
5. Checkpointing y tolerancia a fallos con soporte para --dry-run, --target, --limit y --resume.
"""

import os
import sys
import json
import time
import signal
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional

from neo4j import GraphDatabase
from dotenv import load_dotenv

# Configurar paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(BASE_DIR)
env_path = os.path.join(BASE_DIR, '.env')
load_dotenv(env_path)

from SNII.resolve_snii_2026_identities import (
    normalize_text,
    get_accent_insensitive_regex,
    calc_cand_score,
    search_web_orcid_candidates,
    call_llm_evaluator,
    get_orcid_client,
    get_ch_client,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASS
)

SPANISH_PARTICLES = {'de', 'del', 'la', 'las', 'los', 'san', 'santa', 'y', 'e', 'van', 'von', 'da', 'di'}

def get_search_keys(name: str):
    """Extrae combinaciones de apellidos y nombres para búsqueda exhaustiva en ClickHouse ignorando partículas nobiliarias."""
    raw_clean = normalize_text(name).replace('‐', ' ').replace('-', ' ')
    parts = [p for p in raw_clean.replace(',', ' ').split() if p not in SPANISH_PARTICLES and len(p) >= 2]
    if not parts:
        parts = [p for p in raw_clean.replace(',', ' ').split() if p]

    if ',' in raw_clean:
        ap_part = raw_clean.split(',')[0]
        nom_part = raw_clean.split(',')[1]
        apellidos = [p for p in ap_part.split() if p not in SPANISH_PARTICLES and len(p) >= 2]
        if not apellidos:
            apellidos = [p for p in ap_part.split() if p]
        nombres = [p for p in nom_part.split() if p not in SPANISH_PARTICLES and len(p) >= 2]
        if not nombres:
            nombres = [p for p in nom_part.split() if p]
    else:
        apellidos = parts[:1]
        nombres = parts[1:]

    paterno = apellidos[0] if apellidos else (parts[0] if parts else 'desconocido')
    materno = apellidos[1] if len(apellidos) > 1 else None
    nombre1 = nombres[0] if nombres else (parts[-1] if parts else 'desconocido')

    pairs = [(paterno, nombre1)]
    if materno:
        pairs.append((materno, nombre1))
        pairs.append((paterno, materno))
    elif len(nombres) > 1:
        pairs.append((paterno, nombres[1]))

    all_keys = list(set([p for p in raw_clean.replace(',', ' ').split() if p not in SPANISH_PARTICLES and len(p) >= 2]))
    if not all_keys:
        all_keys = [paterno, nombre1]
    return paterno, nombre1, pairs, all_keys

DATA_DIR = os.path.join(BASE_DIR, "data")
SNII_DATA_DIR = os.path.join(DATA_DIR, "snii")
os.makedirs(SNII_DATA_DIR, exist_ok=True)

PROGRESS_FILE = os.path.join(SNII_DATA_DIR, "neo4j_orcid_enrichment_progress.json")
LOG_FILE = os.path.join(SNII_DATA_DIR, "neo4j_orcid_enrichment.log")
MASTER_MATCHES_FILE = os.path.join(DATA_DIR, "snii_llm_verified_matches.json")
EXCEL_2026_FILE = os.path.join(SNII_DATA_DIR, "Investigadores_vigentes_2026.xlsx")

SHUTDOWN_REQUESTED = False

def sigint_handler(sig, frame):
    global SHUTDOWN_REQUESTED
    print("\n⚠️ Señal de interrupción recibida. Guardando checkpoint y saliendo de forma segura...", flush=True)
    SHUTDOWN_REQUESTED = True

signal.signal(signal.SIGINT, sigint_handler)
signal.signal(signal.SIGTERM, sigint_handler)


def log(msg: str):
    """Escribe en consola y en el archivo de log con timestamp."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_neo4j_driver():
    """Crea y retorna una instancia del driver de Neo4j."""
    uri = NEO4J_URI or "bolt://127.0.0.1:7687"
    user = NEO4J_USER or "neo4j"
    pwd = NEO4J_PASS or "password123"
    return GraphDatabase.driver(uri, auth=(user, pwd))


def fetch_target_persons(driver, target: str = "unam", limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Extrae los investigadores objetivo desde Neo4j que no tienen ORCID.
    """
    log(f"📡 Consultando personas sin ORCID en Neo4j con target='{target}'...")

    where_extra = ""
    if target == "unam":
        where_extra = "AND inst_name =~ '(?i).*(UNAM|NACIONAL AUTONOMA DE MEXICO).*'"
    elif target == "snii_2026":
        if os.path.exists(EXCEL_2026_FILE):
            import pandas as pd
            df_2026 = pd.read_excel(EXCEL_2026_FILE)
            cvus_2026 = [str(c) for c in df_2026['CVU'].dropna().unique()]
            where_extra = f"AND p.id IN {cvus_2026}"
        else:
            where_extra = "AND p.is_snii = true"
    elif target == "snii_all":
        where_extra = "AND p.is_snii = true"
    elif target == "all":
        where_extra = ""

    limit_clause = f"LIMIT {limit}" if limit else ""

    cypher = f"""
    MATCH (p:Person)
    WHERE (p.orcids IS NULL OR size(p.orcids) = 0) AND (p.orcid IS NULL OR p.orcid = '')
    OPTIONAL MATCH (p)-[:AFFILIATED_TO]->(inst:Institution)
    OPTIONAL MATCH (p)-[:AFFILIATED_TO]->(dep:Dependency)
    OPTIONAL MATCH (p)-[:SPECIALIZED_IN]->(ka:KnowledgeArea)
    WITH p,
         collect(DISTINCT inst.name)[0] as inst_name,
         collect(DISTINCT dep.name)[0] as dep_name,
         collect(DISTINCT ka.name)[0] as ka_name
    WHERE 1=1 {where_extra}
    RETURN p.id as id,
           p.fullname as fullname,
           p.is_snii as is_snii,
           p.openalex_ids as openalex_ids,
           inst_name as institution,
           dep_name as dependency,
           ka_name as area
    {limit_clause}
    """

    with driver.session() as s:
        results = s.run(cypher).data()

    log(f"✅ Recuperados {len(results)} investigadores sin ORCID desde Neo4j.")
    return results


def load_master_matches() -> Dict[str, Dict[str, Any]]:
    """Carga el archivo histórico snii_llm_verified_matches.json indizado por CVU/ID."""
    if not os.path.exists(MASTER_MATCHES_FILE):
        return {}
    try:
        with open(MASTER_MATCHES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        by_cvu = {}
        if isinstance(data, list):
            for item in data:
                cvu = str(item.get("snii_cvu") or item.get("id") or "")
                if cvu:
                    by_cvu[cvu] = item
        elif isinstance(data, dict):
            by_cvu = data
        return by_cvu
    except Exception as e:
        log(f"⚠️ Error cargando master matches: {e}")
        return {}


def load_progress() -> Dict[str, Any]:
    """Carga el estado de progreso guardado."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "processed_ids": {},
        "stats": {
            "total": 0,
            "resolved": 0,
            "auto_history": 0,
            "auto_orcid_local": 0,
            "auto_openalex": 0,
            "llm_local": 0,
            "web_llm": 0,
            "unmatched": 0
        }
    }


def save_progress(progress_data: Dict[str, Any]):
    """Guarda atómicamente el estado de progreso."""
    tmp_path = PROGRESS_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(progress_data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, PROGRESS_FILE)
    except Exception as e:
        log(f"⚠️ Error guardando checkpoint de progreso: {e}")


def update_neo4j_nodes_batch(driver, updates: List[Dict[str, Any]]):
    """
    Escribe en lote las resoluciones verificadas en Neo4j.
    """
    if not updates:
        return

    cypher = """
    UNWIND $updates as u
    MATCH (p:Person {id: u.id})
    SET p.orcids = CASE WHEN u.orcid IS NOT NULL THEN [u.orcid] ELSE p.orcids END,
        p.orcid = CASE WHEN u.orcid IS NOT NULL THEN u.orcid ELSE p.orcid END,
        p.openalex_id = CASE WHEN u.openalex_id IS NOT NULL THEN u.openalex_id ELSE p.openalex_id END,
        p.orcid_source = u.source,
        p.orcid_confidence = u.confidence,
        p.orcid_verified = u.match,
        p.orcid_updated_at = datetime()
    """

    with driver.session() as s:
        s.run(cypher, updates=updates)


def append_to_master_matches(new_matches: List[Dict[str, Any]]):
    """Agrega o actualiza los matches verificados en data/snii_llm_verified_matches.json."""
    if not new_matches:
        return
    try:
        matches_list = []
        if os.path.exists(MASTER_MATCHES_FILE):
            with open(MASTER_MATCHES_FILE, "r", encoding="utf-8") as f:
                matches_list = json.load(f)

        existing_cvus = {str(m.get("snii_cvu")): idx for idx, m in enumerate(matches_list)}
        for nm in new_matches:
            cvu_str = str(nm.get("snii_cvu"))
            if cvu_str in existing_cvus:
                matches_list[existing_cvus[cvu_str]] = nm
            else:
                matches_list.append(nm)
                existing_cvus[cvu_str] = len(matches_list) - 1

        tmp_path = MASTER_MATCHES_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(matches_list, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, MASTER_MATCHES_FILE)
    except Exception as e:
        log(f"⚠️ Error actualizando master matches file: {e}")


def search_orcid_records_for_person(ch, pname: str, limit: int = 4) -> List[Dict[str, Any]]:
    """Busca candidatos en ClickHouse Local (orcid.orcid_records) por persona individual evitando inanición."""
    if not pname:
        return []
    k1, k2, pairs, all_keys = get_search_keys(pname)
    subclauses = []
    for p1, p2 in pairs:
        r1 = get_accent_insensitive_regex(p1.replace("'", "''"))
        r2 = get_accent_insensitive_regex(p2.replace("'", "''"))
        subclauses.append(f"((match(family_name, '{r1}') AND match(given_names, '{r2}')) OR (match(credit_name, '{r1}') AND match(credit_name, '{r2}')))")
    where_sub = " OR ".join(subclauses)
    pre = f"multiSearchAnyCaseInsensitive(family_name, {[k1.lower()]}) OR multiSearchAnyCaseInsensitive(credit_name, {[k1.lower()]})"
    q = f"""
    SELECT orcid, given_names, family_name, credit_name, last_affiliation, last_affiliation_country
    FROM orcid.orcid_records
    WHERE ({pre}) AND ({where_sub})
    LIMIT {limit * 3}
    """
    try:
        rows = ch.query(q).result_rows
    except Exception as e:
        return []

    cands = []
    for row in rows:
        orcid, g_names, f_name, cred_name, aff, aff_country = row
        cand_name = cred_name if cred_name else f"{g_names} {f_name}".strip()
        score = calc_cand_score(pname, cand_name)
        if score >= 0.70 and orcid:
            aff_full = f"{aff or ''} {f'({aff_country})' if aff_country else ''}".strip()
            cands.append({
                "source": "ORCID Local DB",
                "openalex_id": None,
                "name": cand_name,
                "orcid": orcid,
                "inst": aff_full,
                "affiliation": aff_full,
                "scopus_ids": [],
                "score": score,
                "topics": [],
                "works_count": 0,
                "cited_by_count": 0,
                "alt_names": []
            })
    cands.sort(key=lambda x: x["score"], reverse=True)
    return cands[:limit]


def search_openalex_candidates_for_person(ch, pname: str, limit: int = 6) -> List[Dict[str, Any]]:
    """Busca candidatos en ClickHouse (rag.authors_seed_mexico) por persona individual evitando inanición."""
    if not pname:
        return []
    k1, k2, pairs, all_keys = get_search_keys(pname)
    subclauses = []
    for p1, p2 in pairs:
        r1 = get_accent_insensitive_regex(p1.replace("'", "''"))
        r2 = get_accent_insensitive_regex(p2.replace("'", "''"))
        subclauses.append(f"(match(display_name, '{r1}') AND match(display_name, '{r2}'))")
    where_sub = " OR ".join(subclauses)
    pre = f"multiSearchAnyCaseInsensitive(display_name, {[k1.lower()]})"
    q = f"""
    SELECT id, display_name, orcid, ids, raw_data
    FROM rag.authors_seed_mexico
    WHERE ({pre}) AND ({where_sub})
    LIMIT {limit * 3}
    """
    try:
        rows = ch.query(q).result_rows
    except Exception as e:
        return []

    cands = []
    seen_ids = set()
    for r in rows:
        openalex_id, disp_name, orcid_val, ids_json, raw_data_str = r[0], r[1], r[2], r[3], r[4]
        if openalex_id in seen_ids:
            continue
        seen_ids.add(openalex_id)
        score = calc_cand_score(pname, str(disp_name))
        if score >= 0.70:
            inst_name = ""
            topics_list = []
            works_count = 0
            cited_by_count = 0
            alt_names = []
            try:
                if raw_data_str:
                    raw_data = json.loads(raw_data_str) if isinstance(raw_data_str, str) else raw_data_str
                    inst_name = raw_data.get('last_known_institution_name') or (raw_data.get('last_known_institution') or {}).get('display_name') or ""
                    topics_list = [t.get('display_name') for t in (raw_data.get('topics') or [])[:3]]
                    works_count = raw_data.get('works_count', 0)
                    cited_by_count = raw_data.get('cited_by_count', 0)
                    alt_names = (raw_data.get('display_name_alternatives') or [])[:3]
            except:
                pass

            scopus_ids = []
            try:
                ids_data = json.loads(ids_json) if isinstance(ids_json, str) else (ids_json or {})
                scopus_raw = ids_data.get('scopus') or []
                scopus_ids = [scopus_raw] if isinstance(scopus_raw, str) else scopus_raw
            except:
                pass

            cands.append({
                "source": "OpenAlex DB Local",
                "openalex_id": openalex_id,
                "name": disp_name,
                "orcid": orcid_val or None,
                "inst": inst_name,
                "affiliation": inst_name,
                "scopus_ids": scopus_ids,
                "score": score,
                "topics": topics_list,
                "works_count": works_count,
                "cited_by_count": cited_by_count,
                "alt_names": alt_names
            })
    cands.sort(key=lambda x: x["score"], reverse=True)
    return cands[:limit]


def run_enrichment(target: str = "unam", limit: Optional[int] = None, batch_size: int = 20, dry_run: bool = False, resume: bool = True):
    global SHUTDOWN_REQUESTED

    log("=" * 70)
    log(f"🚀 INICIANDO ENRIQUECIMIENTO DE ORCIDS EN NEO4J")
    log(f"   • Target: {target}")
    log(f"   • Límite: {limit or 'Sin límite'}")
    log(f"   • Tamaño de Lote: {batch_size}")
    log(f"   • Modo Dry-Run: {dry_run}")
    log("=" * 70)

    driver = get_neo4j_driver()
    ch_orcid = get_orcid_client()
    ch_oa = get_ch_client()
    master_matches = load_master_matches()
    DEFAULT_STATS = {
        "total": 0, "resolved": 0, "auto_history": 0, "auto_orcid_local": 0,
        "auto_openalex": 0, "llm_local": 0, "web_llm": 0, "unmatched": 0
    }
    progress = load_progress() if resume else {"processed_ids": {}, "stats": DEFAULT_STATS}
    processed_ids = progress.get("processed_ids", {})
    stats = {**DEFAULT_STATS, **progress.get("stats", {})}

    # 1. Extraer personas desde Neo4j
    all_persons = fetch_target_persons(driver, target=target, limit=limit)
    if not all_persons:
        log("✅ No se encontraron personas pendientes para procesar.")
        driver.close()
        return

    # Filtrar las ya procesadas si estamos en modo resume
    if resume and processed_ids:
        pending_persons = [p for p in all_persons if p['id'] not in processed_ids]
        log(f"ℹ️ Modo Resume: {len(processed_ids)} ya procesadas en checkpoints previos. Restantes: {len(pending_persons)}.")
    else:
        pending_persons = all_persons

    total_pending = len(pending_persons)
    start_time = time.time()
    updates_for_neo4j = []
    updates_for_master_json = []

    # Procesar por lotes
    for i in range(0, total_pending, batch_size):
        if SHUTDOWN_REQUESTED:
            break

        chunk = pending_persons[i : i + batch_size]
        batch_idx = i // batch_size + 1
        total_batches = (total_pending + batch_size - 1) // batch_size
        log(f"\n--- 📦 Lote [{batch_idx}/{total_batches}] ({len(chunk)} investigadores) ---")

        # Evaluar cada investigador del lote
        for p in chunk:
            if SHUTDOWN_REQUESTED:
                break

            pid = str(p['id'])
            pname = p.get('fullname', '')
            snii_inst = p.get('institution') or 'SIN INFORMACION'
            snii_dep = p.get('dependency') or 'SIN INFORMACION'
            snii_area = p.get('area') or 'SIN INFORMACION'
            stats["total"] += 1

            matched_record = None
            resolution_type = None

            # --- Paso 1: Checar histórico previo ---
            if pid in master_matches and master_matches[pid].get("matched_orcid"):
                m_hist = master_matches[pid]
                matched_record = {
                    "id": pid,
                    "match": True,
                    "orcid": m_hist.get("matched_orcid"),
                    "author": m_hist.get("matched_author") or pname,
                    "openalex_id": m_hist.get("matched_openalex_id"),
                    "source": "Histórico Verificado",
                    "confidence": "HIGH",
                    "reason": "Propagado desde historial cienciométrico verificado previo."
                }
                resolution_type = "auto_history"

            # --- Paso 2: Búsqueda Local en ClickHouse (ORCID y OpenAlex) ---
            local_orcid_cands = []
            oa_cands = []
            if not matched_record:
                local_orcid_cands = search_orcid_records_for_person(ch_orcid, pname, limit=4)
                oa_cands = search_openalex_candidates_for_person(ch_oa, pname, limit=6)

            # 2a. Auto-Match ORCID Local
            if not matched_record and local_orcid_cands:
                best_loc = local_orcid_cands[0]
                if best_loc.get("score", 0) >= 0.98 and best_loc.get("orcid"):
                    cand_inst = best_loc.get("affiliation", "").lower()
                    inst_tokens = [t for t in normalize_text(snii_inst).split() if len(t) > 3]
                    if any(t in cand_inst for t in inst_tokens) or "sin institucion" in snii_inst.lower():
                        matched_record = {
                            "id": pid,
                            "match": True,
                            "orcid": best_loc["orcid"],
                            "author": best_loc["name"],
                            "openalex_id": None,
                            "source": "ORCID Local DB (Auto-High)",
                            "confidence": "AUTO_HIGH",
                            "reason": f"Nombre con similitud {best_loc['score']:.3f} y afiliación coincidente con {best_loc['affiliation']}."
                        }
                        resolution_type = "auto_orcid_local"

            # 2b. Auto-Match OpenAlex (si tiene ORCID)
            if not matched_record and oa_cands:
                best_oa = oa_cands[0]
                if best_oa.get("score", 0) >= 0.98 and best_oa.get("orcid"):
                    cand_inst = best_oa.get("inst", "").lower()
                    inst_tokens = [t for t in normalize_text(snii_inst).split() if len(t) > 3]
                    if any(t in cand_inst for t in inst_tokens) or "sin institucion" in snii_inst.lower():
                        clean_orcid = best_oa["orcid"].replace("https://orcid.org/", "").strip()
                        matched_record = {
                            "id": pid,
                            "match": True,
                            "orcid": clean_orcid,
                            "author": best_oa["name"],
                            "openalex_id": best_oa.get("openalex_id"),
                            "source": "OpenAlex DB Local (Auto-High)",
                            "confidence": "AUTO_HIGH",
                            "reason": f"Nombre con similitud {best_oa['score']:.3f} y afiliación coincidente con {best_oa['inst']}."
                        }
                        resolution_type = "auto_openalex"

            # --- Paso 3: Reranking y Verificación con LLM Local ---
            if not matched_record:
                # Priorizar candidatos que tengan ORCID
                cands_with_orcid = [c for c in (local_orcid_cands + oa_cands) if c.get("orcid")]
                cands_without_orcid = [c for c in oa_cands if not c.get("orcid")]
                pool_cands = (cands_with_orcid + cands_without_orcid)[:6]

                if pool_cands:
                    snii_eval_dict = {
                        "nombre": pname,
                        "institucion": snii_inst,
                        "dependencia": snii_dep,
                        "subdependencia": "SIN INFORMACION",
                        "area": snii_area
                    }
                    is_match, win_cand, reason_str, conf = call_llm_evaluator(snii_eval_dict, pool_cands, is_web=False)
                    if is_match and win_cand and win_cand.get("orcid"):
                        raw_orc = win_cand["orcid"].replace("https://orcid.org/", "").strip()
                        matched_record = {
                            "id": pid,
                            "match": True,
                            "orcid": raw_orc,
                            "author": win_cand["name"],
                            "openalex_id": win_cand.get("openalex_id"),
                            "source": f"LLM Local ({win_cand.get('source')})",
                            "confidence": conf or "HIGH",
                            "reason": reason_str
                        }
                        resolution_type = "llm_local"

            # --- Paso 4: Fallback Web (ORCID Expanded API + DuckDuckGo) ---
            if not matched_record:
                web_cands = search_web_orcid_candidates(pname, snii_inst, snii_dep, "")
                if web_cands:
                    snii_eval_dict = {
                        "nombre": pname,
                        "institucion": snii_inst,
                        "dependencia": snii_dep,
                        "subdependencia": "SIN INFORMACION",
                        "area": snii_area
                    }
                    is_match, win_cand, reason_str, conf = call_llm_evaluator(snii_eval_dict, web_cands, is_web=True)
                    if is_match and win_cand and win_cand.get("orcid"):
                        raw_orc = win_cand["orcid"].replace("https://orcid.org/", "").strip()
                        matched_record = {
                            "id": pid,
                            "match": True,
                            "orcid": raw_orc,
                            "author": win_cand["name"],
                            "openalex_id": None,
                            "source": f"Web Search + LLM ({win_cand.get('source')})",
                            "confidence": conf or "HIGH_WEB_VERIFIED",
                            "reason": reason_str
                        }
                        resolution_type = "web_llm"

            # --- Paso 5: Registro y persistencia ---
            if matched_record and matched_record.get("orcid"):
                stats["resolved"] += 1
                stats[resolution_type] += 1
                log(f"   ✅ [ID {pid}] {pname} -> ORCID: {matched_record['orcid']} [{matched_record['source']}]")
                processed_ids[pid] = matched_record
                updates_for_neo4j.append(matched_record)

                # Preparar para el archivo maestro JSON
                updates_for_master_json.append({
                    "snii_author": pname,
                    "snii_institution": snii_inst,
                    "snii_dependency": snii_dep,
                    "snii_subdependency": "SIN INFORMACIÓN",
                    "snii_entidad_final": "MÉXICO",
                    "snii_cvu": str(pid),
                    "match": True,
                    "matched_author": matched_record["author"],
                    "matched_author_ids": None,
                    "matched_orcid": f"https://orcid.org/{matched_record['orcid']}" if not matched_record['orcid'].startswith("http") else matched_record['orcid'],
                    "matched_openalex_id": matched_record.get("openalex_id"),
                    "scopus_ids": [],
                    "openalex_ids": [matched_record["openalex_id"]] if matched_record.get("openalex_id") else [],
                    "source": matched_record["source"],
                    "confidence": matched_record["confidence"],
                    "reason": matched_record["reason"],
                    "discarded_candidates": []
                })
            else:
                stats["unmatched"] += 1
                log(f"   ❌ [ID {pid}] {pname} -> Sin match confirmado.")
                processed_ids[pid] = {
                    "id": pid,
                    "match": False,
                    "orcid": None,
                    "source": "Sin match",
                    "confidence": "NONE",
                    "reason": "Candidatos locales y web no coinciden con la afiliación del investigador."
                }

        # Guardar en Neo4j al final de cada lote (si no es dry-run)
        if updates_for_neo4j and not dry_run:
            update_neo4j_nodes_batch(driver, updates_for_neo4j)
            log(f"   💾 Actualizados {len(updates_for_neo4j)} nodos en Neo4j.")
            updates_for_neo4j = []

        if updates_for_master_json and not dry_run:
            append_to_master_matches(updates_for_master_json)
            updates_for_master_json = []

        # Guardar checkpoint de progreso
        progress["processed_ids"] = processed_ids
        progress["stats"] = stats
        save_progress(progress)

        elapsed = (time.time() - start_time) / 60.0
        log(f"   📊 Progreso: [{min(i + batch_size, total_pending)}/{total_pending}] | "
            f"Resueltos: {stats['resolved']} | Sin match: {stats['unmatched']} | T: {elapsed:.1f}m")

    # Flush final
    if updates_for_neo4j and not dry_run:
        update_neo4j_nodes_batch(driver, updates_for_neo4j)
    if updates_for_master_json and not dry_run:
        append_to_master_matches(updates_for_master_json)

    driver.close()

    elapsed_total = (time.time() - start_time) / 60.0
    log("=" * 70)
    log("🏁 PROCESAMIENTO CONCLUIDO")
    log(f"   • Total evaluados en esta sesión: {stats['total']}")
    log(f"   • Total con ORCID asignado: {stats['resolved']} ({(stats['resolved']/max(stats['total'],1))*100:.1f}%)")
    log(f"   • Auto-Match Histórico: {stats['auto_history']}")
    log(f"   • Auto-Match ORCID Local: {stats['auto_orcid_local']}")
    log(f"   • Auto-Match OpenAlex Local: {stats['auto_openalex']}")
    log(f"   • Resueltos con LLM Local: {stats['llm_local']}")
    log(f"   • Resueltos vía Web + LLM: {stats['web_llm']}")
    log(f"   • Sin match confirmado: {stats['unmatched']}")
    log(f"   • Tiempo total: {elapsed_total:.2f} minutos")
    log("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Enriquecimiento de ORCIDs faltantes en Neo4j")
    parser.add_argument("--target", choices=["unam", "snii_2026", "snii_all", "all"], default="unam",
                        help="Conjunto de personas a procesar desde Neo4j (default: unam)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Límite máximo de personas a procesar en esta ejecución")
    parser.add_argument("--batch-size", type=int, default=20,
                        help="Tamaño de lote para consultas y persistencia (default: 20)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Ejecutar en modo de prueba sin escribir cambios en Neo4j")
    parser.add_argument("--resume", action="store_true", default=True,
                        help="Reanudar desde el checkpoint de checkpoints previos (activo por defecto)")
    parser.add_argument("--no-resume", action="store_true",
                        help="No reanudar desde el checkpoint y reiniciar")

    args = parser.parse_args()

    run_enrichment(
        target=args.target,
        limit=args.limit,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        resume=not args.no_resume
    )


if __name__ == "__main__":
    main()
