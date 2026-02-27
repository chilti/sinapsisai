import os
import json
import time
import re
import requests
from  fuzzywuzzy import fuzz
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException
import lxml.html as html

def buscar_en_siia_con_reintentos(ap_pat, ap_mat, nombre):
    """
    Intenta buscar progresivamente eliminando el apellido materno si fracasa la búsqueda estricta.
    """
    base_data = {
        'apellido_paterno': ap_pat,
        'apellido_materno': ap_mat,
        'nombre': nombre
    }
    
    url = "https://web.siia.unam.mx/siia-publico/c/personal.php"
    links = []
    
    # Intento 1: Estricto (con materno si existe)
    try:
        r = requests.post(url, data=base_data, timeout=10)
        hits = re.findall(r'busqueda_individual\.php\?id=\d+', r.text)
        links = list(set(hits))
    except Exception as e:
        print(f"Error HTTP request: {e}")
        
    # Intento 2: Sin apellido materno (suele omitirse en bases de datos)
    if not links and ap_mat:
        print(f"      [!] Búsqueda estricta vacía. Reintentando sin materno para: {ap_pat} {nombre}")
        fallback_data = base_data.copy()
        fallback_data['apellido_materno'] = ""
        try:
            r = requests.post(url, data=fallback_data, timeout=10)
            hits = re.findall(r'busqueda_individual\.php\?id=\d+', r.text)
            links = list(set(hits))
        except Exception:
            pass
            
    # Intento 3: Solo Apellido Paterno (Extremo)
    if not links:
        print(f"      [!] Reintentando ÚNICAMENTE con paterno: {ap_pat}")
        min_data = {
            'apellido_paterno': ap_pat,
            'apellido_materno': '',
            'nombre': ''
        }
        try:
            r = requests.post(url, data=min_data, timeout=10)
            hits = re.findall(r'busqueda_individual\.php\?id=\d+', r.text)
            links = list(set(hits))
        except Exception:
            pass

    return [{"link": "https://web.siia.unam.mx/siia-publico/c/" + lnk} for lnk in links]

def verify_and_scrape_siia(driver, name_to_verify, url):
    try:
        driver.get(url)

        # Modal HTML
        try:
            boton_aceptar = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@class='modal-footer']//button[contains(text(), 'Aceptar')]"))
            )
            boton_aceptar.click()
            time.sleep(1) 
        except Exception:
            pass

        # Validamos H1
        element_h1 = WebDriverWait(driver, 5).until(
            EC.visibility_of_element_located((By.XPATH, '/html/body/center/h1'))
        )
        scraped_name = element_h1.text

        # Fuzzy matching más permisivo para reintentos (70%)
        match_score = fuzz.token_set_ratio(name_to_verify, scraped_name)
        if match_score < 70:
            print(f"      ❌ Descartado por fuzzy match ({match_score}%): Buscado '{name_to_verify}' vs Fallado '{scraped_name}'")
            return None 

        print(f"      ✅ Match válido ({match_score}%): '{scraped_name}'")

        data = {
            'name': scraped_name,
            'scopus': '',
            'orcid': '',
            'areas': []
        }

        # Scopus
        try:
            data['scopus'] = driver.find_element(By.XPATH, '/html/body/center/div/table[2]/tbody/tr[4]/td/span/a').get_attribute('href')
        except NoSuchElementException:
            try:
                td_element = driver.find_element(By.XPATH, "/html/body/center/div/table[2]/tbody/tr[4]/td")
                outer_html_td = td_element.get_attribute('outerHTML')
                tree = html.fromstring(outer_html_td)
                sub_elements = tree.xpath('./span')
                scopus_ids = [s.text_content().strip() for s in sub_elements if s.text_content().strip()]
                data['scopus'] = scopus_ids[0] if scopus_ids else ''
            except Exception:
                pass

        # Orcid
        try:
            data['orcid'] = driver.find_element(By.XPATH, '/html/body/center/div/table[2]/tbody/tr[6]/td/span/a').get_attribute('href')
        except NoSuchElementException:
            pass

        return data
    except Exception as e:
        print(f"      ❌ Error scrapeando data en SIIA: {e}")
        return None

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, required=True, help="Ruta al JSON generado por siia_scraper")
    args = parser.parse_args()

    json_path = args.file
    if not os.path.exists(json_path):
        print(f"No se encontró el JSON: {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Identificar quiénes fallaron en el primer pase
    missing = []
    for k, v in data.items():
        if "No encontrado" in str(v.get('siia', '')):
            missing.append(k)

    if not missing:
        print("🎉 ¡No hay académicos perdidos en este JSON! Todos tienen URL SIIA.")
        return

    print(f"🔎 Encontrados {len(missing)} académicos sin perfil SIIA. Procediendo al reintento agresivo...\n")

    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument('--log-level=3')
    
    driver = webdriver.Chrome(options=options)

    try:
        for name_key in missing:
            entry = data[name_key]
            original_name = entry.get('original_name', name_key)
            print(f"▶️ Procesando: {original_name}")

            # Parsear nombres
            ap_pat, ap_mat, nombre_pila = "", "", ""
            if ',' in original_name:
                apellidos, nombres = original_name.split(',', 1)
                aps = apellidos.split()
                ap_pat = aps[0] if len(aps) >= 1 else ""
                ap_mat = " ".join(aps[1:]) if len(aps) >= 2 else ""
                nombre_pila = nombres.strip()
            else:
                parts = original_name.split()
                if len(parts) >= 3:
                    ap_pat, ap_mat = parts[0], parts[1]
                    nombre_pila = " ".join(parts[2:])
                elif len(parts) == 2:
                    ap_pat, nombre_pila = parts[0], parts[1]
                else:
                    ap_pat = original_name

            # Quitar títulos
            ap_pat = re.sub(r'^(DR\.|DRA\.)\s*', '', ap_pat, flags=re.IGNORECASE).strip()

            siia_results = buscar_en_siia_con_reintentos(ap_pat, ap_mat, nombre_pila)
            
            if not siia_results:
                print("   ❌ Ni siquiera la búsqueda agresiva entregó hits.")
                continue

            found = False
            for res in siia_results:
                link = res.get('link')
                scraped_data = verify_and_scrape_siia(driver, name_key, link)
                if scraped_data:
                    data[name_key]['siia'] = link
                    data[name_key]['scopus'] = scraped_data.get('scopus', '')
                    data[name_key]['orcid'] = scraped_data.get('orcid', '')
                    data[name_key]['areas'] = scraped_data.get('areas', [])
                    found = True
                    break

            if not found:
                print("   ❌ Se evaluaron hits alternativos pero ninguno cruzó el umbral difuso (70%).")

            # Guardar en vivo tras cada hit para no perder nada si se corta
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            time.sleep(2)

    finally:
        driver.quit()
        print("\n✅ Proceso de rescate completado. Revisa tu archivo JSON.")

if __name__ == "__main__":
    main()
