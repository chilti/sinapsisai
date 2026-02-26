import sys
import os

# Agregamos los subdirectorios al path para poder importar
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import base64
import httpx
from dotenv import load_dotenv
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from ingestion.document_processor import DocumentProcessor
from langchain_openai import OpenAIEmbeddings

load_dotenv()

class IngestionPipeline:
    """
    Controla el flujo completo: 
    PDF -> Extracción (Grobid/Unstructured) -> Chunks/Embeddings -> Qdrant & Neo4j
    """
    def __init__(self):
        self.doc_processor = DocumentProcessor()
        self.vector_store = QdrantStore()
        self.graph_store = Neo4jGraphStore()
        
        # Configuración de Autenticación Básica
        user = os.getenv("LLM_USER")
        password = os.getenv("LLM_PASSWORD")
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1/")
        
        headers = {}
        if user and password:
            credentials = f"{user}:{password}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            headers["Authorization"] = f"Basic {encoded_credentials}"
            
        http_client = httpx.Client(verify=False)

        self.embeddings_model = OpenAIEmbeddings(
            model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
            base_url=base_url,
            api_key="lm-studio",
            default_headers=headers,
            http_client=http_client
        )

    def ingest_scientific_paper(self, file_path: str, paper_metadata: dict):
        """
        1. Procesa el PDF con Grobid para obtener el texto estructurado.
        2. Sube los fragmentos vectorizados a Qdrant.
        3. Crea los nodos y relaciones en Neo4j usando los metadatos.
        """
        print(f"🚀 Iniciando ingesta híbrida de: {file_path}")
        
        # 1. Extracción de Texto
        grobid_result = self.doc_processor.process_scientific_pdf(file_path)
        if grobid_result["status"] != "success":
            print("Abortando ingesta por fallo en Grobid.")
            return

        xml_content = grobid_result["tei_xml"]
        
        # TODO: Implementar un parser XML TEI robusto que divida en secciones reales.
        # Por ahora simulamos la fragmentación (chunking)
        chunks = [xml_content[i:i+1000] for i in range(0, len(xml_content), 1000)]
        
        # 2. Vectorización e Inserción en Qdrant
        print("Mapeando a embeddings semánticos...")
        embeddings = self.embeddings_model.embed_documents(chunks)
        
        payloads = [{"source": file_path, "paper_id": paper_metadata["paper_id"], "text": chunk} for chunk in chunks]
        self.vector_store.add_documents(payloads, embeddings)
        
        # 3. Creación de Grafo de Conocimiento en Neo4j
        print("Sincronizando entidades en Neo4j...")
        self.graph_store.add_paper(paper_metadata)
        
        print("✅ Ingesta híbrida completada.")

if __name__ == "__main__":
    # Ejemplo de prueba manual
    # Para que funcione, db, grobid, y neo4j deben estar corriendo.
    pipeline = IngestionPipeline()
    
    # Metadata dummy simulada de OpenAlex o CrossRef
    dummy_metadata = {
        "paper_id": "W12345678",
        "title": "Ejemplo de Paper Híbrido RAG",
        "doi": "10.1234/ejemplo",
        "year": 2024,
        "citations": 5,
        "authors": [
            {"id": "A1", "name": "Dr. Juan Pérez", "institutions": [{"id": "I1", "name": "UNAM"}]}
        ],
        "concepts": [
            {"id": "C1", "name": "Artificial Intelligence"}
        ]
    }
    
    # pipe.ingest_scientific_paper("ruta/a/prueba.pdf", dummy_metadata)
    print("Pipeline de Ingesta Híbrida listo para usar.")
