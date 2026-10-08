#!/usr/bin/env python3
"""
scripts/tools/enrich_neo4j_cpi_entidad_final.py
==============================================
Enriquece los nodos (:Person) del Grafo de Conocimiento Neo4j con:
1. 'entidad_final': Entidad Federativa de adscripción final según el Padrón SNII 2026.
2. 'is_cpi_secihti': Booleano (true/false) que indica si el investigador pertenece a la red
   de Centros Públicos de Investigación SECIHTI (CPI-S).
3. 'cpi_secihti': Etiqueta literal ('CPI-S' o null).

Uso:
  /home/ambientesPy/revistaslatam/bin/python3 scripts/tools/enrich_neo4j_cpi_entidad_final.py
"""

import os
import sys
import time
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

EXCEL_PATH = BASE_DIR / "data" / "Padron-2026-2T.xlsx"
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASS") or os.getenv("NEO4J_PASSWORD", "password123")

def normalize_text(val):
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    return s if s.upper() not in ("", "NAN", "NO APLICA", "-", "SIN INFORMACION", "SIN INFORMACIÓN") else None

def main():
    print("=" * 75)
    print("🚀 ENRIQUECIMIENTO DE NEO4J CON ENTIDAD FINAL Y CENTROS PÚBLICOS SECIHTI")
    print(f"   Fuente: {EXCEL_PATH}")
    print(f"   Destino: {NEO4J_URI}")
    print("=" * 75)

    if not EXCEL_PATH.exists():
        print(f"❌ Error: Archivo no encontrado en {EXCEL_PATH}")
        sys.exit(1)

    t0 = time.time()
    print(f"\n📂 Leyendo {EXCEL_PATH.name}...")
    df = pd.read_excel(EXCEL_PATH)
    print(f"   Filas leídas: {len(df):,}")

    # Detectar columnas relevantes
    col_map = {str(c).upper().strip(): c for c in df.columns}
    
    cvu_col = next((col_map[c] for c in col_map if "CVU" in c), None)
    cpi_col = next((col_map[c] for c in col_map if "CPI" in c or "CENTRO PUBLICO" in c), None)
    ent_col = next((col_map[c] for c in col_map if "ENTIDAD FINAL" in c), None)

    if not cvu_col or not ent_col:
        print(f"❌ Error: Columnas necesarias no detectadas. Encontradas: {list(df.columns)}")
        sys.exit(1)

    print(f"   Columna CVU: '{cvu_col}'")
    print(f"   Columna CPI SECIHTI: '{cpi_col}'")
    print(f"   Columna Entidad Final: '{ent_col}'")

    # Preparar datos
    batch_records = []
    cpi_count = 0

    for _, row in df.iterrows():
        raw_cvu = row[cvu_col]
        if pd.isna(raw_cvu):
            continue
        try:
            cvu_str = str(int(raw_cvu))
        except (ValueError, TypeError):
            cvu_str = str(raw_cvu).strip()

        # CPI
        raw_cpi = str(row[cpi_col]).strip().upper() if cpi_col and pd.notna(row[cpi_col]) else ""
        is_cpi = ("CPI-S" in raw_cpi or "CENTRO PUBLICO" in raw_cpi)
        if is_cpi:
            cpi_count += 1

        # Entidad Final
        ent_final = normalize_text(row[ent_col]) or "SIN ASIGNACION"

        batch_records.append({
            "cvu": cvu_str,
            "entidad_final": ent_final,
            "is_cpi": is_cpi,
            "cpi_label": "CPI-S" if is_cpi else None
        })

    print(f"\n📊 Registros a procesar: {len(batch_records):,}")
    print(f"   Investigadores pertenecientes a CPI-S: {cpi_count:,}")

    # Conectar a Neo4j y crear índices de búsqueda
    print("\n⚡ Conectando a Neo4j...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    
    with driver.session() as session:
        print("   Creando índices de aceleración...")
        session.run("CREATE INDEX person_cvu_idx IF NOT EXISTS FOR (p:Person) ON (p.cvu)")
        session.run("CREATE INDEX person_entidad_final_idx IF NOT EXISTS FOR (p:Person) ON (p.entidad_final)")
        session.run("CREATE INDEX person_is_cpi_idx IF NOT EXISTS FOR (p:Person) ON (p.is_cpi_secihti)")

        # Procesar en batches optimizados por índice
        batch_size = 2000
        total_batches = (len(batch_records) + batch_size - 1) // batch_size
        total_updated = 0

        query_cvu = """
        UNWIND $batch AS row
        MATCH (p:Person {cvu: row.cvu})
        SET p.entidad_final = row.entidad_final,
            p.is_cpi_secihti = row.is_cpi,
            p.cpi_secihti = row.cpi_label
        RETURN count(p) as cnt
        """

        query_id_fallback = """
        UNWIND $batch AS row
        MATCH (p:Person {id: row.cvu})
        WHERE p.entidad_final IS NULL
        SET p.entidad_final = row.entidad_final,
            p.is_cpi_secihti = row.is_cpi,
            p.cpi_secihti = row.cpi_label
        RETURN count(p) as cnt
        """

        print(f"   Iniciando carga de {total_batches} batches por índice cvu...", flush=True)
        for b_idx in range(total_batches):
            chunk = batch_records[b_idx * batch_size : (b_idx + 1) * batch_size]
            res = session.run(query_cvu, batch=chunk).single()
            cnt = res["cnt"] if res else 0
            total_updated += cnt
            print(f"   Lote {b_idx + 1}/{total_batches} procesado ({total_updated:,} nodos Person actualizados)...", flush=True)

        print("\n   Verificando nodos adicionales por índice id...", flush=True)
        fallback_updated = 0
        for b_idx in range(total_batches):
            chunk = batch_records[b_idx * batch_size : (b_idx + 1) * batch_size]
            res = session.run(query_id_fallback, batch=chunk).single()
            cnt = res["cnt"] if res else 0
            fallback_updated += cnt

        total_updated += fallback_updated
        if fallback_updated > 0:
            print(f"   Nodos adicionales actualizados por ID: {fallback_updated:,}", flush=True)

        print(f"\n✅ Actualización finalizada exitosamente.", flush=True)
        print(f"   Total de nodos (:Person) actualizados en Neo4j: {total_updated:,}", flush=True)

        # Verificación analítica en Neo4j
        print("\n🔍 Verificación de calidad en Neo4j:")
        cpi_neo = session.run("MATCH (p:Person {is_cpi_secihti: true}) RETURN count(p) as cnt").single()["cnt"]
        ent_neo = session.run("""
            MATCH (p:Person) 
            WHERE p.entidad_final IS NOT NULL 
            RETURN count(p) as total, count(DISTINCT p.entidad_final) as estados
        """).single()
        
        top_entidades = session.run("""
            MATCH (p:Person) 
            WHERE p.entidad_final IS NOT NULL 
            RETURN p.entidad_final as estado, count(p) as total 
            ORDER BY total DESC LIMIT 6
        """).data()

        print(f"   • Nodos Person con 'is_cpi_secihti = true': {cpi_neo:,}")
        print(f"   • Nodos Person con 'entidad_final': {ent_neo['total']:,} ({ent_neo['estados']} entidades federativas)")
        print("   • Top 6 Entidades Federativas en Neo4j:")
        for te in top_entidades:
            print(f"     - {te['estado']}: {te['total']:,} investigadores")

    driver.close()
    elapsed = time.time() - t0
    print(f"\n⏱️ Tiempo total de ejecución: {elapsed:.2f} s ({elapsed/60:.2f} min)")
    print("=" * 75)

if __name__ == "__main__":
    main()
