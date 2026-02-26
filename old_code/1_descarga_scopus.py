import os
import pandas as pd
import pybliometrics
from pybliometrics.scopus import AuthorRetrieval, AbstractRetrieval
import json
import time
import sys

# Add Base path to find db_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from etl.db_manager import DBManager

pybliometrics.init()

def descargar_produccion_completa_rich(academicos, forzar_descarga=False):
    """
    Descarga la producción científica completa para una lista de académicos,
    extrae metadatos ricos de autores y relaciones, y guarda directamente en LanceDB.
    """
    db = DBManager()
    
    # 1. Identify Faculty Members from JSON
    faculty_auids = set()
    faculty_map = {} # auid -> full_name (from JSON)
    for name, data in academicos.items():
        for sid in data.get("scopus", []):
            faculty_auids.add(str(sid))
            faculty_map[str(sid)] = name
            
    print(f"Loaded {len(faculty_auids)} faculty IDs from configuration.")

    for academico in academicos:
        nombre_json = academico
        lista_scopus_id = academicos[academico]["scopus"]
        
        if not lista_scopus_id:
            print(f"Sin Scopus IDs para {nombre_json}. Saltando.")
            continue
            
        print("-" * 50)
        print(f"Procesando Faculty: {nombre_json} (IDs: {', '.join(map(str, lista_scopus_id))})")

        todos_los_eids = set()

        # Step 1: Find all papers for this Faculty member
        try:
            for scopus_id in lista_scopus_id:
                print(f"  Buscando en perfil ID: {scopus_id}...")
                try:
                    au = AuthorRetrieval(scopus_id)
                    eids_parciales = {pub.eid for pub in au.get_documents()}
                    print(f"    -> Se encontraron {len(eids_parciales)} publicaciones.")
                    todos_los_eids.update(eids_parciales)
                except Exception as e:
                    print(f"    ✗ Advertencia: No se encontró el perfil para el ID: {scopus_id} ({e})")

            lista_eids_unicos = list(todos_los_eids)
            if not lista_eids_unicos:
                print("No se encontraron publicaciones para este autor.")
                continue

            print(f"Total de publicaciones únicas encontradas: {len(lista_eids_unicos)}. Procesando...")
            
            # Step 2: Process each paper
            # We batch updates to DB? Or one by one?
            # One by one is safer for rate limits and partial progress.
            
            for i, eid in enumerate(lista_eids_unicos):
                time.sleep(0.2) # Rate limit
                print(f"  -> Obteniendo doc {i+1}/{len(lista_eids_unicos)} (EID: {eid})")
                
                try:
                    doc = None
                    # Try FULL view first
                    try:
                        doc = AbstractRetrieval(eid, view="FULL")
                    except Exception as e_full:
                        print(f"    ! FULL view access denied. Trying META view...")
                        try:
                            doc = AbstractRetrieval(eid, view="META")
                        except Exception as e_meta:
                            print(f"    ! META view also failed: {e_meta}")
                            continue

                    def safe_get(obj, attr, default=None):
                        try:
                            # pybliometrics properties raise errors if not in view
                            val = getattr(obj, attr, default)
                            return val if val is not None else default
                        except:
                            return default

                    # Basic fields
                    title = safe_get(doc, 'title')
                    coverDate = safe_get(doc, 'coverDate')
                    year = coverDate.split('-')[0] if coverDate else 0
                    publicationName = safe_get(doc, 'publicationName')
                    volume = safe_get(doc, 'volume')
                    issueIdentifier = safe_get(doc, 'issueIdentifier')
                    
                    pageRange = safe_get(doc, 'pageRange')
                    page_start = pageRange.split('-')[0] if pageRange else None
                    page_end = pageRange.split('-')[1] if pageRange and '-' in pageRange else None
                    
                    citedby_count = safe_get(doc, 'citedby_count')
                    doi = safe_get(doc, 'doi')
                    url = safe_get(doc, 'url')
                    abstract = safe_get(doc, 'abstract')
                    authkeywords = safe_get(doc, 'authkeywords')
                    aggregationType = safe_get(doc, 'aggregationType')
                    _eid = safe_get(doc, 'eid')
                    issn = safe_get(doc, 'issn')
                    isbn = safe_get(doc, 'isbn')
                    
                    # Complex lists
                    authors_list = safe_get(doc, 'authors') or []
                    aff_list = safe_get(doc, 'affiliation') or []
                    
                    # Format for 'publications' table
                    authors_str = "; ".join([f"{getattr(a,'indexed_name','')}" for a in authors_list])
                    author_ids_str = ";".join([f"{getattr(a,'auid','')}" for a in authors_list])
                    
                    # Convert authkeywords list to string if needed
                    import json
                    if isinstance(authkeywords, list):
                        authkeywords_str = "; ".join(authkeywords)
                    else:
                        authkeywords_str = authkeywords if authkeywords else ""
                    
                    pub_record = {
                        'title': title,
                        'year': year,
                        'source_title': publicationName,
                        'volume': volume,
                        'issue': issueIdentifier,
                        'cited_by': int(citedby_count) if citedby_count else 0,
                        'doi': doi,
                        'link': url, 
                        'abstract': abstract,
                        'author_keywords': authkeywords_str,
                        'document_type': aggregationType,
                        'eid': _eid,
                        'issn': issn,
                        'isbn': isbn,
                        'authors': authors_str,
                        'author_ids': author_ids_str
                    }
                    
                    # Sanitize ALL values: convert lists to JSON strings, None to empty string
                    for key, value in pub_record.items():
                        if value is None:
                            pub_record[key] = ""
                        elif isinstance(value, list):
                            pub_record[key] = json.dumps(value) if value else ""
                        elif not isinstance(value, (str, int, float, bool)):
                            # Convert any other type to string
                            pub_record[key] = str(value)
                    
                    # Save Publication
                    try:
                        db.save_publications([pub_record])
                    except Exception as e_pub:
                        print(f"    ! Error saving publication: {e_pub}")
                        raise
                    
                    # --- B. Process Authors & Relations ---
                    rich_authors = []
                    author_relations = []
                    
                    if authors_list:
                        for auth in authors_list:
                            try:
                                auid = str(auth.auid)
                                indexed_name = auth.indexed_name # "Surname, Intials"
                                
                                # Determine if Faculty
                                is_faculty = auid in faculty_auids
                                full_name_canonical = faculty_map.get(auid, indexed_name) 
                                
                                rich_authors.append({
                                    'auid': auid,
                                    'full_name': full_name_canonical,
                                    'is_faculty': is_faculty,
                                    'aliases': [indexed_name], 
                                })
                                
                                # Relation
                                author_relations.append({
                                    'auid': auid,
                                    'publication_link': url, 
                                    'paper_eid': _eid,
                                })
                            except Exception as e_auth:
                                # Skip malformed author in list
                                continue
                    
                    # Save Rich Data
                    try:
                        db.save_authors_rich(rich_authors)
                    except Exception as e_authors:
                        print(f"    ! Error saving authors: {e_authors}")
                        raise
                        
                    try:
                        db.save_author_publications(author_relations)
                    except Exception as e_rels:
                        print(f"    ! Error saving relations: {e_rels}")
                        raise

                except Exception as e:
                    print(f"    Error al procesar el EID {eid}: {e}")

        except Exception as e:
            print(f"✗ Ocurrió un error inesperado con el grupo de {nombre_json}: {e}")

if __name__ == "__main__":
    # Lista del personal a procesar.
    # Try different json files if needed
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "../data/raw/profesores2.json")

    # If simple run from root
    if not os.path.exists(json_path):
         # Try local
         if os.path.exists("profesores2.json"):
             json_path = "profesores2.json"
         elif os.path.exists("data/raw/profesores2.json"):
             json_path = "data/raw/profesores2.json"

    if os.path.exists(json_path):
        with open(json_path, "r", encoding='utf-8') as f:
            profesores = json.load(f)
        
        # Override with specific list if argument provided? No.
        descargar_produccion_completa_rich(profesores)
    else:
        print(f"No se encontró {json_path}")
