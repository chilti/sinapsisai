import json
import os

def generate_official_snii_counts():
    # Prioritizar el Padrón oficial más reciente (2026)
    excel_candidates = [
        "data/snii/Investigadores_vigentes_2026.xlsx",
        "data/Padron-2026-2T.xlsx",
        "data/Investigadores_vigentes_2025.xlsx",
        "data/snii/Investigadores_vigentes_2025.xlsx",
    ]
    excel_path = next((p for p in excel_candidates if os.path.exists(p)), None)

    if excel_path:
        print(f"Reading official padrón from {excel_path} via pandas...")
        try:
            import pandas as pd
            df = pd.read_excel(excel_path)
            df.columns = [str(c).upper().strip() for c in df.columns]
            
            inst_col = next((c for c in df.columns if "INSTITUCION" in c or "INSTITUCIÓN" in c), None)
            dep_col = next((c for c in df.columns if "DEPENDENCIA" in c and "SUB" not in c), None)
            sub_col = next((c for c in df.columns if "SUBDEPENDENCIA" in c), None)
            
            counts = {}
            for _, row in df.iterrows():
                for col in [inst_col, dep_col, sub_col]:
                    if col and pd.notna(row[col]):
                        val = str(row[col]).strip()
                        if val and val not in ("NO APLICA", "SIN INFORMACION", "SIN INFORMACIÓN", "NAN"):
                            counts[val] = counts.get(val, 0) + 1
            
            _save(counts)
            return
        except ImportError:
            print("Pandas not found, falling back to JSON.")

    print(f"Reading {json_path}...")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    counts = {}
    for r in data:
        # Extraer todos los niveles posibles
        for key in ['snii_institution', 'snii_dependency', 'snii_subdependency']:
            val = r.get(key)
            if val and val != "NO APLICA":
                val = str(val).strip()
                counts[val] = counts.get(val, 0) + 1
            
    _save(counts)

def _save(counts):
    output_path = "data/official_snii_counts.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(counts, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(counts)} entities to {output_path}")

if __name__ == "__main__":
    generate_official_snii_counts()
