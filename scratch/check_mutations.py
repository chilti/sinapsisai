import clickhouse_connect
import os
from dotenv import load_dotenv

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASS = os.getenv("CH_PASSWORD")
CH_DATABASE = os.getenv("CH_DATABASE", "rag")

def check_mutations():
    print(f"Connecting to ClickHouse {CH_HOST}...")
    try:
        client = clickhouse_connect.get_client(
            host=CH_HOST,
            port=CH_PORT,
            username=CH_USER,
            password=CH_PASS,
            database=CH_DATABASE
        )
        
        query = """
        SELECT 
            command, 
            is_done, 
            latest_fail_reason, 
            parts_to_do, 
            create_time
        FROM system.mutations 
        WHERE table = 'works' AND is_done = 0
        ORDER BY create_time DESC
        """
        
        result = client.query(query)
        if not result.result_rows:
            print("No active mutations found for table 'works'.")
            
            # Verificamos si hay columnas nuevas
            print("\nChecking if columns exist:")
            res_cols = client.query("DESCRIBE works")
            cols = [row[0] for row in res_cols.result_rows]
            target_cols = ['openalex_institution_ids', 'author_ids']
            for tc in target_cols:
                if tc in cols:
                    print(f"  - Column '{tc}' exists.")
                    # Verificamos si tiene datos
                    res_data = client.query(f"SELECT count() FROM works WHERE not empty({tc})")
                    print(f"    Rows with data: {res_data.result_rows[0][0]:,}")
                else:
                    print(f"  - Column '{tc}' DOES NOT EXIST.")
        else:
            print(f"Found {len(result.result_rows)} active mutations:")
            for row in result.result_rows:
                print(f"\nCommand: {row[0][:100]}...")
                print(f"Done: {row[1]}")
                print(f"Parts to do: {row[3]}")
                print(f"Fail Reason: {row[2] or 'None'}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_mutations()
