import pandas as pd
import json

df = pd.read_excel('SNII/Investigadores_vigentes_2025.xlsx', nrows=5)
print("Columnas encontradas:")
print([c for c in df.columns if 'ACREDITAC' in c or 'INSTI' in c])
