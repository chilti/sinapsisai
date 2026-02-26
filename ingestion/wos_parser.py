import re
from typing import List, Dict, Any

class WoSParser:
    """
    Parsea archivos de texto plano (.txt) exportados desde Web of Science (WoS).
    Extrae todos los campos proporcionados y los estandariza.
    """
    
    WOS_FIELDS_MAP = {
        'FN': 'file_name', 'VR': 'version_number', 'PT': 'publication_type', 
        'AU': 'authors_short', 'AF': 'author_full_name', 'BA': 'book_authors', 
        'BF': 'book_authors_full_name', 'CA': 'group_authors', 'GP': 'book_group_authors', 
        'BE': 'editors', 'TI': 'document_title', 'SO': 'publication_name', 
        'SE': 'book_series_title', 'BS': 'book_series_subtitle', 'LA': 'language', 
        'DT': 'document_type', 'CT': 'conference_title', 'CY': 'conference_date', 
        'CL': 'conference_location', 'SP': 'conference_sponsors', 'HO': 'conference_host', 
        'DE': 'author_keywords', 'ID': 'keywords_plus', 'AB': 'abstract_text', 
        'C1': 'author_address', 'RP': 'reprint_address', 'EM': 'email_address', 
        'RI': 'researcher_id_number', 'OI': 'orcid_identifier', 'FU': 'funding_agency_grant', 
        'FX': 'funding_text', 'CR': 'cited_references', 'NR': 'cited_reference_count', 
        'TC': 'wos_times_cited', 'Z9': 'total_times_cited', 'U1': 'usage_count_180_days', 
        'U2': 'usage_count_since_2013', 'PU': 'publisher', 'PI': 'publisher_city', 
        'PA': 'publisher_address', 'SN': 'issn', 'EI': 'eissn', 'BN': 'isbn', 
        'J9': 'source_abbreviation_29', 'JI': 'iso_source_abbreviation', 'PD': 'publication_date', 
        'PY': 'year_published', 'VL': 'volume', 'IS': 'issue', 'SI': 'special_issue', 
        'PN': 'part_number', 'SU': 'supplement', 'MA': 'meeting_abstract', 'BP': 'beginning_page', 
        'EP': 'ending_page', 'AR': 'article_number', 'DI': 'doi_wos', 'D2': 'book_doi', 
        'PG': 'page_count', 'P2': 'chapter_count', 'WC': 'wos_categories', 'SC': 'research_areas', 
        'GA': 'document_delivery_number', 'UT': 'accession_number', 'PM': 'pubmed_id', 
        'ER': 'end_of_record', 'EF': 'end_of_file'
    }

    
    @staticmethod
    def parse_file(file_path: str) -> List[Dict[str, Any]]:
        records = []
        current_record = {}
        current_tag = None
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.rstrip('\n')
                if not line:
                    continue
                
                # Fin de registro
                if line.startswith('ER'):
                    if current_record:
                        records.append(WoSParser._process_record(current_record))
                    current_record = {}
                    current_tag = None
                    continue
                
                # Inicio de archivo o versión (ignorar)
                if line.startswith('FN') or line.startswith('VR'):
                    continue
                
                # Tag de campo (2 caracteres + espacio)
                if len(line) >= 3 and line[2] == ' ' and line[0:2].isupper():
                    current_tag = line[0:2]
                    value = line[3:].strip()
                    if current_tag in current_record:
                        current_record[current_tag].append(value)
                    else:
                        current_record[current_tag] = [value]
                # Continuación de campo
                elif line.startswith('   ') and current_tag:
                    value = line[3:].strip()
                    current_record[current_tag].append(value)
                    
        return records

    @staticmethod
    def _process_record(raw_record: Dict[str, List[str]]) -> Dict[str, Any]:
        """
        Limpia y estructura un registro crudo de WoS agregando la totalidad de la metadata disponible.
        """
        processed = {
            "paper_id": "".join(raw_record.get('UT', ['unknown'])),
            "title": " ".join(raw_record.get('TI', [])),
            "abstract": " ".join(raw_record.get('AB', [])),
            "year": int(raw_record.get('PY', ['0'])[0]) if raw_record.get('PY') and raw_record.get('PY')[0].isdigit() else 0,
            "doi": "".join(raw_record.get('DI', [])),
            "journal": " ".join(raw_record.get('SO', [])),
            "citations": int(raw_record.get('TC', ['0'])[0]) if raw_record.get('TC') and raw_record.get('TC')[0].isdigit() else 0,
            "authors": [],
            "concepts": [],
            "institutions": [],
            "raw_metadata": {} # Guardamos aquí todos los otros campos mapeados
        }
        
        # Mapea todos los campos brutos usando el diccionario
        for tag, values in raw_record.items():
            field_name = WoSParser.WOS_FIELDS_MAP.get(tag, tag)
            if tag in ['AF', 'AU', 'DE', 'ID', 'C1', 'CR', 'WC', 'SC']:
                # Mantenemos las listas estructuradas
                processed["raw_metadata"][field_name] = values
            else:
                # Combinamos texto multilínea
                processed["raw_metadata"][field_name] = " ".join(values)

        
        # Procesar autores (Tag AU o AF)
        authors_list = raw_record.get('AF', raw_record.get('AU', []))
        for au in authors_list:
            processed["authors"].append({"name": au})
            
        # Procesar conceptos/keywords (Tag DE o ID)
        keywords = raw_record.get('DE', []) + raw_record.get('ID', [])
        # A veces vienen en una línea separadas por punto y coma
        all_keywords = []
        for kw in keywords:
            all_keywords.extend([k.strip() for k in kw.split(';') if k.strip()])
        processed["concepts"] = [{"name": k} for k in set(all_keywords)]
        
        # Procesar Afiliaciones (Tag C1)
        # Formato: [Author1; Author2] Univ Name, Dept, City, Country
        affiliations = raw_record.get('C1', [])
        for aff in affiliations:
            # Extraer nombre de institución (groseramente por ahora)
            parts = aff.split(']') if ']' in aff else [aff]
            addr = parts[-1].strip()
            inst_name = addr.split(',')[0].strip()
            if inst_name:
                processed["institutions"].append({"name": inst_name})
        
        # Eliminar duplicados de instituciones
        seen_inst = set()
        unique_inst = []
        for inst in processed["institutions"]:
            if inst["name"] not in seen_inst:
                unique_inst.append(inst)
                seen_inst.add(inst["name"])
        processed["institutions"] = unique_inst

        return processed

if __name__ == "__main__":
    # Test simple
    parser = WoSParser()
    sample_records = parser.parse_file(r"C:\Users\jlja\Documents\Proyectos\RAGs\data\papers_2025_2026.txt")
    print(f"Número de registros parseados: {len(sample_records)}")
    if sample_records:
        print(f"Primer título: {sample_records[0]['title']}")
