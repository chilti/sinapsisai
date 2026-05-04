import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.clickhouse_db import ch_client

# Verificar qué hay en paper_author_map para Banco de Mexico
query = """
SELECT institution, institution_ror, entity, entity_id, count() as c
FROM paper_author_map
WHERE institution ILIKE '%banco de mexico%'
GROUP BY institution, institution_ror, entity, entity_id
"""

df = ch_client.query_df(query)
print("=== PAPER AUTHOR MAP: BANCO DE MEXICO ===")
print(df)

# Verificar en Neo4j cómo están conectadas las entidades
from database.knowledge_graph import Neo4jGraphStore
store = Neo4jGraphStore()

query_neo = """
MATCH (i:Institution)<-[:PART_OF]-(e:Entity)
WHERE i.name =~ '(?i).*banco de mexico.*'
RETURN i.name, e.name, e.id
"""
with store.driver.session() as session:
    res = session.run(query_neo)
    print("\n=== NEO4J ENTITIES ===")
    for r in res:
        print(r)
