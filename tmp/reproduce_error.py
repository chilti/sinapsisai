
source_filter = 'wos'
label_filter = ":IndexedWoS"
academic_filter = "TEST"

try:
    query = f"""
    MATCH (a:Academic {{name: $academic}})-[:AUTHORED]->(p{label_filter})
    OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity)
    OPTIONAL MATCH (a)-[:AFFILIATED_WITH]->(i:Institution)
    OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
    OPTIONAL MATCH (p)-[:HAS_TOPIC]->(t:Topic)
    RETURN a.name AS academic_name,
            a.orcid AS orcid,
            a.scopus_id AS scopus_id,
            a.siia_url AS siia_url,
            a.audit_verdict AS audit_verdict,
            a.audit_reason AS audit_reason,
            a.audit_confidence AS audit_confidence,
            a.audit_timestamp AS audit_timestamp,
            a.is_snii AS is_snii,
            collect(DISTINCT e.name) AS entities,
            collect(DISTINCT i.name) AS institutions,
            p.id AS paper_id,
            p.doi AS paper_doi,
            p.year AS year,
            p.citations AS citations,
            p.raw_metadata AS raw_metadata,
            collect(DISTINCT {{id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}}) AS sdgs,
            collect(DISTINCT {{topic: t.name, domain: t.domain, field: t.field, subfield: t.subfield}}) AS graph_topics
    """
    print("Query 1 OK")
except Exception as e:
    print(f"Query 1 Error: {e}")

try:
    entity_filter = "TEST"
    query = f"""
    MATCH (e:Entity {{name: $entity}})<-[:AFFILIATED_TO]-(a:Academic)-[:AUTHORED]->(p{label_filter})
    OPTIONAL MATCH (a)-[:AFFILIATED_WITH]->(i:Institution)
    OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
    OPTIONAL MATCH (p)-[:HAS_TOPIC]->(t:Topic)
    RETURN a.name AS academic_name,
            a.orcid AS orcid,
            a.scopus_id AS scopus_id,
            a.siia_url AS siia_url,
            a.audit_verdict AS audit_verdict,
            a.audit_reason AS audit_reason,
            a.audit_confidence AS audit_confidence,
            a.audit_timestamp AS audit_timestamp,
            a.is_snii AS is_snii,
            collect(DISTINCT e.name) AS entities,
            collect(DISTINCT i.name) AS institutions,
            p.id AS paper_id,
            p.doi AS paper_doi,
            p.year AS year,
            p.citations AS citations,
            p.raw_metadata AS raw_metadata,
            collect(DISTINCT {{id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}}) AS sdgs,
            collect(DISTINCT {{topic: t.name, domain: t.domain, field: t.field, subfield: t.subfield}}) AS graph_topics
    """
    print("Query 2 OK")
except Exception as e:
    print(f"Query 2 Error: {e}")

try:
    query = f"""
    MATCH (a:Academic)-[:AUTHORED]->(p{label_filter})
    OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(e:Entity)
    OPTIONAL MATCH (a)-[:AFFILIATED_WITH]->(i:Institution)
    OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
    OPTIONAL MATCH (p)-[:HAS_TOPIC]->(t:Topic)
    RETURN a.name AS academic_name,
            a.orcid AS orcid,
            a.scopus_id AS scopus_id,
            a.siia_url AS siia_url,
            a.audit_verdict AS audit_verdict,
            a.audit_reason AS audit_reason,
            a.audit_confidence AS audit_confidence,
            a.audit_timestamp AS audit_timestamp,
            a.is_snii AS is_snii,
            collect(DISTINCT e.name) AS entities,
            collect(DISTINCT i.name) AS institutions,
            p.id AS paper_id,
            p.doi AS paper_doi,
            p.year AS year,
            p.citations AS citations,
            p.raw_metadata AS raw_metadata,
            collect(DISTINCT {{id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}}) AS sdgs,
            collect(DISTINCT {{topic: t.name, domain: t.domain, field: t.field, subfield: t.subfield}}) AS graph_topics
    """
    print("Query 3 OK")
except Exception as e:
    print(f"Query 3 Error: {e}")

try:
    entity_filter = "TEST"
    query = f"""
    MATCH (e:Entity {{name: $entity}})
    OPTIONAL MATCH (e)<-[:AFFILIATED_TO]-(a:Academic)-[:AFFILIATED_WITH]->(i:Institution)
    OPTIONAL MATCH (e)-[:HAS_PAPER]->(p:Paper{label_filter})
    OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
    RETURN e.name AS entity_name,
            collect(DISTINCT i.name) AS institutions,
            p.id AS paper_id,
            p.doi AS paper_doi,
            p.year AS year,
            p.citations AS citations,
            p.raw_metadata AS raw_metadata,
            collect({{id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}}) AS sdgs
    """
    print("Query 4 OK")
except Exception as e:
    print(f"Query 4 Error: {e}")

try:
    query = f"""
    MATCH (e:Entity)-[:HAS_PAPER]->(p:Paper{label_filter})
    OPTIONAL MATCH (e)<-[:AFFILIATED_TO]-(a:Academic)-[:AFFILIATED_WITH]->(i:Institution)
    OPTIONAL MATCH (p)-[r:ADDRESSES]->(s:SDG)
    RETURN e.name AS entity_name,
            collect(DISTINCT i.name) AS institutions,
            p.id AS paper_id,
            p.doi AS paper_doi,
            p.year AS year,
            p.citations AS citations,
            p.raw_metadata AS raw_metadata,
            collect({{id: s.id, name: s.name, confidence: r.confidence, reasoning: r.reasoning}}) AS sdgs
    """
    print("Query 5 OK")
except Exception as e:
    print(f"Query 5 Error: {e}")
