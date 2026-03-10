# ingestion/load_orcid_dump.py
import subprocess
import tarfile
import xml.etree.ElementTree as ET
import clickhouse_connect
import os
import io

# Configuración ClickHouse (Ajustar si el servidor tiene credenciales distintas)
CH_HOST = "localhost" # Asumiendo que corre en el mismo servidor o es accesible localmente
CH_USER = "admin"
CH_PASS = "admin"
CH_DB   = "openalex"

# Ruta al dump en el servidor
ZIP_PATH = "/mnt/expansion/30375589_orcid2025.zip"
TARGET_TAR = "ORCID_2025_10_summaries.tar.gz"

def get_client():
    return clickhouse_connect.get_client(host=CH_HOST, username=CH_USER, password=CH_PASS, database=CH_DB)

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
        activities = root.find('.//activities:activities-summary', ns)
        if activities is not None:
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

        return [orcid_id, given_names, family_name, credit_name, emails, last_aff, last_city, last_country, "orcid_dump_2025"]
    except Exception as e:
        return None

def run_ingestion(batch_size=5000):
    client = get_client()
    cols = ['orcid', 'given_names', 'family_name', 'credit_name', 'emails', 
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
