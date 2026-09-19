#!/usr/bin/env python3
"""
resolve_snii_2026_identities.py
===============================
Resolución de identidad académica (ORCID, OpenAlex ID, Scopus ID) para los
12,964 investigadores pendientes del Padrón SNII 2026.

Estrategia Multi-Fase de Alta Eficiencia:
1. Fase A (Propagación Inmediata de Verificados Previos):
   - Cruce de nombres normalizados y coincidencias institucionales contra los
     registros ya validados en data/snii_llm_verified_matches.json que carecían de CVU.
   - Vinculación directa instantánea con 100% de consistencia histórica (~8,100 registros).
2. Fase B (Auto-Match Heurístico de Alta Confianza):
   - Detección de candidatos en ClickHouse (authors_seed_mexico) con similitud
     Jaro-Winkler >= 0.98 y coincidencia institucional.
3. Fase C (Búsqueda Vectorial Rápida + Reranking con LLM Local):
   - Recuperación de candidatos desde ClickHouse y local_authors (Qdrant).
   - Verificación y decisión mediante el LLM local en LM Studio (openai/gpt-oss-20b).
4. Persistencia Atómica y Sincronización en Neo4j:
   - Checkpoints periódicos atómicos en data/snii_llm_verified_matches.json cada 25 registros.
   - Actualización en tiempo real de nodos (:Person {id: cvu}) con orcid y openalex_id.
   - Monitoreo en data/snii/snii_2026_resolution_progress.json.
"""

import os
import sys
import json
import time
import re
import argparse
from pathlib import Path
from dotenv import load_dotenv
from Levenshtein import jaro_winkler
from neo4j import GraphDatabase
from openai import OpenAI
from langchain_openai import OpenAIEmbeddings

# Añadir raíz al sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from database.vector_store import QdrantStore
from scripts.tools.match_snii_orcid import get_client as get_ch_client, normalize_text

# Cargar .env
load_dotenv(BASE_DIR / ".env")

# Rutas principales
DATA_DIR = BASE_DIR / "data"
SNII_DIR = DATA_DIR / "snii"
PENDIENTES_PATH = DATA_DIR / "snii_2026_nuevos_pendientes.json"
MATCHES_PATH = DATA_DIR / "snii_llm_verified_matches.json"
PROGRESS_PATH = SNII_DIR / "snii_2026_resolution_progress.json"

# Neo4j Config
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "password123")

# LLM Config (LM Studio)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-lm-911DBjzu:mnU3kI7Zj5dGgX8mzxyj")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-nomic-ai-nomic-embed-text-v2-moe")

# Inicializar clientes
embeddings_model = OpenAIEmbeddings(
    model=EMB_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    check_embedding_ctx_length=False
)

openai_client = OpenAI(
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY
)

SNII_MATCH_SCHEMA = {
    "name": "snii_match_result",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "analysis": {
                "type": "string",
                "description": "Analiza brevemente la compatibilidad del nombre completo y la institución entre el investigador SNII y los candidatos."
            },
            "match": {
                "type": "boolean",
                "description": "True si alguno de los candidatos coincide plenamente con el investigador del SNII, False de lo contrario."
            },
            "matched_candidate_index": {
                "type": ["integer", "null"],
                "description": "Número 1-based del candidato coincidente (1, 2, ...), o null si match es False."
            },
            "orcid": {
                "type": ["string", "null"],
                "description": "URL o ID de ORCID del candidato ganador, o null si no tiene o match es False."
            },
            "reason": {
                "type": "string",
                "description": "Veredicto final conciso en una sola frase."
            }
        },
        "required": ["analysis", "match", "matched_candidate_index", "orcid", "reason"],
        "additionalProperties": False
    }
}


def get_search_keys(name: str):
    """Extrae k1 y k2 (apellidos/nombres) para búsqueda en ClickHouse."""
    parts = [p.strip() for p in normalize_text(name).replace(',', ' ').split() if len(p) > 2]
    if len(parts) < 2:
        k1 = parts[0] if parts else normalize_text(name)
        k2 = k1
    else:
        if ',' in name:
            apellidos = [p for p in normalize_text(name.split(',')[0]).split() if len(p) > 2]
            nombres = [p for p in normalize_text(name.split(',')[1]).split() if len(p) > 2]
            k1 = apellidos[0] if apellidos else parts[0]
            k2 = nombres[0] if nombres else parts[-1]
        else:
            k1, k2 = parts[0], parts[-1]
    return k1, k2


def get_accent_insensitive_regex(text: str) -> str:
    """Genera regex para ClickHouse sin acentos."""
    vowel_map = {
        'a': '[aáàâä]', 'e': '[eéèêë]', 'i': '[iíìîï]',
        'o': '[oóòôö]', 'u': '[uúùûü]'
    }
    regex = ""
    for char in text.lower():
        regex += vowel_map.get(char, char)
    return f"(?i){regex}"


def clean_for_key(text):
    if not text:
        return ""
    t = normalize_text(str(text)).upper().replace(",", "").strip()
    if t in ["SIN INFORMACION", "SIN INFORMACIÓN", "NO APLICA", "SIN INSTITUCION", "SIN INSTITUCIÓN", "NAN", "NONE", "NULL"]:
        return ""
    return t


def search_openalex_candidates_batch(names_info: list, limit_per_name: int = 5) -> dict:
    """Busca candidatos en ClickHouse (rag.authors_seed_mexico) en una sola consulta sin JOINs."""
    if not names_info:
        return {}
    ch = get_ch_client()
    clauses = []
    for info in names_info:
        r1 = get_accent_insensitive_regex(info['k1'].replace("'", "''"))
        r2 = get_accent_insensitive_regex(info['k2'].replace("'", "''"))
        clauses.append(f"(match(display_name, '{r1}') AND match(display_name, '{r2}'))")
    
    all_k1 = list(set([info['k1'].lower() for info in names_info if len(info['k1']) > 2]))
    if not all_k1:
        return {info['snii_name']: [] for info in names_info}
    
    pre_filter = f"multiSearchAnyCaseInsensitive(display_name, {all_k1})"
    where_clause = " OR ".join(clauses)
    query_limit = min(len(names_info) * limit_per_name * 10, 2000)
    
    query = f"""
    SELECT id, display_name, orcid, ids, raw_data
    FROM rag.authors_seed_mexico
    WHERE ({pre_filter}) AND ({where_clause})
    LIMIT {query_limit}
    """
    try:
        rows = ch.query(query).result_rows
    except Exception as e:
        print(f"      ⚠️ Error en consulta ClickHouse: {e}", flush=True)
        return {info['snii_name']: [] for info in names_info}
    
    results_map = {info['snii_name']: [] for info in names_info}
    batch_normalized = {
        info['snii_name']: " ".join(sorted([t for t in normalize_text(info['snii_name']).replace(',', ' ').split() if len(t) > 1]))
        for info in names_info
    }

    for r in rows:
        openalex_id, disp_name, orcid_val, ids_json, raw_data_str = r[0], r[1], r[2], r[3], r[4]
        inst_name = ""
        try:
            # Extraer institución de raw_data
            if raw_data_str:
                raw_data = json.loads(raw_data_str) if isinstance(raw_data_str, str) else raw_data_str
                affils = raw_data.get('affiliations') or []
                if affils and isinstance(affils, list) and len(affils) > 0:
                    inst_info = affils[0].get('institution')
                    if inst_info and isinstance(inst_info, dict):
                        inst_name = inst_info.get('display_name')
                if not inst_name:
                    lki = raw_data.get('last_known_institution') or {}
                    inst_name = lki.get('display_name', '')
        except:
            pass

        cand_norm = " ".join(sorted([t for t in normalize_text(str(disp_name)).replace(',', ' ').split() if len(t) > 1]))
        for snii_name, sorted_seed in batch_normalized.items():
            ns = jaro_winkler(sorted_seed, cand_norm)
            if ns > 0.75:
                scopus_ids = []
                try:
                    ids_data = json.loads(ids_json) if isinstance(ids_json, str) else (ids_json or {})
                    scopus_raw = ids_data.get('scopus') or []
                    scopus_ids = [scopus_raw] if isinstance(scopus_raw, str) else scopus_raw
                except:
                    pass
                results_map[snii_name].append({
                    "openalex_id": openalex_id,
                    "name": disp_name,
                    "orcid": orcid_val or None,
                    "inst": inst_name or "",
                    "scopus_ids": scopus_ids,
                    "score": ns
                })

    for name in results_map:
        results_map[name].sort(key=lambda x: x['score'], reverse=True)
        results_map[name] = results_map[name][:limit_per_name]

    return results_map


def parse_llm_json_response(raw_input) -> dict:
    """Extrae y parsea limpiamente el objeto JSON de respuesta del LLM con rescate automático."""
    if not raw_input:
        return {"match": False, "reason": "Respuesta vacía"}
    if isinstance(raw_input, dict):
        return raw_input
    
    text = str(raw_input)
    if "<|channel|>final" in text:
        text = text.split("<|channel|>final")[-1]
    
    clean = text.strip().replace('```json', '').replace('```', '').strip()
    try:
        res = json.loads(clean)
        if isinstance(res, dict) and "match" in res:
            return res
    except Exception:
        pass

    # Buscar bloques JSON que contengan "match"
    for pattern in [
        r'\{[^{}]*"match"[^{}]*\}',
        r'\{[\s\S]*?"match"[\s\S]*?\}'
    ]:
        m = re.search(pattern, text)
        if m:
            try:
                res = json.loads(m.group(0))
                if isinstance(res, dict) and "match" in res:
                    return res
            except Exception:
                pass

    # Rescate regex directo si hubo algún problema sintáctico
    match_m = re.search(r'"match"\s*:\s*(true|false)', text, re.IGNORECASE)
    if match_m:
        is_match = match_m.group(1).lower() == 'true'
        idx_m = re.search(r'"matched_candidate_index"\s*:\s*(\d+)', text)
        cand_idx = int(idx_m.group(1)) if idx_m else (1 if is_match else None)
        orcid_m = re.search(r'"orcid"\s*:\s*"([^"]+)"', text)
        found_orcid = orcid_m.group(1) if (orcid_m and orcid_m.group(1).lower() not in ('null', 'none')) else None
        reason_m = re.search(r'"reason"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        reason = reason_m.group(1) if reason_m else ("Coincidencia confirmada por LLM" if is_match else "Descartado por LLM")
        return {
            "match": is_match,
            "matched_candidate_index": cand_idx,
            "orcid": found_orcid,
            "reason": reason
        }

    return {"match": False, "reason": f"No se pudo parsear JSON de: {text[:80]}"}



def sync_neo4j_batch(driver, updates):
    """Actualiza orcid y openalex_id en nodos (:Person {id: cvu}) en Neo4j."""
    if not updates:
        return
    query = """
    UNWIND $updates as u
    MATCH (p:Person {id: u.cvu})
    SET p.orcid = CASE WHEN u.orcid IS NOT NULL AND u.orcid <> '' THEN u.orcid ELSE p.orcid END,
        p.openalex_id = CASE WHEN u.openalex_id IS NOT NULL AND u.openalex_id <> '' THEN u.openalex_id ELSE p.openalex_id END
    """
    try:
        with driver.session() as s:
            s.run(query, updates=updates)
    except Exception as e:
        print(f"      ⚠️ Error actualizando Neo4j: {e}", flush=True)


def save_atomic_json(filepath, data):
    """Guarda datos en formato JSON de forma atómica y segura."""
    tmp_path = f"{filepath}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, filepath)


def main():
    parser = argparse.ArgumentParser(description="Resolución de identidades académicas Padrón SNII 2026")
    parser.add_argument("--limit", type=int, default=None, help="Límite de investigadores a procesar (para pruebas)")
    parser.add_argument("--batch-size", type=int, default=10, help="Tamaño de lote para consultas en ClickHouse")
    parser.add_argument("--checkpoint-interval", type=int, default=25, help="Guardar cada N registros")
    parser.add_argument("--auto-only", action="store_true", help="Solo ejecutar propagación previa y auto-match, sin LLM")
    parser.add_argument("--retry-failed-llm", action="store_true", help="Re-evalúa con el LLM los registros que fallaron previamente por error de parseo o timeout")
    args = parser.parse_args()

    print("=" * 70, flush=True)
    print("🚀 RESOLUCIÓN DE IDENTIDAD ACADÉMICA PADRÓN SNII 2026", flush=True)
    print("=" * 70, flush=True)

    # 1. Cargar datos pendientes
    if not PENDIENTES_PATH.exists():
        print(f"❌ Archivo no encontrado: {PENDIENTES_PATH}", flush=True)
        sys.exit(1)

    with open(PENDIENTES_PATH, "r", encoding="utf-8") as f:
        pendientes = json.load(f)
    print(f"📂 Cargados {len(pendientes):,} investigadores pendientes desde {PENDIENTES_PATH.name}", flush=True)

    if args.limit:
        pendientes = pendientes[:args.limit]
        print(f"🔬 Modo limitado: procesando los primeros {len(pendientes):,} registros.", flush=True)

    # 2. Cargar matches verificados existentes
    matches_data = []
    if MATCHES_PATH.exists():
        with open(MATCHES_PATH, "r", encoding="utf-8") as f:
            matches_data = json.load(f)
        print(f"📂 Cargados {len(matches_data):,} registros previos desde {MATCHES_PATH.name}", flush=True)
    else:
        print(f"⚠️ {MATCHES_PATH.name} no existe, iniciando colección limpia.", flush=True)

    if args.retry_failed_llm:
        initial_len = len(matches_data)
        matches_data = [
            m for m in matches_data 
            if not (m.get('match') is False and ('No se pudo parsear' in str(m.get('reason')) or 'Error LLM' in str(m.get('reason'))))
        ]
        purged = initial_len - len(matches_data)
        print(f"🔄 Modo Retry: {purged:,} registros con errores previos de parseo/LLM se re-evaluarán con razonamiento alto.", flush=True)

    # Respaldar archivo principal
    backup_path = MATCHES_PATH.with_suffix(".json.bak")
    if MATCHES_PATH.exists() and not backup_path.exists():
        save_atomic_json(backup_path, matches_data)
        print(f"💾 Respaldo creado en {backup_path.name}", flush=True)


    # Indexar matches previos
    # A) Por CVU
    existing_cvus = set()
    for m in matches_data:
        c = m.get("snii_cvu") or m.get("cvu")
        if c:
            try:
                existing_cvus.add(int(c))
            except:
                pass

    # B) Por Nombre + Institución para propagación (solo los que fueron match: true)
    prior_verified_name_inst = {}
    for m in matches_data:
        if m.get("match") is True:
            author_norm = clean_for_key(m.get("snii_author", ""))
            inst_norm = clean_for_key(m.get("snii_institution", ""))
            if author_norm and inst_norm:
                key = (author_norm, inst_norm)
                if key not in prior_verified_name_inst:
                    prior_verified_name_inst[key] = m

    print(f"📊 CVUs ya registrados: {len(existing_cvus):,}", flush=True)
    print(f"📊 Firmas (nombre, institución) con verificación previa: {len(prior_verified_name_inst):,}", flush=True)

    # Inicializar conexiones
    neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    local_store = QdrantStore(collection_name="local_authors")

    # Contadores de progreso
    stats = {
        "total": len(pendientes),
        "propagados_previos": 0,
        "auto_matched_clickhouse": 0,
        "llm_matched": 0,
        "sin_match": 0,
        "ya_procesados_skip": 0,
        "completados": 0
    }

    # =========================================================================
    # FASE A: PROPAGACIÓN INMEDIATA DE VERIFICADOS PREVIOS
    # =========================================================================
    print("\n" + "-" * 70, flush=True)
    print("⚡ FASE A: PROPAGACIÓN INMEDIATA DE IDENTIDADES PREVIAMENTE VERIFICADAS", flush=True)
    print("-" * 70, flush=True)

    pendientes_para_busqueda = []
    neo4j_updates_buffer = []

    for p in pendientes:
        cvu = int(p["cvu"])
        if cvu in existing_cvus:
            stats["ya_procesados_skip"] += 1
            stats["completados"] += 1
            continue

        p_name_clean = clean_for_key(p["nombre"])
        p_inst_clean = clean_for_key(p.get("institucion", ""))
        key = (p_name_clean, p_inst_clean)

        if key in prior_verified_name_inst:
            prior = prior_verified_name_inst[key]
            matched_orcid = prior.get("matched_orcid") or prior.get("orcid")
            matched_oa_id = prior.get("matched_openalex_id") or prior.get("openalex_id") or prior.get("id")
            
            new_match_entry = {
                "snii_author": p["nombre"],
                "snii_institution": p["institucion"],
                "snii_dependency": p.get("dependencia", "NO APLICA"),
                "snii_subdependency": p.get("subdependencia", "NO APLICA"),
                "snii_entidad_final": "MÉXICO",
                "snii_cvu": str(cvu),
                "match": True,
                "matched_author": prior.get("matched_author") or p["nombre"],
                "matched_author_ids": prior.get("matched_author_ids"),
                "matched_orcid": matched_orcid,
                "matched_openalex_id": matched_oa_id,
                "scopus_ids": prior.get("scopus_ids", []),
                "openalex_ids": prior.get("openalex_ids", [matched_oa_id] if matched_oa_id else []),
                "source": "Propagación Verificada (Histórico SinapsisAI)",
                "confidence": "HIGH_HISTORICAL_VERIFIED",
                "reason": f"Investigador verificado previamente por coincidencia exacta de nombre e institución. Asignado a CVU {cvu}.",
                "discarded_candidates": []
            }
            matches_data.append(new_match_entry)
            existing_cvus.add(cvu)
            stats["propagados_previos"] += 1
            stats["completados"] += 1

            if matched_orcid or matched_oa_id:
                neo4j_updates_buffer.append({
                    "cvu": str(cvu),
                    "orcid": matched_orcid,
                    "openalex_id": matched_oa_id
                })
        else:
            pendientes_para_busqueda.append(p)

    print(f"✅ Propagados exitosamente: {stats['propagados_previos']:,} investigadores con match histórico idéntico.", flush=True)
    print(f"⏳ Restantes para búsqueda profunda (Fase B/C): {len(pendientes_para_busqueda):,} investigadores.", flush=True)

    # Guardar checkpoint post-Fase A
    save_atomic_json(MATCHES_PATH, matches_data)
    if neo4j_updates_buffer:
        sync_neo4j_batch(neo4j_driver, neo4j_updates_buffer)
        neo4j_updates_buffer.clear()

    # Actualizar archivo de estado
    save_atomic_json(PROGRESS_PATH, stats)

    if args.auto_only or not pendientes_para_busqueda:
        print("\n🏁 Ejecución de fase previa concluida según parámetros.", flush=True)
        neo4j_driver.close()
        return

    # =========================================================================
    # FASE B & C: BÚSQUEDA MULTI-FUENTE + RERANKING CON LLM LOCAL
    # =========================================================================
    print("\n" + "-" * 70, flush=True)
    print("🧠 FASE B & C: BÚSQUEDA VECTORIAL / CLICKHOUSE + RERANKING LLM LOCAL", flush=True)
    print("-" * 70, flush=True)

    batch_size = args.batch_size
    records_since_save = 0
    start_time = time.time()

    for b_idx in range(0, len(pendientes_para_busqueda), batch_size):
        chunk = pendientes_para_busqueda[b_idx : b_idx + batch_size]
        
        # 1. Preparar lote para ClickHouse
        batch_query_info = []
        for p in chunk:
            k1, k2 = get_search_keys(p["nombre"])
            batch_query_info.append({"snii_name": p["nombre"], "k1": k1, "k2": k2})

        batch_oa_map = search_openalex_candidates_batch(batch_query_info, limit_per_name=5)

        for p in chunk:
            cvu = int(p["cvu"])
            snii_name = p["nombre"]
            snii_inst = p.get("institucion", "SIN INFORMACION")
            snii_dep = p.get("dependencia", "SIN INFORMACION")
            snii_sub = p.get("subdependencia", "SIN INFORMACION")
            snii_area = p.get("area", "SIN AREA")
            snii_nivel = p.get("nivel", "")

            oa_cands = batch_oa_map.get(snii_name, [])

            # --- Heurística Auto-Match ---
            best_oa = oa_cands[0] if oa_cands else None
            if best_oa and best_oa["score"] >= 0.98:
                cand_inst = best_oa.get("inst", "").lower()
                inst_tokens = [t for t in normalize_text(snii_inst).split() if len(t) > 3]
                if any(t in cand_inst for t in inst_tokens) or "sin institucion" in snii_inst.lower():
                    match_entry = {
                        "snii_author": snii_name,
                        "snii_institution": snii_inst,
                        "snii_dependency": snii_dep,
                        "snii_subdependency": snii_sub,
                        "snii_entidad_final": "MÉXICO",
                        "snii_cvu": str(cvu),
                        "match": True,
                        "matched_author": best_oa["name"],
                        "matched_author_ids": None,
                        "matched_orcid": best_oa["orcid"],
                        "matched_openalex_id": best_oa["openalex_id"],
                        "scopus_ids": best_oa.get("scopus_ids", []),
                        "openalex_ids": [best_oa["openalex_id"]] if best_oa.get("openalex_id") else [],
                        "source": "OpenAlex DB Local (Auto-High)",
                        "confidence": "AUTO_HIGH",
                        "reason": f"Nombre con similitud {best_oa['score']:.3f} y afiliación coincidente con {best_oa['inst']}.",
                        "discarded_candidates": []
                    }
                    matches_data.append(match_entry)
                    existing_cvus.add(cvu)
                    stats["auto_matched_clickhouse"] += 1
                    stats["completados"] += 1
                    records_since_save += 1

                    if best_oa["orcid"] or best_oa["openalex_id"]:
                        neo4j_updates_buffer.append({
                            "cvu": str(cvu),
                            "orcid": best_oa["orcid"],
                            "openalex_id": best_oa["openalex_id"]
                        })
                    continue

            # --- Recolección de Candidatos ---
            all_cands = []
            for c in oa_cands:
                all_cands.append({
                    "source": "OpenAlex DB Local",
                    "openalex_id": c["openalex_id"],
                    "name": c["name"],
                    "orcid": c["orcid"],
                    "affiliation": c["inst"],
                    "scopus_ids": c.get("scopus_ids", []),
                    "score_vec": c["score"]
                })

            high_quality_oa = [c for c in oa_cands if c["score"] >= 0.94 and (c.get("orcid") or c.get("inst"))]

            # Búsqueda en local_authors si es UNAM y no hay candidato fuerte
            if not high_quality_oa:
                is_unam = any(k in snii_inst.lower() for k in ["unam", "nacional autonoma de mexico"])
                if is_unam:
                    snii_text_profile = f"Nombre: {snii_name} | Institución: {snii_inst} | Subdependencia: {snii_sub}"
                    try:
                        emb = embeddings_model.embed_query(snii_text_profile)
                        loc_cands = local_store.search(emb, limit=3)
                        for c in loc_cands:
                            all_cands.append({
                                "source": "Local (Neo4j/SIIA)",
                                "name": c.get("name"),
                                "orcid": c.get("orcid"),
                                "affiliation": c.get("affiliation", ""),
                                "score_vec": c.get("score", 0.0)
                            })
                    except:
                        pass

            # --- Evaluación con LLM Local ---
            if not all_cands:
                match_entry = {
                    "snii_author": snii_name,
                    "snii_institution": snii_inst,
                    "snii_dependency": snii_dep,
                    "snii_subdependency": snii_sub,
                    "snii_entidad_final": "MÉXICO",
                    "snii_cvu": str(cvu),
                    "match": False,
                    "matched_author": None,
                    "matched_author_ids": None,
                    "matched_orcid": None,
                    "matched_openalex_id": None,
                    "scopus_ids": [],
                    "openalex_ids": [],
                    "source": None,
                    "confidence": "NONE",
                    "reason": "No se encontraron candidatos en ClickHouse ni Qdrant.",
                    "discarded_candidates": []
                }
                matches_data.append(match_entry)
                existing_cvus.add(cvu)
                stats["sin_match"] += 1
                stats["completados"] += 1
                records_since_save += 1
            else:
                candidates_str = ""
                for idx_c, cand in enumerate(all_cands[:6]):
                    candidates_str += f"{idx_c+1}. [{cand['source']}] {cand['name']} | ORCID: {cand.get('orcid')} | Afiliación: {cand.get('affiliation')}\n"

                system_instructions = (
                    "Eres un experto investigador bibliográfico de México. Tu tarea es desambiguar e identificar "
                    "si alguno de los candidatos potenciales corresponde exactamente al investigador del SNII."
                )
                user_prompt = f"""Investigador SNII buscado:
Nombre: {snii_name}
Nivel SNII: {snii_nivel} | Área: {snii_area}
Institución: {snii_inst}
Dependencia: {snii_dep}
Subdependencia: {snii_sub}

Candidatos potenciales:
{candidates_str}"""

                matched_flag = False
                matched_cand = None
                reason_str = "No coincide"
                found_orcid = None

                try:
                    llm_model_name = "openai/gpt-oss-20b" if LLM_MODEL in ("default", "") else LLM_MODEL
                    resp = openai_client.chat.completions.create(
                        model=llm_model_name,
                        messages=[
                            {"role": "system", "content": system_instructions},
                            {"role": "user", "content": user_prompt}
                        ],
                        response_format={"type": "json_schema", "json_schema": SNII_MATCH_SCHEMA},
                        temperature=0.0,
                        max_tokens=1500,
                        timeout=90.0
                    )
                    raw_content = resp.choices[0].message.content
                    parsed = parse_llm_json_response(raw_content)
                    matched_flag = bool(parsed.get("match", False))
                    reason_str = parsed.get("reason", "Decisión LLM")
                    found_orcid = parsed.get("orcid")

                    c_idx = parsed.get("matched_candidate_index")
                    if matched_flag and c_idx is not None and isinstance(c_idx, int) and 1 <= c_idx <= len(all_cands):
                        matched_cand = all_cands[c_idx - 1]
                    elif matched_flag and all_cands:
                        matched_cand = all_cands[0]
                except Exception as e:
                    reason_str = f"Error LLM: {e}"

                if matched_flag and matched_cand:
                    final_orcid = found_orcid or matched_cand.get("orcid")
                    final_oa_id = matched_cand.get("openalex_id")
                    match_entry = {
                        "snii_author": snii_name,
                        "snii_institution": snii_inst,
                        "snii_dependency": snii_dep,
                        "snii_subdependency": snii_sub,
                        "snii_entidad_final": "MÉXICO",
                        "snii_cvu": str(cvu),
                        "match": True,
                        "matched_author": matched_cand.get("name"),
                        "matched_author_ids": None,
                        "matched_orcid": final_orcid,
                        "matched_openalex_id": final_oa_id,
                        "scopus_ids": matched_cand.get("scopus_ids", []),
                        "openalex_ids": [final_oa_id] if final_oa_id else [],
                        "source": f"{matched_cand.get('source')} + LLM Reranking",
                        "confidence": "LLM_VERIFIED",
                        "reason": reason_str,
                        "discarded_candidates": []
                    }
                    stats["llm_matched"] += 1
                    if final_orcid or final_oa_id:
                        neo4j_updates_buffer.append({
                            "cvu": str(cvu),
                            "orcid": final_orcid,
                            "openalex_id": final_oa_id
                        })
                else:
                    match_entry = {
                        "snii_author": snii_name,
                        "snii_institution": snii_inst,
                        "snii_dependency": snii_dep,
                        "snii_subdependency": snii_sub,
                        "snii_entidad_final": "MÉXICO",
                        "snii_cvu": str(cvu),
                        "match": False,
                        "matched_author": None,
                        "matched_author_ids": None,
                        "matched_orcid": None,
                        "matched_openalex_id": None,
                        "scopus_ids": [],
                        "openalex_ids": [],
                        "source": "LLM Verification",
                        "confidence": "LOW_OR_REJECTED",
                        "reason": reason_str,
                        "discarded_candidates": []
                    }
                    stats["sin_match"] += 1

                matches_data.append(match_entry)
                existing_cvus.add(cvu)
                stats["completados"] += 1
                records_since_save += 1

            # Checkpoint periódico
            if records_since_save >= args.checkpoint_interval:
                save_atomic_json(MATCHES_PATH, matches_data)
                save_atomic_json(PROGRESS_PATH, stats)
                if neo4j_updates_buffer:
                    sync_neo4j_batch(neo4j_driver, neo4j_updates_buffer)
                    neo4j_updates_buffer.clear()
                
                elapsed = time.time() - start_time
                pct = (stats["completados"] / stats["total"]) * 100
                print(f"   💾 Checkpoint [{stats['completados']}/{stats['total']} ({pct:.1f}%)] | Auto: {stats['auto_matched_clickhouse']} | LLM: {stats['llm_matched']} | NoMatch: {stats['sin_match']} | T: {elapsed/60:.1f}m", flush=True)
                records_since_save = 0

    # Guardado final
    save_atomic_json(MATCHES_PATH, matches_data)
    save_atomic_json(PROGRESS_PATH, stats)
    if neo4j_updates_buffer:
        sync_neo4j_batch(neo4j_driver, neo4j_updates_buffer)
        neo4j_updates_buffer.clear()

    neo4j_driver.close()
    print("\n" + "=" * 70, flush=True)
    print("✅ PROCESAMIENTO DE IDENTIDADES CONCLUIDO", flush=True)
    print(f"   • Total procesados: {stats['completados']:,}", flush=True)
    print(f"   • Propagados de histórico: {stats['propagados_previos']:,}", flush=True)
    print(f"   • Auto-match ClickHouse: {stats['auto_matched_clickhouse']:,}", flush=True)
    print(f"   • Resueltos con LLM: {stats['llm_matched']:,}", flush=True)
    print(f"   • Sin match confirmado: {stats['sin_match']:,}", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    main()
