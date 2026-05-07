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
NEO4J_URI = "bolt://localhost:7688"
NEO4J_USER = "neo4j"
NEO4J_PASS = os.getenv("NEO4J_PASSWORD_MEXICO", "password123")
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
        print("\n📥 Sincronizando Works desde Neo4j (SPECTER + FastRP)...")
        query = "MATCH (n:Work) WHERE n.embedding IS NOT NULL OR n.embedding_fastrp IS NOT NULL RETURN n.id as id, n.embedding as specter, n.embedding_fastrp as fastrp"
        
        with self.neo.session() as session:
            records = list(session.run(query))
        
        total = len(records)
        print(f"🚀 Procesando {total:,} artículos...")
        
        for i in range(0, total, batch_size):
            batch = records[i:i+batch_size]
            self.ch.command("CREATE TABLE IF NOT EXISTS tmp_work_embs (id String, specter Array(Float32), fastrp Array(Float32)) ENGINE = Memory")
            
            rows = []
            for r in batch:
                specter = r['specter'] if r['specter'] else []
                fastrp = r['fastrp'] if r['fastrp'] else []
                rows.append([r['id'], specter, fastrp])
            
            self.ch.insert("tmp_work_embs", rows, column_names=['id', 'specter', 'fastrp'])
            self.ch.command("""
                ALTER TABLE works_academic_all 
                UPDATE 
                    embedding_specter = (SELECT specter FROM tmp_work_embs WHERE tmp_work_embs.id = works_academic_all.id),
                    embedding_fastrp = (SELECT fastrp FROM tmp_work_embs WHERE tmp_work_embs.id = works_academic_all.id)
                WHERE id IN (SELECT id FROM tmp_work_embs)
            """)
            self.ch.command("DROP TABLE tmp_work_embs")
            print(f"  -> {i+len(batch):,}/{total:,} sincronizados.", end="\r")
        print("\n✅ Neo4j -> CH OK.")

    def sync_academics_from_neo4j(self, batch_size=5000):
        print("\n📥 Poblando academics_all desde Neo4j...")
        query = "MATCH (n:Author) WHERE n.embedding_fastrp IS NOT NULL RETURN n.id as id, n.name as name, n.embedding_fastrp as fastrp"
        
        with self.neo.session() as session:
            records = list(session.run(query))
        
        total = len(records)
        for i in range(0, total, batch_size):
            batch = records[i:i+batch_size]
            rows = []
            for r in batch:
                rows.append([r['id'], r['name'], r['fastrp'] if r['fastrp'] else []])
            self.ch.insert("academics_all", rows, column_names=['id', 'name', 'embedding_fastrp'])
            print(f"  -> {i+len(batch):,}/{total:,} académicos insertados.", end="\r")
        print("\n✅ Académicos OK.")

    def sync_nomic_from_qdrant(self, batch_size=2000):
        print("\n📥 Sincronizando Nomic desde Qdrant (vía UUID determinista)...")
        # Obtenemos DOI e ID para generar el UUID
        df = self.ch.query_df("SELECT id, doi FROM works_academic_all WHERE length(embedding_nomic) = 0")
        total = len(df)
        
        if total == 0:
            print("✅ Todos los artículos ya tienen Nomic.")
            return

        for i in range(0, total, batch_size):
            batch_df = df.iloc[i:i+batch_size]
            
            # Generar mapeo de UUID -> ID Original
            id_map = {}
            uuids = []
            for _, row in batch_df.iterrows():
                # Preferir DOI para el UUID si está disponible (como hace vector_store.py)
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
                    self.ch.command("CREATE TABLE IF NOT EXISTS tmp_nomic (id String, nomic Array(Float32)) ENGINE = Memory")
                    rows = [[id_map[r.id], r.vector] for r in results if r.vector]
                    if rows:
                        self.ch.insert("tmp_nomic", rows, column_names=['id', 'nomic'])
                        self.ch.command("""
                            ALTER TABLE works_academic_all 
                            UPDATE embedding_nomic = (SELECT nomic FROM tmp_nomic WHERE tmp_nomic.id = works_academic_all.id)
                            WHERE id IN (SELECT id FROM tmp_nomic)
                        """)
                        self.ch.command("DROP TABLE tmp_nomic")
            except Exception as e:
                print(f"\n  ⚠️ Error batch {i}: {e}")
            
            print(f"  -> {i+len(batch_df):,}/{total:,} procesados.", end="\r")
        print("\n✅ Nomic OK.")

    def compute_academic_semantic_profiles(self):
        print("\n🧠 Calculando Perfiles Semánticos para Académicos (Promedio SPECTER)...")
        df_avg = self.ch.query_df("""
            SELECT 
                pm.author_id as id,
                groupArray(embedding_specter) as all_vecs
            FROM works_academic_all wf
            JOIN paper_author_map pm ON wf.id = pm.paper_id
            WHERE length(wf.embedding_specter) > 0
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
            self.ch.command("CREATE TABLE IF NOT EXISTS tmp_ac_spec (id String, spec Array(Float32)) ENGINE = Memory")
            self.ch.insert("tmp_ac_spec", rows, column_names=['id', 'spec'])
            self.ch.command("""
                ALTER TABLE academics_all 
                UPDATE embedding_specter = (SELECT spec FROM tmp_ac_spec WHERE tmp_ac_spec.id = academics_all.id)
                WHERE id IN (SELECT id FROM tmp_ac_spec)
            """)
            self.ch.command("DROP TABLE tmp_ac_spec")
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
