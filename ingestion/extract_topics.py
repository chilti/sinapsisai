import os
import json
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

load_dotenv()
neo4j = Neo4jGraphStore()

def extract_and_link_topics():
    print("⏳ Iniciando extracción de Tópicos desde Neo4j (APIPapers)...")
    
    # Usar COALESCE para evitar el warning de Neo4j sobre propiedades inexistentes
    query_fetch = """
    MATCH (p:Paper)
    WHERE p.raw_metadata IS NOT NULL AND COALESCE(p.topics_extracted, false) = false
    RETURN p.doi AS doi, p.raw_metadata AS metadata
    """
    
    updates = 0
    with neo4j.driver.session() as read_session:
        result = read_session.run(query_fetch)
        papers = list(result)
        
        print(f"✅ Se encontraron {len(papers)} papers pendientes de extraer tópicos.")
        
    for record in papers:
            doi = record['doi']
            raw_meta = record['metadata']
            
            try:
                meta_json = json.loads(raw_meta)
            except Exception:
                continue
                
            topics = meta_json.get('OpenAlex_Topics', [])
            
            with neo4j.driver.session() as write_session:
                if not isinstance(topics, list) or not topics:
                    # Marcar como procesado aunque no tenga
                    write_session.run("MATCH (p:Paper {doi: $doi}) SET p.topics_extracted = true", doi=doi)
                    continue
                    
                for t in topics:
                    topic_id = t.get('topic', '')
                    if not topic_id: continue
                    
                    topic_name = topic_id
                    domain_name = t.get('domain', '')
                    field_name = t.get('field', '')
                    subfield_name = t.get('subfield', '')
                    score = t.get('score', 0.0)
                    
                    # Nodos de Topic
                    merge_topic_query = """
                    MATCH (p:Paper {doi: $doi})
                    MERGE (t:Topic {id: $topic_id})
                    SET t.name = $topic_name,
                        t.domain = $domain_name,
                        t.field = $field_name,
                        t.subfield = $subfield_name
                    MERGE (p)-[r:HAS_TOPIC]->(t)
                    SET r.score = $score
                    """
                    write_session.run(merge_topic_query, 
                                doi=doi, topic_id=topic_id, topic_name=topic_name,
                                domain_name=domain_name, field_name=field_name, 
                                subfield_name=subfield_name, score=score)
                                
                # Marcar el paper como procesado al final
                write_session.run("MATCH (p:Paper {doi: $doi}) SET p.topics_extracted = true", doi=doi)
                
            updates += 1
            if updates % 500 == 0:
                print(f"  -> Procesados y vinculados {updates} papers...")

    print(f"🎉 Extracción completada para {updates} papers.")

if __name__ == "__main__":
    extract_and_link_topics()
