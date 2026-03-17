from neo4j import GraphDatabase
from typing import List, Dict, Any

class Neo4jGraphStore:
    """
    Gestor de la base de datos de grafos Neo4j para almacenar 
    relaciones complejas (citas, coautorías, afiliaciones).
    """
    def __init__(self, uri="bolt://127.0.0.1:7687", user="neo4j", password="password123"):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._init_constraints()

    def close(self):
        self.driver.close()

    def _init_constraints(self):
        """Inicializa restricciones de unicidad para evitar duplicados."""
        queries = [
            "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE",
            "CREATE INDEX paper_doi_idx IF NOT EXISTS FOR (p:Paper) ON (p.doi)",
            "CREATE CONSTRAINT author_id IF NOT EXISTS FOR (a:Author) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT institution_id IF NOT EXISTS FOR (i:Institution) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT academic_id IF NOT EXISTS FOR (a:Academic) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE",
            "CREATE CONSTRAINT funder_id IF NOT EXISTS FOR (f:Funder) REQUIRE f.name IS UNIQUE",
            "CREATE CONSTRAINT award_id IF NOT EXISTS FOR (aw:Award) REQUIRE aw.id IS UNIQUE"
        ]
        with self.driver.session() as session:
            for query in queries:
                try:
                    session.run(query)
                except Exception as e:
                    print(f"Nota: {e} (quizás ya existía u otro problema menor de constraint)")

    def add_paper(self, paper_data: Dict[str, Any]):
        """
        Inserta un paper y sus relaciones (autores, conceptos) en el grafo.
        Soporta autores y conceptos como listas de strings o listas de diccionarios.
        """
        import json
        
        # Preparar data
        data = paper_data.copy()
        
        # Valores por defecto para evitar errores en Cypher
        data.setdefault("citations", 0)
        data.setdefault("doi", "")
        data.setdefault("title", "Unknown Title")
        data.setdefault("year", 0)
        
        # Normalizar autores: string -> {"name": s}
        authors_raw = data.get("authors", [])
        normalized_authors = []
        for a in authors_raw:
            if isinstance(a, str):
                normalized_authors.append({"name": a.strip()})
            elif isinstance(a, dict):
                # Asegurar que tenga la clave 'name'
                if "name" not in a and "display_name" in a:
                    a["name"] = a["display_name"]
                normalized_authors.append(a)
        data["authors"] = normalized_authors

        # Normalizar conceptos/keywords
        concepts_raw = data.get("concepts", [])
        normalized_concepts = []
        for c in concepts_raw:
            if isinstance(c, str):
                normalized_concepts.append({"name": c.strip()})
            elif isinstance(c, dict):
                normalized_concepts.append(c)
        data["concepts"] = normalized_concepts

        raw = data.get("raw_metadata", {}).copy()
        
        # Si hay campos planos, los movemos a raw_metadata
        top_level_keys = [
            "fwci", "citation_normalized_percentile", "is_in_top_1_percent", 
            "is_in_top_10_percent", "OpenAlex_Topics", "open_access"
        ]
        for k in top_level_keys:
            if k in data:
                raw[k] = data[k]

        # Extracción de funders/awards desde raw
        funders_list = []
        awards_list = []
        grants = raw.get("grants", [])
        for g in grants:
            if g.get("funder_display_name"):
                funders_list.append({
                    "name": g.get("funder_display_name"),
                    "openalex_id": g.get("funder") or ""
                })
            if g.get("award_id"):
                awards_list.append(g.get("award_id"))
                
        unique_funders = []
        seen_f = set()
        for f in funders_list:
            if f["name"] not in seen_f:
                unique_funders.append(f)
                seen_f.add(f["name"])
                
        unique_awards = list(set(awards_list))
        
        data["funders"] = unique_funders
        data["awards"]  = unique_awards
        data["raw_metadata_json"] = json.dumps(raw, ensure_ascii=False)

        query = """
        MERGE (p:Paper {id: $paper_id})
        SET p.title = $title, p.doi = $doi, p.year = $year, p.citations = $citations,
            p.raw_metadata = $raw_metadata_json
        
        WITH p
        UNWIND $authors AS author
        MERGE (a:Author {id: author.name})
        SET a.name = author.name
        MERGE (a)-[:AUTHORED]->(p)
        
        WITH p, author, a
        UNWIND (CASE WHEN author.institutions IS NOT NULL THEN author.institutions ELSE [] END) AS inst
        MERGE (i:Institution {id: inst.id})
        SET i.name = inst.name
        MERGE (a)-[:AFFILIATED_WITH]->(i)
        
        WITH p
        UNWIND $concepts AS concept
        MERGE (c:Concept {id: coalesce(concept.id, concept.name)})
        SET c.name = concept.name
        MERGE (p)-[:HAS_CONCEPT]->(c)
        
        WITH p
        FOREACH (funder IN $funders | 
            MERGE (f:Funder {name: funder.name})
            SET f.openalex_id = funder.openalex_id
            MERGE (p)-[:FUNDED_BY]->(f)
        )
        FOREACH (award_id IN $awards | 
            MERGE (aw:Award {id: award_id})
            MERGE (p)-[:HAS_AWARD]->(aw)
        )
        """
        with self.driver.session() as session:
            try:
                session.run(query, **data)
            except Exception as e:
                print(f"Error Neo4j en paper {data.get('paper_id')}: {e}")
            
    def get_author_coauthors(self, author_name: str) -> List[str]:
        """Ejemplo: Encuentra coautores de un investigador dado."""
        query = """
        MATCH (a1:Author {name: $name})-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(a2:Author)
        RETURN DISTINCT a2.name AS coauthor
        """
        with self.driver.session() as session:
            result = session.run(query, name=author_name)
            return [record["coauthor"] for record in result]

    def add_api_paper(self, paper_data: Dict[str, Any], academic_name: str, orcid: str = None, scopus_id: str = None, siia_url: str = None):
        """
        Inserta datos de APIs (OpenAlex/Scopus/ORCID) vinculando el nombre completo (Academic) y el artículo por DOI.
        Conserva todos los campos crudos en raw_metadata_json.
        """
        import json
        data = paper_data.copy()
        if "raw_metadata" in data and isinstance(data["raw_metadata"], dict):
            data["raw_metadata_json"] = json.dumps(data["raw_metadata"], ensure_ascii=False)
        else:
            data["raw_metadata_json"] = "{}"

        # Extracción de funders/awards desde raw_metadata ('grants' en OpenAlex)
        funders_list = []
        awards_list = []
        grants = []
        if isinstance(data.get("raw_metadata"), dict):
            grants = data["raw_metadata"].get("grants", [])
        for g in grants:
            if g.get("funder_display_name"):
                funders_list.append({
                    "name": g.get("funder_display_name"),
                    "openalex_id": g.get("funder") or ""
                })
            if g.get("award_id"):
                awards_list.append(g.get("award_id"))
                
        unique_funders = []
        seen_f = set()
        for f in funders_list:
            if f["name"] not in seen_f:
                unique_funders.append(f)
                seen_f.add(f["name"])
                
        unique_awards = list(set(awards_list))

        # Parametros para la query
        params = {
            "doi": data.get("doi", ""),
            "title": data.get("title", ""),
            "year": int(data.get("year", 0)) if data.get("year") else 0,
            "citations": int(data.get("citations", 0)) if data.get("citations") else 0,
            "raw_metadata": data["raw_metadata_json"],
            "academic_name": academic_name,
            "orcid": orcid,
            "scopus_id": scopus_id,
            "siia_url": siia_url,
            "funders": unique_funders,
            "awards": unique_awards
        }

        # Si no hay DOI válido, no podemos ligarlos estrictamente o creamos id random
        if not params["doi"]:
            import uuid
            params["doi"] = str(uuid.uuid4())

        query = """
        MERGE (a:Academic:Author {id: $academic_name})
        SET a.name = $academic_name
        WITH a
        CALL (a) {
            WITH a WHERE $orcid IS NOT NULL
            SET a.orcid = $orcid
        }
        CALL (a) {
            WITH a WHERE $scopus_id IS NOT NULL
            SET a.scopus_id = $scopus_id
        }
        CALL (a) {
            WITH a WHERE $siia_url IS NOT NULL AND $siia_url <> ''
            SET a.siia_url = $siia_url
        }
        WITH a
        MERGE (p:Paper {id: $doi})
        SET p.doi = $doi, p.title = $title, p.year = $year, p.citations = $citations,
            p.raw_metadata = $raw_metadata

        MERGE (a)-[:AUTHORED]->(p)
        
        WITH p
        FOREACH (funder IN $funders | 
            MERGE (f:Funder {name: funder.name})
            SET f.openalex_id = funder.openalex_id
            MERGE (p)-[:FUNDED_BY]->(f)
        )
        FOREACH (award_id IN $awards | 
            MERGE (aw:Award {id: award_id})
            MERGE (p)-[:HAS_AWARD]->(aw)
        )
        """
        
        with self.driver.session() as session:
            try:
                session.run(query, **params)
            except Exception as e:
                print(f"Error Neo4j en add_api_paper {params['doi']}: {e}")

    def add_entity_paper_link(self, entity_name: str, doi: str):
        """
        Vincula un Entity institucional con un Paper utilizando su DOI.
        """
        if not doi:
            return

        query = """
        MERGE (e:Entity:Institution {name: $entity_name})
        WITH e
        MATCH (p:Paper {doi: $doi})
        MERGE (e)-[:HAS_PAPER]->(p)
        """
        with self.driver.session() as session:
            try:
                session.run(query, entity_name=entity_name, doi=doi)
            except Exception as e:
                pass

    def check_paper_exists(self, paper_id_or_doi: str) -> bool:
        """
        Verifica si un artículo ya existe en Neo4j buscando por su ID (DOI o WOS ID).
        """
        if not paper_id_or_doi:
            return False
        query = "MATCH (p:Paper {id: $id}) RETURN count(p) > 0 as exists"
        # También intentamos buscar por la propiedad .doi si el id no coincide exactamente (por prefijos https://doi.org/)
        query_alt = "MATCH (p:Paper) WHERE p.id = $id OR p.doi = $id OR p.doi = $doi_clean RETURN count(p) > 0 as exists"
        
        doi_clean = paper_id_or_doi.replace("https://doi.org/", "").strip().lower()
        
        with self.driver.session() as session:
            try:
                result = session.run(query_alt, id=paper_id_or_doi, doi_clean=doi_clean)
                record = result.single()
                return record["exists"] if record else False
            except Exception:
                return False

    def add_academic_affiliation(self, academic_name: str, entity_name: str):
        """
        Vincula un Academic con un Entity institucional.
        """
        query = """
        MERGE (e:Entity:Institution {name: $entity_name})
        WITH e
        MATCH (a:Academic:Author {name: $academic_name})
        MERGE (a)-[:AFFILIATED_TO]->(e)
        """
        with self.driver.session() as session:
            try:
                session.run(query, academic_name=academic_name, entity_name=entity_name)
            except Exception as e:
                pass

    def check_academic_exists(self, academic_name: str) -> bool:
        """
        Verifica si un académico ya fue ingestados con sus documentos en Neo4j.
        """
        query = "MATCH (a:Academic {name: $academic_name}) RETURN count(a) > 0 as exists"
        with self.driver.session() as session:
            try:
                result = session.run(query, academic_name=academic_name)
                record = result.single()
                return record["exists"] if record else False
            except Exception as e:
                return False

    def set_academic_snii(self, academic_name: str, is_snii: bool = True):
        """
        Establece o remueve la etiqueta SNII a un académico.
        """
        label_action = "SET a:SNII, a.is_snii = true" if is_snii else "REMOVE a:SNII SET a.is_snii = false"
        query = f"MERGE (a:Academic {{id: $name}}) SET a.name = $name {label_action}"
        with self.driver.session() as session:
            try:
                session.run(query, name=academic_name)
            except Exception as e:
                print(f"Error marcando SNII para {academic_name}: {e}")

    def get_database_statistics(self) -> dict:
        """Obtiene un resumen de la cantidad de nodos por etiqueta y relaciones en el grafo."""
        stats = {"nodes": {}, "relationships": 0}
        
        query_nodes = """
        MATCH (n)
        WITH labels(n) AS labels, count(n) AS count
        UNWIND labels AS label
        RETURN label, sum(count) AS total_count
        """
        query_rels = "MATCH ()-[r]->() RETURN count(r) AS total_rels"
        
        with self.driver.session() as session:
            try:
                result_nodes = session.run(query_nodes)
                for record in result_nodes:
                    stats["nodes"][record["label"]] = record["total_count"]
                    
                result_rels = session.run(query_rels)
                rels_record = result_rels.single()
                if rels_record:
                    stats["relationships"] = rels_record["total_rels"]
            except Exception as e:
                stats["error"] = str(e)
                
        return stats

    def get_sample_graph(self, limit: int = 150) -> dict:
        """Extrae una sub-muestra del grafo para visualización en PyVis interactiva."""
        query = f"MATCH (n)-[r]->(m) RETURN n, r, m LIMIT {limit}"
        nodes = {}
        edges = []
        with self.driver.session() as session:
            try:
                result = session.run(query)
                for record in result:
                    n = record["n"]
                    m = record["m"]
                    r = record["r"]
                    
                    n_id = n.element_id
                    m_id = m.element_id
                    
                    if n_id not in nodes:
                        nodes[n_id] = {
                            "id": n_id, 
                            "label": list(n.labels)[0] if n.labels else "Unknown", 
                            "title": n.get("name", n.get("title", str(n_id)))
                        }
                    if m_id not in nodes:
                        nodes[m_id] = {
                            "id": m_id, 
                            "label": list(m.labels)[0] if m.labels else "Unknown", 
                            "title": m.get("name", m.get("title", str(m_id)))
                        }
                        
                    edges.append({"source": n_id, "target": m_id, "label": r.type})
                return {"nodes": list(nodes.values()), "edges": edges}
            except Exception as e:
                return {"error": str(e)}

    def get_collaboration_sample_graph(self, entity1: str, entity2: str, limit: int = 150) -> dict:
        """
        Extrae una muestra de la colaboración entre dos entidades.
        Retorna artículos co-autoreados por investigadores de ambas entidades.
        """
        query = """
        MATCH (e1:Entity {name: $entity1})<-[:AFFILIATED_TO]-(a1:Academic)-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(a2:Academic)-[:AFFILIATED_TO]->(e2:Entity {name: $entity2})
        WITH e1, e2, p, a1, a2 LIMIT 10
        UNWIND [[a1, 'AUTHORED', p], [a2, 'AUTHORED', p], [a1, 'AFFILIATED_TO', e1], [a2, 'AFFILIATED_TO', e2]] AS triple
        RETURN triple[0] AS n, triple[1] AS rel_type, triple[2] AS m
        """
        nodes = {}
        edges = []
        with self.driver.session() as session:
            try:
                result = session.run(query, entity1=entity1, entity2=entity2)
                for record in result:
                    n = record["n"]
                    m = record["m"]
                    rel_type = record["rel_type"]
                    
                    n_id = n.element_id
                    m_id = m.element_id
                    
                    if n_id not in nodes:
                        nodes[n_id] = {
                            "id": n_id, 
                            "label": list(n.labels)[0] if n.labels else "Unknown", 
                            "title": n.get("name", n.get("title", str(n_id)))
                        }
                    if m_id not in nodes:
                        nodes[m_id] = {
                            "id": m_id, 
                            "label": list(m.labels)[0] if m.labels else "Unknown", 
                            "title": m.get("name", m.get("title", str(m_id)))
                        }
                        
                    edges.append({"source": n_id, "target": m_id, "label": rel_type})
                
                # Si no hay colaboraciones directas, traer algunos de cada una para que no se vea vacío
                if not edges:
                    query_fallback = """
                    MATCH (e1:Entity {name: $entity1})<-[:HAS_PAPER|AFFILIATED_TO*1..2]-(n1)
                    WITH e1, n1 LIMIT 20
                    MATCH (e2:Entity {name: $entity2})<-[:HAS_PAPER|AFFILIATED_TO*1..2]-(n2)
                    WITH e1, n1, e2, n2 LIMIT 40
                    RETURN e1, n1, e2, n2
                    """
                    # Para simplificar el fallback, solo retornamos los nodos de las entidades
                    # pero en el dashboard se manejará mejor.
                    
                return {"nodes": list(nodes.values()), "edges": edges}
            except Exception as e:
                return {"error": str(e)}

    def get_funder_sample_graph(self, entity_name: str, limit: int = 150) -> dict:
        """Extrae una sub-muestra del grafo para una entidad, enfocada en financiadores."""
        query = f"""
        MATCH (e:Entity {{name: $entity_name}})<-[r0:AFFILIATED_TO]-(a:Academic)-[r1:AUTHORED]->(p:Paper)-[r2:FUNDED_BY]->(f:Funder)
        WITH e, a, p, f, r0, r1, r2 LIMIT {limit // 3}
        UNWIND [[a, r0, e], [a, r1, p], [p, r2, f]] AS triple
        RETURN triple[0] AS n, triple[1] AS r, triple[2] AS m
        """
        nodes = {}
        edges = []
        with self.driver.session() as session:
            try:
                result = session.run(query, entity_name=entity_name)
                for record in result:
                    n = record["n"]
                    m = record["m"]
                    r = record["r"]
                    
                    n_id = n.element_id
                    m_id = m.element_id
                    
                    if n_id not in nodes:
                        nodes[n_id] = {
                            "id": n_id, 
                            "label": list(n.labels)[0] if n.labels else "Unknown", 
                            "title": n.get("name", n.get("title", str(n_id)))
                        }
                    if m_id not in nodes:
                        nodes[m_id] = {
                            "id": m_id, 
                            "label": list(m.labels)[0] if m.labels else "Unknown", 
                            "title": m.get("name", m.get("title", str(m_id)))
                        }
                        
                    edges.append({"source": n_id, "target": m_id, "label": r.type})
                return {"nodes": list(nodes.values()), "edges": edges}
            except Exception as e:
                return {"error": str(e)}
