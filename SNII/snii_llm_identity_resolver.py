"""
snii_llm_identity_resolver.py
─────────────────────────────
Resuelve la identidad de los investigadores del SNII 2025 contra múltiples
fuentes de datos externas (OpenAlex, ORCID dump, Neo4j local) mediante un
pipeline de búsqueda semántica + reranking con LLM.

Flujo principal:
  1. Por cada investigador en el Excel del SNII, genera un embedding semántico.
  2. Busca candidatos en:
       - OpenAlex Authors (ClickHouse local, búsqueda lexicográfica + Jaro-Winkler)
       - ORCID Dump via Qdrant ('orcid_authors_vec')
       - Neo4j / SIIA local via Qdrant ('local_authors')  [prioridad UNAM]
       - ClickHouse text-search fuzzy (fallback)
  3. Presenta los candidatos a un LLM para verificación y decisión final.
  4. Guarda resultados incrementales en data/snii_llm_verified_matches.json.
"""

import os
import sys
import json
import time
import pandas as pd
import httpx
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.messages import HumanMessage

# Añadir path raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.vector_store import QdrantStore
from match_snii_orcid import normalize_text, get_client as get_ch_client, get_orcid_client, SNII_PATH, CH_DB, CH_DB_ORCID

# Cargar .env
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

# --- Config MEX_KEYWORDS (para fallbacks Qdrant) ---
MEX_KEYWORDS = [
    "mexico", "mexic", "unam", "ipn", "cinvestav", "tecnologico", "autonoma", "itamb", "colmex",
    "buap", "uaslp", "udem", "itesm", "uam", "politecnico"
]

if os.path.exists(SNII_PATH):
    try:
        print("📡 Cargando instituciones desde SNII para expandir red de seguridad...")
        df_snii = pd.read_excel(SNII_PATH)
        instituciones = df_snii['INSTITUCIÓN DE ACREDITACIÓN'].dropna().unique().tolist()
        subdependencias = df_snii['SUBDEPENDENCIA DE ACREDITACIÓN'].dropna().unique().tolist()

        for ext_name in instituciones + subdependencias:
            clean_name = str(ext_name).lower().replace("'", "").strip()
            if len(clean_name) > 4:
                MEX_KEYWORDS.append(clean_name)

        MEX_KEYWORDS = list(set(MEX_KEYWORDS))
        print(f"✅ Red de seguridad expandida a {len(MEX_KEYWORDS)} términos clave.")
    except Exception as e:
        print(f"⚠️ No se pudo expandir MEX_KEYWORDS desde Excel: {e}")

# --- Config Embeddings ---
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
if not base_url.endswith("/"):
    base_url += "/"
model_name = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
auth_url = base_url
if user and password:
    if "://" in base_url:
        proto, rest = base_url.split("://", 1)
        auth_url = f"{proto}://{user}:{password}@{rest}"
    else:
        auth_url = f"http://{user}:{password}@{base_url}"

http_client = httpx.Client(verify=False, timeout=120)

embeddings_model = OpenAIEmbeddings(
    model=model_name,
    base_url=auth_url,
    api_key="lm-studio",
    http_client=http_client,
    check_embedding_ctx_length=False
)

# --- Config LLM ---
llm_model_name = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
llm = ChatOpenAI(
    model=llm_model_name,
    base_url=auth_url,
    api_key="lm-studio",
    http_client=http_client,
    temperature=0
)


def get_embeddings(texts: list, batch_size: int = 10) -> list:
    """Genera embeddings en batches con reintentos automáticos."""
    if not texts:
        return []
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = [str(t) if t else " " for t in texts[i:i + batch_size]]
        for attempt in range(5):
            try:
                embs = embeddings_model.embed_documents(batch)
                all_embeddings.extend(embs)
                break
            except Exception as e:
                wait = 10 * (attempt + 1)
                print(f"      ⚠️ Error embeddings (intento {attempt+1}/5): {e}. Reintentando en {wait}s...")
                time.sleep(wait)
        else:
            print(f"      ❌ Embeddings fallaron para batch {i}. Usando vector cero.")
            all_embeddings.extend([[0.0] * 768] * len(batch))
    return all_embeddings


def search_openalex_authors(name: str, institution: str, limit: int = 5) -> list:
    """Busca candidatos en la tabla de autores de OpenAlex en ClickHouse local.
    Retorna hasta `limit` autores con nombre, orcid, last_known_institution y scopus ids.
    """
    try:
        ch = get_ch_client()
        # Tomamos la primera palabra del apellido (antes de la coma) como llave de búsqueda
        search_term = normalize_text(name.split(',')[0].split()[0]).replace("'", "").replace("'", "")
        if len(search_term) < 3:
            return []

        query = f"""
        SELECT
            id,
            display_name,
            orcid,
            last_known_institution_name,
            ids
        FROM {CH_DB}.authors
        WHERE lower(display_name) LIKE '%{search_term.lower()}%'
        LIMIT {limit * 25}
        """
        rows = ch.query(query).result_rows

        from Levenshtein import jaro_winkler
        sorted_seed = " ".join(sorted([t for t in normalize_text(name).replace(',', ' ').split() if len(t) > 1]))

        scored = []
        for r in rows:
            openalex_id, disp_name, orcid_val, inst_name, ids_json = r[0], r[1], r[2], r[3], r[4]
            cand_norm = " ".join(sorted([t for t in normalize_text(str(disp_name)).replace(',', ' ').split() if len(t) > 1]))
            ns = jaro_winkler(sorted_seed, cand_norm)
            if ns > 0.75:
                # Extraer Scopus IDs del campo ids (JSON) si están disponibles
                scopus_ids = []
                try:
                    ids_data = json.loads(ids_json) if isinstance(ids_json, str) else (ids_json or {})
                    scopus_raw = ids_data.get('scopus') or []
                    if isinstance(scopus_raw, str):
                        scopus_ids = [scopus_raw]
                    elif isinstance(scopus_raw, list):
                        scopus_ids = scopus_raw
                except Exception:
                    pass
                scored.append({
                    "openalex_id": openalex_id,
                    "name": disp_name,
                    "orcid": orcid_val or None,
                    "inst": inst_name or "",
                    "scopus_ids": scopus_ids,
                    "score": ns
                })

        scored.sort(key=lambda x: x['score'], reverse=True)
        return scored[:limit]
    except Exception as e:
        print(f"      ⚠️ Error buscando en OpenAlex authors ClickHouse: {e}")
        return []


def resolve_snii_identities(limit_test=None, target_name=None):
    """Pipeline principal: SNII → candidatos multi-fuente → verificación LLM → JSON de resultados.

    Args:
        limit_test:   Si se indica, procesa solo los primeros N registros del padrón.
        target_name:  Si se indica, filtra el padrón por nombre (búsqueda parcial,
                      insensible a mayúsculas). Permite pasar un apellido, nombre parcial
                      o cualquier fragmento del nombre completo del investigador.
    """
    print("\n🚀 Resolviendo identidades SNII con LLM (búsqueda semántica + reranking)...")

    df = pd.read_excel(SNII_PATH)

    if target_name:
        mask = df['NOMBRE DEL INVESTIGADOR'].str.contains(target_name, case=False, na=False)
        df = df[mask].reset_index(drop=True)
        if df.empty:
            print(f"   ⚠️  No se encontró ningún investigador que coincida con '{target_name}' en el padrón SNII.")
            return
        print(f"   🔍 Modo búsqueda individual: {len(df)} registro(s) encontrado(s) para '{target_name}'.")

    if limit_test and not target_name:
        df = df.head(limit_test)
        print(f"   Modo prueba: procesando solo {limit_test} registros.")

    local_store = QdrantStore(collection_name="local_authors")
    orcid_store = QdrantStore(collection_name="orcid_authors_vec")

    name_col = 'NOMBRE DEL INVESTIGADOR'
    inst_col = 'INSTITUCIÓN DE ACREDITACIÓN'
    dep_inst_col = 'DEPENDENCIA DE ACREDITACIÓN'
    sub_inst_col = 'SUBDEPENDENCIA DE ACREDITACIÓN'

    output_path = os.path.join("data", "snii_llm_verified_matches.json")
    verified_results = []
    lookup = {}  # (name, inst, sub) -> index
    processed_in_this_run = set()

    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                temp_data = json.load(f)
                # Deduplicar al cargar
                seen_keys = set()
                for r in temp_data:
                    key = (r["snii_author"], r.get("snii_institution", ""), r.get("snii_subdependency", ""))
                    if key not in seen_keys:
                        lookup[key] = len(verified_results)
                        verified_results.append(r)
                        seen_keys.add(key)
            print(f"   Cargados {len(verified_results)} registros previos deduplicados.")
        except Exception as e:
            print(f"   ⚠️ No se pudo cargar progreso previo: {e}")

    for idx, row in df.iterrows():
        snii_name = str(row[name_col]).strip()

        raw_inst = str(row[inst_col]).strip() if pd.notna(row[inst_col]) else ""
        raw_dep = str(row[dep_inst_col]).strip() if pd.notna(row[dep_inst_col]) else ""
        raw_sub = str(row[sub_inst_col]).strip() if pd.notna(row[sub_inst_col]) else ""

        if raw_inst.upper() in ["SIN INSTITUCIÓN", "SIN INSTITUCION"]:
            final_inst = "SIN INSTITUCIÓN"
            final_sub = "NO APLICA"
        elif raw_sub.upper() in ["SIN INFORMACION", "SIN INFORMACIÓN", ""]:
            final_inst = raw_inst
            final_sub = raw_dep if raw_dep else raw_sub
        else:
            final_inst = raw_inst
            final_sub = raw_sub

        key = (snii_name, final_inst, final_sub)

        # Evitar procesar lo mismo dos veces en la misma corrida (duplicados en Excel)
        if key in processed_in_this_run:
            continue

        # Si ya existe match confirmado, saltar
        if key in lookup:
            existing_record = verified_results[lookup[key]]
            if existing_record.get("match") is True:
                processed_in_this_run.add(key)
                continue

        snii_info = f"Nombre: {snii_name} | Institución: {final_inst} | Subdependencia: {final_sub}"

        print(f"   [{idx+1}/{len(df)}] Verificando: {snii_name}...")

        # Obtener embedding del autor SNII
        emb = get_embeddings([snii_info])[0]

        all_candidates = []
        is_unam = any(k in final_inst.lower() for k in ['unam', 'nacional autonoma de mexico', 'nacional autónoma de méxico'])

        # ── OpenAlex Authors (Prioridad Alta) ─────────────────────────────────
        openalex_candidates = search_openalex_authors(snii_name, final_inst, limit=5)
        oa_scopus_map = {}  # openalex_id -> scopus_ids (para usar después si hay match)
        for c in openalex_candidates:
            oa_scopus_map[c['openalex_id']] = c.get('scopus_ids', [])
            all_candidates.append({
                "source": "OpenAlex DB Local",
                "openalex_id": c['openalex_id'],
                "name": c['name'],
                "orcid": c['orcid'],
                "affiliation": c['inst'],
                "scopus_ids": c.get('scopus_ids', []),
                "score_vec": c['score']
            })

        # Saltamos Qdrant si ya tenemos suficientes candidatos de calidad de OpenAlex
        high_quality_oa = [c for c in openalex_candidates if c['score'] >= 0.95]

        if is_unam and not high_quality_oa:
            # UNAM: Priorizar local via Qdrant (ahí está SIIA)
            local_candidates = local_store.search(emb, limit=5)
            orcid_candidates = orcid_store.search(emb, limit=2)
            for c in local_candidates:
                all_candidates.append({
                    "source": "Local (Neo4j/SIIA)",
                    "name": c.get("name"),
                    "orcid": c.get("orcid"),
                    "affiliation": c.get("affiliation"),
                    "score_vec": c.get("score")
                })
            for c in orcid_candidates:
                all_candidates.append({
                    "source": "ORCID Dump (Qdrant)",
                    "name": c.get("name"),
                    "orcid": c.get("orcid"),
                    "affiliation": c.get("affiliation"),
                    "score_vec": c.get("score")
                })
        elif not high_quality_oa:

            # Resto del país: ORCID Qdrant + ClickHouse SQL Directo
            orcid_candidates = orcid_store.search(emb, limit=5)
            for c in orcid_candidates:
                all_candidates.append({
                    "source": "ORCID Dump (Qdrant)",
                    "name": c.get("name"),
                    "orcid": c.get("orcid"),
                    "affiliation": c.get("affiliation"),
                    "score_vec": c.get("score")
                })

            # ClickHouse SQL Fuzzy Fallback
            try:
                ch_client = get_orcid_client()
                parts = snii_name.replace(',', ' ').strip().split()
                if ',' in snii_name:
                    search_term = normalize_text(snii_name.split(',')[0].split()[0])
                elif not high_quality_oa:
                    search_term = parts[0]
                    common_names = ['juan', 'jose', 'maria', 'ana', 'luis', 'carlos', 'martha', 'rosa', 'pedro', 'jesus']
                    if search_term in common_names and len(parts) > 1:
                        search_term = parts[-1]

                t_esc = search_term.strip().replace("'", "").lower().replace("'", "''")

                if len(t_esc) >= 3:
                    # Verificar si la base de datos de ORCID existe en este servidor
                    db_exists = ch_client.query(f"SELECT count() FROM system.databases WHERE name = '{CH_DB_ORCID}'").result_rows[0][0]
                    if db_exists:
                        query = f"SELECT orcid, given_names, family_name, credit_name, last_affiliation FROM {CH_DB_ORCID}.orcid_records WHERE (lower(family_name) LIKE '%{t_esc}%' OR lower(credit_name) LIKE '%{t_esc}%') LIMIT 20"
                        res = ch_client.query(query).result_rows
                    else:
                        print(f"      ℹ️  Base de datos {CH_DB_ORCID} no encontrada en este servidor. Saltando búsqueda fuzzy de ORCID.")
                        res = []

                    from Levenshtein import jaro_winkler
                    sorted_seed = " ".join(sorted([t for t in normalize_text(snii_name).replace(',', ' ').split() if len(t) > 1]))

                    scored_cands = []
                    for r in res:
                        fn, gn, cn, aff, orc = str(r[2] or ''), str(r[1] or ''), str(r[3] or ''), str(r[4] or ''), r[0]
                        sorted_ch = " ".join(sorted([t for t in normalize_text(f"{gn} {fn}").replace(',', ' ').split() if len(t) > 1]))
                        ns = jaro_winkler(sorted_seed, sorted_ch)
                        if cn:
                            ns = max(ns, jaro_winkler(sorted_seed, " ".join(sorted([t for t in normalize_text(cn).replace(',', ' ').split() if len(t) > 1]))))
                        if ns > 0.8:
                            scored_cands.append({"score": ns, "name": f"{gn} {fn}".strip() if not cn else cn, "orcid": orc, "aff": aff})

                    scored_cands.sort(key=lambda x: x['score'], reverse=True)
                    for c in scored_cands[:4]:
                        if not any(a['orcid'] == c['orcid'] for a in all_candidates):
                            all_candidates.append({"source": "ClickHouse Text Search", "name": c['name'], "orcid": c['orcid'], "affiliation": c['aff'], "score_vec": c['score']})
            except Exception as e:
                print(f"      ⚠️ Error consultando ClickHouse text search: {e}")

        # Preparar Prompt para el LLM
        candidates_str = ""
        for i, cand in enumerate(all_candidates):
            candidates_str += f"{i+1}. [{cand['source']}] Nombre: {cand['name']} | ORCID: {cand['orcid']} | Afiliación: {cand['affiliation']}\n"

        prompt = f"""Eres un experto investigador bibliográfico. Tu tarea es identificar si alguno de los candidatos recuperados coincide exactamente con el investigador del SNII.

Investigador SNII buscado:
{snii_info}

Candidatos potenciales:
{candidates_str}

Instrucciones vitales:
1. Analiza el nombre (variaciones por apellidos compuestos, omisiones de nombre central, apodos, etc).
2. Analiza la afiliación desglosada en Nivel 1 (Institución) y Nivel 2 (Subdependencia).
3. ATENCIÓN: Si el investigador SNII indica 'Institución: SIN INSTITUCIÓN', DEBES IGNORAR por completo las afiliaciones de los candidatos y realizar el match 100% evaluando la compatibilidad de los nombres. ¡No penalices al candidato por tener una institución registrada en ORCID si al SNII le falta el dato!
4. Si crees que hay coincidencia segura, responde con el número del candidato y su ORCID.
5. No respondas con "NINGUNO" si hay dudas; mejor marca "match": false.
6. Requisito de formato de salida estricto: JSON plano {{
    "match": true/false, 
    "candidate_index": int/null, 
    "orcid": "...", 
    "reason": "breve justificación",
    "discarded_candidates": [
        {{"index": int, "name": "...", "orcid": "...", "reason": "razón breve del descarte"}}
    ]
}}. No agregues markdown de bloques de código.

Respuesta:"""

        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            res_text = response.content.strip()
            # Limpiar posibles bloques de código
            if "```json" in res_text:
                res_text = res_text.split("```json")[1].split("```")[0].strip()

            res_json = json.loads(res_text)

            result_entry = {
                "snii_author": snii_name,
                "snii_institution": final_inst,
                "snii_subdependency": final_sub,
                "match": False,
                "matched_author": None,
                "matched_orcid": None,
                "reason": res_json.get("reason", "No match"),
                "discarded_candidates": res_json.get("discarded_candidates", []),
                "source": None
            }

            if res_json.get("match"):
                m_idx = res_json.get("candidate_index")
                if m_idx and 1 <= m_idx <= len(all_candidates):
                    final_match = all_candidates[m_idx - 1]
                    confirmed_orcid = res_json.get("orcid") or final_match.get('orcid')

                    # Extraer Scopus IDs: Prioridad CANDIDATO (OpenAlex), luego FALLBACK REMOTE
                    scopus_ids = final_match.get('scopus_ids') or []

                    if not scopus_ids and confirmed_orcid and str(confirmed_orcid).lower() != 'none':
                        clean_orcid = str(confirmed_orcid).replace('https://orcid.org/', '').strip()
                        if not scopus_ids:
                            try:
                                ch_remote = get_ch_client()
                                col_to_get = "ids"
                                q_remote = f"SELECT {col_to_get} FROM {CH_DB}.authors WHERE orcid = '{clean_orcid}' LIMIT 1"
                                rows = ch_remote.query(q_remote).result_rows
                                if rows and rows[0][0]:
                                    ext = json.loads(rows[0][0]) if isinstance(rows[0][0], str) else rows[0][0]
                                    raw = ext.get('Scopus') or ext.get('scopus') or []
                                    scopus_ids = [raw] if isinstance(raw, str) else raw
                            except Exception as se:
                                print(f"      ⚠️ No se pudieron extraer Scopus IDs de Remote: {se}")

                    print(f"      ✅ MATCH CONFIRMADO por LLM: [SNII] {snii_name} ≈ [Match] {final_match['name']} ({confirmed_orcid})")
                    result_entry.update({
                        "match": True,
                        "matched_author": final_match['name'],
                        "matched_orcid": confirmed_orcid,
                        "matched_openalex_id": final_match.get('openalex_id'),
                        "scopus_ids": scopus_ids,
                        "source": final_match['source']
                    })
            else:
                print(f"      ❌ NINGUNO: No se encontró match para {snii_name}")

            # Actualizar o Añadir
            if key in lookup:
                verified_results[lookup[key]] = result_entry
            else:
                lookup[key] = len(verified_results)
                verified_results.append(result_entry)

            processed_in_this_run.add(key)

            # Guardado incremental cada 10 registros
            if (idx + 1) % 10 == 0:
                os.makedirs("data", exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(verified_results, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"      ⚠️ Error consultando LLM para {snii_name}: {e}")
            error_entry = {
                "snii_author": snii_name,
                "snii_institution": final_inst,
                "snii_subdependency": final_sub,
                "match": False,
                "matched_author": None,
                "matched_orcid": None,
                "reason": f"Error en LLM: {e}",
                "source": None
            }
            if key in lookup:
                verified_results[lookup[key]] = error_entry
            else:
                lookup[key] = len(verified_results)
                verified_results.append(error_entry)

            processed_in_this_run.add(key)

            # Guardado inmediato para no perder progreso ante interrupciones
            os.makedirs("data", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(verified_results, f, ensure_ascii=False, indent=2)

    # Guardado final
    os.makedirs("data", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(verified_results, f, ensure_ascii=False, indent=2)

    print(f"\n✨ Resolución de identidades completada. {len(verified_results)} registros guardados en {output_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Resuelve identidades SNII contra OpenAlex/ORCID usando LLM.")
    parser.add_argument(
        "--limit",
        type=int,
        help="Límite de registros del padrón completo para pruebas (opcional)."
    )
    parser.add_argument(
        "--name",
        type=str,
        help=(
            "Filtra el padrón SNII por nombre de investigador (búsqueda parcial, "
            "insensible a mayúsculas). Ejemplo: --name 'GARCIA' o --name 'Maria Elena'."
        )
    )
    args = parser.parse_args()

    resolve_snii_identities(limit_test=args.limit, target_name=args.name)
