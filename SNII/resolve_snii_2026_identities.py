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
import clickhouse_connect
import requests
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

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

# ClickHouse ORCID Config (Local)
CH_ORCID_HOST = os.getenv("CH_ORCID_HOST", "127.0.0.1")
CH_ORCID_PORT = int(os.getenv("CH_ORCID_PORT", 8123))
CH_ORCID_USER = os.getenv("CH_ORCID_USER", "admin")
CH_ORCID_PASS = os.getenv("CH_ORCID_PASSWORD", "admin")
CH_DB_ORCID   = os.getenv("CH_ORCID_DATABASE", "orcid")

def get_orcid_client():
    """Conector para ORCID Records (Local ClickHouse)."""
    return clickhouse_connect.get_client(
        host=CH_ORCID_HOST,
        port=CH_ORCID_PORT,
        username=CH_ORCID_USER,
        password=CH_ORCID_PASS,
        database=CH_DB_ORCID,
        connect_timeout=10
    )

# LLM Config (LM Studio)
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "sk-lm-911DBjzu:mnU3kI7Zj5dGgX8mzxyj")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/default")
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
                "description": "Paso a paso: compara nombre y variantes, jerarquía institucional (UNAM, UAM, IPN, etc.), y tópicos de investigación con el Área SNII (máx 40 palabras)."
            },
            "match": {
                "type": "boolean",
                "description": "True si alguno de los candidatos coincide con el investigador del SNII, False de lo contrario."
            },
            "matched_candidate_index": {
                "type": ["integer", "null"],
                "description": "Número 1-based del candidato ganador (1, 2, ...), o null si match es False."
            },
            "confidence": {
                "type": "string",
                "enum": ["HIGH", "MEDIUM", "LOW", "NONE"],
                "description": "Nivel de certeza de la coincidencia."
            }
        },
        "required": ["analysis", "match", "matched_candidate_index", "confidence"],
        "additionalProperties": False
    }
}

SPANISH_PARTICLES = {'de', 'del', 'la', 'las', 'los', 'san', 'santa', 'y', 'e', 'van', 'von', 'da', 'di'}


def get_search_keys(name: str):
    """Extrae combinaciones de apellidos y nombres para búsqueda exhaustiva en ClickHouse ignorando partículas nobiliarias/preposiciones."""
    if not name or not isinstance(name, str) or not name.strip():
        return "desconocido", "desconocido", [("desconocido", "desconocido")], ["desconocido"]
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


def calc_cand_score(seed_str: str, cand_str: str) -> float:
    """Calcula similitud híbrida combinando Jaro-Winkler sobre cadenas ordenadas y coincidencia por tokens/iniciales con prioridad en apellido paterno."""
    if not seed_str or not cand_str:
        return 0.0
    seed_str = str(seed_str)
    cand_str = str(cand_str)
    raw_clean = seed_str.replace('‐', ' ').replace('-', ' ').lower()
    if ',' in raw_clean:
        ap = [p for p in raw_clean.split(',')[0].split() if p not in SPANISH_PARTICLES and len(p) > 2]
        paterno = ap[0] if ap else ''
    else:
        ap = [p for p in raw_clean.split() if p not in SPANISH_PARTICLES and len(p) > 2]
        paterno = ap[0] if ap else ''

    seed_tokens = set([t for t in raw_clean.replace(',', ' ').split() if len(t) > 1 and t not in SPANISH_PARTICLES])
    cand_tokens = [t.strip('.-') for t in cand_str.lower().replace('‐', ' ').replace('-', ' ').replace(',', ' ').split() if len(t.strip('.-')) > 0 and t.strip('.-') not in SPANISH_PARTICLES]
    if not cand_tokens:
        return 0.0
    matched = 0.0
    for ct in cand_tokens:
        if ct in seed_tokens:
            matched += 1.0
        elif len(ct) == 1 and any(st.startswith(ct) for st in seed_tokens):
            matched += 0.9
        elif any(len(st) > 3 and (st in ct or ct in st) for st in seed_tokens):
            matched += 0.8
    token_score = matched / len(cand_tokens)

    # Si el apellido paterno no está presente en el candidato, aplicar penalización para evitar falsos positivos
    if paterno and not (paterno in cand_tokens or any(paterno in ct or ct in paterno for ct in cand_tokens if len(ct) > 3)):
        token_score *= 0.75

    seed_norm = ' '.join(sorted(list(seed_tokens)))
    cand_norm = ' '.join(sorted(cand_tokens))
    jw_score = jaro_winkler(seed_norm, cand_norm)
    return max(jw_score, token_score)


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


def search_openalex_candidates_batch(names_info: list, limit_per_name: int = 6) -> dict:
    """Busca candidatos en ClickHouse (rag.authors_seed_mexico) en una sola consulta sin JOINs."""
    if not names_info:
        return {}
    ch = get_ch_client()
    clauses = []
    all_k1 = []
    for info in names_info:
        subclauses = []
        pairs = info.get('pairs') or [(info['k1'], info['k2'])]
        for p1, p2 in pairs:
            r1 = get_accent_insensitive_regex(p1.replace("'", "''"))
            r2 = get_accent_insensitive_regex(p2.replace("'", "''"))
            subclauses.append(f"(match(display_name, '{r1}') AND match(display_name, '{r2}'))")
        clauses.append(f"({' OR '.join(subclauses)})")
        all_k1.extend([k.lower() for k in info.get('all_keys', [info['k1']]) if len(k) > 2])
    
    all_k1 = list(set(all_k1))
    if not all_k1:
        return {info['snii_name']: [] for info in names_info}
    
    pre_filter = f"multiSearchAnyCaseInsensitive(display_name, {all_k1})"
    where_clause = " OR ".join(clauses)
    query_limit = min(max(len(names_info) * 300, 1500), 10000)
    
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
    seen_ids = {info['snii_name']: set() for info in names_info}

    for r in rows:
        openalex_id, disp_name, orcid_val, ids_json, raw_data_str = r[0], r[1], r[2], r[3], r[4]
        inst_name = ""
        topics_list = []
        works_count = 0
        cited_by_count = 0
        alt_names = []
        try:
            if raw_data_str:
                raw_data = json.loads(raw_data_str) if isinstance(raw_data_str, str) else raw_data_str
                affils = raw_data.get('affiliations') or []
                if affils and isinstance(affils, list):
                    # Priorizar instituciones mexicanas (MX) y las más recientes
                    def affil_sort_key(a):
                        inst = a.get('institution', {}) if isinstance(a, dict) else {}
                        is_mx = 1 if inst.get('country_code') == 'MX' else 0
                        years = a.get('years', []) if isinstance(a, dict) else []
                        max_year = max(years) if years else 0
                        return (is_mx, max_year)
                    
                    sorted_affils = sorted(affils, key=affil_sort_key, reverse=True)
                    inst_names = []
                    for a in sorted_affils:
                        if isinstance(a, dict) and a.get('institution'):
                            d_name = a['institution'].get('display_name')
                            if d_name and d_name not in inst_names:
                                inst_names.append(d_name)
                    if inst_names:
                        inst_name = ", ".join(inst_names[:3])
                
                if not inst_name:
                    lki = raw_data.get('last_known_institution') or {}
                    inst_name = lki.get('display_name', '')
                
                # Extraer tópicos disciplinarios
                t_data = raw_data.get('topics') or []
                if isinstance(t_data, list):
                    for t in t_data[:3]:
                        if isinstance(t, dict) and t.get('display_name'):
                            topics_list.append(t['display_name'])

                # Métricas y variantes
                works_count = raw_data.get('works_count', 0)
                cited_by_count = raw_data.get('cited_by_count', 0)
                alt_names = (raw_data.get('display_name_alternatives') or [])[:3]
        except:
            pass

        for info in names_info:
            snii_name = info['snii_name']
            ns = calc_cand_score(snii_name, str(disp_name))
            if ns > 0.70:
                if openalex_id in seen_ids[snii_name]:
                    continue
                seen_ids[snii_name].add(openalex_id)

                scopus_ids = []
                try:
                    ids_data = json.loads(ids_json) if isinstance(ids_json, str) else (ids_json or {})
                    scopus_raw = ids_data.get('scopus') or []
                    scopus_ids = [scopus_raw] if isinstance(scopus_raw, str) else scopus_raw
                except:
                    pass
                results_map[snii_name].append({
                    "source": "OpenAlex DB Local",
                    "openalex_id": openalex_id,
                    "name": disp_name,
                    "orcid": orcid_val or None,
                    "inst": inst_name or "",
                    "affiliation": inst_name or "",
                    "scopus_ids": scopus_ids,
                    "score": ns,
                    "topics": topics_list,
                    "works_count": works_count,
                    "cited_by_count": cited_by_count,
                    "alt_names": alt_names
                })

    for name in results_map:
        results_map[name].sort(key=lambda x: x['score'], reverse=True)
        results_map[name] = results_map[name][:limit_per_name]

    return results_map


def search_orcid_records_batch(names_info: list, limit_per_name: int = 4) -> dict:
    """Busca candidatos en ClickHouse Local (orcid.orcid_records) en una sola consulta sin JOINs."""
    if not names_info:
        return {}
    try:
        ch = get_orcid_client()
    except Exception as e:
        print(f"      ⚠️ No se pudo conectar a ClickHouse ORCID Local: {e}", flush=True)
        return {info['snii_name']: [] for info in names_info}

    clauses = []
    all_k1 = []
    for info in names_info:
        subclauses = []
        pairs = info.get('pairs') or [(info['k1'], info['k2'])]
        for p1, p2 in pairs:
            r1 = get_accent_insensitive_regex(p1.replace("'", "''"))
            r2 = get_accent_insensitive_regex(p2.replace("'", "''"))
            subclauses.append(f"((match(family_name, '{r1}') AND match(given_names, '{r2}')) OR (match(credit_name, '{r1}') AND match(credit_name, '{r2}')))")
        clauses.append(f"({' OR '.join(subclauses)})")
        all_k1.extend([k.lower() for k in info.get('all_keys', [info['k1']]) if len(k) > 2])

    all_k1 = list(set(all_k1))
    if not all_k1:
        return {info['snii_name']: [] for info in names_info}

    pre_filter = f"multiSearchAnyCaseInsensitive(family_name, {all_k1}) OR multiSearchAnyCaseInsensitive(credit_name, {all_k1})"
    where_clause = " OR ".join(clauses)
    query_limit = min(max(len(names_info) * 100, 500), 5000)

    query = f"""
    SELECT orcid, given_names, family_name, credit_name, last_affiliation, last_affiliation_country
    FROM orcid.orcid_records
    WHERE ({pre_filter}) AND ({where_clause})
    LIMIT {query_limit}
    """
    try:
        rows = ch.query(query).result_rows
    except Exception as e:
        print(f"      ⚠️ Error en consulta ClickHouse ORCID: {e}", flush=True)
        return {info['snii_name']: [] for info in names_info}

    results_map = {info['snii_name']: [] for info in names_info}
    seen_orcids = {info['snii_name']: set() for info in names_info}

    for r in rows:
        orc, gn, fn, cn, aff, aff_country = r[0], str(r[1] or ''), str(r[2] or ''), str(r[3] or ''), str(r[4] or ''), str(r[5] or '')
        cand_name = cn.strip() if cn else f"{gn} {fn}".strip()
        full_aff = f"{aff} ({aff_country})".strip() if aff_country and aff else (aff or aff_country or "")

        for info in names_info:
            snii_name = info['snii_name']
            ns = calc_cand_score(snii_name, cand_name)
            if ns > 0.70:
                if orc in seen_orcids[snii_name]:
                    continue
                seen_orcids[snii_name].add(orc)
                results_map[snii_name].append({
                    "source": "ORCID Local DB",
                    "openalex_id": None,
                    "name": cand_name,
                    "orcid": orc,
                    "inst": full_aff,
                    "affiliation": full_aff,
                    "scopus_ids": [],
                    "score": ns,
                    "topics": [],
                    "works_count": 0,
                    "cited_by_count": 0,
                    "alt_names": []
                })

    for name in results_map:
        results_map[name].sort(key=lambda x: x['score'], reverse=True)
        results_map[name] = results_map[name][:limit_per_name]

    return results_map


def search_web_orcid_candidates(snii_name: str, snii_inst: str, snii_dep: str = "", snii_sub: str = "") -> list:
    """
    Búsqueda web de último recurso:
    1. Consulta ORCID Public API expanded-search estructurada.
    2. Respaldo en DuckDuckGo (ddgs) para capturar perfiles orcid.org y páginas institucionales.
    Retorna lista de candidatos estructurados para evaluación del LLM.
    """
    if not snii_name or not isinstance(snii_name, str) or not snii_name.strip():
        return []
    snii_name = snii_name.strip()
    snii_inst = str(snii_inst or "")
    snii_dep = str(snii_dep or "")
    snii_sub = str(snii_sub or "")

    web_cands = []
    seen_orcids = set()

    k1, k2, pairs, all_keys = get_search_keys(snii_name)

    # 1. Búsqueda estructurada en ORCID Public Expanded-Search API
    headers = {"Accept": "application/json"}
    orcid_api_url = "https://pub.orcid.org/v3.0/expanded-search/"

    query_parts = []
    if k1 and k2:
        query_parts.append(f'(family-name:"{k1}" AND given-names:"{k2}")')
    clean_paterno = snii_name.split(',')[0].strip() if ',' in snii_name else k1
    if clean_paterno and clean_paterno != k1:
        query_parts.append(f'family-name:"{clean_paterno}"')

    inst_clean = normalize_text(snii_inst).lower()
    inst_keyword = ""
    for kw in ["unam", "ipn", "cinvestav", "uam", "uanl", "udeg", "buap", "uaeh", "uaz", "colmex", "cicese", "cio", "inaoe", "itesm", "tecnologico nacional"]:
        if kw in inst_clean:
            inst_keyword = kw
            break

    full_query = " OR ".join(query_parts) if query_parts else f'text:"{snii_name}"'
    if inst_keyword and len(inst_keyword) > 3:
        full_query = f"({full_query}) AND affiliation-org-name:{inst_keyword}"

    try:
        resp = requests.get(orcid_api_url, params={"q": full_query}, headers=headers, timeout=6.0)
        if resp.status_code == 200:
            exp_results = resp.json().get("expanded-result", [])
            for res in exp_results:
                o_id = res.get("orcid-id")
                if not o_id or o_id in seen_orcids:
                    continue
                g_names = res.get("given-names") or ""
                f_names = res.get("family-names") or ""
                c_name = res.get("credit-name") or f"{g_names} {f_names}".strip()
                aff_list = res.get("institution-name") or []
                aff_clean = list(dict.fromkeys(aff_list)) if isinstance(aff_list, list) else [str(aff_list)]
                aff_str = ", ".join(aff_clean[:6])

                score = calc_cand_score(snii_name, c_name)
                if score >= 0.70:
                    seen_orcids.add(o_id)
                    web_cands.append({
                        "source": "Web ORCID API",
                        "openalex_id": None,
                        "name": c_name,
                        "orcid": o_id,
                        "inst": aff_str,
                        "affiliation": aff_str,
                        "scopus_ids": [],
                        "score": score,
                        "topics": [],
                        "works_count": 0,
                        "cited_by_count": 0,
                        "alt_names": []
                    })
    except Exception:
        pass

    if web_cands:
        web_cands.sort(key=lambda x: x["score"], reverse=True)
        return web_cands[:4]

    # 2. Respaldo DuckDuckGo si ORCID API no arrojó candidatos
    ddg_query = f'"{snii_name}" {inst_keyword if inst_keyword else ""} orcid.org'.strip()
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(ddg_query, max_results=4))
            for item in results:
                title = item.get("title", "")
                link = item.get("href", "")
                body = item.get("body", "")

                orcid_m = re.search(r'orcid\.org/(\d{4}-\d{4}-\d{4}-[\dX]{4})', f"{link} {body} {title}")
                if orcid_m:
                    o_id = orcid_m.group(1)
                    if o_id not in seen_orcids:
                        seen_orcids.add(o_id)
                        cand_title_clean = re.sub(r'\(.*?\)|[-|].*?orcid.*|padron.*', '', title, flags=re.IGNORECASE).strip()
                        score = calc_cand_score(snii_name, cand_title_clean if cand_title_clean else title)
                        if score >= 0.65:
                            web_cands.append({
                                "source": "Web DuckDuckGo",
                                "openalex_id": None,
                                "name": cand_title_clean or title,
                                "orcid": o_id,
                                "inst": f"Snippet: {body[:100]}...",
                                "affiliation": f"Snippet: {body[:100]}...",
                                "scopus_ids": [],
                                "score": score,
                                "topics": [],
                                "works_count": 0,
                                "cited_by_count": 0,
                                "alt_names": []
                            })
    except Exception:
        pass

    web_cands.sort(key=lambda x: x["score"], reverse=True)
    return web_cands[:4]


def call_llm_evaluator(snii_dict: dict, candidates: list, is_web: bool = False) -> tuple:
    """
    Evalúa candidatos (locales o web) con el LLM local en LM Studio.
    Retorna: (matched_flag: bool, matched_cand: dict or None, reason_str: str, confidence_val: str)
    """
    if not candidates:
        return False, None, "No se encontraron candidatos", "NONE"

    candidates_str = ""
    for idx_c, cand in enumerate(candidates[:6]):
        src_label = cand.get('source', 'Candidato')
        parts = [f"[{src_label}] {cand['name']}"]
        if cand.get("alt_names"):
            parts.append(f"Variantes: {', '.join(cand['alt_names'])}")
        parts.append(f"ORCID: {cand.get('orcid') or 'None'}")
        parts.append(f"Afiliación: {cand.get('affiliation') or cand.get('inst') or 'None'}")
        if cand.get("works_count") or cand.get("cited_by_count"):
            parts.append(f"Obras: {cand.get('works_count', 0)} | Citas: {cand.get('cited_by_count', 0)}")
        if cand.get("topics"):
            parts.append(f"Tópicos: {', '.join(cand['topics'])}")
        candidates_str += f"{idx_c+1}. {' | '.join(parts)}\n"

    system_instructions = (
        "Eres un experto cienciómetra y desambiguador de identidades académicas de México (SNII/CONAHCYT, OpenAlex, ORCID).\n"
        "Tu tarea es evaluar con rigor si alguno de los candidatos potenciales corresponde a la misma persona física que el investigador del SNII.\n\n"
        "DIRECTRICES CRÍTICAS DE DECISIÓN:\n"
        "1. NOMBRES HISPANOS:\n"
        "   - El SNII registra 'APELLIDO_PATERNO APELLIDO_MATERNO, NOMBRES'.\n"
        "   - En OpenAlex/ORCID/Web los autores firman como 'Nombre Primer-Apellido', 'Nombre ApellidoPaterno ApellidoMaterno', con iniciales o con guión (ej. Taide Arista-Ugalde o Taide L. Arista). Son variantes válidas de la misma persona.\n\n"
        "2. JERARQUÍA INSTITUCIONAL MEXICANA:\n"
        "   - OpenAlex y ORCID suelen indexar únicamente la institución paraguas (ej. 'Universidad Nacional Autónoma de México' o 'UNAM'), mientras que SNII detalla la subdependencia ('Facultad de Ciencias', 'FES Iztacala', 'Instituto de Investigaciones...'). ¡ESTO ES UNA COINCIDENCIA INSTITUCIONAL PLENA Y VÁLIDA!\n"
        "   - Aplica igual para UAM (Iztapalapa, Azcapotzalco, Xochimilco, etc.), IPN (ESFM, UPIITA, CINVESTAV), Universidades Estatales (UANL, UdeG, BUAP, UAZ, etc.) e Institutos Nacionales de Salud.\n"
        "   - Si la institución del candidato es la institución paraguas de la dependencia del SNII, tómalo como match institucional válido.\n"
        "   - Si el candidato pertenece a una universidad o estado completamente diferente (ej. Universidad Autónoma de Nuevo León vs UNAM, o UdeG vs BUAP), ¡ES UN HOMÓNIMO DISTINTO, RECHÁZALO con match: false!\n\n"
        "3. ÁREA DEL SNII Y TÓPICOS CIENTÍFICOS:\n"
        "   - Compara el Área del SNII con los tópicos y publicaciones del candidato para confirmar afinidad disciplinaria.\n"
        "   - Si el nombre coincide y los tópicos corresponden al área del SNII, confirma el match aunque la institución no esté registrada o esté desactualizada.\n\n"
        "4. BREVEDAD EN ANÁLISIS:\n"
        "   - En 'analysis', escribe ÚNICAMENTE 1 o 2 oraciones breves (máximo 40 palabras, sin tablas ni markdown largo).\n"
        "   - Concluye tu decisión final en 'match': true/false, y especifica 'matched_candidate_index' (1-based) y 'confidence'."
    )

    fuente_label = "Candidatos encontrados en la WEB (último intento):" if is_web else "Candidatos potenciales:"
    user_prompt = f"""Investigador SNII buscado:
Nombre: {snii_dict['nombre']}
Nivel SNII: {snii_dict.get('nivel', '')} | Área: {snii_dict.get('area', 'SIN AREA')}
Institución: {snii_dict.get('institucion', 'SIN INFORMACION')}
Dependencia: {snii_dict.get('dependencia', 'SIN INFORMACION')}
Subdependencia: {snii_dict.get('subdependencia', 'SIN INFORMACION')}

{fuente_label}
{candidates_str}"""

    matched_flag = False
    matched_cand = None
    reason_str = "No coincide"
    confidence_val = "NONE"

    try:
        llm_model_name = "openai/default" if LLM_MODEL in ("default", "") else LLM_MODEL
        resp = openai_client.chat.completions.create(
            model=llm_model_name,
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_schema", "json_schema": SNII_MATCH_SCHEMA},
            temperature=0.0,
            max_tokens=2500,
            timeout=90.0
        )
        raw_content = resp.choices[0].message.content
        if not raw_content and hasattr(resp.choices[0].message, "reasoning") and resp.choices[0].message.reasoning:
            raw_content = resp.choices[0].message.reasoning
        parsed = parse_llm_json_response(raw_content)
        matched_flag = bool(parsed.get("match", False))
        reason_str = parsed.get("reason") or (parsed.get("analysis", "")[:250] if parsed.get("analysis") else "Decisión LLM")
        confidence_val = parsed.get("confidence") or ("HIGH_WEB_VERIFIED" if is_web else "LLM_VERIFIED")

        c_idx = parsed.get("matched_candidate_index")
        if matched_flag and c_idx == 0:
            c_idx = 1
        if matched_flag and c_idx is not None and isinstance(c_idx, int) and 1 <= c_idx <= len(candidates):
            matched_cand = candidates[c_idx - 1]
        elif matched_flag and candidates:
            matched_cand = candidates[0]
    except Exception as e:
        reason_str = f"Error LLM: {e}"

    return matched_flag, matched_cand, reason_str, confidence_val


def parse_llm_json_response(raw_input) -> dict:
    """Extrae y parsea limpiamente el objeto JSON de respuesta del LLM con rescate automático y normalización de claves."""
    if not raw_input:
        return {"match": False, "reason": "Respuesta vacía"}
    if isinstance(raw_input, dict):
        return raw_input
    
    text = str(raw_input)
    if "<|channel|>final" in text:
        text = text.split("<|channel|>final")[-1]
    
    clean = text.strip().replace('```json', '').replace('```', '').strip()

    def normalize_dict(d):
        if not isinstance(d, dict):
            return None
        # Normalizar match
        match_val = None
        for k in ["match", "match_found", "is_match", "matched", "matching", "matches"]:
            if k in d and d[k] is not None:
                if isinstance(d[k], bool):
                    match_val = d[k]
                elif isinstance(d[k], str):
                    match_val = d[k].lower() in ('true', 'yes', 'si', '1')
                elif isinstance(d[k], (int, float)):
                    match_val = bool(d[k])
                break
        if match_val is None:
            return None
        d["match"] = match_val

        # Normalizar índice de candidato ganador
        for k in ["matched_candidate_id", "candidate_index", "winner_index", "matched_index", "candidate_id", "candidate"]:
            if k in d and "matched_candidate_index" not in d:
                try:
                    d["matched_candidate_index"] = int(d[k]) if d[k] is not None else None
                except:
                    pass

        # Normalizar ORCID
        for k in ["matched_orcid", "orcid_id", "orcid_url"]:
            if k in d and "orcid" not in d:
                d["orcid"] = d[k]

        return d

    try:
        res = json.loads(clean)
        norm = normalize_dict(res)
        if norm:
            return norm
    except Exception:
        pass

    # Buscar bloques JSON que contengan llaves
    for pattern in [r'\{[^{}]*\}', r'\{[\s\S]*?\}']:
        for m in re.finditer(pattern, text):
            try:
                res = json.loads(m.group(0))
                norm = normalize_dict(res)
                if norm:
                    return norm
            except Exception:
                pass

    # Rescate regex directo si hubo algún problema sintáctico
    match_m = re.search(r'"(?:match|match_found|is_match|matched)"\s*:\s*(true|false)', text, re.IGNORECASE)
    if match_m:
        is_match = match_m.group(1).lower() == 'true'
        idx_m = re.search(r'"(?:matched_candidate_index|matched_candidate_id|candidate_index)"\s*:\s*(\d+)', text)
        cand_idx = int(idx_m.group(1)) if idx_m else (1 if is_match else None)
        orcid_m = re.search(r'"(?:orcid|matched_orcid)"\s*:\s*"([^"]+)"', text)
        found_orcid = orcid_m.group(1) if (orcid_m and orcid_m.group(1).lower() not in ('null', 'none')) else None
        reason_m = re.search(r'"(?:reason|analysis)"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
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
    parser.add_argument("--retry-unmatched", action="store_true", help="Re-evalúa con ORCID local y búsqueda web los registros que previamente quedaron como match: False")
    parser.add_argument("--no-web", action="store_true", help="Desactiva la búsqueda web como último recurso")
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

    if args.retry_unmatched:
        initial_len = len(matches_data)
        pend_cvus = set(str(p["cvu"]) for p in pendientes)
        matches_data = [
            m for m in matches_data 
            if not ((str(m.get("snii_cvu") or m.get("cvu"))) in pend_cvus and m.get("match") is False)
        ]
        purged = initial_len - len(matches_data)
        print(f"🔄 Modo Retry Unmatched: {purged:,} registros sin match previo se re-evaluarán con ORCID Local, Búsqueda Web y LLM.", flush=True)
    elif args.retry_failed_llm:
        initial_len = len(matches_data)
        matches_data = [
            m for m in matches_data 
            if not (m.get('match') is False and ('No se pudo parsear' in str(m.get('reason')) or 'Error LLM' in str(m.get('reason'))))
        ]
        purged = initial_len - len(matches_data)
        print(f"🔄 Modo Retry LLM: {purged:,} registros con errores previos de parseo/LLM se re-evaluarán con razonamiento alto.", flush=True)

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
        "auto_matched_orcid": 0,
        "llm_matched": 0,
        "web_matched": 0,
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
            k1, k2, pairs, all_keys = get_search_keys(p["nombre"])
            batch_query_info.append({
                "snii_name": p["nombre"],
                "k1": k1,
                "k2": k2,
                "pairs": pairs,
                "all_keys": all_keys
            })

        batch_oa_map = search_openalex_candidates_batch(batch_query_info, limit_per_name=6)
        batch_orcid_map = search_orcid_records_batch(batch_query_info, limit_per_name=4)

        for p in chunk:
            cvu = int(p["cvu"])
            snii_name = p["nombre"]
            snii_inst = p.get("institucion", "SIN INFORMACION")
            snii_dep = p.get("dependencia", "SIN INFORMACION")
            snii_sub = p.get("subdependencia", "SIN INFORMACION")
            snii_area = p.get("area", "SIN AREA")
            snii_nivel = p.get("nivel", "")

            oa_cands = batch_oa_map.get(snii_name, [])
            local_orcid_cands = batch_orcid_map.get(snii_name, [])

            # --- 1. Heurística Auto-Match (OpenAlex u ORCID Local >= 0.98 + Afiliación) ---
            auto_matched = False
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
                    auto_matched = True

            if not auto_matched and local_orcid_cands:
                best_loc = local_orcid_cands[0]
                if best_loc["score"] >= 0.98:
                    cand_inst = best_loc.get("affiliation", "").lower()
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
                            "matched_author": best_loc["name"],
                            "matched_author_ids": None,
                            "matched_orcid": best_loc["orcid"],
                            "matched_openalex_id": None,
                            "scopus_ids": [],
                            "openalex_ids": [],
                            "source": "ORCID Local DB (Auto-High)",
                            "confidence": "AUTO_HIGH",
                            "reason": f"Nombre con similitud {best_loc['score']:.3f} en ORCID y afiliación coincidente con {best_loc['affiliation']}.",
                            "discarded_candidates": []
                        }
                        matches_data.append(match_entry)
                        existing_cvus.add(cvu)
                        stats["auto_matched_orcid"] += 1
                        stats["completados"] += 1
                        records_since_save += 1

                        if best_loc["orcid"]:
                            neo4j_updates_buffer.append({
                                "cvu": str(cvu),
                                "orcid": best_loc["orcid"],
                                "openalex_id": None
                            })
                        auto_matched = True

            if auto_matched:
                continue

            # --- 2. Recolección y Deduplicación de Candidatos Locales ---
            all_cands = []
            seen_cand_orcids = set()

            for c in oa_cands:
                o_val = c.get("orcid")
                if o_val:
                    seen_cand_orcids.add(o_val)
                all_cands.append({
                    "source": "OpenAlex DB Local",
                    "openalex_id": c["openalex_id"],
                    "name": c["name"],
                    "orcid": o_val,
                    "affiliation": c.get("inst", ""),
                    "scopus_ids": c.get("scopus_ids", []),
                    "score_vec": c["score"],
                    "topics": c.get("topics", []),
                    "works_count": c.get("works_count", 0),
                    "cited_by_count": c.get("cited_by_count", 0),
                    "alt_names": c.get("alt_names", [])
                })

            for c in local_orcid_cands:
                o_val = c.get("orcid")
                if o_val and o_val in seen_cand_orcids:
                    continue
                if o_val:
                    seen_cand_orcids.add(o_val)
                all_cands.append(c)

            # Búsqueda en local_authors si es UNAM y no hay candidatos locales de alta calidad
            high_quality_cands = [c for c in all_cands if c.get("score_vec", c.get("score", 0)) >= 0.94 and (c.get("orcid") or c.get("affiliation"))]
            if not high_quality_cands:
                is_unam = any(k in snii_inst.lower() for k in ["unam", "nacional autonoma de mexico"])
                if is_unam:
                    snii_text_profile = f"Nombre: {snii_name} | Institución: {snii_inst} | Subdependencia: {snii_sub}"
                    try:
                        emb = embeddings_model.embed_query(snii_text_profile)
                        loc_cands = local_store.search(emb, limit=3)
                        for c in loc_cands:
                            o_val = c.get("orcid")
                            if o_val and o_val in seen_cand_orcids:
                                continue
                            if o_val:
                                seen_cand_orcids.add(o_val)
                            all_cands.append({
                                "source": "Local (Neo4j/SIIA)",
                                "openalex_id": None,
                                "name": c.get("name"),
                                "orcid": o_val,
                                "affiliation": c.get("affiliation", ""),
                                "scopus_ids": [],
                                "score_vec": c.get("score", 0.0),
                                "topics": [],
                                "works_count": 0,
                                "cited_by_count": 0,
                                "alt_names": []
                            })
                    except:
                        pass

            # --- 3. Evaluación con LLM de Candidatos Locales ---
            snii_dict = {
                "nombre": snii_name,
                "institucion": snii_inst,
                "dependencia": snii_dep,
                "subdependencia": snii_sub,
                "area": snii_area,
                "nivel": snii_nivel
            }

            matched_flag = False
            matched_cand = None
            reason_str = "No coincide con candidatos locales"
            confidence_val = "NONE"
            is_web_match = False

            if all_cands:
                matched_flag, matched_cand, reason_str, confidence_val = call_llm_evaluator(snii_dict, all_cands, is_web=False)

            # --- 4. Búsqueda Web como ÚLTIMO RECURSO si no se encontró o fue rechazado localmente ---
            if not matched_flag and not args.no_web:
                web_cands = search_web_orcid_candidates(snii_name, snii_inst, snii_dep, snii_sub)
                if web_cands:
                    w_flag, w_cand, w_reason, w_conf = call_llm_evaluator(snii_dict, web_cands, is_web=True)
                    if w_flag and w_cand:
                        matched_flag = True
                        matched_cand = w_cand
                        reason_str = w_reason
                        confidence_val = w_conf
                        is_web_match = True

            # --- 5. Registro y Persistencia de Resultados ---
            if matched_flag and matched_cand:
                final_orcid = matched_cand.get("orcid")
                final_oa_id = matched_cand.get("openalex_id")
                source_label = f"{matched_cand.get('source')} + LLM Verified" if is_web_match else f"{matched_cand.get('source')} + LLM Reranking"

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
                    "source": source_label,
                    "confidence": confidence_val,
                    "reason": reason_str,
                    "discarded_candidates": []
                }
                if is_web_match:
                    stats["web_matched"] += 1
                else:
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
                    "source": "Agotado (OpenAlex, ORCID Local, Web)",
                    "confidence": "NONE",
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
                print(f"   💾 Checkpoint [{stats['completados']}/{stats['total']} ({pct:.1f}%)] | AutoOA: {stats['auto_matched_clickhouse']} | AutoORCID: {stats['auto_matched_orcid']} | LLM: {stats['llm_matched']} | Web: {stats['web_matched']} | NoMatch: {stats['sin_match']} | T: {elapsed/60:.1f}m", flush=True)
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
    print(f"   • Auto-match OpenAlex: {stats['auto_matched_clickhouse']:,}", flush=True)
    print(f"   • Auto-match ORCID Local: {stats['auto_matched_orcid']:,}", flush=True)
    print(f"   • Resueltos con LLM Local: {stats['llm_matched']:,}", flush=True)
    print(f"   • Resueltos vía Web (ORCID/DDG) + LLM: {stats['web_matched']:,}", flush=True)
    print(f"   • Sin match confirmado: {stats['sin_match']:,}", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    main()
