import clickhouse_connect

def check_ch_schema():
    try:
        client = clickhouse_connect.get_client(
            host='10.90.0.87',
            port=8124,
            username='rag_user',
            password='$B3tt3r-R4g-3veR-d0N3++'
        )
        
        print("--- Verificando columnas mediante SELECT en rag.works_seed_mexico ---")
        try:
            res = client.query("SELECT apc_paid_usd, counts_by_year, language, is_doaj_indexed FROM rag.works_seed_mexico LIMIT 1")
            print("✅ Las columnas existen en rag.works_seed_mexico.")
            
            res_count = client.query("SELECT count() FROM rag.works_seed_mexico WHERE apc_paid_usd > 0")
            print(f"Registros con APC > 0: {res_count.result_rows[0][0]}")
            
        except Exception as e:
            if "Unknown column" in str(e):
                print("❌ Algunas columnas NO existen en rag.works_seed_mexico.")
                print(f"Detalle: {e}")
            else:
                print(f"Error inesperado: {e}")
            
    except Exception as e:
        print(f"Error de conexión: {e}")

if __name__ == "__main__":
    check_ch_schema()
