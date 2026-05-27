import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import json
import numpy as np
import uuid
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from database.clickhouse_db import ch_client
from dotenv import load_dotenv
import time

load_dotenv()

# Configuración
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = os.getenv("NEO4J_PASS", "password123")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

class EmbeddingSync:
    def __init__(self):
        print("🔗 Conectando a servicios...")
        self.neo = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        self.qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self.ch = ch_client.get_client()

    def close(self):
        self.neo.close()

    def generate_qdrant_id(self, unique_str):
        if not unique_str or unique_str == "None":
            return None
        return str(uuid.uuid5(uuid.NAMESPACE_URL, unique_str))

    def sync_works_from_neo4j(self, batch_size=5000):
        # Desactivado a petición del usuario: "De momento no me parece interesante calcular fastrp para articulos"
        print("\n📥 [SALTADO] Sincronización de FastRP para artículos desactivada.")
        return

    def sync_academics_from_neo4j(self, batch_size=5000):
        print("\n📥 Sincronizando Académicos desde Neo4j...")
        
        # Obtener IDs existentes en ClickHouse para decidir si insertar o actualizar
        print("🔍 Cargando IDs de académicos existentes en ClickHouse...")
        existing_rows = self.ch.query("SELECT id FROM academics_all").result_rows
        existing_ids = {r[0] for r in existing_rows}
        print(f"  -> {len(existing_ids):,} académicos encontrados en ClickHouse.")
        
        self.ch.command("DROP TABLE IF EXISTS tmp_ac_fastrp_all")
        self.ch.command("""
            CREATE TABLE tmp_ac_fastrp_all (
                id String,
                fastrp Array(Float32)
            ) ENGINE = Memory
        """)
        
        query = "MATCH (n:Author) WHERE n.embedding_fastrp IS NOT NULL RETURN n.id as id, coalesce(n.fullname, n.id, 'SIN NOMBRE') as name, n.embedding_fastrp as fastrp"
        
        insert_batch = []
        update_batch = []
        total_inserts = 0
        total_updates = 0
        
        with self.neo.session() as session:
            result = session.run(query)
            for record in result:
                id_val = record['id']
                name_val = record['name']
                fastrp = record['fastrp'] if record['fastrp'] else []
                
                if id_val in existing_ids:
                    update_batch.append([id_val, fastrp])
                else:
                    insert_batch.append([id_val, name_val, fastrp])
                
                if len(insert_batch) >= batch_size:
                    self.ch.insert("academics_all", insert_batch, column_names=['id', 'name', 'embedding_fastrp'])
                    total_inserts += len(insert_batch)
                    insert_batch = []
                
                if len(update_batch) >= batch_size:
                    self.ch.insert("tmp_ac_fastrp_all", update_batch, column_names=['id', 'fastrp'])
                    total_updates += len(update_batch)
                    update_batch = []
                    
                print(f"  -> Procesados: {total_inserts + total_updates + len(insert_batch) + len(update_batch):,} (Nuevos insertados: {total_inserts:,}, Actualizados en temp: {total_updates:,})", end="\r")
            
            if insert_batch:
                self.ch.insert("academics_all", insert_batch, column_names=['id', 'name', 'embedding_fastrp'])
                total_inserts += len(insert_batch)
            
            if update_batch:
                self.ch.insert("tmp_ac_fastrp_all", update_batch, column_names=['id', 'fastrp'])
                total_updates += len(update_batch)
        
        if total_updates > 0:
            print(f"\n⏳ Aplicando mutación de Académicos en ClickHouse ({total_updates:,} filas)...")
            self.ch.command("DROP TABLE IF EXISTS tmp_ac_fastrp_join")
            self.ch.command("CREATE TABLE tmp_ac_fastrp_join (id String, fastrp Array(Float32), val_exists UInt8) ENGINE = Join(ANY, LEFT, id)")
            self.ch.command("""
                INSERT INTO tmp_ac_fastrp_join
                SELECT id, fastrp, 1
                FROM tmp_ac_fastrp_all
            """)
            
            # Reemplazo de tabla 100% síncrono y fiable en ClickHouse
            self.ch.command("DROP TABLE IF EXISTS academics_all_temp")
            self.ch.command("CREATE TABLE academics_all_temp AS academics_all")
            self.ch.command("""
                INSERT INTO academics_all_temp
                SELECT 
                    id, name, institution, dependency, subdependency, snii_level, orcid, paper_count, citation_count,
                    embedding_nomic, embedding_specter,
                    if(joinGet('tmp_ac_fastrp_join', 'val_exists', id) = 1, joinGet('tmp_ac_fastrp_join', 'fastrp', id), embedding_fastrp) AS embedding_fastrp
                FROM academics_all
            """)
            self.ch.command("DROP TABLE academics_all")
            self.ch.command("RENAME TABLE academics_all_temp TO academics_all")
            self.ch.command("DROP TABLE IF EXISTS tmp_ac_fastrp_join")
            
        self.ch.command("DROP TABLE IF EXISTS tmp_ac_fastrp_all")
        print(f"✅ Académicos OK. (Nuevos insertados: {total_inserts:,}, Actualizados: {total_updates:,})")

    def sync_nomic_from_qdrant(self, batch_size=2000):
        print("\n📥 Sincronizando Nomic desde Qdrant (vía UUID determinista)...")
        df = self.ch.query_df("SELECT id, doi FROM works_academic_all WHERE length(embedding_nomic) = 0")
        total = len(df)
        
        if total == 0:
            print("✅ Todos los artículos ya tienen Nomic.")
            return

        self.ch.command("DROP TABLE IF EXISTS tmp_nomic_all")
        self.ch.command("""
            CREATE TABLE tmp_nomic_all (
                id String,
                nomic Array(Float32)
            ) ENGINE = Memory
        """)

        print(f"🚀 Recuperando vectores de Qdrant en lotes...")
        inserted_count = 0
        for i in range(0, total, batch_size):
            batch_df = df.iloc[i:i+batch_size]
            
            id_map = {}
            uuids = []
            for _, row in batch_df.iterrows():
                unique_str = row['doi'] if row['doi'] and row['doi'] != 'None' else row['id']
                u = self.generate_qdrant_id(unique_str)
                if u:
                    id_map[u] = row['id']
                    uuids.append(u)
            
            try:
                results = self.qdrant.retrieve(
                    collection_name="api_papers",
                    ids=uuids,
                    with_vectors=True
                )
                
                if results:
                    rows = [[id_map[r.id], r.vector] for r in results if r.vector]
                    if rows:
                        self.ch.insert("tmp_nomic_all", rows, column_names=['id', 'nomic'])
                        inserted_count += len(rows)
            except Exception as e:
                print(f"\n  ⚠️ Error recuperando lote de Qdrant: {e}")
            
            print(f"  -> {i+len(batch_df):,}/{total:,} procesados de Qdrant (encontrados: {inserted_count:,}).", end="\r")

        if inserted_count > 0:
            print(f"\n⏳ Aplicando mutación única de Nomic en ClickHouse ({inserted_count:,} vectores)...")
            self.ch.command("DROP TABLE IF EXISTS tmp_nomic_join")
            self.ch.command("CREATE TABLE tmp_nomic_join (id String, nomic Array(Float32), val_exists UInt8) ENGINE = Join(ANY, LEFT, id)")
            self.ch.command("""
                INSERT INTO tmp_nomic_join
                SELECT id, nomic, 1
                FROM tmp_nomic_all
            """)
            
            # Reemplazo de tabla 100% síncrono y fiable en ClickHouse
            self.ch.command("DROP TABLE IF EXISTS works_academic_all_temp")
            self.ch.command("CREATE TABLE works_academic_all_temp AS works_academic_all")
            self.ch.command("""
                INSERT INTO works_academic_all_temp
                SELECT 
                    id, raw_data, doi, title, publication_year, cited_by_count, is_oa, type, updated_date, is_xpac, source_id,
                    author_names, institution_rors, institution_names, primary_topic_id, institution_ids, subfield, field, domain,
                    topic, language, oa_status, fwci, percentile, is_top_10, is_top_1, country_code, source_type, sdg_ids, awards,
                    concept_ids, all_country_codes, apc_paid_usd, apc_list_usd, counts_by_year, is_doaj_indexed, is_doaj_journal,
                    is_core_journal, is_retracted, has_repository_fulltext, license, referenced_works_count, keywords, sdgs,
                    journal_is_in_doaj, journal_is_core, any_repository_has_fulltext,
                    if(joinGet('tmp_nomic_join', 'val_exists', id) = 1, joinGet('tmp_nomic_join', 'nomic', id), embedding_nomic) AS embedding_nomic,
                    embedding_specter,
                    embedding_fastrp
                FROM works_academic_all
            """)
            self.ch.command("DROP TABLE works_academic_all")
            self.ch.command("RENAME TABLE works_academic_all_temp TO works_academic_all")
            self.ch.command("DROP TABLE IF EXISTS tmp_nomic_join")

        self.ch.command("DROP TABLE IF EXISTS tmp_nomic_all")
        print("\n✅ Nomic OK.")

    def compute_academic_semantic_profiles(self):
        print("\n🧠 Calculando Perfiles Semánticos para Académicos (Promedio SPECTER)...")
        df_avg = self.ch.query_df("""
            SELECT 
                pm.openalex_id as id,
                groupArray(embedding_specter) as all_vecs
            FROM works_academic_all wf
            JOIN paper_author_map pm ON (
                wf.id = pm.paper_id 
                OR (pm.paper_id NOT LIKE 'https://%' AND lower(replaceOne(wf.doi, 'https://doi.org/', '')) = lower(pm.paper_id))
            )
            WHERE length(wf.embedding_specter) > 0 AND pm.openalex_id != ''
            GROUP BY id
        """)
        
        print(f"  -> {len(df_avg):,} perfiles semánticos a calcular...")
        rows = []
        for _, row in df_avg.iterrows():
            vecs = [v for v in row['all_vecs'] if len(v) > 0]
            if vecs:
                avg = np.mean(vecs, axis=0).tolist()
                rows.append([row['id'], avg])
        
        if rows:
            self.ch.command("DROP TABLE IF EXISTS tmp_ac_spec_join")
            self.ch.command("CREATE TABLE tmp_ac_spec_join (id String, spec Array(Float32), val_exists UInt8) ENGINE = Join(ANY, LEFT, id)")
            rows_with_flag = [r + [1] for r in rows]
            self.ch.insert("tmp_ac_spec_join", rows_with_flag, column_names=['id', 'spec', 'val_exists'])
            
            # Reemplazo de tabla 100% síncrono y fiable en ClickHouse
            self.ch.command("DROP TABLE IF EXISTS academics_all_temp")
            self.ch.command("CREATE TABLE academics_all_temp AS academics_all")
            self.ch.command("""
                INSERT INTO academics_all_temp
                SELECT 
                    id, name, institution, dependency, subdependency, snii_level, orcid, paper_count, citation_count,
                    embedding_nomic,
                    if(joinGet('tmp_ac_spec_join', 'val_exists', id) = 1, joinGet('tmp_ac_spec_join', 'spec', id), embedding_specter) AS embedding_specter,
                    embedding_fastrp
                FROM academics_all
            """)
            self.ch.command("DROP TABLE academics_all")
            self.ch.command("RENAME TABLE academics_all_temp TO academics_all")
            self.ch.command("DROP TABLE tmp_ac_spec_join")
        print("✅ Perfiles Semánticos OK.")

if __name__ == "__main__":
    sync = EmbeddingSync()
    try:
        sync.sync_works_from_neo4j()
        sync.sync_academics_from_neo4j()
        sync.sync_nomic_from_qdrant()
        sync.compute_academic_semantic_profiles()
    finally:
        sync.close()
