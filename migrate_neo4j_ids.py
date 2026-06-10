import sys
import os

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from database.knowledge_graph import Neo4jGraphStore

cypher = """
MATCH (a:Person)
SET a.orcids = CASE 
    WHEN a.orcid IS NOT NULL AND a.orcid <> "" THEN [a.orcid] 
    WHEN a.orcids IS NOT NULL THEN a.orcids
    ELSE [] 
END
SET a.openalex_ids = CASE 
    WHEN a.openalex_id IS NOT NULL AND a.openalex_id <> "" THEN [x IN split(a.openalex_id, ',') WHERE x <> ''] 
    WHEN a.openalex_ids IS NOT NULL THEN a.openalex_ids
    ELSE [] 
END
SET a.scopus_ids = apoc.coll.toSet(coalesce(a.scopus_ids, []) + CASE WHEN a.scopus_id IS NOT NULL AND a.scopus_id <> "" AND NOT a.scopus_id STARTS WITH "2-s2.0-" THEN [a.scopus_id] ELSE [] END)
REMOVE a.orcid, a.openalex_id, a.scopus_id
RETURN count(a) as migrated_nodes
"""

def migrate():
    graph_store = Neo4jGraphStore()
    try:
        with graph_store.driver.session() as session:
            result = session.run(cypher)
            record = result.single()
            print(f"Migrated nodes: {record['migrated_nodes']}")
    except Exception as e:
        print(f"Error migrating: {e}")
    finally:
        graph_store.close()

if __name__ == "__main__":
    migrate()
