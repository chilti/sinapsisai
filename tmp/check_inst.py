
import os
import json
import clickhouse_connect
from dotenv import load_dotenv

# Path relative to the script location
env_path = os.path.join(os.getcwd(), 'ROR', '.env')
load_dotenv(env_path)

CH_HOST = os.environ.get('CH_HOST')
CH_PORT = int(os.environ.get('CH_PORT'))
CH_USER = os.environ.get('CH_USER')
CH_PASSWORD = os.environ.get('CH_PASSWORD')
CH_DATABASE = os.environ.get('CH_DATABASE')

def check_sample():
    client = clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DATABASE
    )
    
    query = """
    SELECT raw_data 
    FROM institutions 
    WHERE JSONExtractString(raw_data, 'country_code') = 'MX' 
      AND JSONExtractString(raw_data, 'associated_institutions') != '[]'
    LIMIT 1
    """
    result = client.query(query).result_rows
    if result:
        data = json.loads(result[0][0])
        print("Entity:", data.get('display_name'))
        print("Associated Institutions:", json.dumps(data.get('associated_institutions', []), indent=2))
        print("Lineage:", data.get('lineage', []))
    else:
        print("No result found with associated institutions.")

if __name__ == "__main__":
    check_sample()
