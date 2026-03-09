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

    def ingest_directory(self, directory_path: str, entity_name: str = None):
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
                self.ingest_file(file_path, entity_name)
            except Exception as e:
                print(f"❌ Error procesando {file_path}: {e}")

    def ingest_file(self, file_path: str, entity_name: str = None):
        print(f"\n📑 Procesando archivo InCites: {file_path}")
        if entity_name: print(f"🏢 Entidad objetivo: {entity_name}")
        
        df = pd.read_excel(file_path)
        df.columns = [c.strip() for c in df.columns]
        
        records = []
        for _, row in df.iterrows():
            doi = str(row.get('DOI', '')).strip()
            if doi.lower() == 'nan': doi = ''
            
            record = {
                "paper_id": str(row.get('Accession Number', '')),
                "title": str(row.get('Article Title', 'No Title')),
                "year": self._extract_year(row.get('Publication Date')),
                "doi": doi,
                "authors_list": str(row.get('Authors', '')).split(';'),
                "journal": str(row.get('Source', ''))
            }
            records.append(record)

        total = len(records)
        print(f"✅ {total} registros cargados. Iniciando ingesta por lotes de {self.batch_size} (con enriquecimiento OpenAlex)...")

        for i in range(0, total, self.batch_size):
            batch = records[i:i + self.batch_size]
            self._process_batch(batch, i, total, entity_name)
            
        print(f"🎉 Finalizada ingesta de {os.path.basename(file_path)}")

    def _extract_year(self, date_val):
        try:
            if pd.isna(date_val): return 0
            date_str = str(date_val)
            import re
            match = re.search(r'\b(19|20)\d{2}\b', date_str)
            return int(match.group(0)) if match else 0
        except:
            return 0

    def _process_batch(self, batch: List[Dict[str, Any]], start_idx: int, total: int, entity_name: str = None):
        print(f"📦 Procesando lote {start_idx // self.batch_size + 1} ({start_idx}/{total})...", end="\r")
        
        # 1. Enriquecimiento OpenAlex (Batch)
        dois_in_batch = [rec.get('doi') for rec in batch if rec.get('doi')]
        openalex_data = {}
        if dois_in_batch:
            try:
                doi_query = "|".join([f"https://doi.org/{d}" for d in dois_in_batch])
                works = pyalex.Works().filter(doi=doi_query).get()
                for w in works:
                    if w.get('doi'):
                        openalex_data[w['doi'].replace("https://doi.org/", "").lower()] = w
            except Exception:
                pass

        texts_to_embed = []
        payloads = []
        
        for record in batch:
            doi = record.get('doi', '').lower()
            
            # Si hay datos de OpenAlex, enriquecer record
            if doi and doi in openalex_data:
                work = openalex_data[doi]
                record['citations'] = work.get('cited_by_count', 0)
                # Copiar campos clave para Neo4j (add_paper los usará)
                record['fwci'] = work.get('fwci')
                record['open_access'] = work.get('open_access', {})
                # ... otros campos se guardan en raw_metadata vía add_paper si se desea, 
                # pero aquí nos enfocamos en lo que add_paper e ingest_entity_docs hacen.
                
                # Abstract desde OpenAlex
                if not record.get('abstract') and work.get('abstract_inverted_index'):
                    inverted = work.get('abstract_inverted_index')
                    try:
                        abs_len = max(pos for v in inverted.values() for pos in v) + 1
                        abs_list = [""] * abs_len
                        for word, positions in inverted.items():
                            for pos in positions: abs_list[pos] = word
                        record['abstract'] = " ".join(filter(None, abs_list))
                    except Exception: pass

            title = record.get('title', 'No Title')
            abstract = record.get('abstract', '')
            text_content = f"Title: {title}\nAbstract: {abstract}".strip()
            texts_to_embed.append(text_content)
            
            payloads.append({
                "paper_id": record["paper_id"],
                "title": title,
                "year": record["year"],
                "doi": record["doi"],
                "entity": entity_name,
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
                    "source": record["journal"],
                    "citations": record.get("citations", 0),
                    "abstract": record.get("abstract", "")
                })
                if entity_name and record.get("doi"):
                    self.graph_store.add_entity_paper_link(entity_name, record["doi"])
        except Exception as e:
            print(f"\n❌ Error en lote {start_idx}: {e}")

if __name__ == "__main__":
    import argparse
    import pyalex as pyalex_lib # Evitar conflicto de nombre
    
    parser = argparse.ArgumentParser(description="Ingesta de registros InCites (Excel) con enriquecimiento OpenAlex.")
    parser.add_argument("path", help="Ruta al archivo .xlsx o al directorio que contiene los archivos de InCites.")
    parser.add_argument("--entity", type=str, default=None, help="Nombre de la entidad (ej. 'UNAM') para vincular los papers.")
    parser.add_argument("--batch", type=int, default=20, help="Tamaño del lote (default: 20).")
    
    args = parser.parse_args()
    
    # Configurar PyAlex si es necesario
    pyalex_lib.config.email = "test@example.com"
    
    ingestor = InCitesIngestor(batch_size=args.batch)
    
    if os.path.isdir(args.path):
        ingestor.ingest_directory(args.path, args.entity)
    elif os.path.isfile(args.path):
        ingestor.ingest_file(args.path, args.entity)
    else:
        print(f"❌ La ruta no existe: {args.path}")
