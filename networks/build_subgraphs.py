import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
from pyvis.network import Network
import pandas as pd

# Setup paths to import project modules
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))
load_dotenv(str(_THIS.parent / '.env'))

from database.knowledge_graph import Neo4jGraphStore

# Paleta de colores para niveles de SNII
SNII_COLORS = {
    '3': '#dc2626',       # Rojo vibrante
    '2': '#ea580c',       # Naranja oscuro
    '1': '#ca8a04',       # Amarillo/Dorado
    'C': '#16a34a',       # Verde
    'SIN': '#64748b',     # Gris
    'EXT': '#94a3b8'      # Gris claro
}

def get_academic_ego_network(neo, academic_id, depth=1, min_weight=1):
    """
    Obtiene las relaciones de coautoría de primer grado para un académico.
    """
    print(f"🔍 Consultando red de coautoría para ID '{academic_id}' (min_colabs={min_weight})...")
    
    # Query Cypher para coautoría
    query = """
    MATCH (a:Person)-[:AUTHOR_OF]->(p:Paper)<-[:AUTHOR_OF]-(b:Person)
    WHERE a.id = $id AND a <> b
    WITH a, b, count(p) AS weight
    WHERE weight >= $min_weight
    RETURN 
        a.fullname AS source_name, 
        a.id AS source_id,
        a.is_snii AS source_is_snii,
        coalesce(a.snii_max_level, 'SIN') AS source_snii_level,
        b.fullname AS target_name,
        b.id AS target_id,
        b.is_snii AS target_is_snii,
        coalesce(b.snii_max_level, 'SIN') AS target_snii_level,
        weight
    ORDER BY weight DESC
    """
    
    with neo.driver.session() as session:
        records = session.run(query, id=academic_id, min_weight=min_weight).data()
        
    if not records:
        print("⚠️ No se encontraron colaboradores para este académico.")
        return []
        
    return records

def build_pyvis_html(records, out_path, title="Red de Colaboración"):
    """
    Construye la visualización interactiva Pyvis y la guarda como HTML.
    """
    # Inicializar red pyvis
    # Usamos fondo oscuro/sutil, y controles activados para zoom/fuerzas
    net = Network(height="750px", width="100%", bgcolor="#0f172a", font_color="#f1f5f9")
    
    # Configurar opciones de física de red para mejor visualización
    net.barnes_hut(gravity=-3000, central_gravity=0.3, spring_length=95, spring_strength=0.04, damping=0.09)
    
    # Diccionario para evitar duplicidad de nodos
    added_nodes = set()
    
    for r in records:
        src_name = r['source_name']
        if isinstance(src_name, list):
            src_name = src_name[0] if src_name else "SIN NOMBRE"
        src_name = str(src_name or "SIN NOMBRE")
        
        tgt_name = r['target_name']
        if isinstance(tgt_name, list):
            tgt_name = tgt_name[0] if tgt_name else "SIN NOMBRE"
        tgt_name = str(tgt_name or "SIN NOMBRE")
        
        weight = r['weight']
        
        # Procesar nodo origen (Academic principal)
        if src_name not in added_nodes:
            snii = str(r['source_snii_level']).strip().upper()
            color = SNII_COLORS.get(snii, SNII_COLORS['SIN'])
            net.add_node(
                src_name, 
                label=src_name, 
                title=f"Investigador: {src_name}\nSNII: {snii}\nID: {r['source_id']}",
                color=color,
                size=25,
                borderWidth=3,
                borderWidthSelected=5
            )
            added_nodes.add(src_name)
            
        # Procesar nodo destino (Colaborador)
        if tgt_name not in added_nodes:
            snii = str(r['target_snii_level']).strip().upper()
            color = SNII_COLORS.get(snii, SNII_COLORS['SIN'])
            net.add_node(
                tgt_name, 
                label=tgt_name, 
                title=f"Colaborador: {tgt_name}\nSNII: {snii}\nID: {r['target_id']}",
                color=color,
                size=15 + min(weight * 2, 15), # Escala según peso
                borderWidth=1
            )
            added_nodes.add(tgt_name)
            
        # Agregar arista
        net.add_edge(
            src_name, 
            tgt_name, 
            value=weight, 
            title=f"Coautorías: {weight}",
            color="#38bdf8", # Celeste brillante
            opacity=0.6 + min(weight * 0.05, 0.4)
        )
        
    # Guardar red
    net.save_graph(str(out_path))
    print(f"✅ Red guardada en {out_path}")

def main():
    parser = argparse.ArgumentParser(description="Generador de Subgrafos de Redes Académicas en HTML")
    parser.add_argument("--academic", type=str, required=True, help="Nombre completo o ID del académico")
    parser.add_argument("--min-colabs", type=int, default=1, help="Mínimo de coautorías para incluir arista")
    parser.add_argument("--out", type=str, default=None, help="Ruta de salida del archivo HTML")
    
    args = parser.parse_args()
    
    neo = Neo4jGraphStore()
    try:
        # Intento de matching del académico
        with neo.driver.session() as session:
            # Buscar por ID o por coincidencia parcial de nombre
            search_query = """
            MATCH (p:Person)
            WHERE p.id = $name OR p.fullname = $name OR p.fullname CONTAINS $name
            OPTIONAL MATCH (p)-[:AUTHOR_OF]->(papers:Paper)
            RETURN p.fullname AS fullname, p.id AS id, count(papers) AS paper_count
            ORDER BY paper_count DESC
            LIMIT 1
            """
            match = session.run(search_query, name=args.academic.upper()).single()
            
        if match:
            matched_name = match['fullname']
            if isinstance(matched_name, list):
                matched_name = matched_name[0] if matched_name else "SIN NOMBRE"
            matched_name = str(matched_name or "SIN NOMBRE")
            matched_id = match['id']
            print(f"🎯 Académico encontrado: '{matched_name}' (ID: {matched_id})")
            records = get_academic_ego_network(neo, matched_id, min_weight=args.min_colabs)
        else:
            print(f"❌ No se encontró ningún académico con el nombre o ID '{args.academic}'")
            return

        if not records:
            print("❌ No hay colaboradores suficientes para generar la red con este umbral.")
            return
            
        # Determinar nombre del archivo
        if args.out:
            out_path = Path(args.out)
        else:
            safe_name = matched_name.replace(" ", "_").replace(",", "").lower()
            out_path = Path(f"public/tiles/subgraph_{safe_name}.html")
            
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        build_pyvis_html(records, out_path, title=f"Red de coautoría - {matched_name}")
        
    finally:
        neo.close()

if __name__ == "__main__":
    main()
