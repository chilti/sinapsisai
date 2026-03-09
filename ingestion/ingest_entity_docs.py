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

    def ingest_directory(self, directory_path: str, entity_name: str):
        print(f"📂 Escaneando directorio para la Entidad '{entity_name}': {directory_path}")
        if not os.path.isdir(directory_path):
            print(f"❌ Error: {directory_path} no es un directorio válido.")
            return

        # Buscamos archivos .txt (WoS) y .bib (BibTeX)
        files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) 
                 if f.endswith('.txt') or f.endswith('.bib') or f.endswith('.txt.txt')]
        
        if not files:
            print(f"⚠️ No se encontraron archivos de soporte (.txt, .bib) en {directory_path}")
            return

        print(f"🔍 Encontrados {len(files)} archivos para procesar.")
        for file_path in sorted(files):
            try:
                self.ingest_file(file_path, entity_name)
            except Exception as e:
                print(f"❌ Error procesando {file_path}: {e}")

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
                        openalex_data[w['doi'].replace("https://doi.org/", "").lower()] = w
            except Exception as e:
                pass
                
        for record in batch:
            doi = record.get('doi', '').lower()
            
            if doi and doi in openalex_data:
                work = openalex_data[doi]
                
                record['citations'] = work.get('cited_by_count', record.get('citations', 0))
                record.setdefault('raw_metadata', {})

                # ── KPIs de impacto ────────────────────────────────────────────
                record['fwci']        = work.get('fwci', None)
                record['open_access'] = work.get('open_access', {})
                if work.get('citation_normalized_percentile'):
                    perc_data = work['citation_normalized_percentile']
                    record['citation_normalized_percentile'] = perc_data.get('value', 0.0)
                    record['is_in_top_1_percent']  = int(perc_data.get('is_in_top_1_percent', False))
                    record['is_in_top_10_percent'] = int(perc_data.get('is_in_top_10_percent', False))
                cyp = work.get('cited_by_percentile_year') or {}
                record['cited_by_percentile_year_min'] = cyp.get('min')
                record['cited_by_percentile_year_max'] = cyp.get('max')

                # ── Trayectoria de citas ────────────────────────────────────────
                record['counts_by_year']        = work.get('counts_by_year', [])
                record['referenced_works_count'] = work.get('referenced_works_count', 0)
                record['referenced_works']      = work.get('referenced_works', [])

                # ── Costes APC ─────────────────────────────────────────────────
                record['apc_paid_usd'] = (work.get('apc_paid') or {}).get('value_usd', 0) or 0
                record['apc_list_usd'] = (work.get('apc_list') or {}).get('value_usd', 0) or 0

                # ── Colaboración e autoría ──────────────────────────────────────
                _auths = work.get('authorships', [])
                record['author_count']             = len(_auths)
                record['countries_distinct_count']  = work.get('countries_distinct_count', 0)
                record['institutions_distinct_count'] = work.get('institutions_distinct_count', 0)
                record['countries'] = list({c for a in _auths for c in a.get('countries', [])})
                record['coauthor_institutions'] = [
                    {
                        'author':   (a.get('author') or {}).get('display_name'),
                        'orcid':    (a.get('author') or {}).get('orcid'),
                        'position': a.get('author_position'),
                        'is_corresponding': a.get('is_corresponding', False),
                        'countries': a.get('countries', []),
                        'institutions': [
                            {'name': i.get('display_name'), 'ror': i.get('ror'),
                             'country': i.get('country_code'), 'type': i.get('type')}
                            for i in a.get('institutions', [])
                        ]
                    }
                    for a in _auths
                ]

                # ── Acceso abierto avanzado ────────────────────────────────────
                _loc = work.get('primary_location') or {}
                record['license']                    = _loc.get('license')
                record['any_repository_has_fulltext'] = (work.get('open_access') or {}).get('any_repository_has_fulltext', False)
                record['oa_url']                     = (work.get('open_access') or {}).get('oa_url')
                record['locations_count']            = work.get('locations_count', 0)

                # ── Indexación y visibilidad ───────────────────────────────────
                record['indexed_in']   = work.get('indexed_in', [])
                record['is_retracted'] = work.get('is_retracted', False)
                record['language']     = work.get('language', 'en')
                record['type']         = work.get('type', 'article')

                # ── Revista / fuente ───────────────────────────────────────────
                _src = _loc.get('source') or {}
                record['journal_is_oa']      = _src.get('is_oa', False)
                record['journal_is_in_doaj'] = _src.get('is_in_doaj', False)
                record['journal_is_core']    = _src.get('is_core', False)
                record['issn']               = _src.get('issn_l')
                record['journal_type']       = _src.get('type')

                # ── Tópico primario (jerarquía completa) ───────────────────────
                pt = work.get('primary_topic') or {}
                record['primary_topic_name']     = pt.get('display_name')
                record['primary_topic_score']    = pt.get('score')
                record['primary_topic_field']    = (pt.get('field') or {}).get('display_name')
                record['primary_topic_subfield'] = (pt.get('subfield') or {}).get('display_name')
                record['primary_topic_domain']   = (pt.get('domain') or {}).get('display_name')

                # ── Topics (hasta 3, con score) ────────────────────────────────
                topics = []
                for t in work.get('topics', []):
                    try:
                        topics.append({
                            'domain':   (t.get('domain') or {}).get('display_name'),
                            'field':    (t.get('field') or {}).get('display_name'),
                            'subfield': (t.get('subfield') or {}).get('display_name'),
                            'topic':    t.get('display_name'),
                            'score':    t.get('score'),
                        })
                    except Exception:
                        pass
                record['OpenAlex_Topics'] = topics

                # ── Keywords (hasta 15) ────────────────────────────────────────
                record['keywords'] = [k.get('display_name') for k in work.get('keywords', [])[:15]]

                # ── ODS desde OpenAlex ─────────────────────────────────────────
                record['sustainable_development_goals'] = [
                    {'id': s.get('id', '').rstrip('/').split('/')[-1],
                     'display_name': s.get('display_name'),
                     'score': s.get('score')}
                    for s in work.get('sustainable_development_goals', [])
                ]

                # ── Abstract desde OpenAlex si falta ──────────────────────────
                if not record.get('abstract') and work.get('abstract_inverted_index'):
                    inverted = work.get('abstract_inverted_index')
                    try:
                        abs_len = max(pos for v in inverted.values() for pos in v) + 1
                        abs_list = [""] * abs_len
                        for word, positions in inverted.items():
                            for pos in positions: abs_list[pos] = word
                        record['abstract'] = " ".join(filter(None, abs_list))
                    except Exception:
                        pass

            title_str = record.get('title', 'Unknown Title').strip()
            abs_str = record.get('abstract', '').strip()
            text_content = f"Title: {title_str}\nAbstract: {abs_str}".strip()
            
            if not text_content or text_content == "Title: Unknown Title\nAbstract:" or len(text_content) < 5:
                text_content = "Documento con metadatos faltantes."
                
            texts_to_embed.append(text_content)
            
            payloads.append({
                "paper_id": record.get("paper_id", ""),
                "title":    record.get("title", ""),
                "year":     record.get("year", 0),
                "doi":      doi,
                "entity":   entity_name,
                "text":     text_content,
                # Campos filtrables para búsqueda semántica
                "is_oa":         (record.get("open_access") or {}).get("is_oa", False),
                "oa_status":     (record.get("open_access") or {}).get("oa_status", "closed"),
                "language":      record.get("language", "en"),
                "fwci":          record.get("fwci"),
                "country_codes": record.get("countries", []),
                "indexed_in":    record.get("indexed_in", []),
                "primary_topic_domain": record.get("primary_topic_domain"),
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
    parser.add_argument("path", help="Ruta al archivo (.txt, .bib) o al directorio que contiene los archivos.")
    parser.add_argument("--entity", type=str, required=True, help="Nombre de la Entidad (ej. 'Facultad de Ciencias')")
    parser.add_argument("--batch", type=int, default=20, help="Tamaño del lote (default: 20)")
    
    args = parser.parse_args()
    
    ingestor = EntityDocsIngestor(batch_size=args.batch)
    
    if os.path.exists(args.path):
        if os.path.isdir(args.path):
            ingestor.ingest_directory(args.path, args.entity)
        else:
            ingestor.ingest_file(args.path, args.entity)
    else:
        print(f"La ruta no existe: {args.path}")
