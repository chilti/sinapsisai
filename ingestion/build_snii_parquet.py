"""
build_snii_parquet.py
=====================
Consolida los 41 archivos Excel del padrón histórico SNII (1984-2025)
en un único archivo Parquet local con schema normalizado.

Reglas de selección de hoja:
  - Archivos de 1 hoja: se usa la única hoja disponible.
  - 2022 (3 hojas): se usa la hoja '2022'.
  - 2023 (4 hojas trimestrales): se usa el 4T (cierre de año).
  - 2024 (4 hojas trimestrales): se usa el 4T (cierre de año).
  - 2025 (6 hojas): se usa el 4T (cierre de año).

Reglas de identificador (CVU):
  - 1984–1999: EXPEDIENTE se trata como CVU (misma numeración).
  - 2000–2002: columna CVU existe pero vacía → usar EXPEDIENTE.
  - 2003+:     columna CVU.

Schema de salida (snii_historico.parquet):
  year, cvu, nombre, nombre_key, nivel, area, disciplina,
  subdisciplina, especialidad, institucion, dependencia,
  subdependencia, entidad, pais, fecha_inicio, fecha_fin,
  snii_active_2025, source_sheet
"""

import os
import sys
import re
import unicodedata
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "snii"
OUTPUT_PATH = DATA_DIR / "snii_historico.parquet"

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def normalize_key(s: str) -> str:
    """Nombre normalizado para comparación: minúsculas, sin acentos, sin comas ni espacios."""
    if not s or pd.isna(s):
        return ""
    s = str(s).strip()
    # Quitar acentos
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Minúsculas, sin comas ni espacios
    s = re.sub(r"[,\s]+", "", s.lower())
    return s


def clean_str(val) -> str | None:
    """Convierte a str strip+upper; retorna None si vacío/NaN/SIN INFORMACIÓN."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().upper()
    if s in ("", "NAN", "SIN INFORMACIÓN", "SIN INFORMACION", "NO APLICA", "-"):
        return None
    return s


def normalize_nivel(val) -> str | None:
    """Normaliza el nivel: C, 1, 2, 3, E, etc."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip().upper()
    mapping = {
        "CANDIDATO": "C", "CANDIDATURA": "C", "C": "C",
        "CANDIDATO(A) A INVESTIGADORA O INVESTIGADOR NACIONAL": "C",
        "1": "1", "I": "1", "NIVEL I": "1", "NIVEL 1": "1",
        "INVESTIGADOR(A) NACIONAL NIVEL I": "1",
        "INVESTIGADORA O INVESTIGADOR NACIONAL NIVEL I": "1",
        "2": "2", "II": "2", "NIVEL II": "2", "NIVEL 2": "2",
        "INVESTIGADOR(A) NACIONAL NIVEL II": "2",
        "INVESTIGADORA O INVESTIGADOR NACIONAL NIVEL II": "2",
        "3": "3", "III": "3", "NIVEL III": "3", "NIVEL 3": "3",
        "INVESTIGADOR(A) NACIONAL NIVEL III": "3",
        "INVESTIGADORA O INVESTIGADOR NACIONAL NIVEL III": "3",
        "E": "E", "EMÉRITO": "E", "EMERITO": "E",
        "EM": "E",
    }
    return mapping.get(s, s)


def to_date(val):
    """Convierte a date o None."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return pd.to_datetime(val, dayfirst=False, errors="coerce").date()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Selección de hoja correcta por año
# ---------------------------------------------------------------------------

def select_sheet(xl: pd.ExcelFile, year: int) -> str:
    sheets = xl.sheet_names

    if len(sheets) == 1:
        return sheets[0]

    # 2022: hoja nombrada '2022'
    if year == 2022:
        if "2022" in sheets:
            return "2022"
        # fallback: última hoja
        return sheets[-1]

    # 2023: buscar T4
    t4_patterns = ["4T", "4t", "T4", "t4", "4°T", "PADRÓN 4T", "4T_"]
    for s in sheets:
        if any(p in s for p in t4_patterns):
            return s

    # 2024/2025: mismo patrón
    for s in sheets:
        if "4T" in s.upper() or "T4" in s.upper():
            return s

    # fallback: última hoja con datos (evitar CPI, OBSERVACIONES)
    data_sheets = [s for s in sheets if s.upper() not in ("CPI", "OBSERVACIONES", "NOTAS")]
    return data_sheets[-1] if data_sheets else sheets[-1]


# ---------------------------------------------------------------------------
# Extracción de CVU de cada fila según la era
# ---------------------------------------------------------------------------

def extract_cvu(row: pd.Series, era: str) -> int | None:
    """
    Era puede ser:
      'pre2003'  → usar EXPEDIENTE como CVU
      'post2003' → usar columna CVU (ya normalizada a 'cvu_raw')
    """
    if era == "pre2003":
        val = row.get("exp_raw")
    else:
        val = row.get("cvu_raw")
        if val is None or (isinstance(val, float) and pd.isna(val)):
            # Fallback a expediente si existe
            val = row.get("exp_raw")

    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        v = int(float(str(val).strip()))
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Mapeo de columnas por época → diccionario de extracción
# ---------------------------------------------------------------------------

COLUMN_ALIASES = {
    # CVU
    "cvu": [
        "CVU padrón corregido", "CVU", "CVU (a partir de 2003)",
    ],
    # Expediente
    "expediente": ["EXPEDIENTE"],
    # Nombre
    "nombre": [
        "NOMBRE DEL INVESTIGADOR",
        "NOMBRE DE LA INVESTIGADORA O DEL INVESTIGADOR",
        "NOMBRE DE LA INVESTIGADORA O INVESTIGADOR",
        "NOMBRE",  # hoja 2022
    ],
    # Nivel
    "nivel": ["NIVEL"],
    # Area
    "area": [
        "ÁREA DEL CONOCIMIENTO", "ÁREA DE CONOCIMIENTO",
        "AREA DEL CONOCIMIENTO", "AREA DE CONOCIMIENTO",
    ],
    # Disciplina
    "disciplina": [
        "DISCIPLINA", "DISCIPLINA (a partir de 1991)",
    ],
    # Subdisciplina
    "subdisciplina": [
        "SUBDISCIPLINA", "SUBDISCIPLINA (a partir de 1991)",
        "SUBDISCIPLINA ",  # con espacio trailing en algunos años
    ],
    # Especialidad
    "especialidad": [
        "ESPECIALIDAD", "ESPECIALIDAD (a partir de 1991)",
        "ESPECIALIDAD ",
    ],
    # Institución
    "institucion": [
        "INSTITUCIÓN DE ACREDITACIÓN",
        "INSTITUCIÓN DE ADSCRIPCIÓN",
        "INSTITUCIÓN DE ADSCRIPCIÓN (a partir de 1990)",
        "INSTITUCIÓN DE ADSCRIPCIÓN ",
        "INSTITUCION DE ADSCRIPCIÓN",   # 2022: sin tilde en INSTITUCIÓN
        "INSTITUCION DE ADSCRIPCION",
    ],
    # Dependencia
    "dependencia": [
        "DEPENDENCIA DE ACREDITACIÓN",
        "DEPENDENCIA",
        "DEPENDENCIA (a partir de 1991)",
        "DEPENDENCIA ",
        "DEPENDENCIA DE ADSCRIPCIÓN",
    ],
    # Subdependencia
    "subdependencia": [
        "SUBDEPENDENCIA DE ACREDITACIÓN",
    ],
    # Entidad
    "entidad": [
        "ENTIDAD DE ACREDITACIÓN",
        "ENTIDAD FEDERATIVA",
        "ENTIDAD FEDERATIVA ADSCRIPCIÓN\n(a partir de 1990)",
        "ENTIDAD FEDERATIVA DE ADSCRIPCIÓN",
        "ENTIDAD FEDERATIVA ",
    ],
    # País
    "pais": [
        "PAÍS DE ADSCRIPCIÓN",
        "PAIS",
        "PAIS ADSCRIPCIÓN \n(a partir de 1990)",
        "PAIS ",
    ],
    # Fechas
    "fecha_inicio": [
        "FECHA DE INICIO DE VIGENCIA",
        "FECHA INICIO DE VIGENCIA",
    ],
    "fecha_fin": [
        "FECHA DE FIN DE VIGENCIA",
        "FECHA FIN DE VIGENCIA",
    ],
}


def find_col(df_cols: list[str], aliases: list[str]) -> str | None:
    """Busca la primera columna que coincida (comparación case-insensitive y con strip)."""
    cols_clean = {c.strip(): c for c in df_cols}
    for alias in aliases:
        if alias.strip() in cols_clean:
            return cols_clean[alias.strip()]
        # También buscar case-insensitive
        for orig_stripped, orig in cols_clean.items():
            if orig_stripped.lower() == alias.strip().lower():
                return orig
    return None


def map_row(row: pd.Series, col_map: dict, era: str, year: int, source_sheet: str) -> dict:
    """Convierte una fila del Excel al schema normalizado."""
    cvu = extract_cvu(row, era)
    nombre_raw = row.get("nombre_raw", "")
    nombre = clean_str(nombre_raw) or ""

    return {
        "year": year,
        "cvu": cvu,
        "nombre": nombre,
        "nombre_key": normalize_key(nombre_raw),
        "nivel": normalize_nivel(row.get("nivel_raw")),
        "area": clean_str(row.get("area_raw")),
        "disciplina": clean_str(row.get("disciplina_raw")),
        "subdisciplina": clean_str(row.get("subdisciplina_raw")),
        "especialidad": clean_str(row.get("especialidad_raw")),
        "institucion": clean_str(row.get("institucion_raw")),
        "dependencia": clean_str(row.get("dependencia_raw")),
        "subdependencia": clean_str(row.get("subdependencia_raw")),
        "entidad": clean_str(row.get("entidad_raw")),
        "pais": clean_str(row.get("pais_raw")),
        "fecha_inicio": to_date(row.get("fecha_inicio_raw")),
        "fecha_fin": to_date(row.get("fecha_fin_raw")),
        "source_sheet": source_sheet,
    }


# ---------------------------------------------------------------------------
# Proceso de un único archivo Excel
# ---------------------------------------------------------------------------

def process_file(path: Path, year: int) -> pd.DataFrame:
    xl = pd.ExcelFile(path)
    sheet = select_sheet(xl, year)
    df = xl.parse(sheet)

    # Determinar era para lógica de CVU
    era = "pre2003" if year < 2003 else "post2003"

    cols = list(df.columns)

    # Construir un DataFrame intermedio con los campos crudos que necesitamos
    raw_cols = {}
    raw_cols["cvu_raw"] = find_col(cols, COLUMN_ALIASES["cvu"])
    raw_cols["exp_raw"] = find_col(cols, COLUMN_ALIASES["expediente"])
    raw_cols["nombre_raw"] = find_col(cols, COLUMN_ALIASES["nombre"])
    raw_cols["nivel_raw"] = find_col(cols, COLUMN_ALIASES["nivel"])
    raw_cols["area_raw"] = find_col(cols, COLUMN_ALIASES["area"])
    raw_cols["disciplina_raw"] = find_col(cols, COLUMN_ALIASES["disciplina"])
    raw_cols["subdisciplina_raw"] = find_col(cols, COLUMN_ALIASES["subdisciplina"])
    raw_cols["especialidad_raw"] = find_col(cols, COLUMN_ALIASES["especialidad"])
    raw_cols["institucion_raw"] = find_col(cols, COLUMN_ALIASES["institucion"])
    raw_cols["dependencia_raw"] = find_col(cols, COLUMN_ALIASES["dependencia"])
    raw_cols["subdependencia_raw"] = find_col(cols, COLUMN_ALIASES["subdependencia"])
    raw_cols["entidad_raw"] = find_col(cols, COLUMN_ALIASES["entidad"])
    raw_cols["pais_raw"] = find_col(cols, COLUMN_ALIASES["pais"])
    raw_cols["fecha_inicio_raw"] = find_col(cols, COLUMN_ALIASES["fecha_inicio"])
    raw_cols["fecha_fin_raw"] = find_col(cols, COLUMN_ALIASES["fecha_fin"])

    # Construir un DF de trabajo con columnas renombradas
    work = pd.DataFrame()
    for alias, orig_col in raw_cols.items():
        if orig_col and orig_col in df.columns:
            work[alias] = df[orig_col]
        else:
            work[alias] = None

    # Convertir cada fila
    records = []
    for _, row in work.iterrows():
        records.append(map_row(row, raw_cols, era, year, sheet))

    result = pd.DataFrame(records)
    # Filtrar filas sin nombre (headers duplicados, etc.)
    result = result[result["nombre"].str.len() > 2].copy()
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build():
    all_files = sorted(DATA_DIR.glob("Investigadores_vigentes_*.xlsx"))
    if not all_files:
        print(f"❌ No se encontraron archivos en {DATA_DIR}")
        sys.exit(1)

    print(f"📂 Procesando {len(all_files)} archivos...")

    # Primero construimos el set de CVUs activos en 2025 (T4)
    path_2025 = DATA_DIR / "Investigadores_vigentes_2025.xlsx"
    xl25 = pd.ExcelFile(path_2025)
    sheet_2025 = select_sheet(xl25, 2025)
    df25 = xl25.parse(sheet_2025)
    cvu_col_2025 = find_col(list(df25.columns), COLUMN_ALIASES["cvu"])
    active_cvus_2025: set[int] = set(
        pd.to_numeric(df25[cvu_col_2025], errors="coerce").dropna().astype(int)
    ) if cvu_col_2025 else set()
    print(f"✅ CVUs activos en 2025 (T4): {len(active_cvus_2025):,}")

    all_dfs = []
    for path in all_files:
        year = int(path.stem.replace("Investigadores_vigentes_", ""))
        try:
            df_year = process_file(path, year)
            all_dfs.append(df_year)
            print(f"  {year}: {len(df_year):>6} registros")
        except Exception as e:
            print(f"  ⚠️  {year}: ERROR — {e}")

    print("\n🔀 Consolidando...")
    full = pd.concat(all_dfs, ignore_index=True)

    # Añadir snii_active_2025
    full["snii_active_2025"] = full["cvu"].apply(
        lambda c: (int(c) in active_cvus_2025) if (c is not None and not pd.isna(c)) else False
    )

    # Asegurar tipos correctos
    full["year"] = full["year"].astype("int16")
    full["cvu"] = pd.to_numeric(full["cvu"], errors="coerce").astype("Int32")
    full["snii_active_2025"] = full["snii_active_2025"].astype(bool)

    print(f"\n📊 Total filas: {len(full):,}")
    print(f"   CVUs únicos: {full['cvu'].dropna().nunique():,}")
    print(f"   Activos 2025: {full['snii_active_2025'].sum():,}")
    print(f"   Sin CVU: {full['cvu'].isna().sum():,}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    full.to_parquet(OUTPUT_PATH, index=False)
    print(f"\n✅ Guardado en: {OUTPUT_PATH}")
    print(f"   Tamaño: {OUTPUT_PATH.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    build()
