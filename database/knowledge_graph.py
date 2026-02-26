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
            "CREATE CONSTRAINT author_id IF NOT EXISTS FOR (a:Author) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT institution_id IF NOT EXISTS FOR (i:Institution) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT api_paper_id IF NOT EXISTS FOR (p:APIPaper) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT academic_id IF NOT EXISTS FOR (a:Academic) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE"
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
        """
        import json
        
        # Preparar data asegurando que metadata sea string de JSON
        data = paper_data.copy()
        if "raw_metadata" in data and isinstance(data["raw_metadata"], dict):
            # Limpiar listas para que no den problemas o guardarlo como json puro
            data["raw_metadata_json"] = json.dumps(data["raw_metadata"], ensure_ascii=False)
        else:
            data["raw_metadata_json"] = "{}"

        query = """
        MERGE (p:Paper {id: $paper_id})
        SET p.title = $title, p.doi = $doi, p.year = $year, p.citations = $citations,
            p.raw_metadata = $raw_metadata_json
        
        WITH p
        UNWIND $authors AS author
        MERGE (a:Author {id: author.name}) // Usando name como ID simplificado por ahora, o author.id
        SET a.name = author.name
        MERGE (a)-[:AUTHORED]->(p)
        
        WITH p, author, a
        // Comprobar si hay institutions en author, o saltar si no hay
        // En tu parser original no hay institutions por author, sino globales del paper.
        // Pero mantenemos compatibilidad por si la data la trae:
        UNWIND (CASE WHEN author.institutions IS NOT NULL THEN author.institutions ELSE [] END) AS inst
        MERGE (i:Institution {id: inst.id})
        SET i.name = inst.name
        MERGE (a)-[:AFFILIATED_WITH]->(i)
        
        WITH p
        UNWIND $concepts AS concept
        MERGE (c:Concept {id: coalesce(concept.id, concept.name)})
        SET c.name = concept.name
        MERGE (p)-[:HAS_CONCEPT]->(c)
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

    def add_api_paper(self, paper_data: Dict[str, Any], academic_name: str):
        """
        Inserta datos de APIs (OpenAlex/Scopus/ORCID) en tablas/labels distintos (APIPaper, Academic).
        Vincula el nombre completo (Academic) y el artículo por DOI.
        Conserva todos los campos crudos en raw_metadata_json.
        """
        import json
        data = paper_data.copy()
        if "raw_metadata" in data and isinstance(data["raw_metadata"], dict):
            data["raw_metadata_json"] = json.dumps(data["raw_metadata"], ensure_ascii=False)
        else:
            data["raw_metadata_json"] = "{}"

        # Parametros para la query
        params = {
            "doi": data.get("doi", ""),
            "title": data.get("title", ""),
            "year": int(data.get("year", 0)) if data.get("year") else 0,
            "citations": int(data.get("citations", 0)) if data.get("citations") else 0,
            "raw_metadata": data["raw_metadata_json"],
            "academic_name": academic_name
        }

        # Si no hay DOI válido, no podemos ligarlos estrictamente o creamos id random
        if not params["doi"]:
            import uuid
            params["doi"] = str(uuid.uuid4())

        query = """
        MERGE (a:Academic {id: $academic_name}) // Usar el nombre completo json como ID principal
        SET a.name = $academic_name
        
        MERGE (p:APIPaper {id: $doi})
        SET p.doi = $doi, p.title = $title, p.year = $year, p.citations = $citations,
            p.raw_metadata = $raw_metadata
            
        MERGE (a)-[:AUTHORED]->(p)
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
        MERGE (e:Entity {name: $entity_name})
        WITH e
        MATCH (p:Paper {doi: $doi}) // Buscamos en Label genérico Paper
        MERGE (e)-[:HAS_PAPER]->(p)
        """
        with self.driver.session() as session:
            try:
                session.run(query, entity_name=entity_name, doi=doi)
            except Exception as e:
                pass

    def add_academic_affiliation(self, academic_name: str, entity_name: str):
        """
        Vincula un Academic con un Entity institucional.
        """
        query = """
        MERGE (e:Entity {name: $entity_name})
        WITH e
        MATCH (a:Academic {name: $academic_name})
        MERGE (a)-[:AFFILIATED_TO]->(e)
        """
        with self.driver.session() as session:
            try:
                session.run(query, academic_name=academic_name, entity_name=entity_name)
            except Exception as e:
                pass

