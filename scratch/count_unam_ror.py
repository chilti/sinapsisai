import clickhouse_connect
import os
from dotenv import load_dotenv

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASS = os.getenv("CH_PASSWORD")
CH_DATABASE = os.getenv("CH_DATABASE", "rag")

UNAM_ROR = "https://ror.org/01tmp8f25"

def count_via_ror():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASS, database=CH_DATABASE)
    print(f"Counting UNAM works via ROR {UNAM_ROR}...")
    query = f"SELECT count() FROM works WHERE has(institution_rors, '{UNAM_ROR}')"
    res = client.query(query)
    print(f"Total found via ROR: {res.result_rows[0][0]:,}")

if __name__ == "__main__":
    count_via_ror()
