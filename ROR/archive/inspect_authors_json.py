import os
import json
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv('ROR/.env')

def inspect_structure():
    client = clickhouse_connect.get_client(
        host=os.environ.get('CH_HOST'),
        port=int(os.environ.get('CH_PORT')),
        username=os.environ.get('CH_USER'),
        password=os.environ.get('CH_PASSWORD'),
        database=os.environ.get('CH_DATABASE')
    )
    
    print("🔍 Inspeccionando 10 registros de 'authors' para entender la estructura de afiliación...")
    res = client.query("SELECT raw_data FROM authors LIMIT 10").result_rows
    
    for i, row in enumerate(res):
        data = json.loads(row[0])
        print(f"\n--- Autor {i+1}: {data.get('display_name')} ---")
        
        # Ver qué campos de afiliación existen
        relevant_keys = ['last_known_institution', 'last_known_institutions', 'affiliations']
        for key in relevant_keys:
            if key in data:
                print(f"✅ {key}: {json.dumps(data[key], indent=2)[:200]}...")
        
        # Ver campos de país
        country_keys = [k for k in data.keys() if 'country' in k.lower()]
        for k in country_keys:
            print(f"📍 {k}: {data[k]}")

if __name__ == "__main__":
    inspect_structure()
