from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, PayloadSchemaType
import uuid
from typing import List, Dict, Any, Optional
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
    def __init__(self, host=None, port=None, collection_name="scientific_papers"):
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        self.host = host or os.getenv("QDRANT_HOST", "127.0.0.1")
        self.port = int(port or os.getenv("QDRANT_PORT", 6333))
        self.client = QdrantClient(host=self.host, port=self.port)
        self.collection_name = collection_name
        self.vector_size = 768 # Dimensión para nomic-embed-text (O usar 1024 para bge-large-en-v1.5)
        
        self._ensure_collection_exists()

    def _ensure_collection_exists(self):
        """Verifica si la colección existe, si no, la crea. También asegura índices de payload."""
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)
        
        if not exists:
            print(f"Creando colección en Qdrant: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
        
        # Asegurar índices en campos clave para filtrado eficiente
        fields_to_index = {
            "entity": PayloadSchemaType.KEYWORD,
            "doi": PayloadSchemaType.KEYWORD,
            "year": PayloadSchemaType.INTEGER
        }
        
        for field, schema in fields_to_index.items():
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=schema
                )
            except Exception:
                pass 

    def add_documents(self, documents: List[Dict[str, Any]], embeddings: List[List[float]]):
        """
        Añade documentos y sus embeddings a Qdrant.
        documents: lista de diccionarios con metadatos (ej. {"text": "...", "doi": "...", "title": "..."})
        """
        if len(documents) != len(embeddings):
            raise ValueError("El número de documentos y embeddings debe coincidir.")
            
        points = []
        for doc, emb in zip(documents, embeddings):
            # Usar un UUID determinista basado en el DOI (o título si el DOI falla)
            # Esto previene que los papers de co-autores se registren múltiples veces en Qdrant
            unique_str = doc.get("doi")
            if not unique_str or unique_str == "None":
                unique_str = doc.get("title", str(uuid.uuid4()))
                
            deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, unique_str))
            
            points.append(
                PointStruct(
                    id=deterministic_id,
                    vector=emb,
                    payload=doc
                )
            )
            
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        print(f"✅ Se insertaron {len(points)} documentos en Qdrant.")

    def check_document_exists(self, doi: str, title: str = None) -> bool:
        """Verifica si un documento ya existe en Qdrant usando su ID determinista."""
        unique_str = doi
        if not unique_str or str(unique_str).strip().lower() == "none":
            unique_str = title
            
        if not unique_str:
            return False
            
        deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, unique_str))
        try:
            res = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[deterministic_id],
                with_payload=False,
                with_vectors=False
            )
            return len(res) > 0
        except Exception:
            return False

    def search(self, query_vector: List[float], limit: int = 5, entity_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Realiza una búsqueda semántica usando un vector de consulta.
        
        Args:
            query_vector: El vector de la consulta.
            limit: Número máximo de resultados.
            entity_filter: Si se proporciona, filtra los resultados por entidad usando
                           el campo 'entity' del payload de Qdrant de forma nativa.
        """
        qdrant_filter = None
        if entity_filter:
            qdrant_filter = Filter(
                must=[FieldCondition(key="entity", match=MatchValue(value=entity_filter))]
            )
        
        try:
            # En qdrant-client 1.11+, query_points es la API preferida
            search_result = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=qdrant_filter,
                limit=limit,
                timeout=60  # segundos – defensa ante consultas lentas
            ).points
        except Exception as e:
            # Reintento con timeout extendido (no llamamos a client.search, ya no existe en qdrant-client >= 1.7)
            print(f"DEBUG: Primer query_points falló ({e}). Reintentando con timeout=120s...")
            try:
                search_result = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=qdrant_filter,
                    limit=limit,
                    timeout=120
                ).points
            except Exception as e2:
                print(f"DEBUG: Segundo intento también falló ({e2}). Retornando lista vacía.")
                return []

        
        results = []
        for hit in search_result:
            result = hit.payload.copy() if hit.payload else {}
            result["score"] = hit.score
            results.append(result)
            
        return results

    def get_collection_stats(self) -> dict:
        """Obtiene estadísticas de la colección vectorial (número de documentos)."""
        try:
            count_result = self.client.count(collection_name=self.collection_name)
            return {"total_vectors": count_result.count}
        except Exception as e:
            return {"total_vectors": 0, "error": str(e)}

    def get_schema_info(self) -> dict:
        """Devuelve configuración base de métricas del ecosistema vectorial."""
        try:
            col_info = self.client.get_collection(self.collection_name)
            return {
                "collection_name": self.collection_name,
                "vector_size": getattr(col_info.config.params.vectors, 'size', getattr(col_info.config.params, 'size', 768)),
                "distance": str(getattr(col_info.config.params.vectors, 'distance', getattr(col_info.config.params, 'distance', 'Cosine'))).split('.')[-1],
                "payload_schema": {
                    "academic_name": "String (Author fullname)",
                    "doi": "String (Unique Web Identifier)",
                    "title": "String (Paper Title)",
                    "year": "Numeric (Publication Year)",
                    "source": "String (Scopus / ORCID)",
                    "text": "String (Concat of Title + Abstract for LLM)"
                }
            }
        except Exception as e:
            return {"error": str(e)}
