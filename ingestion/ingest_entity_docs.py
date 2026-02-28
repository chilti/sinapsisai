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

    def ingest_file(self, file_path: str, entity_name: str):
        print(f"📂 Cargando archivo: {file_path} para la Entidad: {entity_name}")
        
        if file_path.endswith('.bib'):
            records = BibParser.parse_file(file_path)
        else:
            records = WoSParser.parse_file(file_path)
            
        total = len(records)
        print(f"✅ {total} registros encontrados. Iniciando ingesta por lotes de {self.batch_size}...")

        for i in range(0, total, self.batch_size):
            batch = records[i:i + self.batch_size]
            self._process_batch(batch, i, total, entity_name)
            
        print(f"\n🎉 Ingesta de {file_path} completada con éxito para la entidad '{entity_name}'.")

    def _process_batch(self, batch: List[Dict[str, Any]], start_idx: int, total: int, entity_name: str):
        print(f"📦 Procesando lote {start_idx // self.batch_size + 1} ({start_idx}/{total})...", end="\r")
        
        texts_to_embed = []
        payloads = []
        
        # 1. Traer datos de OpenAlex en lote
        dois_in_batch = [rec.get('doi') for rec in batch if rec.get('doi')]
        openalex_data = {}
        if dois_in_batch:
            try:
                doi_query = "|".join([f"https://doi.org/{d}" for d in dois_in_batch])
                works = pyalex.Works().filter(doi=doi_query).get()
                for w in works:
                    if w.get('doi'):
                        openalex_data[w['doi'].replace("https://doi.org/", "")] = w
            except Exception as e:
                pass
                
        for record in batch:
            doi = record.get('doi', '')
            
            if doi and doi in openalex_data:
                work = openalex_data[doi]
                
                record['citations'] = work.get('cited_by_count', record.get('citations', 0))
                record.setdefault('raw_metadata', {})
                record['fwci'] = work.get('fwci', None)
                record['open_access'] = work.get('open_access', {})
                if work.get('citation_normalized_percentile'):
                    perc_data = work['citation_normalized_percentile']
                    record['citation_normalized_percentile'] = perc_data.get('value', 0.0)
                    record['is_in_top_1_percent'] = int(perc_data.get('is_in_top_1_percent', False))
                    record['is_in_top_10_percent'] = int(perc_data.get('is_in_top_10_percent', False))
                
                topics = []
                for t in work.get('topics', []):
                    try:
                        topics.append({
                            'domain': t.get('domain', {}).get('display_name'),
                            'field': t.get('field', {}).get('display_name'),
                            'subfield': t.get('subfield', {}).get('display_name'),
                            'topic': t.get('display_name')
                        })
                    except:
                        pass
                record['OpenAlex_Topics'] = topics
                
                if not record.get('abstract') and work.get('abstract_inverted_index'):
                    inverted = work.get('abstract_inverted_index')
                    try:
                        abs_len = max(pos for v in inverted.values() for pos in v) + 1
                        abs_list = [""] * abs_len
                        for word, positions in inverted.items():
                            for pos in positions: abs_list[pos] = word
                        record['abstract'] = " ".join(filter(None, abs_list))
                    except:
                        pass

            title_str = record.get('title', 'Unknown Title').strip()
            abs_str = record.get('abstract', '').strip()
            text_content = f"Title: {title_str}\nAbstract: {abs_str}".strip()
            
            if not text_content or text_content == "Title: Unknown Title\nAbstract:" or len(text_content) < 5:
                text_content = "Documento con metadatos faltantes."
                
            texts_to_embed.append(text_content)
            
            payloads.append({
                "paper_id": record.get("paper_id", ""),
                "title": record.get("title", ""),
                "year": record.get("year", 0),
                "doi": doi,
                "text": text_content
            })

        try:
            # 1. Embeddings y Qdrant
            embeddings = self.embeddings_model.embed_documents(texts_to_embed)
            self.vector_store.add_documents(payloads, embeddings)
            
            # 2. Grafo Neo4j (Nodos, Relaciones generales y de Entidad)
            for record in batch:
                self.graph_store.add_paper(record)
                if record.get("doi"):
                    self.graph_store.add_entity_paper_link(entity_name, record["doi"])
                
        except Exception as e:
            print(f"\n❌ Error en lote {start_idx}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingesta de documentos por Entidad (WoS .txt o .bib)")
    parser.add_argument("--file", type=str, required=True, help="Ruta al archivo WoS .txt o BibTeX .bib")
    parser.add_argument("--entity", type=str, required=True, help="Nombre de la Entidad (ej. 'Facultad de Ciencias')")
    
    args = parser.parse_args()
    
    if os.path.exists(args.file):
        ingestor = EntityDocsIngestor(batch_size=20)
        ingestor.ingest_file(args.file, args.entity)
    else:
        print(f"Archivo no encontrado: {args.file}")
