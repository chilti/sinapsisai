import os
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()

# Configuración ClickHouse
CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASS = os.getenv("CH_PASSWORD")
CH_DB   = os.getenv("CH_DATABASE", "rag")

UNAM_ROR = "https://ror.org/01tmp8f25"

def check_funding():
    print(f"🔍 Conectando a ClickHouse {CH_HOST}...")
    client = clickhouse_connect.get_client(
        host=CH_HOST, 
        port=CH_PORT, 
        username=CH_USER, 
        password=CH_PASS, 
        database=CH_DB
    )
    
    # Consulta para contar registros con grants no vacíos
    query = f"""
    SELECT 
        count() as total_works,
        countIf(raw_data LIKE '%"grants": [%' AND raw_data NOT LIKE '%"grants": []%') as works_with_funding
    FROM works
    WHERE has(institution_rors, '{UNAM_ROR}')
    """
    
    result = client.query(query)
    total, with_funding = result.result_rows[0]
    
    print(f"\n📊 Resultados para UNAM ({UNAM_ROR}):")
    print(f"   - Total de trabajos: {total:,}")
    print(f"   - Trabajos con datos de financiamiento (grants): {with_funding:,}")
    
    if total > 0:
        percent = (with_funding / total) * 100
        print(f"   - Cobertura: {percent:.2f}%")

if __name__ == "__main__":
    check_funding()
