import sys
import os
import argparse

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass
from typing import List, Dict, Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
from ingestion.wos_parser import WoSParser
from ingestion.bib_parser import BibParser
from ingestion.scopus_csv_parser import ScopusCSVParser
from database.vector_store import QdrantStore
from database.knowledge_graph import Neo4jGraphStore
from ingestion import openalex_utils
import json
from lib.llm_utils import get_embeddings_model
from database.clickhouse_db import ch_client
import pandas as pd



load_dotenv()

class EntityDocsIngestor:
    def __init__(self, batch_size: int = 50, save_to_ch: bool = False):
        self.vector_store = QdrantStore(collection_name="scientific_papers")
        self.graph_store = Neo4jGraphStore()
        self.embeddings_model = get_embeddings_model()
        self.batch_size = batch_size
        self.save_to_ch = save_to_ch

    def ingest_file(self, file_path: str, inst_name: str, dep_name: str = "SIN INFORMACIÓN", sub_name: str = "SIN INFORMACIÓN", skip_existing: bool = False):
        print(f"📂 Cargando archivo: {file_path}")
        print(f"   🏢 Jerarquía: {inst_name} -> {dep_name} -> {sub_name}")
        
        if file_path.endswith('.bib'):
            records = BibParser.parse_file(file_path)
        elif file_path.endswith('.csv'):
            print(f"   📊 Formato detectado: CSV de Scopus")
            records = ScopusCSVParser.parse_file(file_path)
        else:
            records = WoSParser.parse_file(file_path)
            
        total = len(records)
        print(f"✅ {total} registros encontrados. Iniciando ingesta por lotes de {self.batch_size}...")

        for i in range(0, total, self.batch_size):
            batch = records[i:i + self.batch_size]
            self._process_batch(batch, i, total, inst_name, dep_name, sub_name, skip_existing)
            
        print(f"\n🎉 Ingesta de {file_path} completada con éxito.")

    def ingest_directory(self, directory_path: str, inst_name: str, dep_name: str = "SIN INFORMACIÓN", sub_name: str = "SIN INFORMACIÓN", skip_existing: bool = False):
        print(f"📂 Escaneando directorio: {directory_path}")
        print(f"   🏢 Jerarquía: {inst_name} -> {dep_name} -> {sub_name}")
        if not os.path.isdir(directory_path):
            print(f"❌ Error: {directory_path} no es un directorio válido.")
            return

        files = [os.path.join(directory_path, f) for f in os.listdir(directory_path)
                 if f.endswith('.txt') or f.endswith('.bib') or f.endswith('.txt.txt') or f.endswith('.csv')]
        
        if not files:
            print(f"⚠️ No se encontraron archivos de soporte (.txt, .bib, .csv) en {directory_path}")
            return

        print(f"🔍 Encontrados {len(files)} archivos para procesar.")
        for file_path in sorted(files):
            try:
                self.ingest_file(file_path, inst_name, dep_name, sub_name, skip_existing)
            except Exception as e:
                print(f"❌ Error procesando {file_path}: {e}")

    def _process_batch(self, batch: List[Dict[str, Any]], start_idx: int, total: int, inst_name: str, dep_name: str, sub_name: str, skip_existing: bool = False):
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
        if skip_existing and inst_name and skipped_records:
            for record in skipped_records:
                doi = record.get("doi")
                if doi:
                    # Vincular a la jerarquía
                    if sub_name != "SIN INFORMACIÓN":
                        self.graph_store.add_hierarchical_entity_paper_link(inst_name, dep_name, sub_name, 'Subdependency', doi)
                    elif dep_name != "SIN INFORMACIÓN":
                        self.graph_store.add_hierarchical_entity_paper_link(inst_name, dep_name, sub_name, 'Dependency', doi)
                    else:
                        self.graph_store.add_hierarchical_entity_paper_link(inst_name, dep_name, sub_name, 'Institution', doi)

        if not filtered_batch:
            return

        texts_to_embed = []
        payloads = []
        
        # 1. Traer datos de OpenAlex en lote (con fallback local)
        dois_in_batch = [rec.get('doi').strip().lower() for rec in filtered_batch if rec.get('doi')]
        openalex_data = openalex_utils.get_works_batch(dois_in_batch)
                
        for record in filtered_batch:
            doi = record.get('doi', '').lower()
            work = None
            
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

                # Extraer campos de tópicos (vienen aplanados de openalex_utils o anidados de la API oficial)
                record['topic_domain'] = work.get('topic_domain')
                record['topic_field'] = work.get('topic_field')
                record['topic_subfield'] = work.get('topic_subfield')
                record['topic_name'] = work.get('topic_name')

                # Fallback para la API oficial (formato anidado)
                if not record['topic_name'] and work.get('topics'):
                    main_t = work.get('topics')[0]
                    record['topic_domain'] = main_t.get('domain', {}).get('display_name')
                    record['topic_field'] = main_t.get('field', {}).get('display_name')
                    record['topic_subfield'] = main_t.get('subfield', {}).get('display_name')
                    record['topic_name'] = main_t.get('display_name')
                
                # Extraer SDGs
                sdgs_list = work.get('sdgs', [])
                if not sdgs_list and work.get('sustainable_development_goals'):
                    sdgs_list = [s.get('display_name') for s in work.get('sustainable_development_goals', []) if s.get('display_name')]
                record['sdgs'] = sdgs_list
                
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
                "institution": inst_name,
                "dependency": dep_name,
                "subdependency": sub_name,
                "text":     text_content
            })

        # 2. Preparar datos para Qdrant (solo lo que no existe)
        dois_in_batch = [d.strip().lower() for d in [rec.get('doi') for rec in filtered_batch] if d]
        # filter_existing_ids espera una lista de dicts: [{"doi": "..."}]
        existing_in_qdrant = self.vector_store.filter_existing_ids([{"doi": d} for d in dois_in_batch])
        missing_in_qdrant = [d for d in dois_in_batch if d not in existing_in_qdrant]
        
        texts_to_embed = []
        payloads = []
                
        for record in filtered_batch:
            doi = record.get('doi', '').lower()
            work = openalex_data.get(doi) if doi else None
            
            if work:
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

                # Extraer campos de tópicos (vienen aplanados de openalex_utils o anidados de la API oficial)
                record['topic_domain'] = work.get('topic_domain')
                record['topic_field'] = work.get('topic_field')
                record['topic_subfield'] = work.get('topic_subfield')
                record['topic_name'] = work.get('topic_name')

                # Fallback para la API oficial (formato anidado)
                if not record['topic_name'] and work.get('topics'):
                    main_t = work.get('topics')[0]
                    record['topic_domain'] = main_t.get('domain', {}).get('display_name')
                    record['topic_field'] = main_t.get('field', {}).get('display_name')
                    record['topic_subfield'] = main_t.get('subfield', {}).get('display_name')
                    record['topic_name'] = main_t.get('display_name')
                
                # Extraer SDGs
                sdgs_list = work.get('sdgs', [])
                if not sdgs_list and work.get('sustainable_development_goals'):
                    sdgs_list = [s.get('display_name') for s in work.get('sustainable_development_goals', []) if s.get('display_name')]
                record['sdgs'] = sdgs_list
                
                if not record.get('abstract') and work.get('abstract_inverted_index'):
                    inverted = work.get('abstract_inverted_index')
                    try:
                        abs_len = max(pos for v in inverted.values() for pos in v) + 1
                        abs_list = [""] * abs_len
                        for word, positions in inverted.items():
                            for pos in positions: abs_list[pos] = word
                        record['abstract'] = " ".join(filter(None, abs_list))
                    except Exception: pass

            # --- Preparación para Qdrant (solo si falta) ---
            if doi in missing_in_qdrant:
                title_str = record.get('title', 'Unknown Title').strip()
                abs_str = record.get('abstract', '').strip()
                text_content = f"Title: {title_str}\nAbstract: {abs_str}".strip()
                
                if not text_content or len(text_content) < 5:
                    text_content = "Documento con metadatos faltantes."
                    
                texts_to_embed.append(text_content)
                
                payloads.append({
                    "paper_id": doi or record.get("paper_id"),
                    "title":    record.get("title", ""),
                    "year":     int(record.get("year", 0)) if record.get("year") else 0,
                    "doi":      doi,
                    "institution": inst_name,
                    "dependency": dep_name,
                    "subdependency": sub_name,
                    "topic":    record.get('topic_name', 'Unknown Topic'),
                    "sdgs":     record.get('sdgs', []),
                    "text":     text_content
                })

        try:
            # 3. Ingesta en Qdrant
            if texts_to_embed:
                embeddings = self.embeddings_model.embed_documents(texts_to_embed)
                self.vector_store.add_documents(payloads, embeddings)
                print(f"      ✅ Se insertaron {len(payloads)} documentos nuevos en Qdrant.")
            else:
                if filtered_batch:
                    print(f"      ⏩ Todos los documentos ya existían en Qdrant.")
                
            # 4. Ingesta en Neo4j (Siempre se intenta el MERGE para asegurar jerarquía)
            for record in filtered_batch:
                doi = record.get("doi", "").lower()
                work = openalex_data.get(doi) if doi else None
                
                row = {
                    "paper_id": doi or record.get("paper_id"),
                    "title": record.get('title'),
                    "year": int(record.get('year', 0)) if record.get('year') else 0,
                    "doi": doi,
                    "citations": int(record.get('citations', 0)) if record.get('citations') else 0,
                    "openalex_id": work.get('id') if work else None,
                    "wos_id": record.get("wos_id"),
                    "scopus_id": record.get("scopus_id"),
                    "fwci": record.get('fwci'),
                    "topic_domain": record.get('topic_domain'),
                    "topic_field": record.get('topic_field'),
                    "topic_subfield": record.get('topic_subfield'),
                    "topic_name": record.get('topic_name'),
                    "sdgs": record.get('sdgs', []),
                    "author_cvu": None,
                    "author_position": None,
                    "is_corresponding": False,
                    "institucion": inst_name,
                    "dependencia": dep_name,
                    "subdependencia": sub_name
                }
                self.graph_store.ingest_paper_row(row)
                
            # Dual Write a ClickHouse
            if self.save_to_ch:
                self._sync_to_clickhouse(filtered_batch, inst_name, dep_name, sub_name)

        except Exception as e:
            print(f"\n❌ Error en lote {start_idx}: {e}")

    def _sync_to_clickhouse(self, batch, inst, dep, sub):
        try:
            rows = []
            for record in batch:
                doi = record.get('doi', '').lower()
                rows.append({
                    'paper_id': doi or record.get('paper_id'),
                    'institution': inst,
                    'institution_ror': '',
                    'dependency': dep,
                    'dependency_id': '',
                    'subdependency': sub,
                    'subdependency_id': '',
                    'paper_title': record.get('title', ''),
                    'paper_year': int(record.get('year', 0)) if record.get('year') else 0,
                    'citations': int(record.get('citations', 0)) if record.get('citations') else 0,
                    'is_wos': 1 if record.get('wos_id') else 0,
                    'is_scopus': 1 if record.get('scopus_id') else 0,
                    'is_openalex': 1 if record.get('fwci') is not None else 0,
                    'source': 'Entity_Docs_Ingest'
                })
            if rows:
                ch = ch_client.get_client()
                ch.insert_df('paper_entity_map', pd.DataFrame(rows))
                print(f"      📊 [ClickHouse] {len(rows)} registros sincronizados.")
        except Exception as e:
            print(f"      [WARN] Error en ClickHouse Sync: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingesta de documentos por Entidad (WoS .txt o .bib)")
    parser.add_argument("path", help="Ruta al archivo (.txt, .bib) o al directorio que contiene los archivos.")
    parser.add_argument("--institution", type=str, required=True, help="Nombre de la Institución")
    parser.add_argument("--dependency", type=str, default="SIN INFORMACIÓN", help="Nombre de la Dependencia")
    parser.add_argument("--subdependency", type=str, default="SIN INFORMACIÓN", help="Nombre de la Subdependencia")
    parser.add_argument("--batch", type=int, default=20, help="Tamaño del lote (default: 20)")
    parser.add_argument("--skip-existing", action="store_true", help="Saltar artículos que ya existen en la base de datos.")
    parser.add_argument("--ch", action="store_true", help="Sincronizar simultáneamente con ClickHouse (paper_entity_map)")
    
    args = parser.parse_args()
    
    ingestor = EntityDocsIngestor(batch_size=args.batch, save_to_ch=args.ch)
    
    if os.path.exists(args.path):
        if os.path.isdir(args.path):
            ingestor.ingest_directory(args.path, args.institution, args.dependency, args.subdependency, args.skip_existing)
        else:
            ingestor.ingest_file(args.path, args.institution, args.dependency, args.subdependency, args.skip_existing)
    else:
        print(f"La ruta no existe: {args.path}")
