"""
materialize_works_academic.py
==============================
Sincroniza works_academic_all desde works_flat usando paper_author_map como
índice de qué papers incluir.

Flujo:
  1. Obtiene los IDs de works_flat que matchean por DOI normalizado contra paper_author_map
  2. Inserta esos papers en works_academic_all (dedupando por id)
  - Columnas presentes en works_flat → se copian directamente
  - Columnas exclusivas de works_academic_all (author_names, institution_rors, etc.)
    → se dejan vacías (pueden enriquecerse después con patch_openalex_metadata.py)

Uso:
  python ingestion/materialize_works_academic.py
  python ingestion/materialize_works_academic.py --dry-run    # solo cuenta, no inserta
  python ingestion/materialize_works_academic.py --truncate   # vacía la tabla primero
"""

import os, sys, argparse
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env')))
from database.clickhouse_db import ch_client

_Q_COUNT = """
SELECT count() AS n
FROM works_flat wf
JOIN (
    SELECT paper_id FROM paper_author_map
    UNION DISTINCT
    SELECT paper_id FROM paper_entity_map
) pm ON (
    lower(replaceOne(wf.doi, 'https://doi.org/', '')) = lower(pm.paper_id)
    OR
    wf.id = 'https://openalex.org/' || pm.paper_id
    OR
    wf.id = pm.paper_id
)
WHERE wf.id NOT IN (SELECT id FROM works_academic_all)
"""

# Mapeo: columna en works_academic_all → expresión SQL desde works_flat
# works_flat cols: id, doi, title, abstract, publication_year, publication_date, type,
#   language, cited_by_count, fwci, percentile, is_top_10, is_top_1,
#   referenced_works_count, source_id, source_type, is_oa, oa_status,
#   topic_id, subfield_id, subfield_name, field_name, domain_name,
#   author_ids, institution_ids, institution_types, country_codes, referenced_works,
#   concepts, pmid, mag_id, is_retracted, is_paratext, volume, issue,
#   first_page, last_page, all_topics, keywords, mesh, funder_ids, funder_names, sdgs
_COL_MAP = {
    'id':                          'wf.id',
    'raw_data':                    'wf.raw_data',
    'doi':                         'wf.doi',
    'title':                       'wf.title',
    'publication_year':            'wf.publication_year',
    'cited_by_count':              'wf.cited_by_count',
    'is_oa':                       'wf.is_oa',
    'type':                        'wf.type',
    'updated_date':                'wf.updated_date',
    'is_xpac':                     'wf.is_xpac',
    'source_id':                   'wf.source_id',
    'author_names':                'wf.author_names',
    'institution_rors':            'wf.institution_rors',
    'institution_names':           'wf.institution_names',
    'primary_topic_id':            'wf.primary_topic_id',
    'institution_ids':             'wf.institution_ids',
    'subfield':                    'wf.subfield',
    'field':                       'wf.field',
    'domain':                      'wf.domain',
    'topic':                       'wf.topic',
    'language':                    'wf.language',
    'oa_status':                   'wf.oa_status',
    'fwci':                        'wf.fwci',
    'percentile':                  'wf.percentile',
    'is_top_10':                   'wf.is_top_10',
    'is_top_1':                    'wf.is_top_1',
    'country_code':                'wf.country_code',
    'source_type':                 'wf.source_type',
    'sdg_ids':                     'wf.sdg_ids',
    'awards':                      'wf.awards',
    'concept_ids':                 'wf.concept_ids',
    'all_country_codes':           'wf.all_country_codes',
    'apc_paid_usd':                'wf.apc_paid_usd',
    'apc_list_usd':                'wf.apc_list_usd',
    'counts_by_year':              'wf.counts_by_year',
    'is_doaj_indexed':             'wf.is_doaj_indexed',
    'is_doaj_journal':             'wf.is_doaj_journal',
    'is_core_journal':             'wf.is_core_journal',
    'is_retracted':                'wf.is_retracted',
    'has_repository_fulltext':     'wf.has_repository_fulltext',
    'license':                     'wf.license',
    'referenced_works_count':      'wf.referenced_works_count',
    'keywords':                    'wf.keywords',
    'sdgs':                        'wf.sdgs',
    'journal_is_in_doaj':          'wf.journal_is_in_doaj',
    'journal_is_core':             'wf.journal_is_core',
    'any_repository_has_fulltext': 'wf.any_repository_has_fulltext',
    'embedding_nomic':             "'[]'",
    'embedding_specter':           "'[]'",
    'embedding_fastrp':            "'[]'",
}


def main(dry_run=False, truncate=False):
    ch = ch_client.get_client()

    r = ch_client.query_df('SELECT count() AS n FROM works_academic_all')
    current = int(r['n'].iloc[0])
    print(f"works_academic_all actual : {current:,} papers")

    r2 = ch_client.query_df("SELECT count() AS n FROM paper_author_map WHERE paper_id LIKE '10.%'")
    print(f"paper_author_map DOIs     : {int(r2['n'].iloc[0]):,}")

    if truncate:
        print("\n⚠️  Truncando works_academic_all...")
        ch.command('TRUNCATE TABLE works_academic_all')
        print("  → Tabla vaciada.")
        current = 0

    print("\n⏳ Contando papers nuevos en works_flat que matchean paper_author_map + paper_entity_map...")
    r3 = ch_client.query_df(_Q_COUNT)
    to_insert = int(r3['n'].iloc[0])
    print(f"  → Nuevos a materializar : {to_insert:,}")

    if dry_run:
        print("\n[dry-run] No se insertó nada.")
        return

    if to_insert == 0:
        print("✅ works_academic_all ya está sincronizado.")
        return

    # Construir INSERT usando _COL_MAP, en el orden exacto del esquema
    schema = ch_client.query_df('DESCRIBE works_academic_all')
    col_names = schema['name'].tolist()

    select_parts = []
    insert_cols  = []
    for col in col_names:
        expr = _COL_MAP.get(col)
        if expr is None:
            print(f"  ⚠️  Columna '{col}' sin mapeo — usando default ''")
            expr = "''"
        insert_cols.append(col)
        # Alias con nombre original para columnas directas con distinto nombre
        if expr.startswith('wf.') and expr[3:] != col:
            select_parts.append(f"{expr} AS {col}")
        elif not expr.startswith('wf.'):
            select_parts.append(f"{expr} AS {col}")
        else:
            select_parts.append(expr)

    # Construir partes de SELECT y GROUP BY (wf.id deduplica works_flat)
    group_cols  = ['wf.id']
    select_agg  = []
    for i, (col, expr) in enumerate(zip(insert_cols, select_parts)):
        if col == 'id':
            select_agg.append(expr)        # clave de agrupación
        else:
            # Para el resto usamos any() para tomar un valor arbitrario por id
            alias = f" AS {col}" if (f"AS {col}" not in expr) else ""
            select_agg.append(f"any({expr}){alias}")

    q_insert = f"""
INSERT INTO works_academic_all
({', '.join(insert_cols)})
SELECT
    {',\n    '.join(select_agg)}
FROM works_flat wf
JOIN (
    SELECT paper_id FROM paper_author_map
    UNION DISTINCT
    SELECT paper_id FROM paper_entity_map
) pm ON (
    lower(replaceOne(wf.doi, 'https://doi.org/', '')) = lower(pm.paper_id)
    OR
    wf.id = 'https://openalex.org/' || pm.paper_id
    OR
    wf.id = pm.paper_id
)
WHERE wf.id NOT IN (SELECT id FROM works_academic_all)
GROUP BY wf.id
"""

    print(f"\n⏳ Insertando {to_insert:,} papers en works_academic_all...")
    try:
        ch.command(q_insert)
    except Exception as e:
        print(f"  ❌ Error en INSERT masivo: {e}")
        print("  ℹ️  Revisa el esquema y el mapeo _COL_MAP en el script.")
        return

    r_final = ch_client.query_df('SELECT count() AS n FROM works_academic_all')
    final = int(r_final['n'].iloc[0])
    print(f"✅ Completado. works_academic_all: {current:,} → {final:,} (+{final - current:,})")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Materializa works_academic_all desde works_flat')
    parser.add_argument('--dry-run',  action='store_true', help='Solo cuenta, no inserta')
    parser.add_argument('--truncate', action='store_true', help='Vacía la tabla antes de insertar')
    args = parser.parse_args()
    main(dry_run=args.dry_run, truncate=args.truncate)
