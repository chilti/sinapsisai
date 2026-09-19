import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from database.clickhouse_db import ch_client

def main():
    ch = ch_client.get_client()
    
    # Obtener esquema de ambas tablas
    flat_schema = ch.query_df("DESCRIBE works_flat")
    acad_schema = ch.query_df("DESCRIBE works_academic_all")
    
    flat_cols = set(flat_schema['name'].tolist())
    
    print("-- Columnas faltantes en works_flat pero presentes en works_academic_all --")
    
    missing = []
    for _, row in acad_schema.iterrows():
        col_name = row['name']
        col_type = row['type']
        
        if col_name not in flat_cols:
            missing.append((col_name, col_type))
            print(f"ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `{col_name}` {col_type};")

if __name__ == '__main__':
    main()
