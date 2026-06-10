"""
SNII/enrich_snii_oa_ids.py
───────────────────────────
Enriquece los JSONs del pipeline SNII con:
  1. OpenAlex Author IDs  (campo 'matched_openalex_id' / 'openalex_id')
  2. Scopus Author IDs    (campo 'scopus_ids') — recuperados desde el perfil ORCID

Flujo de resolución de OA ID (local-first):
  a. ORCID  → ClickHouse  `authors WHERE orcid = ?`
  b. Scopus → ClickHouse  `JSONExtractString(raw_data, 'ids', 'scopus') = ?`
  c. pyalex (API oficial) — solo si --no-local está activo

Flujo de enriquecimiento de Scopus IDs:
  → ORCID /external-identifiers → Scopus Author ID(s) del investigador

Archivos soportados:
  - data/snii_llm_verified_matches.json  (formato SNII:    campo 'matched_orcid')
  - data/*/profesores*.json              (formato scraper:  campo 'orcid')
  - cualquier JSON pasado como argumento

Uso:
  python SNII/enrich_snii_oa_ids.py
  python SNII/enrich_snii_oa_ids.py --input data/snii_llm_verified_matches.json
  python SNII/enrich_snii_oa_ids.py --dir data/FCiencias
  python SNII/enrich_snii_oa_ids.py --no-local           # habilita pyalex como fallback
  python SNII/enrich_snii_oa_ids.py --force              # re-resuelve aunque ya tenga OA ID
  python SNII/enrich_snii_oa_ids.py --dry-run            # imprime sin modificar archivos
  python SNII/enrich_snii_oa_ids.py --skip-scopus        # solo resuelve OA ID, no Scopus
"""

import os
import sys
import json
import argparse
import time
import re
import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ingestion.openalex_utils import resolve_author_oa_id


# ── Constantes ──────────────────────────────────────────────────────────────
_ROOT      = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DEFAULT_IN = os.path.join(_ROOT, 'data', 'snii_llm_verified_matches.json')


# ── Helpers de formato ───────────────────────────────────────────────────────

def _get_orcid(record: dict) -> str | None:
    """Extrae el ORCID del registro independientemente del formato del JSON."""
    return (record.get('matched_orcid')
            or record.get('orcid')
            or None)


def _get_scopus(record: dict) -> list:
    """Extrae los Scopus IDs ya existentes en el registro."""
    raw = record.get('scopus_ids') or record.get('scopus') or []
    if isinstance(raw, str):
        raw = [s.strip() for s in raw.replace(';', ',').split(',') if s.strip()]
    return list(raw) if isinstance(raw, list) else []


def _get_name(record: dict) -> str:
    """Nombre legible del investigador para logs."""
    return (record.get('snii_author')
            or record.get('name')
            or record.get('original_name')
            or '?')


def _already_has_oa_id(record: dict) -> bool:
    return bool(
        record.get('matched_openalex_id')
        or record.get('openalex_id')
        or record.get('openalex_ids')
    )


def _set_oa_id(record: dict, oa_id: str) -> None:
    """Escribe el OA ID en el campo canónico según el formato del JSON."""
    if 'snii_author' in record:
        record['matched_openalex_id'] = oa_id
    else:
        record['openalex_id'] = oa_id


def _set_scopus_ids(record: dict, ids: list) -> None:
    """Escribe los Scopus IDs en el campo canónico del registro."""
    existing = _get_scopus(record)
    nuevos = [s for s in ids if s not in existing]
    if not nuevos:
        return
    merged = existing + nuevos
    if 'snii_author' in record:
        record['scopus_ids'] = merged
    else:
        record['scopus'] = merged


# ── Scopus IDs desde perfil ORCID ───────────────────────────────────────────

def obtener_scopus_ids_de_orcid(orcid_url: str) -> list:
    """
    Consulta el endpoint /external-identifiers del perfil ORCID del investigador
    para recuperar sus Scopus Author IDs vinculados.
    Retorna lista de strings, posiblemente vacía.
    """
    if not orcid_url:
        return []
    orcid_id = str(orcid_url).rstrip('/').split('/')[-1]
    if not re.search(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', orcid_id, re.IGNORECASE):
        return []

    url = f"https://pub.orcid.org/v3.0/{orcid_id}/external-identifiers"
    try:
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
        if resp.status_code != 200:
            return []
        ext_ids = resp.json().get('external-identifier', [])
        found = [
            str(eid['external-id-value']).strip()
            for eid in ext_ids
            if isinstance(eid, dict)
            and eid.get('external-id-type', '').lower() == 'scopus author id'
            and eid.get('external-id-value')
        ]
        return found
    except Exception as e:
        print(f"    [WARN] ORCID external-identifiers ({orcid_id}): {e}")
        return []


# ── Proceso principal ────────────────────────────────────────────────────────

def enrich_file(
    json_path: str,
    force: bool,
    force_local: bool,
    dry_run: bool,
    skip_scopus: bool,
) -> dict:
    """
    Enriquece un único JSON con OA IDs y Scopus IDs.
    Retorna estadísticas.
    """
    print(f"\n📂 Procesando: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    # Normalizar: el JSON puede ser list o dict
    if isinstance(raw, dict):
        records = list(raw.values())
        is_dict = True
    else:
        records = raw
        is_dict = False

    stats = {
        'total': len(records),
        'oa_resueltos': 0, 'oa_ya_tenian': 0, 'oa_fallidos': 0,
        'scopus_nuevos': 0, 'sin_ids': 0,
    }

    modified = False

    for rec in records:
        if not isinstance(rec, dict):
            continue

        name  = _get_name(rec)
        orcid = _get_orcid(rec)

        # ── Paso A: Scopus IDs desde ORCID ──────────────────────────────────
        if not skip_scopus and orcid:
            orcid_scopus = obtener_scopus_ids_de_orcid(orcid)
            if orcid_scopus:
                existing_scopus = _get_scopus(rec)
                nuevos = [s for s in orcid_scopus if s not in existing_scopus]
                if nuevos:
                    print(f"  🔗 {name}: Scopus IDs ORCID → {nuevos}")
                    if not dry_run:
                        _set_scopus_ids(rec, orcid_scopus)
                        modified = True
                    stats['scopus_nuevos'] += len(nuevos)

        # ── Paso B: OpenAlex Author ID ───────────────────────────────────────
        if _already_has_oa_id(rec) and not force:
            stats['oa_ya_tenian'] += 1
            continue

        scopus = _get_scopus(rec)  # puede haber sido enriquecido en Paso A

        if not orcid and not scopus:
            stats['sin_ids'] += 1
            continue

        oa_ids_found = resolve_author_oa_id(
            orcid=orcid,
            scopus_ids=scopus,
            force_local=force_local,
        )

        if oa_ids_found:
            if not dry_run:
                # Guardar el primero como campo canonical; los demás se usan en ingesta
                _set_oa_id(rec, oa_ids_found[0])
                if len(oa_ids_found) > 1:
                    rec['openalex_ids'] = oa_ids_found
                modified = True
            stats['oa_resueltos'] += 1
            print(f"  ✅ {name}: {oa_ids_found}")
        else:
            stats['oa_fallidos'] += 1
            print(f"  ⚠️  {name}: OA ID no encontrado "
                  f"(ORCID={orcid or '—'}, Scopus={scopus or '—'})")

        # Pausa mínima si pyalex está activo
        if not force_local and not oa_ids_found:
            time.sleep(0.2)

    # ── Guardar ──────────────────────────────────────────────────────────────
    if not dry_run and modified:
        if is_dict:
            with open(json_path, 'r', encoding='utf-8') as f:
                original = json.load(f)
            for key, val in zip(original.keys(), records):
                original[key] = val
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(original, f, ensure_ascii=False, indent=2)
        else:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"  💾 JSON actualizado.")
    elif dry_run:
        print(f"  👁  Dry-run: no se modificó el archivo.")

    return stats


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Enriquece JSONs SNII/profesores con OpenAlex IDs y Scopus IDs"
    )
    parser.add_argument(
        '--input', '-i', nargs='+',
        help=("Archivo(s) JSON a procesar. "
              "Por defecto: data/snii_llm_verified_matches.json")
    )
    parser.add_argument(
        '--dir', '-d',
        help="Directorio: procesa todos los profesores*.json dentro de él."
    )
    parser.add_argument(
        '--force', action='store_true',
        help="Re-resolver incluso los registros que ya tienen OA ID."
    )
    parser.add_argument(
        '--no-local', dest='no_local', action='store_true',
        help="Habilita pyalex como fallback adicional (además de ClickHouse)."
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help="Imprime lo que haría pero NO modifica los archivos."
    )
    parser.add_argument(
        '--skip-scopus', action='store_true',
        help="Omite la resolución de Scopus IDs desde ORCID."
    )
    args = parser.parse_args()

    # Resolver archivos a procesar
    paths = []
    if args.input:
        paths = [os.path.abspath(p) for p in args.input if os.path.isfile(p)]
    elif args.dir:
        d = os.path.abspath(args.dir)
        paths = sorted([
            os.path.join(d, f) for f in os.listdir(d)
            if f.startswith('profesores') and f.endswith('.json')
        ])
    else:
        paths = [DEFAULT_IN]

    if not paths:
        print("❌ No se encontraron archivos para procesar.")
        sys.exit(1)

    force_local = not args.no_local  # por defecto: solo ClickHouse

    total = {
        'total': 0, 'oa_resueltos': 0, 'oa_ya_tenian': 0,
        'oa_fallidos': 0, 'scopus_nuevos': 0, 'sin_ids': 0,
    }

    for p in paths:
        st = enrich_file(
            p,
            force=args.force,
            force_local=force_local,
            dry_run=args.dry_run,
            skip_scopus=args.skip_scopus,
        )
        for k in total:
            total[k] += st[k]

    print(f"\n{'='*60}")
    print(f"📊 RESUMEN ({len(paths)} archivo(s))")
    print(f"   Total registros     : {total['total']}")
    print(f"   ✅ OA IDs resueltos : {total['oa_resueltos']}")
    print(f"   📌 Ya tenían OA ID  : {total['oa_ya_tenian']}")
    print(f"   ❌ OA no encontrado : {total['oa_fallidos']}")
    print(f"   🔗 Scopus IDs nuevos: {total['scopus_nuevos']}")
    print(f"   ⚠️  Sin ORCID/Scopus : {total['sin_ids']}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
