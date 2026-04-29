import os
import json
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_PORT", 8123))
CH_USER = os.getenv("CH_USER", "admin")
CH_PASSWORD = os.getenv("CH_PASSWORD", "admin")

def check_hierarchy():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    
    # Buscar una facultad o instituto para ver relaciones
    res = client.query("SELECT display_name, raw_data FROM rag.institutions WHERE lower(display_name) LIKE '%institute%' AND country_code = 'MX' LIMIT 5")
    for row in res.result_rows:
        name = row[0]
        data = json.loads(row[1])
        print(f"\n--- {name} ---")
        print(f"ID: {data.get('id')}")
        print(f"Lineage: {data.get('lineage')}")
        print(f"Relationships: {data.get('relationships')}")

if __name__ == "__main__":
    check_hierarchy()
