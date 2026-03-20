import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

def main():
    store = Neo4jGraphStore()
    
    subdependencies = [
        'FACULTAD LATINOAMERICANA DE CIENCIAS SOCIALES',
        'INSTITUTO NACIONAL DE INVESTIGACIONES NUCLEARES',
        'INSTITUTO NACIONAL DE CIENCIAS MEDICAS Y NUTRICION SALVADOR ZUBIRAN'
    ]
    
    unam_target = 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)'
    unam_old = 'UNAM'

    with store.driver.session() as session:
        print("=== PASO 1: Remover Subdependencias Excluidas ===")
        # Eliminar las relaciones AFFILIATED_TO hacia UNAM para los académicos de esas subdependencias,
        # SOLAMENTE si no tienen otra subdependencia válida en la UNAM.
        q1a = """
        MATCH (s:Entity)-[:PART_OF]->(i:Entity {name: $unam_target})
        WHERE s.name IN $bad_subs
        MATCH (a:Author)-[:AFFILIATED_TO]->(s)
        MATCH (a)-[r:AFFILIATED_TO]->(i)
        // Check that they don't have any OTHER subdependency that is part of UNAM
        WHERE NOT EXISTS {
            MATCH (a)-[:AFFILIATED_TO]->(other_s:Entity)-[:PART_OF]->(i)
            WHERE other_s.name <> s.name AND NOT other_s.name IN $bad_subs
        }
        DELETE r
        RETURN count(r) AS deleted_affiliations
        """
        res = session.run(q1a, unam_target=unam_target, bad_subs=subdependencies)
        print(f"Academics fully unlinked from UNAM: {res.single()['deleted_affiliations']}")

        # Eliminar la relación PART_OF
        q1b = """
        MATCH (s:Entity)-[r:PART_OF]->(i:Entity {name: $unam_target})
        WHERE s.name IN $bad_subs
        DELETE r
        RETURN count(r) AS deleted_part_of
        """
        res2 = session.run(q1b, unam_target=unam_target, bad_subs=subdependencies)
        print(f"Subdependencies detached from UNAM: {res2.single()['deleted_part_of']}")

        print("\n=== PASO 2: Unir 'UNAM' con 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)' ===")
        # Mover AFFILIATED_TO
        q2a = """
        MATCH (old:Entity {name: $old_name}), (new:Entity {name: $new_name})
        MATCH (x)-[r:AFFILIATED_TO]->(old)
        MERGE (x)-[:AFFILIATED_TO]->(new)
        DELETE r
        RETURN count(r) AS moved_affiliations
        """
        r2a = session.run(q2a, old_name=unam_old, new_name=unam_target)
        print(f"Moved AFFILIATED_TO relationships: {r2a.single()['moved_affiliations']}")

        # Mover PART_OF
        q2b = """
        MATCH (old:Entity {name: $old_name}), (new:Entity {name: $new_name})
        MATCH (x)-[r:PART_OF]->(old)
        MERGE (x)-[:PART_OF]->(new)
        DELETE r
        RETURN count(r) AS moved_part_of
        """
        r2b = session.run(q2b, old_name=unam_old, new_name=unam_target)
        print(f"Moved PART_OF relationships: {r2b.single()['moved_part_of']}")

        # Mover HAS_PAPER
        q2c = """
        MATCH (old:Entity {name: $old_name}), (new:Entity {name: $new_name})
        MATCH (old)-[r:HAS_PAPER]->(x)
        MERGE (new)-[:HAS_PAPER]->(x)
        DELETE r
        RETURN count(r) AS moved_has_paper
        """
        r2c = session.run(q2c, old_name=unam_old, new_name=unam_target)
        print(f"Moved HAS_PAPER relationships: {r2c.single()['moved_has_paper']}")

        # Transfer labels and delete old node
        q2d = """
        MATCH (old:Entity {name: $old_name}), (new:Entity {name: $new_name})
        SET new:Institution
        DELETE old
        RETURN count(old) AS deleted_old
        """
        r2d = session.run(q2d, old_name=unam_old, new_name=unam_target)
        if r2d.peek():
            print(f"Deleted old node UNAM: {r2d.single()['deleted_old']}")
        else:
             print("Node UNAM already deleted or not found.")

    store.close()
    print("Done!")

if __name__ == '__main__':
    main()
