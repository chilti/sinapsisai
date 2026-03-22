# ingestion/load_orcid_dump.py
import subprocess
import tarfile
import xml.etree.ElementTree as ET
import clickhouse_connect
import os
import io

from dotenv import load_dotenv
load_dotenv()

# Configuración ClickHouse (Ajustar si el servidor tiene credenciales distintas)
CH_HOST = os.getenv("CH_ORCID_HOST", "127.0.0.1")
CH_PORT = int(os.getenv("CH_ORCID_PORT", 8123))
CH_USER = os.getenv("CH_ORCID_USER", "admin")
CH_PASS = os.getenv("CH_ORCID_PASSWORD", "admin")
CH_DB   = os.getenv("CH_ORCID_DATABASE", "orcid")

# Ruta al dump en el servidor
ZIP_PATH = "/mnt/expansion/30375589_orcid2025.zip"
TARGET_TAR = "ORCID_2025_10_summaries.tar.gz"

def get_client():
    client = clickhouse_connect.get_client(
        host=CH_HOST, 
        port=CH_PORT, 
        username=CH_USER, 
        password=CH_PASS, 
        database=CH_DB
    )
    
    # Asegurar que la tabla existe antes de empezar
    try:
        with open('database/setup_orcid_db.sql', 'r', encoding='utf-8') as f:
            sql = f.read()
        for command in sql.split(';'):
            lines = [line for line in command.splitlines() if not line.strip().startswith('--')]
            cleaned = " ".join(lines).strip()
            if cleaned:
                client.command(cleaned)
    except Exception as e:
        print(f"Advertencia al preparar la tabla: {e}")
        
    return client

def parse_orcid_xml(xml_content):
    """Parsea lo básico de un XML de ORCID v3.0"""
    try:
        root = ET.fromstring(xml_content)
        ns = {
            'common': 'http://www.orcid.org/ns/common',
            'person': 'http://www.orcid.org/ns/person',
            'activities': 'http://www.orcid.org/ns/activities',
            'personal-details': 'http://www.orcid.org/ns/personal-details'
        }
        
        orcid_id = root.find('.//common:path', ns).text if root.find('.//common:path', ns) is not None else ""
        
        person = root.find('.//person:person', ns)
        given_names, family_name, credit_name = "", "", ""
        if person is not None:
            name_elem = person.find('person:name', ns)
            if name_elem is not None:
                gn = name_elem.find('personal-details:given-names', ns)
                fn = name_elem.find('personal-details:family-name', ns)
                cn = name_elem.find('personal-details:credit-name', ns)
                given_names = gn.text if gn is not None else ""
                family_name = fn.text if fn is not None else ""
                credit_name = cn.text if cn is not None else ""

        emails = [e.text for e in root.findall('.//person:email', ns) if e.text]
        
        last_aff, last_city, last_country = "", "", ""
        dois = []
        scopus_ids = []
        activities = root.find('.//activities:activities-summary', ns)
        if activities is not None:
            # 1. Empleos para Affiliation
            employments = activities.find('activities:employments', ns)
            if employments is not None:
                emp_summaries = employments.findall('.//common:organization', ns)
                if emp_summaries:
                    org = emp_summaries[0]
                    name_elem = org.find('common:name', ns)
                    last_aff = name_elem.text if name_elem is not None else ""
                    address = org.find('common:address', ns)
                    if address is not None:
                        city_elem = address.find('common:city', ns)
                        country_elem = address.find('common:country', ns)
                        last_city = city_elem.text if city_elem is not None else ""
                        last_country = country_elem.text if country_elem is not None else ""
            
            # 2. Artículos (DOIs)
            works = activities.find('activities:works', ns)
            if works is not None:
                for work in works.findall('.//activities:work-summary', ns):
                    ext_ids = work.find('common:external-ids', ns)
                    if ext_ids is not None:
                        for ext_id in ext_ids.findall('common:external-id', ns):
                            id_type = ext_id.find('common:external-id-type', ns)
                            if id_type is not None and id_type.text.lower() == 'doi':
                                val = ext_id.find('common:external-id-value', ns)
                                if val is not None and val.text:
                                    dois.append(val.text.lower().strip())
                            elif id_type is not None and id_type.text.lower() == 'scopus':
                                val = ext_id.find('common:external-id-value', ns)
                                if val is not None and val.text:
                                    scopus_ids.append(val.text.strip())

        return [orcid_id, given_names, family_name, credit_name, emails, dois, scopus_ids, last_aff, last_city, last_country, "orcid_dump_2025"]
    except Exception as e:
        return None

def run_ingestion(batch_size=5000):
    client = get_client()
    cols = ['orcid', 'given_names', 'family_name', 'credit_name', 'emails', 'dois', 'scopus_ids',
            'last_affiliation', 'last_affiliation_city', 'last_affiliation_country', 'source_id']
    
    print(f"Iniciando ingesta desde {ZIP_PATH} -> {TARGET_TAR}...")
    
    # Usamos pipe para no descomprimir 46GB en disco
    cmd = f"unzip -p {ZIP_PATH} {TARGET_TAR} | gunzip -c"
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, bufsize=1024*1024)
    
    batch = []
    total = 0
    
    try:
        # tarfile puede leer de un stream
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:
                if member.isfile() and member.name.endswith(".xml"):
                    f = tar.extractfile(member)
                    if f:
                        content = f.read()
                        record = parse_orcid_xml(content)
                        if record:
                            batch.append(record)
                            total += 1
                        
                        if len(batch) >= batch_size:
                            client.insert('orcid_records', batch, column_names=cols)
                            print(f"Insertados {total} registros...")
                            batch = []
                            
            # Insertar remanente
            if batch:
                client.insert('orcid_records', batch, column_names=cols)
                print(f"Ingesta finalizada. Total: {total}")
                
    except Exception as e:
        print(f"Error durante la ingesta: {e}")
    finally:
        proc.terminate()

if __name__ == "__main__":
    run_ingestion()
