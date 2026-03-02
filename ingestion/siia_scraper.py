"""
Script para ubicar el perfil de los profesores en el SIIA y extraer áreas temáticas e identificadores.
Mismo funcionamiento que el paso 1 y 2 del notebook, pero utilizando DuckDuckGo Search (gratuito)
en lugar de SerpAPI.
"""

import os
import re
import time
import json
import unicodedata
import pandas as pd

import sys
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from lxml import html
import argparse

# Importar DB para checar existentes
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

def limpiar_nombre(nombre):
    """
    Quita prefijos DR./DRA., acentos y estandariza a mayúsculas.
    """
    if not isinstance(nombre, str):
        return ""
    nombre_sin_prefijo = re.sub(r'^(DR\.|DRA\.)\s*', '', nombre, flags=re.IGNORECASE).strip()
    nombre_normalizado = unicodedata.normalize('NFD', nombre_sin_prefijo)
    nombre_sin_acentos = ''.join(
        c for c in nombre_normalizado
        if unicodedata.category(c) != 'Mn'
    )
    return nombre_sin_acentos.upper()


def buscar_en_siia_interno(original_name, cleaned_name):
    """
    Realiza una búsqueda al endpoint /c/personal.php del sitio propio de SIIA.
    """
    try:
        if ',' in original_name:
            surnames, names = original_name.split(',', 1)
        elif ',' in cleaned_name:
            surnames, names = cleaned_name.split(',', 1)
        else:
            parts = cleaned_name.split()
            if len(parts) >= 3:
                surnames = " ".join(parts[:2])
                names = " ".join(parts[2:])
            else:
                surnames = cleaned_name
                names = ""
                
        surnames = re.sub(r'^(DR\.|DRA\.)\s*', '', surnames, flags=re.IGNORECASE).strip()
        parts = surnames.split()
        if len(parts) >= 2:
            ap_pat = parts[0]
            ap_mat = " ".join(parts[1:])
        else:
            ap_pat = surnames
            ap_mat = ""
            
        data = {
            'apellido_paterno': ap_pat.strip(),
            'apellido_materno': ap_mat.strip(),
            'nombre': names.strip()
        }
        
        r = requests.post("https://web.siia.unam.mx/siia-publico/c/personal.php", data=data, timeout=10)
        links = re.findall(r'busqueda_individual\.php\?id=\d+', r.text)
        links = list(set(links))
        return [{"link": "https://web.siia.unam.mx/siia-publico/c/" + lnk} for lnk in links]
    except Exception as e:
        print(f"    ⚠️ Error en búsqueda interna para '{cleaned_name}': {e}")
        return []


def verify_and_scrape_siia(driver, name_to_verify, url):
    """
    Navega a una URL del SIIA, cierra el MODAL HTML si aparece, 
    verifica el nombre extraído vs el buscado y extrae ORCID, Scopus y Áreas.
    """
    try:
        driver.get(url)

        # 1. GESTIÓN DEL MODAL (HTML / BOOTSTRAP)
        try:
            boton_aceptar = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@class='modal-footer']//button[contains(text(), 'Aceptar')]"))
            )
            print("    ⚠️ Modal detectado. Intentando cerrar...")
            boton_aceptar.click()
            time.sleep(1) 
        except TimeoutException:
            pass
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", boton_aceptar)
            time.sleep(1)

        # 2. EXTRAER NOMBRE
        try:
            element_h1 = WebDriverWait(driver, 5).until(
                EC.visibility_of_element_located((By.XPATH, '/html/body/center/h1'))
            )
            scraped_name = element_h1.text
        except TimeoutException:
            print(f"    ❌ No se encontró el nombre (H1). ¿La página cargó bien?")
            return None

        # 3. VERIFICAR EL NOMBRE (Fuzzy Matching > 90)
        if fuzz.token_set_ratio(name_to_verify, scraped_name) < 90:
            print(f"    -> No coincide: buscado '{name_to_verify}' vs hallado '{scraped_name}'")
            return None 

        print(f"    ✅ Coincidencia encontrada para '{name_to_verify}' en la página.")

        # 4. EXTRAER DATOS
        data = {
            'name': scraped_name,
            'scopus': [],
            'orcid': '',
            'areas': []
        }

        # Búsqueda robusta por texto en tablas
        try:
            rows = driver.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 2:
                    label = cells[0].text.upper()
                    if "SCOPUS" in label:
                        # Extraer links de scopus o texto
                        links = cells[1].find_elements(By.TAG_NAME, "a")
                        if links:
                            for l in links:
                                href = l.get_attribute("href")
                                if href and "authorId=" in href:
                                    data['scopus'].append(href)
                        # Si no hay links, buscar span o texto
                        spans = cells[1].find_elements(By.TAG_NAME, "span")
                        for s in spans:
                            txt = s.text.strip()
                            if txt and txt not in data['scopus']:
                                data['scopus'].append(txt)
                    elif "ORCID" in label:
                        try:
                            orcid_a = cells[1].find_element(By.TAG_NAME, "a")
                            data['orcid'] = orcid_a.get_attribute("href")
                        except:
                            data['orcid'] = cells[1].text.strip()
        except Exception as e:
            print(f"    ⚠️ Error en extracción robusta: {e}")

        # Fallback a XPaths originales si falló lo anterior
        if not data['scopus']:
            try:
                td_element = driver.find_element(By.XPATH, "/html/body/center/div/table[2]/tbody/tr[4]/td")
                outer_html_td = td_element.get_attribute('outerHTML')
                tree = html.fromstring(outer_html_td)
                sub_elements = tree.xpath('.//span') # Más general
                for sub_element in sub_elements:
                   data['scopus'].append(sub_element.text_content().strip())
            except Exception:
                pass

        # Orcid
        try:
            data['orcid'] = driver.find_element(By.XPATH, '//html/body/center/div/table[2]/tbody/tr[6]/td/span/a').get_attribute('href')
        except NoSuchElementException:
            pass

        # Áreas Temáticas
        try:
            td_element = driver.find_element(By.XPATH, "/html/body/center/div/table[3]/tbody/tr[2]/td")
            outer_html_td = td_element.get_attribute('outerHTML')
            tree = html.fromstring(outer_html_td)
            sub_elements = tree.xpath('./span')
            for sub_element in sub_elements:
                area_text = sub_element.text_content().strip()
                if area_text:
                    data['areas'].append(area_text)
        except Exception:
            pass 

        return data

    except Exception as e:
        print(f"    ❌ Error general en {url}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Scraper SIIA para profesores por Entidad UNAM")
    parser.add_argument("--file", type=str, required=True, help="Ruta al archivo Excel con profesores")
    parser.add_argument("--entity", type=str, required=True, help="Nombre de la Entidad (ej. 'Centro de Ciencias de la Complejidad')")
    parser.add_argument("--force", action="store_true", help="Forzar la búsqueda aunque ya existan en Neo4j")
    args = parser.parse_args()

    excel_path = args.file
    entity_name = args.entity
    # Sanitizar el nombre para el archivo (remover espacios)
    safe_name = entity_name.replace(' ', '_').replace(',', '')
    out_json_path = os.path.join(os.path.dirname(__file__), f"profesores_{safe_name}.json")
    
    # 1. Cargar Profesores
    if not os.path.exists(excel_path):
        print(f"❌ No se encontró el archivo de excel en {excel_path}.")
        return

    try:
        df_profesores = pd.read_excel(excel_path)
        # Asumimos que los nombres puden venir en cualquira, la col "Unnamed: 10" fue para ciencias, probaremos general o buscar
        # Buscamos la columna con más strings similares a nombres o le pedimos la columna índice 10 por legacy
        col_idx = 10 if df_profesores.shape[1] > 10 else 0
        lista_nombres = df_profesores.iloc[:, col_idx].dropna().values
    except Exception as e:
        print(f"❌ Error leyendo excel: {e}")
        return

    print(f"📋 Encontrados {len(lista_nombres)} posibles profesores para procesar (Columna {col_idx}).")

    # 1.5 Cargar la lista actual de Académicos en Neo4j
    print("⏳ Consultando académicos existentes en Neo4j para evitar duplicados...")
    graph_store = Neo4jGraphStore()
    nombres_existentes = []
    try:
        with graph_store.driver.session() as session:
            res = session.run("MATCH (a:Academic) RETURN a.name AS name")
            nombres_existentes = [record["name"] for record in res]
    except Exception as e:
        print(f"Aviso: No se pudo conectar a Neo4j para cache ({e})")
    
    # 2. Configurar Selenium Headless
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument('--log-level=3') # silenciar logs innecesarios
    
    print("⏳ Iniciando WebDriver de Chrome...")
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e:
        print(f"❌ Falló inicio de ChromeDriver: {e}")
        return

    profesores_data = {}

    try:
        for original_name in lista_nombres:
            profesor_name = limpiar_nombre(original_name)
            if not profesor_name:
                continue
                
            print(f"\n🔍 Buscando a: {profesor_name} (Original: {original_name})")
            profesores_data[profesor_name] = {'original_name': str(original_name), 'entity': entity_name}

            # LÓGICA FUZZY MATCHING INTERNA (Saltar si existee en Neo4j, a menos que se use --force)
            is_duplicate = False
            if not args.force:
                for neo_name in nombres_existentes:
                    if fuzz.token_sort_ratio(profesor_name, limpiar_nombre(neo_name)) >= 90:
                        print(f"    🌟 Encontrado en Base de Datos previa como '{neo_name}'! Omite Scraper.")
                        profesores_data[profesor_name]['already_in_db'] = True
                        profesores_data[profesor_name]['mapped_name'] = neo_name
                        is_duplicate = True
                        break
            
            if is_duplicate and not args.force:
                continue
                
            profesores_data[profesor_name]['already_in_db'] = False

            # Llamada al buscador (Búsqueda interna SIIA)
            siia_results = buscar_en_siia_interno(str(original_name), profesor_name)

            if not siia_results:
                print("    -> No se encontraron resultados en el buscador.")
                profesores_data[profesor_name]['siia'] = 'No encontrado'
                time.sleep(2) # Pausa por cortesía al buscador
                continue

            found = False
            for res in siia_results:
                link = res.get('link')
                if not link:
                    continue
                    
                print(f"    🌐 Revisando link: {link}")
                scraped_data = verify_and_scrape_siia(driver, profesor_name, link)
                
                if scraped_data:
                    # Guardamos la data
                    profesores_data[profesor_name]['siia'] = link
                    # Unificar scopus como string separado por ;
                    scopus_data = scraped_data.get('scopus', [])
                    if isinstance(scopus_data, list):
                        profesores_data[profesor_name]['scopus'] = "; ".join(scopus_data)
                    else:
                        profesores_data[profesor_name]['scopus'] = scopus_data
                    profesores_data[profesor_name]['orcid'] = scraped_data.get('orcid', '')
                    profesores_data[profesor_name]['areas'] = scraped_data.get('areas', [])
                    found = True
                    break # Salimos del loop de resultados y vamos al próximo profesor
            
            if not found:
                profesores_data[profesor_name]['siia'] = 'No encontrado en los hits iniciales'

            # Pausa natural para no abrumar al servidor ni al buscador
            time.sleep(3)
            
            # Guardado progresivo: por si falla en medio
            with open(out_json_path, "w", encoding='utf-8') as json_file:
                json.dump(profesores_data, json_file, indent=4, ensure_ascii=False)

    finally:
        driver.quit()
        print(f"\n🎉 Proceso completado. Datos guardados en '{out_json_path}'")

if __name__ == "__main__":
    main()
