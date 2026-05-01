import sys; sys.path.insert(0,'.')
from dotenv import load_dotenv; load_dotenv()
from database.clickhouse_db import ch_client

df = ch_client.query_df('SELECT * FROM works_seed_mexico LIMIT 2')
print('=== works_seed_mexico ===')
print('Columnas:', sorted(df.columns.tolist()))
print()

c = ch_client.query_df('SELECT count() AS n FROM works_seed_mexico')
n = int(c['n'].iloc[0])
print(f'Total filas: {n:,}')

# Ver si tiene fwci y institution_ids
for col in ['fwci', 'institution_ids', 'country_codes', 'id', 'doi', 'publication_year']:
    if col in df.columns:
        print(f'  {col}: {df[col].iloc[0]}')
