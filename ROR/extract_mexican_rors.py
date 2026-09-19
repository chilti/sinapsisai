import os
import json
import clickhouse_connect
from dotenv import load_dotenv
from pathlib import Path

# Cargar variables de entorno desde la raíz del proyecto
root_env = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(root_env if root_env.exists() else None)

CH_HOST = os.environ.get('CH_HOST', 'localhost')
CH_PORT = int(os.environ.get('CH_PORT', 8124))
CH_USER = os.environ.get('CH_USER', 'default')
CH_PASSWORD = os.environ.get('CH_PASSWORD', '')
CH_DATABASE = os.environ.get('CH_DATABASE', 'rag')

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

    table_name = "institutions"
    print(f"🔍 Extrayendo RORs mexicanos vigentes desde '{CH_DATABASE}.{table_name}'...")

    # Query optimizada sobre columnas nativas, deduplicando por ID y descartando instituciones borradas
    query = f"""
    SELECT 
        id as openalex_id,
        display_name as name,
        ror,
        country_code,
        type,
        JSONExtractString(raw_data, 'associated_institutions') as associated_institutions,
        JSONExtract(raw_data, 'lineage', 'Array(String)') as lineage
    FROM {table_name}
    WHERE country_code = 'MX'
      AND ror != ''
      AND display_name != 'Deleted Institution'
      AND display_name != ''
    ORDER BY display_name ASC
    """

    try:
        result = client.query(query)
        rows = result.result_rows
        
        seen_ids = set()
        output_data = []
        for row in rows:
            oa_id = row[0]
            if oa_id in seen_ids:
                continue
            seen_ids.add(oa_id)

            try:
                assocs = json.loads(row[5]) if row[5] else []
            except Exception:
                assocs = []

            output_data.append({
                "openalex_id": oa_id,
                "name": row[1],
                "ror": row[2],
                "country_code": row[3],
                "type": row[4],
                "associated_institutions": assocs,
                "lineage": row[6]
            })

        output_file = Path(__file__).parent / "mexican_institutions_rors.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Se han extraído {len(output_data)} instituciones mexicanas únicas con ROR.")
        print(f"📂 Resultados guardados en: {output_file.absolute()}")

        # Resumen por tipo
        if output_data:
            from collections import Counter
            types = Counter(item['type'] for item in output_data)
            print("\nResumen por tipo:")
            for t, count in types.most_common():
                print(f" - {t or 'Unknown'}: {count}")

    except Exception as e:
        print(f"❌ Error durante la extracción: {e}")

if __name__ == "__main__":
    extract_mexican_rors()

