import clickhouse_connect
import os
import time
from dotenv import load_dotenv

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASS = os.getenv("CH_PASSWORD", "$B3tt3r-R4g-3veR-d0N3++")
CH_DATABASE = os.getenv("CH_DATABASE", "rag")

def apply_optimizations():
    client = clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASS,
        database=CH_DATABASE
    )
    
    commands = [
        # 1. Crear columna correcta para IDs de Instituciones de OpenAlex
        "ALTER TABLE works ADD COLUMN IF NOT EXISTS openalex_institution_ids Array(String) MATERIALIZED arrayMap(x -> JSONExtractString(x, 'id'), JSONExtractArrayRaw(raw_data, 'institutions'))",
        
        # 2. Crear columna para IDs de Autores
        "ALTER TABLE works ADD COLUMN IF NOT EXISTS author_ids Array(String) MATERIALIZED arrayMap(x -> JSONExtractString(x, 'author', 'id'), JSONExtractArrayRaw(raw_data, 'authorships'))",
        
        # 3. Agregar Índices Bloom Filter
        "ALTER TABLE works ADD INDEX IF NOT EXISTS idx_oa_inst_ids openalex_institution_ids TYPE bloom_filter(0.01) GRANULARITY 1",
        "ALTER TABLE works ADD INDEX IF NOT EXISTS idx_author_ids author_ids TYPE bloom_filter(0.01) GRANULARITY 1",
        
        # 4. Forzar la materialización en los datos existentes (esto puede tardar)
        "ALTER TABLE works MATERIALIZE COLUMN openalex_institution_ids",
        "ALTER TABLE works MATERIALIZE COLUMN author_ids",
        "ALTER TABLE works MATERIALIZE INDEX idx_oa_inst_ids",
        "ALTER TABLE works MATERIALIZE INDEX idx_author_ids"
    ]
    
    for cmd in commands:
        print(f"Executing: {cmd[:100]}...")
        try:
            client.command(cmd)
            print("  -> Success")
        except Exception as e:
            print(f"  -> Error: {e}")
            # Si el error es que la columna ya existe, está bien
            if "already exists" in str(e).lower():
                continue
            else:
                raise e

if __name__ == "__main__":
    apply_optimizations()
