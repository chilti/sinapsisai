"""
materialize_sdg_relations.py
=============================
Materializa los ODS/SDG como nodos `:SDG` y relaciones `[:RELEVANT_TO]`
en Neo4j a partir de la propiedad `sdgs_processed` que ya existe en los nodos `:Paper`.

La propiedad `sdgs_processed` es una lista de IDs enteros (1-17) que OpenAlex
asigna a cada paper. Este script no necesita LLM — solo lee esa lista y crea
el grafo de relaciones.

Diferencia con ingest_sdg.py:
  - ingest_sdg.py usa LLM para clasificar papers SIN sdgs_processed.
  - Este script materializa lo que OpenAlex ya clasificó (sdgs_processed).

Uso:
  python ingestion/materialize_sdg_relations.py [--dry-run] [--batch 500]
"""

import sys
import os
import argparse
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv

load_dotenv()

# ── Mapa oficial de SDGs ───────────────────────────────────────────────────────

SDG_MAP = {
    1:  "No Poverty",
    2:  "Zero Hunger",
    3:  "Good Health and Well-being",
    4:  "Quality Education",
    5:  "Gender Equality",
    6:  "Clean Water and Sanitation",
    7:  "Affordable and Clean Energy",
    8:  "Decent Work and Economic Growth",
    9:  "Industry, Innovation and Infrastructure",
    10: "Reduced Inequalities",
    11: "Sustainable Cities and Communities",
    12: "Responsible Consumption and Production",
    13: "Climate Action",
    14: "Life Below Water",
    15: "Life on Land",
    16: "Peace, Justice and Strong Institutions",
    17: "Partnerships for the Goals",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_sdg_list(raw) -> list[int]:
    """
    Convierte sdgs_processed al formato estándar: lista de int 1-17.
    Acepta: lista de int, lista de strings, JSON string, None.
    """
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if isinstance(raw, (int, float)):
        raw = [raw]
    result = []
    for v in raw:
        try:
            n = int(v)
            if 1 <= n <= 17:
                result.append(n)
        except (ValueError, TypeError):
            pass
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def materialize(batch_size: int = 500, dry_run: bool = False):
    from database.knowledge_graph import Neo4jGraphStore

    neo = Neo4jGraphStore()

    # 1. Crear nodos SDG (idempotente con MERGE)
    if not dry_run:
        print("⚙️  Asegurando nodos :SDG en Neo4j...")
        with neo.driver.session() as session:
            for sdg_id, sdg_name in SDG_MAP.items():
                session.run(
                    """
                    MERGE (s:SDG {id: $sdg_id})
                    ON CREATE SET s.name = $sdg_name, s.short = $short
                    ON MATCH  SET s.name = $sdg_name
                    """,
                    sdg_id=sdg_id,
                    sdg_name=sdg_name,
                    short=f"SDG{sdg_id}",
                )
        print("  ✅ Nodos SDG listos.")

    # 2. Obtener papers con sdgs_processed
    print("\n🔍 Consultando papers con sdgs_processed...")
    with neo.driver.session() as session:
        rows = session.run(
            """
            MATCH (p:Paper)
            WHERE p.sdgs_processed IS NOT NULL
            RETURN p.doi AS doi, p.sdgs_processed AS sdgs
            """
        ).data()

    print(f"  → {len(rows):,} papers con sdgs_processed encontrados.")

    # 3. Crear relaciones RELEVANT_TO
    created = 0
    skipped = 0
    errors = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        
        with neo.driver.session() as session:
            for row in batch:
                doi = row.get("doi")
                sdg_ids = _parse_sdg_list(row.get("sdgs"))

                if not doi or not sdg_ids:
                    skipped += 1
                    continue

                if dry_run:
                    created += len(sdg_ids)
                    continue

                try:
                    session.run(
                        """
                        MATCH (p:Paper {doi: $doi})
                        WITH p
                        UNWIND $sdg_ids AS sdg_id
                        MATCH (s:SDG {id: sdg_id})
                        MERGE (p)-[:RELEVANT_TO]->(s)
                        """,
                        doi=doi,
                        sdg_ids=sdg_ids,
                    )
                    created += len(sdg_ids)
                except Exception as e:
                    errors += 1
                    print(f"  ❌ Error en {doi}: {e}")

        pct = min(100, round((i + len(batch)) / len(rows) * 100))
        print(f"  Progreso: {pct}% — relaciones {'simuladas' if dry_run else 'creadas'}: {created:,}")

    print(f"\n🎉 Proceso completado:")
    print(f"  ✅ Relaciones RELEVANT_TO {'que se crearían' if dry_run else 'creadas/verificadas'}: {created:,}")
    print(f"  ⏭️  Papers sin SDG o sin DOI: {skipped:,}")
    if errors:
        print(f"  ❌ Errores: {errors:,}")


def add_indexes(dry_run: bool):
    """Crea los índices de Neo4j para consultas eficientes sobre SDG."""
    if dry_run:
        return
    try:
        from database.knowledge_graph import Neo4jGraphStore
        neo = Neo4jGraphStore()
        with neo.driver.session() as session:
            # Índice en SDG.id para MERGE rápido
            session.run("CREATE INDEX sdg_id_idx IF NOT EXISTS FOR (s:SDG) ON (s.id)")
            # Índice en SDG.short
            session.run("CREATE INDEX sdg_short_idx IF NOT EXISTS FOR (s:SDG) ON (s.short)")
        print("✅ Índices SDG creados.")
    except Exception as e:
        print(f"⚠️  No se pudo crear índice SDG: {e}")


def main():
    parser = argparse.ArgumentParser(description="Materializa relaciones SDG en Neo4j.")
    parser.add_argument("--dry-run", action="store_true", help="Simula sin escribir en Neo4j.")
    parser.add_argument("--batch", type=int, default=500, help="Tamaño de lote (default 500).")
    args = parser.parse_args()

    if args.dry_run:
        print("🔍 DRY-RUN activado — no se escribirá nada en Neo4j.")

    add_indexes(args.dry_run)
    materialize(batch_size=args.batch, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
