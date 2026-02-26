from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import uuid
from typing import List, Dict, Any
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

class QdrantStore:
    """
    Gestor de la base de datos vectorial Qdrant para almacenar 
    representaciones semánticas de textos y documentos.
    """
    def __init__(self, host="127.0.0.1", port=6333, collection_name="scientific_papers"):
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        self.vector_size = 768 # Dimensión para nomic-embed-text (O usar 1024 para bge-large-en-v1.5)
        
        self._ensure_collection_exists()

    def _ensure_collection_exists(self):
        """Verifica si la colección existe, si no, la crea."""
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)
        
        if not exists:
            print(f"Creando colección en Qdrant: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

    def add_documents(self, documents: List[Dict[str, Any]], embeddings: List[List[float]]):
        """
        Añade documentos y sus embeddings a Qdrant.
        documents: lista de diccionarios con metadatos (ej. {"text": "...", "doi": "...", "title": "..."})
        """
        if len(documents) != len(embeddings):
            raise ValueError("El número de documentos y embeddings debe coincidir.")
            
        points = []
        for doc, emb in zip(documents, embeddings):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb,
                    payload=doc
                )
            )
            
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        print(f"✅ Se insertaron {len(points)} documentos en Qdrant.")

    def search(self, query_vector: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """Realiza una búsqueda semántica usando un vector de consulta."""
        search_result = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit
        )
        
        results = []
        for hit in search_result:
            result = hit.payload.copy() if hit.payload else {}
            result["score"] = hit.score
            results.append(result)
            
        return results
