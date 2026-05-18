"""
patch_qdrant_payload.py  (#12)
───────────────────────────────
Actualiza el payload de los vectores existentes en Qdrant con los nuevos
campos filtrables: is_oa, oa_status, language, fwci, country_codes,
indexed_in, primary_topic_domain.

Lee los datos de raw_metadata desde Neo4j y los empuja a Qdrant usando
`set_payload()` (no re-embedea, solo enriquece el payload).

Uso:
    python ingestion/patch_qdrant_payload.py
    python ingestion/patch_qdrant_payload.py --dry-run
    python ingestion/patch_qdrant_payload.py --collection scientific_papers
    python ingestion/patch_qdrant_payload.py --collection api_papers
    python ingestion/patch_qdrant_payload.py --both           # ambas colecciones
"""

import sys
import os
import json
import ast
import argparse
import time

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointIdsList, SetPayload

QDRANT_URL  = os.getenv("QDRANT_URL",  "http://localhost:6333")
QDRANT_KEY  = os.getenv("QDRANT_API_KEY", None)
BATCH_SIZE  = 100


def _parse_meta(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return ast.literal_eval(raw)
    return {}


def _extract_payload_fields(raw_meta: dict) -> dict:
    """Extrae los campos filtrables nuevos del raw_metadata."""
    oa = raw_meta.get("open_access") or {}
    return {
        "is_oa":         bool(oa.get("is_oa", False)),
        "oa_status":     oa.get("oa_status", "closed") or "closed",
        "language":      raw_meta.get("language", "en") or "en",
        "fwci":          raw_meta.get("fwci"),
        "country_codes": raw_meta.get("countries", []) or [],
        "indexed_in":    raw_meta.get("indexed_in", []) or [],
        "primary_topic_domain":   raw_meta.get("primary_topic_domain"),
        "primary_topic_field":    raw_meta.get("primary_topic_field"),
        "journal_is_in_doaj":     raw_meta.get("journal_is_in_doaj", False),
        "journal_is_core":        raw_meta.get("journal_is_core", False),
        "is_retracted":           raw_meta.get("is_retracted", False),
        "apc_paid_usd":           raw_meta.get("apc_paid_usd", 0) or 0,
    }


def patch_collection(client: QdrantClient, collection: str,
                     doi_to_fields: dict, dry_run: bool):
    """
    Itera los puntos de la colección y actualiza el payload con doi_to_fields.
    doi_to_fields = {doi: {field: value, ...}}
    """
    print(f"\n📦 Colección: '{collection}'", flush=True)
    updated = 0
    skipped = 0

    offset = None
    while True:
        resp = client.scroll(
            collection_name=collection,
            with_payload=True,
            limit=BATCH_SIZE,
            offset=offset,
        )
        points, next_offset = resp

        if not points:
            break

        for p in points:
            doi = p.payload.get("doi") or p.payload.get("DOI")
            if not doi:
                skipped += 1
                continue
            doi_clean = doi.replace("https://doi.org/", "").lower().strip()
            fields = doi_to_fields.get(doi_clean)
            if not fields:
                skipped += 1
                continue
            if not dry_run:
                client.set_payload(
                    collection_name=collection,
                    payload=fields,
                    points=PointIdsList(points=[p.id]),
                )
            updated += 1

        print(f"  → actualizados={updated}  sin_doi_o_meta={skipped}",
              end="\r", flush=True)

        if next_offset is None:
            break
        offset = next_offset
        time.sleep(0.02)

    print(f"\n  ✅ '{collection}': {updated} actualizados, {skipped} sin match.")
    return updated


def patch_qdrant_payload(collections: list, dry_run: bool = False):
    # 1. Obtener raw_metadata desde Neo4j (todos los papers)
    graph = Neo4jGraphStore()
    print("📋 Leyendo papers desde Neo4j...", flush=True)
    doi_to_fields = {}
    with graph.driver.session() as session:
        result = session.run(
            "MATCH (p:Paper) WHERE p.raw_metadata IS NOT NULL "
            "RETURN p.id AS doi, p.raw_metadata AS meta"
        )
        for row in result:
            doi = row["doi"].replace("https://doi.org/", "").lower().strip()
            try:
                meta = _parse_meta(row["meta"])
                doi_to_fields[doi] = _extract_payload_fields(meta)
            except Exception:
                pass
    graph.close()
    print(f"  → {len(doi_to_fields):,} papers con metadata extraída.", flush=True)

    if dry_run:
        sample = list(doi_to_fields.items())[:3]
        print(f"🔍 DRY-RUN: muestra de campos a actualizar:")
        for doi, fields in sample:
            print(f"   {doi}: {fields}")
        return

    # 2. Conectar a Qdrant
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_KEY, prefer_grpc=False)
    existing = {c.name for c in client.get_collections().collections}

    total = 0
    for col in collections:
        if col not in existing:
            print(f"  ⚠️  Colección '{col}' no existe en Qdrant, saltando.")
            continue
        total += patch_collection(client, col, doi_to_fields, dry_run)

    print(f"\n🎉 Patch de Qdrant completado. Total actualizado: {total}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enriquece el payload de Qdrant con nuevos campos filtrables."
    )
    parser.add_argument("--collection", type=str,  default="scientific_papers",
                        help="Nombre de la colección Qdrant a parchear")
    parser.add_argument("--both",       action="store_true",
                        help="Parchear ambas colecciones: scientific_papers y api_papers")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Mostrar muestra sin modificar Qdrant")
    args = parser.parse_args()

    if args.both:
        cols = ["scientific_papers", "api_papers"]
    else:
        cols = [args.collection]

    patch_qdrant_payload(collections=cols, dry_run=args.dry_run)
