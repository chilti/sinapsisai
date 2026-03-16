
import os
import sys
import json
from qdrant_client import QdrantClient

# Añadir path raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.vector_store import QdrantStore

def export_matches():
    q_store = QdrantStore(collection_name="snii_authors_vec")
    
    print("🔍 Recuperando investigadores del SNII con matches desde Qdrant...")
    
    # Scroll a través de todos los puntos de la colección
    client = q_store.client
    collection_name = "snii_authors_vec"
    
    matches = []
    offset = None
    
    while True:
        response = client.scroll(
            collection_name=collection_name,
            limit=100,
            with_payload=True,
            with_vectors=False,
            offset=offset
        )
        points, next_offset = response
        
        for p in points:
            payload = p.payload
            # Verificar si tiene algún match
            if payload.get("match_local_orcid") or payload.get("match_orcid_id"):
                matches.append(payload)
                
        offset = next_offset
        if offset is None:
            break
            
    print(f"✅ Se encontraron {len(matches)} investigadores con match semántico.")
    
    # Guardar en JSON
    output_path = os.path.join("data", "snii_semantic_matches.json")
    os.makedirs("data", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)
        
    print(f"📂 Resultados exportados a: {output_path}")

if __name__ == "__main__":
    export_matches()
