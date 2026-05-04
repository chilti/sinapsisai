import clickhouse_connect
import time
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

def finalize_mexico_materialization():
    try:
        client = clickhouse_connect.get_client(
            host='10.90.0.87',
            port=8124,
            username='rag_user',
            password='$B3tt3r-R4g-3veR-d0N3++'
        )
        
        print("Añadiendo columnas faltantes a rag.works_seed_mexico para compatibilidad con Dashboard v2...")
        
        # 1. AGREGAR TODAS LAS COLUMNAS REQUERIDAS POR LA QUERY
        columns_to_add = [
            "ADD COLUMN IF NOT EXISTS referenced_works_count UInt32",
            "ADD COLUMN IF NOT EXISTS keywords Array(String)",
            "ADD COLUMN IF NOT EXISTS sdgs Array(String)",
            "ADD COLUMN IF NOT EXISTS author_names Array(String)",
            "ADD COLUMN IF NOT EXISTS all_country_codes Array(String)",
            "ADD COLUMN IF NOT EXISTS journal_is_in_doaj UInt8",
            "ADD COLUMN IF NOT EXISTS journal_is_core UInt8",
            "ADD COLUMN IF NOT EXISTS any_repository_has_fulltext UInt8",
            "ADD COLUMN IF NOT EXISTS type String"
        ]
        
        for col_cmd in columns_to_add:
            print(f"  -> {col_cmd}")
            try:
                client.command(f"ALTER TABLE rag.works_seed_mexico {col_cmd}")
            except Exception as e:
                print(f"     (Nota: {e})")
            
        # 2. POBLAR DATOS FALTANTES
        print("Poblando nuevos campos desde raw_json...")
        
        update_query = """
        ALTER TABLE rag.works_seed_mexico UPDATE
            referenced_works_count = JSONExtractUInt(raw_json, 'referenced_works_count'),
            keywords = arrayMap(x -> JSONExtractString(x, 'display_name'), JSONExtractArrayRaw(raw_json, 'keywords')),
            sdgs = arrayMap(x -> JSONExtractString(x, 'display_name'), JSONExtractArrayRaw(raw_json, 'sustainable_development_goals')),
            author_names = arrayMap(x -> JSONExtractString(x, 'author', 'display_name'), JSONExtractArrayRaw(raw_json, 'authorships')),
            all_country_codes = arrayMap(x -> JSONExtractString(x), JSONExtractArrayRaw(raw_json, 'production_countries')),
            journal_is_in_doaj = JSONExtractBool(raw_json, 'is_oa', 'is_doaj_indexed'),
            journal_is_core = JSONExtractBool(raw_json, 'is_oa', 'is_doaj_journal'),
            any_repository_has_fulltext = JSONExtractBool(raw_json, 'is_oa', 'has_repository_fulltext'),
            type = JSONExtractString(raw_json, 'type')
        WHERE 1=1
        """
        
        client.command(update_query)
        print("Mutacion de actualizacion lanzada. Monitoreando...")
        
        while True:
            res = client.query("SELECT is_done FROM system.mutations WHERE table = 'works_seed_mexico' AND is_done = 0")
            if not res.result_rows:
                print("Finalizado: La tabla rag.works_seed_mexico ya tiene todas las columnas y datos necesarios.")
                break
            print("... procesando mutacion ...")
            time.sleep(10)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    finalize_mexico_materialization()
