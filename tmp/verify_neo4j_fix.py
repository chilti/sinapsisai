
import sys
import os

# Add root path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.knowledge_graph import Neo4jGraphStore

graph = Neo4jGraphStore()

ENTITY_NAME = "SECRETARIA DE SALUD TEST"
PAPER_ID = "test-doi-123"

print(f"Creating Entity by name: {ENTITY_NAME}")
# Simulate ROR link (which creates entity by name)
graph.add_entity_paper_link(ENTITY_NAME, PAPER_ID)

print(f"Adding paper with Institution by ID and same name...")
paper_data = {
    "paper_id": PAPER_ID,
    "doi": PAPER_ID,
    "title": "Test Paper",
    "authors": [
        {
            "name": "Test Author",
            "institutions": [
                {
                    "id": "https://openalex.org/I-TEST-ID",
                    "name": ENTITY_NAME
                }
            ]
        }
    ]
}

try:
    graph.add_paper(paper_data)
    print("✅ Successfully added paper without constraint violation.")
except Exception as e:
    print(f"❌ Failed with error: {e}")

graph.close()
