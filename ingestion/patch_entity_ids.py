import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env')))

from database.knowledge_graph import Neo4jGraphStore

def clean_id(id_str):
    if not id_str or str(id_str).lower() == 'null' or str(id_str).lower() == 'none':
        return None
    return str(id_str).strip()

def patch_hierarchy_ids():
    json_path = Path(__file__).parent.parent / 'data' / 'snii_ror_verified_matches.json'
    
    if not json_path.exists():
        print(f"❌ No se encontró el archivo: {json_path}")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        mapping = json.load(f)

    gs = Neo4jGraphStore()
    updates = {"inst": 0, "dep": 0, "sub": 0}

    print(f"🔄 Procesando {len(mapping)} registros del JSON...")

    with gs.driver.session() as session:
        for key, data in mapping.items():
            parts = [p.strip() for p in key.split('||')]
            if len(parts) != 3:
                continue
            
            inst_name, dep_name, sub_name = parts
            
            parent_ror = clean_id(data.get('parent_ror'))
            parent_oa  = clean_id(data.get('parent_openalex_id'))
            
            matched_ror = clean_id(data.get('matched_ror'))
            matched_oa  = clean_id(data.get('matched_openalex_id'))
            is_sub_match = data.get('is_subdependency_match', False)
            
            # 1. Parchear Institución (siempre usa parent)
            if parent_ror or parent_oa:
                set_clause = []
                if parent_ror: set_clause.append("n.ror = $ror")
                if parent_oa:  set_clause.append("n.openalex_id = $id")
                
                if set_clause:
                    q = f"MATCH (n:Institution {{name: $name}}) SET {', '.join(set_clause)}"
                    res = session.run(q, name=inst_name, ror=parent_ror, id=parent_oa)
                    updates["inst"] += res.consume().counters.properties_set
            
            # 2. Parchear Subdependencia
            if sub_name != "SIN INFORMACIÓN":
                # Si el match es de la subdependencia, usamos matched.
                if is_sub_match and (matched_ror or matched_oa):
                    set_clause = []
                    if matched_ror: set_clause.append("n.ror = $ror")
                    if matched_oa:  set_clause.append("n.openalex_id = $id")
                    
                    if set_clause:
                        q = f"MATCH (n:Subdependency {{name: $name}}) SET {', '.join(set_clause)}"
                        res = session.run(q, name=sub_name, ror=matched_ror, id=matched_oa)
                        updates["sub"] += res.consume().counters.properties_set
                else:
                    # Si no hay match específico, hereda del padre (según la lógica, puede heredar)
                    # El usuario indicó "verifica que se agreguen en los tres niveles si las tenemos"
                    # Por consistencia de agrupación, inyectamos el del padre si no tiene propio.
                    if parent_ror or parent_oa:
                        set_clause = []
                        if parent_ror: set_clause.append("n.ror = $ror")
                        if parent_oa:  set_clause.append("n.openalex_id = $id")
                        if set_clause:
                            q = f"MATCH (n:Subdependency {{name: $name}}) SET {', '.join(set_clause)}"
                            res = session.run(q, name=sub_name, ror=parent_ror, id=parent_oa)
                            updates["sub"] += res.consume().counters.properties_set

            # 3. Parchear Dependencia
            if dep_name != "SIN INFORMACIÓN":
                # Si no es match de subdependencia pero hay matched_ror, es de la dependencia
                if not is_sub_match and (matched_ror or matched_oa):
                    set_clause = []
                    if matched_ror: set_clause.append("n.ror = $ror")
                    if matched_oa:  set_clause.append("n.openalex_id = $id")
                    
                    if set_clause:
                        q = f"MATCH (n:Dependency {{name: $name}}) SET {', '.join(set_clause)}"
                        res = session.run(q, name=dep_name, ror=matched_ror, id=matched_oa)
                        updates["dep"] += res.consume().counters.properties_set
                else:
                    # Hereda del padre
                    if parent_ror or parent_oa:
                        set_clause = []
                        if parent_ror: set_clause.append("n.ror = $ror")
                        if parent_oa:  set_clause.append("n.openalex_id = $id")
                        if set_clause:
                            q = f"MATCH (n:Dependency {{name: $name}}) SET {', '.join(set_clause)}"
                            res = session.run(q, name=dep_name, ror=parent_ror, id=parent_oa)
                            updates["dep"] += res.consume().counters.properties_set

    print("\n✅ Resumen de propiedades actualizadas en Neo4j:")
    print(f"   Instituciones:  {updates['inst']} propiedades actualizadas")
    print(f"   Dependencias:   {updates['dep']} propiedades actualizadas")
    print(f"   Subdependencias: {updates['sub']} propiedades actualizadas")

if __name__ == '__main__':
    patch_hierarchy_ids()
