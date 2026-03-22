import clickhouse_connect
import os
from dotenv import load_dotenv

load_dotenv()

host = os.getenv("CH_ORCID_HOST", "127.0.0.1")
port = int(os.getenv("CH_ORCID_PORT", 8123))
user = os.getenv("CH_ORCID_USER", "admin")
password = os.getenv("CH_ORCID_PASSWORD", "admin")
database = os.getenv("CH_ORCID_DATABASE", "openalex")

try:
    client = clickhouse_connect.get_client(host=host, port=port, username=user, password=password, database=database)
    res = client.query(f"DESCRIBE {database}.orcid_records")
    for row in res.result_rows:
        print(f"Column: {row[0]}, Type: {row[1]}")
except Exception as e:
    print(f"Error: {e}")
