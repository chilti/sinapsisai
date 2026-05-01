"""
Diagnóstico: verifica si los DOIs de Neo4j matchean en works_flat de ClickHouse.
"""
import sys, os
sys.path.append(os.path.abspath('.'))
from dotenv import load_dotenv
load_dotenv()

from database.clickhouse_db import ch_client

# DOIs que vienen de Neo4j para PARDO CEMO (muestra del papers_profesor.parquet)
test_dois_original = [
    '10.1038/nm1685',
    '10.1513/pats.200906-041AL',
    '10.1152/ajplung.2000.279.5.l950',
    '10.1164/rccm.200701-093OC',
]

print("=== TEST 1: DOI exacto (case sensitive) ===")
for doi in test_dois_original:
    r = ch_client.query_df(f"SELECT id, doi FROM works_flat WHERE doi = '{doi}' LIMIT 1")
    print(f"  {doi[:40]} -> {'FOUND' if not r.empty else 'NOT FOUND'}")

print()
print("=== TEST 2: DOI en minúsculas ===")
for doi in test_dois_original:
    doi_lower = doi.lower()
    r = ch_client.query_df(f"SELECT id, doi FROM works_flat WHERE doi = '{doi_lower}' LIMIT 1")
    print(f"  {doi_lower[:40]} -> {'FOUND: ' + r['doi'].iloc[0] if not r.empty else 'NOT FOUND'}")

print()
print("=== TEST 3: DOI con LIKE (case-insensitive) ===")
test_doi = '10.1038/nm1685'
r = ch_client.query_df(f"SELECT id, doi FROM works_flat WHERE lower(doi) = lower('{test_doi}') LIMIT 3")
print(f"  lower(doi)=lower('{test_doi}') -> {r.to_dict('records') if not r.empty else 'NOT FOUND'}")

print()
print("=== TEST 4: Muestra de DOIs reales en CH ===")
r = ch_client.query_df("SELECT doi FROM works_flat LIMIT 5")
print(r)
