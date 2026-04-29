import os
import json
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_PORT", 8123))
CH_USER = os.getenv("CH_USER", "admin")
CH_PASSWORD = os.getenv("CH_PASSWORD", "admin")

def check_acronyms():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    # Buscar INAOE
    res = client.query("SELECT display_name, raw_data FROM rag.institutions WHERE display_name LIKE '%Instituto Nacional de Astrofísica%' LIMIT 1")
    if res.result_rows:
        row = res.result_rows[0]
        data = json.loads(row[1])
        print(f"Name: {row[0]}")
        print(f"Acronyms: {data.get('display_name_acronyms')}")
    else:
        print("INAOE not found.")

if __name__ == "__main__":
    check_acronyms()
