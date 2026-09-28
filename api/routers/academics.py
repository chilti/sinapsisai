"""
api/routers/academics.py - Router para búsqueda, perfiles y producción de investigadores
"""
from fastapi import APIRouter, Query, HTTPException
from typing import List, Dict, Any, Optional
from api.db import get_neo4j_store, get_clickhouse_client
from lib.citations_explorer import get_author_work_and_openalex_ids

router = APIRouter(prefix="/api/academics", tags=["Investigadores"])

@router.get("/search")
def search_academics(
    q: str = Query(..., min_length=2, description="Nombre o apellido del investigador"),
    limit: int = Query(10, ge=1, le=50)
) -> Dict[str, Any]:
    """Búsqueda predictiva de investigadores en el padrón nacional."""
    neo = get_neo4j_store()
    results = neo.global_search(q, limit=limit)
    academics = [r for r in results if r.get("type") == "Academic"]
    return {
        "query": q,
        "total": len(academics),
        "results": academics
    }

@router.get("/profile")
def get_academic_profile(
    name: Optional[str] = Query(None, description="Nombre completo del investigador"),
    orcid: Optional[str] = Query(None, description="ORCID iD del investigador")
) -> Dict[str, Any]:
    """Recupera los datos biográficos, padrón SNII y métricas de impacto de un investigador."""
    if not name and not orcid:
        raise HTTPException(status_code=400, detail="Debe proporcionar 'name' o 'orcid'")

    neo = get_neo4j_store()
    query = """
    MATCH (a:Person)
    WHERE (a.fullname = $name OR a.orcid = $orcid)
    OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(node)
    OPTIONAL MATCH path = (node)-[:PART_OF*0..3]->(parent)
    WITH a, node, nodes(path) as hierarchy_nodes
    RETURN a.id as id,
           a.fullname as name,
           a.orcid as orcid,
           coalesce(a.orcids, []) as orcids,
           coalesce(a.openalex_ids, []) as openalex_ids,
           coalesce(a.scopus_ids, []) as scopus_ids,
           a.snii_level as snii_level,
           a.snii_area as snii_area,
           a.snii_institution as snii_institution,
           a.snii_dependency as snii_dependency,
           a.snii_subdependency as snii_subdependency,
           a.snii_active_2026 as snii_active_2026,
           node.name as affiliation_direct,
           [n IN hierarchy_nodes | n.name] as hierarchy_names
    LIMIT 1
    """
    profile = {}
    with neo.driver.session() as session:
        result = session.run(query, name=name, orcid=orcid)
        record = result.single()
        if record:
            profile = dict(record)

    if not profile:
        # Fallback a nombre directo si no está en Neo4j
        profile = {
            "name": name or "",
            "orcid": orcid or "",
            "snii_level": "No registrado en Padrón",
            "gender": "No especificado"
        }

    # Resolver jerarquía en orden: Institución -> Dependencia -> Subdependencia
    hierarchy = profile.get("hierarchy_names") or []
    inst = hierarchy[-1] if hierarchy else profile.get("affiliation_direct", "SIN INFORMACIÓN")
    dep = hierarchy[-2] if len(hierarchy) >= 2 else ""
    sub = hierarchy[0] if len(hierarchy) >= 3 else ""

    profile["institution"] = inst
    profile["dependency"] = dep
    profile["subdependency"] = sub

    # Recuperar métricas analíticas de ClickHouse
    wids, author_oa_ids = get_author_work_and_openalex_ids(name or profile.get("name"), orcid or profile.get("orcid"))
    profile["total_works_identified"] = len(wids)

    return {
        "status": "success",
        "profile": profile
    }

@router.get("/works")
def get_academic_works(
    name: Optional[str] = Query(None),
    orcid: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    year: Optional[int] = Query(None),
    oa_status: Optional[str] = Query(None),
    is_top_10: Optional[bool] = Query(None)
) -> Dict[str, Any]:
    """Recupera la lista de publicaciones del investigador desde ClickHouse con filtros dinámicos."""
    wids, _ = get_author_work_and_openalex_ids(name, orcid)
    if not wids:
        return {"total": 0, "works": [], "limit": limit, "offset": offset}

    client = get_clickhouse_client()
    conditions = ["id IN %(ids)s"]
    params = {"ids": wids, "limit": limit, "offset": offset}

    if year:
        conditions.append("publication_year = %(year)s")
        params["year"] = year
    if oa_status:
        conditions.append("oa_status = %(oa_status)s")
        params["oa_status"] = oa_status.lower()
    if is_top_10 is not None:
        conditions.append("is_top_10 = %(is_top_10)s")
        params["is_top_10"] = 1 if is_top_10 else 0

    where_sql = " AND ".join(conditions)
    query = f"""
        SELECT id, doi, title, publication_year, author_names, institution_names,
               topic, fwci, oa_status, is_top_10, is_top_1, cited_by_count, source_type
        FROM works
        WHERE {where_sql}
        ORDER BY publication_year DESC, cited_by_count DESC
        LIMIT %(limit)s OFFSET %(offset)s
    """
    count_query = f"SELECT count() FROM works WHERE {where_sql}"

    try:
        total = client.query(count_query, params).result_rows[0][0]
        rows = client.query_df(query, params)
        works_list = rows.to_dict(orient="records") if not rows.empty else []
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "works": works_list
        }
    except Exception as e:
        return {"total": 0, "works": [], "error": str(e)}
