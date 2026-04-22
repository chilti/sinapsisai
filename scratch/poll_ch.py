import clickhouse_connect
import os
from dotenv import load_dotenv
import time

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASS = os.getenv("CH_PASSWORD")
CH_DATABASE = os.getenv("CH_DATABASE", "rag")

def test_conn():
    print(f"Polling ClickHouse {CH_HOST}:{CH_PORT}...")
    try:
        client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASS,
            database=CH_DATABASE,
            connect_timeout=5
        )
        print("Connected!")
        return True
    except Exception as e:
        print(f"Failed: {e}")
        return False

if __name__ == "__main__":
    test_conn()
