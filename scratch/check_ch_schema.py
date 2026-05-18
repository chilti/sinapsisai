from database.clickhouse_db import ch_client
import pandas as pd

try:
    df = ch_client.query_df("DESCRIBE TABLE paper_author_map")
    print(df[['name', 'type']])
except Exception as e:
    print(f"Error: {e}")
