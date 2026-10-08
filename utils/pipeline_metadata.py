"""
utils/pipeline_metadata.py - Generador de Metadatos de Pipeline y Snapshot para Info TlachIA SNII
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

def save_pipeline_metadata(base_dir=None):
    """
    Genera y guarda metadatos de la corrida del pipeline y snapshot utilizado
    en data/pipeline_metadata.json.
    """
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent
    else:
        base_dir = Path(base_dir)

    if str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))

    data_dir = base_dir / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)

    snapshot_date = "2026-09-23"
    total_works = 1652927
    total_authors = 2241792
    total_entities = 1218109

    try:
        from database.clickhouse_db import ch_client
        res = ch_client.query("SELECT max(updated_date) FROM works").result_rows
        if res and res[0][0]:
            val = str(res[0][0])
            snapshot_date = val.split('T')[0]
    except Exception as e:
        print(f"⚠️ [pipeline_metadata] Advertencia al consultar snapshot de ClickHouse: {e}")

    try:
        from database.clickhouse_db import ch_client
        def _get_count(table):
            try:
                return int(ch_client.query(f"SELECT count() FROM {table}").result_rows[0][0])
            except Exception:
                return None

        w_cnt = _get_count("works_academic_all")
        if w_cnt is not None: total_works = w_cnt
        a_cnt = _get_count("paper_author_map")
        if a_cnt is not None: total_authors = a_cnt
        e_cnt = _get_count("paper_entity_map")
        if e_cnt is not None: total_entities = e_cnt
    except Exception as e:
        print(f"⚠️ [pipeline_metadata] Advertencia al consultar conteos de ClickHouse: {e}")

    # Conteos SNII y ROR
    snii_total = 82334
    snii_with_orcid = 33677
    snii_with_oa = 34323
    institutions_total = 2263

    mapping_path = data_dir / "snii_ror_verified_matches_v2.json"
    if mapping_path.exists():
        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                mapping = json.load(f)
            inst_count = len(mapping)
            if inst_count > 0:
                institutions_total = inst_count
        except Exception:
            pass

    metadata = {
        "last_updated": datetime.now().isoformat(timespec="seconds"),
        "snapshot_date": snapshot_date,
        "openalex_release": f"OpenAlex Snapshot {snapshot_date}",
        "total_works": total_works,
        "total_author_links": total_authors,
        "total_entity_links": total_entities,
        "snii_total": snii_total,
        "snii_with_orcid": snii_with_orcid,
        "snii_with_oa": snii_with_oa,
        "institutions_total": institutions_total,
        "pipeline_version": "2.0.0",
        "database_engine": "ClickHouse + Neo4j + Qdrant"
    }

    out_file = data_dir / 'pipeline_metadata.json'
    try:
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"✅ [pipeline_metadata] Metadatos guardados en: {out_file}")
        print(f"   Última actualización: {metadata['last_updated']}")
        print(f"   Snapshot OpenAlex:    {metadata['openalex_release']}")
        print(f"   Obras indizadas:      {metadata['total_works']:,}")
    except Exception as e:
        print(f"❌ [pipeline_metadata] Error guardando metadatos: {e}")

    return metadata

if __name__ == '__main__':
    save_pipeline_metadata()
