import clickhouse_connect
import os
from dotenv import load_dotenv

load_dotenv()

CH_HOST = os.environ.get('CH_HOST', 'localhost')
CH_PORT = int(os.environ.get('CH_PORT', 8123))
CH_USER = os.environ.get('CH_USER', 'default')
CH_PASSWORD = os.environ.get('CH_PASSWORD', '')
CH_DATABASE = os.environ.get('CH_DATABASE', 'rag')

try:
    client = clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DATABASE
    )
    print("Columns in summing_subfield_metrics:")
    print(client.query("DESCRIBE summing_subfield_metrics").result_rows)
    print("\nColumns in works:")
    print(client.query("DESCRIBE works").result_rows)
except Exception as e:
    print(f"Error: {e}")
