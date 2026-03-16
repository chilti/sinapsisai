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

def buscar_en_siia_interno(original_name, cleaned_name):
    try:
        if ',' in original_name:
            surnames, names = original_name.split(',', 1)
        else:
            parts = cleaned_name.split()
            if len(parts) >= 3:
                surnames = " ".join(parts[:2])
                names = " ".join(parts[2:])
            else:
                surnames = cleaned_name
                names = ""
                
        parts = surnames.split()
        ap_pat = parts[0] if len(parts) >= 1 else ""
        ap_mat = " ".join(parts[1:]) if len(parts) >= 2 else ""
            
        data = {
            'apellido_paterno': ap_pat.strip(),
            'apellido_materno': ap_mat.strip(),
            'nombre': names.strip()
        }
        
        r = requests.post("https://web.siia.unam.mx/siia-publico/c/personal.php", data=data, timeout=10)
        links = re.findall(r'busqueda_individual\.php\?id=\d+', r.text)
        return [{"link": "https://web.siia.unam.mx/siia-publico/c/" + lnk} for lnk in set(links)]
    except Exception as e:
        print(f"    ⚠️ Error en búsqueda interna para '{cleaned_name}': {e}")
        return []

def verify_and_scrape_siia(driver, name_to_verify, url):
    try:
        try:
            driver.get(url)
        except (TimeoutException, WebDriverException):
            print(f"    ⏱️ Timeout o error de carga en {url}. Saltando.")
            return None

        # Cerrar Modal si aparece
        try:
            boton_aceptar = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@class='modal-footer']//button[contains(text(), 'Aceptar')]"))
            )
            boton_aceptar.click()
            time.sleep(1)
        except:
            pass

        # Extraer y verificar nombre
        try:
            scraped_name = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.XPATH, '/html/body/center/h1'))
            ).text
        except:
            return None

        if fuzz.token_set_ratio(name_to_verify, scraped_name) < 90:
            return None 

        print(f"    ✅ Match: {scraped_name}")

        data = {'name': scraped_name, 'scopus': [], 'orcid': '', 'areas': []}
        
        # Scopus
        try:
            td_scopus = driver.find_element(By.XPATH, "/html/body/center/div/table[2]/tbody/tr[4]/td")
            tree = html.fromstring(td_scopus.get_attribute('outerHTML'))
            data['scopus'] = [s.text_content().strip() for s in tree.xpath('.//span')]
        except: pass

        # ORCID
        try:
            data['orcid'] = driver.find_element(By.XPATH, '//html/body/center/div/table[2]/tbody/tr[6]/td/span/a').get_attribute('href')
        except: pass

        # Áreas
        try:
            td_areas = driver.find_element(By.XPATH, "/html/body/center/div/table[3]/tbody/tr[2]/td")
            tree = html.fromstring(td_areas.get_attribute('outerHTML'))
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
    
    entities = df_unam[sub_inst_col].unique()
    
    try:
        for entity in entities:
            if pd.isna(entity): continue
            
            safe_entity = entity.replace(' ', '_').replace(',', '').replace('/', '_')
            out_path = os.path.join("data", f"profesores_SNII_{safe_entity}.json")
            
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
                siia_links = buscar_en_siia_interno(str(original_name), p_name)
                
                found_data = None
                for res in siia_links:
                    found_data = verify_and_scrape_siia(driver, p_name, res['link'])
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
