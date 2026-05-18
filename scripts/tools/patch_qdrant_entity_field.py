"""
patch_qdrant_entity_field.py
============================
Actualizacion de los payloads existentes en Qdrant para agregar el campo `entity`
a los vectores que no lo tienen.

Estrategia:
  1. Consulta Neo4j para obtener el mapeo doi -> entity_name de todos los papers.
  2. Recorre ambas colecciones Qdrant (scientific_papers, api_papers) en batches.
  3. Para cada punto sin campo `entity`, lo actualiza via set_payload().

Uso:
  python ingestion/patch_qdrant_entity_field.py [--dry-run]
"""

import sys
import os
import json
import argparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, IsNullCondition, PayloadField
from dotenv import load_dotenv

load_dotenv()


# ── Configuración ─────────────────────────────────────────────────────────────

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTIONS = ["scientific_papers", "api_papers"]
BATCH_SIZE = 100


# ── 1. Construir mapeo doi → entity desde Neo4j ─────────────────────────────

def build_doi_entity_map() -> dict[str, str]:
    """
    Consulta Neo4j para mapear cada DOI a su entidad UNAM.
    Patrón: Academic -[:AFFILIATED_TO]-> Entity, Academic -[:AUTHORED]-> Paper
    """
    try:
        from database.knowledge_graph import Neo4jGraphStore
        neo = Neo4jGraphStore()
        query = """
        MATCH (e:Entity)<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)
        WHERE p.doi IS NOT NULL AND e.name IS NOT NULL
        RETURN p.doi AS doi, e.name AS entity
        """
        with neo.driver.session() as session:
            result = session.run(query).data()
        
        doi_map = {}
        for row in result:
            doi = row.get("doi", "").strip()
            entity = row.get("entity", "").strip()
            if doi and entity:
                doi_map[doi] = entity
        
        print(f"✅ Neo4j: {len(doi_map):,} DOIs mapeados a entidad.")
        return doi_map

    except Exception as e:
        print(f"❌ Error conectando a Neo4j: {e}")
        return {}


# ── 2. Patch en Qdrant ────────────────────────────────────────────────────────

def patch_collection(client: QdrantClient, collection: str, doi_map: dict, dry_run: bool):
    """Itera todos los puntos de la colección y actualiza los que no tienen `entity`."""

    updated = 0
    skipped_has_entity = 0
    skipped_no_doi = 0
    skipped_no_match = 0
    offset = None

    print(f"\n📦 Procesando colección: {collection}")

    while True:
        # Scroll de todos los puntos
        result = client.scroll(
            collection_name=collection,
            offset=offset,
            limit=BATCH_SIZE,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = result

        if not points:
            break

        for point in points:
            payload = point.payload or {}

            # Ya tiene entity → saltar
            if payload.get("entity"):
                skipped_has_entity += 1
                continue

            doi = payload.get("doi", "").strip()
            if not doi:
                skipped_no_doi += 1
                continue

            entity = doi_map.get(doi)
            if not entity:
                skipped_no_match += 1
                continue

            if not dry_run:
                client.set_payload(
                    collection_name=collection,
                    payload={"entity": entity},
                    points=[point.id],
                )
            updated += 1

        offset = next_offset
        if offset is None:
            break

    print(f"  ✅ Actualizados:         {updated:,}")
    print(f"  ⏭️  Ya tenían entity:    {skipped_has_entity:,}")
    print(f"  ⚠️  Sin DOI en payload:  {skipped_no_doi:,}")
    print(f"  ❓ DOI sin match Neo4j:  {skipped_no_match:,}")
    return updated


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Parchea el campo entity en Qdrant.")
    parser.add_argument("--dry-run", action="store_true", help="Simula cambios sin escribir.")
    args = parser.parse_args()

    if args.dry_run:
        print("🔍 DRY-RUN activado — no se escribirá nada en Qdrant.")

    doi_map = build_doi_entity_map()
    if not doi_map:
        print("No hay datos de Neo4j. Abortando.")
        sys.exit(1)

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    total = 0
    for collection in COLLECTIONS:
        try:
            total += patch_collection(client, collection, doi_map, args.dry_run)
        except Exception as e:
            print(f"  ❌ Error en colección {collection}: {e}")

    verb = "se actualizarían" if args.dry_run else "actualizados"
    print(f"\n🎉 Total de vectores {verb}: {total:,}")


if __name__ == "__main__":
    main()
