import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Añadir path raíz
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv()

from database.knowledge_graph import Neo4jGraphStore

# Configuración
JSON_PATH = 'data/snii_llm_verified_matches.json'

def recover():
    print("🧬 Iniciando recuperación de cache desde Neo4j...")
    gs = Neo4jGraphStore()
    
    # Query para traer académicos SNII con su jerarquía
    # Buscamos el camino desde el académico hasta la institución raíz
    query = """
    MATCH (a:Academic {is_snii: true})-[:AFFILIATED_TO]->(e)
    OPTIONAL MATCH (e)-[:PART_OF*0..]->(i:Institution)
    RETURN 
        a.name AS name,
        a.openalex_id AS oa_id,
        a.orcid AS orcid,
        a.entidad_final AS ent_final,
        e.name AS direct_entity,
        i.name AS root_inst
    """
    
    recovered_data = []
    seen_keys = set()

    with gs.driver.session() as session:
        results = session.run(query)
        for r in results:
            name = r["name"]
            oa_id = r["oa_id"]
            orcid = r["orcid"]
            inst = r["root_inst"] or r["direct_entity"] # Fallback si no hay path a Institution
            sub = r["direct_entity"]
            
            # Formatear como el JSON original
            entry = {
                "snii_author": name,
                "snii_institution": inst,
                "snii_subdependency": sub,
                "snii_entidad_final": r["ent_final"],
                "match": True,
                "matched_author": name,
                "matched_orcid": orcid,
                "matched_openalex_id": oa_id,
                "source": "Neo4j Recovery",
                "reason": "Recuperado desde base de datos Neo4j (is_snii=true)",
                "confidence": "HIGH"
            }
            
            # Crear llave de deduplicación (usando la misma lógica que el resolver)
            # Para simplificar, aquí solo evitamos duplicados exactos en este script
            key = (name, inst, sub)
            if key not in seen_keys:
                recovered_data.append(entry)
                seen_keys.add(key)

    print(f"✅ Se encontraron {len(recovered_data)} académicos SNII en Neo4j.")

    # Combinar con lo que ya exista en el JSON (para no perder los 30 nuevos)
    final_data = recovered_data
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                # Añadir solo los que no están en lo recuperado
                recovered_names = {r["snii_author"] for r in recovered_data}
                for e in existing:
                    if e["snii_author"] not in recovered_names:
                        final_data.append(e)
            print(f"📦 Combinado con {len(existing)} registros del JSON actual.")
        except:
            pass

    # Guardar resultado
    os.makedirs("data", exist_ok=True)
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    
    print(f"✨ Archivo {JSON_PATH} reconstruido con {len(final_data)} registros.")

if __name__ == "__main__":
    recover()
