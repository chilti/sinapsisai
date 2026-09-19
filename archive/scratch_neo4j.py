import json
from database.clickhouse_db import ClickHouseClient
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "chilti2024")

driver = GraphDatabase.driver(uri, auth=(user, password))

with driver.session() as session:
    res = session.run("MATCH (p:Person {fullname: 'BAYARD, PIERRE MICHEL'}) RETURN p.scopus_ids, p.orcids, p.openalex_ids, p.id")
    for r in res:
        print(f"Scopus IDs: {r['p.scopus_ids']} (Type: {type(r['p.scopus_ids'])})")
        print(f"ORCIDs: {r['p.orcids']} (Type: {type(r['p.orcids'])})")
        print(f"OpenAlex IDs: {r['p.openalex_ids']} (Type: {type(r['p.openalex_ids'])})")
