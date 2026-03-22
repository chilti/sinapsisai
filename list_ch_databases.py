import os
import clickhouse_connect
from dotenv import load_dotenv

def test_connection(host, port, user, password):
    print(f"\n--- Probando conexión a {host}:{port} ---")
    try:
        client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=user,
            password=password
        )
        print("✅ ¡Conexión exitosa!")
        
        databases = client.query("SHOW DATABASES").result_rows
        print("\nBases de datos encontradas:")
        for db in databases:
            print(f"  - {db[0]}")
            
        # Listar tablas en la base 'openalex' si existe
        if any(db[0] == 'openalex' for db in databases):
            print("\nTablas en 'openalex':")
            tables = client.query("SHOW TABLES FROM openalex").result_rows
            for t in tables:
                print(f"    * {t[0]}")
                
    except Exception as e:
        print(f"❌ Error de conexión: {e}")

if __name__ == "__main__":
    load_dotenv()
    
    # 1. Probar con lo que dice el .env (que ahora es el remoto)
    test_connection(
        os.getenv("CH_HOST"),
        int(os.getenv("CH_PORT", 8123)),
        os.getenv("CH_USER"),
        os.getenv("CH_PASSWORD")
    )
    
    # 2. Probar con LOCALHOST (por si el usuario quiere ver lo que tiene local)
    # Solo si el .env no es ya localhost
    if os.getenv("CH_HOST") not in ["localhost", "127.0.0.1"]:
        print("\n" + "="*40)
        print("¿Quieres probar tu ClickHouse LOCAL? (Usa Ctrl+C para cancelar)")
        test_connection("127.0.0.1", 8123, "default", "")
