import os
import sys
import uuid
from typing import Set, Dict
from collections import defaultdict
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.vector_store import QdrantStore

def deduplicate_collection(collection_name: str):
    print(f"\n🔍 Iniciando deduplicación en la colección: '{collection_name}'...")
    
    try:
        # Inicializa Qdrant para conectar con el servidor
        store = QdrantStore(collection_name=collection_name)
        client = store.client
    except Exception as e:
        print(f"Error conectando a Qdrant: {e}")
        return

    # Usamos el API de paginación (scroll) de Qdrant para iterar sobre todos los vectores
    offset = None
    seen_identifiers: Dict[str, str] = {} # Mapea "deterministic_id" -> "qdrant_point_id_que_conservaremos"
    points_to_delete = []

    total_scanned = 0

    while True:
        try:
            records, next_page_offset = client.scroll(
                collection_name=collection_name,
                limit=1000,
                offset=offset,
                with_payload=True,
                with_vectors=False
            )
            
            if not records:
                break
                
            for record in records:
                total_scanned += 1
                payload = record.payload or {}
                
                # Identificar de manera única el documento (mismos criterios que vector_store.py)
                unique_str = payload.get("doi")
                if not unique_str or unique_str == "None":
                    unique_str = payload.get("title")
                    
                if not unique_str:
                    continue # Salto si no tiene ni DOI ni título
                    
                deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(unique_str)))
                
                # Si ya habíamos visto este documento exacto antes, agendamos el actual para eliminación
                if deterministic_id in seen_identifiers:
                    points_to_delete.append(record.id)
                else:
                    seen_identifiers[deterministic_id] = record.id

            if next_page_offset is None:
                break
            offset = next_page_offset
            
        except Exception as e:
            print(f"Error durante el scroll en Qdrant: {e}")
            break

    print(f"  -> Total de documentos revisados: {total_scanned}")
    print(f"  -> Documentos duplicados encontrados: {len(points_to_delete)}")

    if points_to_delete:
        print(f"🧹 Eliminando {len(points_to_delete)} duplicados...")
        
        # Qdrant requiere borrar por lotes para no exceder límites de request URL
        batch_size = 500
        for i in range(0, len(points_to_delete), batch_size):
            batch = points_to_delete[i:i + batch_size]
            client.delete(
                collection_name=collection_name,
                points_selector=batch
            )
        print("✅ Deduplicación completada con éxito.")
    else:
        print("✅ La colección está limpia. No se requiere acción.")

if __name__ == "__main__":
    load_dotenv()
    
    # Qdrant en este proyecto usa 2 colecciones principales:
    # 1. api_papers (proveniente de ingest_apis.py)
    # 2. scientific_papers (proveniente de ingest_entity_docs.py)
    
    deduplicate_collection("api_papers")
    deduplicate_collection("scientific_papers")
    
    print("\n🎉 Proceso Global de Deduplicación Vectorial finalizado.")
