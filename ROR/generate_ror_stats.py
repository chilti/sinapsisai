import json
import pandas as pd
import os

# Rutas prioritarias
MAPPING_PATHS = ["data/snii_ror_verified_matches.json", "ROR/snii_ror_mapping.json"]
OUTPUT_EXCEL = "ROR/snii_ror_inventory.xlsx"

def generate_stats():
    mapping_file = next((p for p in MAPPING_PATHS if os.path.exists(p)), None)
    
    if not mapping_file:
        print(f" No se encontr ningn archivo de mapeo en: {MAPPING_PATHS}")
        return

    print(f" Leyendo datos desde: {mapping_file}")
    with open(mapping_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rows = []
    stats = {
        "total_entries": 0,
        "mapped_rors": 0,
        "mapped_openalex": 0,
        "unique_institutions": set(),
        "unique_rors": set(),
        "unique_oa_ids": set()
    }

    for key, info in data.items():
        # Split Institution || Subdependency
        parts = key.split(" || ")
        inst = parts[0]
        # Manejar formato con o sin dependencia intermedia
        sub = parts[-1] if len(parts) > 1 else "SIN INFORMACIN"
        
        # Soporte para ambos formatos de llaves (nuevo vs antiguo)
        ror = info.get("matched_ror") or info.get("best_match_ror")
        oa_id = info.get("matched_openalex_id")
        parent_ror = info.get("parent_ror")
        parent_oa = info.get("parent_openalex_id")
        
        conf = info.get("confidence", 0)
        reason = info.get("reason", "")

        stats["total_entries"] += 1
        stats["unique_institutions"].add(inst)
        
        if ror and str(ror).lower() != 'none':
            stats["mapped_rors"] += 1
            stats["unique_rors"].add(ror)
        
        if oa_id and str(oa_id).lower() != 'none':
            stats["mapped_openalex"] += 1
            stats["unique_oa_ids"].add(oa_id)

        rows.append({
            "Institucin": inst,
            "Subdependencia": sub,
            "ROR ID": ror,
            "OpenAlex ID": oa_id,
            "Parent ROR": parent_ror,
            "Parent OpenAlex ID": parent_oa,
            "Confianza": conf,
            "Razn": reason
        })

    # Crear DataFrame y guardar Excel
    df = pd.DataFrame(rows)
    df = df.sort_values(by=["Institucin", "Subdependencia"])
    df.to_excel(OUTPUT_EXCEL, index=False)

    # Imprimir Estadsticas
    print("\n ESTADSTICAS DE MAPEO ROR/OPENALEX (SNII)")
    print("="*50)
    print(f"Total de registros analizados:      {stats['total_entries']}")
    print(f"Instituciones nicas en SNII:      {len(stats['unique_institutions'])}")
    print("-" * 50)
    print(f"Registros con ROR ID:              {stats['mapped_rors']} ({stats['mapped_rors']/stats['total_entries']:.1%})")
    print(f"Registros con OpenAlex ID:         {stats['mapped_openalex']} ({stats['mapped_openalex']/stats['total_entries']:.1%})")
    print("-" * 50)
    print(f"ROR IDs nicos:                    {len(stats['unique_rors'])}")
    print(f"OpenAlex IDs nicos:               {len(stats['unique_oa_ids'])}")
    print("=" * 50)
    print(f" Inventario generado en: {OUTPUT_EXCEL}")

if __name__ == "__main__":
    generate_stats()
