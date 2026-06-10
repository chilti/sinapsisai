import requests
import json

url = "http://localhost:7474/db/neo4j/tx/commit"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Basic bmVvNGo6cGFzc3dvcmQ=" # base64 for neo4j:password
}

query = '''
MATCH (i:Institution {name: 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)'})
MATCH (d:Dependency {name: 'SECRETARIA GENERAL'})-[:PART_OF]->(i)
MATCH (s:Subdependency {name: 'FACULTAD DE CIENCIAS'})-[:PART_OF]->(d)
MATCH (p:Person)-[:AFFILIATED_TO]->(s)
WITH toLower(trim(replace(p.fullname, ',', ''))) AS nameNorm, collect(DISTINCT p) AS persons
WHERE size(persons) > 1
RETURN nameNorm, size(persons) as dups, persons LIMIT 5
'''

payload = {
    "statements": [{"statement": query}]
}

response = requests.post(url, headers=headers, json=payload)
data = response.json()

if 'errors' in data and data['errors']:
    print("Errors:", data['errors'])
else:
    for result in data['results']:
        for row in result['data']:
            print("Name:", row['row'][0], "Dups:", row['row'][1])
            for p in row['row'][2]:
                print("  Props:", p)
