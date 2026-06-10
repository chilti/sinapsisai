import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
from database.knowledge_graph import Neo4jGraphStore

cypher_orcid = """
MATCH (a:Person)
WHERE a.orcid IS NOT NULL
WITH a, CASE 
  WHEN apoc.meta.cypher.type(a.orcid) = 'LIST OF STRING' THEN a.orcid
  WHEN apoc.meta.cypher.type(a.orcid) = 'STRING' THEN [a.orcid]
  ELSE [] END AS new_orcids
SET a.orcids = new_orcids
REMOVE a.orcid
"""

cypher_openalex = """
MATCH (a:Person)
WHERE a.openalex_id IS NOT NULL
WITH a, CASE 
  WHEN apoc.meta.cypher.type(a.openalex_id) = 'LIST OF STRING' THEN a.openalex_id
  WHEN apoc.meta.cypher.type(a.openalex_id) = 'STRING' THEN [x IN split(a.openalex_id, ',') WHERE x <> '']
  ELSE [] END AS new_openalex_ids
SET a.openalex_ids = new_openalex_ids
REMOVE a.openalex_id
"""

cypher_scopus = """
MATCH (a:Person)
WHERE a.scopus_id IS NOT NULL
WITH a, CASE 
  WHEN apoc.meta.cypher.type(a.scopus_id) = 'LIST OF STRING' THEN a.scopus_id
  WHEN apoc.meta.cypher.type(a.scopus_id) = 'STRING' AND NOT a.scopus_id STARTS WITH '2-s2.0-' THEN [a.scopus_id]
  ELSE [] END AS extra_scopus_ids
SET a.scopus_ids = apoc.coll.toSet(coalesce(a.scopus_ids, []) + extra_scopus_ids)
REMOVE a.scopus_id
"""

def migrate():
    graph_store = Neo4jGraphStore()
    try:
        with graph_store.driver.session() as session:
            for n, q in [('ORCID', cypher_orcid), ('OpenAlex', cypher_openalex), ('Scopus', cypher_scopus)]:
                print(f"Migrating {n}...")
                try:
                    session.run(q)
                    print(f"Migrating {n}... Done.")
                except Exception as e:
                    print(f"Error in {n}: {e}")
    finally:
        graph_store.close()

if __name__ == "__main__":
    migrate()
