"""
lib/citations_explorer.py - Motor de Análisis de Artículos Citantes (Zero-Join ClickHouse)
Permite extraer y analizar la red cualitativa de citas de un investigador:
- Geopolítica de citas (países e instituciones que citan).
- Citas netas vs. autocitas.
- Citas de alto impacto (Top 10% y Top 1%).
- Tópicos y evolución temporal de citas.
"""

import os
import re
import unicodedata
from typing import List, Dict, Any, Optional, Set, Tuple
import pandas as pd
from database.clickhouse_db import ch_client

def normalize_name_for_matching(name: str) -> str:
    """Normaliza un nombre de autor eliminando acentos, guiones y signos de puntuación."""
    if not name:
        return ""
    # Quitar acentos/diacríticos
    n = unicodedata.normalize('NFKD', str(name)).encode('ASCII', 'ignore').decode('utf-8')
    # Reemplazar guiones, comas y puntos por espacios
    n = n.upper().replace("-", " ").replace(",", " ").replace(".", " ")
    parts = [p.strip() for p in n.split() if len(p.strip()) > 1]
    return " ".join(parts)

def get_author_work_and_openalex_ids(
    academic_name: Optional[str] = None, 
    orcid: Optional[str] = None
) -> Tuple[List[str], Set[str]]:
    """
    Recupera:
    1. Lista de IDs canónicos de obras (OpenAlex W...).
    2. Conjunto de OpenAlex Author IDs (A...) asociados al investigador en paper_author_map.
    Resuelve tanto IDs directos de OpenAlex como DOIs contra la tabla works (zero-join).
    """
    client = ch_client.get_client()
    conditions = []
    params = {}

    if orcid:
        clean_orc = str(orcid).strip().split('/')[-1]
        conditions.append("orcid LIKE %(orc)s")
        params["orc"] = f"%{clean_orc}%"
    
    if academic_name:
        conditions.append("academic_name = %(name)s")
        params["name"] = academic_name.strip()

    if not conditions:
        return [], set()

    where_clause = " OR ".join(conditions)
    query = f"""
        SELECT DISTINCT paper_id, openalex_id 
        FROM paper_author_map 
        WHERE ({where_clause})
        LIMIT 1000
    """
    try:
        rows = client.query(query, params).result_rows
    except Exception as e:
        print(f"[citations_explorer] Error recuperando registros de paper_author_map: {e}")
        return [], set()

    resolved_wids = set()
    doi_candidates = set()
    author_oa_ids = set()

    for r in rows:
        pid = str(r[0]).strip() if r[0] else ""
        oaid = str(r[1]).strip() if len(r) > 1 and r[1] else ""
        
        if oaid:
            for m in re.findall(r'A\d+', oaid):
                author_oa_ids.add(m)
        
        if "openalex.org/W" in pid:
            resolved_wids.add(pid)
        elif pid:
            doi_candidates.add(pid)
            if not pid.startswith("http"):
                doi_candidates.add(f"https://doi.org/{pid}")

    # Resolver DOIs hacia sus IDs en works
    if doi_candidates:
        try:
            w_rows = client.query(
                "SELECT DISTINCT id FROM works WHERE id IN %(pids)s OR doi IN %(dois)s",
                {"pids": list(doi_candidates), "dois": list(doi_candidates)}
            ).result_rows
            for wr in w_rows:
                if wr[0]:
                    resolved_wids.add(wr[0])
        except Exception as e_doi:
            print(f"[citations_explorer] Error resolviendo DOIs en works: {e_doi}")

    return list(resolved_wids), author_oa_ids

def get_author_work_ids(academic_name: Optional[str] = None, orcid: Optional[str] = None) -> List[str]:
    """
    Recupera los IDs de obras de OpenAlex (https://openalex.org/W...) pertenecientes al investigador.
    Mantiene compatibilidad hacia atrás con los componentes llamadores.
    """
    wids, _ = get_author_work_and_openalex_ids(academic_name, orcid)
    return wids

def get_citing_works_data(
    work_ids: List[str], 
    author_name: str = "", 
    author_openalex_ids: Optional[Set[str]] = None,
    limit: int = 500
) -> Dict[str, Any]:
    """
    Ejecuta el pipeline Zero-Join para recuperar y agregar todos los artículos citantes.
    Paso 1: Consulta work_citations por cited_work_id.
    Paso 2: Consulta works por id IN (citing_work_ids), extrayendo author_ids y author_names.
    """
    empty_result = {
        "total_citations": 0,
        "net_citations": 0,
        "self_citations": 0,
        "self_citation_rate": 0.0,
        "top_10_percent_citations": 0,
        "top_1_percent_citations": 0,
        "citing_countries_count": 0,
        "citing_institutions_count": 0,
        "by_country": [],
        "by_institution": [],
        "by_year": [],
        "by_topic": [],
        "by_oa_status": [],
        "top_citing_works": [],
        "citing_works_df": pd.DataFrame()
    }

    if not work_ids:
        return empty_result

    client = ch_client.get_client()
    clean_wids = list(set(work_ids))[:1000]

    # ── Paso 1: Obtener relaciones de citación desde work_citations ──
    try:
        cite_rows = client.query(
            "SELECT citing_work_id, citing_publication_year, cited_work_id FROM work_citations WHERE cited_work_id IN %(wks)s LIMIT %(lim)s",
            {"wks": clean_wids, "lim": limit * 3}
        ).result_rows
    except Exception as e:
        print(f"[citations_explorer] Error en Paso 1 (work_citations): {e}")
        return empty_result

    if not cite_rows:
        return empty_result

    # Mapeo de obra citada por cada obra citante
    cited_map = {}
    for r in cite_rows:
        citing_id, yr, cited_id = r[0], r[1], r[2]
        if citing_id not in cited_map:
            cited_map[citing_id] = set()
        cited_map[citing_id].add(cited_id)

    unique_citing_ids = list(cited_map.keys())[:limit]

    # ── Paso 2: Obtener detalles de obras citantes desde works (incluye author_ids) ──
    try:
        details_df = client.query_df(
            """
            SELECT id, doi, title, publication_year, author_names, author_ids, institution_names, 
                   all_country_codes, topic, fwci, oa_status, is_top_10, is_top_1, cited_by_count, source_type
            FROM works 
            WHERE id IN %(ids)s
            """,
            {"ids": unique_citing_ids}
        )
    except Exception as e:
        print(f"[citations_explorer] Error en Paso 2 (works): {e}")
        return empty_result

    if details_df.empty:
        return empty_result

    # ── Detección Híbrida de Autocitas y Métricas Netas ──
    norm_author = normalize_name_for_matching(author_name)
    author_tokens = set(norm_author.split()) if norm_author else set()
    clean_target_aids = set()
    if author_openalex_ids:
        for x in author_openalex_ids:
            found = re.findall(r'A\d+', str(x))
            for f in found:
                clean_target_aids.add(f)

    def check_self_cite(row):
        # 1. Prioridad: Coincidencia determinista y exacta por OpenAlex Author ID
        if clean_target_aids:
            row_aids = row.get("author_ids")
            if isinstance(row_aids, (list, tuple)):
                for aid in row_aids:
                    found = re.findall(r'A\d+', str(aid))
                    for f in found:
                        if f in clean_target_aids:
                            return True

        # 2. Respaldo (Fallback): Coincidencia por tokens de nombre
        authors_list = row.get("author_names")
        if not author_tokens or not isinstance(authors_list, (list, tuple)):
            return False
        for a in authors_list:
            a_norm = normalize_name_for_matching(str(a))
            tokens_match = len(author_tokens.intersection(set(a_norm.split())))
            if tokens_match >= min(2, len(author_tokens)):
                return True
        return False

    details_df["is_self_citation"] = details_df.apply(check_self_cite, axis=1)
    details_df["first_author"] = details_df["author_names"].apply(lambda x: x[0] if isinstance(x, (list, tuple)) and len(x) > 0 else "Anónimo")
    details_df["cited_works_target"] = details_df["id"].apply(lambda cid: list(cited_map.get(cid, [])))

    total_cites = len(details_df)
    self_cites = int(details_df["is_self_citation"].sum())
    net_cites = max(0, total_cites - self_cites)
    self_rate = round((self_cites / max(total_cites, 1)) * 100, 1)

    top_10_cnt = int((details_df["is_top_10"] == 1).sum())
    top_1_cnt = int((details_df["is_top_1"] == 1).sum())

    # ── Agregaciones Geopolíticas (Países e Instituciones) ──
    # Explotar países
    countries_series = details_df["all_country_codes"].explode().dropna()
    countries_counts = countries_series[countries_series != ""].value_counts().head(15).reset_index()
    countries_counts.columns = ["country_code", "citations_count"]
    by_country = countries_counts.to_dict(orient="records")

    # Explotar instituciones
    inst_series = details_df["institution_names"].explode().dropna()
    inst_counts = inst_series[inst_series != ""].value_counts().head(15).reset_index()
    inst_counts.columns = ["institution", "citations_count"]
    by_inst = inst_counts.to_dict(orient="records")

    # Distribución por Año
    year_counts = details_df["publication_year"].value_counts().sort_index().reset_index()
    year_counts.columns = ["year", "citations_count"]
    by_year = year_counts.to_dict(orient="records")

    # Distribución por Tópicos
    topic_series = details_df["topic"].dropna()
    topic_counts = topic_series[topic_series != ""].value_counts().head(10).reset_index()
    topic_counts.columns = ["topic", "citations_count"]
    by_topic = topic_counts.to_dict(orient="records")

    # Distribución por Acceso Abierto
    oa_series = details_df["oa_status"].dropna()
    oa_counts = oa_series[oa_series != ""].value_counts().reset_index()
    oa_counts.columns = ["oa_status", "citations_count"]
    by_oa = oa_counts.to_dict(orient="records")

    # Top Citing Works (Obras más citadas que citan al autor)
    top_works = details_df.sort_values(by="cited_by_count", ascending=False).head(10).to_dict(orient="records")

    return {
        "total_citations": total_cites,
        "net_citations": net_cites,
        "self_citations": self_cites,
        "self_citation_rate": self_rate,
        "top_10_percent_citations": top_10_cnt,
        "top_1_percent_citations": top_1_cnt,
        "citing_countries_count": int(countries_series.nunique()),
        "citing_institutions_count": int(inst_series.nunique()),
        "by_country": by_country,
        "by_institution": by_inst,
        "by_year": by_year,
        "by_topic": by_topic,
        "by_oa_status": by_oa,
        "top_citing_works": top_works,
        "citing_works_df": details_df
    }


def get_author_works(academic_name: Optional[str] = None, orcid: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Recupera la lista canónica de publicaciones del autor desde ClickHouse (Zero-Join).
    Obtiene los IDs desde paper_author_map y luego consulta la tabla works por ID.
    """
    wids = get_author_work_ids(academic_name, orcid)
    if not wids:
        return []

    client = ch_client.get_client()
    clean_wids = list(set(wids))[:500]
    
    query = """
        SELECT 
            id, doi, title, publication_year, cited_by_count, 
            fwci, is_top_10, is_top_1, oa_status, topic, 
            author_names, all_country_codes, raw_data
        FROM works
        WHERE id IN %(wids)s
        ORDER BY publication_year DESC, cited_by_count DESC
    """
    try:
        rows = client.query(query, {"wids": clean_wids}).result_rows
    except Exception as e:
        print(f"[citations_explorer] Error recuperando obras del autor: {e}")
        return []

    import json
    author_works = []
    for r in rows:
        wid, doi, title, yr, cites, fwci, top10, top1, oa, topc, auts, countries, raw_str = r
        journal = ""
        volume = None
        issue = None
        pages = None
        publisher = None
        issn = None
        abstract = None

        if raw_str:
            try:
                raw_j = json.loads(raw_str)
                bib = raw_j.get("biblio") or {}
                loc = raw_j.get("primary_location") or {}
                src = loc.get("source") or {}
                journal = src.get("display_name") or ""
                volume = bib.get("volume")
                issue = bib.get("issue")
                f_p = bib.get("first_page")
                l_p = bib.get("last_page")
                pages = f"{f_p}--{l_p}" if f_p and l_p else (f_p or "")
                publisher = src.get("publisher") or src.get("host_organization_name")
                issn = ", ".join(src.get("issn") or []) if isinstance(src.get("issn"), list) else None
                abstract = raw_j.get("abstract")
            except Exception:
                pass

        author_works.append({
            "work_id": wid,
            "paper_id": wid,
            "doi": doi or "",
            "title": title or "Sin Título",
            "publication_year": yr,
            "year": yr,
            "journal": journal,
            "Source": journal,
            "authors": auts or [],
            "author_names": auts or [],
            "cited_by_count": cites or 0,
            "citations": cites or 0,
            "fwci": fwci if fwci is not None else 1.0,
            "is_top_10": top10 or 0,
            "is_top_1": top1 or 0,
            "oa_status": oa or "Desconocido",
            "topic": topc or "",
            "volume": volume,
            "issue": issue,
            "pages": pages,
            "publisher": publisher,
            "issn": issn,
            "abstract": abstract
        })

    return author_works


def get_citing_works_analysis(academic_name: Optional[str] = None, orcid: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
    """
    Función de alto nivel que recupera los IDs de obras del autor y computa
    todo el análisis de artículos citantes (zero-join).
    Utiliza OpenAlex IDs para desambiguación exacta de autocitas y respaldo heurístico de nombres.
    """
    wids, author_oa_ids = get_author_work_and_openalex_ids(academic_name, orcid)
    raw_data = get_citing_works_data(
        wids, 
        author_name=academic_name or "", 
        author_openalex_ids=author_oa_ids, 
        limit=limit
    )
    
    # Formatear distribuciones como dicts para compatibilidad con componentes UI
    country_dist = {}
    for c in raw_data.get("by_country", []):
        country_dist[c["country_code"]] = c["citations_count"]

    inst_dist = {}
    for i in raw_data.get("by_institution", []):
        inst_dist[i["institution"]] = i["citations_count"]

    year_dist = {}
    for y in raw_data.get("by_year", []):
        year_dist[y["year"]] = y["citations_count"]

    raw_data["country_distribution"] = country_dist
    raw_data["institution_distribution"] = inst_dist
    raw_data["year_distribution"] = year_dist

    return raw_data

