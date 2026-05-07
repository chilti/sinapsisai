import json
import os

def generate_official_snii_counts():
    json_path = "data/snii_llm_verified_matches.json"
    if not os.path.exists(json_path):
        # Fallback to Excel if JSON doesn't exist
        excel_path = "data/Investigadores_vigentes_2025.xlsx"
        if os.path.exists(excel_path):
            print(f"Reading {excel_path} via pandas...")
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
                        if col and pd.notna(row[col]) and str(row[col]).strip() != "NO APLICA":
                            val = str(row[col]).strip()
                            counts[val] = counts.get(val, 0) + 1
                
                _save(counts)
                return
            except ImportError:
                print("Pandas not found, cannot read Excel.")
                return
        else:
            print(f"No source found (JSON or Excel)")
            return

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
