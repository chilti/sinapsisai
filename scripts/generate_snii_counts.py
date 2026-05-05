import pandas as pd
import json
import os

def generate_official_snii_counts():
    excel_path = "data/Investigadores_vigentes_2025.xlsx"
    if not os.path.exists(excel_path):
        print(f"File not found: {excel_path}")
        return

    print(f"Reading {excel_path}...")
    df = pd.read_excel(excel_path)
    
    # Normalizar nombres de columnas
    df.columns = [str(c).upper().strip() for c in df.columns]
    
    inst_col = "INSTITUCIÓN DE ACREDITACIÓN"
    if inst_col not in df.columns:
        # Fallback si hay tildes o variaciones
        for c in df.columns:
            if "INSTITUCION" in c or "INSTITUCIÓN" in c:
                inst_col = c
                break
    
    print(f"Grouping by {inst_col}...")
    counts = df.groupby(inst_col).size().to_dict()
    
    output_path = "data/official_snii_counts.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(counts, f, ensure_ascii=False, indent=2)
    
    print(f"Saved {len(counts)} institutions to {output_path}")

if __name__ == "__main__":
    generate_official_snii_counts()
