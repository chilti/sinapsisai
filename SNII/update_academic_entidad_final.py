import sys
import os
import pandas as pd
import json
from pathlib import Path
from dotenv import load_dotenv

# Añadir path raíz para importar módulos internos
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv()

from database.knowledge_graph import Neo4jGraphStore

# Configuración
EXCEL_PATH = 'data/Investigadores_vigentes_2025.xlsx'
JSON_PATH = 'data/snii_llm_verified_matches.json'

def normalize(val):
    s = str(val).strip()
    if not s or s.upper() in ['SIN INFORMACIÓN', 'NO APLICA', 'NAN', 'NONE']:
        return ""
    return s

def run_update():
    print("🚀 Iniciando actualización de ENTIDAD FINAL...")
    
    # 1. Cargar Excel
    if not os.path.exists(EXCEL_PATH):
        print(f"❌ No se encontró el Excel en {EXCEL_PATH}")
        return
        
    print(f"📂 Cargando Excel: {EXCEL_PATH}...")
    df = pd.read_excel(EXCEL_PATH, usecols=['NOMBRE DEL INVESTIGADOR', 'ENTIDAD FINAL'], sheet_name='4T_2025 (44,794)')
    df = df.rename(columns={
        'NOMBRE DEL INVESTIGADOR': 'nombre',
        'ENTIDAD FINAL': 'entidad_final'
    })
    
    # Crear un diccionario para mapeo rápido
    entidad_map = {str(row['nombre']).strip(): normalize(row['entidad_final']) for _, row in df.iterrows()}
    print(f"✅ Se cargaron {len(entidad_map)} investigadores del Excel.")

    # 2. Actualizar Neo4j
    print("\n🧬 Actualizando Neo4j...")
    gs = Neo4jGraphStore()
    with gs.driver.session() as session:
        # Procesamos en lotes para eficiencia
        names = list(entidad_map.keys())
        batch_size = 1000
        total_updated_neo = 0
        
        for i in range(0, len(names), batch_size):
            batch_names = names[i:i+batch_size]
            # Creamos una lista de dicts para la query
            params = [{"name": n, "ent_final": entidad_map[n]} for n in batch_names]
            
            res = session.run("""
                UNWIND $data AS item
                MATCH (a:Academic {name: item.name})
                SET a.entidad_final = item.ent_final
                RETURN count(a) as count
            """, data=params).single()
            
            total_updated_neo += res["count"]
            print(f"   Progreso Neo4j: {min(i+batch_size, len(names))}/{len(names)}...", end='\r')
            
    print(f"\n✅ Neo4j actualizado: {total_updated_neo} nodos Academic modificados.")

    # 3. Actualizar JSON
    if os.path.exists(JSON_PATH):
        print(f"\n📄 Actualizando JSON: {JSON_PATH}...")
        with open(JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        updated_json_count = 0
        for entry in data:
            name = entry.get('snii_author')
            if name in entidad_map:
                entry['snii_entidad_final'] = entidad_map[name]
                updated_json_count += 1
                
        with open(JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        print(f"✅ JSON actualizado: {updated_json_count} registros enriquecidos.")
    else:
        print(f"\n⚠️ No se encontró el JSON en {JSON_PATH}. Saltando esta fase.")

    print("\n✨ Proceso finalizado.")

if __name__ == "__main__":
    run_update()
