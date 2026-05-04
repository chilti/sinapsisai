import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.clickhouse_db import ch_client

query = """
SELECT institution, institution_ror, entity, entity_id, count() as count
FROM paper_author_map
WHERE institution ILIKE '%banco de mexico%' OR institution_ror ILIKE '%banco de mexico%'
GROUP BY institution, institution_ror, entity, entity_id
ORDER BY count DESC
"""

df = ch_client.query_df(query)
print("=== PAPER AUTHOR MAP ===")
print(df.to_string())
