import clickhouse_connect
import time
import sys

# Forzar UTF-8 para evitar errores de charmap en Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

def materialize_metrics():
    try:
        client = clickhouse_connect.get_client(
            host='10.90.0.87',
            port=8124,
            username='rag_user',
            password='$B3tt3r-R4g-3veR-d0N3++'
        )
        
        print("Iniciando materializacion de metricas en rag.works_seed_mexico...")
        
        # 1. AGREGAR COLUMNAS (Si no existen)
        columns_to_add = [
            "ADD COLUMN IF NOT EXISTS apc_paid_usd Float64",
            "ADD COLUMN IF NOT EXISTS apc_list_usd Float64",
            "ADD COLUMN IF NOT EXISTS counts_by_year String",
            "ADD COLUMN IF NOT EXISTS language String",
            "ADD COLUMN IF NOT EXISTS is_doaj_indexed UInt8",
            "ADD COLUMN IF NOT EXISTS is_doaj_journal UInt8",
            "ADD COLUMN IF NOT EXISTS is_core_journal UInt8",
            "ADD COLUMN IF NOT EXISTS is_retracted UInt8",
            "ADD COLUMN IF NOT EXISTS has_repository_fulltext UInt8",
            "ADD COLUMN IF NOT EXISTS license String"
        ]
        
        for col_cmd in columns_to_add:
            print(f"  -> Ejecutando: {col_cmd}")
            client.command(f"ALTER TABLE rag.works_seed_mexico {col_cmd}")
            
        print("Columnas creadas exitosamente.")
        
        # 2. POBLAR DATOS (UPDATE)
        print("Poblando datos desde raw_json (esto puede tardar unos minutos)...")
        
        update_query = """
        ALTER TABLE rag.works_seed_mexico UPDATE
            apc_paid_usd = JSONExtractFloat(raw_json, 'apc_paid', 'value'),
            apc_list_usd = JSONExtractFloat(raw_json, 'apc_list', 'value'),
            counts_by_year = JSONExtractRaw(raw_json, 'counts_by_year'),
            language = JSONExtractString(raw_json, 'language'),
            is_doaj_indexed = JSONExtractBool(raw_json, 'is_oa', 'is_doaj_indexed'),
            is_doaj_journal = JSONExtractBool(raw_json, 'is_oa', 'is_doaj_journal'),
            is_core_journal = JSONExtractBool(raw_json, 'is_oa', 'is_core_journal'),
            is_retracted = JSONExtractBool(raw_json, 'is_retracted'),
            has_repository_fulltext = JSONExtractBool(raw_json, 'is_oa', 'has_repository_fulltext'),
            license = JSONExtractString(raw_json, 'primary_location', 'license')
        WHERE 1=1
        """
        
        client.command(update_query)
        print("Mutacion de actualizacion lanzada.")
        
        # 3. MONITOREO
        print("Monitoreando progreso de la mutacion...")
        while True:
            # Filtrar por is_done=0 para ver las activas
            res = client.query("SELECT is_done, latest_fail_reason FROM system.mutations WHERE table = 'works_seed_mexico' AND is_done = 0")
            if not res.result_rows:
                # Verificar si alguna termino con error
                res_err = client.query("SELECT latest_fail_reason FROM system.mutations WHERE table = 'works_seed_mexico' AND latest_fail_reason != '' ORDER BY creation_time DESC LIMIT 1")
                if res_err.result_rows and res_err.result_rows[0][0]:
                     print(f"Error en mutacion: {res_err.result_rows[0][0]}")
                     break
                print("Finalizado: Mutacion completada.")
                break
            
            print("... procesando mutacion ...")
            time.sleep(15)
            
    except Exception as e:
        print(f"Error general: {e}")

if __name__ == "__main__":
    materialize_metrics()
