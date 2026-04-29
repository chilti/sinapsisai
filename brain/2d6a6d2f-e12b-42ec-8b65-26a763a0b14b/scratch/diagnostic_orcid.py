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
    print(f"--- Diagnóstico de Búsqueda en ORCID ({CH_ORCID_HOST}:{CH_ORCID_PORT}) ---")
    start_conn = time.time()
    try:
        # Timeout corto para diagnosticar rápido
        client = clickhouse_connect.get_client(
            host=CH_ORCID_HOST, 
            port=CH_ORCID_PORT, 
            username=CH_ORCID_USER, 
            password=CH_ORCID_PASS,
            connect_timeout=5
        )
        print(f"✅ Conector creado en {time.time() - start_conn:.2f}s")
        
        # Prueba de consulta básica
        start_q = time.time()
        res = client.query("SELECT count() FROM system.databases").result_rows[0][0]
        print(f"✅ Consulta básica exitosa: {res} dbs | Tiempo: {time.time() - start_q:.2f}s")
        
        # Prueba de búsqueda por nombre (Nicandro)
        k1, k2 = "CRUZ", "NICANDRO"
        query = f"""
        SELECT count() 
        FROM {CH_DB_ORCID}.orcid_records 
        WHERE (lower(family_name) LIKE '%{k1.lower()}%' OR lower(credit_name) LIKE '%{k1.lower()}%') 
          AND (lower(given_names) LIKE '%{k2.lower()}%' OR lower(credit_name) LIKE '%{k2.lower()}%')
        """
        start_search = time.time()
        count = client.query(query).result_rows[0][0]
        print(f"✅ Búsqueda Nicandro en ORCID: {count} resultados | Tiempo: {time.time() - start_search:.2f}s")
        
    except Exception as e:
        print(f"❌ FALLO en ORCID: {e}")

if __name__ == "__main__":
    test_orcid_performance()
