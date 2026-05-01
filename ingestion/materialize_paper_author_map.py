"""
materialize_paper_author_map.py
================================
Extrae de Neo4j todas las relaciones Academic → Paper (AUTHORED) con su
contexto de entidad/institución y las materializa en ClickHouse como la
tabla `paper_author_map`.

Esta tabla es la pieza clave del nuevo pipeline:
    works_flat  JOIN  paper_author_map
    ─────────────────────────────────
    → cálculo directo en CH de métricas por académico/entidad/institución
      sin necesidad de merge Python.

Fuentes en Neo4j:
  - (a:Academic)-[:AUTHORED]->(p:Paper)
  - (a:Academic)-[:AFFILIATED_TO]->(e:Entity)-[:PART_OF]->(inst:Institution)
  - Propiedades del nodo: a.id, a.name, a.orcid, a.openalex_id, a.is_snii,
                          a.siia_url, a.audit_verdict

Uso:
    python ingestion/materialize_paper_author_map.py [--reset]
    --reset: elimina y recrea la tabla antes de insertar (útil para recarga completa)
"""
import os
import sys
import argparse
import re
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

# ── Path setup ─────────────────────────────────────────────────────────────
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))
load_dotenv(str(_THIS.parent / '.env'))

from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client

# ── Constantes ─────────────────────────────────────────────────────────────
TABLE     = 'paper_author_map'
BATCH_NEO = 10_000   # filas a procesar por lote desde Neo4j
BATCH_CH  = 5_000    # filas a insertar por lote en ClickHouse

# Regex para identificar OpenAlex Work IDs (W + dígitos)
_OA_RE = re.compile(r'^W\d+$', re.IGNORECASE)


# ── DDL ────────────────────────────────────────────────────────────────────
DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    paper_id        String,
    academic_name   String,
    academic_id     String,
    orcid           String,
    openalex_id     String,
    entity          String,
    institution     String,
    is_snii         UInt8,
    source          String,
    audit_verdict   String
)
ENGINE = ReplacingMergeTree()
ORDER BY (paper_id, academic_id)
SETTINGS index_granularity = 8192
"""

# Índices para acelerar los JOINs y filtros del dashboard
DDL_INDEXES = [
    f"ALTER TABLE {TABLE} ADD INDEX IF NOT EXISTS idx_academic (academic_name) TYPE bloom_filter(0.01) GRANULARITY 1",
    f"ALTER TABLE {TABLE} ADD INDEX IF NOT EXISTS idx_entity   (entity)        TYPE bloom_filter(0.01) GRANULARITY 1",
    f"ALTER TABLE {TABLE} ADD INDEX IF NOT EXISTS idx_inst     (institution)   TYPE bloom_filter(0.01) GRANULARITY 1",
    f"ALTER TABLE {TABLE} ADD INDEX IF NOT EXISTS idx_orcid    (orcid)         TYPE bloom_filter(0.01) GRANULARITY 1",
]


def _ensure_table(reset: bool = False):
    """Crea la tabla si no existe; si reset=True la elimina primero."""
    client = ch_client.get_client()
    if reset:
        print(f"  ⚠️  --reset: eliminando tabla {TABLE}...")
        client.command(f"DROP TABLE IF EXISTS {TABLE}")
    client.command(DDL)
    for idx_sql in DDL_INDEXES:
        try:
            client.command(idx_sql)
        except Exception:
            pass  # índice ya existe o no soportado en esta versión
    print(f"  ✅ Tabla {TABLE} lista.")


def _count_neo4j_relations(graph_store) -> int:
    """Cuenta el total de relaciones Academic→Paper en Neo4j."""
    with graph_store.driver.session() as session:
        result = session.run("MATCH (a:Academic)-[:AUTHORED]->(p:Paper) RETURN count(*) AS n")
        return result.single()["n"]


_NEO4J_QUERY = """
MATCH (a:Academic)-[:AUTHORED]->(p:Paper)
OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity)
OPTIONAL MATCH (e)-[:PART_OF]->(inst:Institution)
RETURN
    p.id                AS paper_id,
    a.name              AS academic_name,
    a.id                AS academic_id,
    coalesce(a.orcid, '')           AS orcid,
    coalesce(a.openalex_id, '')     AS openalex_id,
    coalesce(e.name, 'Sin Entidad') AS entity,
    coalesce(
        inst.name,
        CASE WHEN e:Institution THEN e.name ELSE 'Sin Institución' END
    )                               AS institution,
    coalesce(a.is_snii, false)      AS is_snii,
    coalesce(a.siia_url, '')        AS siia_url,
    coalesce(a.audit_verdict, '')   AS audit_verdict
ORDER BY a.name
SKIP $skip LIMIT $limit
"""


def _stream_neo4j_pages(graph_store):
    """
    Genera páginas de BATCH_NEO filas desde Neo4j usando SKIP/LIMIT.
    Mantiene el uso de RAM acotado a un lote a la vez.
    """
    skip = 0
    while True:
        with graph_store.driver.session() as session:
            records = [dict(r) for r in session.run(
                _NEO4J_QUERY, skip=skip, limit=BATCH_NEO)]
        if not records:
            break
        yield pd.DataFrame(records)
        skip += BATCH_NEO


def _normalize_paper_id(pid: str) -> str:
    """
    Normaliza el paper_id para que coincida con works_flat:
    - Si es OpenAlex Work ID (W + dígitos) → mayúsculas
    - Si es DOI → normalizar a 'https://doi.org/10.xxx'
    - Otro → retornar tal cual
    """
    if not pid:
        return ''
    s = str(pid).strip()

    # OpenAlex ID corto (ej. "W2898934631")
    short = s.rstrip('/').split('/')[-1]
    if _OA_RE.match(short):
        return short.upper()

    # DOI completo o crudo
    doi = (s
           .replace('https://doi.org/', '')
           .replace('http://doi.org/', '')
           .lower()
           .strip('/'))
    if doi.startswith('10.'):
        return f'https://doi.org/{doi}'

    return s


def _determine_source(row: dict) -> str:
    """Infiere la fuente de ingesta del académico."""
    if row.get('siia_url'):
        return 'siia'
    if row.get('orcid'):
        return 'snii'
    if row.get('openalex_id'):
        return 'ror'
    return 'manual'


def _insert_to_clickhouse(df: pd.DataFrame):
    """Inserta el DataFrame en paper_author_map en lotes."""
    client = ch_client.get_client()
    total  = len(df)
    print(f"  📥 Insertando {total:,} filas en ClickHouse (lotes de {BATCH_CH})...")

    for i in range(0, total, BATCH_CH):
        batch = df.iloc[i:i + BATCH_CH]
        client.insert_df(TABLE, batch)
        pct = min(100, (i + BATCH_CH) * 100 // total)
        print(f"    {pct:3d}%  ({min(i + BATCH_CH, total):,}/{total:,})", end='\r')

    print(f"\n  ✅ {total:,} filas insertadas.")


def _run_final_optimize():
    """OPTIMIZE para activar ReplacingMergeTree y eliminar duplicados."""
    print("  🔄 Optimizando tabla (deduplicación)...")
    ch_client.get_client().command(f"OPTIMIZE TABLE {TABLE} FINAL")
    row = ch_client.query_df(f"SELECT count() AS n FROM {TABLE}").iloc[0]
    print(f"  ✅ Filas finales en {TABLE}: {row['n']:,}")


def _transform_page(df: pd.DataFrame) -> pd.DataFrame:
    """Limpia y normaliza una página de filas de Neo4j."""
    df = df.dropna(subset=['paper_id', 'academic_name']).copy()
    df['paper_id'] = df['paper_id'].apply(_normalize_paper_id)
    df = df[df['paper_id'] != '']   # descartar UUIDs generados cuando no había DOI
    if df.empty:
        return df
    df['is_snii'] = df['is_snii'].apply(lambda x: 1 if x else 0)
    df['source']  = df.apply(_determine_source, axis=1)
    df = df[[
        'paper_id', 'academic_name', 'academic_id',
        'orcid', 'openalex_id',
        'entity', 'institution',
        'is_snii', 'source', 'audit_verdict'
    ]].fillna('').astype(str)
    df['is_snii'] = df['is_snii'].astype('uint8')
    return df


def materialize(reset: bool = False):
    print("=" * 60)
    print(" MATERIALIZANDO paper_author_map")
    print("=" * 60)

    # 1. Preparar tabla en CH
    print("\n[1/3] Preparando tabla ClickHouse...")
    _ensure_table(reset)

    # 2. Streaming paginado Neo4j → transform → insert CH
    graph_store = Neo4jGraphStore()
    total_neo = _count_neo4j_relations(graph_store)
    print(f"\n[2/3] Streaming {total_neo:,} relaciones de Neo4j "
          f"(páginas de {BATCH_NEO:,})...")

    inserted    = 0
    page_num    = 0
    total_pages = -(-total_neo // BATCH_NEO)  # ceiling division

    for page_df in _stream_neo4j_pages(graph_store):
        page_num += 1
        clean = _transform_page(page_df)
        if not clean.empty:
            _insert_to_clickhouse(clean)
            inserted += len(clean)
        print(f"  Página {page_num}/{total_pages} — {inserted:,} filas insertadas")

    if inserted == 0:
        print("  ❌ No se insertaron filas. Verifica la conexión Neo4j.")
        return

    # Resumen
    print("\n" + "=" * 60)
    print(" RESUMEN")
    print("=" * 60)
    sample = ch_client.query_df(f"""
        SELECT institution, entity, count() AS papers, countDistinct(academic_name) AS academics
        FROM {TABLE}
        GROUP BY institution, entity
        ORDER BY papers DESC
        LIMIT 15
    """)
    print(sample.to_string(index=False))
    print("=" * 60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Materializa Neo4j Academic→Paper en ClickHouse paper_author_map')
    parser.add_argument('--reset', action='store_true',
                        help='Eliminar y recrear la tabla antes de insertar')
    args = parser.parse_args()
    materialize(reset=args.reset)
