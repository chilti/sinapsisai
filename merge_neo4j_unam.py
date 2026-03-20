import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

def merge_entity(session, old_name, new_name, is_institution=False):
    print(f"\n--- Fusionando '{old_name}' -> '{new_name}' ---")
    
    # Asegurar que el destino exista
    session.run("MERGE (e:Entity {name: $new_name})", new_name=new_name)
    
    if is_institution:
        session.run("MATCH (e:Entity {name: $new_name}) SET e:Institution", new_name=new_name)
    else:
        session.run("MATCH (e:Entity {name: $new_name}) SET e:Subdependency", new_name=new_name)

    # 1. Mover AFFILIATED_TO (entrantes a old_name desde investigadores/dependencias)
    q_affil = """
    MATCH (old:Entity {name: $old_name}), (new:Entity {name: $new_name})
    MATCH (x)-[r:AFFILIATED_TO]->(old)
    MERGE (x)-[:AFFILIATED_TO]->(new)
    DELETE r
    RETURN count(r) AS moved
    """
    res = session.run(q_affil, old_name=old_name, new_name=new_name).single()
    print(f"Relaciones AFFILIATED_TO movidas: {res['moved'] if res else 0}")

    # 2. Mover PART_OF (entrantes, e.g. laboratorios a subdependencias)
    q_part_in = """
    MATCH (old:Entity {name: $old_name}), (new:Entity {name: $new_name})
    MATCH (x)-[r:PART_OF]->(old)
    MERGE (x)-[:PART_OF]->(new)
    DELETE r
    RETURN count(r) AS moved
    """
    res = session.run(q_part_in, old_name=old_name, new_name=new_name).single()
    print(f"Relaciones PART_OF (entrantes) movidas: {res['moved'] if res else 0}")

    # 3. Mover PART_OF (salientes, e.g. subdependencias a UNAM)
    q_part_out = """
    MATCH (old:Entity {name: $old_name}), (new:Entity {name: $new_name})
    MATCH (old)-[r:PART_OF]->(x)
    MERGE (new)-[:PART_OF]->(x)
    DELETE r
    RETURN count(r) AS moved
    """
    res = session.run(q_part_out, old_name=old_name, new_name=new_name).single()
    print(f"Relaciones PART_OF (salientes) movidas: {res['moved'] if res else 0}")

    # 4. Mover HAS_PAPER (salientes a Papers)
    q_paper = """
    MATCH (old:Entity {name: $old_name}), (new:Entity {name: $new_name})
    MATCH (old)-[r:HAS_PAPER]->(x)
    MERGE (new)-[:HAS_PAPER]->(x)
    DELETE r
    RETURN count(r) AS moved
    """
    res = session.run(q_paper, old_name=old_name, new_name=new_name).single()
    print(f"Relaciones HAS_PAPER movidas: {res['moved'] if res else 0}")

    # 5. Eliminar nodo viejo de forma segura (con DETACH por si quedaron relaciones aisladas)
    q_del = """
    MATCH (old:Entity {name: $old_name})
    DETACH DELETE old
    RETURN count(old) AS deleted
    """
    res = session.run(q_del, old_name=old_name).single()
    print(f"Nodos viejos '{old_name}' eliminados de la BD: {res['deleted'] if res else 0}")


def main():
    store = Neo4jGraphStore()
    
    with store.driver.session() as session:
        # Primer paso: Fusionar las subdependencias mixtas o desactualizadas hacia sus versiones en MAYÚSCULAS
        # Si la versión en mayúsculas no existe, nuestro código la crea (MERGE).
        merge_entity(session, 
            old_name="Facultad de Ciencias", 
            new_name="FACULTAD DE CIENCIAS",
            is_institution=False
        )
        merge_entity(session, 
            old_name="Instituto de Ciencias Nucleares", 
            new_name="INSTITUTO DE CIENCIAS NUCLEARES",
            is_institution=False
        )
        merge_entity(session, 
            old_name="Centro de Ciencias de la Complejidad", 
            new_name="CENTRO DE CIENCIAS DE LA COMPLEJIDAD",
            is_institution=False
        )

        unam_target = "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)"
        
        # Segundo paso: Fusionar la vieja sub-institución (con tildes y nombres largos) hacia la institución maestra en mayúsculas.
        # Esto automáticamente transferirá todos los links PART_OF y AFFILIATED_TO que apuntaban a 
        # "Universidad Nacional Autónoma de México (UNAM)" para que apunten a "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)".
        merge_entity(session,
            old_name="Universidad Nacional Autónoma de México (UNAM)",
            new_name=unam_target,
            is_institution=True
        )

        # Tercer paso (Seguridad y Normalización): 
        # Garantizamos explícitamente que las 3 subdependencias están PART_OF de la UNAM destino
        q_enforce = """
        UNWIND $subs AS sub_name
        MATCH (s:Entity {name: sub_name})
        MATCH (i:Entity {name: $unam_target})
        MERGE (s)-[:PART_OF]->(i)
        """
        session.run(q_enforce, 
            subs=["FACULTAD DE CIENCIAS", "INSTITUTO DE CIENCIAS NUCLEARES", "CENTRO DE CIENCIAS DE LA COMPLEJIDAD"],
            unam_target=unam_target
        )
        print("\n✅ Enlaces PART_OF hacia UNAM garantizados para las 3 subdependencias integradas.")
        
    store.close()
    print("\n¡Limpieza y unificación completadas exitosamente! Todo alineado al formato MAYÚSCULAS nacional.")

if __name__ == '__main__':
    main()
