#!/usr/bin/env python3
"""
SNII/merge_duplicate_researchers_by_cvu.py
==========================================
Script para integrar y unificar nodos de investigadores duplicados en Neo4j usando el CVU.

Problema detectado:
- Existen ~11,140 pares de nodos que comparten el mismo CVU:
  1. Nodo Padrón SNII: id = toString(cvu) (ej. '522'), contiene nivel SNII actual (ej. 'E'), vigencia y adscripción.
  2. Nodo Bibliométrico / Autor: id = 'EXT_...' (ej. 'EXT_CARRILLOCALVETHUMBERTOANDRES'), contiene 100+ obras (AUTHOR_OF),
     scopus_ids, openalex_ids, siia, embeddings FastRP y enlaces User->REPRESENTS.

Solución:
- Fusiona mediante apoc.refactor.mergeNodes manteniendo como nodo canónico el nodo oficial con id = CVU.
- Reasigna todas las relaciones de autoría (AUTHOR_OF -> Paper), afiliaciones y vínculos de usuario al nodo canónico.
- Copia y consolida identificadores externos (scopus_ids, openalex_ids, siia, verified_orcid, orcids).
- Normaliza el ORCID canónico sin prefijos url.
- Asigna etiquetas completas (:Person:Author:SNII).
- Elimina el nodo duplicado 'EXT_...'.

Uso:
    python SNII/merge_duplicate_researchers_by_cvu.py --dry-run
    python SNII/merge_duplicate_researchers_by_cvu.py --cvu 522
    python SNII/merge_duplicate_researchers_by_cvu.py --target all --batch-size 100
"""

import os
import sys
import time
import argparse
import json
from pathlib import Path
from datetime import datetime

# Asegurar entorno
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database.knowledge_graph import Neo4jGraphStore

MERGE_CYPHER = """
MATCH (target:Person) WHERE elementId(target) = $target_elem_id
MATCH (source:Person) WHERE elementId(source) = $source_elem_id

// 1. Guardar identificador de origen como referencia histórica
SET target.legacy_id = source.id,
    target.ext_id = source.id

// 2. Consolidar identificadores y metadatos bibliométricos si faltan en target
SET target.scopus_ids = coalesce(target.scopus_ids, source.scopus_ids),
    target.openalex_ids = coalesce(target.openalex_ids, source.openalex_ids),
    target.openalex_id = coalesce(target.openalex_id, source.openalex_id),
    target.siia = coalesce(target.siia, source.siia),
    target.verified_orcid = coalesce(target.verified_orcid, source.verified_orcid),
    target.verified = coalesce(target.verified, source.verified, true),
    target.embedding_fastrp = coalesce(target.embedding_fastrp, source.embedding_fastrp),
    target.embedding_fastrp_topics = coalesce(target.embedding_fastrp_topics, source.embedding_fastrp_topics)

// 3. Consolidar lista de ORCIDs limpios
WITH target, source,
     [x IN coalesce(target.orcids, []) + coalesce(source.orcids, []) + [target.orcid, source.orcid, source.verified_orcid] 
      WHERE x IS NOT NULL AND x <> ''] AS raw_orcids
WITH target, source,
     [x IN raw_orcids | replace(replace(toString(x), 'https://orcid.org/', ''), 'http://orcid.org/', '')] AS clean_orcids
SET target.orcids = apoc.coll.toSet(clean_orcids)

// 4. Normalizar orcid principal si viene con URL
FOREACH (_ IN CASE WHEN target.orcid IS NOT NULL AND target.orcid STARTS WITH 'http' THEN [1] ELSE [] END |
    SET target.orcid = replace(replace(target.orcid, 'https://orcid.org/', ''), 'http://orcid.org/', '')
)
FOREACH (_ IN CASE WHEN target.orcid IS NULL AND size(target.orcids) > 0 THEN [1] ELSE [] END |
    SET target.orcid = target.orcids[0]
)

// 5. Asignar etiquetas consolidadas
SET target:Author, target:SNII

// 6. Fusionar relaciones y eliminar source mediante APOC
WITH target, source
CALL apoc.refactor.mergeNodes([target, source], {properties: 'discard', mergeRels: true}) YIELD node
RETURN node.id AS final_id,
       node.fullname AS fullname,
       node.cvu AS cvu,
       node.orcid AS orcid,
       size([(node)-[:AUTHOR_OF]->() | 1]) AS total_papers,
       labels(node) AS final_labels
"""


def get_duplicate_cvu_groups(kg: Neo4jGraphStore, specific_cvu: str = None):
    """Recupera los pares de nodos Person duplicados por CVU."""
    where_clause = "WHERE p.cvu IS NOT NULL"
    if specific_cvu:
        where_clause += f" AND (toString(p.cvu) = '{specific_cvu}' OR p.id = '{specific_cvu}')"

    query = f"""
    MATCH (p:Person)
    {where_clause}
    WITH toString(p.cvu) AS cvu_str, collect(p) AS nodes
    WHERE size(nodes) > 1
    RETURN cvu_str, [n IN nodes | {{
        elem_id: elementId(n),
        id: n.id,
        fullname: coalesce(n.fullname, n.name, ''),
        labels: labels(n),
        has_papers: size([(n)-[:AUTHOR_OF]->() | 1]),
        has_snii: (n.snii_level IS NOT NULL OR n.snii_active_2026 = true),
        snii_level: n.snii_level
    }}] AS node_list
    ORDER BY cvu_str
    """
    with kg.driver.session() as session:
        return session.run(query).data()


def decide_target_source(node_list: list):
    """
    Determina cuál nodo debe ser el canónico (target) y cuál el secundario (source).
    Regla:
    - Target: El nodo oficial con id numérico igual al CVU (nodo SNII oficial).
    - Source: El nodo con id 'EXT_...' o legacy con publicaciones.
    """
    if len(node_list) != 2:
        # Si hubiera más de 2, ordenar: primero numérico, luego el resto
        sorted_nodes = sorted(
            node_list,
            key=lambda x: (
                1 if x['id'].isdigit() else 2,
                0 if x['has_snii'] else 1
            )
        )
        return sorted_nodes[0], sorted_nodes[1:]

    n1, n2 = node_list[0], node_list[1]
    if n1['id'].isdigit() and not n2['id'].isdigit():
        return n1, [n2]
    elif n2['id'].isdigit() and not n1['id'].isdigit():
        return n2, [n1]
    elif n1['has_snii'] and not n2['has_snii']:
        return n1, [n2]
    elif n2['has_snii'] and not n1['has_snii']:
        return n2, [n1]
    else:
        # Si ambos son iguales, el que tenga ID numérico o el primero
        return n1, [n2]


def main():
    parser = argparse.ArgumentParser(description="Unificación de nodos duplicados en Neo4j por CVU.")
    parser.add_argument("--cvu", type=str, help="Procesar únicamente un CVU específico (ej. 522)")
    parser.add_argument("--dry-run", action="store_true", help="Solo simular sin aplicar cambios en Neo4j")
    parser.add_argument("--batch-size", type=int, default=100, help="Tamaño de lote para commits (default: 100)")
    parser.add_argument("--target", type=str, default="single", choices=["single", "all"], help="'single' para prueba o 'all' para todo el grafo")
    args = parser.parse_args()

    print("=" * 70)
    print(" UNIFICACIÓN DE INVESTIGADORES DUPLICADOS EN NEO4J POR CVU")
    print(f" Modo: {'DRY-RUN (Simulación)' if args.dry_run else 'EJECUCIÓN REAL'}")
    if args.cvu:
        print(f" Objetivo específico: CVU {args.cvu}")
    print("=" * 70)

    kg = Neo4jGraphStore()

    try:
        print("\n🔍 Buscando grupos de nodos duplicados por CVU...")
        groups = get_duplicate_cvu_groups(kg, specific_cvu=args.cvu)
        total_groups = len(groups)
        print(f"✅ Se encontraron {total_groups:,} CVUs con nodos duplicados en Neo4j.\n")

        if total_groups == 0:
            print("No hay duplicados que procesar.")
            return

        merged_count = 0
        total_papers_rewired = 0
        errors = []
        report_records = []

        start_time = time.time()

        with kg.driver.session() as session:
            for idx, g in enumerate(groups, 1):
                cvu_str = g['cvu_str']
                nodes = g['node_list']
                target_node, source_nodes = decide_target_source(nodes)

                if args.dry_run:
                    source_ids = [s['id'] for s in source_nodes]
                    total_source_papers = sum(s['has_papers'] for s in source_nodes)
                    print(f"[{idx}/{total_groups}] DRY-RUN CVU {cvu_str}:")
                    print(f"   Target canónico: {target_node['id']} ({target_node['fullname']}) [SNII: {target_node.get('snii_level')}]")
                    print(f"   Source(s) a fusionar: {source_ids} (total papers a reasignar: {total_source_papers})")
                    continue

                # Ejecución real
                for source_node in source_nodes:
                    try:
                        res = session.run(
                            MERGE_CYPHER,
                            target_elem_id=target_node['elem_id'],
                            source_elem_id=source_node['elem_id']
                        ).single()

                        if res:
                            merged_count += 1
                            papers = res['total_papers'] or 0
                            total_papers_rewired += papers
                            report_records.append({
                                "cvu": cvu_str,
                                "final_id": res['final_id'],
                                "fullname": res['fullname'],
                                "merged_source_id": source_node['id'],
                                "total_papers": papers,
                                "labels": res['final_labels']
                            })
                            print(f"[{idx}/{total_groups}] ✅ CVU {cvu_str} ({res['fullname']}) -> Fusión exitosa en nodo {res['final_id']} ({papers} obras vinculadas).")
                        else:
                            print(f"[{idx}/{total_groups}] ⚠️ CVU {cvu_str}: No se retornó resultado de la fusión.")
                    except Exception as e:
                        err_msg = f"Error fusionando CVU {cvu_str} (target {target_node['id']} <- source {source_node['id']}): {e}"
                        print(f"[{idx}/{total_groups}] ❌ {err_msg}")
                        errors.append(err_msg)

                # Pausa leve cada batch
                if idx % args.batch_size == 0 and not args.dry_run:
                    elapsed = time.time() - start_time
                    rate = idx / elapsed if elapsed > 0 else 0
                    print(f"\n--- Progreso: {idx}/{total_groups} ({idx/total_groups*100:.1f}%) | Velocidad: {rate:.1f} fusiones/s ---\n")

        elapsed_total = time.time() - start_time
        print("\n" + "=" * 70)
        print(" RESUMEN DE INTEGRACIÓN:")
        print(f" Total CVUs procesados: {total_groups:,}")
        if not args.dry_run:
            print(f" Fusiones exitosas: {merged_count:,}")
            print(f" Total obras reasignadas al nodo canónico: {total_papers_rewired:,}")
            print(f" Errores: {len(errors)}")
            print(f" Tiempo total: {elapsed_total:.2f} s ({elapsed_total/60:.2f} min)")

            # Guardar reporte de auditoría
            report_file = BASE_DIR / "data" / "snii_cvu_merge_audit_report.json"
            report_file.parent.mkdir(parents=True, exist_ok=True)
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "total_merged": merged_count,
                    "total_papers_rewired": total_papers_rewired,
                    "errors": errors,
                    "sample": report_records[:50]
                }, f, indent=2, ensure_ascii=False)
            print(f" Reporte de auditoría guardado en: {report_file}")
        print("=" * 70)

    finally:
        kg.close()


if __name__ == "__main__":
    main()
