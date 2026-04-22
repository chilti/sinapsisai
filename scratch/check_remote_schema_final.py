import clickhouse_connect
import os
from dotenv import load_dotenv

load_dotenv()

# Configuración ClickHouse (Remoto desde .env)
CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASS = os.getenv("CH_PASSWORD", "$B3tt3r-R4g-3veR-d0N3++")
CH_DATABASE = os.getenv("CH_DATABASE", "rag")

def check_schema():
    print(f"Connecting to ClickHouse {CH_HOST}:{CH_PORT}...")
    try:
        client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASS,
            database=CH_DATABASE
        )
        
        print(f"Describing table 'works'...")
        res = client.query("DESCRIBE works")
        for row in res.result_rows:
            print(f"{row[0]}: {row[1]}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_schema()
