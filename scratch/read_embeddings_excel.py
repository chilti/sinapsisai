import pandas as pd
import json

file_path = r"C:\Users\jlja\Downloads\Generación de Embeddings para Neo4j.xlsx"

try:
    # Leer todas las hojas
    xl = pd.ExcelFile(file_path)
    print(f"Hojas encontradas: {xl.sheet_names}")
    
    for sheet in xl.sheet_names:
        print(f"\n--- Contenido de la hoja: {sheet} ---")
        df = pd.read_excel(file_path, sheet_name=sheet)
        print(df.to_string())
except Exception as e:
    print(f"Error leyendo el archivo Excel: {e}")
