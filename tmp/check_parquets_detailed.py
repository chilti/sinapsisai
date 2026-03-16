import pandas as pd
import os

CACHE_DIR = r"c:\Users\jlja\Documents\Proyectos\RAGs\data\cache"

def check_parquets():
    path = os.path.join(CACHE_DIR, "institucion_total.parquet")
    if os.path.exists(path):
        df = pd.read_parquet(path)
        print("\n--- Columns in institucion_total.parquet ---")
        for col in df.columns:
            print(col)
        
        if 'entity_name' in df.columns:
            print("\nUnique entity_name:", df['entity_name'].unique().tolist())
        if 'institution_name' in df.columns:
            print("\nUnique institution_name:", df['institution_name'].unique().tolist())
        elif 'institution' in df.columns:
            print("\nUnique institution:", df['institution'].unique().tolist())
            
if __name__ == "__main__":
    check_parquets()
