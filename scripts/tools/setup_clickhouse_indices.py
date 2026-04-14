import clickhouse_connect
import os
from dotenv import load_dotenv

def optimize_clickhouse():
    load_dotenv()
    
    # --- 1. OPTIMIZAR ORCID LOCAL (127.0.0.1) ---
    orcid_host = os.getenv("CH_ORCID_HOST", "127.0.0.1")
    orcid_port = int(os.getenv("CH_ORCID_PORT", 8123))
    orcid_user = os.getenv("CH_ORCID_USER", "admin")
    orcid_password = os.getenv("CH_ORCID_PASSWORD", "admin")
    orcid_db = os.getenv("CH_ORCID_DATABASE", "orcid")

    print(f"--- Optimizing Local ORCID DB ({orcid_host}:{orcid_port}) ---")
    try:
        client_local = clickhouse_connect.get_client(
            host=orcid_host, port=orcid_port, 
            username=orcid_user, password=orcid_password, 
            database=orcid_db
        )
        print("Connected to Local ClickHouse.")
        
        try:
            client_local.command("ALTER TABLE orcid_records ADD INDEX idx_family_name family_name TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 1")
            client_local.command("ALTER TABLE orcid_records ADD INDEX idx_credit_name credit_name TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 1")
            client_local.command("ALTER TABLE orcid_records MATERIALIZE INDEX idx_family_name")
            client_local.command("ALTER TABLE orcid_records MATERIALIZE INDEX idx_credit_name")
            print("   Indices for orcid_records created and materialized.")
        except Exception as e:
            print(f"   Note (orcid_records): {e}")
            
    except Exception as e:
        print(f"   Connection Error (Local): {e}")

    # --- 2. OPTIMIZAR OPENALEX REMOTO (10.90.0.87) ---
    oa_host = os.getenv("CH_HOST", "10.90.0.87")
    oa_port = int(os.getenv("CH_PORT", 8124))
    oa_user = os.getenv("CH_USER", "rag_user")
    oa_password = os.getenv("CH_PASSWORD", "admin")
    oa_db = os.getenv("CH_DATABASE", "rag")

    print(f"\n--- Optimizing Remote OpenAlex DB ({oa_host}:{oa_port}) ---")
    try:
        client_remote = clickhouse_connect.get_client(
            host=oa_host, port=oa_port, 
            username=oa_user, password=oa_password, 
            database=oa_db
        )
        print(f"Connected to Remote ClickHouse (DB: {oa_db}).")
        
        try:
            client_remote.command("ALTER TABLE works ADD INDEX idx_title title TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 1")
            client_remote.command("ALTER TABLE works MATERIALIZE INDEX idx_title")
            print(f"   Index for works.title created and materialized.")
        except Exception as e:
            print(f"   Note (works): {e}")

    except Exception as e:
        print(f"   Connection Error (Remote): {e}")

    print("\nIndexing process finished.")

if __name__ == "__main__":
    optimize_clickhouse()
