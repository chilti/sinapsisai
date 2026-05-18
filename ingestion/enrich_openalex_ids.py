"""
enrich_openalex_ids.py
──────────────────────
Enriquece los nodos Person de Neo4j que tienen ORCID o Scopus ID pero carecen
de openalex_id, resolviéndolo contra ClickHouse (tabla `authors`) y, como
fallback, contra la API oficial de OpenAlex (pyalex).

Flujo por académico:
  1. ClickHouse: WHERE orcid = ?
  2. ClickHouse: JSONExtractString(raw_data, 'ids', 'scopus') = ?
  3. pyalex fallback (solo si no se usó --local)

Uso:
  python ingestion/enrich_openalex_ids.py [--local] [--dry-run] [--limit N]

Flags:
  --local     No usa la API oficial de pyalex (solo ClickHouse).
  --dry-run   Muestra qué actualizaría sin escribir en Neo4j.
  --limit N   Procesa solo los primeros N nodos (pruebas).
"""

import os
import sys
import argparse
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client


# ── Resolución de OpenAlex Author ID ──────────────────────────────────────────

def _resolve_openalex_author_id(
    orcid: str,
    scopus_ids: list,
    ch,
    force_local: bool = False
) -> str | None:
    """
    Busca el OpenAlex Author ID para un académico dado su ORCID y/o Scopus IDs.

    Orden:
      1. ClickHouse authors.orcid (columna directa)
      2. ClickHouse authors.raw_data → ids.scopus
      3. pyalex oficial (fallback, omitido con --local)
    """

    # 1. Por ORCID en ClickHouse
    # ClickHouse almacena orcid con URL completa: https://orcid.org/XXXX
    if orcid:
        orcids = [orcid] if isinstance(orcid, str) else orcid
        for o in orcids:
            bare = str(o).strip().replace('https://orcid.org/', '').replace('http://orcid.org/', '')
            if not bare:
                continue
            orcid_url = f"https://orcid.org/{bare}"
            try:
                rows = ch.query(
                    "SELECT id FROM authors WHERE orcid = {orcid:String} LIMIT 1",
                    parameters={'orcid': orcid_url}
                ).result_rows
                if rows:
                    return rows[0][0]
            except Exception as e:
                print(f"    [CH/orcid] Error: {e}")

    # 2. Por Scopus ID en ClickHouse (campo anidado en raw_data JSON)
    for sid in (scopus_ids or []):
        sid_str = str(sid).strip()
        if not sid_str:
            continue
        try:
            rows = ch.query(
                """SELECT id FROM authors
                   WHERE JSONExtractString(raw_data, 'ids', 'scopus') = {sid:String}
                   LIMIT 1""",
                parameters={'sid': sid_str}
            ).result_rows
            if rows:
                return rows[0][0]
        except Exception as e:
            print(f"    [CH/scopus {sid_str}] Error: {e}")

    # 3. Fallback pyalex (API oficial)
    if not force_local:
        try:
            import pyalex
            if orcid:
                orcids = [orcid] if isinstance(orcid, str) else orcid
                for o in orcids:
                    orcid_clean = str(o).strip().replace('https://orcid.org/', '')
                    if not orcid_clean: continue
                    results = pyalex.Authors().filter(orcid=orcid_clean).get()
                    if results:
                        return results[0].get('id')
            for sid in (scopus_ids or []):
                results = pyalex.Authors().filter(
                    ids={'scopus': str(sid).strip()}
                ).get()
                if results:
                    return results[0].get('id')
        except Exception as e:
            print(f"    [pyalex fallback] Error: {e}")

    return None


# ── Consulta Neo4j ─────────────────────────────────────────────────────────────

def fetch_persons_without_oa_id(neo: Neo4jGraphStore, limit: int | None) -> list[dict]:
    """
    Devuelve nodos Person que tienen orcid o scopus_id pero no openalex_id.
    """
    limit_clause = f"LIMIT {limit}" if limit else ""
    query = f"""
    MATCH (p:Person)
    WHERE (p.orcid IS NOT NULL OR p.scopus_id IS NOT NULL)
      AND (p.openalex_id IS NULL OR p.openalex_id = '')
    RETURN p.id        AS pid,
           p.fullname  AS name,
           p.orcid     AS orcid,
           p.scopus_id AS scopus_id
    {limit_clause}
    """
    with neo.driver.session() as session:
        rows = session.run(query).data()
    return rows


# ── Actualización Neo4j ────────────────────────────────────────────────────────

def update_person_openalex_id(neo: Neo4jGraphStore, person_id: str, oa_id: str):
    """Escribe openalex_id en el nodo Person."""
    query = """
    MATCH (p:Person {id: $pid})
    SET p.openalex_id = $oa_id
    """
    with neo.driver.session() as session:
        session.run(query, pid=person_id, oa_id=oa_id)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enriquece nodos Person de Neo4j con openalex_id desde ClickHouse."
    )
    parser.add_argument("--local", action="store_true",
                        help="Solo ClickHouse, sin fallback a la API oficial de pyalex")
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra cambios sin escribir en Neo4j")
    parser.add_argument("--limit", type=int, default=None,
                        help="Número máximo de nodos a procesar (pruebas)")
    args = parser.parse_args()

    print("🔗 Conectando a Neo4j y ClickHouse...")
    neo = Neo4jGraphStore()
    ch  = ch_client.get_client()

    print("🔍 Consultando nodos Person sin openalex_id...")
    persons = fetch_persons_without_oa_id(neo, args.limit)
    total = len(persons)
    print(f"   → {total:,} nodos a procesar.\n")

    encontrados = 0
    no_resueltos = 0

    for i, row in enumerate(persons, 1):
        pid      = row['pid']
        name     = row['name'] or pid
        orcid    = row['orcid'] or ''
        scopus_raw = row['scopus_id'] or ''

        # scopus_id puede ser string "['id1','id2']" o una lista
        if isinstance(scopus_raw, str):
            scopus_ids = [s.strip().strip("'\"") for s in scopus_raw.strip('[]').split(',') if s.strip()]
        elif isinstance(scopus_raw, list):
            scopus_ids = scopus_raw
        else:
            scopus_ids = []

        print(f"[{i}/{total}] {name}")
        print(f"       ORCID={orcid or '—'}  Scopus={scopus_ids or '—'}")

        oa_id = _resolve_openalex_author_id(orcid, scopus_ids, ch, force_local=args.local)

        if oa_id:
            print(f"       ✅ OpenAlex ID: {oa_id}")
            encontrados += 1
            if not args.dry_run:
                update_person_openalex_id(neo, pid, oa_id)
        else:
            print(f"       ❌ No resuelto")
            no_resueltos += 1

        # Pausa cortés para no saturar ClickHouse en lotes grandes
        if i % 50 == 0:
            time.sleep(0.2)

    print(f"\n{'='*60}")
    print(f"✅ Resueltos  : {encontrados:,}")
    print(f"❌ Sin resolver: {no_resueltos:,}")
    if args.dry_run:
        print("⚠️  Modo dry-run: ningún cambio fue escrito en Neo4j.")
    print(f"{'='*60}")

    neo.close()


if __name__ == "__main__":
    main()
