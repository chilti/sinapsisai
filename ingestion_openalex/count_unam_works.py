import clickhouse_connect
import os
from dotenv import load_dotenv

load_dotenv()

# Configuración ClickHouse (Remoto)
CH_HOST = "10.90.0.87"
CH_PORT = 8123
CH_USER = "admin"
CH_PASS = "admin"
CH_DATABASE = "openalex"

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
        
        print(f"📊 Contando trabajos para UNAM ({UNAM_ID})...")
        
        # Query optimizada para conteo
        query = f"SELECT count() as total FROM works WHERE has(authorships.institutions.id, '{UNAM_ID}')"
        
        result = client.query(query)
        total = result.result_rows[0][0]
        
        print(f"\n✅ Total de trabajos encontrados: {total:,}")
        
        # Opcional: Conteo por año
        print("\n📈 Distribución por año (Top 10 recientes):")
        query_years = f"""
        SELECT publication_year, count() as count 
        FROM works 
        WHERE has(authorships.institutions.id, '{UNAM_ID}') 
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
