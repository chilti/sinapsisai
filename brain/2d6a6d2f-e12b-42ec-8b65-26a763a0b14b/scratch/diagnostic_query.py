import os
import time
from dotenv import load_dotenv
import clickhouse_connect

load_dotenv()

CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASSWORD = os.getenv("CH_PASSWORD")
CH_DB = os.getenv("CH_DATABASE", "rag")

def get_accent_insensitive_regex(text: str) -> str:
    vowel_map = {'a': '[aáàâä]', 'e': '[eéèêë]', 'i': '[iíìîï]', 'o': '[oóòôö]', 'u': '[uúùûü]'}
    regex = ""
    for char in text.lower():
        regex += vowel_map.get(char, char)
    return f"(?i){regex}"

def test_query():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    
    name = "CRUZ RAMIREZ, NICANDRO"
    k1 = "CRUZ"
    k2 = "NICANDRO"
    
    r1 = get_accent_insensitive_regex(k1)
    r2 = get_accent_insensitive_regex(k2)
    
    # Intento 1: Sin pre-filtro (como estaba antes)
    print(f"--- Test 1: match() puro para {name} ---")
    query1 = f"SELECT count() FROM {CH_DB}.authors_seed_mexico WHERE (match(display_name, '{r1}') AND match(display_name, '{r2}'))"
    start = time.time()
    try:
        res1 = client.query(query1).result_rows[0][0]
        print(f"Resultados: {res1} | Tiempo: {time.time() - start:.2f}s")
    except Exception as e:
        print(f"Error Test 1: {e}")

    # Intento 2: Con multiSearchAny (nueva optimización)
    print(f"\n--- Test 2: multiSearchAny + match() ---")
    pre_filter = f"multiSearchAnyCaseInsensitive(display_name, ['{k1.lower()}', '{k2.lower()}'])"
    query2 = f"SELECT count() FROM {CH_DB}.authors_seed_mexico WHERE ({pre_filter}) AND (match(display_name, '{r1}') AND match(display_name, '{r2}'))"
    start = time.time()
    try:
        res2 = client.query(query2).result_rows[0][0]
        print(f"Resultados: {res2} | Tiempo: {time.time() - start:.2f}s")
    except Exception as e:
        print(f"Error Test 2: {e}")

    # Intento 3: Con ILIKE (Alternativa)
    print(f"\n--- Test 3: ILIKE puro (sin acentos) ---")
    query3 = f"SELECT count() FROM {CH_DB}.authors_seed_mexico WHERE display_name ILIKE '%{k1}%' AND display_name ILIKE '%{k2}%'"
    start = time.time()
    try:
        res3 = client.query(query3).result_rows[0][0]
        print(f"Resultados: {res3} | Tiempo: {time.time() - start:.2f}s")
    except Exception as e:
        print(f"Error Test 3: {e}")

if __name__ == "__main__":
    test_query()
