"""
extract_authors_local.py
───────────────────────
Extrae perfiles de autores (especialmente ORCIDs y afiliaciones) de la 
producción científica vinculada a la entidad "Mexico" en Neo4j.

Genera un archivo JSON 'data/authors_mexico_seed.json' que servirá como 
entrada para el matching con el dump de ORCID.
"""

import sys
import os
import json
import ast
import argparse
from collections import defaultdict

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

def _parse_meta(raw):
    if isinstance(raw, dict): return raw
    if isinstance(raw, str):
        try: return json.loads(raw)
        except: return ast.literal_eval(raw)
    return {}

def extract_authors(limit: int = None):
    graph = Neo4jGraphStore()
    
    print("📋 Consultando papers de la entidad 'Mexico'...", flush=True)
    query = """
    MATCH (e:Entity {name: 'Mexico'})-[:HAS_PAPER]->(p:Paper)
    WHERE p.raw_metadata IS NOT NULL
    RETURN coalesce(p.doi, p.id) AS doi, p.title AS title, p.year AS year, 
           p.citations AS citations, p.raw_metadata AS meta
    """
    if limit:
        query += f" LIMIT {limit}"
        
    rows = []
    with graph.driver.session() as session:
        result = session.run(query)
        for r in result:
            rows.append(dict(r))
    
    print(f"  → {len(rows):,} papers recuperados.", flush=True)

    # author_id (orcid or name) -> data
    authors_data = {}

    # Extraer autores de metadatos (existente)
    for r in rows:
        meta = _parse_meta(r["meta"])
        meta_low = {k.lower(): v for k, v in meta.items()}
        coauthors = meta_low.get("coauthor_institutions", [])
        incites_authors = meta_low.get("authors", "")
        
        paper_info = {"doi": r["doi"], "title": r["title"], "year": r["year"], "citations": r["citations"] or 0}

        def add_to_dataset(aid, name, orcid, institutions):
            if aid not in authors_data:
                authors_data[aid] = {"name": name, "orcid": orcid, "affiliations": defaultdict(int), "papers": []}
            if name and not authors_data[aid]["name"]: authors_data[aid]["name"] = name
            for inst in institutions:
                if inst.get("name"): authors_data[aid]["affiliations"][inst.get("name")] += 1
            if not any(p["doi"] == paper_info["doi"] for p in authors_data[aid].get("papers", [])):
                authors_data[aid]["papers"].append(paper_info)

        if isinstance(coauthors, list) and len(coauthors) > 0:
            for ca in coauthors:
                orcid = ca.get("orcid")
                if orcid: orcid = orcid.replace("https://orcid.org/", "").strip()
                name = ca.get("author")
                if name or orcid: 
                    # ID limpio: ORCID o Nombre (sin prefijo "name:")
                    aid = orcid if orcid else name
                    if name or orcid: add_to_dataset(aid, name, orcid, ca.get("institutions", []))
        elif isinstance(incites_authors, str) and incites_authors.strip():
            for name in [n.strip() for n in incites_authors.split(";")]:
                if name: add_to_dataset(name, name, None, [])

    # FALLBACK: Si no encontramos suficientes autores en metadatos, consultar el grafo directamente
    print(f"🔍 Buscando autores en relaciones del grafo para papers sin metadatos de autor...", flush=True)
    with graph.driver.session() as session:
        # Buscamos autores vinculados a los mismos papers de la entidad
        q_rels = """
        MATCH (e:Entity {name: 'Mexico'})-[:HAS_PAPER]->(p:Paper)<-[:AUTHORED]-(a:Author)
        RETURN p.id AS doi, a.name AS name, a.orcid AS orcid
        """
        if limit: q_rels += f" LIMIT {limit * 10}" # Más relaciones que papers
        rels = session.run(q_rels)
        for rel in rels:
            doi = rel["doi"]
            name = rel["name"]
            orcid = rel["orcid"]
            if orcid: orcid = orcid.replace("https://orcid.org/", "").strip()
            
            # ID limpio
            aid = orcid if orcid else name
            
            # Solo añadir si no lo procesamos ya (o si queremos completar)
            if aid not in authors_data:
                authors_data[aid] = {"name": name, "orcid": orcid, "affiliations": defaultdict(int), "papers": []}
            
            # Normalizar DOI para búsqueda en rows
            doi_clean = doi.replace("https://doi.org/", "").strip().lower()
            
            if not any(p["doi"].lower().strip().endswith(doi_clean) for p in authors_data[aid]["papers"]):
                # Buscar paper_info en rows
                p_match = next((row for row in rows if row["doi"] and row["doi"].lower().strip().endswith(doi_clean)), None)
                if p_match:
                    authors_data[aid]["papers"].append({
                        "doi": p_match["doi"], "title": p_match["title"], "year": p_match["year"], "citations": p_match["citations"] or 0
                    })
                else:
                    # Si no está en rows (raro), al menos guardar el DOI/id que tenemos del grafo
                    authors_data[aid]["papers"].append({
                        "doi": doi, "title": "Unknown Title", "year": None, "citations": 0
                    })

    # Refinar y exportar
    total_authors = len(authors_data)
    print(f"📊 Procesando {total_authors:,} autores únicos encontrados...", flush=True)

    refined_authors = []
    if total_authors > 0:
        for aid, data in authors_data.items():
            # Sort papers handling None values (use 0 for citations and 0 for year if None)
            sorted_papers = sorted(
                data["papers"], 
                key=lambda x: (x.get("citations") or 0, x.get("year") or 0), 
                reverse=True
            )
            main_aff = None
            if data["affiliations"]:
                main_aff = max(data["affiliations"], key=data["affiliations"].get)
            
            top_dois = [p["doi"] for p in sorted_papers[:5]]
            
            refined_authors.append({
                "id": aid,
                "name": data["name"],
                "orcid": data["orcid"],
                "main_affiliation": main_aff,
                "total_papers": len(data["papers"]),
                "representative_dois": top_dois
            })
    else:
        print("⚠️ No se encontraron autores en los metadatos de los papers procesados.")

    # Guardar resultados
    output_path = os.path.join("data", "authors_mexico_seed.json")
    os.makedirs("data", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(refined_authors, f, ensure_ascii=False, indent=2)

    print(f"✅ Extracción completada. Archivo guardado en: {output_path}")
    graph.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrae metadatos de autores desde Neo4j (Entity: Mexico).")
    parser.add_argument("--limit", type=int, help="Límite de papers a procesar para pruebas")
    args = parser.parse_args()
    extract_authors(limit=args.limit)
