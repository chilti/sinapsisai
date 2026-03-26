import pandas as pd
import os
import sys

# Agregar el directorio raíz al path para poder importar la base de datos
sys.path.append(os.getcwd())

from database.knowledge_graph import Neo4jGraphStore

def populate_geography():
    excel_path = 'SNII/Investigadores_vigentes_2025.xlsx'
    if not os.path.exists(excel_path):
        print(f"❌ No se encontró el Excel: {excel_path}")
        return

    print(f"📊 Leyendo Excel: {excel_path}...")
    try:
        df = pd.read_excel(excel_path)
        # Normalizar nombres de columnas
        df.columns = [c.strip() for c in df.columns]
        
        inst_col = 'INSTITUCIÓN DE COMISIÓN'
        state_col = 'ENTIDAD DE ACREDITACIÓN'
        
        if inst_col not in df.columns or state_col not in df.columns:
            print(f"❌ Columnas no encontradas. Disponibles: {df.columns.tolist()}")
            return

        # Conectar a Neo4j (asumiendo localhost como en los scripts del usuario)
        graph = Neo4jGraphStore(uri="bolt://localhost:7687", user="neo4j", password="password123")
        
        print("🌍 Actualizando geografía de instituciones...")
        unique_pairs = df[[inst_col, state_col]].drop_duplicates()
        total = len(unique_pairs)
        processed = 0
        
        for _, row in unique_pairs.iterrows():
            inst = str(row[inst_col]).strip() if pd.notna(row[inst_col]) else None
            state = str(row[state_col]).strip() if pd.notna(row[state_col]) else None
            
            if inst and inst != "nan":
                graph.upsert_geography(inst_name=inst, state_name=state, country_name="Mexico")
                processed += 1
                if processed % 50 == 0:
                    print(f"   ✅ Procesadas {processed}/{total} instituciones...")
        
        graph.close()
        print(f"✨ Geografía completada. Se actualizaron {processed} instituciones.")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    populate_geography()
