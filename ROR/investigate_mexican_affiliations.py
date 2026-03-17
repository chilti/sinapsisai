import os
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv('ROR/.env')

CH_HOST = os.environ.get('CH_HOST')
CH_PORT = int(os.environ.get('CH_PORT'))
CH_USER = os.environ.get('CH_USER')
CH_PASSWORD = os.environ.get('CH_PASSWORD')
CH_DATABASE = os.environ.get('CH_DATABASE')

def check_mexican_author_affiliations():
    client = clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DATABASE
    )
    
    # 1. Autores con última afiliación MX
    print("⏳ Contando autores cuya última afiliación es de México...")
    mx_query = "SELECT count(*) FROM authors WHERE JSONExtractString(raw_data, 'last_known_institution', 'country_code') = 'MX'"
    mx_count = client.query(mx_query).result_rows[0][0]
    print(f"✅ Total de autores mexicanos (por última afiliación): {mx_count:,}")
    
    if mx_count > 0:
        # 2. De esos, cuántos tienen ROR
        print("⏳ Verificando presencia de ROR en estos autores...")
        ror_query = "SELECT count(*) FROM authors WHERE JSONExtractString(raw_data, 'last_known_institution', 'country_code') = 'MX' AND JSONExtractString(raw_data, 'last_known_institution', 'ror') != ''"
        ror_count = client.query(ror_query).result_rows[0][0]
        print(f"✅ Autores con ROR asignado: {ror_count:,} ({ror_count/mx_count:.1%})")
        
        # 3. Muestra de ejemplos
        print("\n📝 Ejemplos de registros mexicanos en la tabla 'authors':")
        query_sample = """
        SELECT 
            JSONExtractString(raw_data, 'id'),
            JSONExtractString(raw_data, 'display_name'),
            JSONExtractString(raw_data, 'last_known_institution', 'display_name'),
            JSONExtractString(raw_data, 'last_known_institution', 'ror')
        FROM authors 
        WHERE JSONExtractString(raw_data, 'last_known_institution', 'country_code') = 'MX'
        LIMIT 10
        """
        samples = client.query(query_sample).result_rows
        for s in samples:
            print(f" - [{s[1]}] | Inst: {s[2]} | ROR: {s[3] or 'N/A'}")

if __name__ == "__main__":
    check_mexican_author_affiliations()
