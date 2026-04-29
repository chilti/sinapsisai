import os
import json
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_PORT", 8123))
CH_USER = os.getenv("CH_USER", "admin")
CH_PASSWORD = os.getenv("CH_PASSWORD", "admin")

def find_hierarchy():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    
    # Buscar instituciones con lineage > 1
    query = """
    SELECT display_name, raw_data 
    FROM rag.institutions 
    WHERE length(JSONExtract(raw_data, 'lineage', 'Array(String)')) > 1 
    LIMIT 5
    """
    res = client.query(query)
    if res.result_rows:
        for row in res.result_rows:
            name = row[0]
            data = json.loads(row[1])
            print(f"\n--- {name} ---")
            print(f"ID: {data.get('id')}")
            print(f"Lineage: {data.get('lineage')}")
            print(f"Relationships: {data.get('relationships')}")
    else:
        print("No hierarchy found with lineage > 1.")

if __name__ == "__main__":
    find_hierarchy()
