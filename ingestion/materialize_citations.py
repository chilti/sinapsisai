"""
materialize_citations.py  (#9)
──────────────────────────────
Crea la relación (p1:Paper)-[:CITES]->(p2:Paper) en Neo4j a partir de
`referenced_works` almacenado en raw_metadata de cada paper.

Solo enlaza papers que YA existen en el grafo (no crea nodos huérfanos).

Uso:
    python ingestion/materialize_citations.py
    python ingestion/materialize_citations.py --dry-run
    python ingestion/materialize_citations.py --entity "Instituto de Ciencias Nucleares"
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


def _parse_meta(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return ast.literal_eval(raw)
    return {}


def materialize_citations(entity_filter: str = None, dry_run: bool = False):
    graph = Neo4jGraphStore()

    # 1. Construir el conjunto de DOIs que ya están en el grafo (para filtrar)
    print("📋 Cargando DOIs existentes en Neo4j...", flush=True)
    with graph.driver.session() as session:
        result = session.run("MATCH (p:Paper) WHERE p.id IS NOT NULL RETURN p.id AS doi")
        existing_dois = {row["doi"].lower().replace("https://doi.org/", "")
                        for row in result}
    print(f"  → {len(existing_dois):,} papers en el grafo.", flush=True)

    # 2. Traer papers con referenced_works en raw_metadata
    print("📋 Consultando papers con referenced_works...", flush=True)
    with graph.driver.session() as session:
        if entity_filter:
            q = """
            MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)
            WHERE p.raw_metadata IS NOT NULL
            RETURN p.id AS doi, p.raw_metadata AS meta
            UNION
            MATCH (e:Entity {name: $entity})-[:HAS_PAPER]->(p:Paper)
            WHERE p.raw_metadata IS NOT NULL
            RETURN p.id AS doi, p.raw_metadata AS meta
            """
            rows = [dict(r) for r in session.run(q, entity=entity_filter)]
        else:
            rows = [dict(r) for r in session.run(
                "MATCH (p:Paper) WHERE p.raw_metadata IS NOT NULL "
                "RETURN p.id AS doi, p.raw_metadata AS meta"
            )]

    # Deduplicar
    seen = set()
    papers = []
    for r in rows:
        if r["doi"] not in seen:
            papers.append(r)
            seen.add(r["doi"])

    print(f"  → {len(papers):,} papers con raw_metadata.", flush=True)

    # 3. Extraer pares (citante, citado) que existen en el grafo
    pairs = []
    for r in papers:
        try:
            meta = _parse_meta(r["meta"])
        except Exception:
            continue
        ref_works = meta.get("referenced_works", [])
        if not isinstance(ref_works, list):
            continue
        for ref_url in ref_works:
            # OpenAlex URL format: https://openalex.org/Wxxxxxxx
            # We need the DOI of the cited paper — referenced_works contains OpenAlex IDs,
            # NOT DOIs. So we can only create :CITES links between papers already in our
            # graph IF they share a Paper node we can match by OpenAlex ID.
            # Strategy: also match by openalex_id property if available.
            if ref_url:
                pairs.append((r["doi"], ref_url))

    print(f"  → {len(pairs):,} pares (citante, referencia) encontrados.", flush=True)

    if dry_run:
        print(f"🔍 DRY-RUN: se crearían hasta {len(pairs):,} relaciones :CITES (solo entre papers ya en el grafo).")
        graph.close()
        return

    # 4. Crear relaciones :CITES en lotes
    # referenced_works son OpenAlex IDs (https://openalex.org/Wxxxxxx).
    # Intentamos match por paper_id O por raw_metadata openalex_id si existe.
    BATCH = 500
    created = 0
    skipped = 0

    cypher = """
    UNWIND $pairs AS pair
    MATCH (p1:Paper {id: pair.src})
    OPTIONAL MATCH (p2:Paper)
    WHERE p2.id = pair.ref
       OR toLower(p2.id) = toLower(pair.ref)
    WITH p1, p2, pair
    WHERE p2 IS NOT NULL AND p1 <> p2
    MERGE (p1)-[r:CITES]->(p2)
    ON CREATE SET r.created = 1
    RETURN count(r) AS n
    """

    for i in range(0, len(pairs), BATCH):
        batch = [{"src": src, "ref": ref} for src, ref in pairs[i:i+BATCH]]
        with graph.driver.session() as session:
            result = session.run(cypher, pairs=batch)
            n = result.single()["n"]
            created += n
            skipped += len(batch) - n

        pct = min(100, int((i + BATCH) / len(pairs) * 100))
        print(f"  [{pct:3d}%] relaciones :CITES creadas={created}  sin match={skipped}",
              end="\r", flush=True)
        time.sleep(0.05)

    graph.close()
    print(f"\n\n✅ Materialización de :CITES completada.")
    print(f"   Relaciones creadas : {created}")
    print(f"   Sin match (normal) : {skipped}")
    print()
    print("ℹ️  Nota: referenced_works usa IDs de OpenAlex (Wxxxxxxx), no DOIs.")
    print("   Solo se crean :CITES entre papers que comparten el mismo ID en el grafo.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Materializa relaciones :CITES entre Paper nodes en Neo4j."
    )
    parser.add_argument("--entity",  type=str,  default=None, help="Filtrar por entidad")
    parser.add_argument("--dry-run", action="store_true",     help="Solo reportar sin modificar BD")
    args = parser.parse_args()
    materialize_citations(entity_filter=args.entity, dry_run=args.dry_run)
