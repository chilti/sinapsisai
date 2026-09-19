#!/usr/bin/env python3
"""
update_neo4j_snii_2026.py
=========================
Actualiza el Grafo de Conocimiento Neo4j (bolt://localhost:7687) con el Padrón SNII 2026:
1. Actualiza propiedades (nivel, vigencia, snii_active_2026 = true, snii_last_year = 2026)
   en los nodos (:Person) continuantes.
2. Marca snii_active = false y snii_active_2026 = false en los 1,606 investigadores dados de baja.
3. Crea nodos (:Person:Author {is_snii: true}) para los 4,812 nuevos ingresos de 2026.
4. Conecta dependencias (:AFFILIATED_TO) y áreas de conocimiento (:SPECIALIZED_IN).
"""

import os
import sys
import json
import argparse
import pandas as pd
from pathlib import Path
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

parser = argparse.ArgumentParser(description="Actualizar Neo4j con padrón SNII")
parser.add_argument("--excel", type=str, default=None, help="Ruta al nuevo archivo Excel del SNII")
args = parser.parse_args()

SNII_EXCEL = Path(args.excel) if args.excel else (DATA_DIR / "snii" / "Investigadores_vigentes_2026.xlsx")
AUDIT_JSON = DATA_DIR / "snii" / "snii_audit_diff_2025_2026.json"

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "password123")


def normalize_nivel(val):
    if val is None or pd.isna(val):
        return "UNKNOWN"
    s = str(val).strip().upper()
    mapping = {
        "CANDIDATO": "C", "C": "C",
        "1": "1", "I": "1", "NIVEL I": "1", "NIVEL 1": "1",
        "2": "2", "II": "2", "NIVEL II": "2", "NIVEL 2": "2",
        "3": "3", "III": "3", "NIVEL III": "3", "NIVEL 3": "3",
        "E": "E", "EMERITO": "E", "EMÉRITO": "E",
    }
    return mapping.get(s, s)


def clean_str(val):
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    return s if s.upper() not in ("", "NAN", "NO APLICA", "-", "SIN INFORMACION", "SIN INFORMACIÓN") else None


def update_neo4j():
    print("=" * 70)
    print(f"🚀 INICIANDO SINCRONIZACIÓN NEO4J PADRÓN SNII 2026 -> {NEO4J_URI}")
    print("=" * 70)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    
    # 1. Cargar datos del Excel 2026
    print("\n📂 Leyendo datos del Padrón 2026...")
    df = pd.read_excel(SNII_EXCEL)
    df.columns = [str(c).upper().strip() for c in df.columns]

    cvu_col = next(c for c in df.columns if "CVU" in c)
    name_col = next(c for c in df.columns if "NOMBRE" in c)
    nivel_col = next(c for c in df.columns if "NIVEL" in c)
    area_col = next(c for c in df.columns if "AREA" in c or "ÁREA" in c)
    inst_col = next(c for c in df.columns if "INSTITUCION" in c or "INSTITUCIÓN" in c)
    dep_col = next((c for c in df.columns if "DEPENDENCIA" in c and "SUB" not in c), None)
    sub_col = next((c for c in df.columns if "SUBDEPENDENCIA" in c), None)
    vig_fin_col = next((c for c in df.columns if "FIN DE VIGENCIA" in c or "FIN" in c), None)

    # 2. Desactivar investigadores dados de baja en 2026
    if AUDIT_JSON.exists():
        with open(AUDIT_JSON, "r", encoding="utf-8") as f:
            audit = json.load(f)
        
        # Bajas
        print("\n🔒 Marcando investigadores dados de baja (snii_active_2026 = false)...")
        active_2026_cvus = [str(int(c)) for c in pd.to_numeric(df[cvu_col], errors="coerce").dropna()]
        
        with driver.session() as session:
            # Poner snii_active_2026 = false a quienes no estén en el padrón 2026
            session.run("""
                MATCH (p:Person {is_snii: true})
                WHERE NOT p.cvu IN $active_cvus
                SET p.snii_active = false,
                    p.snii_active_2026 = false
            """, active_cvus=active_2026_cvus)
            print("   ✅ Estatus de bajas actualizado.")

    # 3. Procesar y actualizar los 48,000 investigadores activos en 2026 en batches
    print(f"\n🔄 Actualizando/Creando {len(df):,} investigadores en Neo4j...")
    batch_size = 2000
    rows = []

    for _, r in df.iterrows():
        cvu_val = r[cvu_col]
        if pd.isna(cvu_val):
            continue
        try:
            cvu_str = str(int(cvu_val))
        except:
            continue

        rows.append({
            "cvu": cvu_str,
            "fullname": str(r[name_col]).strip(),
            "nivel": normalize_nivel(r[nivel_col]),
            "area": str(r[area_col]).strip() if pd.notna(r[area_col]) else "SIN AREA",
            "institucion": clean_str(r[inst_col]),
            "dependencia": clean_str(r[dep_col]) if dep_col else None,
            "subdependencia": clean_str(r[sub_col]) if sub_col else None,
            "vigencia_fin": str(r[vig_fin_col]) if vig_fin_col and pd.notna(r[vig_fin_col]) else None
        })

    total_batches = (len(rows) + batch_size - 1) // batch_size
    with driver.session() as session:
        for b_idx in range(total_batches):
            chunk = rows[b_idx * batch_size : (b_idx + 1) * batch_size]
            
            session.run("""
                UNWIND $batch AS r
                MERGE (p:Person {id: r.cvu})
                ON CREATE SET
                    p.cvu = r.cvu,
                    p.fullname = r.fullname,
                    p.is_snii = true,
                    p.snii_ever = true,
                    p.snii_first_year = 2026,
                    p.snii_active = true,
                    p.snii_active_2026 = true,
                    p.snii_last_year = 2026,
                    p.snii_level = r.nivel,
                    p.snii_max_level = r.nivel,
                    p.snii_area = r.area,
                    p.snii_institution = r.institucion,
                    p.snii_dependency = r.dependencia,
                    p.snii_subdependency = r.subdependencia,
                    p.snii_vigencia_fin = r.vigencia_fin
                ON MATCH SET
                    p.fullname = r.fullname,
                    p.is_snii = true,
                    p.snii_active = true,
                    p.snii_active_2026 = true,
                    p.snii_last_year = 2026,
                    p.snii_level = r.nivel,
                    p.snii_area = r.area,
                    p.snii_institution = r.institucion,
                    p.snii_dependency = r.dependencia,
                    p.snii_subdependency = r.subdependencia,
                    p.snii_vigencia_fin = r.vigencia_fin,
                    p.snii_max_level = CASE 
                        WHEN r.nivel = 'E' THEN 'E'
                        WHEN r.nivel = '3' AND p.snii_max_level <> 'E' THEN '3'
                        WHEN r.nivel = '2' AND NOT p.snii_max_level IN ['E', '3'] THEN '2'
                        WHEN r.nivel = '1' AND NOT p.snii_max_level IN ['E', '3', '2'] THEN '1'
                        ELSE coalesce(p.snii_max_level, r.nivel)
                    END
                
                // Conectar Área de Conocimiento
                WITH p, r
                WHERE r.area IS NOT NULL
                MERGE (k:KnowledgeArea {name: r.area})
                MERGE (p)-[:SPECIALIZED_IN]->(k)

                // Conectar Institución si existe
                WITH p, r
                WHERE r.institucion IS NOT NULL
                MERGE (i:Institution {name: r.institucion})
                MERGE (p)-[:AFFILIATED_TO]->(i)
            """, batch=chunk)

            print(f"   -> Batch {b_idx + 1}/{total_batches} completado ({(b_idx + 1) * batch_size:,} registros)...")

    # 4. Verificación final
    with driver.session() as session:
        active_cnt = session.run("MATCH (p:Person {snii_active_2026: true}) RETURN count(p) as c").single()["c"]
        total_snii = session.run("MATCH (p:Person {is_snii: true}) RETURN count(p) as c").single()["c"]
        level_dist = session.run("""
            MATCH (p:Person {snii_active_2026: true})
            RETURN p.snii_level as nivel, count(p) as cnt
            ORDER BY cnt DESC
        """).data()

    print("\n" + "=" * 70)
    print("🎉 ACTUALIZACIÓN DE NEO4J COMPLETADA CON ÉXITO")
    print(f"   • Total Person is_snii:true en grafo: {total_snii:,}")
    print(f"   • Investigadores activos en 2026:      {active_cnt:,}")
    print("   • Distribución en Neo4j (2026):")
    for row in level_dist:
        print(f"       Nivel {row['nivel']}: {row['cnt']:,}")
    print("=" * 70)

    driver.close()


if __name__ == "__main__":
    update_neo4j()
