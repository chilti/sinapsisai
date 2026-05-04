
import json

path = r"c:\Users\jlja\Documents\Proyectos\RAGs\data\snii_ror_verified_matches.json"
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# Buscar entradas que tengan algún ID que no sea del padre
matches = {}
for k, v in data.items():
    if v.get('matched_ror') or v.get('matched_openalex_id'):
        matches[k] = v
    if len(matches) > 10: break

print(json.dumps(matches, indent=2))
