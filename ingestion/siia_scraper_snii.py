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
from SNII.match_snii_orcid import SNII_PATH

# --- Funciones de Utilidad (Replicadas de siia_scraper.py) ---

def limpiar_nombre(nombre):
    if not isinstance(nombre, str):
        return ""
    nombre_sin_prefijo = re.sub(r'^(DR\.|DRA\.)\s*', '', nombre, flags=re.IGNORECASE).strip()
    nombre_normalizado = unicodedata.normalize('NFD', nombre_sin_prefijo)
    return ''.join(c for c in nombre_normalizado if unicodedata.category(c) != 'Mn').upper()

def buscar_en_siia_con_reintentos(original_name, cleaned_name):
    """
    Intenta buscar progresivamente eliminando el apellido materno si fracasa la búsqueda estricta.
    Identifica apellidos y nombres a partir de la coma si existe.
    """
    ap_pat, ap_mat, nombre_pila = "", "", ""
    if ',' in original_name:
        apellidos, nombres = original_name.split(',', 1)
        aps = apellidos.split()
        ap_pat = aps[0] if len(aps) >= 1 else ""
        ap_mat = " ".join(aps[1:]) if len(aps) >= 2 else ""
        nombre_pila = nombres.strip()
    else:
        parts = cleaned_name.split()
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
    parser.add_argument("--subdependency", type=str, help="Filtrar por una subdependencia específica")
    parser.add_argument("--limit", type=int, help="Límite de profesores por entidad para pruebas")
    args = parser.parse_args()

    # 1. Cargar y Filtrar Excel
    print(f"📋 Cargando SNII desde {SNII_PATH}...")
    df = pd.read_excel(SNII_PATH)
    
    inst_col = 'INSTITUCIÓN DE ACREDITACIÓN'
    sub_inst_col = 'SUBDEPENDENCIA DE ACREDITACIÓN'
    name_col = 'NOMBRE DEL INVESTIGADOR'
    
    # Filtrar UNAM
    df_unam = df[df[inst_col] == "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)"].copy()
    print(f"🎯 Investigadores UNAM encontrados: {len(df_unam)}")
    
    if args.subdependency:
        df_unam = df_unam[df_unam[sub_inst_col].str.contains(args.subdependency, case=False, na=False)]
        print(f"🔎 Filtrando por subdependencia '{args.subdependency}': {len(df_unam)} registros.")

    # 2. Configurar Selenium
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(40)

    # 3. Cache de Neo4j
    graph_store = Neo4jGraphStore()
    existing_academics = []
    try:
        with graph_store.driver.session() as session:
            res = session.run("MATCH (a:Academic) RETURN a.name AS name")
            existing_academics = {limpiar_nombre(r["name"]) for r in res}
    except: pass
    
    # Asegurar directorio de salida
    unam_data_dir = os.path.join("data", "UNAM")
    os.makedirs(unam_data_dir, exist_ok=True)
    
    entities = df_unam[sub_inst_col].unique()
    
    try:
        for entity in entities:
            if pd.isna(entity): continue
            
            safe_entity = entity.replace(' ', '_').replace(',', '').replace('/', '_')
            out_path = os.path.join(unam_data_dir, f"profesores_SNII_{safe_entity}.json")
            
            # Cargar progreso si existe
            profesores_data = {}
            if os.path.exists(out_path):
                with open(out_path, "r", encoding='utf-8') as f:
                    profesores_data = json.load(f)
            
            df_entity = df_unam[df_unam[sub_inst_col] == entity]
            lista_nombres = df_entity[name_col].values
            
            if args.limit:
                lista_nombres = lista_nombres[:args.limit]
                
            print(f"\n🏢 Entidad: {entity} ({len(lista_nombres)} investigadores)")
            
            for original_name in lista_nombres:
                p_name = limpiar_nombre(original_name)
                if p_name in profesores_data and profesores_data[p_name].get('siia') != 'No encontrado':
                    continue
                
                # Evitar duplicados de Neo4j (SIIA ya procesados)
                if p_name in existing_academics:
                    print(f"    🌟 {p_name} ya existe en Neo4j. Saltando.")
                    continue
                
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
                            found_data['siia_url'] = res['link']
                            found_data['original_name'] = str(original_name)
                            found_data['entity'] = entity
                            break
                
                if found_data:
                    profesores_data[p_name] = found_data
                else:
                    profesores_data[p_name] = {'original_name': str(original_name), 'siia': 'No encontrado', 'entity': entity}
                
                # Guardado progresivo por entidad
                with open(out_path, "w", encoding='utf-8') as f:
                    json.dump(profesores_data, f, indent=4, ensure_ascii=False)
                
                time.sleep(2)
                
    finally:
        driver.quit()
        graph_store.close()
        print("\n✨ Proceso de scraping SNII-UNAM finalizado.")

if __name__ == "__main__":
    main()
