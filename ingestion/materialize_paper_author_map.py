"""
materialize_paper_author_map.py
================================
Extrae de Neo4j todas las relaciones Academic → Paper (AUTHORED) con su
contexto de entidad/institución y las materializa en ClickHouse como la
tabla `paper_author_map`.

Modos de uso:
  --reset        Elimina y recrea la tabla completa (recarga total).
                 Úsar cuando cambia el esquema o tras migraciones mayores.

  --incremental  Solo inserta relaciones de papers añadidos después del
                 último sync exitoso. Úsar después de correr
                 snii_llm_identity_resolver.py o snii_ror_resolver.py.

  (sin flags)    Inserta todas las relaciones actuales. ReplacingMergeTree
                 elimina duplicados automáticamente. Seguro en cualquier
                 momento pero más lento que --incremental.

Flujo recomendado:
  1. Primera vez:   python materialize_paper_author_map.py --reset
  2. Periódicamente: python materialize_paper_author_map.py --incremental
  3. Tras cambios de esquema: python materialize_paper_author_map.py --reset

Fuentes en Neo4j:
  - (a:Academic)-[:AUTHORED]->(p:Paper)
  - (a)-[:AFFILIATED_TO]->(e:Entity)-[:PART_OF]->(inst:Institution)
  - Propiedades del nodo: a.id, a.name, a.orcid, a.openalex_id, a.is_snii,
                          a.siia_url, a.audit_verdict
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

# Forzar UTF-8 en Windows para evitar errores con emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# ── Constantes ─────────────────────────────────────────────────────────────
TABLE      = 'paper_author_map'
META_TABLE = 'paper_author_map_meta'   # rastrea el último sync exitoso
BATCH_NEO  = 10_000   # filas a procesar por lote desde Neo4j
BATCH_CH   = 5_000    # filas a insertar por lote en ClickHouse

_OA_RE = re.compile(r'^W\d+$', re.IGNORECASE)


# ── DDL ────────────────────────────────────────────────────────────────────
DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    paper_id          String,
    academic_name     String,
    academic_id       String,
    orcid             String,
    openalex_id       String,
    institution       String,
    institution_ror   String,
    dependency        String,
    dependency_id     String,
    subdependency     String,
    subdependency_id  String,
    is_snii           UInt8,
    source            String,
    audit_verdict     String,
    ODS               Array(String)
)
ENGINE = ReplacingMergeTree()
ORDER BY (institution_ror, paper_id, academic_id)
SETTINGS index_granularity = 8192
"""

# Índices para acelerar los JOINs y filtros del dashboard
DDL_INDEXES = [
    f"ALTER TABLE {TABLE} ADD INDEX IF NOT EXISTS idx_academic (academic_name) TYPE bloom_filter(0.01) GRANULARITY 1",
    f"ALTER TABLE {TABLE} ADD INDEX IF NOT EXISTS idx_dep      (dependency)    TYPE bloom_filter(0.01) GRANULARITY 1",
    f"ALTER TABLE {TABLE} ADD INDEX IF NOT EXISTS idx_inst     (institution)   TYPE bloom_filter(0.01) GRANULARITY 1",
    f"ALTER TABLE {TABLE} ADD INDEX IF NOT EXISTS idx_orcid    (orcid)         TYPE bloom_filter(0.01) GRANULARITY 1",
]


DDL_META = f"""
CREATE TABLE IF NOT EXISTS {META_TABLE} (
    sync_ts     DateTime DEFAULT now(),
    mode        String,
    rows_synced UInt64,
    ok          UInt8
)
ENGINE = MergeTree()
ORDER BY sync_ts
"""


def _ensure_table(reset: bool = False):
    """Crea la tabla si no existe; si reset=True la elimina primero."""
    client = ch_client.get_client()
    if reset:
        print(f"  ⚠️  --reset: eliminando tabla {TABLE}...")
        client.command(f"DROP TABLE IF EXISTS {TABLE}")
    client.command(DDL)
    client.command(DDL_META)
    for idx_sql in DDL_INDEXES:
        try:
            client.command(idx_sql)
        except Exception:
            pass
    print(f"  ✅ Tabla {TABLE} lista.")


def _get_last_sync_ts() -> str:
    """
    Retorna el timestamp del último sync exitoso como string ISO,
    o '1970-01-01 00:00:00' si nunca se ha sincronizado.
    """
    try:
        df = ch_client.query_df(
            f"SELECT max(sync_ts) AS ts FROM {META_TABLE} WHERE ok = 1")
        ts = df['ts'].iloc[0]
        if pd.isnull(ts) or str(ts) == 'NaT':
            return '1970-01-01 00:00:00'
        return str(ts)
    except Exception:
        return '1970-01-01 00:00:00'


def _record_sync(mode: str, rows: int, ok: bool):
    """Registra el resultado del sync en la tabla de metadatos."""
    try:
        ch_client.get_client().command(
            f"INSERT INTO {META_TABLE} (mode, rows_synced, ok) "
            f"VALUES ('{mode}', {rows}, {1 if ok else 0})"
        )
    except Exception as e:
        print(f"  ⚠️ No se pudo registrar sync: {e}")


_NEO4J_QUERY = """
MATCH (a:Academic)-[:AUTHORED]->(p:Paper)
OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e)
OPTIONAL MATCH path = (e)-[:PART_OF*0..3]->(i:Institution)
OPTIONAL MATCH (p)-[:ADDRESSES]->(s:SDG)
WITH a, p, e, i, 
     [n in nodes(path) | n.name] AS h_names, 
     [n in nodes(path) | n.id] AS h_ids, 
     collect(DISTINCT s.id) AS ods
RETURN
    coalesce(p.openalex_id, p.id)    AS paper_id,
    a.name                          AS academic_name,
    a.id                            AS academic_id,
    coalesce(a.orcid, '')           AS orcid,
    coalesce(a.openalex_id, '')     AS openalex_id,
    coalesce(i.ror, i.id)           AS institution_ror,
    h_names,
    h_ids,
    coalesce(a.is_snii, false)      AS is_snii,
    coalesce(a.siia_url, '')        AS siia_url,
    coalesce(a.audit_verdict, '')   AS audit_verdict,
    ods                             AS ODS
ORDER BY a.name
SKIP $skip LIMIT $limit
"""


_NEO4J_COUNT = """
MATCH (a:Academic)-[:AUTHORED]->(p:Paper)
RETURN count(*) AS n
"""


def _count_neo4j_relations(graph_store, since: str = '1970-01-01 00:00:00') -> int:
    """Cuenta relaciones Academic→Paper en Neo4j, opcionalmente filtradas por fecha."""
    # Convertir al formato de datetime de Cypher
    since_cy = since.replace(' ', 'T')
    with graph_store.driver.session() as session:
        result = session.run(_NEO4J_COUNT, since=since_cy)
        return result.single()["n"]


def _stream_neo4j_pages(graph_store, since: str = '1970-01-01 00:00:00'):
    """
    Genera páginas de BATCH_NEO filas desde Neo4j usando SKIP/LIMIT.
    Si `since` no es la época, filtra solo papers agregados después de esa fecha.
    """
    since_cy = since.replace(' ', 'T')
    skip = 0
    while True:
        with graph_store.driver.session() as session:
            records = [dict(r) for r in session.run(
                _NEO4J_QUERY, since=since_cy, skip=skip, limit=BATCH_NEO)]
        if not records:
            break
        yield pd.DataFrame(records)
        skip += BATCH_NEO


def _normalize_paper_id(pid: str) -> str:
    """
    Normaliza el paper_id para que coincida con works_seed_mexico (URL completa):
    - Si es W... -> https://openalex.org/W...
    - Si ya es URL -> retornar tal cual (asegurar https)
    - Si es ORCID o basura -> retornar None para filtrar
    """
    if not pid: return None
    s = str(pid).strip()

    # Si es un ORCID (común en errores de Neo4j), lo descartamos como ID de Paper
    if re.match(r'^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$', s):
        return None

    # Caso OpenAlex ID corto o largo
    short = s.rstrip('/').split('/')[-1].upper()
    if short.startswith('W') and short[1:].isdigit():
        return f'https://openalex.org/{short}'
    
    if 'openalex.org/W' in s:
        return s.replace('http://', 'https://')

    return None


_NEO4J_DIAG = """
MATCH (a:Academic)-[:AUTHORED]->(p:Paper)
OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e)
OPTIONAL MATCH path = (e)-[:PART_OF*0..5]->(i:Institution)
RETURN
    coalesce(i.name, 'SIN_INST') AS institution,
    count(*) AS n
ORDER BY n DESC
LIMIT 15
"""

def _run_neo4j_diagnostics(graph_store):
    """Muestra qué devuelve Neo4j para institution antes de materializar."""
    print("\n🔍 Diagnóstico Neo4j — distribución de institution:")
    with graph_store.driver.session() as session:
        results = session.run(_NEO4J_DIAG)
        for r in results:
            print(f"   {r['institution'][:60]:<60} → {r['n']:>7,} relaciones")
    print()


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
    """Limpia y normaliza una página de filas de Neo4j usando la jerarquía en columnas."""
    df = df.dropna(subset=['paper_id', 'academic_name']).copy()
    df['paper_id'] = df['paper_id'].apply(_normalize_paper_id)
    df = df[df['paper_id'].notna()].copy()
    if df.empty:
        return df

    rows = []
    for _, r in df.iterrows():
        # Nodes(path) devuelve el camino desde la Entidad (e) hasta la Institución (i)
        # p.ej. [Subdependency, Dependency, Institution]
        raw_names = r.get('h_names')
        raw_ids   = r.get('h_ids')
        
        h_names = list(reversed(raw_names)) if isinstance(raw_names, list) else []
        h_ids   = list(reversed(raw_ids))   if isinstance(raw_ids, list)   else []
        
        row = {
            'paper_id':         r['paper_id'],
            'academic_name':    r['academic_name'],
            'academic_id':      r['academic_id'],
            'orcid':           r['orcid'],
            'openalex_id':     r['openalex_id'],
            'is_snii':         1 if r['is_snii'] else 0,
            'source':          _determine_source(r),
            'audit_verdict':   r['audit_verdict'],
            'institution_ror': r['institution_ror'],
            'ODS':             r.get('ODS', []),
            'institution':      h_names[0] if len(h_names) > 0 else 'Sin Institución',
            'dependency':       h_names[1] if len(h_names) > 1 else '',
            'dependency_id':    h_ids[1]   if len(h_ids) > 1 else '',
            'subdependency':    h_names[2] if len(h_names) > 2 else '',
            'subdependency_id': h_ids[2]   if len(h_ids) > 2 else '',
        }
        rows.append(row)

    expanded_df = pd.DataFrame(rows)
    return expanded_df.fillna('').astype({'is_snii': 'uint8'})


def materialize(reset: bool = False, incremental: bool = False):
    print("=" * 60)
    print(" MATERIALIZANDO paper_author_map")
    print("=" * 60)

    # 1. Preparar tabla en CH
    print("\n[1/3] Preparando tabla ClickHouse...")
    _ensure_table(reset)

    # Determinar desde cuándo sincronizar
    if incremental:
        # Obtener paper_ids ya existentes en CH para filtrar el diff
        print("  🔄 Modo incremental: cargando paper_ids existentes en CH...")
        existing_df = ch_client.query_df(
            f"SELECT DISTINCT paper_id FROM {TABLE}")
        existing_ids = set(existing_df['paper_id'].tolist()) if not existing_df.empty else set()
        print(f"  ℹ️ {len(existing_ids):,} paper_ids ya en CH (se omitirán duplicados)")
        mode = 'incremental'
    else:
        existing_ids = set()
        mode = 'reset' if reset else 'full'

    # 2. Streaming paginado Neo4j → transform → insert CH
    graph_store = Neo4jGraphStore()
    total_neo = _count_neo4j_relations(graph_store)
    _run_neo4j_diagnostics(graph_store)
    print(f"\n[2/3] Streaming {total_neo:,} relaciones de Neo4j "
          f"(páginas de {BATCH_NEO:,})...")

    if total_neo == 0:
        print("  ℹ️ Sin relaciones en Neo4j.")
        _record_sync(mode, 0, ok=True)
        return

    inserted    = 0
    page_num    = 0
    total_pages = -(-total_neo // BATCH_NEO)
    ok          = True

    try:
        for page_df in _stream_neo4j_pages(graph_store):
            page_num += 1
            clean = _transform_page(page_df)
            # En modo incremental, filtrar rows cuyo paper_id ya existe en CH
            if incremental and existing_ids and not clean.empty:
                clean = clean[~clean['paper_id'].isin(existing_ids)]
            if not clean.empty:
                _insert_to_clickhouse(clean)
                inserted += len(clean)
            print(f"  Página {page_num}/{total_pages} — {inserted:,} filas nuevas")
    except Exception as e:
        print(f"  ❌ Error durante el streaming: {e}")
        ok = False

    if inserted == 0 and not incremental:
        print("  ❌ No se insertaron filas. Verifica la conexión Neo4j.")
        _record_sync(mode, 0, ok=False)
        _run_final_optimize()
    _record_sync(mode, inserted, ok=ok)

    # Resumen
    print("\n" + "=" * 60)
    print(" RESUMEN")
    print("=" * 60)
    sample = ch_client.query_df(f"""
        SELECT institution, dependency, subdependency,
               count() AS papers,
               countDistinct(academic_name) AS academics
        FROM {TABLE}
        GROUP BY institution, dependency, subdependency
        ORDER BY papers DESC
        LIMIT 15
    """)
    print(sample.to_string(index=False))
    print("=" * 60)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Materializa Neo4j Academic→Paper en ClickHouse paper_author_map')
    parser.add_argument('--reset', action='store_true',
                        help='Eliminar y recrear la tabla antes de insertar (recarga completa)')
    parser.add_argument('--incremental', action='store_true',
                        help='Solo insertar relaciones nuevas desde el último sync exitoso')
    args = parser.parse_args()

    if args.reset and args.incremental:
        print("Error: --reset y --incremental son mutuamente excluyentes.")
        sys.exit(1)

    materialize(reset=args.reset, incremental=args.incremental)
