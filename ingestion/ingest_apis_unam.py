"""
ingest_apis_unam.py
───────────────────
Wrapper especializado de ingest_apis.py para procesar todos los archivos JSON
de data/UNAM/ generados por siia_scraper_snii.py.

Diferencia clave respecto a ingest_apis.py:
  - No requiere --hierarchy manual.
  - Consulta el Excel del SNII para determinar automáticamente si cada entidad
    del nombre de archivo es una Subdependencia o una Dependencia de la UNAM.
  - Pasa la jerarquía correcta (institución / dependencia / subdependencia) a
    process_and_ingest_academics() para cada archivo.
  - El matching de entidades usa normalización de texto (sin acentos, uppercase)
    para ser robusto ante variaciones entre versiones del Excel.

Uso:
  python ingestion/ingest_apis_unam.py [--force] [--ch] [--local] [--limit_acads N] [--name "APELLIDO"]
  python ingestion/ingest_apis_unam.py data/UNAM/profesores_SNII_FACULTAD_DE_INGENIERIA.json
"""

import os
import sys
import argparse
import unicodedata
import pandas as pd
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def _normalize(text: str) -> str:
    """Normaliza para comparación: quita acentos, pasa a mayúsculas, colapsa espacios."""
    if not text:
        return ''
    nfkd = unicodedata.normalize('NFD', str(text))
    ascii_str = ''.join(c for c in nfkd if unicodedata.category(c) != 'Mn')
    return ' '.join(ascii_str.upper().split())


# Importar la función de ingesta del script genérico
from ingestion.ingest_apis import process_and_ingest_academics, graph_store

# ── Constantes ─────────────────────────────────────────────────────────────────
INST_NAME  = "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)"
DATA_DIR   = os.path.join(os.path.dirname(__file__), '..', 'data', 'UNAM')
_ROOT      = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SNII_PATH  = os.path.join(_ROOT, 'data', 'Investigadores_vigentes_2025.xlsx')
SNII_SHEET = '4T_2025 (44,794)'

INST_COL = 'INSTITUCION DE ACREDITACION'
DEP_COL  = 'DEPENDENCIA DE ACREDITACIÓN'
SUB_COL  = 'SUBDEPENDENCIA DE ACREDITACIÓN'


def _build_entity_map() -> dict:
    """
    Lee el Excel SNII y construye un mapa:
        normalize(entity_name) -> {'dep': str, 'sub': str | None, 'dep_raw': str, 'sub_raw': str}

    Las claves están normalizadas (sin acentos, uppercase) para que el match
    sea robusto ante diferencias entre versiones del Excel.
    """
    print(f"📋 Cargando padrón SNII para mapeo de jerarquía...")
    df = pd.read_excel(SNII_PATH, sheet_name=SNII_SHEET)
    df_unam = df[df[INST_COL] == INST_NAME].copy()

    entity_map = {}  # normalized_key -> {dep, sub, dep_raw, sub_raw}
    _invalid = {'NAN', 'SIN INFORMACIÓN', 'SIN INFORMACION', 'NO APLICA', ''}

    for _, row in df_unam.iterrows():
        dep_raw = str(row[DEP_COL]).strip() if pd.notna(row[DEP_COL]) else ''
        sub_raw = str(row[SUB_COL]).strip() if pd.notna(row[SUB_COL]) else ''
        dep_norm = _normalize(dep_raw)
        sub_norm = _normalize(sub_raw)

        if sub_norm and sub_norm not in _invalid:
            if sub_norm not in entity_map:
                entity_map[sub_norm] = {
                    'dep':     dep_raw if dep_norm and dep_norm not in _invalid else None,
                    'sub':     sub_raw,
                    'dep_raw': dep_raw,
                    'sub_raw': sub_raw,
                }
        elif dep_norm and dep_norm not in _invalid:
            if dep_norm not in entity_map:
                entity_map[dep_norm] = {
                    'dep':     dep_raw,
                    'sub':     None,
                    'dep_raw': dep_raw,
                    'sub_raw': None,
                }

    print(f"   → {len(entity_map)} entidades únicas de UNAM mapeadas.")
    return entity_map


def _entity_name_from_filename(filename: str) -> str:
    """
    Convierte 'profesores_SNII_FACULTAD_DE_INGENIERIA.json'
    → 'FACULTAD DE INGENIERIA'
    """
    base = os.path.basename(filename)
    base = base.replace('profesores_SNII_', '').replace('.json', '')
    return base.replace('_', ' ').strip()


def _resolve_hierarchy(entity_name: str, entity_map: dict) -> tuple[str, str | None, str | None]:
    """
    Retorna (institución, dependencia, subdependencia) para una entidad dada.
    Usa _normalize() para comparar sin acentos ni diferencias de mayúsculas.
    """
    key = _normalize(entity_name)

    # 1. Coincidencia exacta (normalizada)
    if key in entity_map:
        entry = entity_map[key]
        return INST_NAME, entry['dep'], entry['sub']

    # 2. Coincidencia parcial (el nombre del archivo contiene o está contenido)
    for map_key, entry in entity_map.items():
        if key in map_key or map_key in key:
            print(f"   ⚠️  Match parcial: '{entity_name}' → '{entry.get('sub_raw') or entry.get('dep_raw')}'")
            return INST_NAME, entry['dep'], entry['sub']

    # 3. Fallback: asumir que es una dependencia no registrada
    print(f"   ❌ '{entity_name}' no encontrada en el Excel. Se usará como dependencia.")
    return INST_NAME, entity_name, None


def _resolve_openalex_author_id(orcid: str, scopus_ids: list, force_local: bool = False) -> list:
    """
    Delegado a openalex_utils.resolve_author_oa_id (devuelve lista de Author IDs).
    """
    from ingestion import openalex_utils
    return openalex_utils.resolve_author_oa_id(
        orcid=orcid,
        scopus_ids=scopus_ids,
        force_local=force_local,
    )



def _enrich_json_with_openalex_ids(json_path: str, force_local: bool = False) -> int:
    """
    Lee el JSON de académicos, resuelve el openalex_id para quienes no lo tienen
    (usando ORCID o Scopus ID) y sobreescribe el archivo con los datos enriquecidos.
    Retorna el número de IDs nuevos encontrados.
    """
    import json as _json

    with open(json_path, encoding='utf-8') as f:
        data = _json.load(f)

    nuevos = 0
    for name, rec in data.items():
        if not isinstance(rec, dict):
            continue
        if rec.get('openalex_id'):          # ya resuelto → saltar
            continue
        if rec.get('siia') == 'No encontrado':  # sin perfil → saltar
            continue

        orcid     = rec.get('orcid', '') or ''
        scopus    = rec.get('scopus', []) or []
        if not orcid and not scopus:
            continue

        oa_ids_found = _resolve_openalex_author_id(orcid, scopus, force_local=force_local)
        if oa_ids_found:
            rec['openalex_id']  = oa_ids_found[0]
            if len(oa_ids_found) > 1:
                rec['openalex_ids'] = oa_ids_found
            nuevos += 1
            print(f"      🔑 OA ID(s) resueltos para {name}: {oa_ids_found}")

    if nuevos:
        with open(json_path, 'w', encoding='utf-8') as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)

    return nuevos


def main():
    parser = argparse.ArgumentParser(
        description="Ingesta UNAM: procesa todos los JSON de data/UNAM/ con jerarquía automática."
    )
    parser.add_argument("input", nargs="?",
                        help="Archivo JSON específico o directorio. Por defecto: data/UNAM/")
    parser.add_argument("--limit_acads", type=int,
                        help="Límite de académicos por entidad (pruebas)")
    parser.add_argument("--name", type=str,
                        help="Filtrar por un académico específico")
    parser.add_argument("--force", action="store_true",
                        help="Re-ingestar académicos ya existentes")
    parser.add_argument("--local", action="store_true",
                        help="Usar API local de OpenAlex (no oficial) y SDK lmstudio para embeddings")
    parser.add_argument("--ch", action="store_true",
                        help="Sincronizar con ClickHouse (Dual Write)")
    parser.add_argument("--source", type=str,
                        help="Forzar origen (wos, scopus, pubmed, doaj)")
    args = parser.parse_args()

    # ── Construir mapa de jerarquía ──────────────────────────────────────────
    entity_map = _build_entity_map()

    # ── Resolver archivos a procesar ─────────────────────────────────────────
    input_paths = []
    if args.input:
        p = os.path.abspath(args.input)
        if os.path.isfile(p):
            input_paths = [p]
        elif os.path.isdir(p):
            input_paths = sorted([
                os.path.join(p, f) for f in os.listdir(p)
                if f.startswith('profesores_') and f.endswith('.json')
            ])
    
    if not input_paths:
        data_dir = os.path.abspath(DATA_DIR)
        if os.path.exists(data_dir):
            input_paths = sorted([
                os.path.join(data_dir, f) for f in os.listdir(data_dir)
                if f.startswith('profesores_') and f.endswith('.json')
            ])

    if not input_paths:
        print("❌ No se encontraron archivos para procesar.")
        sys.exit(1)

    print(f"\n🚀 Procesando {len(input_paths)} archivos de entidad UNAM...\n")

    try:
        for json_file in input_paths:
            entity_name = _entity_name_from_filename(json_file)
            h_inst, h_dep, h_sub = _resolve_hierarchy(entity_name, entity_map)

            print(f"\n{'='*70}")
            print(f"📂 ARCHIVO  : {os.path.basename(json_file)}")
            print(f"🏛️  Institución  : {h_inst}")
            print(f"🏢  Dependencia  : {h_dep or '—'}")
            print(f"🔬  Subdependencia: {h_sub or '—'}")
            print(f"{'='*70}")

            # Enriquecer JSON con OpenAlex Author IDs antes de ingestar
            nuevos_oa = _enrich_json_with_openalex_ids(json_file, force_local=args.local)
            if nuevos_oa:
                print(f"   🔍 {nuevos_oa} OpenAlex Author ID(s) nuevos resueltos y guardados en JSON.")

            # Determinar si el archivo es de SNII o de académicos generales
            is_snii_file = os.path.basename(json_file).startswith('profesores_SNII_')
            process_and_ingest_academics(
                json_file,
                force=args.force,
                force_local=args.local,
                target_name=args.name,
                is_snii=is_snii_file,           # True solo para archivos profesores_SNII_*
                limit_acads=args.limit_acads,
                override_entity=h_sub or h_dep,
                institution_name=h_inst,
                dependency_name=h_dep,
                subdependency_name=h_sub,
                save_to_ch=args.ch,
                source_override=args.source,
            )

    except KeyboardInterrupt:
        print("\n🛑 Proceso interrumpido por el usuario.")
    finally:
        print("\n🎉 Ingesta UNAM completada.")
        graph_store.close()


if __name__ == "__main__":
    main()
