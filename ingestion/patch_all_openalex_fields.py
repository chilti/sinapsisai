"""
patch_all_openalex_fields.py
────────────────────────────
Rellena los nuevos campos de OpenAlex en los nodos :Paper de Neo4j que ya
fueron ingestados con la versión anterior del pipeline (antes de la expansión
de campos de marzo 2026).

Campos que añade / actualiza en raw_metadata:
  - counts_by_year, referenced_works_count, referenced_works
  - apc_paid_usd, apc_list_usd
  - author_count, countries_distinct_count, institutions_distinct_count
  - countries, coauthor_institutions
  - license, any_repository_has_fulltext, oa_url, locations_count
  - indexed_in, is_retracted, language, type
  - journal_is_oa, journal_is_in_doaj, journal_is_core, issn, journal_type
  - primary_topic_name/domain/field/subfield/score
  - keywords (top-15), sustainable_development_goals
  - OpenAlex_Topics (con score)

Uso:
    python ingestion/patch_all_openalex_fields.py
    python ingestion/patch_all_openalex_fields.py --entity "Instituto de Ciencias Nucleares"
    python ingestion/patch_all_openalex_fields.py --dry-run
    python ingestion/patch_all_openalex_fields.py --skip-existing
"""

import sys
import os
import json
import time
import argparse
import ast

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore
import pyalex
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
pyalex.config.email = os.getenv("EMAIL_ADDRESS", "sin_correo@ciencias.unam.mx")
if os.getenv("OPENALEX_API_KEY"):
    pyalex.config.api_key = os.getenv("OPENALEX_API_KEY")

# ─── Extracción de campos desde un work de OpenAlex ────────────────────────

def extract_new_fields(work: dict) -> dict:
    """Devuelve un dict con todos los campos nuevos a parchear en raw_metadata."""
    cyp    = work.get('cited_by_percentile_year') or {}
    _auths = work.get('authorships', [])
    _loc   = work.get('primary_location') or {}
    _src   = _loc.get('source') or {}
    pt     = work.get('primary_topic') or {}
    oa     = work.get('open_access') or {}

    topics = []
    for t in work.get('topics', []):
        try:
            topics.append({
                'domain':   (t.get('domain') or {}).get('display_name'),
                'field':    (t.get('field') or {}).get('display_name'),
                'subfield': (t.get('subfield') or {}).get('display_name'),
                'topic':    t.get('display_name'),
                'score':    t.get('score'),
            })
        except Exception:
            pass

    coauthor_institutions = [
        {
            'author':   (a.get('author') or {}).get('display_name'),
            'orcid':    (a.get('author') or {}).get('orcid'),
            'position': a.get('author_position'),
            'is_corresponding': a.get('is_corresponding', False),
            'countries': a.get('countries', []),
            'institutions': [
                {'name': i.get('display_name'), 'ror': i.get('ror'),
                 'country': i.get('country_code'), 'type': i.get('type')}
                for i in a.get('institutions', [])
            ]
        }
        for a in _auths
    ]

    sdgs = [
        {'id': s.get('id', '').rstrip('/').split('/')[-1],
         'display_name': s.get('display_name'),
         'score': s.get('score')}
        for s in work.get('sustainable_development_goals', [])
    ]

    return {
        # Impacto
        'fwci':                         work.get('fwci'),
        'open_access':                  oa,
        'citation_normalized_percentile': (work.get('citation_normalized_percentile') or {}).get('value'),
        'is_in_top_1_percent':          (work.get('citation_normalized_percentile') or {}).get('is_in_top_1_percent', False),
        'is_in_top_10_percent':         (work.get('citation_normalized_percentile') or {}).get('is_in_top_10_percent', False),
        'cited_by_percentile_year_min': cyp.get('min'),
        'cited_by_percentile_year_max': cyp.get('max'),
        # Trayectoria
        'counts_by_year':         work.get('counts_by_year', []),
        'referenced_works_count': work.get('referenced_works_count', 0),
        'referenced_works':       work.get('referenced_works', []),
        # APC
        'apc_paid_usd': (work.get('apc_paid') or {}).get('value_usd', 0) or 0,
        'apc_list_usd': (work.get('apc_list') or {}).get('value_usd', 0) or 0,
        # Colaboración
        'author_count':               len(_auths),
        'countries_distinct_count':   work.get('countries_distinct_count', 0),
        'institutions_distinct_count': work.get('institutions_distinct_count', 0),
        'countries':                  list({c for a in _auths for c in a.get('countries', [])}),
        'coauthor_institutions':      coauthor_institutions,
        # OA avanzado
        'license':                    _loc.get('license'),
        'any_repository_has_fulltext': oa.get('any_repository_has_fulltext', False),
        'oa_url':                     oa.get('oa_url'),
        'locations_count':            work.get('locations_count', 0),
        # Indexación
        'indexed_in':   work.get('indexed_in', []),
        'is_retracted': work.get('is_retracted', False),
        'language':     work.get('language', 'en'),
        'type':         work.get('type', 'article'),
        # Revista
        'journal_is_oa':      _src.get('is_oa', False),
        'journal_is_in_doaj': _src.get('is_in_doaj', False),
        'journal_is_core':    _src.get('is_core', False),
        'issn':               _src.get('issn_l'),
        'journal_type':       _src.get('type'),
        # Tópico primario
        'primary_topic_name':     pt.get('display_name'),
        'primary_topic_score':    pt.get('score'),
        'primary_topic_field':    (pt.get('field') or {}).get('display_name'),
        'primary_topic_subfield': (pt.get('subfield') or {}).get('display_name'),
        'primary_topic_domain':   (pt.get('domain') or {}).get('display_name'),
        # Topics + keywords + SDGs
        'OpenAlex_Topics': topics,
        'keywords':        [k.get('display_name') for k in work.get('keywords', [])[:15]],
        'sustainable_development_goals': sdgs,
    }


def _parse_raw_meta(raw_meta_json):
    """Deserializa raw_metadata de Neo4j (puede ser dict, JSON string, o repr Python)."""
    if isinstance(raw_meta_json, dict):
        return raw_meta_json
    if isinstance(raw_meta_json, str):
        try:
            return json.loads(raw_meta_json)
        except json.JSONDecodeError:
            # fallback: repr de Python con comillas simples
            return ast.literal_eval(raw_meta_json)
    return {}


# ─── Script principal ───────────────────────────────────────────────────────

def patch_all_fields(entity_filter: str = None, dry_run: bool = False, skip_existing: bool = False):
    graph_store = Neo4jGraphStore()

    print("📋 Mapeando papers desde Neo4j...")
    papers = []
    with graph_store.driver.session() as session:
        if entity_filter:
            query = """
            MATCH (e:Entity {name: $entity})-[:HAS_PAPER]->(p:Paper)
            WHERE p.raw_metadata IS NOT NULL
            RETURN p.id AS doi, p.raw_metadata AS meta
            UNION
            MATCH (e:Entity {name: $entity})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p:Paper)
            WHERE p.raw_metadata IS NOT NULL
            RETURN p.id AS doi, p.raw_metadata AS meta
            """
            result = session.run(query, entity=entity_filter)
        else:
            result = session.run(
                "MATCH (p:Paper) WHERE p.raw_metadata IS NOT NULL "
                "RETURN p.id AS doi, p.raw_metadata AS meta"
            )
        seen_dois = set()
        for row in result:
            if row['doi'] not in seen_dois:
                papers.append((row['doi'], row['meta']))
                seen_dois.add(row['doi'])

    # Filtrar DOIs válidos para OpenAlex
    valid = [(doi, meta) for doi, meta in papers
             if doi and doi.startswith("10.") and not doi.startswith("urn:")]

    if skip_existing:
        def _needs_patch(meta_json):
            try:
                m = _parse_raw_meta(meta_json)
                return 'author_count' not in m or 'counts_by_year' not in m
            except Exception:
                return True
        valid = [(doi, meta) for doi, meta in valid if _needs_patch(meta)]
        print(f"  → {len(valid)} papers necesitan parche (--skip-existing activo).")
    else:
        print(f"  → {len(valid)} DOIs válidos encontrados.")

    if dry_run:
        print(f"🔍 DRY-RUN: se parchearían {len(valid)} papers. Sin cambios en la BD.")
        graph_store.close()
        return

    batch_size = 20
    updated = 0
    skipped = 0
    errors  = 0
    first_skip_printed = False
    total   = len(valid)

    for i in range(0, total, batch_size):
        batch = valid[i:i + batch_size]
        clean_dois = [d[0].replace("https://doi.org/", "").strip().lower() for d in batch]

        # Fetch individual por DOI (lookup directo, más confiable que .filter() con listas)
        oa_data = {}
        for d in clean_dois:
            url = f"https://doi.org/{d}"
            try:
                work = pyalex.Works()[url]
                if work and work.get('doi'):
                    oa_data[d] = work
            except Exception:
                pass
            time.sleep(0.08)  # ~12 req/s respeta rate limit pública de OpenAlex

        if not oa_data and not first_skip_printed:
            print(f"\n  ⚠️  Primer lote sin resultados de OpenAlex. DOI de prueba: {clean_dois[0]!r}", flush=True)
            first_skip_printed = True

        # Parchar en Neo4j
        with graph_store.driver.session() as session:
            for doi_full, raw_meta_json in batch:
                clean = doi_full.replace("https://doi.org/", "").strip().lower()
                if clean not in oa_data:
                    skipped += 1
                    continue
                try:
                    meta = _parse_raw_meta(raw_meta_json)
                    new_fields = extract_new_fields(oa_data[clean])
                    meta.update(new_fields)
                    session.run(
                        "MATCH (p:Paper {id: $id}) SET p.raw_metadata = $meta",
                        id=doi_full, meta=json.dumps(meta, ensure_ascii=False)
                    )
                    updated += 1
                except Exception as e:
                    print(f"\n  ❌ Error en {doi_full}: {e}", flush=True)
                    errors += 1

        pct = int((i + len(batch)) / total * 100)
        print(f"  [{pct:3d}%] actualizados={updated}  omitidos={skipped}  errores={errors}",
              end="\r", flush=True)

    print(f"\n\n✅ Parche completado.")
    print(f"   Actualizados : {updated}")
    print(f"   Sin datos OA : {skipped}")
    print(f"   Errores      : {errors}")
    graph_store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parche de campos OpenAlex faltantes en papers existentes."
    )
    parser.add_argument(
        "--entity", type=str, default=None,
        help="Filtrar por nombre de entidad (ej. 'Instituto de Ciencias Nucleares')"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Muestra cuántos se parchearían sin modificar la BD"
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Solo parchear papers que no tienen author_count o counts_by_year"
    )
    args = parser.parse_args()

    patch_all_fields(
        entity_filter=args.entity,
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
    )
