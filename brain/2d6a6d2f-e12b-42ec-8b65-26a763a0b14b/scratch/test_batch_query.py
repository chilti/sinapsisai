import os
import time
import json
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

def test_batch():
    client = clickhouse_connect.get_client(host=CH_HOST, port=CH_PORT, username=CH_USER, password=CH_PASSWORD)
    
    # 10 nombres de ejemplo (incluyendo Nicandro)
    names = [
        {"k1": "CRUZ", "k2": "NICANDRO", "name": "CRUZ RAMIREZ, NICANDRO"},
        {"k1": "GARCIA", "k2": "JUAN", "name": "GARCIA, JUAN"},
        {"k1": "LOPEZ", "k2": "MARIA", "name": "LOPEZ, MARIA"},
        {"k1": "HERNANDEZ", "k2": "JOSE", "name": "HERNANDEZ, JOSE"},
        {"k1": "MARTINEZ", "k2": "ANA", "name": "MARTINEZ, ANA"},
        {"k1": "RODRIGUEZ", "k2": "CARLOS", "name": "RODRIGUEZ, CARLOS"},
        {"k1": "GONZALEZ", "k2": "LUIS", "name": "GONZALEZ, LUIS"},
        {"k1": "PEREZ", "k2": "ELENA", "name": "PEREZ, ELENA"},
        {"k1": "SANCHEZ", "k2": "PEDRO", "name": "SANCHEZ, PEDRO"},
        {"k1": "RAMIREZ", "k2": "LAURA", "name": "RAMIREZ, LAURA"}
    ]
    
    clauses = []
    all_k1 = []
    for info in names:
        r1 = get_accent_insensitive_regex(info['k1'])
        r2 = get_accent_insensitive_regex(info['k2'])
        clauses.append(f"(match(display_name, '{r1}') AND match(display_name, '{r2}'))")
        all_k1.append(info['k1'].lower())
    
    all_k1 = list(set(all_k1))
    pre_filter = f"multiSearchAnyCaseInsensitive(display_name, {all_k1})"
    where_clause = " OR ".join(clauses)
    
    query = f"""
    SELECT count()
    FROM {CH_DB}.authors_seed_mexico
    WHERE ({pre_filter}) AND ({where_clause})
    """
    
    print(f"--- Test Batch: {len(names)} investigadores ---")
    start = time.time()
    try:
        res = client.query(query).result_rows[0][0]
        print(f"Resultados totales: {res} | Tiempo: {time.time() - start:.2f}s")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_batch()
