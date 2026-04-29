import json
import pandas as pd
import os

# Rutas
MAPPING_PATH = "ROR/snii_ror_mapping.json"
OUTPUT_EXCEL = "ROR/snii_ror_inventory.xlsx"

def generate_stats():
    if not os.path.exists(MAPPING_PATH):
        print(f"❌ No se encontr el archivo {MAPPING_PATH}")
        return

    with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    rows = []
    stats = {
        "total_entries": 0,
        "mapped_entries": 0,
        "unique_institutions": set(),
        "mapped_institutions": set(),
        "unique_rors": set()
    }

    for key, info in data.items():
        # Split Institution || Subdependency
        parts = key.split(" || ")
        inst = parts[0]
        sub = parts[1] if len(parts) > 1 else "SIN INFORMACIN"
        
        ror = info.get("best_match_ror")
        conf = info.get("confidence", 0)
        reason = info.get("reason", "")

        stats["total_entries"] += 1
        stats["unique_institutions"].add(inst)
        
        if ror:
            stats["mapped_entries"] += 1
            stats["mapped_institutions"].add(inst)
            stats["unique_rors"].add(ror)

        rows.append({
            "Institucin": inst,
            "Subdependencia": sub,
            "ROR ID": ror,
            "Confianza": conf,
            "Razn": reason
        })

    # Crear DataFrame y guardar Excel
    df = pd.DataFrame(rows)
    # Ordenar por institucion para mejor lectura
    df = df.sort_values(by=["Institucin", "Subdependencia"])
    df.to_excel(OUTPUT_EXCEL, index=False)

    # Imprimir Estadsticas
    print("\n ESTADSTICAS DE MAPEO ROR (SNII)")
    print("="*40)
    print(f"Total de registros analizados:      {stats['total_entries']}")
    print(f"Instituciones nicas en SNII:      {len(stats['unique_institutions'])}")
    print("-" * 40)
    print(f"Registros con ROR identificado:     {stats['mapped_entries']} ({stats['mapped_entries']/stats['total_entries']:.1%})")
    print(f"Instituciones con al menos un ROR:  {len(stats['mapped_institutions'])} ({len(stats['mapped_institutions'])/len(stats['unique_institutions']):.1%})")
    print(f"ROR IDs nicos utilizados:          {len(stats['unique_rors'])}")
    print("=" * 40)
    print(f" Excel generado en: {OUTPUT_EXCEL}")

if __name__ == "__main__":
    generate_stats()
