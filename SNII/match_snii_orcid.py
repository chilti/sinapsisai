# ingestion/match_snii_orcid.py
import json
import clickhouse_connect
import os
import pandas as pd
import unicodedata
import re
import pyalex
from Levenshtein import jaro_winkler
from datetime import datetime

# Configurar Pyalex
pyalex.config.email = "sin_correo@ciencias.unam.mx"

# Configuración ClickHouse
CH_HOST = "127.0.0.1"
CH_PORT = 8123
CH_USER = "admin"
CH_PASS = "admin"
CH_DB   = "openalex"

# Definir rutas absolutas basadas en la ubicación del script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SEED_PATH = os.path.join(SCRIPT_DIR, "..", "data", "authors_mexico_seed.json")
SNII_PATH = os.path.join(SCRIPT_DIR, "Investigadores_vigentes_2025.xlsx")
EXCEL_FILES = [
    os.path.join(SCRIPT_DIR, "..", "data", "C3-autores.xlsx"),
    os.path.join(SCRIPT_DIR, "..", "data", "ListadoICN-ORCID.xlsx")
]
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "..", "data", "authors_matched_orcid.json")

def normalize_text(text):
    if not text: return ""
    # Remover acentos y convertir a minúsculas
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
    text = text.lower().strip()
    # Remover títulos académicos comunes (y el punto/espacio que los siga)
    text = re.sub(r'\b(dr|dra|msc|phd|mtro|mtra|lic|ing|profr?|profra)\.?\s*', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_sub_affiliation(affiliation):
    """Extrae facultades, centros, institutos o departamentos de una cadena de afiliación"""
    if not affiliation: return None
    
    # Patrones comunes en español e inglés
    patterns = [
        r"(facultad de [^,]+)",
        r"(instituto de [^,]+)",
        r"(centro de [^,]+)",
        r"(departamento de [^,]+)",
        r"(school of [^,]+)",
        r"(department of [^,]+)",
        r"(institute of [^,]+)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, affiliation, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def fetch_recent_dois(orcid, years=3):
    """Obtiene DOIs de los últimos años usando Pyalex"""
    current_year = datetime.now().year
    min_year = current_year - years
    
    recent_dois = []
    try:
        # Buscar trabajos del autor en OpenAlex
        works = pyalex.Works().filter(author={"orcid": orcid}, publication_year=f">{min_year-1}").select(["doi", "publication_year", "title"]).get()
        for work in works:
            if work.get('doi'):
                doi = work['doi'].replace("https://doi.org/", "")
                recent_dois.append({
                    "doi": doi,
                    "year": work.get('publication_year'),
                    "title": work.get('title')
                })
    except Exception as e:
        print(f"      ! Error consultando OpenAlex para {orcid}: {e}")
    
    return recent_dois

def calculate_score(seed_author, ch_record):
    """
    Calcula un score de 0 a 1 basado en la coincidencia. 
    ch_record: (orcid, given_names, family_name, credit_name, emails, last_aff, city, country)
    """
    orcid, gn, fn, cn, emails, last_aff, city, country = ch_record
    
    # 0. Coincidencia de ARTÍCULOS (DOIs) - Si la semilla tiene DOIs y podemos cruzarlos
    # (En este entorno local, orcid_records no tiene DOIs, omitimos este paso de CH directo)
    
    # 0.1 Coincidencia de EMAILS
    seed_emails = set([e.lower().strip() for e in seed_author.get('emails', [])])
    ch_emails_set = set([e.lower().strip() for e in emails])
    if seed_emails.intersection(ch_emails_set) and len(seed_emails.intersection(ch_emails_set)) > 0:
        return 1.0

    # 1. Nombre Completo (Fuzzy Matching con Tokens Ordenados)
    # Esto hace que "Lopez, Juan" y "Juan Lopez" sean idénticos al compararlos
    def get_token_sorted_name(name_str):
        clean = normalize_text(name_str).replace(',', ' ')
        tokens = sorted([t for t in clean.split() if len(t) > 1])
        return " ".join(tokens)

    sorted_seed = get_token_sorted_name(seed_author['name'])
    sorted_ch = get_token_sorted_name(f"{gn} {fn}")
    
    name_score = jaro_winkler(sorted_seed, sorted_ch)
    
    # También probar contra el nombre de crédito si existe
    if cn:
        sorted_cn = get_token_sorted_name(cn)
        name_score = max(name_score, jaro_winkler(sorted_seed, sorted_cn))
    
    # 2. Afiliación
    aff_score = 0
    seed_aff = normalize_text(seed_author.get('main_affiliation', ''))
    
    keywords = ["unam", "ipn", "cinvestav", "tecnologico", "autonoma", "instituto", "universidad", "ciencias", "nucleares"]
    
    if seed_aff and last_aff:
        last_aff_norm = normalize_text(last_aff)
        match_keywords = [k for k in keywords if k in seed_aff and k in last_aff_norm]
        
        jw_aff = jaro_winkler(seed_aff, last_aff_norm)
        # Boost si hay keywords comunes o alta similitud
        if jw_aff > 0.85:
            aff_score = jw_aff
        elif match_keywords:
            aff_score = 0.5 + (0.1 * len(match_keywords))
            aff_score = min(aff_score, 0.9)
    
    # Puntuación final ponderada
    # Si NO hay afiliación registrada en CH, no penalizamos tanto, confiamos más en nombre
    if not last_aff:
        total_score = name_score
    else:
        total_score = (name_score * 0.6) + (aff_score * 0.4)
    
    # REGLA ESTRICTA: Si el nombre no es casi idéntico, penalización fuerte
    if name_score < 0.93:
        total_score *= 0.5 
        
    return min(total_score, 1.0)

def get_client():
    return clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASS, database=CH_DB)

def load_existing_mappings():
    """Carga mapeos desde archivos Excel si existen para pre-llenar ORCIDs"""
    mappings = {}
    for f_path in EXCEL_FILES:
        if os.path.exists(f_path):
            try:
                # Intentamos detectar columnas de nombre y ORCID
                df = pd.read_excel(f_path)
                cols = df.columns.tolist()
                name_col = next((c for c in cols if 'nombre' in c.lower() or 'autor' in c.lower()), None)
                orcid_col = next((c for c in cols if 'orcid' in c.lower()), None)
                
                if name_col and orcid_col:
                    for _, row in df.iterrows():
                        name = normalize_text(str(row[name_col]))
                        orcid = str(row[orcid_col]).strip()
                        if orcid and orcid != 'nan' and len(orcid) > 10:
                            mappings[name] = orcid
            except Exception as e:
                print(f"Error cargando {f_path}: {e}")
    return mappings

def load_snii_authors():
    """Carga autores desde el archivo del SNII 2025"""
    if not os.path.exists(SNII_PATH):
        print(f"No se encontró el archivo SNII en {SNII_PATH}")
        return []
    try:
        df = pd.read_excel(SNII_PATH)
        # Ajustar nombres de columnas según inspección del archivo real 2025
        name_col = 'NOMBRE DEL INVESTIGADOR'
        inst_col = 'INSTITUCIÓN DE ACREDITACIÓN'
        sub_inst_col = 'DEPENDENCIA DE ACREDITACIÓN'
        
        authors = []
        for _, row in df.iterrows():
            # Extraer afiliación combinando institución y dependencia
            inst = str(row[inst_col]) if pd.notna(row[inst_col]) else ""
            dep = str(row[sub_inst_col]) if pd.notna(row[sub_inst_col]) else ""
            full_aff = f"{dep}, {inst}" if dep else inst
            
            authors.append({
                "name": str(row[name_col]),
                "main_affiliation": full_aff,
                "source": "SNII_2025"
            })
        return authors
    except Exception as e:
        print(f"Error cargando SNII: {e}")
        return []

def run_matching(limit=500, min_score=0.95):
    client = get_client()
    existing_mappings = load_existing_mappings()
    print(f"Mapeos locales cargados: {len(existing_mappings)}")

    mex_keywords = [
        "mexico", "mexic", "unam", "ipn", "cinvestav", "tecnologico", "autonoma", "itamb", "colmex", 
        "buap", "uaslp", "udem", "itesm", "uam", "politecnico",
        "guadalajara", "monterrey", "puebla", "queretaro", "yucatan", "chiapas", "veracruz", 
        "jalisco", "michoacan", "hidalgo", "zacatecas", "tabasco", "sinaloa", "sonora"
    ]
    
    # 1. Cargar SNII 2025 como base principal
    snii_authors = load_snii_authors()
    print(f"Autores SNII cargados: {len(snii_authors)}")

    # 2. Cargar Seed de Neo4j para cruce de datos
    neo4j_data = {}
    if os.path.exists(SEED_PATH) and os.path.getsize(SEED_PATH) > 0:
        try:
            with open(SEED_PATH, 'r', encoding='utf-8') as f:
                seed_data = json.load(f)
                for a in seed_data:
                    norm_n = normalize_text(a.get('name'))
                    if norm_n:
                        neo4j_data[norm_n] = a
            print(f"Base de conocimiento Neo4j cargada: {len(neo4j_data)} autores.")
        except Exception as e:
            print(f"Aviso: No se pudo cargar el archivo seed {SEED_PATH}: {e}")
    else:
        print(f"Aviso: El archivo seed {SEED_PATH} no existe o está vacío. Se omitirá el cruce con Neo4j.")

    # Asegurar que el directorio de salida existe
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    print(f"Procesando hasta {limit} investigadores del SNII...")
    results = []
    authors_to_search = []
    
    for author in snii_authors[:limit]:
        name = author['name']
        norm_name = normalize_text(name)
        if not norm_name: continue
        
        author['source_origin'] = 'SNII_2025'
        
        # A. ¿Ya tenemos el ORCID en archivos de mapeo manual (Excel)?
        if norm_name in existing_mappings:
            orcid = existing_mappings[norm_name]
            results.append({
                "source_name": name,
                "source_origin": "SNII_Excel",
                "source_aff": author.get('main_affiliation'),
                "matched_orcid": orcid,
                "matched_name": name,
                "score": 1.0,
                "match_type": "excel_mapping",
                "dois_last_3yr": fetch_recent_dois(orcid)
            })
            continue

        # B. ¿Existe en la base de Neo4j (Seed)?
        if norm_name in neo4j_data:
            n4j_author = neo4j_data[norm_name]
            if n4j_author.get('orcid'):
                orcid = n4j_author['orcid']
                results.append({
                    "source_name": name,
                    "source_origin": "SNII_Excel",
                    "source_aff": author.get('main_affiliation'),
                    "matched_orcid": orcid,
                    "matched_name": n4j_author.get('name'),
                    "score": 0.99, # Muy alta confianza por nombre exacto en Neo4j
                    "match_type": "neo4j_crosslink",
                    "dois_last_3yr": fetch_recent_dois(orcid)
                })
                continue
            
        # C. De lo contrario, buscar en ClickHouse (ORCID)
        # Limpiar puntuación para la búsqueda
        clean_name = norm_name.replace(',', ' ').strip()
        parts = clean_name.split()
        if not parts: continue
        
        # Estrategia de búsqueda mejorada para SNII (Apellido Paterno)
        # Si el nombre original tenía coma "APELLIDOS, NOMBRES", tomamos el primer apellido
        if ',' in author['name']:
            search_term = normalize_text(author['name'].split(',')[0].split()[0])
        else:
            # Si no hay coma, intentamos evitar nombres comunes como primer término de búsqueda
            common_names = ['juan', 'jose', 'maria', 'ana', 'luis', 'carlos', 'martha', 'rosa', 'pedro', 'jesus']
            search_term = parts[0]
            if search_term in common_names and len(parts) > 1:
                search_term = parts[-1] # Probar con el último si el primero es muy común
            
        author['search_term'] = search_term.strip().replace("'", "")
        authors_to_search.append(author)

    # 3. Buscar en ClickHouse por Lotes
    batch_size = 50
    total = len(authors_to_search)
    
    for i in range(0, total, batch_size):
        batch = authors_to_search[i:i + batch_size]
        # Filtrar stop words de los términos de búsqueda
        stop_words = {'de', 'del', 'la', 'los', 'las', 'san', 'santa'}
        terms = list(set([a['search_term'] for a in batch if a['search_term'] not in stop_words]))
        if not terms: continue
        
        # Opción universalmente compatible: LOWER(...) LIKE ...
        filters = []
        for t in terms:
            t_esc = t.lower().replace("'", "''")
            if len(t_esc) < 3: continue # Ignorar términos muy cortos
            filters.append(f"lower(family_name) LIKE '%{t_esc}%'")
            filters.append(f"lower(credit_name) LIKE '%{t_esc}%'")
        
        if not filters: continue
        where_clause = " OR ".join(filters)
        
        query = f"""
        SELECT orcid, given_names, family_name, credit_name, emails,
               last_affiliation, last_affiliation_city, last_affiliation_country
        FROM orcid_records
        WHERE {where_clause}
        LIMIT 5000
        """
        
        try:
            print(f"Consultando bloque {i//batch_size + 1} de {total//batch_size + 1} (Términos: {terms})...")
            candidates = client.query(query).result_rows
            print(f" -> {len(candidates)} candidatos devueltos por ClickHouse.")
            
            for author in batch:
                sterm = author['search_term'].lower()
                # Filtrar candidatos: que coincida el apellido Y que sea de México (MX) o tenga institución mexicana
                my_cands = []
                for c in candidates:
                    last_fn = str(c[2] or '').lower()
                    credit_n = str(c[3] or '').lower()
                    country = str(c[7] or '').upper()
                    aff_text = str(c[5] or '').lower()
                    
                    if sterm in last_fn or sterm in credit_n:
                        # Prioridad absoluta a México
                        if country == 'MX' or any(k in aff_text for k in mex_keywords):
                            my_cands.append(c)
                
                best_match = None
                max_s = 0
                for cand in my_cands:
                    score = calculate_score(author, cand)
                    if score > max_s:
                        max_s = score
                        best_match = cand
                
                if best_match and max_s >= 0.8: # Log para depuración si es cercano
                    print(f"   [Debug] Mejor match para '{author['name']}': ORCID={best_match[0]}, Score={max_s:.4f}")

                if best_match and max_s >= min_score:
                    orcid = best_match[0]
                    aff = best_match[5] # Ajustado índice por eliminación de 'dois'
                    res = {
                        "source_name": author['name'],
                        "source_origin": author.get('source_origin'),
                        "source_aff": author.get('main_affiliation'),
                        "matched_orcid": orcid,
                        "matched_name": f"{best_match[1]} {best_match[2]}",
                        "matched_institution": aff,
                        "matched_city": best_match[6],
                        "matched_country": best_match[7],
                        "sub_affiliation": extract_sub_affiliation(aff),
                        "score": round(max_s, 3),
                        "match_type": "clickhouse_fuzzy",
                        "dois_last_3yr": fetch_recent_dois(orcid)
                    }
                    results.append(res)
                    print(f"   ✓ Match! {author['name']} (Score: {max_s:.2f})")
                
        except Exception as e:
            print(f"Error en batch_query: {e}")

    # Guardar resultados
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"Proceso completado. Matches encontrados: {len(results)}")

if __name__ == "__main__":
    run_matching(limit=200) # Límite razonable para pruebas en este entorno
