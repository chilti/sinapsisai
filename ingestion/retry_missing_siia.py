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
            'scopus': [],
            'orcid': '',
            'areas': []
        }

        # Scopus — igual que siia_scraper.py: lista de spans por texto, no href
        try:
            td_element = driver.find_element(By.XPATH, "/html/body/center/div/table[2]/tbody/tr[4]/td")
            outer_html_td = td_element.get_attribute('outerHTML')
            tree = html.fromstring(outer_html_td)
            sub_elements = tree.xpath('.//span')  # Más general
            for sub_element in sub_elements:
                data['scopus'].append(sub_element.text_content().strip())
        except Exception as e:
            print(f"      ❌ Error al extraer Scopus: {e}")

        # ORCID
        try:
            data['orcid'] = driver.find_element(
                By.XPATH, '//html/body/center/div/table[2]/tbody/tr[6]/td/span/a'
            ).get_attribute('href')
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
        except Exception as e:
            print(f"      ❌ Error al extraer áreas: {e}")

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

    # Identificar quiénes fallaron o necesitan scrape manual
    missing_search = []
    missing_scrape_only = []
    for k, v in data.items():
        siia_val = str(v.get('siia', '')).strip()
        scopus_val = str(v.get('scopus', '')).strip()
        orcid_val = str(v.get('orcid', '')).strip()
        
        if "No encontrado" in siia_val:
            missing_search.append(k)
        elif siia_val.startswith("http") and (not scopus_val or not orcid_val):
            missing_scrape_only.append(k)

    if not missing_search and not missing_scrape_only:
        print("🎉 ¡No hay académicos pendientes en este JSON! Todos tienen URL SIIA, Scopus y ORCID.")
        return

    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument('--log-level=3')
    
    driver = webdriver.Chrome(options=options)

    try:
        # Fase 1: Scrape directo para los que ya tienen URL manual pero les falta ORCID/Scopus
        if missing_scrape_only:
            print(f"🔗 Encontrados {len(missing_scrape_only)} académicos con URL manual SIIA pero sin Scopus/ORCID. Extrayendo directo...\n")
            for name_key in missing_scrape_only:
                entry = data[name_key]
                print(f"▶️ Scrape directo de URL manual: {entry.get('original_name', name_key)}")
                
                link = entry.get('siia')
                # Hacemos verify_and_scrape (si el fuzzy falla es porque el link manual es incorrecto)
                scraped_data = verify_and_scrape_siia(driver, name_key, link)
                if scraped_data:
                    sc = scraped_data.get('scopus', [])
                    data[name_key]['scopus'] = "; ".join(sc) if isinstance(sc, list) else sc
                    data[name_key]['orcid'] = scraped_data.get('orcid', entry.get('orcid', ''))
                    if not data[name_key].get('areas') and scraped_data.get('areas'):
                        data[name_key]['areas'] = scraped_data.get('areas')
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                time.sleep(2)

        # Fase 2: Reintento agresivo para los que tienen "No encontrado"
        if missing_search:
            print(f"\n🔎 Encontrados {len(missing_search)} académicos SIN perfil SIIA. Procediendo al reintento de búsqueda agresivo...\n")
            for name_key in missing_search:
                entry = data[name_key]
                original_name = entry.get('original_name', name_key)
                print(f"▶️ Procesando Búsqueda: {original_name}")

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
                        sc = scraped_data.get('scopus', [])
                        data[name_key]['siia'] = link
                        data[name_key]['scopus'] = "; ".join(sc) if isinstance(sc, list) else sc
                        data[name_key]['orcid'] = scraped_data.get('orcid', '')
                        data[name_key]['areas'] = scraped_data.get('areas', [])
                        found = True
                        break

                if not found:
                    print("   ❌ Se evaluaron hits alternativos pero ninguno cruzó el umbral difuso (70%).")

                # Guardar en vivo tras cada hit
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                
                time.sleep(2)

    finally:
        driver.quit()
        print("\n✅ Proceso de rescate completado. Revisa tu archivo JSON.")

if __name__ == "__main__":
    main()
