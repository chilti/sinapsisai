import os
import json
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_PORT", 8123))
CH_USER = os.getenv("CH_USER", "admin")
CH_PASSWORD = os.getenv("CH_PASSWORD", "admin")

def inspect_associated():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    query = """
    SELECT display_name, raw_data 
    FROM rag.institutions 
    WHERE length(JSONExtract(raw_data, 'lineage', 'Array(String)')) > 1 
    LIMIT 1
    """
    res = client.query(query)
    if res.result_rows:
        data = json.loads(res.result_rows[0][1])
        print(f"Name: {res.result_rows[0][0]}")
        print("Associated Institutions:")
        print(json.dumps(data.get('associated_institutions', []), indent=2))

if __name__ == "__main__":
    inspect_associated()
