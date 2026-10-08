import json
import os
import time
import urllib.request
from neo4j import GraphDatabase

NEO4J_URI = "bolt://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password123"
CATALOG_PATH = "/home/sinapsisai/data/openalex_topics_catalog.json"

def fetch_openalex_topics():
    if os.path.exists(CATALOG_PATH):
        print(f"Cargando catálogo existente desde {CATALOG_PATH}...")
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    print("Descargando catálogo completo de tópicos desde OpenAlex API...")
    topics_map = {}
    cursor = "*"
    headers = {"User-Agent": "mailto:jlja@comunidad.unam.mx (SECIHTI SinapsisAI)"}
    page = 1

    while cursor:
        url = f"https://api.openalex.org/topics?per-page=200&cursor={cursor}&select=id,display_name,subfield,field,domain"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            print(f"Error en página {page}: {e}. Reintentando...")
            time.sleep(2)
            continue

        results = data.get("results", [])
        if not results:
            break

        for t in results:
            tid = t.get("id")
            tname = t.get("display_name")
            subfield = t.get("subfield", {}).get("display_name") if t.get("subfield") else None
            field = t.get("field", {}).get("display_name") if t.get("field") else None
            domain = t.get("domain", {}).get("display_name") if t.get("domain") else None

            entry = {
                "display_name": tname,
                "subfield": subfield,
                "field": field,
                "domain": domain
            }
            topics_map[tid] = entry
            short_id = tid.split("/")[-1]
            topics_map[short_id] = entry

        meta = data.get("meta", {})
        cursor = meta.get("next_cursor")
        print(f"  Página {page}: {len(topics_map)} entradas indexadas...")
        page += 1
        time.sleep(0.1)

    os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(topics_map, f, ensure_ascii=False, indent=2)
    print(f"Catálogo guardado en {CATALOG_PATH} con {len(topics_map)} entradas.")
    return topics_map

def update_neo4j_topics(topics_map):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as s:
        # Obtener todos los tópicos con URL o name que empieza con http
        print("\nConsultando tópicos con URL en Neo4j...")
        records = s.run("""
        MATCH (t:Topic)
        WHERE t.name STARTS WITH 'http' OR t.id CONTAINS 'https://openalex.org/'
        RETURN t.id AS id, t.name AS name
        """).data()
        print(f"Encontrados {len(records)} nodos Topic para verificar/actualizar.")

        to_update = []
        not_found = 0

        for r in records:
            tid = r["id"]
            tname = r["name"]

            # Intentar match por tname completo o por la URL al final del id
            info = topics_map.get(tname)
            if not info and "||" in tid:
                last_part = tid.split("||")[-1].strip()
                info = topics_map.get(last_part)
                if not info:
                    short_part = last_part.split("/")[-1].strip()
                    info = topics_map.get(short_part)

            if info and info.get("display_name"):
                to_update.append({
                    "id": tid,
                    "new_name": info["display_name"],
                    "url": tname if tname.startswith("http") else tid.split("||")[-1].strip(),
                    "subfield": info.get("subfield"),
                    "field": info.get("field"),
                    "domain": info.get("domain")
                })
            else:
                not_found += 1

        print(f"Identificados {len(to_update)} tópicos para actualizar con nombre oficial. (Sin match: {not_found})")

        # Actualizar en batches de 500
        batch_size = 500
        total_updated = 0
        for i in range(0, len(to_update), batch_size):
            batch = to_update[i:i+batch_size]
            s.run("""
            UNWIND $batch AS row
            MATCH (t:Topic {id: row.id})
            SET t.name = row.new_name,
                t.openalex_url = row.url,
                t.subfield = coalesce(row.subfield, t.subfield),
                t.field = coalesce(row.field, t.field),
                t.domain = coalesce(row.domain, t.domain)
            """, batch=batch)
            total_updated += len(batch)
            print(f"  Actualizados {total_updated}/{len(to_update)} nodos...")

        print(f"\n¡Éxito! Total de tópicos actualizados en Neo4j: {total_updated}")

        # Verificación posterior
        verify = s.run("""
        MATCH (p:Person)-[:AUTHOR_OF]->(w:Paper)-[:HAS_TOPIC]->(t:Topic)
        WHERE p.snii_area IS NOT NULL
        RETURN count(DISTINCT CASE WHEN NOT t.name STARTS WITH 'http' THEN t END) AS real_name_topics,
               count(DISTINCT CASE WHEN t.name STARTS WITH 'http' THEN t END) AS url_topics,
               count(DISTINCT t) AS total_topics
        """).single()
        print("\nVerificación en SNII tras la actualización:")
        print(dict(verify))

if __name__ == "__main__":
    tmap = fetch_openalex_topics()
    update_neo4j_topics(tmap)
