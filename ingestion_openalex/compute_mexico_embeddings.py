import os
import json
from neo4j import GraphDatabase
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
import numpy as np
import time

load_dotenv()

# Configuración Neo4j (Nueva instancia México)
NEO4J_URI = "bolt://localhost:7688"
NEO4J_USER = "neo4j"
NEO4J_PASS = os.getenv("NEO4J_PASSWORD_MEXICO", "password123")

# Modelo SPECTER2
#allenai/specter2_base es el modelo base recomendado para papers cientificos
SPECTER_MODEL_NAME = 'allenai/specter2_base'

class MexicoEmbeddingsManager:
    def __init__(self):
        print(f"🔗 Conectando a Neo4j {NEO4J_URI}...")
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        print(f"🧠 Cargando modelo SPECTER2 ({SPECTER_MODEL_NAME})...")
        self.model = SentenceTransformer(SPECTER_MODEL_NAME)

    def close(self):
        self.driver.close()

    def compute_specter_embeddings(self, label, text_fields, embedding_property="embedding", batch_size=2000):
        """
        Calcula embeddings SPECTER2 para una etiqueta y campos específicos usando procesamiento por lotes optimizado.
        """
        query = f"MATCH (n:{label}) WHERE n.{embedding_property} IS NULL RETURN n.id as id, " + \
                ", ".join([f"n.{f} as {f}" for f in text_fields])
        
        with self.driver.session() as session:
            records = list(session.run(query))
        
        if not records:
            print(f"✅ No hay nodos de tipo {label} pendientes de embedding SPECTER2.")
            return

        total = len(records)
        print(f"🚀 Procesando {total:,} nodos de tipo {label} (Batch Size: {batch_size})...")
        
        start_time = time.time()
        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            ids = []
            texts = []
            for r in batch:
                ids.append(r['id'])
                # Formato SPECTER2: Title: [title] [SEP] Abstract: [abstract]
                if len(text_fields) > 1:
                    title = r.get('title', '') or ''
                    abstract = r.get('abstract', '') or ''
                    texts.append(f"{title} [SEP] {abstract}")
                else:
                    texts.append(r.get(text_fields[0], '') or '')
            
            # Calcular embeddings (la 4090 brillará aquí)
            embeddings = self.model.encode(texts, convert_to_numpy=True).tolist()
            
            # Guardar en Neo4j usando la función optimizada para vectores de v5.x
            update_query = f"""
            UNWIND $data AS row
            MATCH (n:{label} {{id: row.id}})
            CALL db.create.setNodeVectorProperty(n, '{embedding_property}', row.embedding)
            """
            data = [{"id": id_val, "embedding": emb} for id_val, emb in zip(ids, embeddings)]
            
            with self.driver.session() as session:
                session.run(update_query, data=data)
            
            elapsed = time.time() - start_time
            processed = i + len(batch)
            rate = processed / elapsed
            eta = (total - processed) / rate / 60
            print(f"  -> {processed:,}/{total:,} | Velocidad: {rate:.1f} nodes/s | ETA: {eta:.1f} min", end="\r")
        print(f"\n✅ Embeddings SPECTER2 para {label} finalizados.")

    def run_fastrp(self):
        """
        Ejecuta FastRP para Author, Institution, Source y Funder.
        """
        print("🛠️ Preparando FastRP en Neo4j (GDS)...")
        
        projection_queries = [
            # Borrar si existe
            "CALL gds.graph.drop('mexico_graph', false)",
            # Crear proyección
            """
            CALL gds.graph.project(
              'mexico_graph',
              ['Author', 'Work', 'Institution', 'Source', 'Funder'],
              {
                AUTHORED: {orientation: 'UNDIRECTED'},
                AFFILIATED_TO: {orientation: 'UNDIRECTED'},
                PUBLISHED_IN: {orientation: 'UNDIRECTED'},
                FUNDED_BY: {orientation: 'UNDIRECTED'}
              }
            )
            """
        ]
        
        fastrp_query = """
        CALL gds.fastRP.write(
          'mexico_graph',
          {
            embeddingDimension: 128,
            writeProperty: 'embedding_fastrp'
          }
        )
        """
        
        with self.driver.session() as session:
            for q in projection_queries:
                session.run(q)
            print("  -> Proyección 'mexico_graph' creada.")
            
            print("  -> Ejecutando FastRP...")
            session.run(fastrp_query)
            print("✅ FastRP completado y guardado en la propiedad 'embedding_fastrp'.")

    def aggregate_country_embeddings(self):
        """
        Calcula el embedding de Country como el promedio de sus Institutions.
        """
        print("🌍 Agregando embeddings para nodos Country...")
        query = """
        MATCH (c:Country)<-[:LOCATED_IN]-(i:Institution)
        WHERE i.embedding_fastrp IS NOT NULL
        WITH c, collect(i.embedding_fastrp) AS embs
        SET c.embedding = apoc.coll.avg(embs)
        """
        # Nota: apoc.coll.avg podría no funcionar directamente para vectores en versiones antiguas
        # Usamos una alternativa Cypher pura si es necesario, o cargamos y promediamos en Python
        
        # Versión Python por seguridad
        fetch_query = """
        MATCH (c:Country)<-[:LOCATED_IN]-(i:Institution)
        WHERE i.embedding_fastrp IS NOT NULL
        RETURN c.name as country, i.embedding_fastrp as emb
        """
        with self.driver.session() as session:
            results = list(session.run(fetch_query))
        
        country_data = {}
        for r in results:
            country = r['country']
            if country not in country_data: country_data[country] = []
            country_data[country].append(r['emb'])
            
        updates = []
        for country, embs in country_data.items():
            avg_emb = np.mean(embs, axis=0).tolist()
            updates.append({"name": country, "embedding": avg_emb})
            
        update_query = """
        UNWIND $data AS row
        MATCH (c:Country {name: row.name})
        SET c.embedding = row.embedding
        """
        with self.driver.session() as session:
            session.run(update_query, data=updates)
        print(f"✅ Agregación completada para {len(updates)} países.")

if __name__ == "__main__":
    manager = MexicoEmbeddingsManager()
    try:
        # 1. SPECTER2 para Works (Título + Abstract)
        # Nota: Asegurarse de que el script de ingesta guarde 'abstract' en el nodo Work si se desea usar aquí
        manager.compute_specter_embeddings("Work", ["title", "abstract"])
        
        # 2. SPECTER2 para Concept, SDG, Topic
        manager.compute_specter_embeddings("Concept", ["name"])
        manager.compute_specter_embeddings("SDG", ["name"])
        manager.compute_specter_embeddings("Topic", ["name"])
        
        # 3. FastRP para la red estructural
        manager.run_fastrp()
        
        # 4. Agregación Geográfica
        manager.aggregate_country_embeddings()
        
    finally:
        manager.close()
