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
import pandas as pd

# Cargar .env de la raíz
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
load_dotenv(env_path)
print(f"DEBUG: Cargando .env desde {env_path}")

# Configuración de LLM (usando el patrón del proyecto)
user = os.getenv("LLM_USER")
password = os.getenv("LLM_PASSWORD")
base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
model_name = os.getenv("LLM_MODEL", "local-model")

# Cache de detalles de ROR para evitar duplicar llamadas
ROR_CACHE = {}

def get_ror_details(ror_url):
    """Obtiene detalles adicionales de la API de ROR."""
    if not ror_url: return None
    ror_id = ror_url.replace("https://ror.org/", "").strip()
    if ror_id in ROR_CACHE:
        return ROR_CACHE[ror_id]
    
    print(f"      📡 Fetching ROR details: {ror_id}...")
    try:
        with httpx.Client(verify=False, timeout=20) as client:
            resp = client.get(f"https://api.ror.org/organizations/{ror_id}")
            if resp.status_code == 200:
                data = resp.json()
                # Extraemos solo lo relevante para ahorrar tokens
                details = {
                    "labels": [l.get('label') for l in data.get('labels', [])],
                    "aliases": data.get('aliases', []),
                    "types": data.get('types', []),
                    "relationships": [
                        {"type": r.get('type'), "label": r.get('label'), "id": r.get('id')}
                        for r in data.get('relationships', [])
                    ],
                    "status": data.get('status')
                }
                ROR_CACHE[ror_id] = details
                return details
    except Exception as e:
        print(f"      ⚠️ Error fetching ROR API: {e}")
    return None

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
    snii_entities = set()
    
    # 1. Intentar cargar desde Excel para cobertura TOTAL
    excel_path = 'SNII/Investigadores_vigentes_2025.xlsx'
    if os.path.exists(excel_path):
        print(f"   📊 Leyendo Excel: {excel_path}...")
        try:
            df = pd.read_excel(excel_path)
            # Normalizar nombres de columnas (quitar espacios extra si los hay)
            df.columns = [c.strip() for c in df.columns]
            
            # Usar las columnas identificadas
            inst_col = 'INSTITUCIÓN DE COMISIÓN'
            sub_col = 'DEPENDENCIA DE COMISIÓN'
            
            if inst_col in df.columns:
                for _, row in df.iterrows():
                    inst = str(row[inst_col]).strip() if pd.notna(row[inst_col]) else None
                    sub = str(row[sub_col]).strip() if pd.notna(row[sub_col]) else "SIN INFORMACIÓN"
                    if inst and inst != "nan":
                        snii_entities.add((inst, sub))
                print(f"   ✅ Extraídas {len(snii_entities)} entidades únicas del Excel.")
        except Exception as e:
            print(f"   ⚠️ Error leyendo Excel: {e}")

    # 2. Fallback/Complemento: Cargar desde JSON verificado si existe
    json_path = 'data/snii_llm_verified_matches.json'
    if os.path.exists(json_path):
        print(f"   📂 Leyendo JSON: {json_path}...")
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                snii_data = json.load(f)
                for r in snii_data:
                    inst = r.get('snii_institution')
                    sub = r.get('snii_subdependency') or "SIN INFORMACIÓN"
                    if inst:
                        snii_entities.add((inst, sub))
        except Exception as e:
            print(f"   ⚠️ Error leyendo JSON: {e}")

    with open('ROR/mexican_institutions_rors.json', 'r', encoding='utf-8') as f:
        ror_data = json.load(f)
        
    return sorted(list(snii_entities)), ror_data

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
        record = next(r for r in ror_list if r['name'] == match_name)
        
        # Enriquecer con API para los top 3 candidatos
        api_details = None
        if len(candidates) < 3:
            api_details = get_ror_details(record['ror'])

        candidates.append({
            "name": record['name'],
            "ror": record['ror'],
            "id": record['openalex_id'],
            "type": record['type'],
            "score": score,
            "lineage": record.get('lineage', []),
            "api_details": api_details
        })
    return candidates

def validate_with_llm(snii_inst, snii_sub, parent_candidates, child_candidates):
    # Formatear candidatos con detalles enriquecidos
    def format_cand(c):
        base = f"- {c['name']} | {c['ror']} | {c['type']}"
        if c.get('api_details'):
            det = c['api_details']
            extras = []
            if det.get('aliases'): extras.append(f"Aliases: {', '.join(det['aliases'])}")
            if det.get('relationships'):
                rels = [f"{r['type']}:{r['label']}" for r in det['relationships']]
                extras.append(f"Rels: {', '.join(rels)}")
            if extras:
                base += f" ({'; '.join(extras)})"
        return base

    prompt = f"""
Eres un experto en el sistema de investigación mexicano. Necesito mapear una entidad del SNII a su registro ROR/OpenAlex correcto.

ENTIDAD SNII:
- Institución: {snii_inst}
- Subdependencia: {snii_sub}

CANDIDATOS PARA LA INSTITUCIÓN ({snii_inst}):
{chr(10).join([format_cand(c) for c in parent_candidates[:5]])}

CANDIDATOS PARA LA SUBDEPENDENCIA ({snii_sub}):
{chr(10).join([format_cand(c) for c in child_candidates[:10]]) if child_candidates else "Sin subdependencia específica o sin candidatos."}

REGLAS CRÍTICAS:
1. Si la subdependencia es "SIN INFORMACIÓN", busca el mejor ROR entre los CANDIDATOS PARA LA INSTITUCIÓN.
2. Si existe una subdependencia específica (ej: Facultad, Instituto):
   - BUSCA ACTIVAMENTE un ROR que sea una sub-unidad (Facility o Education) y que tenga una relación de "parent" o "child" con la institución {snii_inst}.
   - NUNCA elijas el ROR de la institución padre (Universidad) si existe un ROR específico para la Facultad/Instituto solicitado.
   - Si la subdependencia es específica pero los candidatos solo muestran el ROR de la Universidad principal, pon "best_match_ror": null en lugar de asignar el padre.
3. Fíjate en los 'Aliases' y 'Rels' (Relationships). Si el candidato tiene un alias que coincide con la subdependencia, es muy probable que sea el correcto.

Responde ÚNICAMENTE en formato JSON con la siguiente estructura:
{{
  "best_match_ror": "url_o_null",
  "confidence": 0-100,
  "reason": "breve explicacion mencionando por qué coincide la jerarquía o el nombre"
}}
"""
    response = call_llm(prompt)
    try:
        clean_json = response.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except:
        return {"best_match_ror": None, "confidence": 0, "reason": "Error parsing LLM response"}

def main():
    print("🚀 Cargando datos...")
    unique_entities, ror_data = load_data()
    print(f"Entities to process: {len(unique_entities)}")

    mapping_file = os.path.join("data", "snii_ror_verified_matches.json")
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
        
        # Saltamos si ya existe y no se fuerza, A MENOS que queramos corregir errores conocidos
        # Por ejemplo, si el nombre del ROR es exactamente igual al de la institución padre 
        # pero tenemos una subdependencia específica.
        if key in mapping and mapping[key].get('best_match_ror') is not None:
             if not getattr(args, 'force', False):
                 continue

        print(f"🔍 Mapeando ({len(mapping)+1}/{len(unique_entities)}): {inst} | {sub}")
        
        # 1. Candidatos para la institución
        parent_candidates = find_ror_candidates(inst, ror_data)
        
        # 2. Candidatos para la subdependencia
        child_candidates = []
        if sub and sub != "SIN INFORMACIÓN":
            # Buscamos combinando sub + inst para desambiguar en la búsqueda fuzzy
            child_candidates = find_ror_candidates(f"{sub} {inst}", ror_data)
        
        # 3. Validación LLM
        result = validate_with_llm(inst, sub, parent_candidates, child_candidates)
        
        mapping[key] = result
        print(f"   -> Result: {result.get('best_match_ror')} ({result.get('confidence')}%)")
        
        if len(mapping) % 5 == 0:
            with open(mapping_file, 'w', encoding='utf-8') as f:
                json.dump(mapping, f, ensure_ascii=False, indent=2)
        
        time.sleep(1)

    with open(mapping_file, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"✅ Proceso completo. Mapeo guardado en {mapping_file}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Mapea SNII a ROR usando LLM")
    parser.add_argument("--force", action="store_true", help="Fuerza el re-procesamiento de mapeos existentes")
    args = parser.parse_args()
    
    main()
