import clickhouse_connect
import os
from dotenv import load_dotenv

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASS = os.getenv("CH_PASSWORD")
CH_DATABASE = os.getenv("CH_DATABASE", "rag")

def search_unam():
    client = clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASS,
        database=CH_DATABASE
    )
    
    print("Searching for UNAM in raw_data (exhaustive)...")
    res = client.query("SELECT count() FROM works WHERE raw_data LIKE '%I8961855%'")
    print(f"Total found via LIKE: {res.result_rows[0][0]}")
    
    if res.result_rows[0][0] > 0:
        print("\nChecking first result columns:")
        res_sample = client.query("SELECT * FROM works WHERE raw_data LIKE '%I8961855%' LIMIT 1")
        cols = res_sample.column_names
        row = res_sample.result_rows[0]
        for c, v in zip(cols, row):
            if c != 'raw_data':
                print(f"{c}: {v}")

if __name__ == "__main__":
    search_unam()
