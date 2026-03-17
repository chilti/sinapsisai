import os
import json
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv('ROR/.env')

def get_author_mx_stats():
    client = clickhouse_connect.get_client(
        host=os.environ.get('CH_HOST'),
        port=int(os.environ.get('CH_PORT')),
        username=os.environ.get('CH_USER'),
        password=os.environ.get('CH_PASSWORD'),
        database=os.environ.get('CH_DATABASE')
    )
    
    print("🚀 Consultando autores mexicanos y sus RORs...")

    # Usamos LIKE para filtrar por país MX dentro del JSON raw_data
    # Buscamos específicamente la estructura de last_known_institution
    query = """
    SELECT 
        count(*) as total_mx,
        countIf(JSONExtractString(raw_data, 'last_known_institution', 'ror') != '') as with_ror
    FROM authors 
    WHERE JSONExtractString(raw_data, 'last_known_institution', 'country_code') = 'MX'
    """
    
    try:
        res = client.query(query).result_rows[0]
        total_mx = res[0]
        with_ror = res[1]
        
        print(f"\n📊 Resultados para Autores Mexicanos:")
        print(f" - Total de autores: {total_mx:,}")
        print(f" - Autores con ROR en su última institución: {with_ror:,}")
        if total_mx > 0:
            print(f" - Cobertura de ROR: {with_ror/total_mx:.1%}")
        
        # Obtener una muestra para validar visualmente
        print("\n📝 Muestra de 5 autores mexicanos:")
        sample_query = """
        SELECT 
            JSONExtractString(raw_data, 'display_name'),
            JSONExtractString(raw_data, 'last_known_institution', 'display_name'),
            JSONExtractString(raw_data, 'last_known_institution', 'ror')
        FROM authors 
        WHERE JSONExtractString(raw_data, 'last_known_institution', 'country_code') = 'MX'
        LIMIT 5
        """
        samples = client.query(sample_query).result_rows
        for s in samples:
            print(f" - {s[0]} | Inst: {s[1]} | ROR: {s[2] or 'No asignado'}")
            
    except Exception as e:
        print(f"❌ Error en la consulta: {e}")

if __name__ == "__main__":
    get_author_mx_stats()
