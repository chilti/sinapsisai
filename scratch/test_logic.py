import os
import json
import pandas as pd

# Simular la lógica de vectorize_snii_with_llm (solo la parte de manejo de datos)
def test_logic(json_content, excel_rows):
    # Simular carga
    verified_results = []
    lookup = {} 
    processed_in_this_run = set()
    
    # Simular deduplicación al cargar
    seen_keys = set()
    for r in json_content:
        key = (r["snii_author"], r.get("snii_institution", ""), r.get("snii_subdependency", ""))
        if key not in seen_keys:
            lookup[key] = len(verified_results)
            verified_results.append(r)
            seen_keys.add(key)
    
    print(f"Initial load: {len(verified_results)} records")

    for idx, row in enumerate(excel_rows):
        snii_name = row['name']
        final_inst = row['inst']
        final_sub = row['sub']
        key = (snii_name, final_inst, final_sub)
        
        if key in processed_in_this_run:
            print(f"[{idx}] Skipping INTERNAL duplicate: {snii_name}")
            continue
            
        if key in lookup:
            existing_record = verified_results[lookup[key]]
            if existing_record.get("match") is True:
                print(f"[{idx}] Skipping ALREADY MATCHED: {snii_name}")
                processed_in_this_run.add(key)
                continue
            else:
                print(f"[{idx}] RE-PROCESSING NO MATCH: {snii_name}")
        else:
            print(f"[{idx}] PROCESSING NEW: {snii_name}")

        # Simular procesamiento
        result_entry = {
            "snii_author": snii_name,
            "snii_institution": final_inst,
            "snii_subdependency": final_sub,
            "match": True if "match" in snii_name.lower() else False, # Mock logic
            "reason": "Test"
        }

        # Actualizar o Añadir
        if key in lookup:
            verified_results[lookup[key]] = result_entry
        else:
            lookup[key] = len(verified_results)
            verified_results.append(result_entry)
        
        processed_in_this_run.add(key)

    return verified_results

# Datos de prueba
mock_json = [
    {"snii_author": "A", "snii_institution": "U", "snii_subdependency": "S", "match": True},
    {"snii_author": "B", "snii_institution": "U", "snii_subdependency": "S", "match": False},
    {"snii_author": "B", "snii_institution": "U", "snii_subdependency": "S", "match": False}, # Duplicado en JSON
]

mock_excel = [
    {"name": "A", "inst": "U", "sub": "S"}, # Ya existe match true -> debe saltar
    {"name": "B", "inst": "U", "sub": "S"}, # Ya existe match false -> debe re-procesar y actualizar
    {"name": "C", "inst": "U", "sub": "S"}, # Nuevo -> debe añadir
    {"name": "C", "inst": "U", "sub": "S"}, # Duplicado en excel -> debe saltar
]

results = test_logic(mock_json, mock_excel)
print("\nFinal Results:")
print(json.dumps(results, indent=2))
if len(results) == 3:
    print("\n✅ Verification SUCCESS: No duplicates, correct updates.")
else:
    print(f"\n❌ Verification FAILED: Got {len(results)} records instead of 3.")
