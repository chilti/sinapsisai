import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.clickhouse_db import ch_client

def cleanup():
    print("⏳ Iniciando limpieza física de duplicados en paper_entity_map...")
    try:
        # OPTIMIZE table forces a merge of all parts and deduplication for ReplacingMergeTree
        ch_client.get_client().command("OPTIMIZE TABLE paper_entity_map FINAL")
        
        # Verificar resultados
        res = ch_client.query_df("SELECT count() as total FROM paper_entity_map")
        print(f"✅ Limpieza completada. Filas restantes: {res.iloc[0,0]:,}")
        
    except Exception as e:
        print(f"❌ Error durante la limpieza: {e}")

if __name__ == "__main__":
    cleanup()
