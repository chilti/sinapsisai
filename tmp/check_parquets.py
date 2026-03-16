import pandas as pd
import os

CACHE_DIR = r"c:\Users\jlja\Documents\Proyectos\RAGs\data\cache"

def check_parquets():
    files = [
        "institucion_total.parquet",
        "investigador_total.parquet"
    ]
    
    for f in files:
        path = os.path.join(CACHE_DIR, f)
        if os.path.exists(path):
            df = pd.read_parquet(path)
            print(f"\n--- {f} ---")
            print(df.columns.tolist())
            print(df.head(2))
        else:
            print(f"{f} not found at {path}")

if __name__ == "__main__":
    check_parquets()
