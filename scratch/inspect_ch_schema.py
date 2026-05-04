from database.clickhouse_db import ch_client
import pandas as pd

def inspect():
    print("--- SCHEMA: works_flat ---")
    try:
        df = ch_client.query_df("DESCRIBE TABLE works_flat")
        print(df[['name', 'type']])
    except Exception as e:
        print(f"Error describing works_flat: {e}")

    print("\n--- SCHEMA: works_seed_mexico ---")
    try:
        df = ch_client.query_df("DESCRIBE TABLE works_seed_mexico")
        print(df[['name', 'type']])
    except Exception as e:
        print(f"Error describing works_seed_mexico: {e}")

if __name__ == "__main__":
    inspect()
