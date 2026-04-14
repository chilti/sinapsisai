import clickhouse_connect
import os
from dotenv import load_dotenv

def optimize_clickhouse():
    load_dotenv()
    
    # 1. Conexion (Local ORCID / Works)
    host = os.getenv("CH_ORCID_HOST", "127.0.0.1")
    port = int(os.getenv("CH_ORCID_PORT", 8123))
    user = os.getenv("CH_ORCID_USER", "admin")
    password = os.getenv("CH_ORCID_PASSWORD", "admin")
    database = os.getenv("CH_ORCID_DATABASE", "orcid")

    try:
        print(f"Connecting to ClickHouse at {host}:{port}...")
        client = clickhouse_connect.get_client(host=host, port=port, username=user, password=password, database=database)
        print("Success.")
        
        # --- orcid_records ---
        print("\nOptimizing table 'orcid_records'...")
        try:
            client.command("ALTER TABLE orcid_records ADD INDEX idx_family_name family_name TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 1")
            client.command("ALTER TABLE orcid_records ADD INDEX idx_credit_name credit_name TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 1")
            client.command("ALTER TABLE orcid_records MATERIALIZE INDEX idx_family_name")
            client.command("ALTER TABLE orcid_records MATERIALIZE INDEX idx_credit_name")
            print("   Indices for names created and materialized.")
        except Exception as e:
            print(f"   Note (might already exist): {e}")

        # --- works ---
        print("\nOptimizing table 'works'...")
        target_db = os.getenv("CH_DATABASE", "rag")
        try:
            client.command(f"USE {target_db}")
            client.command("ALTER TABLE works ADD INDEX idx_title title TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 1")
            client.command("ALTER TABLE works MATERIALIZE INDEX idx_title")
            print(f"   Index for titles in {target_db}.works created.")
        except Exception as e:
            print(f"   Note (works): {e}")

        print("\nIndexing complete.")
        
    except Exception as e:
        print(f"\nConnection Error: {e}")

if __name__ == "__main__":
    optimize_clickhouse()
