import sys
sys.path.insert(0, '/home/sinapsisai')
from dotenv import load_dotenv
load_dotenv('/home/sinapsisai/.env')
from database.clickhouse_db import ch_client

print("=== 5 DOIs de muestra en works_flat ===")
r = ch_client.query_df("SELECT doi FROM works_flat WHERE doi != '' LIMIT 5")
print(r.to_string())
print()

test_dois = [
    '10.1038/nm1685',
    '10.1513/pats.200906-041AL',
    '10.1152/ajplung.2000.279.5.l950',
]
for doi in test_dois:
    r1 = ch_client.query_df(f"SELECT id, doi FROM works_flat WHERE doi = '{doi}' LIMIT 1")
    r2 = ch_client.query_df(f"SELECT id, doi FROM works_flat WHERE doi = '{doi.lower()}' LIMIT 1")
    print(f"DOI original : {doi}")
    print(f"  exact match : {'FOUND -> ' + str(r1['doi'].iloc[0]) if not r1.empty else 'NOT FOUND'}")
    print(f"  lower match : {'FOUND -> ' + str(r2['doi'].iloc[0]) if not r2.empty else 'NOT FOUND'}")
    print()
