"""
materialize_paper_entity_map.py
===============================
Materializa la relación Entidad (Facultad/Instituto) -> Paper en ClickHouse.
A diferencia de paper_author_map, esta tabla representa la producción institucional
indexada directamente en fuentes globales (WoS, Scopus, etc) o identificada vía ROR.
"""
import os
import sys
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))
load_dotenv(str(_THIS.parent / '.env'))

from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client

TABLE = 'paper_entity_map'

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    paper_id          String,
    institution       String,
    institution_ror   String,
    dependency        String,
    dependency_id     String,
    subdependency     String,
    subdependency_id  String,
    paper_title       String,
    paper_year        UInt16,
    citations         UInt32,
    is_wos            UInt8,
    is_scopus         UInt8,
    is_pubmed         UInt8,
    is_openalex       UInt8,
    is_doaj           UInt8,
    is_semantic_scholar UInt8,
    is_dimensions     UInt8,
    is_lens           UInt8,
    source            String
)
ENGINE = ReplacingMergeTree()
ORDER BY (institution_ror, paper_id, dependency_id, subdependency_id)
"""

def materialize():
    client = ch_client.get_client()
    print(f"✅ Asegurando tabla {TABLE}...")
    client.command(DDL)
    
    gs = Neo4jGraphStore()
    # Consulta enriquecida para traer metadatos del Paper
    query = """
    MATCH (e:Entity)-[:PRODUCED]->(p:Paper)
    OPTIONAL MATCH path = (e)-[:PART_OF*0..3]->(i:Institution)
    WITH e, p, i, [n in nodes(path) | n.name] AS h_names, [n in nodes(path) | n.id] AS h_ids
    RETURN 
        p.id AS paper_id,
        p.title AS paper_title,
        p.year AS paper_year,
        p.citations AS citations,
        coalesce(i.ror, i.id) AS institution_ror,
        h_names,
        h_ids,
        p.wos_indexed AS is_wos,
        p.scopus_indexed AS is_scopus,
        p.pubmed_id IS NOT NULL AS is_pubmed,
        p.openalex_id IS NOT NULL AS is_openalex,
        p.dimensions_id IS NOT NULL AS is_dimensions
    """
    
    print("📡 Consultando producción institucional en Neo4j...")
    with gs.driver.session() as session:
        results = session.run(query)
        rows = []
        for r in results:
            h_names = list(reversed(r['h_names']))
            h_ids = list(reversed(r['h_ids']))
            rows.append({
                'paper_id': r['paper_id'],
                'institution': h_names[0] if len(h_names) > 0 else '',
                'institution_ror': r['institution_ror'],
                'dependency': h_names[1] if len(h_names) > 1 else '',
                'dependency_id': h_ids[1] if len(h_ids) > 1 else '',
                'subdependency': h_names[2] if len(h_names) > 2 else '',
                'subdependency_id': h_ids[2] if len(h_ids) > 2 else '',
                'paper_title': r['paper_title'] or '',
                'paper_year': int(r['paper_year'] or 0),
                'citations': int(r['citations'] or 0),
                'is_wos': 1 if r['is_wos'] else 0,
                'is_scopus': 1 if r['is_scopus'] else 0,
                'is_pubmed': 1 if r['is_pubmed'] else 0,
                'is_openalex': 1 if r['is_openalex'] else 0,
                'is_doaj': 0, # Se puede enriquecer después
                'is_semantic_scholar': 0,
                'is_dimensions': 1 if r['is_dimensions'] else 0,
                'is_lens': 0,
                'source': 'Neo4j PRODUCED'
            })
            
        if rows:
            df = pd.DataFrame(rows)
            print(f"📥 Insertando {len(df)} registros en {TABLE}...")
            client.insert_df(TABLE, df)
            print("✅ Hecho.")
        else:
            print("⚠️ No se encontró producción institucional en Neo4j.")

if __name__ == "__main__":
    materialize()

if __name__ == "__main__":
    materialize()
