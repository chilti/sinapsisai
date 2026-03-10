import httpx
import urllib3
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

doi = "10.1002/cjce.70273"
clean_doi = doi.lower().strip()

# Probar acceso directo via API de OpenAlex con HTTPX
# Nota: OpenAlex prefiere el DOI completo con prefijo https://doi.org/
url = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"

print(f"Probando conexion a: {url}")

params = {"mailto": "jlja@ciencias.unam.mx"}

try:
    with httpx.Client(verify=False, timeout=10.0) as client:
        resp = client.get(url, params=params)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Exito! Titulo: {data.get('title')}")
            print(f"ORCIDs encontrados: {[a['author'].get('orcid') for a in data.get('authorships', []) if a['author'].get('orcid')]}")
        else:
            print(f"Error de respuesta: {resp.text[:200]}")
except Exception as e:
    print(f"Error critico de red: {e}")
