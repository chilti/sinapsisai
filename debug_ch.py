import sys, os
sys.path.append(os.path.abspath('.'))
from database.clickhouse_db import ch_client

print("--- DIAGNÓSTICO CLICKHOUSE ---")

res1 = ch_client.query_df("SELECT count() as c FROM paper_entity_map WHERE subdependency = 'CENTRO REGIONAL DE INVESTIGACIONES MULTIDISCIPLINARIAS'")
print("1. Total de filas guardadas en paper_entity_map para el Centro:", res1['c'][0])

res2 = ch_client.query_df("SELECT paper_id FROM paper_entity_map WHERE subdependency = 'CENTRO REGIONAL DE INVESTIGACIONES MULTIDISCIPLINARIAS' LIMIT 5")
print("\n2. Muestra de los primeros 5 IDs guardados en la tabla:")
print(res2['paper_id'].tolist() if not res2.empty else "Vacío")

res3 = ch_client.query_df("SELECT count() as c FROM paper_entity_map WHERE subdependency = 'CENTRO REGIONAL DE INVESTIGACIONES MULTIDISCIPLINARIAS' AND paper_id LIKE 'W%'")
print("\n3. Cuántos IDs empezando con 'W' hay en paper_entity_map:", res3['c'][0])

res4 = ch_client.query_df("SELECT count() as c FROM works_academic_all WHERE id LIKE 'https://openalex.org/W%'")
print("\n4. Cuántos W-IDs globales existen materializados en works_academic_all:", res4['c'][0])

print("\n------------------------------")
