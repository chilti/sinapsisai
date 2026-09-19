import os
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv('ROR/.env')

CH_HOST = os.environ.get('CH_HOST')
CH_PORT = int(os.environ.get('CH_PORT'))
CH_USER = os.environ.get('CH_USER')
CH_PASSWORD = os.environ.get('CH_PASSWORD')
CH_DATABASE = os.environ.get('CH_DATABASE')

def check_author_affiliations():
    client = clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DATABASE
    )
    
    print(f"📊 Investigando base de datos: {CH_DATABASE}")
    
    # 1. Total de autores
    total_authors = client.query("SELECT count(*) FROM authors").result_rows[0][0]
    print(f"Total de autores: {total_authors:,}")
    
    # 2. Autores con last_known_institution
    with_inst = client.query("SELECT count(*) FROM authors WHERE JSONExtractString(raw_data, 'last_known_institution') != ''").result_rows[0][0]
    print(f"Autores con última institución conocida: {with_inst:,} ({with_inst/total_authors:.1%})")
    
    # 3. Autores con ROR en su última institución
    with_ror = client.query("SELECT count(*) FROM authors WHERE JSONExtractString(raw_data, 'last_known_institution', 'ror') != ''").result_rows[0][0]
    print(f"Autores con ROR en su última institución: {with_ror:,} ({with_ror/total_authors:.1%})")
    
    # 4. Ejemplo de un autor mexicano (si existe)
    query_mx = """
    SELECT 
        JSONExtractString(raw_data, 'display_name'),
        JSONExtractString(raw_data, 'last_known_institution', 'display_name'),
        JSONExtractString(raw_data, 'last_known_institution', 'ror')
    FROM authors 
    WHERE JSONExtractString(raw_data, 'last_known_institution', 'country_code') = 'MX'
    LIMIT 5
    """
    try:
        mx_authors = client.query(query_mx).result_rows
        print("\nEjemplos de autores mexicanos:")
        for r in mx_authors:
            print(f" - Autor: {r[0]:<30} | Institución: {r[1]:<40} | ROR: {r[2]}")
    except Exception as e:
        print(f"Error consultando autores MX: {e}")

if __name__ == "__main__":
    check_author_affiliations()
