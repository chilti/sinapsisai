"""
Script para mapear instituciones de SNII a ROR.
Lógica:
1. Extraer nombres únicos (Institución, Subdependencia) de snii_llm_verified_matches.json.
2. Buscar candidatos en mexican_institutions_rors.json mediante fuzzy matching.
3. Usar LLM para validar cuál es el ROR correcto para la Institución y la Subdependencia.
4. Generar un archivo de mapeo snii_ror_map.json.
"""

import os
import json
import time
from thefuzz import fuzz, process
from dotenv import load_dotenv
import httpx

# Cargar .env de la raíz
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)
print(f"DEBUG: Cargando .env desde {env_path}")

# Configuración de LLM (usando el patrón del proyecto)
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
model_name = os.getenv("LLM_MODEL", "local-model")

if not base_url.endswith("/"): base_url += "/"
auth_url = base_url
if user and password:
    if "://" in base_url:
        proto, rest = base_url.split("://", 1)
        auth_url = f"{proto}://{user}:{password}@{rest}"

def call_llm(prompt):
    """Llamada simple al LLM para validación."""
    try:
        with httpx.Client(verify=False, timeout=60) as client:
            resp = client.post(
                f"{auth_url}chat/completions",
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                },
                headers={"Authorization": "Bearer lm-studio"}
            )
            resp.raise_for_status()
            return resp.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Error LLM: {e}")
        return None

def load_data():
    with open('data/snii_llm_verified_matches.json', 'r', encoding='utf-8') as f:
        snii_data = json.load(f)
    with open('ROR/mexican_institutions_rors.json', 'r', encoding='utf-8') as f:
        ror_data = json.load(f)
    return snii_data, ror_data

def get_unique_snii_entities(snii_data):
    entities = set()
    for r in snii_data:
        inst = r.get('snii_institution')
        sub = r.get('snii_subdependency')
        if inst:
            entities.add((inst, sub))
    return sorted(list(entities))

def find_ror_candidates(name, ror_list, limit=10):
    """Busca candidatos ROR por nombre."""
    names = [r['name'] for r in ror_list]
    matches = process.extract(name, names, scorer=fuzz.token_sort_ratio, limit=limit)
    
    candidates = []
    for match_name, score in matches:
        # Encontrar el record original
        # Usamos el primer match exacto por nombre
        record = next(r for r in ror_list if r['name'] == match_name)
        candidates.append({
            "name": record['name'],
            "ror": record['ror'],
            "id": record['openalex_id'],
            "type": record['type'],
            "score": score,
            "lineage": record.get('lineage', [])
        })
    return candidates

def validate_with_llm(snii_inst, snii_sub, ror_candidates):
    prompt = f"""
Eres un experto en el sistema de investigación mexicano. Necesito mapear una entidad del SNII a su registro ROR/OpenAlex correcto.

ENTIDAD SNII:
- Institución: {snii_inst}
- Subdependencia: {snii_sub}

CANDIDATOS ROR (Nombre | ROR | Tipo):
{chr(10).join([f"- {c['name']} | {c['ror']} | {c['type']}" for c in ror_candidates])}

Responde ÚNICAMENTE en formato JSON con la siguiente estructura:
{{
  "best_match_ror": "url_o_null",
  "confidence": 0-100,
  "reason": "breve explicacion"
}}
Si la subdependencia tiene su propio ROR (ej. un Instituto), elígelo. Si no, elige el de la institución padre.
"""
    response = call_llm(prompt)
    try:
        # Limpiar posible markdown del LLM
        clean_json = response.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except:
        return {"best_match_ror": None, "confidence": 0, "reason": "Error parsing LLM response"}

def main():
    print("🚀 Cargando datos...")
    snii_data, ror_data = load_data()
    unique_entities = get_unique_snii_entities(snii_data)
    print(f"Entities found: {len(unique_entities)}")

    mapping_file = 'ROR/snii_ror_mapping.json'
    mapping = {}
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            print(f"✅ Cargados {len(mapping)} mapeos previos.")
        except:
            print("⚠️ No se pudo cargar el mapeo previo, iniciando desde cero.")

    # Procesar todas las entidades
    for inst, sub in unique_entities:
        key = f"{inst} || {sub}"
        if key in mapping and mapping[key].get('best_match_ror') is not None:
             # Omitimos print para no saturar si ya existen
             continue

        print(f"🔍 Mapeando ({len(mapping)+1}/{len(unique_entities)}): {inst} | {sub}")
        
        # 1. Candidatos para la subdependencia (si existe)
        target = f"{sub} {inst}" if sub and sub != "SIN INFORMACIÓN" else inst
        candidates = find_ror_candidates(target, ror_data)
        
        # 2. Validación LLM
        result = validate_with_llm(inst, sub, candidates)
        
        mapping[key] = result
        print(f"   -> Result: {result.get('best_match_ror')} ({result.get('confidence')}%)")
        
        # Guardar progreso incrementalmente cada 5 registros para no perder trabajo
        if len(mapping) % 5 == 0:
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
        
        time.sleep(1)

    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"✅ Proceso completo. Mapeo guardado en {mapping_file}")

if __name__ == "__main__":
    main()
