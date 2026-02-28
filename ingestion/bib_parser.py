import bibtexparser
from typing import List, Dict, Any

class BibParser:
    """
    Parsea archivos de bibliografía (.bib) exportados desde gestores o Scopus/WoS.
    Extrae campos clave y los adapta al esquema similar a WoSParser.
    """
    
    @staticmethod
    def parse_file(file_path: str) -> List[Dict[str, Any]]:
        records = []
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as bibtex_file:
            bib_database = bibtexparser.load(bibtex_file)
            
        for entry in bib_database.entries:
            records.append(BibParser._process_record(entry))
            
        return records

    @staticmethod
    def _process_record(raw_record: Dict[str, str]) -> Dict[str, Any]:
        """
        Estructura un registro usando las llaves de bibtex (title, author, year, doi, etc).
        """
        # Normalizar llaves a minúsculas por si acaso
        rec = {k.lower(): v for k, v in raw_record.items()}
        
        # Extraer año
        year_str = rec.get('year', '0')
        year = int(year_str) if year_str.isdigit() else 0

        # Extraer DOI (eliminando URLs si las tiene incrustadas)
        doi = rec.get('doi', '').strip()
        if 'doi.org/' in doi:
            doi = doi.split('doi.org/')[-1]
            
        # Extraer título
        title = rec.get('title', '').replace('{', '').replace('}', '')
        
        # Procesar autores (separados por ' and ')
        authors_raw = rec.get('author', '')
        authors_list = [au.strip() for au in authors_raw.split(' and ') if au.strip()]
        
        authors = [{"name": au} for au in authors_list]
        
        # Conceptos 
        keywords_str = rec.get('keywords', '')
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        concepts = [{"name": k} for k in keywords]
        
        # Priorizar DOI como paper_id para unificar con otras fuentes
        # Si no hay DOI, usamos el ID del bibtex
        bib_id = raw_record.get('ID', 'unknown')
        paper_id = doi if doi else bib_id

        processed = {
            "paper_id": paper_id,
            "title": title,
            "abstract": rec.get('abstract', '').replace('{', '').replace('}', ''),
            "year": year,
            "doi": doi,
            "journal": rec.get('journal', ''),
            "citations": 0,
            "authors": authors,
            "concepts": concepts,
            "institutions": [],
            "raw_metadata": raw_record 
        }

        return processed

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        parser = BibParser()
        sample = parser.parse_file(sys.argv[1])
        print(f"Parsed {len(sample)} records from {sys.argv[1]}.")
        if sample:
            print(f"First title: {sample[0]['title']}")
