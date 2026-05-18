
import os
import sys
import json
import time
from pathlib import Path

# Añadir el path del proyecto
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.clickhouse_db import ch_client

def polite_patch(batch_size=5000, limit=None):
    print("🚀 Iniciando materialización 'polite' de trayectorias de citas...")
    
    # 1. Obtener los IDs que necesitamos parchear (de works_academic_all que es pequeña)
    query_ids = "SELECT id FROM works_academic_all WHERE length(counts_by_year) <= 2 OR counts_by_year = ''"
    if limit:
        query_ids += f" LIMIT {limit}"
        
    print("🔍 Identificando registros sin trayectoria...")
    ids_df = ch_client.query_df(query_ids)
    all_ids = ids_df['id'].tolist()
    total = len(all_ids)
    
    if total == 0:
        print("✅ No hay registros pendientes de trayectoria en works_academic_all.")
        return

    print(f"📊 Encontrados {total} registros para parchear. Procesando en lotes de {batch_size}...")

    updated = 0
    for i in range(0, total, batch_size):
        batch = all_ids[i:i+batch_size]
        
        # 2. Obtener raw_data de la tabla principal 'works' usando el índice de ID (muy rápido)
        # Usamos un JOIN temporal en memoria o una subconsulta filtrada por IDs específicos
        ids_str = ", ".join([f"'{id}'" for id in batch])
        
        # Extraer el fragmento JSON directamente en ClickHouse para no mover todo el raw_data
        patch_query = f"""
        SELECT id, JSONExtractString(raw_data, 'counts_by_year') as cby
        FROM works
        WHERE id IN ({ids_str})
        """
        
        try:
            patch_df = ch_client.query_df(patch_query)
            if patch_df.empty:
                print(f"      ⚠️ Lote {i//batch_size + 1}: No se encontró raw_data en 'works' para estos IDs.")
                continue
                
            # 3. Actualizar works_academic_all y works_flat
            # Nota: En ClickHouse las actualizaciones masivas son asíncronas (mutaciones)
            # Para ser "polite", procesamos bloque a bloque
            
            # 3. Actualizar works_academic_all y works_flat en UN SOLO COMANDO por tabla
            # Construimos una sentencia CASE para actualizar todas las filas del lote a la vez
            case_parts = []
            ids_in_batch = []
            for _, row in patch_df.iterrows():
                if not row['cby'] or row['cby'] == '[]':
                    continue
                cby_val = row['cby'].replace("'", "''")
                case_parts.append(f"WHEN '{row['id']}' THEN '{cby_val}'")
                ids_in_batch.append(f"'{row['id']}'")
            
            if ids_in_batch:
                case_sql = "CASE id " + " ".join(case_parts) + " END"
                ids_sql = ", ".join(ids_in_batch)
                
                # Una sola mutación por tabla por lote
                ch_client.command(f"ALTER TABLE works_academic_all UPDATE counts_by_year = {case_sql} WHERE id IN ({ids_sql})")
                ch_client.command(f"ALTER TABLE works_flat UPDATE counts_by_year = {case_sql} WHERE id IN ({ids_sql})")
                updated += len(ids_in_batch)
            
            print(f"  ✅ Lote {i//batch_size + 1}: {len(patch_df)} procesados. Acumulado: {updated}/{total}")
            
            # Respiro más largo para permitir que ClickHouse procese la mutación
            time.sleep(2)
            
        except Exception as e:
            print(f"  ❌ Error en lote {i//batch_size + 1}: {e}")
            time.sleep(2)

    print(f"\n✨ Finalizado. {updated} registros enriquecidos con éxito.")

if __name__ == "__main__":
    # Empezamos con un límite pequeño para validar
    polite_patch(batch_size=500)
