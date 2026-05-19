import os
import sys
import json
import time
import pandas as pd
from pathlib import Path
from tqdm import tqdm
import pyalex

# Añadir path raíz
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))

from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client
from ROR.ingest_ror_docs import deconstruct_abstract, RORIngestor

# Cargar variables de entorno
from dotenv import load_dotenv
load_dotenv(_THIS.parent / '.env')

class RORIngestorV2(RORIngestor):
    """
    Ingestor de documentos ROR adaptado a la estructura jerárquica del JSON v2.
    """

    def run_v2(self, limit=None, local_only=False):
        input_path = os.path.join("data", "snii_ror_verified_matches_v2.json")
        if not os.path.exists(input_path):
            print(f"❌ No existe el archivo {input_path}")
            return

        with open(input_path, "r", encoding="utf-8") as f:
            verified_results = json.load(f)

        print(f"🚀 Iniciando ingesta jerárquica desde {input_path}...")
        
        inst_count = 0
        for inst_root_name, data in verified_results.items():
            if limit and inst_count >= limit: break
            
            root_info = data.get('root_info', {})
            root_id = root_info.get('root_openalex_id')
            if not root_id: continue
            
            print(f"\n🏛️ Procesando Institución Raíz: {inst_root_name}")
            
            # 1. Procesar la raíz misma
            root_unit = {
                'inst': inst_root_name,
                'dep': "SIN INFORMACIÓN",
                'sub': "SIN INFORMACIÓN",
                'id': root_id
            }
            self._ingest_unit(root_unit, local_only=local_only)
            
            # 2. Procesar cada unidad (Dependencia/Subdependencia)
            units = data.get('units', {})
            for unit_key, unit_info in units.items():
                dep, sub = unit_key.split(" || ")
                match_id = unit_info.get('matched_openalex_id')
                if match_id:
                    unit_data = {
                        'inst': inst_root_name,
                        'dep': dep,
                        'sub': sub,
                        'id': match_id
                    }
                    self._ingest_unit(unit_data, local_only=local_only)
                else:
                    print(f"  ⚠️ Saltando {dep} | {sub} (Sin OpenAlex ID específico)")
            
            inst_count += 1

    def _ingest_unit(self, unit, local_only=False):
        """Ingesta papers para una unidad específica (Raíz, Dep o Sub).
        Si local_only=True usa la API local (sin límite de paginación);
        si no, usa pyalex oficial con límite de 100 papers.
        """
        print(f"  📄 Ingeriendo: {unit['dep']} | {unit['sub']} (ID: {unit['id']})")

        entities = [{
            'inst': unit['inst'],
            'dep': unit['dep'],
            'sub': unit['sub']
        }]

        try:
            inst_id_clean = unit['id'].split('/')[-1]
            processed_count = 0

            if local_only:
                from database.clickhouse_db import ch_client
                ch = ch_client.get_client()
                full_id = unit['id'] if unit['id'].startswith('https://') else f"https://openalex.org/{inst_id_clean}"
                offset, per_page = 0, 200
                print(f"    🗄️  Usando ClickHouse (works_flat) para {full_id}")
                while True:
                    rows = ch.query(
                        '''SELECT id, doi, title, publication_year, type,
                                  cited_by_count, raw_data
                           FROM works_flat FINAL
                           WHERE has(institution_ids, {id:String})
                           ORDER BY id
                           LIMIT {limit:UInt32} OFFSET {offset:UInt32}''',
                        parameters={'id': full_id, 'limit': per_page, 'offset': offset}
                    ).result_rows
                    if not rows:
                        break
                    import json as _json
                    works_page = []
                    for oa_id, doi, title, year, wtype, cites, raw in rows:
                        try:
                            w = _json.loads(raw) if raw else {}
                        except Exception:
                            w = {}
                        w.setdefault('id', oa_id)
                        w.setdefault('doi', doi)
                        w.setdefault('display_name', title)
                        w.setdefault('publication_year', year)
                        w.setdefault('type', wtype)
                        w.setdefault('cited_by_count', cites)
                        works_page.append(w)
                    print(f"   📂 Procesando bloque de {len(works_page)} trabajos para [{unit['inst']}]...")
                    self._process_works_batch(works_page, entities)
                    processed_count += len(works_page)
                    if len(rows) < per_page:
                        break
                    offset += per_page
            else:
                import pyalex
                query = pyalex.Works().filter(
                    institutions={"id": inst_id_clean}
                ).select([
                    "id", "display_name", "doi", "publication_year", "type",
                    "cited_by_count", "authorships", "concepts",
                    "abstract_inverted_index", "primary_topic"
                ])
                for page in query.paginate(per_page=50, n_max=100):
                    print(f"   📂 Procesando bloque de {len(page)} trabajos para [{unit['inst']}]...")
                    self._process_works_batch(page, entities)
                    processed_count += len(page)

            print(f"    ✅ Finalizado: {processed_count} trabajos procesados.")

        except Exception as e:
            print(f"    ❌ Error ingiriendo unidad {unit['id']}: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingesta jerárquica de documentos ROR.")
    parser.add_argument("--limit", type=int, help="Límite de instituciones raíz a procesar")
    parser.add_argument("--local", action="store_true",
                        help="Usar API local de OpenAlex (OPENALEX_LOCAL_API) sin límite de paginación")
    args = parser.parse_args()

    ingestor = RORIngestorV2()
    try:
        ingestor.run_v2(limit=args.limit, local_only=args.local)
    finally:
        ingestor.graph_store.close()
