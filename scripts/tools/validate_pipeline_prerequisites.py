#!/usr/bin/env python3
"""
validate_pipeline_prerequisites.py
==================================
Validador de Pre-requisitos del Pipeline Integral (Paso 0).

Verifica:
1. Conexión y accesibilidad de ClickHouse (rag).
2. Conexión y autenticación de Neo4j.
3. Integridad de RORs institucionales en `rag.paper_author_map`.
4. Existencia de catálogos de RORs en `ROR/mexican_institutions_rors.json`.

Uso:
  python scripts/tools/validate_pipeline_prerequisites.py [--fix-missing-rors]
"""

import sys
import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

def check_clickhouse():
    """Verifica conexión a ClickHouse y cobertura de RORs."""
    print("🔍 [Paso 0.1] Verificando ClickHouse (rag.paper_author_map)...", flush=True)
    try:
        from scripts.tools.match_snii_orcid import get_client
        client = get_client()
        
        # 1. Ping
        version = client.command("SELECT version()")
        print(f"  ✅ ClickHouse conectado (v{version})", flush=True)
        
        # 2. Verificar total de registros y cobertura de ROR
        q_total = "SELECT count() FROM rag.paper_author_map"
        total_rows = client.command(q_total)
        
        q_empty_ror = "SELECT count() FROM rag.paper_author_map WHERE institution_ror = '' OR institution_ror IS NULL"
        empty_ror_rows = client.command(q_empty_ror)
        
        pct_with_ror = ((total_rows - empty_ror_rows) / total_rows * 100) if total_rows > 0 else 0
        print(f"  📊 Total registros paper_author_map: {total_rows:,}", flush=True)
        print(f"  📊 Registros con ROR asignado: {total_rows - empty_ror_rows:,} ({pct_with_ror:.1f}%)", flush=True)
        
        if empty_ror_rows > 0:
            print(f"  ⚠️ Hay {empty_ror_rows:,} registros sin ROR.", flush=True)
        else:
            print("  ✅ 100% de los registros tienen ROR asignado.", flush=True)
            
        return {"status": "ok", "total": total_rows, "with_ror": total_rows - empty_ror_rows, "without_ror": empty_ror_rows}
    except Exception as e:
        print(f"  ❌ Error conectando a ClickHouse: {e}", flush=True)
        return {"status": "error", "error": str(e)}

def check_neo4j():
    """Verifica conexión a Neo4j."""
    print("🔍 [Paso 0.2] Verificando Neo4j (Grafo de Conocimiento)...", flush=True)
    try:
        from neo4j import GraphDatabase
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password123")
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            count = session.run("MATCH (p:Person) RETURN count(p) as c").single()["c"]
            print(f"  ✅ Neo4j conectado ({count:,} nodos :Person)", flush=True)
        driver.close()
        return {"status": "ok", "persons": count}
    except Exception as e:
        print(f"  ❌ Error conectando a Neo4j: {e}", flush=True)
        return {"status": "error", "error": str(e)}

def check_ror_catalog():
    """Verifica la existencia del catálogo de RORs mexicanos."""
    print("🔍 [Paso 0.3] Verificando catálogo local de RORs...", flush=True)
    catalog_path = BASE_DIR / "ROR" / "mexican_institutions_rors.json"
    if catalog_path.exists():
        with open(catalog_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"  ✅ Catálogo ROR disponible ({len(data):,} instituciones mexicanas)", flush=True)
        return {"status": "ok", "institutions": len(data)}
    else:
        print(f"  ⚠️ Catálogo ROR no encontrado en {catalog_path.name}", flush=True)
        return {"status": "warning", "error": "Archivo no encontrado"}

def main():
    print("=" * 70, flush=True)
    print("🛡️ VALIDACIÓN DE PRE-REQUISITOS DEL PIPELINE INTEGRAL (PASO 0)", flush=True)
    print("=" * 70, flush=True)
    
    ch_res = check_clickhouse()
    neo_res = check_neo4j()
    ror_res = check_ror_catalog()
    
    print("-" * 70, flush=True)
    if ch_res.get("status") == "ok" and neo_res.get("status") == "ok":
        print("🚀 Todos los pre-requisitos fundamentales están CUMPLIDOS.", flush=True)
        print("   El Pipeline Integral puede proceder con seguridad.\n", flush=True)
        sys.exit(0)
    else:
        print("❌ Se detectaron fallas en pre-requisitos críticos. Revisa los mensajes anteriores.\n", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
