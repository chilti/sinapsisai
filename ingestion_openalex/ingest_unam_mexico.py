import os
import json
import clickhouse_connect
from neo4j import GraphDatabase
from dotenv import load_dotenv
import sys
import time

# Asegurar que el directorio raíz esté en el path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

# Configuración ClickHouse (Remoto desde .env)
CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASS = os.getenv("CH_PASSWORD")
CH_DB   = os.getenv("CH_DATABASE", "rag")

# Configuración Neo4j (Nueva instancia México)
NEO4J_URI = os.getenv("NEO4J_URI_MEXICO", "bolt://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER_MEXICO", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD_MEXICO", "password123")

UNAM_ROR = "https://ror.org/01tmp8f25"

class UNAMIngestor:
    def __init__(self):
        print(f"🔗 Conectando a ClickHouse {CH_HOST}...")
        self.ch_client = clickhouse_connect.get_client(
            host=CH_HOST, 
            port=CH_PORT, 
            username=CH_USER, 
            password=CH_PASS, 
            database=CH_DB
        )
        
        print(f"🔗 Conectando a Neo4j {NEO4J_URI}...")
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        self._init_constraints()

    def _init_constraints(self):
        constraints = [
            "CREATE CONSTRAINT work_id IF NOT EXISTS FOR (w:Work) REQUIRE w.id IS UNIQUE",
            "CREATE CONSTRAINT author_id IF NOT EXISTS FOR (a:Author) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT institution_id IF NOT EXISTS FOR (i:Institution) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT country_id IF NOT EXISTS FOR (c:Country) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT sdg_id IF NOT EXISTS FOR (s:SDG) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT source_id IF NOT EXISTS FOR (s:Source) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT funder_id IF NOT EXISTS FOR (f:Funder) REQUIRE f.id IS UNIQUE"
        ]
        with self.neo4j_driver.session() as session:
            for c in constraints:
                session.run(c)
        print("✅ Restricciones de unicidad inicializadas.")

    def fetch_unam_works(self, limit=None):
        # Query exhaustiva para producción UNAM usando columna ROR (mucho más rápido)
        query = f"""
        SELECT 
            id, doi, title, publication_year, type, cited_by_count, language,
            raw_data
        FROM works
        WHERE has(institution_rors, '{UNAM_ROR}')
        """
        if limit:
            query += f" LIMIT {limit}"
        
        print(f"Connecting to ClickHouse and fetching works...")
        result = self.ch_client.query(query)
        return result.result_rows, result.column_names

    def reconstruct_abstract(self, inverted_index):
        if not inverted_index: return ""
        try:
            abstract_words = {}
            for word, positions in inverted_index.items():
                for pos in positions:
                    abstract_words[pos] = word
            return " ".join([abstract_words[p] for p in sorted(abstract_words.keys())])
        except:
            return ""

    def ingest_batch(self, batch):
        cypher = """
        UNWIND $batch AS work
        WITH work WHERE work.id IS NOT NULL
        MERGE (w:Work {id: work.id})
        SET w.title = work.title,
            w.doi = work.doi,
            w.year = work.publication_year,
            w.citations = work.cited_by_count,
            w.type = work.type,
            w.language = work.language,
            w.abstract = work.abstract
        
        WITH w, work
        UNWIND work.authorships AS auth
        WITH w, work, auth WHERE auth.author IS NOT NULL AND auth.author.id IS NOT NULL
        MERGE (a:Author {id: auth.author.id})
        SET a.name = auth.author.display_name,
            a.orcid = auth.author.orcid
        MERGE (a)-[:AUTHORED]->(w)
        
        WITH w, work, auth, a
        UNWIND (CASE WHEN auth.institutions IS NOT NULL THEN auth.institutions ELSE [] END) AS inst
        WITH w, work, a, inst WHERE inst.id IS NOT NULL
        MERGE (i:Institution {id: inst.id})
        SET i.name = inst.display_name,
            i.ror = inst.ror,
            i.country_code = inst.country_code,
            i.type = inst.type
        MERGE (a)-[:AFFILIATED_TO]->(i)
        
        // Relación con País
        WITH w, work, i, inst
        WHERE inst.country_code IS NOT NULL
        MERGE (c:Country {name: inst.country_code})
        MERGE (i)-[:LOCATED_IN]->(c)
        
        // Conceptos
        WITH w, work
        UNWIND (CASE WHEN work.concepts IS NOT NULL THEN work.concepts ELSE [] END) AS concept
        WITH w, work, concept WHERE concept.id IS NOT NULL
        MERGE (con:Concept {id: concept.id})
        SET con.name = concept.display_name,
            con.level = concept.level
        MERGE (w)-[:HAS_CONCEPT]->(con)
        
        // Tópicos
        WITH w, work
        UNWIND (CASE WHEN work.topics IS NOT NULL THEN work.topics ELSE [] END) AS topic
        WITH w, work, topic WHERE topic.id IS NOT NULL
        MERGE (t:Topic {id: topic.id})
        SET t.name = topic.display_name,
            t.subfield = topic.subfield.display_name,
            t.field = topic.field.display_name,
            t.domain = topic.domain.display_name
        MERGE (w)-[:HAS_TOPIC]->(t)
        
        // SDGs
        WITH w, work
        UNWIND (CASE WHEN work.sustainable_development_goals IS NOT NULL THEN work.sustainable_development_goals ELSE [] END) AS sdg
        WITH w, work, sdg WHERE sdg.id IS NOT NULL
        MERGE (s:SDG {id: sdg.id})
        SET s.name = sdg.display_name
        MERGE (w)-[:ADDRESSES]->(s)
        
        // Fuente (Source)
        WITH w, work
        WHERE work.primary_location IS NOT NULL 
          AND work.primary_location.source IS NOT NULL 
          AND work.primary_location.source.id IS NOT NULL
        MERGE (src:Source {id: work.primary_location.source.id})
        SET src.name = work.primary_location.source.display_name,
            src.issn_l = work.primary_location.source.issn_l,
            src.type = work.primary_location.source.type
        MERGE (w)-[:PUBLISHED_IN]->(src)
        
        // Financiadores
        WITH w, work
        UNWIND (CASE WHEN work.grants IS NOT NULL THEN work.grants ELSE [] END) AS grant
        WITH w, work, grant WHERE grant.funder IS NOT NULL
        MERGE (f:Funder {id: grant.funder})
        SET f.name = grant.funder_display_name
        MERGE (w)-[:FUNDED_BY]->(f)
        """
        
        with self.neo4j_driver.session() as session:
            session.run(cypher, batch=batch)

    def run(self, batch_size=500, limit=None):
        start_time = time.time()
        
        # Query optimizada para producción UNAM usando columna ROR
        query = f"""
        SELECT 
            id, doi, title, publication_year, type, cited_by_count, language,
            raw_data
        FROM works
        WHERE has(institution_rors, '{UNAM_ROR}')
        """
        if limit:
            query += f" LIMIT {limit}"
        
        # Ajustes de seguridad para el servidor
        query += " SETTINGS use_skip_indexes = 0, max_threads = 4"
        
        print(f"🚀 Iniciando ingesta por streaming desde ClickHouse...")
        
        # Usamos query_row_block_stream para procesar por bloques sin saturar la RAM
        batch = []
        count = 0
        
        try:
            # query_row_block_stream devuelve bloques de filas
            with self.ch_client.query_row_block_stream(query) as stream:
                for block in stream:
                    col_names = ['id', 'doi', 'title', 'publication_year', 'type', 'cited_by_count', 'language', 'raw_data']
                    
                    for row in block:
                        # row es una tupla, la convertimos a dict
                        row_dict = dict(zip(col_names, row))
                        
                        try:
                            work_dict = json.loads(row_dict['raw_data'])
                        except:
                            continue
                        
                        # Metadata básica
                        work_dict['publication_year'] = row_dict.get('publication_year') or work_dict.get('publication_year')
                        work_dict['cited_by_count'] = row_dict.get('cited_by_count') or work_dict.get('cited_by_count')
                        
                        # Reconstruir abstract
                        abstract = ""
                        if 'abstract_inverted_index' in work_dict:
                            abstract = self.reconstruct_abstract(work_dict['abstract_inverted_index'])
                        elif isinstance(work_dict.get('abstract'), str):
                            abstract = work_dict['abstract']
                        work_dict['abstract'] = abstract
                        
                        work_dict['grants'] = work_dict.get('grants', [])
                        
                        batch.append(work_dict)
                        
                        if len(batch) >= batch_size:
                            self.ingest_batch(batch)
                            count += len(batch)
                            elapsed = time.time() - start_time
                            rate = count / elapsed if elapsed > 0 else 1
                            print(f"  -> Ingestados {count:,} | Velocidad: {rate:.1f} doc/s", end="\r")
                            batch = []

            if batch:
                self.ingest_batch(batch)
                count += len(batch)
                
            print(f"\n✅ Ingesta completada. Total: {count:,} trabajos en {time.time() - start_time:.2f}s.")
            
        except Exception as e:
            print(f"\n❌ Error durante la ingesta: {e}")

    def close(self):
        self.neo4j_driver.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingesta de producción UNAM desde ClickHouse a Neo4j.")
    parser.add_argument("--limit", type=int, default=None, help="Límite de registros a procesar (para pruebas).")
    parser.add_argument("--batch", type=int, default=500, help="Tamaño del lote para Neo4j (default 500).")
    args = parser.parse_args()

    ingestor = UNAMIngestor()
    try:
        if args.limit:
            print(f"🧪 Modo prueba activado: Límite de {args.limit} registros.")
        ingestor.run(batch_size=args.batch, limit=args.limit)
    finally:
        ingestor.close()
