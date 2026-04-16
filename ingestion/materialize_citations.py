"""
materialize_citations.py (Memory Efficient Version)
──────────────────────────────────────────────────
Crea la relación (p1:Paper)-[:CITES]->(p2:Paper) en Neo4j a partir de
`referenced_works` almacenado en raw_metadata de cada paper.

Refactorizado para ser eficiente en memoria mediante paginación Cypher
y procesamiento por lotes (Streaming).

Uso:
    python ingestion/materialize_citations.py
    python ingestion/materialize_citations.py --chunk 5000 --batch 500
"""

import sys
import os
import json
import ast
import argparse
import time
from typing import List, Dict

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
            try:
                return ast.literal_eval(raw)
            except:
                return {}
    return {}

def materialize_citations(entity_filter: str = None, dry_run: bool = False, chunk_size: int = 5000, batch_size: int = 500):
    graph = Neo4jGraphStore()

    # 1. Contar total de papers a procesar
    print("📋 Calculando total de papers a procesar...")
    with graph.driver.session() as session:
        if entity_filter:
            count_q = """
            MATCH (e:Entity {name: $entity})
            OPTIONAL MATCH (e)-[:HAS_PAPER]->(p1:Paper)
            OPTIONAL MATCH (e)<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p2:Paper)
            WITH collect(p1) + collect(p2) AS all_p
            UNWIND all_p AS p
            RETURN count(DISTINCT p) AS total
            """
            total_papers = session.run(count_q, entity=entity_filter).single()['total']
        else:
            total_papers = session.run("MATCH (p:Paper) RETURN count(p) AS total").single()['total']
    
    print(f"  → Total de papers en el grafo: {total_papers:,}")

    created_total = 0
    skipped_total = 0
    processed_papers = 0

    # 2. Paginación principal (Streaming de papers)
    for skip in range(0, total_papers, chunk_size):
        print(f"\n📦 Procesando bloque {skip:,} - {min(skip+chunk_size, total_papers):,}...")
        
        pairs_to_link = []
        
        with graph.driver.session() as session:
            if entity_filter:
                fetch_q = """
                MATCH (e:Entity {name: $entity})
                OPTIONAL MATCH (e)-[:HAS_PAPER]->(p1:Paper)
                OPTIONAL MATCH (e)<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p2:Paper)
                WITH collect(p1) + collect(p2) AS all_p
                UNWIND all_p AS p
                WITH DISTINCT p
                RETURN p.id AS doi, p.openalex_id AS oa_id, p.raw_metadata AS meta
                SKIP $skip LIMIT $limit
                """
                results = session.run(fetch_q, entity=entity_filter, skip=skip, limit=chunk_size)
            else:
                fetch_q = """
                MATCH (p:Paper)
                RETURN p.id AS doi, p.openalex_id AS oa_id, p.raw_metadata AS meta
                SKIP $skip LIMIT $limit
                """
                results = session.run(fetch_q, skip=skip, limit=chunk_size)

            # 3. Extraer citas del chunk actual
            for row in results:
                processed_papers += 1
                source_id = row['doi']
                source_oa_id = row['oa_id']
                meta = _parse_meta(row['meta'])
                
                # referenced_works es una lista de OpenAlex IDs (https://openalex.org/W...)
                refs = meta.get('referenced_works', [])
                if not isinstance(refs, list): continue
                
                for ref_url in refs:
                    if ref_url:
                        # Guardamos el par (citante_doi, citado_oa_id)
                        pairs_to_link.append({"src": source_id, "ref": ref_url})

        if not pairs_to_link:
            continue

        if dry_run:
            print(f"  [DRY] Se intentarían crear {len(pairs_to_link)} relaciones desde este bloque.")
            continue

        # 4. Inserción por lotes (Streaming de relaciones)
        # Usamos BATCH_SIZE para no saturar las transacciones de Neo4j
        for j in range(0, len(pairs_to_link), batch_size):
            batch = pairs_to_link[j:j+batch_size]
            
            # Query optimizado: busca p2 por OpenAlex ID
            # fallback: busca p2 por id (por si el ID es la URL de OpenAlex)
            cypher_link = """
            UNWIND $pairs AS pair
            MATCH (p1:Paper {id: pair.src})
            MATCH (p2:Paper)
            WHERE p2.openalex_id = pair.ref OR p2.id = pair.ref
            WITH p1, p2
            WHERE p1 <> p2
            MERGE (p1)-[r:CITES]->(p2)
            ON CREATE SET r.created_at = timestamp()
            RETURN count(r) AS n
            """
            
            with graph.driver.session() as session:
                res = session.run(cypher_link, pairs=batch)
                n_created = res.single()["n"]
                created_total += n_created
                skipped_total += len(batch) - n_created
            
            # Reportar progreso
            total_pairs_chunk = len(pairs_to_link)
            progress = min(100, int((j + batch_size) / total_pairs_chunk * 100))
            print(f"  🚀 Vinculando citas del bloque: {progress}% | Creadas: {created_total} | Sin match: {skipped_total}      ", end="\r")

    graph.close()
    print(f"\n\n✨ Finalizado.")
    print(f"   Papers procesados  : {processed_papers:,}")
    print(f"   Relaciones creadas : {created_total:,}")
    print(f"   Citas externas/missing : {skipped_total:,}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Materializa relaciones :CITES entre Paper nodes en Neo4j de forma eficiente.")
    parser.add_argument("--entity",  type=str, default=None, help="Filtrar por entidad")
    parser.add_argument("--dry-run", action="store_true", help="Solo reportar sin modificar BD")
    parser.add_argument("--chunk",   type=int, default=5000, help="Tamaño de bloque de lectura de papers")
    parser.add_argument("--batch",   type=int, default=500,  help="Tamaño de lote de escritura de relaciones")
    args = parser.parse_args()
    
    start_t = time.time()
    materialize_citations(entity_filter=args.entity, dry_run=args.dry_run, 
                          chunk_size=args.chunk, batch_size=args.batch)
    end_t = time.time()
    print(f"⏱️ Tiempo total: {int((end_t - start_t)/60)} min {int((end_t - start_t)%60)} seg")
