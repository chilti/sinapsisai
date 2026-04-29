import os
from qdrant_client import QdrantClient
from dotenv import load_dotenv

load_dotenv()

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

def list_collections():
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    collections = client.get_collections().collections
    print("Qdrant Collections:")
    for c in collections:
        print(f"- {c.name}")

if __name__ == "__main__":
    list_collections()
