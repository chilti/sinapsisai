import pandas as pd
import json
import os

print("Cargando matriz Excel...")
df = pd.read_excel('SNII/Investigadores_vigentes_2025.xlsx')

mapping = {}
for _, row in df.iterrows():
    name = str(row['NOMBRE DEL INVESTIGADOR']).strip()
    inst = str(row['INSTITUCIÓN DE ACREDITACIÓN']).strip() if pd.notna(row['INSTITUCIÓN DE ACREDITACIÓN']) else ""
    dep = str(row['DEPENDENCIA DE ACREDITACIÓN']).strip() if pd.notna(row['DEPENDENCIA DE ACREDITACIÓN']) else ""
    subdep = str(row['SUBDEPENDENCIA DE ACREDITACIÓN']).strip() if pd.notna(row['SUBDEPENDENCIA DE ACREDITACIÓN']) else ""
    mapping[name] = {"inst": inst, "dep": dep, "subdep": subdep}

json_path = 'SNII/snii_llm_verified_matches.json'
print(f"Cargando JSON desde {json_path}...")
with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

modificados_2_niveles = 0
modificados_sin_inst = 0

for item in data:
    author = item.get('snii_author', '').strip()
    if author in mapping:
        info = mapping[author]
        inst = info['inst']
        dep = info['dep']
        subdep = info['subdep']
        
        # Rule 2: SIN INSTITUCION
        if inst.upper() in ["SIN INSTITUCIÓN", "SIN INSTITUCION"]:
            item['snii_institution'] = "SIN INSTITUCIÓN"
            item['snii_subdependency'] = "NO APLICA"
            modificados_sin_inst += 1
        # Rule 1: Two levels
        elif subdep.upper() in ["SIN INFORMACION", "SIN INFORMACIÓN", ""]:
            item['snii_institution'] = inst
            item['snii_subdependency'] = dep if dep else subdep
            modificados_2_niveles += 1
        # Three levels (Default)
        else:
            item['snii_institution'] = inst
            item['snii_subdependency'] = subdep

print("Guardando JSON...")
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Actualización completada exitosamente.")
print(f" - Modificados por ser 2 niveles (DEPENDENCIA -> SUBDEPENDENCIA): {modificados_2_niveles}")
print(f" - Modificados por ser SIN INSTITUCIÓN: {modificados_sin_inst}")
