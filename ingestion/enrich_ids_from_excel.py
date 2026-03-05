"""
enrich_ids_from_excel.py
────────────────────────
Enrichment bidireccional entre:
  • ingestion/profesores_<ENTIDAD>.json  (ORCID / scopus IDs)
  • data/ListadoICN-ORCID.xlsx           (ORCID / researcherID / Scopus ID)

Salidas:
  • JSON actualizado (in-place o con sufijo _enriched)
  • Excel actualizado (.xlsx)  con datos del JSON que no estaban

Uso:
    python ingestion/enrich_ids_from_excel.py
    python ingestion/enrich_ids_from_excel.py --json ingestion/profesores_Instituto_de_Ciencias_Nucleares.json
                                               --excel data/ListadoICN-ORCID.xlsx
"""

import json
import re
import unicodedata
import argparse
from pathlib import Path

import pandas as pd

# ─── Patrones de validación ────────────────────────────────────────────────────
ORCID_RE  = re.compile(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', re.IGNORECASE)
SCOPUS_RE = re.compile(r'^\d{8,13}$')


def _clean_orcid(val: str) -> str | None:
    """Devuelve el ORCID en formato 0000-0000-0000-000X o None."""
    if not val:
        return None
    val = str(val).strip()
    m = ORCID_RE.search(val)
    return m.group(0).upper() if m else None


def _clean_scopus(val) -> str | None:
    """Devuelve el Scopus ID numérico limpio o None."""
    if not val or (isinstance(val, float) and pd.isna(val)):
        return None
    val = str(val).strip()
    # URL scopus
    if 'authorId=' in val:
        val = val.split('authorId=')[-1].split('&')[0].strip()
    # Puede ser lista separada por comas
    parts = [p.strip() for p in val.split(';')]
    valid = [p for p in parts if SCOPUS_RE.match(p)]
    return '; '.join(valid) if valid else None


def _normalize_name(name: str) -> str:
    """Normaliza a minúsculas, sin acentos, sin doble espacio."""
    if not name:
        return ''
    nfkd = unicodedata.normalize('NFKD', str(name))
    no_accent = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return ' '.join(no_accent.lower().split())


def _excel_full_name(row) -> str:
    """Construye el nombre completo en formato 'APELLIDO1 APELLIDO2, NOMBRE' desde el Excel."""
    first   = _normalize_name(str(row.get('first_name', '') or ''))
    last    = _normalize_name(str(row.get('last_name',  '') or ''))
    surname = _normalize_name(str(row.get('sur_name',   '') or ''))  # segundo apellido
    apellidos = ' '.join(part for part in [last, surname] if part)
    return f"{apellidos}, {first}" if apellidos else first


def _json_full_name(key: str) -> str:
    return _normalize_name(key)


def _best_match(target: str, candidates: dict[str, str], threshold: float = 0.75) -> str | None:
    """
    Matching por tokens: busca el candidato cuyo nombre comparte la mayor
    proporción de palabras con 'target'. Si hay empate, usa Jaccard.
    threshold: fracción mínima de coincidencia para aceptar un match.
    """
    target_words = set(target.split())
    if not target_words:
        return None

    best_score = 0.0
    best_key   = None
    for cand_norm, cand_orig in candidates.items():
        cand_words = set(cand_norm.split())
        if not cand_words:
            continue
        intersection = target_words & cand_words
        # Jaccard
        jaccard = len(intersection) / len(target_words | cand_words)
        # Proporción sobre target
        prop = len(intersection) / len(target_words)
        score = max(jaccard, prop)
        if score > best_score:
            best_score = score
            best_key   = cand_orig

    return best_key if best_score >= threshold else None


# ─── Carga ─────────────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_excel(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str)
    df.columns = df.columns.str.strip()
    return df


# ─── Lógica principal ──────────────────────────────────────────────────────────

def enrich(json_path: Path, excel_path: Path, dry_run: bool = False):
    print(f"\n📂 JSON : {json_path}")
    print(f"📂 Excel: {excel_path}\n")

    prof_json  = load_json(json_path)
    df_excel   = load_excel(excel_path)

    # ── Índice normalizado del JSON ──────────────────────────────────────────────
    # key_norm → key_original
    json_index = {_json_full_name(k): k for k in prof_json}

    # ── Índice normalizado del Excel ─────────────────────────────────────────────
    # full_name_norm → row_index
    df_excel['_full_name'] = df_excel.apply(_excel_full_name, axis=1)
    excel_index = {row['_full_name']: idx for idx, row in df_excel.iterrows()}

    # ── Columnas de salida en Excel ──────────────────────────────────────────────
    for col in ['ORCID_from_json', 'Scopus_from_json', 'json_key']:
        if col not in df_excel.columns:
            df_excel[col] = ''

    matched         = 0
    json_updated    = 0
    excel_updated   = 0
    unmatched_json  = []
    unmatched_excel = []

    # ── 1. Enriquecer JSON con datos del Excel ───────────────────────────────────
    print("=" * 64)
    print(" JSON ← Excel: actualizando ORCID y Scopus ID en el JSON")
    print("=" * 64)

    for norm_json_name, orig_json_key in json_index.items():
        # Intentar match exacto primero
        excel_idx = excel_index.get(norm_json_name)

        # Fallback: match fuzzy
        if excel_idx is None:
            matched_name = _best_match(norm_json_name, excel_index)
            if matched_name:
                excel_idx = excel_index[matched_name]

        if excel_idx is None:
            unmatched_json.append(orig_json_key)
            continue

        row   = df_excel.loc[excel_idx]
        entry = prof_json[orig_json_key]
        changed = False

        # Nombre que usamos para el match (logging)
        excel_display = f"{row.get('first_name','')} {row.get('last_name','')}".strip()

        # ORCID: Excel es la fuente de verdad → siempre reemplazar si Excel tiene valor
        orcid_excel = _clean_orcid(str(row.get('ORCID', '') or ''))
        orcid_json  = _clean_orcid(str(entry.get('orcid', '') or ''))
        if orcid_excel:
            if not orcid_json:
                entry['orcid'] = orcid_excel
                changed = True
                print(f"  ✅ [{orig_json_key}]  ORCID  ← {orcid_excel}  (Excel: {excel_display})")
            elif orcid_excel != orcid_json:
                entry['orcid'] = orcid_excel
                changed = True
                print(f"  🔄 [{orig_json_key}]  ORCID  reemplazado: {orcid_json} → {orcid_excel}  (Excel gana)")

        # Scopus: MERGE de ambas listas (union deduplicada)
        scopus_excel_raw = _clean_scopus(row.get('authorID', '') or '')
        scopus_json_raw  = entry.get('scopus', '') or ''
        # Convertir ambos a sets de IDs
        existing_ids = {s.strip() for s in str(scopus_json_raw).split(';') if _clean_scopus(s.strip())}
        excel_ids    = {s.strip() for s in str(scopus_excel_raw or '').split(';') if _clean_scopus(s.strip())}
        all_ids = existing_ids | excel_ids
        added  = excel_ids - existing_ids
        if added:
            entry['scopus'] = '; '.join(sorted(all_ids))
            changed = True
            print(f"  ✅ [{orig_json_key}]  Scopus ← {added}  (Excel: {excel_display})")
        scopus_json  = _clean_scopus(entry.get('scopus', '') or '')

        # ResearcherID: Excel → JSON (si existe campo)
        rid_excel = str(row.get('researcherID', '') or '').strip()
        if rid_excel and not entry.get('researcher_id'):
            entry['researcher_id'] = rid_excel
            changed = True

        # Sexo: Excel → JSON
        sex_excel = str(row.get('sex', '') or '').strip().lower()
        if sex_excel and sex_excel not in ('nan', '') and not entry.get('sex'):
            entry['sex'] = sex_excel
            changed = True

        prof_json[orig_json_key] = entry
        if changed:
            json_updated += 1
        matched += 1

        # ── 2. Enriquecer Excel con datos del JSON ───────────────────────────────
        orcid_json_cleaned  = _clean_orcid(str(entry.get('orcid', '') or ''))
        scopus_json_cleaned = entry.get('scopus', '') or ''

        if not _clean_orcid(str(row.get('ORCID', '') or '')) and orcid_json_cleaned:
            df_excel.at[excel_idx, 'ORCID'] = orcid_json_cleaned
            df_excel.at[excel_idx, 'ORCID_from_json'] = '✓'
            excel_updated += 1
            print(f"  📊 [{excel_display}]  ORCID  → Excel  {orcid_json_cleaned}")

        # Scopus: escribir lista completa (merge) a una columna 'Scopus_merged' en el Excel
        if scopus_json_cleaned:
            df_excel.at[excel_idx, 'Scopus_merged']    = scopus_json_cleaned
            df_excel.at[excel_idx, 'Scopus_from_json'] = '✓'
            df_excel.at[excel_idx, 'json_key']         = orig_json_key
            excel_updated += 1

    # ── Unmatched en Excel ───────────────────────────────────────────────────────
    matched_excel_idxs = {excel_index.get(_json_full_name(k)) for k in json_index
                          if excel_index.get(_json_full_name(k)) is not None}
    for norm_ex, idx in excel_index.items():
        if idx not in matched_excel_idxs:
            row = df_excel.loc[idx]
            unmatched_excel.append(f"{row.get('first_name','')} {row.get('last_name','')}".strip())

    # ── Reporte ──────────────────────────────────────────────────────────────────
    print(f"\n{'='*64}")
    print(f"  Emparejados     : {matched}")
    print(f"  JSON actualizados: {json_updated}")
    print(f"  Excel actualizados: {excel_updated}")
    print(f"  Sin match en JSON: {len(unmatched_json)}")
    print(f"  Sin match en Excel: {len(unmatched_excel)}")

    if unmatched_json:
        print(f"\n  Sin match (JSON → Excel):")
        for name in sorted(unmatched_json): print(f"    - {name}")

    if unmatched_excel:
        print(f"\n  Sin match (Excel → JSON):")
        for name in sorted(unmatched_excel): print(f"    - {name}")

    # ── Guardar ──────────────────────────────────────────────────────────────────
    if dry_run:
        print("\n🔍 DRY-RUN: no se escribieron cambios.")
        return

    # JSON
    out_json = json_path
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(prof_json, f, indent=4, ensure_ascii=False)
    print(f"\n💾 JSON guardado : {out_json}")

    # Excel
    df_excel.drop(columns=['_full_name'], errors='ignore', inplace=True)
    out_excel = excel_path.with_stem(excel_path.stem + '_enriched')
    df_excel.to_excel(out_excel, index=False)
    print(f"💾 Excel guardado: {out_excel}")


# ─── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Enriquecimiento bidireccional JSON ↔ Excel de IDs académicos.')
    parser.add_argument('--json',   default='ingestion/profesores_Instituto_de_Ciencias_Nucleares.json',
                        help='Ruta al JSON de profesores')
    parser.add_argument('--excel',  default='data/ListadoICN-ORCID.xlsx',
                        help='Ruta al Excel con IDs')
    parser.add_argument('--dry-run', action='store_true',
                        help='Mostrar cambios sin escribir archivos')
    args = parser.parse_args()

    enrich(Path(args.json), Path(args.excel), dry_run=args.dry_run)
