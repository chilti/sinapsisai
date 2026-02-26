import sys
import os
import time
from typing import List, Dict, Any

# Agregamos los subdirectorios al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import base64
import httpx
from dotenv import load_dotenv
from ingestion.wos_parser import WoSParser
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from langchain_openai import OpenAIEmbeddings

load_dotenv()

class WoSIngestor:
    def __init__(self, batch_size: int = 50):
        self.parser = WoSParser()
        self.vector_store = QdrantStore()
        self.graph_store = Neo4jGraphStore()
        
        # Configuración de Autenticación Básica (espejo de orchestrator.py)
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
            model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"), # Nombre no crítico si el servidor lo mapea
            base_url=base_url,
            api_key="lm-studio",
            default_headers=headers,
            http_client=http_client
        )
        self.batch_size = batch_size

    def ingest_file(self, file_path: str):
        print(f"📂 Cargando archivo WoS: {file_path}")
        records = self.parser.parse_file(file_path)
        total = len(records)
        print(f"✅ {total} registros encontrados. Iniciando ingesta por lotes de {self.batch_size}...")

        for i in range(0, total, self.batch_size):
            batch = records[i:i + self.batch_size]
            self._process_batch(batch, i, total)
            
        print(f"\n🎉 Ingesta de {file_path} completada con éxito.")

    def _process_batch(self, batch: List[Dict[str, Any]], start_idx: int, total: int):
        print(f"📦 Procesando lote {start_idx // self.batch_size + 1} ({start_idx}/{total})...", end="\r")
        
        # 1. Preparar textos para Qdrant (Título + Abstract)
        texts_to_embed = []
        payloads = []
        
        for record in batch:
            # Combinamos título y abstract para mejor búsqueda semántica
            text_content = f"Title: {record['title']}\nAbstract: {record['abstract']}"
            texts_to_embed.append(text_content)
            
            payloads.append({
                "paper_id": record["paper_id"],
                "title": record["title"],
                "year": record["year"],
                "doi": record["doi"],
                "text": text_content # Guardamos el texto también en el payload
            })

        # 2. Generar Embeddings
        try:
            embeddings = self.embeddings_model.embed_documents(texts_to_embed)
            
            # 3. Insertar en Qdrant
            self.vector_store.add_documents(payloads, embeddings)
            
            # 4. Sincronizar con Neo4j
            for record in batch:
                # El método add_paper en knowledge_graph.py espera una estructura específica
                # Adaptamos si es necesario o usamos una versión simplificada
                self.graph_store.add_paper(record)
                
        except Exception as e:
            print(f"\n❌ Error en lote {start_idx}: {e}")

if __name__ == "__main__":
    ingestor = WoSIngestor(batch_size=20)
    
    # Ingestar primero el archivo pequeño para prueba
    small_file = r"C:\Users\jlja\Documents\Proyectos\RAGs\data\papers_2025_2026.txt"
    if os.path.exists(small_file):
        ingestor.ingest_file(small_file)
    else:
        print(f"Archivo no encontrado: {small_file}")
