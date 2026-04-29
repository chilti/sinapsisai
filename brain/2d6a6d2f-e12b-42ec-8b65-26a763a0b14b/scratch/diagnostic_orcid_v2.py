import os
import time
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

CH_ORCID_HOST = os.getenv("CH_ORCID_HOST", "127.0.0.1")
CH_ORCID_PORT = int(os.getenv("CH_ORCID_PORT", 8123))
CH_ORCID_USER = os.getenv("CH_ORCID_USER", "default")
CH_ORCID_PASS = os.getenv("CH_ORCID_PASSWORD", "")
CH_DB_ORCID = os.getenv("CH_ORCID_DATABASE", "orcid")

def test_orcid_performance():
    print(f"--- Diagnostico de Busqueda en ORCID ({CH_ORCID_HOST}:{CH_ORCID_PORT}) ---")
    start_conn = time.time()
    try:
        client = clickhouse_connect.get_client(
            host=CH_ORCID_HOST, 
            port=CH_ORCID_PORT, 
            username=CH_ORCID_USER, 
            password=CH_ORCID_PASS,
            connect_timeout=5
        )
        print(f"Conector creado en {time.time() - start_conn:.2f}s")
        
        start_q = time.time()
        res = client.query("SELECT count() FROM system.databases").result_rows[0][0]
        print(f"Consulta basica exitosa: {res} dbs | Tiempo: {time.time() - start_q:.2f}s")
        
    except Exception as e:
        print(f"FALLO en ORCID: {type(e).__name__}: {str(e)}")

if __name__ == "__main__":
    test_orcid_performance()
