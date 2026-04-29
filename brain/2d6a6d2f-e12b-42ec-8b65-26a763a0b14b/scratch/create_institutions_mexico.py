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
    raw_data
FROM {CH_DB}.institutions
WHERE country_code = 'MX'
   OR lower(display_name) LIKE '%mexico%'
   OR ror != '';
"""

def run():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    print(f"Creating table {target_table}...")
    try:
        client.command(create_query)
        print("Table created successfully!")
        
        # Verify count
        res = client.query(f"SELECT count() FROM {target_table}")
        print(f"Total rows in {target_table}: {res.result_rows[0][0]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run()
