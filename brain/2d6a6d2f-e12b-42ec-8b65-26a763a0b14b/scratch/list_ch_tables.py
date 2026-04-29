import os
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_PORT", 8123))
CH_USER = os.getenv("CH_USER", "admin")
CH_PASSWORD = os.getenv("CH_PASSWORD", "admin")
CH_DB       = os.getenv("CH_DATABASE", "rag")

def list_tables():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    print(f"Tables in {CH_DB}:")
    res = client.query(f"SHOW TABLES FROM {CH_DB}")
    for row in res.result_rows:
        print(row[0])

if __name__ == "__main__":
    list_tables()
