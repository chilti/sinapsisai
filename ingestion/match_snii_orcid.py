# ingestion/match_snii_orcid.py
import json
import clickhouse_connect
import os
import pandas as pd
import unicodedata
import re
from Levenshtein import jaro_winkler

# Configuración ClickHouse
CH_HOST = "127.0.0.1"
CH_PORT = 8123
CH_USER = "admin"
CH_PASS = "admin"
CH_DB   = "openalex"

# Paths
SEED_PATH = "data/authors_mexico_seed.json"
SNII_PATH = "data/Investigadores_vigentes_2025.xlsx"
EXCEL_FILES = [
    "data/C3-autores.xlsx",
    "data/ListadoICN-ORCID.xlsx"
]
OUTPUT_PATH = "data/authors_matched_orcid.json"

def normalize_text(text):
    if not text: return ""
    # Remover acentos y convertir a minúsculas
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8')
    text = text.lower().strip()
    return re.sub(r'\s+', ' ', text)

def calculate_score(seed_author, ch_record):
    """
    Calcula un score de 0 a 1 basado en la coincidencia.
    ch_record: (orcid, given_names, family_name, credit_name, emails, ch_dois, last_aff, city, country)
    """
    orcid, gn, fn, cn, emails, ch_dois, last_aff, city, country = ch_record
    
    # 0. Coincidencia de ARTÍCULOS (DOIs) - ¡Factor más fuerte!
    seed_dois = set([d.lower().strip() for d in seed_author.get('representative_dois', [])])
    ch_dois_set = set([d.lower().strip() for d in ch_dois])
    common_dois = seed_dois.intersection(ch_dois_set)
    
    if common_dois:
        # Si comparten al menos un DOI, la confianza es máxima
        return 1.0
    
    # 1. Nombre Completo (Peso 0.6 si no hay DOIs)
    full_name_seed = normalize_text(seed_author['name'])
    full_name_ch = normalize_text(f"{gn} {fn}")
    name_score = jaro_winkler(full_name_seed, full_name_ch)
    
    if cn:
        cn_score = jaro_winkler(full_name_seed, normalize_text(cn))
        name_score = max(name_score, cn_score)
    
    # 2. Afiliación (Peso 0.4 si no hay DOIs)
    aff_score = 0
    seed_aff = normalize_text(seed_author.get('main_affiliation', ''))
    if seed_aff and last_aff:
        last_aff_norm = normalize_text(last_aff)
        keywords = ["unam", "ipn", "cinvestav", "tecnologico", "autonoma", "instituto", "universidad"]
        match_keywords = [k for k in keywords if k in seed_aff and k in last_aff_norm]
        
        jw_aff = jaro_winkler(seed_aff, last_aff_norm)
        aff_score = jw_aff if jw_aff > 0.8 else (0.4 if match_keywords else 0)

    total_score = (name_score * 0.6) + (aff_score * 0.4)
    return total_score

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
        return []
    try:
        df = pd.read_excel(SNII_PATH)
        # Ajustar nombres de columnas según inspección
        name_col = 'NOMBRE DEL INVESTIGADOR'
        inst_col = 'INSTITUCION DE ACREDITACION'
        
        authors = []
        for _, row in df.iterrows():
            authors.append({
                "name": str(row[name_col]),
                "main_affiliation": str(row[inst_col]),
                "source": "SNII_2025"
            })
        return authors
    except Exception as e:
        print(f"Error cargando SNII: {e}")
        return []

def run_matching(limit=1000, min_score=0.85):
    client = get_client()
    existing_mappings = load_existing_mappings()
    print(f"Mapeos locales cargados: {len(existing_mappings)}")
    
    all_authors = []
    # 1. Cargar Seed de Neo4j (autores ya identificados localmente)
    if os.path.exists(SEED_PATH):
        with open(SEED_PATH, 'r', encoding='utf-8') as f:
            all_authors.extend(json.load(f))
    
    # 2. Cargar SNII 2025
    snii_authors = load_snii_authors()
    print(f"Autores SNII cargados: {len(snii_authors)}")
    all_authors.extend(snii_authors)

    print(f"Procesando {min(len(all_authors), limit)} autores seleccionados...")
    results = []
    authors_to_search = []
    
    for author in all_authors[:limit]:
        name = author['name']
        norm_name = normalize_text(name)
        
        # 1. ¿Ya tenemos el ORCID en Excel?
        if norm_name in existing_mappings:
            results.append({
                "seed_name": name,
                "seed_aff": author.get('main_affiliation'),
                "matched_orcid": existing_mappings[norm_name],
                "matched_name": name,
                "score": 1.0,
                "source": "excel_mapping"
            })
            continue

        # 2. ¿Ya tenía ORCID en Neo4j?
        if author.get('orcid'):
            continue
            
        parts = norm_name.split()
        if not parts: continue
        
        search_term = parts[-1] 
        if len(parts) > 1:
            search_term = parts[-2]
            
        author['search_term'] = search_term
        authors_to_search.append(author)

    # 3. Buscar en ClickHouse por Lotes
    batch_size = 50
    total = len(authors_to_search)
    
    for i in range(0, total, batch_size):
        batch = authors_to_search[i:i + batch_size]
        # Extraer términos de búsqueda únicos
        terms = list(set([a['search_term'] for a in batch]))
        
        # Formatear array SQL estricto para ClickHouse (ej. ['perez', 'lopez'])
        terms_sql = "[" + ",".join([f"'{t.replace(chr(39), chr(39)+chr(39))}'" for t in terms]) + "]"
        
        query = f"""
        SELECT orcid, given_names, family_name, credit_name, emails, dois,
               last_affiliation, last_affiliation_city, last_affiliation_country
        FROM orcid_records
        WHERE multiSearchAnyCaseInsensitiveUTF8(family_name, {terms_sql}) > 0
           OR multiSearchAnyCaseInsensitiveUTF8(credit_name, {terms_sql}) > 0
           OR multiSearchAnyCaseInsensitiveUTF8(given_names, {terms_sql}) > 0
        """
        
        try:
            print(f"Consultando ClickHouse para {len(terms)} apellidos (lote {i//batch_size + 1} de {total//batch_size + 1}) - Esto leerá disco masivamente una sola vez...")
            candidates = client.query(query).result_rows
            print(f" -> {len(candidates)} candidatos descargados a memoria.")
            
            for author in batch:
                sterm = author['search_term'].lower()
                # Filtrar rápido en memoria los candidatos que pertenecen a ESTE autor específico
                my_cands = []
                for cand in candidates:
                    gn = str(cand[1] or '').lower()
                    fn = str(cand[2] or '').lower()
                    cn = str(cand[3] or '').lower()
                    if sterm in gn or sterm in fn or sterm in cn:
                        my_cands.append(cand)
                
                best_match = None
                max_s = 0
                for cand in my_cands:
                    score = calculate_score(author, cand)
                    if score > max_s:
                        max_s = score
                        best_match = cand
                
                if best_match and max_s >= min_score:
                    res = {
                        "seed_name": author['name'],
                        "seed_aff": author.get('main_affiliation'),
                        "matched_orcid": best_match[0],
                        "matched_name": f"{best_match[1]} {best_match[2]}",
                        "matched_aff": best_match[6], 
                        "score": round(max_s, 3),
                        "source": "clickhouse_fuzzy"
                    }
                    results.append(res)
                    print(f"   ✓ Match! {author['name']} -> {best_match[0]} (Score: {max_s:.2f})")
                
        except Exception as e:
            print(f"Error en batch_query (Lote {i}): {e}")

    # Guardar resultados
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"Proceso completado. Matches encontrados: {len(results)}")

if __name__ == "__main__":
    run_matching(limit=500) # Probar con 500 para validar
