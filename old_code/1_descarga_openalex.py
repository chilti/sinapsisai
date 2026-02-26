import os
import pandas as pd
import requests
import json
import time
import pyalex
import pybliometrics
from pybliometrics.scopus import AuthorRetrieval, ScopusSearch
from config import EMAIL_ADDRESS
from db_manager import DBManager

# --- CONFIGURACIÓN ---

pyalex.config.email = EMAIL_ADDRESS
pybliometrics.scopus.init()

# --- FUNCIONES AUXILIARES ---

def limpiar_nombre_archivo(nombre):
    """Limpia un nombre para que sea válido como nombre de archivo."""
    return "".join([c for c in nombre if c.isalpha() or c.isdigit() or c.isspace()]).rstrip()

def deconstruct_abstract(inverted_abstract):
    """Reconstruye un abstract desde el formato de índice invertido de OpenAlex."""
    if not inverted_abstract: return None
    try:
        abstract_len = max(pos for val in inverted_abstract.values() for pos in val) + 1
        abstract_list = [""] * abstract_len
        for word, positions in inverted_abstract.items():
            for pos in positions: abstract_list[pos] = word
        return " ".join(filter(None, abstract_list))
    except (ValueError, TypeError):
        return None

# <-- MODIFICADO: Ahora devuelve un diccionario {doi: metadata}
def obtener_metadatos_de_scopus(scopus_ids):
    """Obtiene metadatos básicos para una lista de Scopus Author IDs."""
    if not scopus_ids:
        return {}
    
    metadatos_encontrados = {}
    for scopus_id in scopus_ids:
        try:
            au = AuthorRetrieval(scopus_id)
            
            for pub in au.get_documents():
                #print(pub)
                if pub.doi and pub.doi not in metadatos_encontrados:
                    record = {
                        'Title': pub.title,
                        'Year': pub.coverDate.split('-')[0] if pub.coverDate else None,
                        'Source title': pub.publicationName,
                        'Cited by': pub.citedby_count,
                        'DOI': pub.doi,
                        'Authors': pub.author_names,
                        'Author Keywords': pub.authkeywords,
                        'Document Type': pub.subtypeDescription,
                        'Source': 'Scopus', # Indicamos el origen de estos datos
                        'EID': pub.eid
                    }
                    metadatos_encontrados[pub.doi] = record
        except Exception as e:
            print(f"    -> Advertencia: No se pudo procesar Scopus ID {scopus_id}. Error: {e}")
    print(f"    -> Encontrados {len(metadatos_encontrados)} DOIs únicos en Scopus.")
    return metadatos_encontrados

# <-- MODIFICADO: Ahora devuelve un diccionario {doi: metadata}
def obtener_metadatos_de_orcid(orcid_id):
    """Obtiene metadatos básicos para un ORCID iD."""
    if not orcid_id:
        return {}
    orcid_id = orcid_id.replace('https://orcid.org/','')
    metadatos_encontrados = {}
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    headers = {"Accept": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        for work_group in data.get('group', []):
            summary = work_group.get('work-summary', [{}])[0]
            doi = None
            if isinstance(summary.get('external-ids'), dict):
                for eid in summary.get('external-ids', {}).get('external-id', []):
                    if isinstance(eid, dict) and eid.get('external-id-type') == 'doi':
                        doi = eid.get('external-id-value')
                        break
            #print(summary)
            journal_title_dict = summary.get('journal-title')
            publicationDate = summary.get('publication-date', {})
            if doi and doi not in metadatos_encontrados:
                record = {
                    'Title': summary.get('title', {}).get('title', {}).get('value'),
                    'Year': publicationDate.get('year', {}).get('value') if publicationDate else None,
                    'Source title': journal_title_dict.get('value') if journal_title_dict else None,
                    'DOI': doi,
                    'Source': 'ORCID',
                    # ORCID no provee citas o autores de forma sencilla aquí
                    'Cited by': None, 
                    'Authors': None,
                    'Document Type': summary.get('type'),
                    'EID': None
                }
                metadatos_encontrados[doi] = record
    except requests.exceptions.RequestException as e:
        print(f"    -> Advertencia: No se pudo procesar ORCID {orcid_id}. Error: {e}")
    
    print(f"    -> Encontrados {len(metadatos_encontrados)} DOIs únicos en ORCID.")
    return metadatos_encontrados
import requests

def obtener_autores_de_crossref(doi):
    """
    Toma un DOI, consulta la API de Crossref y devuelve la lista de autores.
    
    Args:
        doi (str): El DOI de la publicación.

    Returns:
        str: Una cadena con los nombres de los autores separados por punto y coma,
             o None si no se encuentran.
    """
    if not doi:
        return None
        
    url = f"https://api.crossref.org/works/{doi}"
    try:
        response = requests.get(url, timeout=10) # Añadimos un timeout
        # Si el DOI no existe, Crossref devuelve un 404
        if response.status_code != 200:
            print(f"      -> Crossref: DOI {doi} no encontrado (status: {response.status_code}).")
            return None

        data = response.json().get('message', {})
        authors = data.get('author', [])
        
        if not authors:
            return None

        # Formateamos la lista de autores
        author_list = []
        for author in authors:
            name = ""
            if 'given' in author and 'family' in author:
                name = f"{author['family']}, {author['given']}"
            elif 'family' in author:
                name = author['family']
            elif 'name' in author:
                name = author['name']
            
            if name:
                author_list.append(name)
        
        return "; ".join(author_list) if author_list else None

    except requests.exceptions.RequestException as e:
        print(f"      -> Crossref: Error de red para DOI {doi}. Error: {e}")
        return None

import requests

def obtener_metadatos_de_datacite(doi):
    """
    Toma un DOI, consulta la API de DataCite y devuelve metadatos clave.
    
    Args:
        doi (str): El DOI de la publicación.

    Returns:
        dict: Un diccionario con los metadatos formateados (Title, Authors, Year, etc.)
              o None si no se encuentran.
    """
    if not doi:
        return None
        
    url = f"https://api.datacite.org/dois/{doi}"
    headers = {'Accept': 'application/vnd.api+json'} # DataCite recomienda esta cabecera
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"      -> DataCite: DOI {doi} no encontrado (status: {response.status_code}).")
            return None

        data = response.json().get('data', {}).get('attributes', {})
        if not data:
            return None

        # --- Extracción de metadatos ---
        authors_list = [author.get('name', '') for author in data.get('creators', [])]
        authors_str = "; ".join(filter(None, authors_list))

        record = {
            'Title': data.get('titles', [{}])[0].get('title'),
            'Authors': authors_str if authors_str else None,
            'Year': data.get('publicationYear'),
            'Source title': data.get('publisher'),
            'DOI': data.get('doi'),
            'Document Type': data.get('types', {}).get('resourceTypeGeneral'),
            'Source': 'DataCite', # Indicamos el origen de los datos
            'Cited by': None, # DataCite no provee conteo de citas de forma directa
            'EID': None
        }
        
        return record

    except requests.exceptions.RequestException as e:
        print(f"      -> DataCite: Error de red para DOI {doi}. Error: {e}")
        return None

# --- FUNCIÓN PRINCIPAL ---

def descargar_produccion_unificada(academicos_json_path="../data/raw/profesores2.json", directorio_salida="../data/raw/datos_crudos_autores_openalex", forzar_descarga=False):
    """
    Combina DOIs de Scopus y ORCID, enriquece con OpenAlex y usa datos de respaldo si es necesario.
    """
    if not os.path.exists(directorio_salida):
        os.makedirs(directorio_salida)

    with open(academicos_json_path, 'r', encoding='utf-8') as f:
        academicos = json.load(f)

    for nombre, info in academicos.items():
        scopus_ids = info.get("scopus")
        orcid_id = info.get("orcid")
        id_primario = scopus_ids[0] if scopus_ids else limpiar_nombre_archivo(nombre)
        ruta_archivo = os.path.join(directorio_salida, f"{id_primario}_{limpiar_nombre_archivo(nombre)}.csv")

        print("-" * 50)
        print(f"Procesando a: {nombre}")

        if os.path.exists(ruta_archivo) and not forzar_descarga:
            print("El archivo ya existe. Saltando.")
            continue

        # --- FASE 1: RECOPILACIÓN DE METADATOS BÁSICOS ---
        print("  Fase 1: Recopilando metadatos desde Scopus y ORCID...")
        meta_scopus = obtener_metadatos_de_scopus(scopus_ids)
        meta_orcid = obtener_metadatos_de_orcid(orcid_id)
        
        # <-- NUEVO: Combinamos los metadatos, dando prioridad a Scopus
        meta_unificada = meta_scopus.copy()
        for doi, data in meta_orcid.items():
            if doi not in meta_unificada:
                meta_unificada[doi] = data

        if not meta_unificada:
            print("  No se encontraron publicaciones en ninguna fuente para este autor.")
            continue
            
        print(f"  Total de publicaciones únicas encontradas: {len(meta_unificada)}. Iniciando Fase 2...")

        # --- FASE 2: ENRIQUECIMIENTO CON OPENALEX Y LÓGICA DE RESPALDO ---
        datos_publicaciones = []
        for i, doi in enumerate(meta_unificada):
            print(f"    -> Procesando DOI {i+1}/{len(meta_unificada)}: https://doi.org/{doi}")
            try:
                # Intenta obtener el registro enriquecido de OpenAlex
                work = pyalex.Works()['https://doi.org/'+doi]
                
                # Mapeo de campos
                authorships = work.get('authorships', [])
                authors = "; ".join([au['author']['display_name'] for au in authorships])
                author_ids = ";".join([au['author']['id'].split('/')[-1] for au in authorships]) # OpenAlex Author IDs
                biblio = work.get('biblio', {})
                references = " || ".join([ref.split('/')[-1] for ref in work.get('referenced_works', []) if ref])
                keywords_str = "; ".join([kw['display_name'] for kw in work.get('keywords', [])])

                record = {
                    'Authors': authors,
                    'Author(s) ID': author_ids,
                    'Title': work.get('title'),
                    'Year': work.get('publication_year'),
                    'Source title': work.get('source', {}).get('display_name'),
                    'Volume': biblio.get('volume'),
                    'Issue': biblio.get('issue'),
                    'Art. No.': None,
                    'Page start': biblio.get('first_page'),
                    'Page end': biblio.get('last_page'),
                    'Cited by': work.get('cited_by_count'),
                    'DOI': work.get('doi', ''),#.replace("https://doi.org/", ""),
                    'Link': work.get('id'),
                    'Affiliations': "; ".join(list(set(au.get('raw_affiliation_string', '') for au in authorships if au.get('raw_affiliation_string')))),
                    'Abstract': deconstruct_abstract(work.get('abstract_inverted_index')),
                    'Author Keywords': None,
                    'Index Keywords': keywords_str,
                    'References': references,
                    'Document Type': work.get('type'),
                    'Source': 'OpenAlex',
                    'EID': work.get('id').split('/')[-1],
                    'ISSN': work.get('source', {}).get('issn_l'),
                    'ISBN': work.get('source', {}).get('isbn'),
                    'Funding Details': None,
                    'Funding Agencies': "; ".join([funder.get('funder_display_name', '') for funder in work.get('grants', [])]),
                }
                datos_publicaciones.append(record)
                
            except Exception as e:
                # --- LÓGICA DE RESPALDO MEJORADA (CON DATACITE) ---
                print(f"    -> Info: No se encontró en OpenAlex para DOI {doi}. Usando datos de respaldo.")
                datos_respaldo = meta_unificada[doi].copy() # Usamos .copy() para modificarlo de forma segura
                
                # Si la fuente es ORCID (y por tanto no tenemos autores), intentamos enriquecer
                if datos_respaldo.get('Source') == 'ORCID':
                    print(f"      -> Buscando en Crossref para el registro de ORCID...")
                    autores_crossref = obtener_autores_de_crossref(doi)
                    
                    if autores_crossref:
                        print(f"      -> ¡Éxito! Autores encontrados en Crossref.")
                        datos_respaldo['Authors'] = autores_crossref
                        datos_respaldo['Source'] = 'ORCID/Crossref' # Indicamos que se enriqueció
                    else:
                        # <-- NUEVO: Si Crossref falla, intentamos con DataCite
                        print(f"      -> No se encontró en Crossref. Buscando en DataCite...")
                        meta_datacite = obtener_metadatos_de_datacite(doi)
                        
                        if meta_datacite:
                            print(f"      -> ¡Éxito! Metadatos encontrados en DataCite.")
                            # Actualizamos nuestro registro de respaldo con los datos de DataCite
                            datos_respaldo.update(meta_datacite)
                        else:
                            print(f"      -> No se encontró en DataCite. Usando datos básicos de ORCID.")
                
                # Creamos el registro con la mejor información que hayamos podido recolectar
                record = {
                    'Authors': datos_respaldo.get('Authors'),
                    'Title': datos_respaldo.get('Title'),
                    'Year': datos_respaldo.get('Year'),
                    'Source title': datos_respaldo.get('Source title'),
                    'Cited by': datos_respaldo.get('Cited by'),
                    'DOI': 'https://doi.org/'+doi,
                    'Document Type': datos_respaldo.get('Document Type'),
                    'Source': datos_respaldo.get('Source'),
                    'EID': datos_respaldo.get('EID'),
                    # Rellenamos el resto de campos con None
                    'Author(s) ID': None, 'Link': None, 'Affiliations': None, 'Abstract': None,
                    'Index Keywords': None, 'References': None, 'Funding Agencies': None,
                }
                datos_publicaciones.append(record)
            
            time.sleep(0.1)

        # --- GUARDADO FINAL ---
        if datos_publicaciones:
            df = pd.DataFrame(datos_publicaciones)
            # Aseguramos un orden de columnas consistente
            column_order = ['EID', 'Title', 'Authors', 'Author(s) ID', 'Year', 'Source title', 'Cited by', 'DOI', 
                            'Link', 'Affiliations', 'Abstract', 'Index Keywords', 'References', 
                            'Document Type', 'Source', 'Funding Agencies']
            df = df.reindex(columns=column_order)
            df.to_csv(ruta_archivo, index=False, encoding='utf-8-sig')
            print(f"✓ {len(df)} registros guardados exitosamente en: '{ruta_archivo}'")

            # --- GUARDADO EN LANCEDB ---
            try:
                db = DBManager()
                # Pasamos la lista de diccionarios original
                db.save_publications(datos_publicaciones)
                print(f"✓ Registros sincronizados con LanceDB.")
            except Exception as e:
                print(f"⚠ Error al guardar en LanceDB: {e}")
        
        time.sleep(0.5)

if __name__ == "__main__":
    descargar_produccion_unificada(forzar_descarga=True)
