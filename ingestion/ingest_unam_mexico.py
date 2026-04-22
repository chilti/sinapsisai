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

# Configuración ClickHouse (Remoto)
CH_HOST = "10.90.0.87"
CH_PORT = 8123
CH_USER = "admin"
CH_PASS = "admin"
CH_DB   = "openalex"

# Configuración Neo4j (Nueva instancia México)
NEO4J_URI = "bolt://localhost:7688"
NEO4J_USER = "neo4j"
NEO4J_PASS = "password123"

UNAM_ID = "https://openalex.org/I8961855"

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
        # Query exhaustiva para producción UNAM
        # Nota: Ajustamos los nombres de columnas según el estándar de OpenAlex en CH
        query = f"""
        SELECT 
            id, doi, title, publication_year, type, cited_by_count, language,
            authorships, concepts, topics, sustainable_development_goals, grants, primary_location
        FROM works
        WHERE has(authorships.institutions.id, '{UNAM_ID}')
        """
        if limit:
            query += f" LIMIT {limit}"
        
        print(f"🔍 Ejecutando consulta en ClickHouse...")
        # Usamos query_json_batches si el volumen es muy grande, o un simple query para empezar
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
        MERGE (p:Work {id: work.id})
        SET p.title = work.title,
            p.doi = work.doi,
            p.year = work.publication_year,
            p.citations = work.cited_by_count,
            p.type = work.type,
            p.language = work.language,
            p.abstract = work.abstract
        
        WITH p, work
        UNWIND work.authorships AS auth
        MERGE (a:Author {id: auth.author.id})
        SET a.name = auth.author.display_name,
            a.orcid = auth.author.orcid
        MERGE (a)-[:AUTHORED]->(p)
        
        WITH p, auth, a
        UNWIND (CASE WHEN auth.institutions IS NOT NULL THEN auth.institutions ELSE [] END) AS inst
        MERGE (i:Institution {id: inst.id})
        SET i.name = inst.display_name,
            i.ror = inst.ror,
            i.country_code = inst.country_code,
            i.type = inst.type
        MERGE (a)-[:AFFILIATED_TO]->(i)
        
        // Relación con País
        WITH i, inst
        WHERE inst.country_code IS NOT NULL
        MERGE (c:Country {name: inst.country_code})
        MERGE (i)-[:LOCATED_IN]->(c)
        
        // Conceptos
        WITH p, work
        UNWIND (CASE WHEN work.concepts IS NOT NULL THEN work.concepts ELSE [] END) AS concept
        MERGE (con:Concept {id: concept.id})
        SET con.name = concept.display_name,
            con.level = concept.level
        MERGE (p)-[:HAS_CONCEPT]->(con)
        
        // Tópicos
        WITH p, work
        UNWIND (CASE WHEN work.topics IS NOT NULL THEN work.topics ELSE [] END) AS topic
        MERGE (t:Topic {id: topic.id})
        SET t.name = topic.display_name,
            t.subfield = topic.subfield.display_name,
            t.field = topic.field.display_name,
            t.domain = topic.domain.display_name
        MERGE (p)-[:HAS_TOPIC]->(t)
        
        // SDGs
        WITH p, work
        UNWIND (CASE WHEN work.sustainable_development_goals IS NOT NULL THEN work.sustainable_development_goals ELSE [] END) AS sdg
        MERGE (s:SDG {id: sdg.id})
        SET s.name = sdg.display_name
        MERGE (p)-[:ADDRESSES]->(s)
        
        // Fuente (Source)
        WITH p, work
        WHERE work.primary_location IS NOT NULL 
          AND work.primary_location.source IS NOT NULL 
          AND work.primary_location.source.id IS NOT NULL
        MERGE (src:Source {id: work.primary_location.source.id})
        SET src.name = work.primary_location.source.display_name,
            src.issn_l = work.primary_location.source.issn_l,
            src.type = work.primary_location.source.type
        MERGE (p)-[:PUBLISHED_IN]->(src)
        
        // Financiadores (Funders)
        WITH p, work
        UNWIND (CASE WHEN work.grants IS NOT NULL THEN work.grants ELSE [] END) AS grant
        MERGE (f:Funder {id: grant.funder})
        SET f.name = grant.funder_display_name
        MERGE (p)-[:FUNDED_BY]->(f)
        """
        
        with self.neo4j_driver.session() as session:
            session.run(cypher, batch=batch)

    def run(self, batch_size=500, limit=None):
        start_time = time.time()
        rows, cols = self.fetch_unam_works(limit=limit)
        total = len(rows)
        print(f"📦 Se recuperaron {total} trabajos. Iniciando ingesta en lotes de {batch_size}...")
        
        batch = []
        count = 0
        for row in rows:
            # Convertir fila (tuple) a dict usando nombres de columnas
            work_dict = dict(zip(cols, row))
            
            # Asegurar que los campos JSON/Array se manejen correctamente si vienen como strings
            for field in ['authorships', 'concepts', 'topics', 'sustainable_development_goals', 'grants', 'primary_location']:
                if isinstance(work_dict.get(field), str):
                    try:
                        work_dict[field] = json.loads(work_dict[field])
                    except:
                        pass
            
            # Reconstruir abstract
            meta = work_dict
            abstract = ""
            if 'abstract_inverted_index' in meta:
                abstract = self.reconstruct_abstract(meta['abstract_inverted_index'])
            elif isinstance(meta.get('abstract'), str):
                abstract = meta['abstract']
            
            work_dict['abstract'] = abstract
            
            batch.append(work_dict)
            
            if len(batch) >= batch_size:
                self.ingest_batch(batch)
                count += len(batch)
                print(f"  -> Ingestados {count}/{total}...")
                batch = []
        
        if batch:
            self.ingest_batch(batch)
            count += len(batch)
            
        end_time = time.time()
        print(f"✅ Ingesta completada. Total: {count} trabajos en {end_time - start_time:.2f}s.")

    def close(self):
        self.neo4j_driver.close()

if __name__ == "__main__":
    ingestor = UNAMIngestor()
    try:
        # Se puede pasar un límite para pruebas, ej: limit=1000
        ingestor.run(batch_size=500)
    finally:
        ingestor.close()
