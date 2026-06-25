"""
ingest_snii_historico.py
========================
Lee el Parquet histórico del SNII y actualiza/crea nodos Person en Neo4j.

Comportamiento:
  1. Agrupa el Parquet por CVU y calcula propiedades de trayectoria:
       snii_ever, snii_active, snii_first_year, snii_last_year, snii_max_level
  2. Para Person ya existentes en Neo4j (por CVU): actualiza esas propiedades.
  3. Para CVUs no existentes en Neo4j: crea nuevos nodos Person y los vincula
     a su última institución/dependencia conocida con AFFILIATED_TO.
  4. Para registros sin CVU (pre-2003 puro): intenta buscar coincidencia por
     nombre_key contra nodos Person existentes; si hay match, actualiza;
     si no, crea nodo aislado con id sintético 'SNII_HIST_<nombre_key>'.

Uso:
    python ingestion/ingest_snii_historico.py [--dry-run] [--batch-size 500]

Flags:
    --dry-run    Simula el proceso sin escribir en Neo4j (muestra estadísticas).
    --batch-size Número de nodos a procesar por transacción (default: 500).
"""

import sys
import argparse
import re
import unicodedata
from pathlib import Path
from collections import defaultdict

import pandas as pd
from tqdm import tqdm

# Rutas
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))

from dotenv import load_dotenv
load_dotenv(str(_THIS.parent / ".env"))

from database.knowledge_graph import Neo4jGraphStore

PARQUET_PATH   = _THIS.parent / "data" / "snii" / "snii_historico.parquet"
NUEVOS_XLS_PATH = _THIS.parent / "data" / "snii" / "snii_historico_nuevos.xlsx"

# Columnas del Excel de salida — deben coincidir con las de la hoja T4 2025
# para que snii_llm_identity_resolver.py las encuentre sin modificación.
COLS_2025 = [
    "CVU padrón corregido",          # CVU numérico
    "NOMBRE DEL INVESTIGADOR",        # Nombre en formato APELLIDOS, NOMBRES
    "NIVEL",                          # C, 1, 2, 3, E
    "CATEGORÍA",                      # null para históricos
    "FECHA INICIO DE VIGENCIA",
    "FECHA FIN DE VIGENCIA",
    "ÁREA DE CONOCIMIENTO",
    "CAMPO DE CONOCIMIENTO",          # null para pre-2025
    "DISCIPLINA",
    "SUBDISCIPLINA",
    "INSTITUCIÓN DE ACREDITACIÓN",
    "DEPENDENCIA DE ACREDITACIÓN",
    "SUBDEPENDENCIA DE ACREDITACIÓN",
    "ENTIDAD DE ACREDITACIÓN",
    "NOTAS",                          # indicará el año histórico
    "ENTIDAD FINAL",                  # requerido por snii_llm_identity_resolver.py
]

# Jerarquía de niveles para calcular max_level
NIVEL_ORDER = {"C": 0, "1": 1, "2": 2, "3": 3, "E": 4}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def max_nivel(niveles: list[str]) -> str | None:
    """Retorna el nivel más alto de una lista."""
    valid = [n for n in niveles if n in NIVEL_ORDER]
    if not valid:
        return None
    return max(valid, key=lambda x: NIVEL_ORDER[x])


def normalize_key(s: str) -> str:
    """Igual que en build_snii_parquet.py — debe mantenerse sincronizado."""
    if not s or pd.isna(s):
        return ""
    s = str(s).strip()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[,\s]+", "", s.lower())
    return s


def clean_str(val) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().upper()
    return s if s and s not in ("NAN", "NONE", "SIN INFORMACIÓN", "SIN INFORMACION") else None


# ---------------------------------------------------------------------------
# Carga del Parquet y agrupación por persona
# ---------------------------------------------------------------------------

def load_and_group(parquet_path: Path) -> dict:
    """
    Retorna un diccionario:
      cvu (int) → {
          "nombre":          str,
          "nombre_key":      str,
          "snii_first_year": int,
          "snii_last_year":  int,
          "snii_max_level":  str,
          "snii_active":     bool,
          "snii_ever":       True,
          "last_institucion": str | None,
          "last_dependencia": str | None,
          "last_subdependencia": str | None,
          "last_entidad":    str | None,
      }
    y una lista separada para registros SIN CVU:
      [{"nombre_key": str, "nombre": str, ...propiedades...}]
    """
    print(f"📂 Leyendo {parquet_path}...")
    df = pd.read_parquet(parquet_path)
    print(f"   {len(df):,} filas, {df['cvu'].dropna().nunique():,} CVUs únicos")

    personas = {}       # cvu → datos
    sin_cvu = []        # registros sin CVU (para matching por nombre)

    # ---- Registros CON CVU ----
    df_con_cvu = df[df["cvu"].notna()].copy()
    df_con_cvu["cvu"] = df_con_cvu["cvu"].astype(int)

    for cvu, grp in df_con_cvu.groupby("cvu"):
        grp_sorted = grp.sort_values("year")

        niveles = grp_sorted["nivel"].dropna().tolist()
        first_year = int(grp_sorted["year"].min())
        last_year  = int(grp_sorted["year"].max())

        # Última aparición para afiliación
        last_row = grp_sorted.iloc[-1]

        personas[cvu] = {
            "nombre":             str(grp_sorted["nombre"].dropna().iloc[-1]) if grp_sorted["nombre"].dropna().size > 0 else "",
            "nombre_key":         str(grp_sorted["nombre_key"].dropna().iloc[-1]) if grp_sorted["nombre_key"].dropna().size > 0 else "",
            "snii_first_year":    first_year,
            "snii_last_year":     last_year,
            "snii_max_level":     max_nivel(niveles),
            "snii_active":        bool(grp_sorted["snii_active_2025"].any()),
            "snii_ever":          True,
            "last_institucion":   clean_str(last_row.get("institucion")),
            "last_dependencia":   clean_str(last_row.get("dependencia")),
            "last_subdependencia":clean_str(last_row.get("subdependencia")),
            "last_entidad":       clean_str(last_row.get("entidad")),
        }

    # ---- Registros SIN CVU ----
    df_sin_cvu = df[df["cvu"].isna()].copy()
    for nombre_key, grp in df_sin_cvu.groupby("nombre_key"):
        if not nombre_key:
            continue
        grp_sorted = grp.sort_values("year")
        niveles = grp_sorted["nivel"].dropna().tolist()
        last_row = grp_sorted.iloc[-1]
        sin_cvu.append({
            "nombre_key":         nombre_key,
            "nombre":             str(grp_sorted["nombre"].dropna().iloc[-1]) if grp_sorted["nombre"].dropna().size > 0 else "",
            "snii_first_year":    int(grp_sorted["year"].min()),
            "snii_last_year":     int(grp_sorted["year"].max()),
            "snii_max_level":     max_nivel(niveles),
            "snii_active":        False,   # Sin CVU → no están en 2025
            "snii_ever":          True,
            "last_institucion":   clean_str(last_row.get("institucion")),
            "last_dependencia":   clean_str(last_row.get("dependencia")),
            "last_subdependencia":clean_str(last_row.get("subdependencia")),
        })

    print(f"   ✅ Personas con CVU: {len(personas):,}")
    print(f"   ℹ️  Personas sin CVU: {len(sin_cvu):,}")
    return personas, sin_cvu


# ---------------------------------------------------------------------------
# Consultar Neo4j para saber qué CVUs ya existen
# ---------------------------------------------------------------------------

def fetch_existing_cvus(gs: Neo4jGraphStore) -> dict[int, str]:
    """Retorna {cvu_int → person_id} para todos los Person con CVU en Neo4j."""
    query = """
    MATCH (p:Person)
    WHERE p.cvu IS NOT NULL AND p.cvu <> ''
    RETURN p.id AS id, p.cvu AS cvu
    """
    existing = {}
    with gs.driver.session() as session:
        result = session.run(query)
        for r in result:
            try:
                cvu_int = int(str(r["cvu"]).strip())
                existing[cvu_int] = r["id"]
            except (ValueError, TypeError):
                pass
    return existing


def fetch_existing_nombre_keys(gs: Neo4jGraphStore) -> dict[str, str]:
    """Retorna {nombre_key → person_id} para todos los Person en Neo4j (para matching sin CVU)."""
    query = """
    MATCH (p:Person)
    WHERE p.fullname IS NOT NULL
    RETURN p.id AS id, p.fullname AS fullname
    """
    existing = {}
    with gs.driver.session() as session:
        result = session.run(query)
        for r in result:
            key = normalize_key(r["fullname"] or "")
            if key:
                existing[key] = r["id"]
    return existing


# ---------------------------------------------------------------------------
# Queries Cypher de actualización
# ---------------------------------------------------------------------------

UPDATE_EXISTING_QUERY = """
UNWIND $batch AS row
MATCH (p:Person {id: row.person_id})
SET p.snii_ever        = true,
    p.snii_active      = row.snii_active,
    p.snii_first_year  = row.snii_first_year,
    p.snii_last_year   = row.snii_last_year,
    p.snii_max_level   = row.snii_max_level
"""

CREATE_NEW_PERSON_QUERY = """
UNWIND $batch AS row
MERGE (p:Person {id: row.person_id})
ON CREATE SET
    p.fullname        = row.nombre,
    p.cvu             = row.cvu_str,
    p.is_snii         = true,
    p.snii_ever       = true,
    p.snii_active     = row.snii_active,
    p.snii_first_year = row.snii_first_year,
    p.snii_last_year  = row.snii_last_year,
    p.snii_max_level  = row.snii_max_level

// Jerarquía institucional de la última afiliación conocida
WITH p, row
WHERE row.last_institucion IS NOT NULL

MERGE (inst:Institution {name: row.last_institucion})

WITH p, inst, row
// Si hay subdependencia, la usamos como nodo de afiliación
CALL (p, inst, row) {
    WITH p, inst, row
    WHERE row.last_subdependencia IS NOT NULL AND row.last_dependencia IS NOT NULL
    MERGE (dep:Dependency {id: row.last_institucion + "||" + row.last_dependencia})
    SET dep.name = row.last_dependencia
    MERGE (dep)-[:PART_OF]->(inst)
    MERGE (sub:Subdependency {id: row.last_institucion + "||" + row.last_dependencia + "||" + row.last_subdependencia})
    SET sub.name = row.last_subdependencia
    MERGE (sub)-[:PART_OF]->(dep)
    MERGE (p)-[:AFFILIATED_TO]->(sub)
}

// Si hay dependencia (sin subdependencia)
CALL (p, inst, row) {
    WITH p, inst, row
    WHERE row.last_dependencia IS NOT NULL AND row.last_subdependencia IS NULL
    AND NOT (p)-[:AFFILIATED_TO]->(:Subdependency)
    MERGE (dep:Dependency {id: row.last_institucion + "||" + row.last_dependencia})
    SET dep.name = row.last_dependencia
    MERGE (dep)-[:PART_OF]->(inst)
    MERGE (p)-[:AFFILIATED_TO]->(dep)
}

// Si solo hay institución
CALL (p, inst, row) {
    WITH p, inst, row
    WHERE row.last_dependencia IS NULL
    AND NOT (p)-[:AFFILIATED_TO]->(:Subdependency)
    AND NOT (p)-[:AFFILIATED_TO]->(:Dependency)
    MERGE (p)-[:AFFILIATED_TO]->(inst)
}
"""

CREATE_ISOLATED_QUERY = """
UNWIND $batch AS row
MERGE (p:Person {id: row.person_id})
ON CREATE SET
    p.fullname        = row.nombre,
    p.is_snii         = true,
    p.snii_ever       = true,
    p.snii_active     = false,
    p.snii_first_year = row.snii_first_year,
    p.snii_last_year  = row.snii_last_year,
    p.snii_max_level  = row.snii_max_level
"""


# ---------------------------------------------------------------------------
# Ejecución principal
# ---------------------------------------------------------------------------

def export_nuevos_to_excel(personas_to_create: dict, parquet_path: Path, output_path: Path):
    """
    Genera un Excel con los investigadores históricos que NO existen en Neo4j,
    usando exactamente las columnas de la hoja T4 2025 del padrón oficial.
    Esto permite pasarlos directamente a snii_llm_identity_resolver.py.
    """
    print(f"\n📄 Exportando {len(personas_to_create):,} investigadores nuevos a Excel...")

    # Leer parquet para obtener los datos completos de la última aparición de cada CVU
    df = pd.read_parquet(parquet_path)
    df_con_cvu = df[df["cvu"].notna()].copy()
    df_con_cvu["cvu"] = df_con_cvu["cvu"].astype(int)

    # Quedarnos solo con los CVUs que van a ser creados nuevos
    cvus_nuevos = set(personas_to_create.keys())
    df_nuevos = df_con_cvu[df_con_cvu["cvu"].isin(cvus_nuevos)].copy()

    # Seleccionar la última aparición de cada CVU (datos más recientes)
    df_last = df_nuevos.sort_values("year").groupby("cvu").last().reset_index()

    # Construir el DataFrame con las columnas del T4 2025
    rows = []
    for _, r in df_last.iterrows():
        datos = personas_to_create.get(int(r["cvu"]), {})
        rows.append({
            "CVU padrón corregido":      int(r["cvu"]),
            "NOMBRE DEL INVESTIGADOR":   r.get("nombre") or datos.get("nombre", ""),
            "NIVEL":                     r.get("nivel") or datos.get("snii_max_level", ""),
            "CATEGORÍA":                 None,
            "FECHA INICIO DE VIGENCIA":  r.get("fecha_inicio"),
            "FECHA FIN DE VIGENCIA":     r.get("fecha_fin"),
            "ÁREA DE CONOCIMIENTO":      r.get("area"),
            "CAMPO DE CONOCIMIENTO":     None,
            "DISCIPLINA":                r.get("disciplina"),
            "SUBDISCIPLINA":             r.get("subdisciplina"),
            "INSTITUCIÓN DE ACREDITACIÓN":   r.get("institucion") or datos.get("last_institucion"),
            "DEPENDENCIA DE ACREDITACIÓN":   r.get("dependencia") or datos.get("last_dependencia"),
            "SUBDEPENDENCIA DE ACREDITACIÓN":r.get("subdependencia") or datos.get("last_subdependencia"),
            "ENTIDAD DE ACREDITACIÓN":   r.get("entidad"),
            "NOTAS":                     f"Padrón histórico SNII — último año: {int(r['year'])}",
            "ENTIDAD FINAL":             r.get("entidad"),  # alias requerido por snii_llm_identity_resolver.py
        })

    df_out = pd.DataFrame(rows, columns=COLS_2025)
    df_out.to_excel(output_path, index=False, sheet_name="4T_2025 (44,794)")
    print(f"   ✅ Guardado en: {output_path}")
    print(f"   📊 Filas: {len(df_out):,} | Columnas: {len(df_out.columns)}")


def run(dry_run: bool = False, batch_size: int = 500):
    personas, sin_cvu = load_and_group(PARQUET_PATH)

    if dry_run:
        print("\n[DRY-RUN] No se escribirá nada en Neo4j.")

    gs = Neo4jGraphStore()

    print("\n🔍 Consultando nodos Person existentes en Neo4j...")
    existing_cvus = fetch_existing_cvus(gs)
    print(f"   Person con CVU en Neo4j: {len(existing_cvus):,}")

    # Separar en: actualizar vs crear
    to_update = {}   # cvu → datos (ya existe en Neo4j)
    to_create = {}   # cvu → datos (nuevo nodo)

    for cvu, data in personas.items():
        if cvu in existing_cvus:
            data["person_id"] = existing_cvus[cvu]
            to_update[cvu] = data
        else:
            data["person_id"] = str(cvu)
            data["cvu_str"] = str(cvu)
            to_create[cvu] = data

    print(f"\n📊 Plan de ingesta:")
    print(f"   Actualizar (ya existen): {len(to_update):,}")
    print(f"   Crear (nuevos):          {len(to_create):,}")
    print(f"   Sin CVU (matching):      {len(sin_cvu):,}")

    # Exportar Excel de nuevos investigadores SIEMPRE (también en dry-run)
    # para poder alimentar snii_llm_identity_resolver.py
    export_nuevos_to_excel(to_create, PARQUET_PATH, NUEVOS_XLS_PATH)

    if dry_run:
        gs.close()
        return

    # ---- 1. Actualizar existentes ----
    print("\n⬆️  Actualizando Person existentes...")
    update_batch = list(to_update.values())
    with gs.driver.session() as session:
        for i in tqdm(range(0, len(update_batch), batch_size), desc="Actualizando"):
            chunk = update_batch[i:i + batch_size]
            try:
                session.run(UPDATE_EXISTING_QUERY, batch=chunk)
            except Exception as e:
                print(f"  [ERROR] batch {i}: {e}")

    # ---- 2. Crear nuevos (con afiliación institucional) ----
    print("\n🆕 Creando nuevos Person (con afiliación)...")
    create_batch = list(to_create.values())
    with gs.driver.session() as session:
        for i in tqdm(range(0, len(create_batch), batch_size), desc="Creando"):
            chunk = create_batch[i:i + batch_size]
            try:
                session.run(CREATE_NEW_PERSON_QUERY, batch=chunk)
            except Exception as e:
                print(f"  [ERROR] batch {i}: {e}")

    # ---- 3. Sin CVU: matching por nombre, luego crear aislados ----
    print("\n🔤 Procesando registros sin CVU...")
    existing_nombre_keys = fetch_existing_nombre_keys(gs)

    sin_cvu_update = []   # coincidieron con nodo existente
    sin_cvu_create = []   # no coincidieron → nodo aislado sintético

    for entry in sin_cvu:
        nk = entry["nombre_key"]
        if nk in existing_nombre_keys:
            entry["person_id"] = existing_nombre_keys[nk]
            sin_cvu_update.append(entry)
        else:
            # ID sintético: SNII_HIST_ + primeros 40 chars del nombre_key
            entry["person_id"] = "SNII_HIST_" + nk[:40]
            sin_cvu_create.append(entry)

    print(f"   Matched por nombre: {len(sin_cvu_update):,}")
    print(f"   Sin match (aislados): {len(sin_cvu_create):,}")

    # Actualizar matched
    if sin_cvu_update:
        with gs.driver.session() as session:
            for i in tqdm(range(0, len(sin_cvu_update), batch_size), desc="Actualizando sin CVU"):
                chunk = sin_cvu_update[i:i + batch_size]
                try:
                    session.run(UPDATE_EXISTING_QUERY, batch=chunk)
                except Exception as e:
                    print(f"  [ERROR] batch {i}: {e}")

    # Crear aislados
    if sin_cvu_create:
        with gs.driver.session() as session:
            for i in tqdm(range(0, len(sin_cvu_create), batch_size), desc="Creando aislados sin CVU"):
                chunk = sin_cvu_create[i:i + batch_size]
                try:
                    session.run(CREATE_ISOLATED_QUERY, batch=chunk)
                except Exception as e:
                    print(f"  [ERROR] batch {i}: {e}")

    gs.close()
    print("\n✅ ¡Ingesta completada!")
    print(f"   Actualizados:   {len(to_update) + len(sin_cvu_update):,}")
    print(f"   Creados nuevos: {len(to_create) + len(sin_cvu_create):,}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingesta del padrón histórico SNII en Neo4j")
    parser.add_argument("--dry-run", action="store_true", help="Simula sin escribir en Neo4j")
    parser.add_argument("--batch-size", type=int, default=500, help="Registros por transacción")
    args = parser.parse_args()

    run(dry_run=args.dry_run, batch_size=args.batch_size)
