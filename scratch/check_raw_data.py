import clickhouse_connect
import os
import json
from dotenv import load_dotenv

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASS = os.getenv("CH_PASSWORD")
CH_DATABASE = os.getenv("CH_DATABASE", "rag")

def check_raw_data():
    client = clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASS,
        database=CH_DATABASE
    )
    
    res = client.query("SELECT raw_data FROM works LIMIT 1")
    raw_data = res.result_rows[0][0]
    try:
        parsed = json.loads(raw_data)
        print("Raw data is valid JSON.")
        print(f"Keys: {list(parsed.keys())}")
    except:
        print("Raw data is NOT valid JSON.")
        print(raw_data[:200])

if __name__ == "__main__":
    check_raw_data()
