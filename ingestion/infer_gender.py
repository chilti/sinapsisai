"""
infer_gender.py
───────────────
Infiere el género de los investigadores (:Academic) en Neo4j usando la API de
Genderize.io y lo guarda como propiedades *nuevas* en el nodo, sin sobrescribir
el campo `gender` si ya tiene un valor reportado.

Propiedades que escribe:
  - Academic.gender_inferred  = "male" | "female" | "nonbinary" | null
  - Academic.gender_confidence = 0.0 – 1.0  (probabilidad que devuelve Genderize)
  - Academic.gender_count      = int  (número de observaciones en Genderize DB)

Plan de la API gratuita de Genderize.io:
  - Sin API key  : 100 req/día (cada req puede traer hasta 10 nombres)
  - Con API key  : planes de pago con cuotas más altas
  Pasa --api-key <key> si tienes una.

Uso:
    python ingestion/infer_gender.py
    python ingestion/infer_gender.py --dry-run
    python ingestion/infer_gender.py --api-key TU_KEY
    python ingestion/infer_gender.py --overwrite          # re-inferir aunque ya tenga valor
    python ingestion/infer_gender.py --entity "Instituto de Ciencias Nucleares"
    python ingestion/infer_gender.py --limit 500          # procesar solo los primeros N
"""

import sys
import os
import re
import time
import json
import argparse
import requests

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

GENDERIZE_URL = "https://api.genderize.io"
BATCH_SIZE    = 10      # Genderize acepta hasta 10 nombres por solicitud
SLEEP_BETWEEN = 0.5     # segundos entre batches para no saturar la API

# ─── Extracción del primer nombre ───────────────────────────────────────────

def extract_first_name(full_name: str) -> str | None:
    """
    Extrae el primer nombre de un nombre completo.
    Maneja formatos 'Apellido, Nombre' y 'Nombre Apellido'.
    Devuelve None si el resultado es un número o una sola letra.
    """
    if not full_name or not isinstance(full_name, str):
        return None
    name = full_name.strip()

    # Formato "Apellido, Nombre Segundo"
    if ',' in name:
        parts = name.split(',', 1)
        first = parts[1].strip().split()[0] if len(parts) > 1 else ""
    else:
        # Formato "Nombre Apellido"
        first = name.split()[0]

    # Limpiar caracteres no alfabéticos excepto guión
    first = re.sub(r"[^a-záéíóúüñA-ZÁÉÍÓÚÜÑ\-]", "", first)

    if len(first) <= 1 or first.isdigit():
        return None
    return first

# ─── Llamada a la API ────────────────────────────────────────────────────────

def genderize_batch(names: list[str], api_key: str | None = None) -> dict:
    """
    Llama a Genderize.io para una lista de hasta 10 nombres.
    Retorna {name_lower: {gender, probability, count}} o {} si falla.
    """
    params = [("name[]", n) for n in names]
    if api_key:
        params.append(("apikey", api_key))

    try:
        resp = requests.get(GENDERIZE_URL, params=params, timeout=10)
        if resp.status_code == 429:
            print("\n  ⚠️  Rate limit alcanzado (429). Esperando 60s...", flush=True)
            time.sleep(60)
            resp = requests.get(GENDERIZE_URL, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"\n  ⚠️  Genderize HTTP {resp.status_code}: {resp.text[:100]}", flush=True)
            return {}
        data = resp.json()
        # La API puede devolver dict (1 nombre) o lista (varios)
        if isinstance(data, dict):
            data = [data]
        return {
            item["name"].lower(): {
                "gender":      item.get("gender"),        # "male" | "female" | null
                "probability": item.get("probability"),   # 0.0 – 1.0
                "count":       item.get("count", 0),
            }
            for item in data
        }
    except Exception as e:
        print(f"\n  ⚠️  Error en Genderize: {e}", flush=True)
        return {}

# ─── Script principal ────────────────────────────────────────────────────────

def infer_gender_for_academics(
    api_key:   str  | None = None,
    entity:    str  | None = None,
    dry_run:   bool = False,
    overwrite: bool = False,
    limit:     int  | None = None,
):
    graph = Neo4jGraphStore()

    # Obtener académicos sin género inferido (o todos si --overwrite)
    print("📋 Consultando académicos en Neo4j...", flush=True)
    with graph.driver.session() as session:
        if entity:
            query = """
            MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic)
            RETURN a.name AS name, a.gender AS gender_reported,
                   a.gender_inferred AS gender_inferred
            ORDER BY a.name
            """
            rows = [dict(r) for r in session.run(query, entity=entity)]
        else:
            query = """
            MATCH (a:Academic)
            RETURN a.name AS name, a.gender AS gender_reported,
                   a.gender_inferred AS gender_inferred
            ORDER BY a.name
            """
            rows = [dict(r) for r in session.run(query)]

    if not overwrite:
        rows = [r for r in rows if r.get("gender_inferred") is None]
    if limit:
        rows = rows[:limit]

    total = len(rows)
    print(f"  → {total} académicos a procesar.", flush=True)

    if dry_run:
        print(f"🔍 DRY-RUN: se inferirían {total} géneros. Sin cambios en BD.")
        # Mostrar muestra de primeros nombres extraídos
        for r in rows[:20]:
            fn = extract_first_name(r["name"])
            print(f"    {r['name']:50s} → primer nombre: {fn}")
        graph.close()
        return

    # Procesar en batches de BATCH_SIZE
    updated = skipped = errors = 0

    for i in range(0, total, BATCH_SIZE):
        batch_rows  = rows[i:i + BATCH_SIZE]
        first_names = []
        name_map    = {}  # first_name_lower → full_name

        for r in batch_rows:
            fn = extract_first_name(r["name"])
            if fn:
                fn_lower = fn.lower()
                first_names.append(fn)
                name_map[fn_lower] = r["name"]
            else:
                skipped += 1

        if not first_names:
            continue

        # Deduplicar (varios académicos pueden tener el mismo primer nombre)
        unique_names = list({n.lower(): n for n in first_names}.values())
        result = genderize_batch(unique_names, api_key=api_key)

        # Escribir resultados en Neo4j
        with graph.driver.session() as session:
            for fn_lower, full_name in name_map.items():
                gender_data = result.get(fn_lower)
                if gender_data is None:
                    skipped += 1
                    continue
                try:
                    session.run(
                        """
                        MATCH (a:Academic {name: $name})
                        SET a.gender_inferred  = $gender,
                            a.gender_confidence = $prob,
                            a.gender_count      = $count
                        """,
                        name   = full_name,
                        gender = gender_data["gender"],      # puede ser null
                        prob   = gender_data["probability"],
                        count  = gender_data["count"],
                    )
                    updated += 1
                except Exception as e:
                    print(f"\n  ❌ Error escribiendo {full_name}: {e}", flush=True)
                    errors += 1

        pct = min(100, int((i + BATCH_SIZE) / total * 100))
        print(
            f"  [{pct:3d}%] actualizados={updated}  omitidos={skipped}  errores={errors}",
            end="\r", flush=True,
        )
        time.sleep(SLEEP_BETWEEN)

    graph.close()

    print(f"\n\n✅ Inferencia de género completada.")
    print(f"   Actualizados : {updated}")
    print(f"   Sin datos    : {skipped}  (nombre no reconocido por Genderize)")
    print(f"   Errores      : {errors}")
    print()
    print("📊 Distribución resultante (desde Neo4j):")
    _show_stats()

def _show_stats():
    """Muestra un resumen rápido de géneros en la BD."""
    try:
        graph = Neo4jGraphStore()
        with graph.driver.session() as session:
            result = session.run(
                """
                MATCH (a:Academic)
                RETURN a.gender_inferred AS gender, count(*) AS n
                ORDER BY n DESC
                """
            )
            for row in result:
                label = row["gender"] or "null (no reconocido)"
                print(f"   {label:20s}: {row['n']:>5d}")
        graph.close()
    except Exception as e:
        print(f"   (no se pudo mostrar resumen: {e})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Inferencia de género de :Academic en Neo4j vía Genderize.io"
    )
    parser.add_argument("--api-key",   type=str,  default=None,  help="API key de Genderize.io (opcional, plan de pago)")
    parser.add_argument("--entity",    type=str,  default=None,  help="Filtrar por entidad (ej. 'Instituto de Ciencias Nucleares')")
    parser.add_argument("--dry-run",   action="store_true",      help="Ver qué se haría sin modificar la BD")
    parser.add_argument("--overwrite", action="store_true",      help="Re-inferir aunque ya tenga gender_inferred")
    parser.add_argument("--limit",     type=int,  default=None,  help="Procesar solo los primeros N académicos")
    args = parser.parse_args()

    infer_gender_for_academics(
        api_key   = args.api_key,
        entity    = args.entity,
        dry_run   = args.dry_run,
        overwrite = args.overwrite,
        limit     = args.limit,
    )
