import os
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_PORT", 8123))
CH_USER = os.getenv("CH_USER", "admin")
CH_PASSWORD = os.getenv("CH_PASSWORD", "admin")
CH_DB       = os.getenv("CH_DATABASE", "rag")

target_table = f"{CH_DB}.institutions_seed_mexico"

# DDL mejorado para incluir jerarquía
create_query = f"""
CREATE TABLE IF NOT EXISTS {target_table}
ENGINE = MergeTree()
ORDER BY (display_name, id)
AS
SELECT 
    id,
    display_name,
    ror,
    type,
    country_code,
    JSONExtractString(raw_data, 'geo', 'city') as city,
    JSONExtractString(raw_data, 'geo', 'region') as state,
    # Intentamos extraer el ID y nombre del padre desde el JSON de relationships
    # Usamos una aproximación simple: el primer elemento que tenga type='parent'
    # Nota: ClickHouse JSONExtract es potente. 
    # Para simplicidad en el seed, extraemos los campos raw y procesaremos en Python o vía LLM,
    # pero aquí agregamos los campos sugeridos.
    arrayFilter(x -> x.3 = 'parent', 
        JSONExtract(raw_data, 'relationships', 'Array(Tuple(id String, label String, type String))')
    ) as parents,
    if(empty(parents), '', parents[1].1) as parent_id,
    if(empty(parents), '', parents[1].2) as parent_name,
    raw_data
FROM {CH_DB}.institutions
WHERE country_code = 'MX'
   OR lower(display_name) LIKE '%mexico%'
   OR ror != '';
"""

def run():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    
    print(f"Dropping existing table {target_table}...")
    client.command(f"DROP TABLE IF EXISTS {target_table}")
    
    print(f"Creating improved table {target_table}...")
    try:
        client.command(create_query)
        print("Table created successfully with hierarchy info!")
        
        # Verify count
        res = client.query(f"SELECT count() FROM {target_table}")
        print(f"Total rows in {target_table}: {res.result_rows[0][0]}")
        
        # Check a few rows with parents
        res = client.query(f"SELECT display_name, parent_name FROM {target_table} WHERE parent_name != '' LIMIT 5")
        print("\nEjemplos de jerarquía encontrada:")
        for row in res.result_rows:
            print(f"  - {row[0]} -> {row[1]}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run()
