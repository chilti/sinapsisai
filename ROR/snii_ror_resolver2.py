import os
import sys
import json
import time
import pandas as pd
import httpx
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Añadir path raíz
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))
# Añadir path de herramientas
sys.path.insert(0, str(_THIS.parent / "scripts" / "tools"))

from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client
from scripts.tools.match_snii_orcid import normalize_text

# Ruta manual al SNII para evitar errores de import
SNII_PATH = os.path.join(str(_THIS.parent), "data", "Investigadores_vigentes_2025.xlsx")

# Cargar .env
load_dotenv(_THIS.parent / '.env')

# --- Config LLM ---
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
if not base_url.endswith("/"): base_url += "/"
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
    vowel_map = {'a': '[aáàâä]', 'e': '[eéèêë]', 'i': '[iíìîï]', 'o': '[oóòôö]', 'u': '[uúùûü]'}
    regex = "".join(vowel_map.get(char, char) for char in text.lower())
    return f"(?i){regex}"

def get_search_keys(name: str):
    if not name or str(name).lower() in ["nan", "sin informacion", "sin información", "no aplica"]:
        return [], []
    import re
    acronyms = []
    match = re.search(r'\(([^)]+)\)', name)
    if match:
        acr = match.group(1).strip().upper()
        if 2 <= len(acr) <= 10: acronyms.append(acr)
    
    stop_words = ["de", "la", "el", "y", "en", "del", "las", "los", "para", "por", "con", "una", "un", 
                  "instituto", "centro", "nacional", "universidad", "investigacion", "cientifica", "tecnologica"]
    parts = [p.strip() for p in normalize_text(name).replace(',', ' ').replace('(', ' ').replace(')', ' ').split() if len(p) > 3 and p.lower() not in stop_words]
    return parts[:3], acronyms

def search_institutions(query_name: str, limit: int = 10):
    keys, acrs = get_search_keys(query_name)
    if not keys and not acrs: return []
    
    sub_clauses = []
    if acrs: sub_clauses.append(f"has(acronyms, '{acrs[0]}')")
    if keys:
        k_regexes = [get_accent_insensitive_regex(k) for k in keys]
        if len(k_regexes) >= 2:
            sub_clauses.append(f"(match(display_name, '{k_regexes[0]}') AND match(display_name, '{k_regexes[1]}'))")
        else:
            sub_clauses.append(f"match(display_name, '{k_regexes[0]}')")
    
    where_clause = " OR ".join(sub_clauses)
    query = f"""
    SELECT id, display_name, ror, type, country_code, city, state, parent_id, parent_name, acronyms, raw_data
    FROM rag.institutions_seed_mexico
    WHERE {where_clause}
    ORDER BY (country_code = 'MX') DESC
    LIMIT {limit * 3}
    """
    rows = ch_client.query(query).result_rows
    
    from Levenshtein import jaro_winkler
    results = []
    for r in rows:
        oa_id, disp_name, ror, itype, country, city, state, p_id, p_name, acronyms, raw_json = r
        score = jaro_winkler(normalize_text(query_name), normalize_text(disp_name))
        if acrs and any(a in acronyms for a in acrs): score = max(score, 0.95)
        if country != 'MX' and score < 0.9: score -= 0.1
        
        if score > 0.6:
            rels = []
            try:
                raw_data = json.loads(raw_json)
                # Extraer tanto asociados como relaciones directas
                for assoc in raw_data.get('associated_institutions', []):
                    rels.append(f"{assoc.get('relationship')}:{assoc.get('display_name')} ({assoc.get('id')})")
            except: pass

            results.append({
                "id": oa_id, "name": disp_name, "ror": ror, "type": itype,
                "country": country, "city": city, "state": state,
                "relationships": rels, "score": score, "raw_data": raw_json
            })
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:limit]

def resolve_rors_v2(limit_test=None, force=False):
    print("\n🚀 Iniciando Resolución ROR v2 (Jerárquica)...")
    
    df = pd.read_excel(SNII_PATH, sheet_name='4T_2025 (44,794)')
    df.columns = [str(c).strip() for c in df.columns]
    cols = df.columns.tolist()

    # Búsqueda robusta de columnas (con o sin acentos)
    inst_col = next((c for c in cols if 'INSTITUCION' in normalize_text(c).upper() and 'ACREDITACION' in normalize_text(c).upper()), None)
    dep_col = next((c for c in cols if 'DEPENDENCIA' in normalize_text(c).upper() and 'ACREDITACION' in normalize_text(c).upper()), None)
    sub_col = next((c for c in cols if 'SUBDEPENDENCIA' in normalize_text(c).upper() and 'ACREDITACION' in normalize_text(c).upper()), None)
    
    if not inst_col:
        print(f"❌ Error: No se encontró la columna de Institución. Columnas: {cols}")
        return

    print(f"📊 Columnas identificadas: Inst={inst_col}, Dep={dep_col}, Sub={sub_col}")
    
    output_path = os.path.join("data", "snii_ror_verified_matches_v2.json")
    results = {}
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f: results = json.load(f)

    # --- FASE 1: Resolver Raíces (Instituciones) ---
    root_names = sorted(df[inst_col].unique())
    if limit_test: root_names = root_names[:limit_test]

    print(f"📦 Fase 1: Resolviendo {len(root_names)} instituciones raíz...")
    
    for inst_name in root_names:
        if inst_name in results and not force: continue
        
        print(f"  🔍 Buscando Raíz: {inst_name}...")
        cands = search_institutions(inst_name)
        
        prompt = f"""Identifica el ROR y OpenAlex ID exactos para esta INSTITUCIÓN MEXICANA.
NOMBRE SNII: {inst_name}
CANDIDATOS:
{chr(10).join([f"{i+1}. {c['name']} | ROR: {c['ror']} | ID: {c['id']} | Tipo: {c['type']} | {c['city']}" for i, c in enumerate(cands)])}

Responde en JSON. IMPORTANTE: Los campos 'root_ror' y 'root_openalex_id' deben ser EXACTAMENTE alguno de los proporcionados en la lista de candidatos, o null si ninguno es correcto. NUNCA inventes o supongas IDs que no estén en la lista.
{{
    "root_ror": "url_o_null",
    "root_openalex_id": "url_o_null",
    "root_name": "nombre_oficial",
    "confidence": 0-100,
    "reason": "breve"
}}"""
        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            res_json = json.loads(resp.content.strip().replace('```json', '').replace('```', ''))
            results[inst_name] = {
                "root_info": res_json,
                "units": {}
            }
            # Guardar raw_data de la raíz elegida para Fase 2
            match_id = res_json.get('root_openalex_id')
            root_raw = next((c['raw_data'] for c in cands if c['id'] == match_id), None)
            results[inst_name]["root_info"]["raw_data"] = root_raw
            print(f"    ✅ Resuelto: {res_json['root_name']} ({res_json['confidence']}%)")
        except Exception as e:
            print(f"    ❌ Error: {e}")
        
        with open(output_path, "w", encoding="utf-8") as f: json.dump(results, f, indent=2, ensure_ascii=False)

    # --- FASE 2: Resolver Unidades (Dep/Sub) ---
    print("\n📦 Fase 2: Resolviendo dependencias y subdependencias...")
    
    def is_invalid(val):
        v = str(val).strip().upper()
        return v in ["SIN INFORMACION", "SIN INFORMACIÓN", "NO APLICA", "NAN", "", "NONE", "SIN ADSCRIPCIÓN"]

    # Obtener combinaciones únicas y filtrar por las raíces procesadas
    detail_entities = df[[inst_col, dep_col, sub_col]].drop_duplicates()
    detail_entities = detail_entities[detail_entities[inst_col].isin(root_names)]
    
    for _, row in detail_entities.iterrows():
        inst = str(row[inst_col]).strip()
        dep = str(row[dep_col]).strip()
        sub = str(row[sub_col]).strip()

        # Reglas de filtrado estrictas
        if is_invalid(dep): continue
        if normalize_text(dep) == normalize_text(inst): continue

        clean_sub = "SIN INFORMACIÓN" if is_invalid(sub) else sub
        unit_key = f"{dep} || {clean_sub}"
        
        if unit_key in results.get(inst, {}).get("units", {}) and not force: continue
        
        root_info = results.get(inst, {}).get("root_info", {})
        if not root_info or not root_info.get('root_openalex_id'): continue
        
        print(f"  🔍 Resolviendo Unidad: {inst} > {dep} > {clean_sub}...")
        
        assoc_cands = []
        exact_match = None
        
        # El nombre objetivo para el match es el nivel más profundo disponible
        target_name_for_matching = sub if not is_invalid(sub) else dep
        target_search = target_name_for_matching

        if root_info.get('raw_data'):
            try:
                from Levenshtein import jaro_winkler
                raw = json.loads(root_info['raw_data'])
                seen_ids = set()  # Inicializar ANTES de los loops

                # 1. Buscar en asociados directos (Childs/Parents)
                assocs = raw.get('associated_institutions', [])
                for a in assocs:
                    score = jaro_winkler(normalize_text(target_name_for_matching), normalize_text(a['display_name']))
                    a['score'] = score
                    seen_ids.add(a['id'])
                    if score > 0.99:    # Umbral estricto: evita FISICA == GEOFISICA
                        exact_match = a
                        break           # No seguir comparando tras match exacto
                    if score > 0.65:
                        assoc_cands.append(a)
                
                # 2. Si no hay match claro, buscar en la DB local hijos de esta raíz
                if not exact_match and len(assoc_cands) < 5:
                    from database.clickhouse_db import ch_client
                    root_id = root_info.get('root_openalex_id')
                    local_children = ch_client.query(f"""
                        SELECT display_name, id, ror, raw_data 
                        FROM rag.institutions_seed_mexico 
                        WHERE parent_id = '{root_id}'
                    """).result_rows
                    for lc_name, lc_id, lc_ror, lc_raw in local_children:
                        score = jaro_winkler(normalize_text(target_name_for_matching), normalize_text(lc_name))
                        if score > 0.99:    # Mismo umbral estricto
                            exact_match = {'display_name': lc_name, 'id': lc_id, 'ror': lc_ror, 'raw_data': lc_raw}
                            break
                        if score > 0.60:
                            assoc_cands.append({'display_name': lc_name, 'id': lc_id, 'ror': lc_ror, 'raw_data': lc_raw, 'score': score})
                
                # Ordenar y deduplicar candidatos para el LLM
                assoc_cands.sort(key=lambda x: x['score'], reverse=True)
                unique_cands = []
                for c in assoc_cands:
                    if c['id'] not in seen_ids:
                        unique_cands.append(c)
                        seen_ids.add(c['id'])
                assoc_cands = unique_cands[:7]
            except Exception as e: 
                print(f"      ⚠️ Error buscando asociados: {e}")

        if exact_match:
            print(f"    ✨ Match exacto en asociados del padre: {exact_match['display_name']}")
            results[inst]["units"][unit_key] = {
                "matched_ror": exact_match.get('ror'),
                "matched_openalex_id": exact_match.get('id'),
                "matched_name": exact_match.get('display_name'),
                "confidence": 100,
                "method": "associated_institutions_exact_match",
                "reason": "Coincidencia exacta encontrada en la lista de instituciones asociadas del padre."
            }
        else:
            general_cands = search_institutions(target_search + f" {inst}")
            prompt = f"""Identifica el ROR/ID de esta UNIDAD de {inst}.
INSTITUCIÓN PADRE: {root_info['root_name']} ({root_info['root_ror']})
UNIDAD SNII: {dep} | {clean_sub}

OPCIONES HIJAS ENCONTRADAS EN EL PADRE (OpenAlex):
{chr(10).join([f"- {c['display_name']} | ID: {c['id']} | ROR: {c['ror']}" for c in assoc_cands]) if assoc_cands else "Ninguna opción clara en asociados."}

OTRAS POSIBILIDADES ENCONTRADAS POR BÚSQUEDA GENERAL:
{chr(10).join([f"- {c['name']} | ID: {c['id']} | ROR: {c['ror']} | Rels: {str(c['relationships'][:1])}" for c in general_cands])}

INSTRUCCIONES:
1. Prioriza las "OPCIONES HIJAS" si alguna coincide razonablemente.
2. Si ninguna coincide, responde con matched_ror: null y matched_openalex_id: null.
3. NUNCA asignes el ROR de la Universidad principal a los campos 'matched'.
4. IMPORTANTE: 'matched_ror' y 'matched_openalex_id' deben ser de la lista de candidatos o null. NO INVENTES IDS.

Responde en JSON:
{{
    "matched_ror": "url_o_null",
    "matched_openalex_id": "url_o_null",
    "matched_name": "nombre_oficial",
    "confidence": 0-100,
    "method": "llm_hierarchical_validation",
    "reason": "explicación"
}}"""
            try:
                resp = llm.invoke([HumanMessage(content=prompt)])
                res_json = json.loads(resp.content.strip().replace('```json', '').replace('```', ''))
                results[inst]["units"][unit_key] = res_json
                print(f"    ✅ LLM: {res_json.get('matched_name') or 'No encontrado'} ({res_json['confidence']}%)")
            except Exception as e:
                print(f"    ❌ Error: {e}")

        with open(output_path, "w", encoding="utf-8") as f: json.dump(results, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    resolve_rors_v2(limit_test=args.limit, force=args.force)
