"""
patch_author_affiliations.py  (#10)
────────────────────────────────────
Enriquece los nodos :Author (coautores externos) en Neo4j con país e institución,
usando el campo `coauthor_institutions` almacenado en raw_metadata de cada paper.

Propiedades que escribe en :Author:
  - country_code       (primera país del primer registro del coautor)
  - country_codes      (lista de todos los países encontrados)
  - institution_name   (nombre de la institución principal)
  - institution_ror    (ROR ID de la institución)
  - institution_type   (education / healthcare / company / etc.)

No modifica nodos :Academic (investigadores propios de UNAM).

Uso:
    python ingestion/patch_author_affiliations.py
    python ingestion/patch_author_affiliations.py --dry-run
    python ingestion/patch_author_affiliations.py --entity "Instituto de Ciencias Nucleares"
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


def patch_author_affiliations(entity_filter: str = None, dry_run: bool = False):
    graph = Neo4jGraphStore()

    # 1. Cargar papers con coauthor_institutions en raw_metadata
    print("📋 Consultando papers con coauthor_institutions...", flush=True)
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
    print(f"  → {len(rows):,} papers leídos.", flush=True)

    # 2. Acumular metadata por ORCID de coautor externo
    # Usamos ORCID como clave primaria (más fiable que nombre)
    # Si no tiene ORCID, usamos nombre como fallback
    orcid_data:  dict = {}   # orcid → affiliation dict
    name_data:   dict = {}   # author_name → affiliation dict (fallback)

    for r in rows:
        try:
            meta = _parse_meta(r["meta"])
        except Exception:
            continue
        coauthors = meta.get("coauthor_institutions", [])
        if not isinstance(coauthors, list):
            continue
        for ca in coauthors:
            if not isinstance(ca, dict):
                continue
            author_name = ca.get("author")
            orcid       = ca.get("orcid")
            countries   = ca.get("countries", []) or []
            institutions = ca.get("institutions", []) or []

            # Construir payload de afiliación
            aff = {
                "country_code":    countries[0] if countries else None,
                "country_codes":   countries,
                "institution_name": institutions[0].get("name") if institutions else None,
                "institution_ror":  institutions[0].get("ror")  if institutions else None,
                "institution_type": institutions[0].get("type") if institutions else None,
            }
            # Solo guardar si tiene algo de información
            if not any([aff["country_code"], aff["institution_name"]]):
                continue

            if orcid:
                # Consolidar: si ya existe, mantener datos previos si los nuevos son nulos
                prev = orcid_data.get(orcid, {})
                for key, val in aff.items():
                    if val and not prev.get(key):
                        prev[key] = val
                    if key == "country_codes" and val:
                        prev[key] = list(set(prev.get(key, []) + val))
                orcid_data[orcid] = prev
            elif author_name:
                prev = name_data.get(author_name, {})
                for key, val in aff.items():
                    if val and not prev.get(key):
                        prev[key] = val
                    if key == "country_codes" and val:
                        prev[key] = list(set(prev.get(key, []) + val))
                name_data[author_name] = prev

    total_by_orcid = len(orcid_data)
    total_by_name  = len(name_data)
    print(f"  → {total_by_orcid:,} coautores únicos por ORCID, {total_by_name:,} por nombre.", flush=True)

    if dry_run:
        sample = list(orcid_data.items())[:5]
        print(f"\n🔍 DRY-RUN: muestra de afiliaciones a escribir (por ORCID):")
        for orcid, aff in sample:
            print(f"   {orcid}: {aff}")
        graph.close()
        return

    # 3. Actualizar nodos :Author en Neo4j (solo los externos, no los :Academic)
    updated = 0
    not_found = 0

    # Por ORCID (más preciso)
    print("\n🔄 Actualizando por ORCID...", flush=True)
    with graph.driver.session() as session:
        for i, (orcid, aff) in enumerate(orcid_data.items()):
            result = session.run(
                """
                MATCH (a:Author {orcid: $orcid})
                WHERE NOT (a:Academic)
                SET a.country_code    = COALESCE($country_code, a.country_code),
                    a.country_codes   = $country_codes,
                    a.institution_name = COALESCE($institution_name, a.institution_name),
                    a.institution_ror  = COALESCE($institution_ror,  a.institution_ror),
                    a.institution_type = COALESCE($institution_type, a.institution_type)
                RETURN count(a) AS n
                """,
                orcid          = orcid,
                country_code   = aff.get("country_code"),
                country_codes  = aff.get("country_codes", []),
                institution_name = aff.get("institution_name"),
                institution_ror  = aff.get("institution_ror"),
                institution_type = aff.get("institution_type"),
            )
            n = result.single()["n"]
            if n > 0:
                updated += n
            else:
                not_found += 1
            if (i + 1) % 200 == 0:
                print(f"  [{i+1}/{total_by_orcid}] actualizados={updated}", end="\r", flush=True)
        print(f"  [ORCID] actualizados={updated}  sin_nodo={not_found}", flush=True)

    # Por nombre (fallback)
    print("🔄 Actualizando por nombre (fallback)...", flush=True)
    name_updated = 0
    name_not_found = 0
    with graph.driver.session() as session:
        for i, (name, aff) in enumerate(name_data.items()):
            result = session.run(
                """
                MATCH (a:Author {name: $name})
                WHERE NOT (a:Academic)
                  AND a.country_code IS NULL
                SET a.country_code    = COALESCE($country_code, a.country_code),
                    a.country_codes   = $country_codes,
                    a.institution_name = COALESCE($institution_name, a.institution_name),
                    a.institution_ror  = COALESCE($institution_ror,  a.institution_ror),
                    a.institution_type = COALESCE($institution_type, a.institution_type)
                RETURN count(a) AS n
                """,
                name           = name,
                country_code   = aff.get("country_code"),
                country_codes  = aff.get("country_codes", []),
                institution_name = aff.get("institution_name"),
                institution_ror  = aff.get("institution_ror"),
                institution_type = aff.get("institution_type"),
            )
            n = result.single()["n"]
            if n > 0:
                name_updated += n
            else:
                name_not_found += 1
            if (i + 1) % 200 == 0:
                print(f"  [{i+1}/{total_by_name}] actualizados={name_updated}", end="\r", flush=True)
    print(f"  [Nombre] actualizados={name_updated}  sin_nodo={name_not_found}", flush=True)

    graph.close()
    print(f"\n✅ Parche de afiliaciones completado.")
    print(f"   Por ORCID   : {updated} nodos actualizados")
    print(f"   Por nombre  : {name_updated} nodos actualizados")
    print(f"   Sin nodo    : {not_found + name_not_found}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enriquece nodos :Author con país e institución desde raw_metadata."
    )
    parser.add_argument("--entity",  type=str,  default=None, help="Filtrar por entidad")
    parser.add_argument("--dry-run", action="store_true",     help="Solo reportar sin modificar BD")
    args = parser.parse_args()
    patch_author_affiliations(entity_filter=args.entity, dry_run=args.dry_run)
