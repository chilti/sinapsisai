# load_orcid_sample.py
import zipfile
import xml.etree.ElementTree as ET
import json
import os
import clickhouse_connect

# Configuración ClickHouse
CH_HOST = "127.0.0.1"
CH_USER = "admin"
CH_PASS = "admin"
CH_DB   = "openalex"

# Path al archivo local que bajamos para la prueba
ZIP_PATH    = "data/orcid_summaries_sample.tar.gz" # O los .xml sueltos
# Vamos a modificar load_files para que use los .xml sueltos que bajamos
SEED_PATH   = "data/authors_mexico_seed.json"

def get_client():
    return clickhouse_connect.get_client(host=CH_HOST, username=CH_USER, password=CH_PASS, database=CH_DB)

def parse_orcid_xml(xml_content):
    """Parsea lo básico de un XML de ORCID v3.0"""
    root = ET.fromstring(xml_content)
    # Namespaces reales según 0000-0001-5099-6000.xml
    ns = {
        'common': 'http://www.orcid.org/ns/common',
        'person': 'http://www.orcid.org/ns/person',
        'activities': 'http://www.orcid.org/ns/activities',
        'record': 'http://www.orcid.org/ns/record',
        'personal-details': 'http://www.orcid.org/ns/personal-details',
        'employment': 'http://www.orcid.org/ns/employment'
    }
    
    # ORCID ID
    orcid_id = root.find('.//common:path', ns).text if root.find('.//common:path', ns) is not None else ""
    
    # Names
    person = root.find('.//person:person', ns)
    given_names = ""
    family_name = ""
    credit_name = ""
    if person is not None:
        name_elem = person.find('person:name', ns)
        if name_elem is not None:
            gn = name_elem.find('personal-details:given-names', ns)
            fn = name_elem.find('personal-details:family-name', ns)
            cn = name_elem.find('personal-details:credit-name', ns)
            given_names = gn.text if gn is not None else ""
            family_name = fn.text if fn is not None else ""
            credit_name = cn.text if cn is not None else ""

    # Emails
    emails = [e.text for e in root.findall('.//person:email', ns) if e.text]
    
    # Affiliation (Empleos)
    last_aff = ""
    last_city = ""
    last_country = ""
    
    activities = root.find('.//activities:activities-summary', ns)
    if activities is not None:
        employments = activities.find('activities:employments', ns)
        if employments is not None:
            # En activities-summary no hay lista de employments detallada sino grupos/summaries
            # Vamos a buscar el nombre de la organización en los summaries
            emp_summaries = employments.findall('.//common:organization', ns)
            if emp_summaries:
                # Tomamos la primera (o última) según la lógica
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

def load_files(file_paths):
    client = get_client()
    records = []
    
    for path in file_paths:
        if not os.path.exists(path):
            print(f"File not found: {path}")
            continue
        print(f"Parsing {path}...")
        with open(path, 'rb') as f:
            content = f.read()
            records.append(parse_orcid_xml(content))
            
    if records:
        print(f"Inserting {len(records)} records into ClickHouse...")
        # clickhouse-connect insert format: table, data, column_names
        cols = ['orcid', 'given_names', 'family_name', 'credit_name', 'emails', 
                'last_affiliation', 'last_affiliation_city', 'last_affiliation_country', 'source_id']
        client.insert('orcid_records', records, column_names=cols)
        print("Insert complete.")

if __name__ == "__main__":
    # Test local con los archivos que ya bajamos
    test_files = ["data/0000-0001-5099-6000.xml"]
    load_files(test_files)
