"""
ingestion/siia_scraper_snii.py
───────────────────────────────
Replicación de siia_scraper.py especializada para investigadores SNII de la UNAM.
Filtrado por: INSTITUCIÓN DE ACREDITACIÓN == 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)'
Genera JSONs por: SUBDEPENDENCIA DE ACREDITACIÓN
"""

import os
import re
import time
import json
import unicodedata
import pandas as pd
import argparse
import sys
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Configurar encoding para consola
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

import requests
from thefuzz import fuzz
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException, WebDriverException
from lxml import html

# Importar dependencias del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

# Ruta al padrón SNII (anclada al root del proyecto)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SNII_PATH = os.path.join(_ROOT, 'data', 'Investigadores_vigentes_2025.xlsx')
SNII_SHEET = '4T_2025 (44,794)'

# --- Funciones de Utilidad (Replicadas de siia_scraper.py) ---

def limpiar_nombre(nombre):
    if not isinstance(nombre, str):
        return ""
    nombre_sin_prefijo = re.sub(r'^(DR\.|DRA\.)\s*', '', nombre, flags=re.IGNORECASE).strip()
    # Protegemos la letra ñ y Ñ para no perderla en la normalización NFD
    s = nombre_sin_prefijo.replace('ñ', '##n##').replace('Ñ', '##N##')
    nombre_normalizado = unicodedata.normalize('NFD', s)
    s_sin_acentos = ''.join(c for c in nombre_normalizado if unicodedata.category(c) != 'Mn').upper()
    # Restauramos la ñ/Ñ
    return s_sin_acentos.replace('##N##', 'Ñ').replace('##n##', 'ñ')

def normalizar_palabras_nombre(nombre):
    clean = limpiar_nombre(nombre)
    # Separar en palabras, eliminar conectores y ordenar para comparación insensible al orden
    palabras = [p for p in clean.split() if p not in {"DE", "DEL", "LA", "LAS", "LOS", "Y"}]
    return "".join(sorted(palabras))

def agrupar_partes_nombre(texto):
    """
    Agrupa partículas como 'DE', 'LA', 'DEL', 'Y' con la palabra que les sigue
    para evitar que se tomen como apellidos independientes al dividir nombres.
    """
    particulas = {"DE", "DEL", "LA", "LAS", "LOS", "MAC", "MC", "SAN", "SANTA", "Y"}
    palabras = texto.split()
    agrupadas = []
    temp = []
    
    for p in palabras:
        if p in particulas:
            temp.append(p)
        else:
            temp.append(p)
            agrupadas.append(" ".join(temp))
            temp = []
            
    if temp and agrupadas:
        agrupadas[-1] += " " + " ".join(temp)
    elif temp:
        agrupadas.append(" ".join(temp))
        
    return agrupadas

def buscar_en_siia_con_reintentos(original_name, cleaned_name):
    """
    Intenta buscar progresivamente eliminando el apellido materno si fracasa la búsqueda estricta.
    Identifica apellidos y nombres a partir de la coma si existe.
    """
    ap_pat, ap_mat, nombre_pila = "", "", ""
    if ',' in original_name:
        apellidos, nombres = original_name.split(',', 1)
        aps = agrupar_partes_nombre(apellidos)
        ap_pat = aps[0] if len(aps) >= 1 else ""
        ap_mat = " ".join(aps[1:]) if len(aps) >= 2 else ""
        nombre_pila = nombres.strip()
    else:
        parts = agrupar_partes_nombre(cleaned_name)
        if len(parts) >= 3:
            ap_pat, ap_mat = parts[0], parts[1]
            nombre_pila = " ".join(parts[2:])
        elif len(parts) == 2:
            ap_pat, nombre_pila = parts[0], parts[1]
        else:
            ap_pat = cleaned_name

    ap_pat = re.sub(r'^(DR\.|DRA\.)\s*', '', ap_pat, flags=re.IGNORECASE).strip()
    
    url = "https://web.siia.unam.mx/siia-publico/c/personal.php"
    
    # Intento 1: Estricto
    data_strict = {'apellido_paterno': ap_pat, 'apellido_materno': ap_mat, 'nombre': nombre_pila}
    try:
        r = requests.post(url, data=data_strict, timeout=10)
        hits = re.findall(r'busqueda_individual\.php\?id=\d+', r.text)
        if hits:
            return [{"link": "https://web.siia.unam.mx/siia-publico/c/" + lnk} for lnk in set(hits)]
    except: pass

    # Intento 2: Sin materno
    if ap_mat:
        print(f"      [!] Reintentando sin materno para: {ap_pat} {nombre_pila}")
        data_no_mat = {'apellido_paterno': ap_pat, 'apellido_materno': '', 'nombre': nombre_pila}
        try:
            r = requests.post(url, data=data_no_mat, timeout=10)
            hits = re.findall(r'busqueda_individual\.php\?id=\d+', r.text)
            if hits:
                return [{"link": "https://web.siia.unam.mx/siia-publico/c/" + lnk} for lnk in set(hits)]
        except: pass

    # Intento 3: Solo Paterno (Extremo)
    print(f"      [!] Reintentando ÚNICAMENTE con paterno: {ap_pat}")
    data_min = {'apellido_paterno': ap_pat, 'apellido_materno': '', 'nombre': ''}
    try:
        r = requests.post(url, data=data_min, timeout=10)
        hits = re.findall(r'busqueda_individual\.php\?id=\d+', r.text)
        return [{"link": "https://web.siia.unam.mx/siia-publico/c/" + lnk} for lnk in set(hits)]
    except:
        return []

def verify_and_scrape_siia(driver, name_to_verify, url, is_retry=False):
    """
    Navega a una URL del SIIA y extrae datos. 
    Usa un umbral de fuzzy match más bajo (70%) si viene de un reintento.
    """
    try:
        try:
            driver.get(url)
        except TimeoutException:
            return None
        except WebDriverException:
            return None

        # Gestión de Modal
        try:
            boton_aceptar = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@class='modal-footer']//button[contains(text(), 'Aceptar')]"))
            )
            boton_aceptar.click()
            time.sleep(1)
        except:
            pass

        # Extraer Nombre
        try:
            scraped_name = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.XPATH, '/html/body/center/h1'))
            ).text
        except:
            return None

        # Verificación Fuzzy (90% normal, 70% reintento)
        threshold = 70 if is_retry else 90
        score = fuzz.token_set_ratio(name_to_verify, scraped_name)
        if score < threshold:
            return None 

        print(f"    ✅ Match ({score}%): {scraped_name}")

        data = {'name': scraped_name, 'scopus': [], 'orcid': '', 'areas': []}
        
        # Scopus
        try:
            td_e = driver.find_element(By.XPATH, "/html/body/center/div/table[2]/tbody/tr[4]/td")
            tree = html.fromstring(td_e.get_attribute('outerHTML'))
            data['scopus'] = [s.text_content().strip() for s in tree.xpath('.//span')]
        except: pass

        if data['scopus']:
            data['scopus'] = "; ".join(data['scopus'])
        else:
            data['scopus'] = ""

        # ORCID
        try:
            data['orcid'] = driver.find_element(By.XPATH, '//html/body/center/div/table[2]/tbody/tr[6]/td/span/a').get_attribute('href')
        except: pass

        # Áreas
        try:
            td_a = driver.find_element(By.XPATH, "/html/body/center/div/table[3]/tbody/tr[2]/td")
            tree = html.fromstring(td_a.get_attribute('outerHTML'))
            data['areas'] = [s.text_content().strip() for s in tree.xpath('./span') if s.text_content().strip()]
        except: pass

        return data
    except Exception as e:
        print(f"    ❌ Error en {url}: {e}")
        return None

# --- Lógica Principal del SNII ---

def main():
    parser = argparse.ArgumentParser(description="Scraper SIIA para Investigadores SNII-UNAM")
    parser.add_argument("--file", type=str, help="Ruta al archivo Excel de entrada (padrón SNII o lista simple de nombres)")
    parser.add_argument("--subdependency", type=str, help="Filtrar por una subdependencia específica")
    parser.add_argument("--limit", type=int, help="Límite de profesores por entidad para pruebas")
    args = parser.parse_args()

    # 1. Cargar y Filtrar Excel
    has_snii_cols = False
    excel_path = args.file if args.file else SNII_PATH
    print(f"📋 Cargando datos desde {excel_path}...")
    
    try:
        # Detectar formato del Excel
        df_temp = pd.read_excel(excel_path, nrows=5)
        has_snii_cols = 'INSTITUCION DE ACREDITACION' in df_temp.columns or 'NOMBRE DEL INVESTIGADOR' in df_temp.columns
        
        if has_snii_cols:
            df = pd.read_excel(excel_path, sheet_name=SNII_SHEET if excel_path == SNII_PATH else 0)
            inst_col    = 'INSTITUCION DE ACREDITACION'          # Sin tilde (como viene en el Excel)
            sub_inst_col = 'SUBDEPENDENCIA DE ACREDITACIÓN'
            name_col    = 'NOMBRE DEL INVESTIGADOR'
            
            # Filtrar UNAM
            df_unam = df[df[inst_col] == "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)"].copy()
            print(f"🎯 Investigadores UNAM encontrados: {len(df_unam)}")
            
            if args.subdependency:
                df_unam = df_unam[df_unam[sub_inst_col].str.contains(args.subdependency, case=False, na=False)]
                print(f"🔎 Filtrando por subdependencia '{args.subdependency}': {len(df_unam)} registros.")
        else:
            # Es una lista simple de nombres (1 sola columna, sin cabeceras)
            df = pd.read_excel(excel_path, header=None)
            df.columns = ['name']
            
            # Construir DataFrame compatible
            subdep_val = args.subdependency if args.subdependency else "FACULTAD DE CIENCIAS"
            df_unam = pd.DataFrame({
                'NOMBRE DEL INVESTIGADOR': df['name'].dropna().astype(str),
                'INSTITUCION DE ACREDITACION': "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)",
                'SUBDEPENDENCIA DE ACREDITACIÓN': subdep_val
            })
            inst_col = 'INSTITUCION DE ACREDITACION'
            sub_inst_col = 'SUBDEPENDENCIA DE ACREDITACIÓN'
            name_col = 'NOMBRE DEL INVESTIGADOR'
            print(f"🎯 Lista simple de nombres cargada: {len(df_unam)} registros para '{subdep_val}'.")
            
    except Exception as e:
        print(f"❌ Error al leer el archivo Excel: {e}")
        return

    # 2. Configurar Selenium
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(40)

    # 3. Cache de Neo4j (opcional — si falla, el JSON es la fuente de verdad)
    graph_store = None
    existing_academics = {}
    try:
        from database.knowledge_graph import Neo4jGraphStore
        graph_store = Neo4jGraphStore()
        with graph_store.driver.session() as session:
            # Filtrar por UNAM en el grafo para optimizar y asegurar precisión
            query = """
            MATCH (a:Person)-[:AFFILIATED_TO]->(sub)
            OPTIONAL MATCH (sub)-[:PART_OF*0..2]->(inst:Institution)
            WHERE inst.name CONTAINS 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO'
            RETURN a.fullname AS name, a.siia AS siia_url, a.orcid AS orcid, a.scopus_ids AS scopus_ids, a.is_snii AS is_snii
            """
            res = session.run(query)
            for r in res:
                if r["name"]:
                    norm_name = normalizar_palabras_nombre(r["name"])
                    existing_academics[norm_name] = {
                        "fullname": r["name"],
                        "siia_url": r["siia_url"],
                        "orcid": r["orcid"],
                        "scopus": r["scopus_ids"],
                        "is_snii": r["is_snii"]
                    }
        print(f"   ✅ Neo4j: {len(existing_academics)} académicos de la UNAM cargados en cache (búsqueda flexible).")
    except Exception as e:
        print(f"   ⚠️  Neo4j no disponible ({e.__class__.__name__}). Usando solo cache JSON.")
        graph_store = None

    # 4. Cargar nombres del padrón SNII master para verificar is_snii cuando el
    #    archivo de entrada es una lista simple (sin columnas SNII propias).
    snii_master_norms = set()
    try:
        _snii_audit = os.path.join(_ROOT, 'data', 'snii_llm_verified_matches.json')
        if os.path.exists(_snii_audit):
            with open(_snii_audit, 'r', encoding='utf-8') as _f:
                _audit_data = json.load(_f)
            for _r in _audit_data:
                _n = _r.get('academic_name') or _r.get('name')
                if _n:
                    snii_master_norms.add(normalizar_palabras_nombre(_n))
            print(f"   📋 Padrón SNII master: {len(snii_master_norms)} nombres cargados para validación.")
        else:
            # Fallback: leer directo del Excel master (más lento)
            if os.path.exists(SNII_PATH):
                _df_snii = pd.read_excel(SNII_PATH, sheet_name=SNII_SHEET, usecols=['NOMBRE DEL INVESTIGADOR'])
                for _n in _df_snii['NOMBRE DEL INVESTIGADOR'].dropna():
                    snii_master_norms.add(normalizar_palabras_nombre(str(_n)))
                print(f"   📋 Padrón SNII Excel: {len(snii_master_norms)} nombres cargados para validación.")
    except Exception as _e:
        print(f"   ⚠️  No se pudo cargar padrón SNII master: {_e}")

    
    # Asegurar directorio de salida en la misma ruta que el Excel procesado (salvo default)
    if excel_path == SNII_PATH:
        unam_data_dir = os.path.join("data", "UNAM")
    else:
        unam_data_dir = os.path.dirname(excel_path)
        if not unam_data_dir:
            unam_data_dir = "."
    os.makedirs(unam_data_dir, exist_ok=True)
    
    entities = df_unam[sub_inst_col].unique()
    
    try:
        for entity in entities:
            if pd.isna(entity): continue
            
            safe_entity = entity.replace(' ', '_').replace(',', '').replace('/', '_')
            prefix = "profesores_SNII" if has_snii_cols else "profesores"
            out_path = os.path.join(unam_data_dir, f"{prefix}_{safe_entity}.json")
            
            # Cargar progreso si existe
            profesores_data = {}
            if os.path.exists(out_path):
                with open(out_path, "r", encoding='utf-8') as f:
                    profesores_data = json.load(f)
            
            # Intentar cargar cache del JSON SNII existente en data/UNAM para optimizar
            snii_json_cache = {}
            snii_json_path = os.path.join("data", "UNAM", f"profesores_SNII_{safe_entity}.json")
            if os.path.exists(snii_json_path):
                try:
                    with open(snii_json_path, "r", encoding='utf-8') as f:
                        raw_cache = json.load(f)
                        for k, v in raw_cache.items():
                            norm_k = normalizar_palabras_nombre(k)
                            snii_json_cache[norm_k] = v
                    print(f"   📂 Cargado cache SNII JSON con {len(snii_json_cache)} perfiles para búsqueda flexible.")
                except Exception as e:
                    print(f"   ⚠️ No se pudo cargar cache SNII JSON ({e})")
            
            df_entity = df_unam[df_unam[sub_inst_col] == entity]
            lista_nombres = df_entity[name_col].values
            
            if args.limit:
                lista_nombres = lista_nombres[:args.limit]
                
            print(f"\n🏢 Entidad: {entity} ({len(lista_nombres)} investigadores)")
            
            for original_name in lista_nombres:
                p_name = limpiar_nombre(original_name)
                
                # Saltar solo si ya tiene siia_url (= scrape exitoso previo)
                # Los registros 'No encontrado' no tienen siia_url → se reintentan
                cached = profesores_data.get(p_name, {})
                if cached.get('siia_url'):
                    print(f"    📂 {p_name} ya tiene perfil SIIA. Saltando.")
                    continue
                
                p_norm = normalizar_palabras_nombre(original_name)
                
                # REVISIÓN JSON SNII PREVIO (data/UNAM/profesores_SNII_*.json)
                json_data = snii_json_cache.get(p_norm)
                if json_data and json_data.get('siia_url') and "No encont" not in str(json_data.get('siia_url')):
                    orig_n = json_data.get('original_name', p_name)
                    print(f"    📄 {p_name} coincide con '{orig_n}' en el JSON de SNIIs previo. Copiando datos...")
                    profesores_data[p_name] = {
                        'name': p_name,
                        'original_name': str(original_name),
                        'entity': entity,
                        'siia': json_data.get('siia_url') or json_data.get('siia'),
                        'siia_url': json_data.get('siia_url') or json_data.get('siia'),
                        'orcid': json_data.get('orcid', ''),
                        'scopus': json_data.get('scopus', ''),
                        'is_snii': True,
                        'areas': [] # Obviamos los temas si viene de cache
                    }
                    with open(out_path, "w", encoding='utf-8') as f:
                        json.dump(profesores_data, f, indent=4, ensure_ascii=False)
                    continue
                
                # REVISIÓN NEO4J: si el académico ya está en Neo4j y tiene siia_url válido
                neo4j_data = existing_academics.get(p_norm)
                if neo4j_data and neo4j_data.get('siia_url') and "No encont" not in str(neo4j_data.get('siia_url')):
                    db_fullname = neo4j_data.get("fullname")
                    print(f"    🧠 {p_name} coincide con '{db_fullname}' en Neo4j. Extrayendo datos...")
                    sc_ids = neo4j_data.get("scopus")
                    neo_scopus = "; ".join(sc_ids) if isinstance(sc_ids, list) else sc_ids
                    
                    profesores_data[p_name] = {
                        'name': p_name,
                        'original_name': str(original_name),
                        'entity': entity,
                        'siia': neo4j_data.get('siia_url'),
                        'siia_url': neo4j_data.get('siia_url'),
                        'orcid': neo4j_data.get('orcid', ''),
                        'scopus': neo_scopus or '',
                        'is_snii': bool(neo4j_data.get('is_snii')),
                        'areas': [] # Obviamos los temas si viene de Neo4j
                    }
                    with open(out_path, "w", encoding='utf-8') as f:
                        json.dump(profesores_data, f, indent=4, ensure_ascii=False)
                    continue
                
                # Info: si ya está en Neo4j pero sin perfil SIIA, se re-intenta de todas formas
                if p_norm in existing_academics and not cached:
                    db_fullname = existing_academics[p_norm].get("fullname")
                    print(f"    ℹ️  {p_name} coincide con '{db_fullname}' en Neo4j pero sin perfil SIIA previo válido. Buscando...")                
                print(f"  🔍 Buscando: {p_name}")
                siia_links = buscar_en_siia_con_reintentos(str(original_name), p_name)
                
                found_data = None
                if siia_links:
                    # Si recibimos links después de intentos fallidos, es un 'retry'
                    # El script buscar_en_siia_con_reintentos ya nos da los links de los hits.
                    for res in siia_links:
                        # Si hay más de un link, o si la búsqueda fue agresiva, 
                        # pasamos is_retry=True para ser más permisivos con el fuzzy match
                        is_retry = len(siia_links) > 1 or "reintentando" in str(sys.stdout) 
                        found_data = verify_and_scrape_siia(driver, p_name, res['link'], is_retry=is_retry)
                        if found_data:
                            found_data['siia'] = res['link']
                            found_data['siia_url'] = res['link']
                            found_data['original_name'] = str(original_name)
                            found_data['entity'] = entity
                            break
                
                if found_data:
                    # is_snii: True si el archivo ya lo confirma (has_snii_cols),
                    # o si está en el padrón SNII master, o si Neo4j lo marca así
                    _p_norm_snii = normalizar_palabras_nombre(found_data.get('name', p_name))
                    found_data['is_snii'] = (
                        has_snii_cols
                        or (_p_norm_snii in snii_master_norms)
                        or (bool(neo4j_data.get('is_snii')) if neo4j_data else False)
                    )
                    profesores_data[p_name] = found_data
                    orcid_str  = found_data.get('orcid') or '—'
                    scopus_str = found_data.get('scopus') or '—'
                    areas_n    = len(found_data.get('areas', []))
                    print(f"       ORCID: {orcid_str}  |  Scopus: {scopus_str}  |  Áreas: {areas_n}  |  SNII: {found_data['is_snii']}")
                else:
                    _p_norm_snii = normalizar_palabras_nombre(p_name)
                    is_snii_val = (
                        has_snii_cols
                        or (_p_norm_snii in snii_master_norms)
                        or (bool(neo4j_data.get('is_snii')) if neo4j_data else False)
                    )
                    profesores_data[p_name] = {
                        'original_name': str(original_name), 
                        'siia': 'No encontrado', 
                        'entity': entity,
                        'is_snii': is_snii_val
                    }
                    print(f"    ❌ No encontrado en SIIA: {p_name}  |  SNII: {is_snii_val}")
                
                # Guardado progresivo por entidad
                with open(out_path, "w", encoding='utf-8') as f:
                    json.dump(profesores_data, f, indent=4, ensure_ascii=False)
                
                time.sleep(2)
                
    finally:
        driver.quit()
        if graph_store:
            try: graph_store.close()
            except: pass
        print("\n✨ Proceso de scraping SNII-UNAM finalizado.")

if __name__ == "__main__":
    main()
