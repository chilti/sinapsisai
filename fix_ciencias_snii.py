import os
import pandas as pd
from database.knowledge_graph import Neo4jGraphStore
from dotenv import load_dotenv

def fix_ciencias_snii():
    # Asegurar que el entorno esté cargado
    load_dotenv()
    
    # Usar el store centralizado que ya maneja las variables correctamente (NEO4J_PASS, NEO4J_USER, etc)
    neo = Neo4jGraphStore()
    driver = neo.driver

    # Leer el Excel (no tiene cabecera, los nombres están en la primera columna)
    df = pd.read_excel("data/FCiencias/sniis_CIENCIAS.xlsx", header=None)
    names_with_comma = df[0].dropna().tolist()

    updated_count = 0
    not_found_count = 0

    query = """
    MATCH (p:Person {fullname: $name_no_comma})-[:AFFILIATED_TO]->(s:Subdependency {name: 'FACULTAD DE CIENCIAS'})-[:PART_OF*1..2]->(i:Institution {name: 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)'})
    SET p.fullname = $name_with_comma,
        p.is_snii = true
    RETURN p.id AS id
    """

    print(f"Buscando {len(names_with_comma)} investigadores de la Facultad de Ciencias...")

    with driver.session() as session:
        for name_with_comma in names_with_comma:
            name_with_comma = str(name_with_comma).strip()
            # Derivamos la versión sin coma para buscarla en la base de datos
            name_no_comma = name_with_comma.replace(",", "").replace("  ", " ")

            result = session.run(query, name_no_comma=name_no_comma, name_with_comma=name_with_comma)
            record = result.single()

            if record:
                updated_count += 1
                print(f"[OK] Actualizado: {name_no_comma} -> {name_with_comma}")
            else:
                not_found_count += 1
                # print(f"[NO ENCONTRADO] {name_no_comma}")

    print("-" * 40)
    print(f"Total procesados: {len(names_with_comma)}")
    print(f"Nodos actualizados exitosamente: {updated_count}")
    print(f"Nodos no encontrados (quizá ya tenían la coma o no existen): {not_found_count}")

    driver.close()

if __name__ == "__main__":
    fix_ciencias_snii()
