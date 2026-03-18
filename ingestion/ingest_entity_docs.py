import sys
import os
import argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass
from typing import List, Dict, Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import base64
import httpx
from dotenv import load_dotenv
from ingestion.wos_parser import WoSParser
from ingestion.bib_parser import BibParser
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from langchain_openai import OpenAIEmbeddings
import pyalex
from ingestion import openalex_utils

pyalex.config.email = "test@example.com"

load_dotenv()

class EntityDocsIngestor:
    def __init__(self, batch_size: int = 50):
        self.vector_store = QdrantStore(collection_name="scientific_papers")
        self.graph_store = Neo4jGraphStore()
        
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
            http_client=http_client,
            check_embedding_ctx_length=False
        )
        self.batch_size = batch_size

    def ingest_file(self, file_path: str, entity_name: str, skip_existing: bool = False):
        print(f"📂 Cargando archivo: {file_path} para la Entidad: {entity_name}")
        
        if file_path.endswith('.bib'):
            records = BibParser.parse_file(file_path)
        else:
            records = WoSParser.parse_file(file_path)
            
        total = len(records)
        print(f"✅ {total} registros encontrados. Iniciando ingesta por lotes de {self.batch_size}...")

        for i in range(0, total, self.batch_size):
            batch = records[i:i + self.batch_size]
            self._process_batch(batch, i, total, entity_name, skip_existing)
            
        print(f"\n🎉 Ingesta de {file_path} completada con éxito para la entidad '{entity_name}'.")

    def ingest_directory(self, directory_path: str, entity_name: str, skip_existing: bool = False):
        print(f"📂 Escaneando directorio para la Entidad '{entity_name}': {directory_path}")
        if not os.path.isdir(directory_path):
            print(f"❌ Error: {directory_path} no es un directorio válido.")
            return

        files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) 
                 if f.endswith('.txt') or f.endswith('.bib') or f.endswith('.txt.txt')]
        
        if not files:
            print(f"⚠️ No se encontraron archivos de soporte (.txt, .bib) en {directory_path}")
            return

        print(f"🔍 Encontrados {len(files)} archivos para procesar.")
        for file_path in sorted(files):
            try:
                self.ingest_file(file_path, entity_name, skip_existing)
            except Exception as e:
                print(f"❌ Error procesando {file_path}: {e}")

    def _process_batch(self, batch: List[Dict[str, Any]], start_idx: int, total: int, entity_name: str, skip_existing: bool = False):
        print(f"📦 Procesando lote {start_idx // self.batch_size + 1} ({start_idx}/{total})...", end="\r")
        
        filtered_batch = []
        skipped_records = []
        if skip_existing:
            for record in batch:
                id_to_check = record.get('doi') or record.get('paper_id')
                if self.graph_store.check_paper_exists(id_to_check):
                    skipped_records.append(record)
                    continue
                filtered_batch.append(record)
        else:
            filtered_batch = batch

        # Vincular los pre-existentes de todas formas si se indicó entidad
        if skip_existing and entity_name and skipped_records:
            for record in skipped_records:
                if record.get("doi"):
                    self.graph_store.add_entity_paper_link(entity_name, record["doi"])

        if not filtered_batch:
            return

        texts_to_embed = []
        payloads = []
        
        # 1. Traer datos de OpenAlex en lote (con fallback local)
        dois_in_batch = [rec.get('doi') for rec in filtered_batch if rec.get('doi')]
        openalex_data = openalex_utils.get_works_batch(dois_in_batch)
                
        for record in filtered_batch:
            doi = record.get('doi', '').lower()
            
            if doi and doi in openalex_data:
                work = openalex_data[doi]
                record['citations'] = work.get('cited_by_count', record.get('citations', 0))
                record.setdefault('raw_metadata', {})

                # KPIs de impacto
                record['fwci'] = work.get('fwci', None)
                record['open_access'] = work.get('open_access', {})
                if work.get('citation_normalized_percentile'):
                    perc_data = work['citation_normalized_percentile']
                    record['citation_normalized_percentile'] = perc_data.get('value', 0.0)
                    record['is_in_top_1_percent'] = int(perc_data.get('is_in_top_1_percent', False))
                    record['is_in_top_10_percent'] = int(perc_data.get('is_in_top_10_percent', False))
                
                # ... (resto de campos OpenAlex) ...
                
                if not record.get('abstract') and work.get('abstract_inverted_index'):
                    inverted = work.get('abstract_inverted_index')
                    try:
                        abs_len = max(pos for v in inverted.values() for pos in v) + 1
                        abs_list = [""] * abs_len
                        for word, positions in inverted.items():
                            for pos in positions: abs_list[pos] = word
                        record['abstract'] = " ".join(filter(None, abs_list))
                    except Exception: pass

            title_str = record.get('title', 'Unknown Title').strip()
            abs_str = record.get('abstract', '').strip()
            text_content = f"Title: {title_str}\nAbstract: {abs_str}".strip()
            
            if not text_content or len(text_content) < 5:
                text_content = "Documento con metadatos faltantes."
                
            texts_to_embed.append(text_content)
            
            payloads.append({
                "paper_id": record.get("paper_id", ""),
                "title":    record.get("title", ""),
                "year":     record.get("year", 0),
                "doi":      doi,
                "entity":   entity_name,
                "text":     text_content
            })

        try:
            if texts_to_embed:
                embeddings = self.embeddings_model.embed_documents(texts_to_embed)
                self.vector_store.add_documents(payloads, embeddings)
                
                for record in filtered_batch:
                    self.graph_store.add_paper(record)
                    if record.get("doi"):
                        self.graph_store.add_entity_paper_link(entity_name, record["doi"])
        except Exception as e:
            print(f"\n❌ Error en lote {start_idx}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingesta de documentos por Entidad (WoS .txt o .bib)")
    parser.add_argument("path", help="Ruta al archivo (.txt, .bib) o al directorio que contiene los archivos.")
    parser.add_argument("--entity", type=str, required=True, help="Nombre de la Entidad (ej. 'Facultad de Ciencias')")
    parser.add_argument("--batch", type=int, default=20, help="Tamaño del lote (default: 20)")
    parser.add_argument("--skip-existing", action="store_true", help="Saltar artículos que ya existen en la base de datos.")
    
    args = parser.parse_args()
    
    ingestor = EntityDocsIngestor(batch_size=args.batch)
    
    if os.path.exists(args.path):
        if os.path.isdir(args.path):
            ingestor.ingest_directory(args.path, args.entity, args.skip_existing)
        else:
            ingestor.ingest_file(args.path, args.entity, args.skip_existing)
    else:
        print(f"La ruta no existe: {args.path}")
