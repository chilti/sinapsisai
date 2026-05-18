import os
from neo4j import GraphDatabase
from typing import List, Dict, Any

class Neo4jGraphStore:
    """
    Gestor de la base de datos de grafos Neo4j para almacenar 
    relaciones complejas (citas, coautorías, afiliaciones).
    """
    def __init__(self, uri=None, user=None, password=None):
        # Prioridad: Argumentos > Variables de Entorno (Standard) > Default Bolt
        if not uri:
            uri = os.getenv("NEO4J_URI") or "bolt://127.0.0.1:7687"
        
        if not user:
            user = os.getenv("NEO4J_USER") or "neo4j"
            
        if not password:
            # Intentar NEO4J_PASS o NEO4J_PASSWORD
            password = os.getenv("NEO4J_PASS") or os.getenv("NEO4J_PASSWORD") or "password"
            
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
            "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (p:Person) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT institution_name IF NOT EXISTS FOR (i:Institution) REQUIRE i.name IS UNIQUE",
            "CREATE CONSTRAINT dependency_id IF NOT EXISTS FOR (d:Dependency) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT subdependency_id IF NOT EXISTS FOR (s:Subdependency) REQUIRE s.id IS UNIQUE",
            "CREATE CONSTRAINT knowledge_area_name IF NOT EXISTS FOR (k:KnowledgeArea) REQUIRE k.name IS UNIQUE",
            "CREATE CONSTRAINT discipline_id IF NOT EXISTS FOR (d:Discipline) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT subdiscipline_id IF NOT EXISTS FOR (sd:Subdiscipline) REQUIRE sd.id IS UNIQUE",
            "CREATE CONSTRAINT specialty_id IF NOT EXISTS FOR (sp:Specialty) REQUIRE sp.id IS UNIQUE",
            "CREATE CONSTRAINT user_orcid IF NOT EXISTS FOR (u:User) REQUIRE u.orcid IS UNIQUE",
            "CREATE CONSTRAINT sdg_name IF NOT EXISTS FOR (s:SDG) REQUIRE s.name IS UNIQUE",
            "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT topic_subfield_id IF NOT EXISTS FOR (t:TopicSubfield) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT topic_field_id IF NOT EXISTS FOR (t:TopicField) REQUIRE t.id IS UNIQUE",
            "CREATE CONSTRAINT topic_domain_name IF NOT EXISTS FOR (t:TopicDomain) REQUIRE t.name IS UNIQUE",
            
            # Indices de performance
            "CREATE INDEX paper_year_idx IF NOT EXISTS FOR (p:Paper) ON (p.year)",
            "CREATE INDEX paper_fwci_idx IF NOT EXISTS FOR (p:Paper) ON (p.fwci)",
            
            # Full-text indices (opcional, para buscadores)
            "CREATE FULLTEXT INDEX paper_title_search IF NOT EXISTS FOR (p:Paper) ON EACH [p.title]",
            "CREATE FULLTEXT INDEX person_name_search IF NOT EXISTS FOR (n:Person) ON EACH [n.fullname]",
            "CREATE FULLTEXT INDEX institution_name_search IF NOT EXISTS FOR (n:Institution|Dependency|Subdependency) ON EACH [n.name]"
        ]
        with self.driver.session() as session:
            # Limpieza preventiva de etiquetas antiguas
            try:
                session.run("DROP CONSTRAINT entity_id IF EXISTS")
            except: pass
                
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
        // Nueva lógica de ID: CVU > ORCID > ScopusID > Name
        MERGE (a:Person {id: coalesce(author.cvu, author.orcid, author.scopus_id, author.name)})
        SET a.fullname = author.name
        SET a:Author
        MERGE (a)-[:AUTHOR_OF]->(p)
        
        WITH p, author, a
        UNWIND (CASE WHEN author.institutions IS NOT NULL THEN author.institutions ELSE [] END) AS inst
        // Usamos la etiqueta base Institution para afiliaciones generales de papers
        MERGE (i:Institution {name: coalesce(inst.name, "Institución Desconocida")})
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
        MERGE (i:Institution {name: $name})
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
        MERGE (i:Institution {name: $inst_name})
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
        MATCH (a1:Author {name: $name})-[:AUTHOR_OF]->(p:Paper)<-[:AUTHOR_OF]-(a2:Author)
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
        
        # 1. Determinar el ID único del académico (Person)
        if cvu:
            system_id = str(cvu)
        elif orcid:
            system_id = orcid
        elif scopus_id:
            # Los scopus_ids pueden venir como lista o string separado por ;
            sid = scopus_id.split(';')[0].strip() if ';' in scopus_id else scopus_id
            system_id = f"scopus:{sid}"
        elif entity_name:
            # Si no hay identificador global, usamos Nombre + Entidad para evitar homónimos
            system_id = f"{academic_name}@{entity_name}"
        else:
            # Fallback al nombre
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
        MERGE (a:Person {id: $system_id})
        SET a:Author, a.fullname = $academic_name, a.is_snii = (CASE WHEN $cvu IS NOT NULL THEN true ELSE a.is_snii END)
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
        WITH a
        MERGE (p:Paper {id: $doi})
        SET p.doi = $doi, p.title = $title, p.year = $year, p.citations = $citations,
            p.raw_metadata = $raw_metadata,
            p.openalex_id = $paper_openalex_id

        MERGE (a)-[:AUTHOR_OF]->(p)
        
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
        Versión optimizada para ingesta masiva de artículos vinculados a Person.
        """
        if not batch_data:
            return

        for row in batch_data:
            self.ingest_paper_row(row)

    def ingest_paper_row(self, row: Dict[str, Any]):
        query = """
        // 1. Nodo del Paper y Fuentes
        MERGE (art:Paper {id: $paper_id})
        ON CREATE SET 
            art.title = $title,
            art.year = $year,
            art.doi = $doi,
            art.citations = $citations,
            art.openalex_id = $openalex_id,
            art.wos_id = $wos_id,
            art.scopus_id = $scopus_id,
            art.fwci = $fwci,
            art.sources = $initial_sources
        ON MATCH SET
            art.citations = COALESCE($citations, art.citations),
            art.fwci = COALESCE(art.fwci, $fwci),
            art.sources = apoc.coll.toSet(art.sources + $initial_sources)

        // 2. Jerarquía de Topics (Domain -> Field -> Subfield -> Topic)
        MERGE (dom:TopicDomain {name: $topic_domain})
        
        MERGE (fld:TopicField {id: $topic_domain + "||" + $topic_field})
        SET fld.name = $topic_field
        MERGE (fld)-[:PART_OF]->(dom)

        MERGE (subf:TopicSubfield {id: $topic_domain + "||" + $topic_field + "||" + $topic_subfield})
        SET subf.name = $topic_subfield
        MERGE (subf)-[:PART_OF]->(fld)

        MERGE (top:Topic {id: $topic_domain + "||" + $topic_field + "||" + $topic_subfield + "||" + $topic_name})
        SET top.name = $topic_name
        MERGE (top)-[:PART_OF]->(subf)
        
        MERGE (art)-[:HAS_TOPIC]->(top)

        // 3. Objetivos de Desarrollo Sostenible (SDG)
        FOREACH (sdg_name IN $sdgs |
            MERGE (s:SDG {name: sdg_name})
            MERGE (art)-[:CONTRIBUTES_TO]->(s)
        )

        // 4. Relación de Autoría (Opcional si el autor existe)
        WITH art
        OPTIONAL MATCH (p:Person {id: $author_cvu})
        FOREACH (_ IN CASE WHEN p IS NOT NULL THEN [1] ELSE [] END |
            MERGE (p)-[r:AUTHOR_OF]->(art)
            SET r.author_order = $author_order,
                r.is_corresponding = $is_corresponding
        )

        // 5. Afiliación Institucional (Crédito)
        WITH art
        OPTIONAL MATCH (sub:Subdependency {id: $inst_name + "||" + $dep_name + "||" + $sub_name})
        OPTIONAL MATCH (dep:Dependency {id: $inst_name + "||" + $dep_name})
        OPTIONAL MATCH (inst:Institution {name: $inst_name})
        
        WITH art, COALESCE(sub, dep, inst) AS targetNode
        WHERE targetNode IS NOT NULL
        MERGE (art)-[:CREDITED_TO]->(targetNode)
        """

        # Manejo de IDs y Fuentes (Estrategia de Identidad Flexible)
        doi = row.get('doi')
        oa_id = row.get('openalex_id')
        wos_id = row.get('wos_id')
        scopus_id = row.get('scopus_id')
        
        # Jerarquía de Identidad: DOI > OpenAlex > WoS > Scopus
        paper_id = doi if (doi and str(doi).strip().lower() != "none") else oa_id
        if not paper_id:
            paper_id = wos_id if wos_id else scopus_id
        
        if not paper_id:
            # Si de plano no tiene nada, no podemos crear el nodo
            return

        detected_sources = []
        if row.get('wos_id'): detected_sources.append('WoS')
        if row.get('scopus_id'): detected_sources.append('Scopus')
        if oa_id: detected_sources.append('OpenAlex')
        if row.get('semantic_id'): detected_sources.append('SemanticScholar')

        # Convertir SDG a lista si viene como string único o nulo
        sdgs = row.get('sdgs', [])
        if isinstance(sdgs, str): sdgs = [sdgs]
        if sdgs is None: sdgs = []

        params = {
            "paper_id": paper_id,
            "title": row.get('title'),
            "year": row.get('year'),
            "doi": doi,
            "citations": row.get('citations', 0),
            "openalex_id": oa_id,
            "wos_id": row.get('wos_id'),
            "scopus_id": row.get('scopus_id'),
            "fwci": row.get('fwci'),
            "initial_sources": detected_sources,
            "topic_domain": row.get('topic_domain') or 'Unknown Domain',
            "topic_field": row.get('topic_field') or 'Unknown Field',
            "topic_subfield": row.get('topic_subfield') or 'Unknown Subfield',
            "topic_name": row.get('topic_name') or 'Unknown Topic',
            "sdgs": sdgs,
            "author_cvu": str(row.get('system_id') or row.get('cvu')) if (row.get('system_id') or row.get('cvu')) else None,
            "author_order": row.get('author_position'),
            "is_corresponding": row.get('is_corresponding', False),
            "inst_name": str(row.get('institucion')).strip().upper() if row.get('institucion') else None,
            "dep_name": str(row.get('dependencia')).strip().upper() if row.get('dependencia') else None,
            "sub_name": str(row.get('subdependencia')).strip().upper() if row.get('subdependencia') else None
        }

        with self.driver.session() as session:
            try:
                session.run(query, **params)
            except Exception as e:
                print(f"Error ingesting paper row {paper_id}: {e}")

    def get_academic_ids(self, academic_name: str) -> dict:
        """
        Recupera los identificadores externos (orcid, openalex_id) de un nodo Academic.
        Útil para enriquecer la ingesta cuando el JSON local no tiene estos datos
        pero ya fueron persistidos desde el pipeline SNII de matching.
        Retorna dict con claves 'orcid' y 'openalex_id' (pueden ser None).
        """
        query = """
        MATCH (a:Person)
        WHERE a.fullname = $name OR a.id = $name
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

    def set_paper_openalex_id(self, doi: str, openalex_id: str):
        """
        Establece la propiedad openalex_id en un nodo Paper identificado por su DOI.
        Se busca tanto por p.id como por p.doi para cubrir ambos esquemas.
        """
        if not doi or not openalex_id:
            return
        doi_clean = doi.replace("https://doi.org/", "").strip().lower()
        with self.driver.session() as session:
            try:
                session.run(
                    """
                    MATCH (p:Paper)
                    WHERE p.id = $id_raw OR p.doi = $doi_clean
                    SET p.openalex_id = $oa_id
                    """,
                    id_raw=doi, doi_clean=doi_clean, oa_id=openalex_id
                )
            except Exception as e:
                print(f"Error estableciendo openalex_id para {doi}: {e}")

    def ingest_academic_row(self, row: Dict[str, Any]):
        query = """
        // 1. Identificación del Académico
        MERGE (p:Person {id: $person_id})
        SET p.fullname = $nombre,
            p.nivel = $nivel,
            p.entidad_federativa = $estado,
            p.is_snii = $is_snii

        // 2. Jerarquía Institucional
        MERGE (inst:Institution {name: $institucion})
        MERGE (dep:Dependency {id: $institucion + "||" + $dependencia})
        SET dep.name = $dependencia
        MERGE (dep)-[:PART_OF]->(inst)

        FOREACH (_ IN CASE WHEN $subdependencia <> "SIN INFORMACIÓN" AND $subdependencia <> "NO APLICA" AND $subdependencia <> "" THEN [1] ELSE [] END |
            MERGE (sub:Subdependency {id: $institucion + "||" + $dependencia + "||" + $subdependencia})
            SET sub.name = $subdependencia
            MERGE (sub)-[:PART_OF]->(dep)
            MERGE (p)-[:AFFILIATED_TO]->(sub)
        )

        WITH p, dep, $area AS areaName, $disciplina AS discName, $subdisciplina AS subName, $especialidad AS espName
        WHERE NOT (p)-[:AFFILIATED_TO]->(:Subdependency)
        MERGE (p)-[:AFFILIATED_TO]->(dep)

        // 3. Jerarquía de Conocimiento (Normalizada)
        WITH p, areaName, discName, subName, espName
        MERGE (a:KnowledgeArea {name: areaName})

        // Disciplina
        FOREACH (_ IN CASE WHEN discName <> "SIN INFORMACIÓN" AND discName <> "" THEN [1] ELSE [] END |
            MERGE (d:Discipline {id: areaName + "||" + discName})
            SET d.name = discName
            MERGE (d)-[:BELONGS_TO]->(a)
            MERGE (p)-[:SPECIALIZED_IN]->(d)
        )

        // Subdisciplina (Referenciando el ID de la disciplina directamente)
        FOREACH (_ IN CASE WHEN subName <> "SIN INFORMACIÓN" AND subName <> "" THEN [1] ELSE [] END |
            MERGE (sd:Subdiscipline {id: areaName + "||" + discName + "||" + subName})
            SET sd.name = subName
            // Para conectar jerárquicamente dentro de FOREACH sin MATCH:
            MERGE (parentD:Discipline {id: areaName + "||" + discName})
            MERGE (sd)-[:BELONGS_TO]->(parentD)
            MERGE (p)-[:SPECIALIZED_IN]->(sd)
        )

        // Especialidad
        FOREACH (_ IN CASE WHEN espName <> "SIN INFORMACIÓN" AND espName <> "" THEN [1] ELSE [] END |
            MERGE (esp:Specialty {id: areaName + "||" + discName + "||" + subName + "||" + espName})
            SET esp.name = espName
            MERGE (parentSD:Subdiscipline {id: areaName + "||" + discName + "||" + subName})
            MERGE (esp)-[:BELONGS_TO]->(parentSD)
            MERGE (p)-[:SPECIALIZED_IN]->(esp)
        )

        // Conexión elástica final
        WITH p, a
        WHERE NOT (p)-[:SPECIALIZED_IN]->(:Discipline) 
          AND NOT (p)-[:SPECIALIZED_IN]->(:Subdiscipline) 
          AND NOT (p)-[:SPECIALIZED_IN]->(:Specialty)
        MERGE (p)-[:SPECIALIZED_IN]->(a)
        """

        # Lógica de identificación (SNII vs Externo)
        cvu = row.get('CVU') or row.get('CVU padrón corregido')
        if cvu and str(cvu).strip().isdigit():
            person_id = str(cvu).strip()
            is_snii = True
        else:
            nombre_raw = str(row.get('NOMBRE DEL INVESTIGADOR', ''))
            person_id = "EXT_" + "".join(filter(str.isalnum, nombre_raw)).upper()
            is_snii = False

        # Limpieza de strings
        def clean(val):
            return str(val).strip().upper() if val else "SIN INFORMACIÓN"

        params = {
            "person_id": person_id,
            "nombre": row.get('NOMBRE DEL INVESTIGADOR'),
            "nivel": row.get('NIVEL'),
            "estado": row.get('ENTIDAD DE ACREDITACIÓN'),
            "is_snii": is_snii,
            "institucion": clean(row.get('INSTITUCION DE ACREDITACION') or row.get('INSTITUCIÓN DE ACREDITACIÓN')),
            "dependencia": clean(row.get('DEPENDENCIA DE ACREDITACIÓN')),
            "subdependencia": clean(row.get('SUBDEPENDENCIA DE ACREDITACIÓN')),
            "area": clean(row.get('ÁREA DE CONOCIMIENTO')),
            "disciplina": clean(row.get('DISCIPLINA')),
            "subdisciplina": clean(row.get('SUBDISCIPLINA')),
            "especialidad": clean(row.get('ESPECIALIDAD'))
        }

        with self.driver.session() as session:
            try:
                session.run(query, **params)
            except Exception as e:
                print(f"Error ingesting academic row {person_id}: {e}")


    def upsert_hierarchical_entity_metadata(self, inst_name: str, dep_name: str, sub_name: str, label: str, ror: str = None, openalex_id: str = None):
        """
        Actualiza metadatos de una entidad asegurando que pertenece a la jerarquía correcta.
        Utiliza IDs compuestos para evitar colisiones y el separador ||.
        """
        if not inst_name: return
        
        # Determinar el nodo objetivo y su jerarquía
        if label == 'Institution':
            query = """
            MERGE (e:Institution {name: $inst_name})
            SET e.ror = coalesce($ror, e.ror),
                e.openalex_id = coalesce($openalex_id, e.openalex_id)
            """
        elif label == 'Dependency':
            query = """
            MERGE (i:Institution {name: $inst_name})
            MERGE (i)<-[:PART_OF]-(e:Dependency {id: $inst_name + "||" + $dep_name})
            SET e.name = $dep_name,
                e.ror = coalesce($ror, e.ror),
                e.openalex_id = coalesce($openalex_id, e.openalex_id)
            """
        elif label == 'Subdependency':
            query = """
            MERGE (i:Institution {name: $inst_name})
            MERGE (i)<-[:PART_OF]-(d:Dependency {id: $inst_name + "||" + $dep_name})
            SET d.name = $dep_name
            MERGE (d)<-[:PART_OF]-(e:Subdependency {id: $inst_name + "||" + $dep_name + "||" + $sub_name})
            SET e.name = $sub_name,
                e.ror = coalesce($ror, e.ror),
                e.openalex_id = coalesce($openalex_id, e.openalex_id)
            """
        else:
            return

        with self.driver.session() as session:
            try:
                session.run(query, inst_name=inst_name, dep_name=dep_name, sub_name=sub_name, ror=ror, openalex_id=openalex_id)
            except Exception as e:
                print(f"Error Neo4j en upsert_hierarchical_entity_metadata ({label}): {e}")


    def upsert_entity_level_metadata(self, name: str, label: str, ror: str = None, openalex_id: str = None):
        if not name or not label: return
        query = f"""
        MATCH (e:{label} {{name: $name}})
        SET e.ror = coalesce($ror, e.ror),
            e.openalex_id = coalesce($openalex_id, e.openalex_id)
        """
        with self.driver.session() as session:
            session.run(query, name=name, ror=ror, openalex_id=openalex_id)

    def add_hierarchical_entity_paper_link(self, inst_name: str, dep_name: str, sub_name: str, label: str, doi: str):
        """
        Vincula un Paper a una entidad (Inst/Dep/Sub) asegurando el contexto jerárquico y el uso de IDs compuestos.
        """
        if not doi or not inst_name: return
        
        # Determinar el MATCH jerárquico según el label
        if label == 'Institution':
            query = """
            MATCH (e:Institution {name: $inst_name})
            MATCH (p:Paper {id: $doi})
            MERGE (p)-[:CREDITED_TO]->(e)
            """
        elif label == 'Dependency':
            query = """
            MATCH (e:Dependency {id: $inst_name + "||" + $dep_name})
            MATCH (p:Paper {id: $doi})
            MERGE (p)-[:CREDITED_TO]->(e)
            """
        elif label == 'Subdependency':
            query = """
            MATCH (e:Subdependency {id: $inst_name + "||" + $dep_name + "||" + $sub_name})
            MATCH (p:Paper {id: $doi})
            MERGE (p)-[:CREDITED_TO]->(e)
            """
        else:
            return

        with self.driver.session() as session:
            try:
                session.run(query, inst_name=inst_name, dep_name=dep_name, sub_name=sub_name, doi=doi)
            except Exception as e:
                print(f"Error Neo4j en add_hierarchical_entity_paper_link ({label}): {e}")

    def add_flexible_entity_paper_link(self, entity_name: str, label: str, doi: str):
        """
        Versión simplificada para compatibilidad. Si es posible, usar add_hierarchical_entity_paper_link.
        """
        if not doi or not entity_name: return
        query = f"""
        MATCH (e:{label} {{name: $entity_name}})
        WITH e
        MATCH (p:Paper {{doi: $doi}})
        MERGE (e)-[:HAS_PAPER]->(p)
        """
        with self.driver.session() as session:
            try: session.run(query, entity_name=entity_name, doi=doi)
            except: pass


    def add_entity_paper_link(self, entity_name: str, doi: str):
        """
        Vincula un Entity institucional con un Paper utilizando su DOI.
        """
        if not doi:
            return

        query = """
        MERGE (i:Institution {name: $entity_name})
        WITH i
        MATCH (p:Paper {doi: $doi})
        MERGE (i)-[:HAS_PAPER]->(p)
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
        MERGE (i:Institution {name: $entity_name})
        WITH i
        MATCH (a:Author {id: $academic_name})
        MERGE (a)-[:AFFILIATED_TO]->(i)
        """
        with self.driver.session() as session:
            try:
                session.run(query, academic_name=academic_name, entity_name=entity_name)
            except Exception as e:
                pass

    def add_academic_full_affiliation(self, academic_id: str, inst_name: str, dep_name: str = None, sub_name: str = None):
        """
        Vincula un Person con su Institución, Dependencia y Subdependencia (jerárquico),
        respetando la estructura de tres niveles y el separador ||.
        """
        # Limpieza de valores nulos o "SIN INFORMACION"
        def _is_valid(val):
            return val and str(val).upper() not in ["SIN INFORMACIÓN", "SIN INFORMACIN", "NO APLICA", "SIN INSTITUCION", "SIN INSTITUCIN", "NAN", "NONE", "NULL"]

        inst = inst_name if _is_valid(inst_name) else "SIN INSTITUCION"
        dep = dep_name if _is_valid(dep_name) else None
        sub = sub_name if _is_valid(sub_name) else None

        query = """
        MATCH (a:Person {id: $academic_id})
        MERGE (i:Institution {name: $inst})
        
        WITH a, i
        CALL (a, i) {
            // Caso: Hay Subdependencia
            WITH a, i WHERE $sub IS NOT NULL AND $dep IS NOT NULL
            MERGE (d:Dependency {id: $inst + "||" + $dep})
            SET d.name = $dep
            MERGE (d)-[:PART_OF]->(i)
            MERGE (s:Subdependency {id: $inst + "||" + $dep + "||" + $sub})
            SET s.name = $sub
            MERGE (s)-[:PART_OF]->(d)
            MERGE (a)-[:AFFILIATED_TO]->(s)
            RETURN count(*) AS sub_c
        }
        CALL (a, i) {
            // Caso: Hay Dependencia pero NO subdependencia
            WITH a, i WHERE $dep IS NOT NULL AND $sub IS NULL
            MERGE (d:Dependency {id: $inst + "||" + $dep})
            SET d.name = $dep
            MERGE (d)-[:PART_OF]->(i)
            MERGE (a)-[:AFFILIATED_TO]->(d)
            RETURN count(*) AS dep_c
        }
        CALL (a, i) {
            // Caso: Solo Institución
            WITH a, i WHERE $dep IS NULL AND $sub IS NULL
            MERGE (a)-[:AFFILIATED_TO]->(i)
            RETURN count(*) AS inst_c
        }
        RETURN count(*) AS done
        """
        
        with self.driver.session() as session:
            try:
                session.run(query, academic_id=academic_id, inst=inst, dep=dep, sub=sub)
            except Exception as e:
                print(f"Error en full affiliation para {academic_id}: {e}")



    def check_academic_exists(self, academic_id_or_name: str) -> bool:
        """
        Verifica si un académico ya fue ingestados con sus documentos en Neo4j.
        Se considera que existe si tiene al menos un artículo vinculado.
        """
        query = "MATCH (a:Person)-[:AUTHOR_OF]->(:Paper) WHERE a.id = $val OR a.fullname = $val RETURN count(a) > 0 as exists"
        with self.driver.session() as session:
            try:
                result = session.run(query, val=academic_id_or_name)
                record = result.single()
                return record["exists"] if record else False
            except Exception as e:
                return False

    def check_academic_node_exists(self, academic_id: str) -> bool:
        """
        Verifica si un académico existe como nodo en Neo4j (Person).
        """
        query = "MATCH (a:Person {id: $academic_id}) RETURN count(a) > 0 as exists"
        with self.driver.session() as session:
            try:
                result = session.run(query, academic_id=academic_id)
                record = result.single()
                return record["exists"] if record else False
            except Exception as e:
                return False


    def set_academic_snii(self, academic_id: str, is_snii: bool = True):
        """
        Establece o remueve la etiqueta SNII a un académico.
        """
        label_action = "SET a:SNII, a.is_snii = true" if is_snii else "REMOVE a:SNII SET a.is_snii = false"
        query = f"MATCH (a:Person {{id: $id}}) {label_action}"
        with self.driver.session() as session:
            try:
                session.run(query, id=academic_id)
            except Exception as e:
                print(f"Error marcando SNII para {academic_id}: {e}")

    def update_academic_metadata(self, academic_id: str, cvu: str = None, orcid: str = None, scopus_id: str = None,
                                  audit_verdict: str = None, audit_reason: str = None, 
                                  audit_confidence: int = None, audit_timestamp: str = None,
                                  match_reason: str = None, is_snii: bool = True,
                                  discarded_candidates: list = None, siia: str = None):
        """
        Actualiza metadatos de un académico (CVU, ORCID, auditoría, SNII, SIIA, Scopus).
        """
        import json
        
        # Normalizar scopus_id a lista si viene como string
        sc_ids = []
        if scopus_id:
            if isinstance(scopus_id, list): sc_ids = scopus_id
            else: sc_ids = [s.strip() for s in str(scopus_id).split(';') if s.strip()]

        query = """
        MERGE (a:Person {id: $academic_id})
        SET a:Author
        SET a.is_snii = (CASE WHEN $is_snii = true THEN true ELSE coalesce(a.is_snii, false) END)
        WITH a
        CALL (a) {
            WITH a WHERE $orcid IS NOT NULL AND $orcid <> ""
            SET a.orcid = $orcid
        }
        CALL (a) {
            WITH a WHERE $cvu IS NOT NULL AND $cvu <> ""
            SET a.cvu = $cvu
        }
        CALL (a) {
            WITH a WHERE $siia IS NOT NULL AND $siia <> ""
            SET a.siia = $siia
        }
        CALL (a) {
            WITH a WHERE size($sc_ids) > 0
            SET a.scopus_ids = apoc.coll.toSet(coalesce(a.scopus_ids, []) + $sc_ids)
        }
        """
        params = {
            "academic_id": academic_id,
            "orcid": orcid,
            "cvu": cvu,
            "sc_ids": sc_ids,
            "siia": siia,
            "audit_verdict": audit_verdict,
            "audit_reason": audit_reason,
            "audit_confidence": audit_confidence,
            "audit_timestamp": audit_timestamp,
            "is_snii": is_snii
        }
        with self.driver.session() as session:
            try:
                session.run(query, **params)
            except Exception as e:
                print(f"Error actualizando metadatos para {academic_id}: {e}")

    def get_total_paper_census(self, inst: str, dep: str = None, sub: str = None) -> int:
        """
        Obtiene el conteo total de papers únicos vinculados a una entidad en Neo4j.
        Sigue la jerarquía: Inst <- Dep <- Sub (Firma física del paper)
        """
        params = {"inst": inst}
        
        # Caso 1: Jerarquía Completa (Dep + Sub)
        if dep and sub and dep != 'SIN INFORMACIÓN' and sub != 'SIN INFORMACIÓN':
            query = """
            MATCH (i:Institution {name: $inst})<-[:PART_OF]-(d:Dependency {id: $inst + "||" + $dep})<-[:PART_OF]-(s:Subdependency {id: $inst + "||" + $dep + "||" + $sub})
            MATCH (p:Paper)-[:CREDITED_TO]->(s)
            RETURN count(DISTINCT p) as total
            """
            params["dep"] = dep
            params["sub"] = sub
        
        # Caso 2: Solo una entidad (puede ser Dep o Sub)
        elif (dep or sub) and (dep != 'SIN INFORMACIÓN' or sub != 'SIN INFORMACIÓN'):
            entity_name = dep if dep and dep != 'SIN INFORMACIÓN' else sub
            query = """
            MATCH (i:Institution {name: $inst})<-[:PART_OF*1..2]-(e)
            WHERE (e:Dependency OR e:Subdependency) AND e.name = $entity
            OPTIONAL MATCH (e)<-[:PART_OF*0..1]-(child)
            WITH e, collect(child) + e as targets
            UNWIND targets as t
            MATCH (p:Paper)-[:CREDITED_TO]->(t)
            RETURN count(DISTINCT p) as total
            """
            params["entity"] = entity_name
            
        # Caso 3: Toda la Institución
        else:
            query = """
            MATCH (i:Institution {name: $inst})
            OPTIONAL MATCH (i)<-[:PART_OF*1..2]-(child)
            WITH i, collect(child) + i as targets
            UNWIND targets as t
            MATCH (p:Paper)-[:CREDITED_TO]->(t)
            RETURN count(DISTINCT p) as total
            """
            
        with self.driver.session() as session:
            try:
                res = session.run(query, **params).single()
                return res["total"] if res else 0
            except Exception as e:
                print(f"Error en get_total_paper_census: {e}")
                return 0

    def get_academic_paper_census(self, name_or_id: str) -> int:
        """
        Obtiene el conteo total de papers únicos vinculados a un académico en Neo4j.
        Busca por ID de persona o por nombre completo/id.
        """
        query = """
        MATCH (a:Person)
        WHERE a.id = $val OR a.fullname = $val OR a.name = $val
        MATCH (a)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
        RETURN count(DISTINCT p) as total
        """
        with self.driver.session() as session:
            try:
                res = session.run(query, val=name_or_id).single()
                return res["total"] if res else 0
            except Exception as e:
                print(f"Error en get_academic_paper_census para {name_or_id}: {e}")
                return 0

    def get_total_capacity_census(self, inst: str, dep: str = None, sub: str = None) -> int:
        """
        Calcula la Capacidad Instalada (Censo): Unión única de todos los papers 
        de los académicos vinculados a esta entidad jerárquica.
        """
        def _is_valid(val):
            return val and str(val).upper() not in ["SIN INFORMACIÓN", "SIN INFORMACIN", "NO APLICA", "SIN INSTITUCION", "SIN INSTITUCIN", "NAN", "NONE", "NULL"]

        # Determinar el nodo objetivo según la jerarquía (usando IDs compuestos para evitar homónimos)
        if _is_valid(sub):
            query = """
            MATCH (i:Institution {name: $inst})<-[:PART_OF]-(d:Dependency {id: $inst + "||" + $dep})<-[:PART_OF]-(e:Subdependency {id: $inst + "||" + $dep + "||" + $sub})
            MATCH (a:Person)-[:AFFILIATED_TO]->(e)
            MATCH (a)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
            RETURN count(DISTINCT p) as total
            """
            params = {"inst": inst, "dep": dep, "sub": sub}
        elif _is_valid(dep):
            query = """
            MATCH (i:Institution {name: $inst})<-[:PART_OF*1..2]-(e)
            WHERE (e:Dependency OR e:Subdependency) AND e.name = $entity
            OPTIONAL MATCH (e)<-[:PART_OF*0..1]-(child)
            WITH e, collect(child) + e as targets
            UNWIND targets as t
            MATCH (a:Person)-[:AFFILIATED_TO]->(t)
            MATCH (a)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
            RETURN count(DISTINCT p) as total
            """
            params = {"inst": inst, "entity": dep}
        else:
            query = """
            MATCH (i:Institution {name: $inst})
            OPTIONAL MATCH (i)<-[:PART_OF*1..2]-(child)
            WITH i, collect(child) + i as targets
            UNWIND targets as t
            MATCH (a:Person)-[:AFFILIATED_TO]->(t)
            MATCH (a)-[:AUTHOR_OF|AUTHORED]->(p:Paper)
            RETURN count(DISTINCT p) as total
            """
            params = {"inst": inst}

        with self.driver.session() as session:
            try:
                res = session.run(query, **params).single()
                return res["total"] if res else 0
            except Exception as e:
                print(f"Error en get_total_capacity_census: {e}")
                return 0

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
        """Extrae una sub-muestra del grafo para visualización interactiva."""
        query = f"""
        MATCH (n)-[r]->(m) 
        WHERE NOT n:Paper AND NOT m:Paper
        WITH n, r, m LIMIT {limit}
        RETURN n, r, m
        UNION
        MATCH (p:Person)-[r:AUTHOR_OF]->(pa:Paper)
        RETURN p as n, r, pa as m LIMIT 20
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
                            "title": n.get("fullname", n.get("name", n.get("title", str(n_id))))
                        }
                    if m_id not in nodes:
                        nodes[m_id] = {
                            "id": m_id, 
                            "label": list(m.labels)[0] if m.labels else "Unknown", 
                            "title": m.get("fullname", m.get("name", m.get("title", str(m_id))))
                        }
                        
                    edges.append({"source": n_id, "target": m_id, "label": r.type})
                return {"nodes": list(nodes.values()), "edges": edges}
            except Exception as e:
                return {"error": str(e)}

    def get_collaboration_sample_graph(self, entity1: str, entity2: str, limit: int = 150) -> dict:
        """
        Extrae una muestra de la colaboración entre dos entidades usando la nueva jerarquía.
        """
        query = """
        MATCH (e1) WHERE (e1:Institution OR e1:Dependency OR e1:Subdependency) AND e1.name = $entity1
        MATCH (e2) WHERE (e2:Institution OR e2:Dependency OR e2:Subdependency) AND e2.name = $entity2
        MATCH (e1)<-[:AFFILIATED_TO]-(a1:Person)-[:AUTHOR_OF]->(p:Paper)<-[:AUTHOR_OF]-(a2:Person)-[:AFFILIATED_TO]->(e2)
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
                            "title": n.get("fullname", n.get("name", n.get("title", str(n_id))))
                        }
                    if m_id not in nodes:
                        nodes[m_id] = {
                            "id": m_id, 
                            "label": list(m.labels)[0] if m.labels else "Unknown", 
                            "title": m.get("fullname", m.get("name", m.get("title", str(m_id))))
                        }
                        
                    edges.append({"source": n_id, "target": m_id, "label": rel_type})
                return {"nodes": list(nodes.values()), "edges": edges}
            except Exception as e:
                return {"error": str(e)}

    def get_funder_sample_graph(self, entity_name: str, limit: int = 150) -> dict:
        """Extrae una sub-muestra del grafo para una entidad, enfocada en financiadores."""
        query = f"""
        MATCH (e) WHERE (e:Institution OR e:Dependency OR e:Subdependency) AND e.name = $entity_name
        MATCH (e)<-[r0:AFFILIATED_TO]-(a:Person)-[r1:AUTHOR_OF]->(p:Paper)-[r2:FUNDED_BY]->(f:Funder)
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

    def upsert_user(self, orcid: str, name: str = None):
        """Crea o actualiza un nodo User basado en su ORCID verificado."""
        query = """
        MERGE (u:User {orcid: $orcid})
        SET u.name = coalesce($name, u.name),
            u.last_login = datetime()
        """
        with self.driver.session() as session:
            session.run(query, orcid=orcid, name=name)

    def link_user_to_academic(self, orcid: str, academic_id: str):
        """
        Vincula un nodo User con un nodo Person mediante la relación REPRESENTS.
        """
        query = """
        MATCH (u:User {orcid: $orcid})
        MATCH (a:Person {id: $academic_id})
        MERGE (u)-[r:REPRESENTS]->(a)
        SET r.verification_date = datetime(),
            a.verified = true,
            a.verified_orcid = $orcid
        """
        with self.driver.session() as session:
            try:
                session.run(query, orcid=orcid, academic_id=academic_id)
            except Exception as e:
                print(f"Error vinculando User {orcid} a Academic {academic_id}: {e}")

    def get_user_profile(self, orcid: str) -> dict:
        """Recupera el perfil de usuario y su académico vinculado si existe."""
        query = """
        MATCH (u:User {orcid: $orcid})
        OPTIONAL MATCH (u)-[:REPRESENTS]->(a:Person)
        RETURN u.name as name, u.orcid as orcid, 
               a.id as academic_id, a.fullname as academic_name
        """
        with self.driver.session() as session:
            result = session.run(query, orcid=orcid)
            record = result.single()
            if record:
                return dict(record)
        return None

    def find_academic_by_orcid(self, orcid: str) -> dict:
        """Busca un nodo Person que ya tenga el ORCID proporcionado."""
        query = """
        MATCH (a:Person {orcid: $orcid})
        RETURN a.id as id, a.fullname as name, a.orcid as orcid
        LIMIT 1
        """
        with self.driver.session() as session:
            result = session.run(query, orcid=orcid)
            record = result.single()
            if record:
                return dict(record)
        return None

    def global_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Búsqueda global optimizada usando índices Full-Text.
        Busca en Académicos e Instituciones simultáneamente.
        """
        if not query or len(query) < 3:
            return []
            
        # Limpieza básica para evitar errores de sintaxis en Lucene
        clean_query = query.replace(':', '').replace('/', '').replace('\\', '').strip()
        
        cypher = """
        CALL db.index.fulltext.queryNodes("person_name_search", $q + "~") YIELD node, score
        RETURN node.fullname as name, node.id as id, labels(node) as labels, score, "Academic" as type
        LIMIT $limit
        UNION
        CALL db.index.fulltext.queryNodes("institution_name_search", $q + "~") YIELD node, score
        RETURN node.name as name, node.id as id, labels(node) as labels, score, "Institution" as type
        LIMIT $limit
        """
        results = []
        with self.driver.session() as session:
            try:
                records = session.run(cypher, q=clean_query, limit=limit)
                for r in records:
                    results.append(dict(r))
            except Exception as e:
                print(f"Error en global_search: {e}")
                
        # Ordenar por score descendente
        return sorted(results, key=lambda x: x['score'], reverse=True)[:limit]

    def get_hierarchical_academic_census(self, inst_name: str, dep_name: str = None, sub_name: str = None) -> List[str]:
        """
        Obtiene la lista de nombres de académicos para una entidad específica,
        respetando la jerarquía para evitar problemas con homónimos.
        """
        # Limpieza de valores para el MATCH
        def _is_valid(val):
            return val and str(val).upper() not in ["SIN INFORMACIÓN", "SIN INFORMACIN", "NO APLICA", "SIN INSTITUCION", "SIN INSTITUCIN", "NAN", "NONE", "NULL"]

        # Determinar el nodo objetivo según la jerarquía proporcionada
        if _is_valid(sub_name):
            # Buscar en Subdependencia ligada a Dependency e Inst
            query = """
            MATCH (i:Institution {name: $inst})<-[:PART_OF]-(d:Dependency {id: $inst + "||" + $dep})<-[:PART_OF]-(e:Subdependency {id: $inst + "||" + $dep + "||" + $sub})
            MATCH (a:Person)-[:AFFILIATED_TO]->(e)
            RETURN DISTINCT a.fullname as name, d.name as dep, e.name as sub
            """
            params = {"inst": inst_name, "dep": dep_name, "sub": sub_name}
        elif _is_valid(dep_name):
            # Buscar en Dependency ligada a Inst y sus Subdependencias
            query = """
            MATCH (i:Institution {name: $inst})<-[:PART_OF]-(d:Dependency {id: $inst + "||" + $dep})
            OPTIONAL MATCH (d)<-[:PART_OF]-(s:Subdependency)
            WITH d, s
            MATCH (a:Person)-[:AFFILIATED_TO]->(node)
            WHERE node = d OR node = s
            RETURN DISTINCT a.fullname as name, d.name as dep, s.name as sub
            """
            params = {"inst": inst_name, "dep": dep_name}
        else:
            # Buscar en toda la jerarquía de la Institución.
            # Usa collect+UNWIND para evitar el producto cartesiano (i,d,s)×Person.
            query = """
            MATCH (i:Institution {name: $inst})
            OPTIONAL MATCH (i)<-[:PART_OF]-(d:Dependency)
            OPTIONAL MATCH (d)<-[:PART_OF]-(s:Subdependency)
            WITH collect(distinct i) + collect(distinct d) + collect(distinct s) AS targets
            UNWIND targets AS node
            MATCH (a:Person)-[:AFFILIATED_TO]->(node)
            WHERE a.fullname IS NOT NULL
            OPTIONAL MATCH (node)-[:PART_OF]->(parent:Dependency)
            RETURN DISTINCT
                a.fullname AS name,
                CASE labels(node)[0]
                    WHEN 'Dependency'    THEN node.name
                    WHEN 'Subdependency' THEN coalesce(parent.name, 'SIN INFORMACIÓN')
                    ELSE 'SIN INFORMACIÓN'
                END AS dep,
                CASE labels(node)[0]
                    WHEN 'Subdependency' THEN node.name
                    ELSE 'SIN INFORMACIÓN'
                END AS sub
            """
            params = {"inst": inst_name}

        with self.driver.session() as session:
            try:
                results = session.run(query, **params)
                census = []
                for r in results:
                    name = r.get("name")
                    if not name:           # saltar Person sin fullname
                        continue
                    census.append({
                        "name": name,
                        "institution": inst_name,
                        "dependency":    r.get("dep") or dep_name or "SIN INFORMACIÓN",
                        "subdependency": r.get("sub") or sub_name or "SIN INFORMACIÓN"
                    })
                return census
            except Exception as e:
                print(f"Error en get_hierarchical_academic_census: {e}")
                return []

