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

    def ingest_directory(self, directory_path: str):
        print(f"📂 Escaneando directorio: {directory_path}")
        if not os.path.isdir(directory_path):
            print(f"❌ Error: {directory_path} no es un directorio válido.")
            return

        files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) 
                 if f.endswith('.txt') or f.endswith('.txt.txt')] # Soporte para extensiones comunes de WoS
        
        if not files:
            print(f"⚠️ No se encontraron archivos .txt en {directory_path}")
            return

        print(f"🔍 Encontrados {len(files)} archivos para procesar.")
        for file_path in sorted(files):
            try:
                self.ingest_file(file_path)
            except Exception as e:
                print(f"❌ Error procesando {file_path}: {e}")

    def _process_batch(self, batch: List[Dict[str, Any]], start_idx: int, total: int):
        print(f"📦 Procesando lote {start_idx // self.batch_size + 1} ({start_idx}/{total})...", end="\r")
        
        # 1. Preparar textos para Qdrant (Título + Abstract)
        texts_to_embed = []
        payloads = []
        
        for record in batch:
            # Combinamos título y abstract para mejor búsqueda semántica
            # Manejamos posibles valores nulos
            title = record.get('title', 'No Title')
            abstract = record.get('abstract', 'No Abstract Available')
            text_content = f"Title: {title}\nAbstract: {abstract}"
            texts_to_embed.append(text_content)
            
            payloads.append({
                "paper_id": record.get("paper_id", ""),
                "title": title,
                "year": record.get("year", 0),
                "doi": record.get("doi", ""),
                "text": text_content
            })

        # 2. Generar Embeddings
        try:
            embeddings = self.embeddings_model.embed_documents(texts_to_embed)
            
            # 3. Insertar en Qdrant
            self.vector_store.add_documents(payloads, embeddings)
            
            # 4. Sincronizar con Neo4j
            for record in batch:
                self.graph_store.add_paper(record)
                
        except Exception as e:
            print(f"\n❌ Error en lote {start_idx}: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingesta de registros Web of Science (WoS) a Qdrant y Neo4j.")
    parser.add_argument("path", help="Ruta al archivo .txt o al directorio que contiene los archivos de WoS.")
    parser.add_argument("--batch", type=int, default=20, help="Tamaño del lote para procesamiento (default: 20).")
    
    args = parser.parse_args()
    
    ingestor = WoSIngestor(batch_size=args.batch)
    
    if os.path.isdir(args.path):
        ingestor.ingest_directory(args.path)
    elif os.path.isfile(args.path):
        ingestor.ingest_file(args.path)
    else:
        print(f"❌ La ruta proporcionada no existe: {args.path}")
