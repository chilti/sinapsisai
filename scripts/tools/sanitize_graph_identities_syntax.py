#!/usr/bin/env python3
"""
scripts/tools/sanitize_graph_identities_syntax.py
==================================================
Motor determinista de sanitización sintáctica de identificadores en Neo4j.
Normaliza y desdobla estructuras compuestas o mal formateadas en nodos (:Person):
- openalex_ids: Desdobla URLs compuestas con comas/puntos y coma, elimina duplicados, normaliza a https://openalex.org/A...
- scopus_ids: Desdobla cadenas concatenadas (';', ','), extrae dígitos puros y deduplica.
- orcid / orcids: Extrae el patrón canónico 0000-0000-0000-0000 sin URLs (https://orcid.org/) y sincroniza p.orcid y p.orcids.
- siia: Limpia espacios en blanco y normaliza URLs.

Soporta --dry-run (modo seguro por defecto) y --commit (escritura en lotes transaccionales).
"""

import os
import sys
import re
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from api.db import get_neo4j_store

# ── Expresiones Regulares de Normalización ──────────────────────────────────────
RE_ORCID = re.compile(r'\b(\d{4}-\d{4}-\d{4}-[\dX]{4})\b', re.IGNORECASE)
RE_OPENALEX = re.compile(r'(?:https?://openalex\.org/)?(A\d{7,12})', re.IGNORECASE)
RE_SCOPUS = re.compile(r'\b(\d{6,13})\b')

def clean_scopus_ids(val: Any) -> List[str]:
    """Extrae y deduplica Scopus IDs numéricos de cadenas o listas."""
    if not val:
        return []
    
    raw_items = [val] if isinstance(val, str) else list(val)
    found = []
    for item in raw_items:
        if not item:
            continue
        # Buscar todos los bloques numéricos de 6 a 13 dígitos
        matches = RE_SCOPUS.findall(str(item))
        for m in matches:
            found.append(m.strip())
            
    # Deduplicar preservando orden
    return list(dict.fromkeys(found))

def clean_openalex_ids(val: Any) -> List[str]:
    """Extrae y normaliza OpenAlex IDs al formato canónico https://openalex.org/A..."""
    if not val:
        return []
        
    raw_items = [val] if isinstance(val, str) else list(val)
    found = []
    for item in raw_items:
        if not item:
            continue
        matches = RE_OPENALEX.findall(str(item))
        for m in matches:
            canonical = f"https://openalex.org/{m.upper()}"
            found.append(canonical)
            
    return list(dict.fromkeys(found))

def clean_orcid(orcid_val: Any, orcids_val: Any) -> Tuple[Optional[str], List[str]]:
    """Extrae códigos ORCID puros (19 chars) y sincroniza orcid con orcids."""
    all_raw = []
    if orcid_val:
        all_raw.append(str(orcid_val))
    if orcids_val:
        if isinstance(orcids_val, list):
            all_raw.extend([str(x) for x in orcids_val if x])
        else:
            all_raw.append(str(orcids_val))
            
    found = []
    for raw in all_raw:
        matches = RE_ORCID.findall(raw)
        for m in matches:
            found.append(m.upper())
            
    dedup = list(dict.fromkeys(found))
    primary = dedup[0] if dedup else None
    return primary, dedup

def clean_siia(val: Any) -> Optional[str]:
    """Normaliza la URL de SIIA eliminando espacios o parámetros redundantes."""
    if not val:
        return None
    val_str = str(val).strip()
    return val_str if val_str else None

# ── Escaneo y Sanitización ───────────────────────────────────────────────────

def scan_and_sanitize(batch_size: int = 1000, commit: bool = False, limit: Optional[int] = None):
    store = get_neo4j_store()
    
    print("=" * 80)
    print("🧹 MOTOR DE SANITIZACIÓN SINTÁCTICA DE IDENTIFICADORES EN NEO4J")
    print(f"   Modo: {'⚠️ ESCRITURA EN BASE DE DATOS (--commit)' if commit else '🛡️ SIMULACIÓN SEGURA (--dry-run)'}")
    print("=" * 80)

    t0 = time.time()
    
    query = """
    MATCH (p:Person)
    WHERE p.scopus_ids IS NOT NULL 
       OR p.openalex_ids IS NOT NULL 
       OR p.orcid IS NOT NULL 
       OR p.orcids IS NOT NULL
       OR p.siia IS NOT NULL
    RETURN p.id as id, p.fullname as fullname, p.cvu as cvu,
           p.scopus_ids as scopus_ids,
           p.openalex_ids as openalex_ids,
           p.orcid as orcid,
           p.orcids as orcids,
           p.siia as siia
    """
    if limit:
        query += f" LIMIT {limit}"

    print("🔍 Consultando nodos :Person con identificadores en Neo4j...")
    with store.driver.session() as s:
        records = s.run(query).data()

    total_nodes = len(records)
    print(f"✅ Recuperados {total_nodes:,} nodos con algún identificador en {time.time()-t0:.2f}s.\n")

    updates = []
    diff_scopus_count = 0
    diff_oa_count = 0
    diff_orcid_count = 0
    diff_siia_count = 0

    scopus_samples = []
    oa_samples = []
    orcid_samples = []

    for r in records:
        node_id = r["id"]
        changed = False
        payload = {"id": node_id}

        # 1. Scopus IDs (y rescate de posibles ORCIDs atrapados en scopus_ids)
        orig_scopus = r["scopus_ids"] or []
        rescued_orcids_from_scopus = []
        for s_item in orig_scopus:
            if s_item:
                m_orc = RE_ORCID.findall(str(s_item))
                rescued_orcids_from_scopus.extend(m_orc)

        new_scopus = clean_scopus_ids(orig_scopus)
        if new_scopus != orig_scopus:
            changed = True
            diff_scopus_count += 1
            payload["scopus_ids"] = new_scopus
            if len(scopus_samples) < 5:
                scopus_samples.append({
                    "name": r["fullname"],
                    "before": orig_scopus,
                    "after": new_scopus
                })

        # 2. OpenAlex IDs
        orig_oa = r["openalex_ids"] or []
        new_oa = clean_openalex_ids(orig_oa)
        if new_oa != orig_oa:
            changed = True
            diff_oa_count += 1
            payload["openalex_ids"] = new_oa
            if len(oa_samples) < 5:
                oa_samples.append({
                    "name": r["fullname"],
                    "before": orig_oa,
                    "after": new_oa
                })

        # 3. ORCID / ORCIDs (incluye los rescatados de scopus_ids si los hay)
        orig_orcid = r["orcid"]
        orig_orcids = list(r["orcids"] or [])
        if rescued_orcids_from_scopus:
            orig_orcids.extend(rescued_orcids_from_scopus)

        new_orcid, new_orcids = clean_orcid(orig_orcid, orig_orcids)
        if new_orcid != orig_orcid or new_orcids != (r["orcids"] or []):
            changed = True
            diff_orcid_count += 1
            payload["orcid"] = new_orcid
            payload["orcids"] = new_orcids
            if len(orcid_samples) < 5:
                orcid_samples.append({
                    "name": r["fullname"],
                    "before": {"orcid": orig_orcid, "orcids": r["orcids"]},
                    "after": {"orcid": new_orcid, "orcids": new_orcids}
                })

        # 4. SIIA
        orig_siia = r["siia"]
        new_siia = clean_siia(orig_siia)
        if new_siia != orig_siia:
            changed = True
            diff_siia_count += 1
            payload["siia"] = new_siia

        if changed:
            updates.append(payload)

    print("📊 RESULTADOS DEL ANÁLISIS SINTÁCTICO:")
    print(f"   • Total nodos analizados: {total_nodes:,}")
    print(f"   • Nodos que requieren corrección: {len(updates):,} ({len(updates)/total_nodes*100:.2f}%)")
    print(f"     - Con correcciones en openalex_ids: {diff_oa_count:,}")
    print(f"     - Con correcciones en orcid / orcids: {diff_orcid_count:,}")
    print(f"     - Con correcciones en scopus_ids: {diff_scopus_count:,}")
    print(f"     - Con correcciones en siia: {diff_siia_count:,}")

    # Mostrar muestras representativas
    if oa_samples:
        print("\n🔎 Muestras de transformación en OpenAlex IDs:")
        for s in oa_samples:
            print(f"   👤 {s['name']}")
            print(f"      Antes: {s['before']}")
            print(f"      Después: {s['after']}")

    if orcid_samples:
        print("\n🔎 Muestras de transformación en ORCID:")
        for s in orcid_samples:
            print(f"   👤 {s['name']}")
            print(f"      Antes: {s['before']}")
            print(f"      Después: {s['after']}")

    if scopus_samples:
        print("\n🔎 Muestras de transformación en Scopus IDs:")
        for s in scopus_samples:
            print(f"   👤 {s['name']}")
            print(f"      Antes: {s['before']}")
            print(f"      Después: {s['after']}")

    # Ejecución o reporte de commit
    if commit and updates:
        print("\n" + "=" * 80)
        print(f"⚡ APLICANDO CORRECCIONES EN NEO4J ({len(updates):,} nodos)...")
        print("=" * 80)

        # Actualizar en lotes mediante Cypher
        update_cypher = """
        UNWIND $batch as row
        MATCH (p:Person {id: row.id})
        SET p.openalex_ids = coalesce(row.openalex_ids, p.openalex_ids),
            p.scopus_ids   = coalesce(row.scopus_ids, p.scopus_ids),
            p.orcid        = CASE WHEN 'orcid' IN keys(row) THEN row.orcid ELSE p.orcid END,
            p.orcids       = coalesce(row.orcids, p.orcids),
            p.siia         = coalesce(row.siia, p.siia),
            p.syntax_sanitized = true,
            p.syntax_sanitized_at = datetime()
        """
        
        applied = 0
        with store.driver.session() as s:
            for i in range(0, len(updates), batch_size):
                chunk = updates[i:i + batch_size]
                s.run(update_cypher, {"batch": chunk})
                applied += len(chunk)
                print(f"   💾 Lote actualizado: {applied:,}/{len(updates):,} ({applied/len(updates)*100:.1f}%)")

        print(f"\n🎉 ¡Actualización exitosa de {applied:,} nodos en Neo4j!")
    else:
        print("\n" + "=" * 80)
        print("🛡️  FIN DEL MODO SIMULACIÓN (--dry-run).")
        print("    No se modificó ningún dato en la base de datos.")
        print("    Para aplicar estos cambios permanentes en Neo4j, ejecuta con: --commit")
        print("=" * 80)

    store.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sanitizador Sintáctico de IDs en Neo4j")
    parser.add_argument("--commit", action="store_true", help="Aplica los cambios en Neo4j (por defecto es dry-run)")
    parser.add_argument("--limit", type=int, default=None, help="Limitar cantidad de nodos para pruebas")
    parser.add_argument("--batch-size", type=int, default=1000, help="Tamaño de lote para commits")
    args = parser.parse_args()

    scan_and_sanitize(batch_size=args.batch_size, commit=args.commit, limit=args.limit)
