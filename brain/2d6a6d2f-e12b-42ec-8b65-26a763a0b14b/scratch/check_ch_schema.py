import os
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_PORT", 8123))
CH_USER = os.getenv("CH_USER", "admin")
CH_PASSWORD = os.getenv("CH_PASSWORD", "admin")
CH_DB       = os.getenv("CH_DATABASE", "rag")

def check_schema():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    
    print(f"Checking schema for {CH_DB}.authors...")
    res = client.query(f"DESCRIBE {CH_DB}.authors")
    for row in res.result_rows:
        print(f"{row[0]}: {row[1]}")

    print("\nChecking first row to see raw_data content...")
    res = client.query(f"SELECT raw_data FROM {CH_DB}.authors LIMIT 1")
    print(res.result_rows[0][0][:500])

if __name__ == "__main__":
    check_schema()
