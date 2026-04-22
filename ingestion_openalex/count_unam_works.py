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

UNAM_ID = "https://openalex.org/I8961855"

def count_works():
    print(f"🔗 Conectando a ClickHouse {CH_HOST}...")
    try:
        client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASS,
            database=CH_DATABASE
        )
        
        # Query optimizada para conteo usando columnas materializadas
        query = f"SELECT count() as total FROM works WHERE has(institution_ids, '{UNAM_ID}')"
        
        result = client.query(query)
        total = result.result_rows[0][0]
        
        print(f"\nTotal de trabajos encontrados: {total:,}")
        
        # Opcional: Conteo por año
        print("\nDistribucion por año (Top 10 recientes):")
        query_years = f"""
        SELECT publication_year, count() as count 
        FROM works 
        WHERE has(institution_ids, '{UNAM_ID}') 
        GROUP BY publication_year 
        ORDER BY publication_year DESC 
        LIMIT 10
        """
        result_years = client.query(query_years)
        for row in result_years.result_rows:
            print(f"   - {row[0]}: {row[1]:,}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    count_works()
