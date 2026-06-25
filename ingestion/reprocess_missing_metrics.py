#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
reprocess_missing_metrics.py
============================
Busca académicos con censo >= 2 en Neo4j but 0 en indizada/analítica,
y re-ingesta su producción desde APIs, sincroniza a ClickHouse y recalcula métricas.
Usa 3 hilos concurrentes para procesamiento secuencial de cada académico.
"""

import os
import sys
import json
import glob
import duckdb
import subprocess
import argparse
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Configuración de rutas
BASE_PATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_PATH))

def normalize_text(text):
    if not text:
        return ""
    text = "".join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn')
    return text.upper().strip()

def resolve_hierarchy_from_neo4j(academic_name):
    # Evitar importar a nivel de módulo para evitar interferencias
    try:
        from database.knowledge_graph import Neo4jGraphStore
        neo = Neo4jGraphStore()
        query = """
        MATCH (a:Person)
        WHERE a.fullname = $name OR a.id = $name
        MATCH (a)-[:AFFILIATED_TO]->(node)
        OPTIONAL MATCH (node)-[:PART_OF*0..2]->(parent)
        RETURN labels(node) as node_labels, node.name as node_name, labels(parent) as parent_labels, parent.name as parent_name
        """
        inst, dep, sub = None, None, None
        with neo.driver.session() as session:
            result = session.run(query, name=academic_name)
            for record in result:
                n_labels = record["node_labels"]
                n_name = record["node_name"]
                p_labels = record["parent_labels"]
                p_name = record["parent_name"]
                
                if n_labels and "Institution" in n_labels: inst = n_name
                if n_labels and "Dependency" in n_labels: dep = n_name
                if n_labels and "Subdependency" in n_labels: sub = n_name
                
                if p_labels and "Institution" in p_labels: inst = p_name
                if p_labels and "Dependency" in p_labels: dep = p_name
                if p_labels and "Subdependency" in p_labels: sub = p_name
        neo.close()
        return inst, dep, sub
    except Exception as e:
        print(f"⚠️ [Neo4j Hierarchy Error] {academic_name}: {e}")
        return None, None, None

def run_command(cmd, academic_name, step_name, dry_run=False):
    print(f"⏳ [{academic_name}] Ejecutando {step_name}: {' '.join(cmd)}")
    if dry_run:
        return True
    try:
        # Ejecutar y capturar salida para reportar errores
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ [{academic_name}] Error en {step_name}!")
        print(f"   Comando: {' '.join(cmd)}")
        print(f"   Código de salida: {e.returncode}")
        print(f"   Stderr:\n{e.stderr}")
        return False

def process_academic(academic_name, db_inst, db_ent, snii_lookup, unam_lookup, dry_run=False):
    norm_name = normalize_text(academic_name)
    print(f"\n🚀 [PROCESO] Iniciando re-procesamiento para: {academic_name}")
    
    # ── Paso 1: Ingesta desde API ──
    step1_ok = False
    if norm_name in snii_lookup:
        # Ingesta SNII consolidada
        cmd_ingest = [
            sys.executable,
            "SNII/ingest_snii_apis.py",
            "--name", academic_name,
            "--force",
            "--ch"
        ]
        step1_ok = run_command(cmd_ingest, academic_name, "Paso 1 (Ingesta SNII)", dry_run)
    elif norm_name in unam_lookup:
        # Ingesta UNAM por dependencia
        json_file = unam_lookup[norm_name]
        
        # Obtener jerarquía precisa desde Neo4j
        inst, dep, sub = resolve_hierarchy_from_neo4j(academic_name)
        
        # Fallback si Neo4j no resolvió la jerarquía completa
        hierarchy_parts = []
        hierarchy_parts.append(inst or db_inst)
        if dep:
            hierarchy_parts.append(dep)
        elif db_ent and db_ent != db_inst:
            hierarchy_parts.append(db_ent)
        if sub:
            hierarchy_parts.append(sub)
            
        hierarchy_str = " || ".join(hierarchy_parts)
        
        cmd_ingest = [
            sys.executable,
            "ingestion/ingest_apis.py",
            json_file,
            "--name", academic_name,
            "--hierarchy", hierarchy_str,
            "--force"
        ]
        step1_ok = run_command(cmd_ingest, academic_name, f"Paso 1 (Ingesta UNAM - {os.path.basename(json_file)})", dry_run)
    else:
        print(f"⚠️ [{academic_name}] Advertencia: No se encontró en snii_llm_verified_matches.json ni en archivos data/UNAM/*.json. Saltando...")
        return academic_name, "SKIPPED_SOURCE"

    if not step1_ok:
        return academic_name, "FAILED_STEP_1"
        
    # ── Paso 2: Sincronización a ClickHouse ──
    cmd_sync = [
        sys.executable,
        "ingestion/sync_analytics_pipeline.py",
        "--phase", "all",
        "--academic", academic_name,
        "--institution", db_inst
    ]
    step2_ok = run_command(cmd_sync, academic_name, "Paso 2 (Sincronización ClickHouse)", dry_run)
    
    if not step2_ok:
        return academic_name, "FAILED_STEP_2"
        
    # ── Paso 3: Cómputo de Métricas y Generación de Parquet (DuckDB Cache) ──
    cmd_metrics = [
        sys.executable,
        "ingestion/compute_scholar_metrics_ch.py",
        "--academic", academic_name,
        "--institution", db_inst
    ]
    step3_ok = run_command(cmd_metrics, academic_name, "Paso 3 (Cómputo de Métricas)", dry_run)
    
    if not step3_ok:
        return academic_name, "FAILED_STEP_3"
        
    print(f"✅ [{academic_name}] Re-procesamiento completado con éxito.")
    return academic_name, "SUCCESS"

def main():
    parser = argparse.ArgumentParser(description="Re-procesamiento automático de académicos con censo pero sin analítica")
    parser.add_argument("--limit", type=int, help="Límite de académicos a procesar")
    parser.add_argument("--threads", type=int, default=3, help="Número máximo de hilos concurrentes")
    parser.add_argument("--dry-run", action="store_true", help="Modo simulación (imprime comandos sin ejecutar)")
    args = parser.parse_args()
    
    # 1. Obtener candidatos desde DuckDB
    db_path = os.path.join(BASE_PATH, 'data', 'analytics_cache.duckdb')
    if not os.path.exists(db_path):
        print(f"❌ No se encontró el caché analítico en {db_path}.")
        sys.exit(1)
        
    con = duckdb.connect(db_path, read_only=True)
    query = """
        SELECT academic_name, db_institution_name, db_entity_name, neo4j_total_papers
        FROM investigador_total
        WHERE neo4j_total_papers >= 2 AND (num_documents IS NULL OR num_documents = 0)
        ORDER BY neo4j_total_papers DESC
    """
    candidates = con.execute(query).fetchall()
    con.close()
    
    total_candidates = len(candidates)
    print(f"🔍 Se encontraron {total_candidates} académicos candidatos (censo >= 2 e indizada == 0).")
    
    if args.limit:
        candidates = candidates[:args.limit]
        print(f"📌 Límite aplicado: procesando solo los primeros {len(candidates)} académicos.")
        
    if not candidates:
        print("🎉 No hay académicos para re-procesar.")
        sys.exit(0)
        
    # 2. Cargar base de datos / mapeos locales para resolver el Paso 1
    # Cargar snii_llm_verified_matches
    snii_path = os.path.join(BASE_PATH, 'data', 'snii_llm_verified_matches.json')
    snii_lookup = {}
    if os.path.exists(snii_path):
        try:
            with open(snii_path, 'r', encoding='utf-8') as f:
                snii_data = json.load(f)
                snii_lookup = {normalize_text(r.get('snii_author')): r for r in snii_data if r.get('snii_author')}
            print(f"📖 Cargado snii_llm_verified_matches.json ({len(snii_lookup)} registros).")
        except Exception as e:
            print(f"⚠️ Error cargando snii_llm_verified_matches.json: {e}")
            
    # Cargar directorio UNAM
    unam_data_dir = os.path.join(BASE_PATH, 'data', 'UNAM')
    unam_lookup = {}
    if os.path.exists(unam_data_dir):
        json_files = glob.glob(os.path.join(unam_data_dir, "*.json"))
        for jf in json_files:
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key in data.keys():
                        unam_lookup[normalize_text(key)] = jf
            except Exception as e:
                print(f"⚠️ Error cargando archivo UNAM {os.path.basename(jf)}: {e}")
        print(f"📖 Mapeado directorio UNAM ({len(unam_lookup)} académicos únicos).")
        
    # 3. Lanzar procesamiento concurrente
    results = {}
    print(f"\n🚀 Lanzando {args.threads} hilos para el procesamiento...")
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {
            executor.submit(
                process_academic, 
                r[0], r[1], r[2], 
                snii_lookup, unam_lookup, 
                dry_run=args.dry_run
            ): r[0] for r in candidates
        }
        
        for future in as_completed(futures):
            name = futures[future]
            try:
                academic_name, status = future.result()
                results[academic_name] = status
            except Exception as exc:
                print(f"❌ [{name}] Excepción no controlada en el procesamiento: {exc}")
                results[name] = f"EXCEPTION: {exc}"
                
    # 4. Resumen final
    print("\n============================================================")
    print("📊 RESUMEN DE PROCESAMIENTO")
    print("============================================================")
    success_count = sum(1 for s in results.values() if s == "SUCCESS")
    skipped_count = sum(1 for s in results.values() if s == "SKIPPED_SOURCE")
    failed_count = len(results) - success_count - skipped_count
    
    print(f"✅ Exitosos: {success_count}")
    print(f"⏭️ Saltados (sin origen conocido): {skipped_count}")
    print(f"❌ Fallidos: {failed_count}")
    print("============================================================")
    
    for name, status in results.items():
        if status != "SUCCESS":
            print(f"• {name}: {status}")

if __name__ == "__main__":
    main()
