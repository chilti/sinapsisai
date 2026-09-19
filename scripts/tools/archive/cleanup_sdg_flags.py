import os
import sys
import argparse
from dotenv import load_dotenv

# Asegurar que el directorio raíz esté en el path para importar database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from database.knowledge_graph import Neo4jGraphStore

load_dotenv()

def cleanup_sdg_flags(dry_run=True):
    neo4j = Neo4jGraphStore()
    
    # Consulta para identificar papers marcados como procesados pero sin resultados reales
    query_check = """
    MATCH (p:Paper {sdg_processed: true})
    WHERE NOT (p)-[:ADDRESSES]->() 
      AND p.sdg_reasoning IS NULL
    RETURN count(p) as count
    """
    
    query_list = """
    MATCH (p:Paper {sdg_processed: true})
    WHERE NOT (p)-[:ADDRESSES]->() 
      AND p.sdg_reasoning IS NULL
    RETURN p.doi as doi, p.title as title
    LIMIT 10
    """

    query_update = """
    MATCH (p:Paper {sdg_processed: true})
    WHERE NOT (p)-[:ADDRESSES]->() 
      AND p.sdg_reasoning IS NULL
    REMOVE p.sdg_processed
    RETURN count(p) as count
    """

    try:
        with neo4j.driver.session() as session:
            # 1. Ver cuantos hay
            result = session.run(query_check).single()
            total = result["count"]
            
            if total == 0:
                print("[INFO] No se encontraron papers marcados erroneamente. Todo esta en orden.")
                return

            print(f"[INFO] Se encontraron {total} papers marcados como procesados que NO tienen resultados (ni ODS ni razonamiento).")
            
            # Mostramos una muestra
            sample_result = session.run(query_list)
            # Consumimos el resultado a una lista para evitar problemas de sesion cerrada
            sample_data = [dict(r) for r in sample_result]
            
            if sample_data:
                print("\nMuestra de papers afectados:")
                for s in sample_data:
                    # Limpiamos el título de caracteres problemáticos por si acaso
                    safe_title = str(s['title']).encode('ascii', 'ignore').decode('ascii')[:50]
                    print(f"  - {s['doi']}: {safe_title}...")

            if dry_run:
                print("\n[WARN] MODO DRY-RUN ACTIVADO. No se han realizado cambios.")
                print("Usa --execute para desmarcar estos papers y permitir que se vuelvan a procesar.")
            else:
                print(f"\n[EXEC] Ejecutando limpieza de {total} registros...")
                # Ejecutamos la actualizacion en una transaccion
                update_res = session.run(query_update).single()
                print(f"[OK] Exito. Se han desmarcado {update_res['count']} papers correctamente.")
                print("Ahora puedes volver a correr ingestion/ingest_sdg.py para procesarlos.")

    except Exception as e:
        print(f"[ERROR] Error durante la limpieza: {e}")
    finally:
        neo4j.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Limpia los flags de procesamiento SDG erróneos en Neo4j.")
    parser.add_argument("--execute", action="store_true", help="Realizar los cambios en la base de datos")
    args = parser.parse_args()
    
    cleanup_sdg_flags(dry_run=not args.execute)
