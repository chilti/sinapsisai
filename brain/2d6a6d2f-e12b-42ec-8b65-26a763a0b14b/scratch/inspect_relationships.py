import os
import json
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_PORT", 8123))
CH_USER = os.getenv("CH_USER", "admin")
CH_PASSWORD = os.getenv("CH_PASSWORD", "admin")

def inspect():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    # Buscar una entidad que probablemente tenga padre
    res = client.query("SELECT display_name, raw_data FROM rag.institutions WHERE lower(display_name) LIKE '%institute of biotechnology%' AND country_code = 'MX' LIMIT 1")
    if not res.result_rows:
        res = client.query("SELECT display_name, raw_data FROM rag.institutions WHERE lower(display_name) LIKE '%facultad%' AND country_code = 'MX' LIMIT 1")
        
    if res.result_rows:
        row = res.result_rows[0]
        print(f"Name: {row[0]}")
        data = json.loads(row[1])
        print("Relationships JSON:")
        print(json.dumps(data.get('relationships', []), indent=2))
    else:
        print("No results found.")

if __name__ == "__main__":
    inspect()
