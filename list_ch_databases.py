import os
import clickhouse_connect
from dotenv import load_dotenv

def test_connection(name, host, port, user, password, database):
    print(f"\n--- Probando [{name}] a {host}:{port} (DB: {database}) ---")
    try:
        client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=user,
            password=password,
            database=database
        )
        print(f"✅ ¡Conexión exitosa a {name}!")
        
        databases = client.query("SHOW DATABASES").result_rows
        print("\nBases de datos encontradas:")
        for db in databases:
            print(f"  - {db[0]}")
            
        tables = client.query(f"SHOW TABLES FROM {database}").result_rows
        print(f"\nTablas en '{database}':")
        for t in tables:
            print(f"    * {t[0]}")
                
    except Exception as e:
        print(f"❌ Error de conexión a {name}: {e}")

if __name__ == "__main__":
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '.env'))
    load_dotenv(env_path)
    
    # 1. Probar REMOTE (OpenAlex)
    test_connection(
        "REMOTO - OpenAlex",
        os.getenv("CH_HOST"),
        int(os.getenv("CH_PORT", 8124)),
        os.getenv("CH_USER"),
        os.getenv("CH_PASSWORD"),
        os.getenv("CH_DATABASE", "rag")
    )
    
    # 2. Probar LOCAL (ORCID)
    print("\n" + "="*40)
    test_connection(
        "LOCAL - ORCID",
        os.getenv("CH_ORCID_HOST", "127.0.0.1"),
        int(os.getenv("CH_ORCID_PORT", 8123)),
        os.getenv("CH_ORCID_USER", "default"),
        os.getenv("CH_ORCID_PASSWORD", ""),
        os.getenv("CH_ORCID_DATABASE", "openalex")
    )
