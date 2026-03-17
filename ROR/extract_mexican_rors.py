import os
import json
import clickhouse_connect
from dotenv import load_dotenv
from pathlib import Path

# Cargar variables de entorno
load_dotenv()

CH_HOST = os.environ.get('CH_HOST', 'localhost')
CH_PORT = int(os.environ.get('CH_PORT', 8123))
CH_USER = os.environ.get('CH_USER', 'default')
CH_PASSWORD = os.environ.get('CH_PASSWORD', '')
CH_DATABASE = os.environ.get('CH_DATABASE', 'openalex')

def get_client():
    """Establece conexión con ClickHouse."""
    try:
        client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASSWORD,
            database=CH_DATABASE
        )
        return client
    except Exception as e:
        print(f"❌ Error conectando a ClickHouse: {e}")
        return None

def extract_mexican_rors():
    client = get_client()
    if not client:
        return

    # Verificar posibles nombres de tabla (institutions o openalex_institutions)
    tables = [r[0] for r in client.query("SHOW TABLES").result_rows]
    
    table_name = None
    if "institutions" in tables:
        table_name = "institutions"
    elif "openalex_institutions" in tables:
        table_name = "openalex_institutions"
    else:
        # Intentar buscar tablas que contengan 'institutions'
        for t in tables:
            if "institutions" in t.lower():
                table_name = t
                break
    
    if not table_name:
        print(f"❌ No se encontró la tabla de instituciones en la base de datos '{CH_DATABASE}'.")
        print(f"Tablas disponibles: {tables}")
        return

    print(f"🔍 Extrayendo RORs desde la tabla '{table_name}'...")

    # Query para extraer instituciones mexicanas con ROR
    # Usamos JSONExtractString para procesar el campo raw_data
    query = f"""
    SELECT 
        JSONExtractString(raw_data, 'id') as openalex_id,
        JSONExtractString(raw_data, 'display_name') as name,
        JSONExtractString(raw_data, 'ror') as ror,
        JSONExtractString(raw_data, 'country_code') as country_code,
        JSONExtractString(raw_data, 'type') as type
    FROM {table_name}
    WHERE JSONExtractString(raw_data, 'country_code') = 'MX'
      AND JSONExtractString(raw_data, 'ror') != ''
    """

    try:
        result = client.query(query)
        rows = result.result_rows
        
        output_data = []
        for row in rows:
            output_data.append({
                "openalex_id": row[0],
                "name": row[1],
                "ror": row[2],
                "country_code": row[3],
                "type": row[4]
            })

        output_file = Path(__file__).parent / "mexican_institutions_rors.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Se han extraído {len(output_data)} instituciones con ROR.")
        print(f"📂 Resultados guardados en: {output_file.absolute()}")

        # Resumen por tipo
        if output_data:
            from collections import Counter
            types = Counter(item['type'] for item in output_data)
            print("\nResumen por tipo:")
            for t, count in types.items():
                print(f" - {t or 'Unknown'}: {count}")

    except Exception as e:
        print(f"❌ Error durante la extracción: {e}")

if __name__ == "__main__":
    extract_mexican_rors()
