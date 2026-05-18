import sys
import os
import json

# Añadir el directorio raíz al path para importar los módulos
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from database.knowledge_graph import Neo4jGraphStore

def run_migration():
    print("Iniciando remediación de homónimos y migración de IDs robustos...")
    graph = Neo4jGraphStore()
    
    with graph.driver.session() as session:
        # --- PASO 1: Migrar autores con identificadores únicos (ORCID/Scopus) ---
        print("\nStep 1: Migrando autores con ORCID o Scopus ID manuales...")
        
        # Primero buscamos los que necesitan cambio
        query_identifiable = """
        MATCH (a:Author)
        WHERE (a.orcid IS NOT NULL OR a.scopus_id IS NOT NULL)
        AND a.id = a.name
        RETURN a.id as old_id, a.name as name, a.orcid as orcid, a.scopus_id as scopus_id
        """
        
        candidates = list(session.run(query_identifiable))
        print(f"🔍 Encontrados {len(candidates)} autores con ID de nombre que tienen identificadores únicos.")
        
        for cand in candidates:
            old_id = cand['old_id']
            name = cand['name']
            orcid = cand['orcid']
            scopus_id = cand['scopus_id']
            
            # Calcular nuevo ID
            if orcid:
                new_id = orcid
            else:
                sid = scopus_id.split(';')[0].strip() if ';' in scopus_id else scopus_id
                new_id = f"scopus:{sid}"
            
            print(f"  -> Migrando: '{name}' ({old_id}) => {new_id}")
            
            # 1. Obtener todas las propiedades actuales
            props_res = session.run("MATCH (a:Author {id: $old_id}) RETURN properties(a) as props", old_id=old_id)
            p_rec = props_res.single()
            if not p_rec: continue
            props = dict(p_rec['props'])
            if 'id' in props: del props['id']
            
            # 2. Migración manual de relaciones para evitar dependencia de APOC
            rels = ["AUTHORED", "AFFILIATED_WITH", "AFFILIATED_TO"]
            for rel in rels:
                # Relaciones salientes
                session.run(f"""
                    MATCH (old:Author {{id: $old_id}})-[r:{rel}]->(target)
                    MERGE (new:Author {{id: $new_id}})
                    MERGE (new)-[nr:{rel}]->(target)
                    SET nr = r
                    DELETE r
                """, old_id=old_id, new_id=new_id)
                
                # Relaciones entrantes
                session.run(f"""
                    MATCH (source)-[r:{rel}]->(old:Author {{id: $old_id}})
                    MERGE (new:Author {{id: $new_id}})
                    MERGE (source)-[nr:{rel}]->(new)
                    SET nr = r
                    DELETE r
                """, old_id=old_id, new_id=new_id)
            
            # 3. Aplicar propiedades al nuevo y borrar viejo
            session.run("""
                MATCH (old:Author {id: $old_id})
                MERGE (new:Author {id: $new_id})
                SET new += $props
                SET new:Academic
                DETACH DELETE old
            """, old_id=old_id, new_id=new_id, props=props)

        # --- PASO 2: Identificar y marcar potenciales homónimos (Nombre@Entidad) ---
        print("\nStep 2: Buscando autores que deberían diferenciarse por Entidad (homónimos potenciales)...")
        # En esta versión simplificada, nos aseguramos de que todos los Academicos tengan ID = name@entity 
        # si no tienen ORCID. Eso ayuda a separarlos en futuras ingestas.
        
        query_academics = """
        MATCH (a:Academic)-[:AFFILIATED_TO]->(e:Entity)
        WHERE a.id = a.name AND a.orcid IS NULL AND a.scopus_id IS NULL
        RETURN a.name as name, e.name as entity_name
        """
        
        acads = list(session.run(query_academics))
        print(f"🔍 Encontrados {len(acads)} académicos sin ID persistente para migrar a ID de Entidad.")
        
        for ac in acads:
            name = ac['name']
            ent = ac['entity_name']
            new_id = f"{name}@{ent}"
            print(f"  -> Refinando ID: '{name}' => {new_id}")
            
            # 1. Obtener propiedades
            props_res = session.run("MATCH (a:Author {id: $old_id}) RETURN properties(a) as props", old_id=name)
            p_rec = props_res.single()
            if not p_rec: continue
            props = dict(p_rec['props'])
            if 'id' in props: del props['id']
            
            # 2. Mover relaciones
            rels = ["AUTHORED", "AFFILIATED_WITH", "AFFILIATED_TO"]
            for rel in rels:
                session.run(f"""
                    MATCH (old:Author {{id: $old_id}})-[r:{rel}]->(target)
                    MERGE (new:Author {{id: $new_id}})
                    MERGE (new)-[nr:{rel}]->(target)
                    SET nr = r
                    DELETE r
                """, old_id=name, new_id=new_id)
                session.run(f"""
                    MATCH (source)-[r:{rel}]->(old:Author {{id: $old_id}})
                    MERGE (new:Author {{id: $new_id}})
                    MERGE (source)-[nr:{rel}]->(new)
                    SET nr = r
                    DELETE r
                """, old_id=name, new_id=new_id)
            
            # 3. Finalizar nodo
            session.run("""
                MATCH (old:Author {id: $old_id})
                MERGE (new:Author {id: $new_id})
                SET new += $props
                SET new:Academic
                DETACH DELETE old
            """, old_id=name, new_id=new_id, props=props)

    print("\n✅ Migración completada. La base de datos ahora usa IDs robustos.")
    graph.close()

if __name__ == "__main__":
    run_migration()
