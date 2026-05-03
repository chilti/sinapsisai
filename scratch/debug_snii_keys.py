import json
import pandas as pd
import os
import sys

# Forzar encoding UTF-8 para evitar errores de consola en Windows
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

JSON_PATH = "data/snii_llm_verified_matches.json"
EXCEL_PATH = "data/Investigadores_vigentes_2025.xlsx"
SHEET = "4T_2025 (44,794)"

def debug_keys():
    print("DEBUG: Comparando llaves de búsqueda...")
    
    # 1. Ver qué hay en el JSON (primeros 3)
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            print("\n--- Muestra del JSON ---")
            for i in range(min(5, len(data))):
                r = data[i]
                # Replicar exactamente la lógica de formación de llave del script original
                key = (r["snii_author"], r.get("snii_institution", ""), r.get("snii_subdependency", ""))
                print(f"JSON Key {i}: {key}")
    
    # 2. Ver cómo se genera la llave del Excel para las primeras filas
    print(f"\n📂 Cargando Excel: {EXCEL_PATH}, Hoja: {SHEET}...")
    df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET, nrows=5)
    
    print("\n--- Muestra del Excel (Generación de llaves) ---")
    for i in range(len(df)):
        row = df.iloc[i]
        name = str(row['NOMBRE DEL INVESTIGADOR']).strip()
        inst = str(row['INSTITUCIÓN DE ACREDITACIÓN']).strip() if pd.notna(row['INSTITUCIÓN DE ACREDITACIÓN']) else ""
        dep = str(row['DEPENDENCIA DE ACREDITACIÓN']).strip() if pd.notna(row['DEPENDENCIA DE ACREDITACIÓN']) else ""
        sub = str(row['SUBDEPENDENCIA DE ACREDITACIÓN']).strip() if pd.notna(row['SUBDEPENDENCIA DE ACREDITACIÓN']) else ""
        
        # Lógica exacta del resolver (con el posible problema de 'SIN INSTITUCIN')
        if inst.upper() in ["SIN INSTITUCIN", "SIN INSTITUCION"]:
            final_inst = "SIN INSTITUCIN"
            final_sub = "NO APLICA"
        elif sub.upper() in ["SIN INFORMACION", "SIN INFORMACIN", ""]:
            final_inst = inst
            final_sub = dep if dep else sub
        else:
            final_inst = inst
            final_sub = sub
            
        excel_key = (name, final_inst, final_sub)
        print(f"Excel Row {i}: {excel_key}")

if __name__ == "__main__":
    debug_keys()
