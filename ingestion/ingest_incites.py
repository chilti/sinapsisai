import sys
import os
import pandas as pd
from typing import List, Dict, Any
from dotenv import load_dotenv

# Agregamos los subdirectorios al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import base64
import httpx
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from langchain_openai import OpenAIEmbeddings

load_dotenv()

class InCitesIngestor:
    def __init__(self, batch_size: int = 50):
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
        self.batch_size = batch_size

    def ingest_directory(self, directory_path: str):
        print(f"📂 Escaneando directorio InCites: {directory_path}")
        if not os.path.isdir(directory_path):
            print(f"❌ Error: {directory_path} no es un directorio válido.")
            return

        files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) 
                 if f.endswith('.xlsx') or f.endswith('.xls')]
        
        if not files:
            print(f"⚠️ No se encontraron archivos Excel en {directory_path}")
            return

        print(f"🔍 Encontrados {len(files)} archivos para procesar.")
        for file_path in sorted(files):
            try:
                self.ingest_file(file_path)
            except Exception as e:
                print(f"❌ Error procesando {file_path}: {e}")

    def ingest_file(self, file_path: str):
        print(f"\n📑 Procesando archivo InCites: {file_path}")
        
        # Leer Excel - InCites suele tener los datos en la primera hoja
        df = pd.read_excel(file_path)
        
        # Limpieza básica de columnas (quitar espacios)
        df.columns = [c.strip() for c in df.columns]
        
        # Registros mapeados al formato interno
        records = []
        for _, row in df.iterrows():
            doi = str(row.get('DOI', '')).strip()
            if doi == 'nan': doi = ''
            
            # Formatear registro para batch
            record = {
                "paper_id": str(row.get('Accession Number', '')),
                "title": str(row.get('Article Title', 'No Title')),
                "year": self._extract_year(row.get('Publication Date')),
                "doi": doi,
                "abstract": "", # InCites excel export usually doesn't have abstract, but we keep the key
                "authors_list": str(row.get('Authors', '')).split(';'),
                "journal": str(row.get('Source', ''))
            }
            records.append(record)

        total = len(records)
        print(f"✅ {total} registros cargados. Iniciando ingesta por lotes de {self.batch_size}...")

        for i in range(0, total, self.batch_size):
            batch = records[i:i + self.batch_size]
            self._process_batch(batch, i, total)
            
        print(f"🎉 Finalizada ingesta de {os.path.basename(file_path)}")

    def _extract_year(self, date_val):
        try:
            if pd.isna(date_val): return 0
            date_str = str(date_val)
            # Intentar extraer 4 dígitos consecutivos
            import re
            match = re.search(r'\b(19|20)\d{2}\b', date_str)
            return int(match.group(0)) if match else 0
        except:
            return 0

    def _process_batch(self, batch: List[Dict[str, Any]], start_idx: int, total: int):
        print(f"📦 Procesando lote {start_idx // self.batch_size + 1} ({start_idx}/{total})...", end="\r")
        
        texts_to_embed = []
        payloads = []
        
        for record in batch:
            # Solo embed de título ya que usualmente no hay abstract en InCites Excel
            text_content = f"Title: {record['title']}"
            texts_to_embed.append(text_content)
            
            payloads.append({
                "paper_id": record["paper_id"],
                "title": record["title"],
                "year": record["year"],
                "doi": record["doi"],
                "source": "InCites",
                "text": text_content
            })

        try:
            embeddings = self.embeddings_model.embed_documents(texts_to_embed)
            self.vector_store.add_documents(payloads, embeddings)
            
            for record in batch:
                # Sincronizamos con el Grafo
                self.graph_store.add_paper({
                    "paper_id": record["paper_id"],
                    "title": record["title"],
                    "year": record["year"],
                    "doi": record["doi"],
                    "authors": record["authors_list"],
                    "source": record["journal"]
                })
        except Exception as e:
            print(f"\n❌ Error en lote {start_idx}: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingesta de registros InCites (Excel) a Qdrant y Neo4j.")
    parser.add_argument("path", help="Ruta al archivo .xlsx o al directorio que contiene los archivos de InCites.")
    parser.add_argument("--batch", type=int, default=30, help="Tamaño del lote (default: 30).")
    
    args = parser.parse_args()
    
    ingestor = InCitesIngestor(batch_size=args.batch)
    
    if os.path.isdir(args.path):
        ingestor.ingest_directory(args.path)
    elif os.path.isfile(args.path):
        ingestor.ingest_file(args.path)
    else:
        print(f"❌ La ruta no existe: {args.path}")
