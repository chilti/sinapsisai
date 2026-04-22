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

UNAM_ROR = "https://ror.org/01tmp8f25"

def count_works():
    print(f"Connecting to ClickHouse {CH_HOST}...")
    try:
        client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASS,
            database=CH_DATABASE
        )
        
        # Query usando la columna ROR que ya está materializada y es rápida
        query = f"""
        SELECT count() as total 
        FROM works 
        WHERE has(institution_rors, '{UNAM_ROR}')
        SETTINGS use_skip_indexes = 0
        """
        
        print(f"Contando trabajos para UNAM via ROR {UNAM_ROR}...")
        result = client.query(query)
        total = result.result_rows[0][0]
        
        print(f"\nTotal de trabajos encontrados (vía ROR): {total:,}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    count_works()
