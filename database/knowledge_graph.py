from neo4j import GraphDatabase
from typing import List, Dict, Any

class Neo4jGraphStore:
    """
    Gestor de la base de datos de grafos Neo4j para almacenar 
    relaciones complejas (citas, coautorías, afiliaciones).
    """
    def __init__(self, uri="bolt://127.0.0.1:7687", user="neo4j", password=None):
        # Intentar obtener password de env si no se proporciona
        if not password:
            password = os.getenv("NEO4J_PASS", "password")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self._init_constraints()

    def close(self):
        self.driver.close()

    def _init_constraints(self):
        """Inicializa restricciones de unicidad para evitar duplicados."""
        queries = [
            "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE",
            "CREATE INDEX paper_doi_idx IF NOT EXISTS FOR (p:Paper) ON (p.doi)",
            "CREATE INDEX paper_oa_idx IF NOT EXISTS FOR (p:Paper) ON (p.openalex_id)",
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
        // Nueva lógica de ID: ORCID > ScopusID > Name
        MERGE (a:Author {id: coalesce(author.orcid, author.scopus_id, author.name)})
        SET a.name = author.name
        MERGE (a)-[:AUTHORED]->(p)
        
        WITH p, author, a
        UNWIND (CASE WHEN author.institutions IS NOT NULL THEN author.institutions ELSE [] END) AS inst
        // Priorizar MERGE por nombre para cumplir con restricción de Entity
        MERGE (i:Entity {name: coalesce(inst.name, "Institución Desconocida")})
        SET i:Institution
        WITH p, a, i, inst
        // Solo asignar ID si el nodo no lo tiene y no existe conflicto con otro nodo
        // Esto evita el error Neo.ClientError.Schema.ConstraintValidationFailed
        // Usamos la nueva sintaxis CALL (i, inst) { ... } para evitar el warning de deprecación.
        CALL (i, inst) {
            WITH i, inst WHERE i.id IS NULL AND inst.id IS NOT NULL
            OPTIONAL MATCH (other:Institution {id: inst.id})
            WITH i, inst, other WHERE other IS NULL
            SET i.id = inst.id
        }
        // Enriquecimiento de metadatos ROR/País/Tipo
        CALL (i, inst) {
            WITH i, inst WHERE inst.ror IS NOT NULL SET i.ror = inst.ror
        }
        CALL (i, inst) {
            WITH i, inst WHERE inst.country_code IS NOT NULL SET i.country_code = inst.country_code
        }
        CALL (i, inst) {
            WITH i, inst WHERE inst.type IS NOT NULL SET i.type = inst.type
        }
        MERGE (a)-[:AFFILIATED_TO]->(i)
        
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

    def upsert_institution_metadata(self, name: str, ror: str = None, inst_type: str = None, country_code: str = None):
        """Actualiza metadatos de una institución (ROR, tipo, país) sin borrar los existentes."""
        query = """
        MERGE (i:Entity {name: $name})
        SET i:Institution
        SET i.ror = coalesce($ror, i.ror),
            i.type = coalesce($inst_type, i.type),
            i.country_code = coalesce($country_code, i.country_code)
        """
        with self.driver.session() as session:
            session.run(query, name=name, ror=ror, inst_type=inst_type, country_code=country_code)

    def upsert_geography(self, inst_name: str, state_name: str = None, country_name: str = "Mexico"):
        """Establece la jerarquía geográfica de una institución (País e Entidad Federativa)."""
        query = """
        MERGE (c:Country {name: $country_name})
        
        WITH c
        MERGE (i:Entity {name: $inst_name})
        SET i:Institution
        MERGE (i)-[:LOCATED_IN]->(c)
        
        WITH i, c, $state_name AS s_name
        CALL (i, c, s_name) {
            WITH i, c, s_name WHERE s_name IS NOT NULL AND s_name <> "" AND s_name <> "nan"
            MERGE (s:State {name: s_name})
            MERGE (i)-[:LOCATED_IN]->(s)
            MERGE (s)-[:PART_OF]->(c)
        }
        """
        with self.driver.session() as session:
            try:
                session.run(query, inst_name=inst_name, state_name=state_name, country_name=country_name)
            except Exception as e:
                print(f"Error Neo4j en upsert_geography para institución {inst_name}: {e}")

    def get_author_coauthors(self, author_name: str) -> List[str]:
        """Ejemplo: Encuentra coautores de un investigador dado."""
        query = """
        MATCH (a1:Author {name: $name})-[:AUTHORED]->(p:Paper)<-[:AUTHORED]-(a2:Author)
        RETURN DISTINCT a2.name AS coauthor
        """
        with self.driver.session() as session:
            result = session.run(query, name=author_name)
            return [record["coauthor"] for record in result]

    def add_api_paper(self, paper_data: Dict[str, Any], academic_name: str, orcid: str = None, scopus_id: str = None, 
                     siia_url: str = None, entity_name: str = None,
                     audit_verdict: str = None, audit_reason: str = None, audit_confidence: int = None, audit_timestamp: str = None,
                     match_reason: str = None, discarded_candidates: list = None):
        """
        Inserta datos de APIs (OpenAlex/Scopus/ORCID) vinculando al investigador por un ID robusto y el artículo por DOI.
        ID Jerárquico: ORCID > Scopus_id > Name@Entity > Name
        """
        import json
        
        # 1. Determinar el ID único del académico (Author/Academic)
        if orcid:
            system_id = orcid
        elif scopus_id:
            # Los scopus_ids pueden venir como lista o string separado por ;
            sid = scopus_id.split(';')[0].strip() if ';' in scopus_id else scopus_id
            system_id = f"scopus:{sid}"
        elif entity_name:
            # Si no hay identificador global, usamos Nombre + Entidad para evitar homónimos entre facultades
            system_id = f"{academic_name}@{entity_name}"
        else:
            # Fallback al nombre (único riesgo de colisión)
            system_id = academic_name

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
            "system_id": system_id,
            "academic_name": academic_name,
            "orcid": orcid,
            "scopus_id": scopus_id,
            "siia_url": siia_url,
            "audit_verdict": audit_verdict,
            "audit_reason": audit_reason,
            "audit_confidence": audit_confidence,
            "audit_timestamp": audit_timestamp,
            "match_reason": match_reason,
            "discarded_candidates": json.dumps(discarded_candidates, ensure_ascii=False) if discarded_candidates else None,
            "funders": unique_funders,
            "awards": unique_awards
        }

        # Si no hay DOI válido, no podemos ligarlos estrictamente o creamos id random
        if not params["doi"]:
            import uuid
            params["doi"] = str(uuid.uuid4())

        query = """
        MERGE (a:Author {id: $system_id})
        SET a:Academic, a.name = $academic_name
        WITH a
        CALL (a) {
            WITH a WHERE $orcid IS NOT NULL
            SET a.orcid = $orcid
        }
        CALL (a) {
            WITH a WHERE $openalex_id IS NOT NULL
            SET a.openalex_id = $openalex_id
        }
        CALL (a) {
            WITH a WHERE $scopus_id IS NOT NULL
            SET a.scopus_id = $scopus_id
        }
        CALL (a) {
            WITH a WHERE $siia_url IS NOT NULL AND $siia_url <> ''
            SET a.siia_url = $siia_url
        }
        CALL (a) {
            WITH a WHERE $audit_verdict IS NOT NULL
            SET a.audit_verdict = $audit_verdict,
                a.audit_reason = $audit_reason,
                a.audit_confidence = $audit_confidence,
                a.audit_timestamp = $audit_timestamp
        }
        CALL (a) {
            WITH a WHERE $match_reason IS NOT NULL
            SET a.match_reason = $match_reason,
                a.discarded_candidates = $discarded_candidates
        }
        WITH a
        MERGE (p:Paper {id: $doi})
        SET p.doi = $doi, p.title = $title, p.year = $year, p.citations = $citations,
            p.raw_metadata = $raw_metadata,
            p.openalex_id = $paper_openalex_id

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

    def add_api_papers_batch(self, batch_data: List[Dict[str, Any]]):
        """
        Inserta un lote de artículos de APIs vinculando autores y papers en una sola transacción.
        batch_data: Lista de diccionarios con la estructura requerida por params.
        """
        if not batch_data:
            return

        query = """
        UNWIND $batch AS item
        MERGE (a:Author {id: item.system_id})
        SET a:Academic, a.name = item.academic_name
        
        WITH a, item
        CALL (a, item) {
            WITH a, item WHERE item.openalex_id IS NOT NULL
            SET a.openalex_id = item.openalex_id
        }
        CALL (a, item) {
            WITH a, item WHERE item.orcid IS NOT NULL
            SET a.orcid = item.orcid
        }
        CALL (a, item) {
            WITH a, item WHERE item.scopus_id IS NOT NULL
            SET a.scopus_id = item.scopus_id
        }
        CALL (a, item) {
            WITH a, item WHERE item.audit_verdict IS NOT NULL
            SET a.audit_verdict = item.audit_verdict,
                a.audit_reason = item.audit_reason,
                a.audit_confidence = item.audit_confidence,
                a.audit_timestamp = item.audit_timestamp
        }
        
        WITH a, item
        MERGE (p:Paper {id: item.doi})
        SET p.doi = item.doi, p.title = item.title, p.year = item.year, 
            p.citations = item.citations, p.raw_metadata = item.raw_metadata,
            p.openalex_id = item.paper_openalex_id
        
        MERGE (a)-[:AUTHORED]->(p)
        
        WITH p, item
        FOREACH (funder IN item.funders | 
            MERGE (f:Funder {name: funder.name})
            SET f.openalex_id = funder.openalex_id
            MERGE (p)-[:FUNDED_BY]->(f)
        )
        FOREACH (award_id IN item.awards | 
            MERGE (aw:Award {id: award_id})
            MERGE (p)-[:HAS_AWARD]->(aw)
        )
        """
        with self.driver.session() as session:
            try:
                session.run(query, batch=batch_data)
            except Exception as e:
                print(f"Error Neo4j en lote de {len(batch_data)} artículos: {e}")

    def get_academic_ids(self, academic_name: str) -> dict:
        """
        Recupera los identificadores externos (orcid, openalex_id) de un nodo Academic.
        Útil para enriquecer la ingesta cuando el JSON local no tiene estos datos
        pero ya fueron persistidos desde el pipeline SNII de matching.
        Retorna dict con claves 'orcid' y 'openalex_id' (pueden ser None).
        """
        query = """
        MATCH (a:Academic)
        WHERE a.name = $name OR a.id = $name
        RETURN a.orcid AS orcid, a.openalex_id AS openalex_id
        LIMIT 1
        """
        with self.driver.session() as session:
            try:
                result = session.run(query, name=academic_name)
                record = result.single()
                if record:
                    return {"orcid": record["orcid"], "openalex_id": record["openalex_id"]}
            except Exception as e:
                print(f"[WARN] get_academic_ids para {academic_name}: {e}")
        return {"orcid": None, "openalex_id": None}

    def mark_paper_as_indexed(self, doi: str, source: str):
        """
        Agrega una etiqueta de indización (ej: IndexedOpenAlex) y una propiedad booleana al artículo.
        Fuentes soportadas: 'openalex', 'wos', 'scopus'.
        """
        if not doi: return
        
        label = ""
        prop = ""
        if source.lower() == 'openalex':
            label = "IndexedOpenAlex"
            prop = "indexed_oa"
        elif source.lower() == 'wos':
            label = "IndexedWoS"
            prop = "indexed_wos"
        elif source.lower() == 'scopus':
            label = "IndexedScopus"
            prop = "indexed_scopus"
        else:
            return

        query = f"""
        MATCH (p:Paper {{id: $doi}})
        SET p.{prop} = true
        SET p:{label}
        """
        # Intentar también por propiedad .doi si el id no coincide
        query_alt = f"""
        MATCH (p:Paper) WHERE p.id = $id_raw OR p.doi = $doi_clean
        SET p.{prop} = true
        SET p:{label}
        """
        doi_clean = doi.replace("https://doi.org/", "").strip().lower()
        
        with self.driver.session() as session:
            try:
                session.run(query_alt, id_raw=doi, doi_clean=doi_clean)
            except Exception as e:
                print(f"Error marcando indización {source} para {doi}: {e}")

    def set_paper_openalex_id(self, doi: str, openalex_url: str):
        """Asocia un OpenAlex ID (URL) a un artículo existente."""
        if not doi or not openalex_url: return
        doi_clean = doi.replace("https://doi.org/", "").strip().lower()
        query = """
        MATCH (p:Paper) WHERE p.id = $id_raw OR p.doi = $doi_clean
        SET p.openalex_id = $oa_id
        """
        with self.driver.session() as session:
            try:
                session.run(query, id_raw=doi, doi_clean=doi_clean, oa_id=openalex_url)
            except Exception: pass

    def add_entity_paper_link(self, entity_name: str, doi: str):
        """
        Vincula un Entity institucional con un Paper utilizando su DOI.
        """
        if not doi:
            return

        query = """
        MERGE (e:Entity {name: $entity_name})
        SET e:Institution
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
        MERGE (e:Entity {name: $entity_name})
        SET e:Institution
        WITH e
        MATCH (a:Author {id: $academic_name})
        MERGE (a)-[:AFFILIATED_TO]->(e)
        """
        with self.driver.session() as session:
            try:
                session.run(query, academic_name=academic_name, entity_name=entity_name)
            except Exception as e:
                pass

    def add_academic_full_affiliation(self, academic_name: str, inst_name: str, sub_name: str = None):
        """
        Vincula un Academic con su Institución y Subdependencia (jerárquico).
        """
        # Si no hay subdependencia, usamos solo la institución
        if not sub_name or sub_name == "SIN INFORMACIÓN":
            self.add_academic_affiliation(academic_name, inst_name)
            return

        query = """
        MERGE (i:Entity {name: $inst_name})
        SET i:Institution
        MERGE (s:Entity {name: $sub_name})
        SET s:Subdependency
        MERGE (s)-[:PART_OF]->(i)
        WITH s, i
        MATCH (a:Author {id: $academic_name})
        MERGE (a)-[:AFFILIATED_TO]->(s)
        MERGE (a)-[:AFFILIATED_TO]->(i)
        """
        with self.driver.session() as session:
            try:
                session.run(query, academic_name=academic_name, inst_name=inst_name, sub_name=sub_name)
            except Exception as e:
                print(f"Error en full affiliation para {academic_name}: {e}")

    def check_academic_exists(self, academic_name: str) -> bool:
        """
        Verifica si un académico ya fue ingestados con sus documentos en Neo4j.
        Se considera que existe si tiene al menos un artículo vinculado.
        """
        query = "MATCH (a:Academic {name: $academic_name})-[:AUTHORED]->(:Paper) RETURN count(a) > 0 as exists"
        with self.driver.session() as session:
            try:
                result = session.run(query, academic_name=academic_name)
                record = result.single()
                return record["exists"] if record else False
            except Exception as e:
                return False

    def check_academic_node_exists(self, academic_name: str) -> bool:
        """
        Verifica si un académico existe como nodo en Neo4j,
        independientemente de si tiene papers vinculados o no.
        """
        query = "MATCH (a:Author {id: $academic_name}) RETURN count(a) > 0 as exists"
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
        query = f"MERGE (a:Author {{id: $name}}) SET a:Academic, a.name = $name {label_action}"
        with self.driver.session() as session:
            try:
                session.run(query, name=academic_name)
            except Exception as e:
                print(f"Error marcando SNII para {academic_name}: {e}")

    def update_academic_metadata(self, academic_name: str, orcid: str = None, scopus_id: str = None,
                                  audit_verdict: str = None, audit_reason: str = None, 
                                  audit_confidence: int = None, audit_timestamp: str = None,
                                  match_reason: str = None, is_snii: bool = True,
                                  discarded_candidates: list = None):
        """
        Actualiza metadatos de un académico (ORCID, auditoría, SNII) sin necesidad de papers.
        """
        import json
        system_id = orcid if orcid else academic_name
        
        query = """
        MERGE (a:Author {id: $system_id})
        SET a:Academic, a.name = $academic_name
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
            WITH a WHERE $audit_verdict IS NOT NULL
            SET a.audit_verdict = $audit_verdict,
                a.audit_reason = $audit_reason,
                a.audit_confidence = $audit_confidence,
                a.audit_timestamp = $audit_timestamp
        }
        CALL (a) {
            WITH a WHERE $match_reason IS NOT NULL
            SET a.match_reason = $match_reason,
                a.discarded_candidates = $discarded_candidates
        }
        CALL (a) {
            WITH a WHERE $is_snii = true
            SET a:SNII, a.is_snii = true
        }
        """
        params = {
            "system_id": system_id,
            "academic_name": academic_name,
            "orcid": orcid,
            "scopus_id": scopus_id,
            "audit_verdict": audit_verdict,
            "audit_reason": audit_reason,
            "audit_confidence": audit_confidence,
            "audit_timestamp": audit_timestamp,
            "match_reason": match_reason,
            "discarded_candidates": json.dumps(discarded_candidates, ensure_ascii=False) if discarded_candidates else None,
            "is_snii": is_snii
        }
        with self.driver.session() as session:
            try:
                session.run(query, **params)
            except Exception as e:
                print(f"Error actualizando metadatos para {academic_name}: {e}")

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
        # Query que intenta traer un poco de todo, incluyendo la jerarquía geográfica
        query = f"""
        MATCH (n)-[r]->(m) 
        WITH n, r, m LIMIT {limit}
        RETURN n, r, m
        UNION
        MATCH (i:Institution)-[r:LOCATED_IN]->(s:State)
        RETURN i as n, r, s as m LIMIT 10
        UNION
        MATCH (s:State)-[r:PART_OF]->(c:Country)
        RETURN s as n, r, c as m LIMIT 5
        """
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
