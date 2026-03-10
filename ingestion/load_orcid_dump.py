"""
load_orcid_dump.py
──────────────────
Script para ingerir el ORCID Public Data Dump (>200GB) en ClickHouse.
Utiliza iterparse de lxml para procesamiento eficiente en memoria.
"""

import os
import lxml.etree as ET
import clickhouse_connect
import argparse
import time
from datetime import datetime

# Namespaces de ORCID XML
NS = {
    'record': 'http://www.orcid.org/ns/record',
    'person': 'http://www.orcid.org/ns/person',
    'personal-details': 'http://www.orcid.org/ns/personal-details',
    'activities': 'http://www.orcid.org/ns/activities',
    'common': 'http://www.orcid.org/ns/common',
    'history': 'http://www.orcid.org/ns/history',
    'employment': 'http://www.orcid.org/ns/employment'
}

def parse_record(file_path):
    """Parsea un archivo XML de ORCID individual o un stream."""
    try:
        context = ET.iterparse(file_path, events=('end',), tag='{http://www.orcid.org/ns/record}record')
        for event, elem in context:
            record_data = {}
            
            # ORCID ID
            orcid_path = elem.xpath('.//common:orcid-identifier/common:path', namespaces=NS)
            record_data['orcid_id'] = orcid_path[0].text if orcid_path else None
            
            # Personal Details
            person = elem.find('record:person', NS)
            if person is not None:
                details = person.find('person:personal-details', NS)
                if details is not None:
                    gn = details.find('personal-details:given-names', NS)
                    fn = details.find('personal-details:family-name', NS)
                    cn = details.find('personal-details:credit-name', NS)
                    
                    record_data['given_names'] = gn.text if gn is not None else ""
                    record_data['family_names'] = fn.text if fn is not None else ""
                    record_data['credit_name'] = cn.text if cn is not None else ""
            
            # Afiliación (Emplois mas recientes)
            # Simplificado: Tomamos el primer empleo que aparezca
            activities = elem.find('record:activities-summary', NS)
            record_data['last_institution'] = ""
            if activities is not None:
                employments = activities.find('activities:employments', NS)
                if employments is not None:
                    # En el dump summary suele haber una lista de afiliaciones
                    aff = employments.find('.//employment:organization', NS)
                    if aff is not None:
                        name = aff.find('common:name', NS)
                        record_data['last_institution'] = name.text if name is not None else ""
            
            # Limpiar memoria
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]
                
            if record_data['orcid_id']:
                yield record_data
    except Exception as e:
        print(f"Error parseando {file_path}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Ingesta dump de ORCID en ClickHouse.")
    parser.add_argument("path", help="Ruta al directorio de XMLs de ORCID")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--batch", type=int, default=5000)
    args = parser.parse_args()

    client = clickhouse_connect.get_client(host=args.host, username='default', password='')
    
    batch = []
    total = 0
    start_time = time.time()

    print(f"🚀 Iniciando ingesta desde {args.path}...")
    
    # El dump de ORCID suele estar dividido en carpetas por los ultimos 3 digitos del ORCID
    for root, dirs, files in os.walk(args.path):
        for file in files:
            if file.endswith(".xml"):
                full_path = os.path.join(root, file)
                for record in parse_record(full_path):
                    batch.append(record)
                    
                    if len(batch) >= args.batch:
                        client.insert('orcid.records', batch, column_names=list(batch[0].keys()))
                        total += len(batch)
                        batch = []
                        elapsed = time.time() - start_time
                        print(f"  → Ingestados: {total:,} | Velocidad: {total/elapsed:.0f} rec/s", end="\r")

    if batch:
        client.insert('orcid.records', batch, column_names=list(batch[0].keys()))
        total += len(batch)

    print(f"\n✅ Ingesta finalizada. Total: {total:,} registros en {time.time()-start_time:.1f}s")

if __name__ == "__main__":
    main()
