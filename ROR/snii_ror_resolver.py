"""
snii_ror_resolver.py
─────────────────────────────
Resuelve el identificador ROR para las instituciones y subdependencias del SNII 2025.
Utiliza un pipeline de búsqueda batch en ClickHouse (sobre la tabla optimizada institutions_seed_mexico)
y verificación con LLM para manejar la jerarquía institucional.
"""

import os
import sys
import json
import time
import pandas as pd
import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Añadir path raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore
from database.vector_store import QdrantStore
from SNII.match_snii_orcid import normalize_text, get_client as get_ch_client, SNII_PATH, CH_DB

# Cargar .env
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)

# --- Config LLM ---
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
if not base_url.endswith("/"):
    base_url += "/"
model_name = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")

auth_url = base_url
if user and password:
    if "://" in base_url:
        proto, rest = base_url.split("://", 1)
        auth_url = f"{proto}://{user}:{password}@{rest}"

http_client = httpx.Client(verify=False, timeout=120)

llm = ChatOpenAI(
    model=model_name,
    base_url=auth_url,
    api_key="lm-studio",
    http_client=http_client,
    temperature=0
)

def get_accent_insensitive_regex(text: str) -> str:
    """Genera una regex para ClickHouse que ignora acentos y es case-insensitive."""
    vowel_map = {
        'a': '[aáàâä]', 'e': '[eéèêë]', 'i': '[iíìîï]', 
        'o': '[oóòôö]', 'u': '[uúùûü]'
    }
    regex = ""
    for char in text.lower():
        regex += vowel_map.get(char, char)
    return f"(?i){regex}"


def get_search_keys(name: str):
    """Extrae palabras clave y acrónimos para búsqueda en ClickHouse."""
    if not name or str(name).lower() in ["nan", "sin informacion", "sin información", "no aplica"]:
        return [], []
    
    import re
    acronyms = []
    # Extraer acrónimo si existe en paréntesis: "INSTITUTO ... (INAOE)"
    match = re.search(r'\(([^)]+)\)', name)
    if match:
        acr = match.group(1).strip().upper()
        if 2 <= len(acr) <= 10: # Longitud razonable para acrónimo
            acronyms.append(acr)
    
    # Filtrar palabras comunes que generan mucho ruido
    stop_words = ["de", "la", "el", "y", "en", "del", "las", "los", "para", "por", "con", "una", "un", 
                  "instituto", "centro", "nacional", "universidad", "investigacion", "cientifica", "tecnologica"]
    parts = [p.strip() for p in normalize_text(name).replace(',', ' ').replace('(', ' ').replace(')', ' ').split() if len(p) > 3 and p.lower() not in stop_words]
    return parts[:3], acronyms

def search_institutions_batch(names_info: list, limit_per_name: int = 10) -> dict:
    """Busca candidatos en ClickHouse para un lote de nombres de instituciones.
    names_info: lista de diccionarios {query_name, keys}
    """
    if not names_info:
        return {}
    
    try:
        ch = get_ch_client()
        clauses = []
        for info in names_info:
            keys = info['keys']
            acrs = info.get('acrs', [])
            
            sub_clauses = []
            if acrs:
                # Búsqueda por acrónimo exacto
                sub_clauses.append(f"has(acronyms, '{acrs[0]}')")
            
            if keys:
                # Búsqueda por Regex insensitivo a acentos
                k_regexes = [get_accent_insensitive_regex(k) for k in keys]
                if len(k_regexes) >= 2:
                    sub_clauses.append(f"(match(display_name, '{k_regexes[0]}') AND match(display_name, '{k_regexes[1]}'))")
                else:
                    sub_clauses.append(f"match(display_name, '{k_regexes[0]}')")
            
            if sub_clauses:
                clauses.append(f"({' OR '.join(sub_clauses)})")
        
        if not clauses:
            return {info['query_name']: [] for info in names_info}

        where_clause = " OR ".join(clauses)
        
        # Consultar la tabla semilla optimizada priorizando México
        query = f"""
        SELECT id, display_name, ror, type, country_code, city, state, parent_id, parent_name, acronyms, raw_data
        FROM {CH_DB}.institutions_seed_mexico
        WHERE {where_clause}
        ORDER BY (country_code = 'MX') DESC
        LIMIT {len(names_info) * limit_per_name * 5}
        """
        rows = ch.query(query).result_rows
        
        from Levenshtein import jaro_winkler
        results_map = {info['query_name']: [] for info in names_info}
        
        for r in rows:
            oa_id, disp_name, ror, itype, country, city, state, p_id, p_name, acronyms, raw_json = r
            cand_norm = normalize_text(disp_name)
            
            for info in names_info:
                query_name = info['query_name']
                query_norm = normalize_text(query_name)
                
                # Scoring simple
                score = jaro_winkler(query_norm, cand_norm)
                
                # Priorizar acrónimos en el score
                if info.get('acrs') and any(a in acronyms for a in info['acrs']):
                    score = max(score, 0.95)
                
                # Penalizar si no es de México a menos que el score sea muy alto
                if country != 'MX' and score < 0.9:
                    score -= 0.1

                if score > 0.65:
                    # Parsear relaciones para el LLM
                    rels = []
                    try:
                        raw_data = json.loads(raw_json)
                        for rel in raw_data.get('relationships', []):
                            rels.append(f"{rel.get('type')}:{rel.get('label')} ({rel.get('id')})")
                    except: pass

                    results_map[query_name].append({
                        "id": oa_id,
                        "name": disp_name,
                        "ror": ror,
                        "type": itype,
                        "country": country,
                        "city": city,
                        "state": state,
                        "parent_id": p_id,
                        "parent_name": p_name,
                        "relationships": rels,
                        "score": score
                    })
        
        # Sort and limit
        for name in results_map:
            results_map[name].sort(key=lambda x: x['score'], reverse=True)
            results_map[name] = results_map[name][:limit_per_name]
                
        return results_map
    except Exception as e:
        print(f"      ⚠️ Error en búsqueda batch ClickHouse: {e}")
        return {info['query_name']: [] for info in names_info}

def resolve_rors(limit_test=None, force=False):
    print("\n🚀 Resolviendo RORs de SNII con LLM + ClickHouse Batch...")

    # 1. Cargar Padrón y extraer entidades únicas (Detalladas)
    df = pd.read_excel(SNII_PATH)
    inst_col = 'INSTITUCIÓN DE ACREDITACIÓN'
    dep_col = 'DEPENDENCIA DE ACREDITACIÓN'
    sub_col = 'SUBDEPENDENCIA DE ACREDITACIÓN'
    df.columns = [c.strip() for c in df.columns]
    
    # Entidades detalladas (Inst || Dep || Sub)
    detail_entities = df[[inst_col, dep_col, sub_col]].drop_duplicates()
    
    # Entidades raíz (Solo Institución) para asegurar el Parent ROR
    root_entities = pd.DataFrame({
        inst_col: df[inst_col].unique(),
        dep_col: "SIN INFORMACIÓN",
        sub_col: "SIN INFORMACIÓN"
    })
    
    entities_df = pd.concat([detail_entities, root_entities]).drop_duplicates().reset_index(drop=True)
    
    if limit_test:
        entities_df = entities_df.head(limit_test)
    
    print(f"📊 Se identificaron {len(entities_df)} entidades a resolver (incluyendo instituciones raíz).")

    output_path = os.path.join("data", "snii_ror_verified_matches.json")
    verified_results = {}
    
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                verified_results = json.load(f)
            print(f"   Cargados {len(verified_results)} mapeos previos.")
        except Exception as e:
            print(f"   ⚠️ No se pudo cargar progreso previo: {e}")

    # 2. Bucle por lotes
    batch_size = 20
    rows_list = list(entities_df.iterrows())
    
    for b_idx in range(0, len(rows_list), batch_size):
        chunk = rows_list[b_idx : b_idx + batch_size]
        
        # Preparar info para búsqueda batch
        batch_query_info = []
        entity_map = {} # (inst, sub) -> query_names
        
        for _, row in chunk:
            inst = str(row[inst_col]).strip()
            dep = str(row[dep_col]).strip() if pd.notna(row[dep_col]) else ""
            sub = str(row[sub_col]).strip() if pd.notna(row[sub_col]) else ""
            
            key = f"{inst} || {dep} || {sub}"
            
            if key in verified_results and not force:
                continue
                
            # 1. Agregamos institución al batch
            if inst not in [q['query_name'] for q in batch_query_info]:
                keys, acrs = get_search_keys(inst)
                batch_query_info.append({'query_name': inst, 'keys': keys, 'acrs': acrs})
            
            # 2. Agregamos dependencia al batch si es específica
            if dep and dep.upper() not in ["SIN INFORMACIÓN", "SIN INFORMACION", "NO APLICA", "NAN", inst.upper()]:
                dep_query = f"{dep} {inst}"
                if dep_query not in [q['query_name'] for q in batch_query_info]:
                    keys, acrs = get_search_keys(dep)
                    batch_query_info.append({'query_name': dep_query, 'keys': keys, 'acrs': acrs})

            # 3. Agregamos subdependencia al batch si es específica
            if sub and sub.upper() not in ["SIN INFORMACIÓN", "SIN INFORMACION", "NO APLICA", "NAN", inst.upper(), dep.upper()]:
                sub_query = f"{sub} {inst}"
                if sub_query not in [q['query_name'] for q in batch_query_info]:
                    keys, acrs = get_search_keys(sub)
                    batch_query_info.append({'query_name': sub_query, 'keys': keys, 'acrs': acrs})
            
            entity_map[key] = (inst, dep, sub)

        if not batch_query_info:
            continue

        print(f"\n📦 Consultando lote de {len(batch_query_info)} nombres en ClickHouse...")
        batch_results = search_institutions_batch(batch_query_info)

        # 3. Procesar cada entidad del lote con el LLM
        for key, (inst, dep, sub) in entity_map.items():
            print(f"🔍 Verificando: {inst} | {dep} | {sub}...")
            
            # Candidatos del padre (Institución)
            parent_cands = batch_results.get(inst, [])
            
            # Candidatos de la dependencia
            dep_query = f"{dep} {inst}"
            dep_cands = batch_results.get(dep_query, [])

            # Candidatos del hijo (Subdependencia)
            sub_query = f"{sub} {inst}"
            child_cands = batch_results.get(sub_query, [])

            # Mostrar candidatos en log
            print(f"      🔎 {len(parent_cands)} candidatos para Institución")
            for i, c in enumerate(parent_cands[:2]):
                print(f"         {i+1}. {c['name']} ({c['type']})")
            
            if dep_cands:
                print(f"      🔎 {len(dep_cands)} candidatos para Dependencia")
                for i, c in enumerate(dep_cands[:2]):
                    print(f"         {i+1}. {c['name']} ({c['type']})")

            if child_cands:
                print(f"      🔎 {len(child_cands)} candidatos para Subdependencia")
                for i, c in enumerate(child_cands[:2]):
                    print(f"         {i+1}. {c['name']} ({c['type']})")
            
            # Formatear para el LLM
            def format_cands(cands):
                lines = []
                for i, c in enumerate(cands):
                    rel_str = f" | Rels: {', '.join(c['relationships'][:3])}" if c['relationships'] else ""
                    parent_str = f" | Padre: {c['parent_name']} ({c['parent_id']})" if c.get('parent_name') else ""
                    lines.append(f"{i+1}. {c['name']} | OpenAlexID: {c['id']} | ROR: {c['ror']} | Tipo: {c['type']}{parent_str} | Ubicación: {c['city']}, {c['state']}{rel_str}")
                return "\n".join(lines) if lines else "Ninguno encontrado."

            prompt = f"""Eres un experto en el ecosistema de investigación de México. Tu tarea es asignar el ROR y el OpenAlex ID correcto a una institución del SNII.

ENTIDAD SNII:
- Institución: {inst}
- Dependencia: {dep}
- Subdependencia: {sub}

CANDIDATOS PARA LA INSTITUCIÓN:
{format_cands(parent_cands)}

CANDIDATOS PARA LA DEPENDENCIA:
{format_cands(dep_cands)}

CANDIDATOS PARA LA SUBDEPENDENCIA:
{format_cands(child_cands)}

INSTRUCCIONES:
1. Identifica el ROR y el OpenAlex ID más específicos (Subdependencia > Dependencia > Institución).
2. REGLA DE ORO: Si la dependencia o subdependencia son específicas pero NO encuentras un candidato que coincida con ellas, debes poner "matched_ror": null y "matched_openalex_id": null. NUNCA asignes el ID de la Universidad principal a los campos 'matched' si la unidad específica no fue encontrada.
3. El 'Parent ROR' / 'Parent OpenAlex ID' siempre debe ser el de la Universidad o Institución principal (ej: UNAM, IPN) identificada, independientemente de si encontraste la subdependencia o no.
4. Si un candidato tiene OpenAlex ID pero no tiene ROR, identifícalo de todos modos y deja el ROR como null.
5. Responde únicamente en JSON:
{{
    "parent_ror": "url_o_null",
    "parent_openalex_id": "url_o_null",
    "parent_name": "nombre_oficial_universidad",
    "matched_ror": "url_o_null",
    "matched_openalex_id": "url_o_null",
    "matched_name": "nombre_oficial_especifico_o_null",
    "confidence": 0-100,
    "is_subdependency_match": true/false,
    "reason": "explicación breve (ej: 'Se identificó la UNAM como padre, pero no hay registro específico para la Facultad de Ciencias')"
}}
"""
            try:
                response = llm.invoke([HumanMessage(content=prompt)])
                res_text = response.content.strip()
                if "```json" in res_text:
                    res_text = res_text.split("```json")[1].split("```")[0].strip()
                res_json = json.loads(res_text)
                
                verified_results[key] = res_json
                match_name = res_json.get('matched_name') or res_json.get('parent_name') or "Ninguno"
                print(f"      ✅ OK: {match_name} ({res_json.get('confidence')}%)")
                print(f"         📝 Razón: {res_json.get('reason')}")
            except Exception as e:
                print(f"      ❌ Error LLM: {e}")

        # Guardado incremental
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(verified_results, f, ensure_ascii=False, indent=2)

    print(f"\n✨ Proceso completado. Resultados en {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Resuelve RORs de SNII.")
    parser.add_argument("--limit", type=int, help="Límite de registros para pruebas.")
    parser.add_argument("--force", action="store_true", help="Fuerza re-procesamiento.")
    args = parser.parse_args()

    resolve_rors(limit_test=args.limit, force=args.force)
