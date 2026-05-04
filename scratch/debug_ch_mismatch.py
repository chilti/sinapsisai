import clickhouse_connect

def debug_ch_data():
    try:
        client = clickhouse_connect.get_client(
            host='10.90.0.87',
            port=8124,
            username='rag_user',
            password='$B3tt3r-R4g-3veR-d0N3++'
        )
        
        print("--- 1. Muestra de nombres de instituciones en paper_author_map ---")
        res = client.query("SELECT institution, count() as total FROM rag.paper_author_map GROUP BY institution ORDER BY total DESC LIMIT 20")
        for row in res.result_rows:
            print(f"{row[0]} -> {row[1]} papers")
            
        print("\n--- 2. Verificando una de las universidades faltantes (BAJA CALIFORNIA SUR) ---")
        res = client.query("SELECT count() FROM rag.paper_author_map WHERE institution LIKE '%BAJA CALIFORNIA SUR%'")
        print(f"Papers encontrados para BAJA CALIFORNIA SUR: {res.result_rows[0][0]}")

        print("\n--- 3. Verificando formato de IDs ---")
        res = client.query("SELECT paper_id FROM rag.paper_author_map LIMIT 5")
        print(f"Muestra de IDs en paper_author_map: {[r[0] for r in res.result_rows]}")
        
        res = client.query("SELECT id FROM rag.works_seed_mexico LIMIT 5")
        print(f"Muestra de IDs en works_seed_mexico: {[r[0] for r in res.result_rows]}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_ch_data()
