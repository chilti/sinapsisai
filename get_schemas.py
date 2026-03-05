import pandas as pd
import json

def get_cols(path):
    try:
        df = pd.read_parquet(path)
        return list(df.columns)
    except Exception as e:
        return [f"Error: {e}"]

schemas = {
    "papers_institucion": get_cols(r'c:\Users\jlja\Documents\Proyectos\RAGs\data\cache\papers_institucion.parquet'),
    "papers_profesor": get_cols(r'c:\Users\jlja\Documents\Proyectos\RAGs\data\cache\papers_profesor.parquet')
}

with open(r'c:\Users\jlja\Documents\Proyectos\RAGs\parquet_schemas.json', 'w') as f:
    json.dump(schemas, f, indent=4)

print("Schemas saved to parquet_schemas.json")
