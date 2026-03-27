import os
from neo4j import GraphDatabase
from qdrant_client import QdrantClient, models

def sync_qdrant():
    # CONFIGURACIÓN
    HOST = "localhost" # Ajustar según necesidad
    NEO4J_URI = f"bolt://{HOST}:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASS = "password123"
    
    QDRANT_HOST = HOST
    QDRANT_PORT = 6333
    QDRANT_COLLECTION = "api_papers"
    
    print(f"🚀 Iniciando SINCRONIZACIÓN QDRANT -> NEO4J...")
    
    try:
        # 1. Obtener todos los DOIs válidos de Neo4j
        print("🔍 Consultando DOIs válidos en Neo4j...")
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
        with driver.session() as session:
            res = session.run("MATCH (p:Paper) RETURN p.doi as doi")
            valid_dois = {r['doi'].lower() for r in res if r['doi']}
        driver.close()
        print(f"✅ Encontrados {len(valid_dois)} papers válidos en Neo4j.")

        # 2. Escanear Qdrant y detectar huérfanos
        q_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        print(f"📡 Escaneando puntos en Qdrant (Colección: {QDRANT_COLLECTION})...")
        
        orphans = []
        next_offset = None
        scanned = 0
        
        while True:
            # Scroll para iterar por todos los puntos
            points, next_offset = q_client.scroll(
                collection_name=QDRANT_COLLECTION,
                limit=10000,
                with_payload=True,
                with_vectors=False,
                offset=next_offset
            )
            
            for p in points:
                scanned += 1
                p_doi = p.payload.get("doi", "").lower()
                if p_doi not in valid_dois:
                    orphans.append(p.id)
            
            if scanned % 50000 == 0:
                print(f"   ... Escaneados {scanned} puntos. Huérfanos detectados: {len(orphans)}")
            
            if not next_offset:
                break
        
        print(f"✅ Escaneo completado. Total escaneados: {scanned}. Huérfanos encontrados: {len(orphans)}")
        
        # 3. Borrado masivo de huérfanos
        if orphans:
            input(f"⚠️ Se van a ELIMINAR {len(orphans)} vectores de Qdrant. Presiona Enter para confirmar...")
            batch_size = 5000
            for i in range(0, len(orphans), batch_size):
                batch = orphans[i:i+batch_size]
                q_client.delete(
                    collection_name=QDRANT_COLLECTION,
                    points_selector=models.PointIdsList(points=batch)
                )
                if (i // batch_size) % 10 == 0:
                    print(f"      🗑️ Borrados {i + len(batch)} / {len(orphans)}...")
            print("✅ Qdrant sincronizado con éxito.")
        else:
            print("✅ Qdrant ya está sincronizado. No se encontraron huérfanos.")

    except Exception as e:
        print(f"❌ Error durante la sincronización: {e}")

if __name__ == "__main__":
    sync_qdrant()
