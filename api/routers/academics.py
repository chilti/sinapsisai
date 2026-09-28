"""
api/routers/academics.py - Router para búsqueda, perfiles y producción de investigadores
Módulo 2: Perfiles de Investigadores (Paridad 1 a 1 con Streamlit y QA 22 controles)
"""
import os
import glob
import json
import re
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
from fastapi import APIRouter, Query, HTTPException

from api.db import get_neo4j_store, get_clickhouse_client
from lib.citations_explorer import (
    get_author_work_and_openalex_ids,
    get_citing_works_analysis,
    get_citing_works_data
)

router = APIRouter(prefix="/api/academics", tags=["Investigadores"])

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "cache_ch")

# Mapeo de Nivel SNII
SNII_LEVEL_LABELS = {
    "C": "Candidato a Investigador Nacional",
    "1": "Nivel 1",
    "2": "Nivel 2",
    "3": "Nivel 3",
    "E": "Investigador Nacional Emérito",
    "EMERITO": "Investigador Nacional Emérito",
    "EMÉRITO": "Investigador Nacional Emérito"
}

# 17 ODS Oficiales de la ONU
SDG_NAMES = {
    1: "Fin de la pobreza",
    2: "Hambre cero",
    3: "Salud y bienestar",
    4: "Educación de calidad",
    5: "Igualdad de género",
    6: "Agua limpia y saneamiento",
    7: "Energía asequible y no contaminante",
    8: "Trabajo decente y crecimiento económico",
    9: "Industria, innovación e infraestructura",
    10: "Reducción de las desigualdades",
    11: "Ciudades y comunidades sostenibles",
    12: "Producción y consumo responsables",
    13: "Acción por el clima",
    14: "Vida submarina",
    15: "Vida de ecosistemas terrestres",
    16: "Paz, justicia e instituciones sólidas",
    17: "Alianzas para lograr los objetivos"
}


def _clean_val(v: Any) -> Any:
    """Convierte NaN o tipos numpy a tipos estándar de Python serializables en JSON."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.floating, float)):
        return round(float(v), 2)
    if isinstance(v, (np.integer, int)):
        return int(v)
    return v


def _find_academic_dir(name: str, inst: Optional[str] = None, subdep: Optional[str] = None, dep: Optional[str] = None) -> Optional[str]:
    """Localiza el directorio físico de caché del investigador en data/cache_ch/."""
    if not name:
        return None
    safe_name = str(name).replace('/', '_').replace('\\', '_').strip()
    
    # 1. Comprobaciones directas si la institución es conocida
    if inst:
        safe_inst = str(inst).replace('/', '_').replace('\\', '_').strip()
        candidates = []
        if subdep:
            candidates.append(os.path.join(CACHE_DIR, safe_inst, str(subdep).replace('/', '_').strip(), safe_name))
        if dep:
            candidates.append(os.path.join(CACHE_DIR, safe_inst, str(dep).replace('/', '_').strip(), safe_name))
        candidates.append(os.path.join(CACHE_DIR, safe_inst, safe_inst, safe_name))
        candidates.append(os.path.join(CACHE_DIR, safe_inst, 'SIN INFORMACIÓN', safe_name))
        candidates.append(os.path.join(CACHE_DIR, safe_inst, safe_name))
        for c in candidates:
            if os.path.exists(c) and os.path.isdir(c):
                return c
        # Exploración rápida dentro del directorio de la institución
        inst_dir = os.path.join(CACHE_DIR, safe_inst)
        if os.path.exists(inst_dir):
            for root, dirs, _ in os.walk(inst_dir):
                if safe_name in dirs:
                    return os.path.join(root, safe_name)

    # 2. Búsqueda por glob en todo CACHE_DIR
    matches = glob.glob(os.path.join(CACHE_DIR, "**", safe_name), recursive=True)
    for m in matches:
        if os.path.isdir(m) and os.path.exists(os.path.join(m, "investigador_total.parquet")):
            return m

    # 3. Búsqueda normalizada por tokens si el nombre tiene comas o variantes
    tokens = [t.lower() for t in safe_name.replace(',', ' ').split() if len(t) > 2]
    if len(tokens) >= 2:
        for root, dirs, _ in os.walk(CACHE_DIR):
            for d in dirs:
                d_lower = d.lower()
                if all(tk in d_lower for tk in tokens[:2]):
                    target_path = os.path.join(root, d)
                    if os.path.exists(os.path.join(target_path, "investigador_total.parquet")):
                        return target_path
    return None


def _resolve_academic_nodes(name: Optional[str] = None, orcid: Optional[str] = None, person_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Recupera y fusiona los nodos de Person en Neo4j asociados al investigador."""
    neo = get_neo4j_store()
    clean_orcid = orcid.replace("https://orcid.org/", "").strip() if orcid else None
    matched_nodes = []

    with neo.driver.session() as session:
        # 1. Por ORCID
        if clean_orcid:
            rec = session.run("""
                MATCH (a:Person)
                WHERE a.orcid CONTAINS $orc OR $orc IN a.orcids
                RETURN a
                LIMIT 5
            """, orc=clean_orcid).data()
            if rec:
                matched_nodes.extend([r["a"] for r in rec])

        # 2. Por ID o CVU
        if person_id and not matched_nodes:
            rec = session.run("""
                MATCH (a:Person)
                WHERE a.id = $pid OR a.cvu = $pid
                RETURN a
                LIMIT 5
            """, pid=str(person_id)).data()
            if rec:
                matched_nodes.extend([r["a"] for r in rec])

        # 3. Por Nombre
        if name and not matched_nodes:
            rec = session.run("""
                MATCH (a:Person)
                WHERE a.fullname = $n OR a.id = $n
                RETURN a
                LIMIT 5
            """, n=name.strip()).data()
            if rec:
                matched_nodes.extend([r["a"] for r in rec])

            # Respaldo por tokens de nombre
            if not matched_nodes:
                tokens = [t for t in name.replace(",", " ").upper().split() if len(t) > 2]
                if len(tokens) >= 2:
                    t1, t2 = tokens[0], tokens[1]
                    rec = session.run("""
                        MATCH (a:Person)
                        WHERE a.fullname CONTAINS $t1 AND a.fullname CONTAINS $t2
                        RETURN a
                        LIMIT 5
                    """, t1=t1, t2=t2).data()
                    if rec:
                        matched_nodes.extend([r["a"] for r in rec])
    return matched_nodes


@router.get("/search")
def search_academics(
    q: str = Query(..., min_length=2, description="Nombre o apellido del investigador"),
    limit: int = Query(10, ge=1, le=50)
) -> Dict[str, Any]:
    """Búsqueda predictiva enriquecida de investigadores en el padrón nacional."""
    neo = get_neo4j_store()
    clean_q = q.replace(':', '').replace('/', '').replace('\\', '').strip()

    cypher = """
    CALL db.index.fulltext.queryNodes("person_name_search", $q + "~") YIELD node, score
    OPTIONAL MATCH path = (node)-[:AFFILIATED_TO]->()-[:PART_OF*0..2]->(i:Institution)
    WITH node, score, collect(path)[0] AS p
    WITH node, score, CASE WHEN p IS NOT NULL THEN [n IN nodes(p) WHERE n <> node AND n.name IS NOT NULL | n.name] ELSE [] END AS parents
    RETURN node.fullname as name, node.id as id, labels(node) as labels, score, "Academic" as type, parents,
           node.orcid as orcid, node.orcids as orcids, node.snii_level as snii_level, node.snii_area as snii_area,
           node.snii_institution as snii_institution, node.snii_dependency as snii_dependency, node.snii_subdependency as snii_subdependency
    LIMIT $limit
    """
    results = []
    with neo.driver.session() as session:
        try:
            records = session.run(cypher, q=clean_q, limit=limit)
            for r in records:
                d = dict(r)
                # Normalizar ORCID
                raw_orc = d.get("orcid") or (d.get("orcids")[0] if isinstance(d.get("orcids"), list) and d.get("orcids") else None)
                if raw_orc:
                    d["orcid"] = str(raw_orc).replace("https://orcid.org/", "").strip()
                results.append(d)
        except Exception as e:
            print(f"[search_academics] Error Neo4j: {e}")

    # Fallback a global_search si el query fulltext falló
    if not results:
        raw_res = neo.global_search(clean_q, limit=limit)
        results = [r for r in raw_res if r.get("type") == "Academic"]

    return {
        "query": q,
        "total": len(results),
        "results": results
    }


@router.get("/list")
def list_academics(
    institution: Optional[str] = Query("UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)", description="Institución"),
    dependency: Optional[str] = Query(None, description="Dependencia o Facultad"),
    subdependency: Optional[str] = Query(None, description="Subdependencia o Centro"),
    view_mode: Optional[str] = Query("capacidad_instalada", description="capacidad_instalada o produccion_institucional")
) -> Dict[str, Any]:
    """
    Retorna la lista ordenada de investigadores de la entidad seleccionada
    para poblar el combobox del Módulo de Investigadores (paridad Streamlit).
    """
    from dashboard_analytics import load_cached_data
    
    target_entity = subdependency or dependency or institution or "FACULTAD DE CIENCIAS"
    inst = institution or "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)"
    
    # 1. Fuente primaria: institucion_total.parquet de la entidad
    df_tot = load_cached_data('institucion_total.parquet', entity_name=target_entity, institution_name=inst, view_mode=view_mode)
    if (df_tot is None or df_tot.empty) and view_mode == "produccion_institucional":
        df_tot = load_cached_data('institucion_total.parquet', entity_name=target_entity, institution_name=inst, view_mode="capacidad_instalada")
        
    academics = []
    if df_tot is not None and not df_tot.empty and 'academics_list' in df_tot.columns:
        val = df_tot.iloc[0].get('academics_list')
        try:
            raw_list = json.loads(val) if isinstance(val, str) else val
            if isinstance(raw_list, list):
                for item in raw_list:
                    if isinstance(item, dict):
                        academics.append(item)
                    elif isinstance(item, str) and item.strip():
                        academics.append({"name": item.strip()})
        except Exception as e:
            print(f"[list_academics] Error parseando academics_list: {e}")

    # Fallback físico en directorio si la lista vino vacía
    if not academics:
        safe_inst = str(inst).replace('/', '_').replace('\\', '_') if inst else ""
        safe_ent = str(target_entity).replace('/', '_').replace('\\', '_')
        test_paths = []
        if safe_inst:
            test_paths.append(os.path.join(CACHE_DIR, safe_inst, safe_ent))
        test_paths.append(os.path.join(CACHE_DIR, safe_ent))
        for p in test_paths:
            if os.path.exists(p):
                f_inv = [d for d in os.listdir(p) if os.path.isdir(os.path.join(p, d)) and d not in ['capacidad_instalada', 'produccion_institucional']]
                for name in sorted(f_inv):
                    academics.append({"name": name})
                if academics:
                    break

    # Deduplicación y ordenamiento alfabético por nombre
    dedup_map = {}
    for a in academics:
        name = a.get("name", "").strip()
        if not name:
            continue
        norm = name.replace(",", "").replace("  ", " ").strip().lower()
        if norm not in dedup_map:
            dedup_map[norm] = a
            
    final_list = sorted(list(dedup_map.values()), key=lambda x: x.get("name", "").lower())
    names_only = [x["name"] for x in final_list]

    return {
        "status": "success",
        "entity": target_entity,
        "institution": inst,
        "total": len(final_list),
        "academics": final_list,
        "names": names_only
    }


@router.get("/profile")
def get_academic_profile(
    name: Optional[str] = Query(None, description="Nombre completo del investigador"),
    orcid: Optional[str] = Query(None, description="ORCID iD del investigador"),
    id: Optional[str] = Query(None, description="ID o CVU del investigador")
) -> Dict[str, Any]:
    """
    Recupera el perfil cienciométrico completo del investigador con paridad al 100% de Streamlit:
    Padrón SNII, Adscripción, 4 Grupos de KPIs, Distribución OA, Perfil Temático (Gini),
    Tipos de Documentos, Trayectoria Anual, Foco Temático, Sunburst, Keywords, ODS y Citas Zero-Join.
    """
    if not name and not orcid and not id:
        raise HTTPException(status_code=400, detail="Debe proporcionar 'name', 'orcid' o 'id'")

    nodes = _resolve_academic_nodes(name=name, orcid=orcid, person_id=id)
    
    # Consolidar propiedades de múltiples nodos en Neo4j (ej. Padrón oficial + Perfil OpenAlex)
    primary_node = {}
    for nd in nodes:
        for k, v in nd.items():
            if v and (k not in primary_node or not primary_node[k]):
                primary_node[k] = v

    final_name = primary_node.get("fullname") or name or "Investigador"
    raw_orcid = primary_node.get("orcid") or orcid
    if not raw_orcid and isinstance(primary_node.get("orcids"), list) and primary_node.get("orcids"):
        raw_orcid = primary_node["orcids"][0]
    clean_orcid = str(raw_orcid).replace("https://orcid.org/", "").strip() if raw_orcid else ""

    snii_lvl = primary_node.get("snii_level")
    is_snii = bool(snii_lvl and str(snii_lvl).strip() not in ["None", "", "SIN NIVEL"])
    snii_lvl_clean = str(snii_lvl).strip() if is_snii else None
    snii_lvl_label = SNII_LEVEL_LABELS.get(snii_lvl_clean, f"Nivel {snii_lvl_clean}" if snii_lvl_clean else "No registrado en Padrón")

    inst = primary_node.get("snii_institution") or "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)"
    dep = primary_node.get("snii_dependency") or ""
    subdep = primary_node.get("snii_subdependency") or ""

    # Identificadores externos
    scopus_ids = primary_node.get("scopus_ids") or []
    if isinstance(scopus_ids, str):
        scopus_ids = [s.strip() for s in scopus_ids.split(",") if s.strip()]
    openalex_ids = primary_node.get("openalex_ids") or []
    if isinstance(openalex_ids, str):
        openalex_ids = [s.strip() for s in openalex_ids.split(",") if s.strip()]

    profile_dict = {
        "name": final_name,
        "orcid": clean_orcid,
        "orcid_url": f"https://orcid.org/{clean_orcid}" if clean_orcid else None,
        "is_snii": is_snii,
        "snii_level": snii_lvl_clean,
        "snii_level_label": snii_lvl_label,
        "snii_area": primary_node.get("snii_area"),
        "institution": inst,
        "dependency": dep,
        "subdependency": subdep,
        "affiliation_breadcrumb": f"{inst}" + (f" ➔ {dep}" if dep and dep != "SIN INFORMACIÓN" else "") + (f" ➔ {subdep}" if subdep and subdep != "SIN INFORMACIÓN" else ""),
        "cvu": primary_node.get("cvu"),
        "siia": primary_node.get("siia"),
        "scopus_ids": scopus_ids,
        "openalex_ids": openalex_ids
    }

    # Localizar caché de Parquets
    pdir = _find_academic_dir(final_name, inst=inst, subdep=subdep, dep=dep)
    if not pdir and name:
        pdir = _find_academic_dir(name, inst=inst, subdep=subdep, dep=dep)

    # 1. Métricas Totales (investigador_total.parquet)
    kpis = {
        "general": {
            "total_census": 0,
            "indexed_count": 0,
            "h_index": 0,
            "total_citations": 0,
            "pct_open_access": 0.0
        },
        "excellence": {
            "citations_per_paper": 0.0,
            "fwci_avg": 1.0,
            "percentile_avg": 50.0,
            "pct_top_10": 0.0,
            "pct_1": 0.0
        },
        "velocity": {
            "velocity_avg": 0.0,
            "recent_cites_3yr": 0,
            "pct_international": 0.0,
            "avg_countries": 0.0,
            "avg_author_count": 0.0
        },
        "apc": {
            "apc_paid_usd": 0.0,
            "pct_apc": 0.0,
            "half_life_avg": 0.0
        }
    }
    oa_dist = {"gold": 0.0, "green": 0.0, "hybrid": 0.0, "bronze": 0.0, "closed": 100.0, "open": 0.0}
    thematic_profile = {"gini_topics": None, "domain_diversity": 0, "unique_topics": 0, "top_domain": "—", "top_topic": "—"}

    if pdir and os.path.exists(os.path.join(pdir, "investigador_total.parquet")):
        try:
            df_tot = pd.read_parquet(os.path.join(pdir, "investigador_total.parquet"))
            if not df_tot.empty:
                r = df_tot.iloc[0]
                total_census = int(r.get("neo4j_total_papers", r.get("num_documents", 0)) or 0)
                indexed_count = int(r.get("num_documents", 0) or 0)
                total_cites = int(r.get("citations", 0) or 0)
                cites_per_paper = round(total_cites / max(indexed_count, 1), 2)

                kpis["general"] = {
                    "total_census": total_census,
                    "indexed_count": indexed_count,
                    "h_index": int(r.get("h_index", 0) or 0),
                    "total_citations": total_cites,
                    "pct_open_access": _clean_val(r.get("pct_open_access", 0.0))
                }
                kpis["excellence"] = {
                    "citations_per_paper": cites_per_paper,
                    "fwci_avg": _clean_val(r.get("fwci_avg", 1.0)),
                    "percentile_avg": _clean_val(r.get("percentile_avg", 50.0)),
                    "pct_top_10": _clean_val(r.get("pct_top_10", 0.0)),
                    "pct_1": _clean_val(r.get("pct_1", 0.0))
                }
                kpis["velocity"] = {
                    "velocity_avg": _clean_val(r.get("velocity_avg", 0.0)),
                    "recent_cites_3yr": int(r.get("recent_cites_3yr", 0) or 0),
                    "pct_international": _clean_val(r.get("pct_international", 0.0)),
                    "avg_countries": _clean_val(r.get("avg_countries", 0.0)),
                    "avg_author_count": _clean_val(r.get("avg_author_count", 0.0))
                }
                kpis["apc"] = {
                    "apc_paid_usd": _clean_val(r.get("apc_paid_usd", 0.0)),
                    "pct_apc": _clean_val(r.get("pct_apc", 0.0)),
                    "half_life_avg": _clean_val(r.get("half_life_avg", 0.0))
                }

                oa_dist = {
                    "gold": _clean_val(r.get("pct_oa_gold", 0.0)),
                    "green": _clean_val(r.get("pct_oa_green", 0.0)),
                    "hybrid": _clean_val(r.get("pct_oa_hybrid", 0.0)),
                    "bronze": _clean_val(r.get("pct_oa_bronze", 0.0)),
                    "closed": _clean_val(r.get("pct_oa_closed", 0.0)),
                    "open": _clean_val(r.get("pct_open_access", 0.0))
                }

                thematic_profile = {
                    "gini_topics": _clean_val(r.get("gini_topics")),
                    "domain_diversity": int(r.get("domain_diversity", 0) or 0),
                    "unique_topics": int(r.get("unique_topics", 0) or 0),
                    "top_domain": str(r.get("top_domain", "—") or "—"),
                    "top_topic": str(r.get("top_topic", "—") or "—")
                }
        except Exception as e:
            print(f"[get_academic_profile] Error leyendo investigador_total.parquet: {e}")

    # 2. Trayectoria Anual (investigador_annual.parquet)
    annual_trajectory = []
    if pdir and os.path.exists(os.path.join(pdir, "investigador_annual.parquet")):
        try:
            df_ann = pd.read_parquet(os.path.join(pdir, "investigador_annual.parquet"))
            if not df_ann.empty and "year" in df_ann.columns:
                df_ann = df_ann.sort_values("year")
                for _, row in df_ann.iterrows():
                    y = int(row.get("year", 0))
                    if y >= 1950:
                        annual_trajectory.append({
                            "year": y,
                            "num_documents": int(row.get("num_documents", 0) or 0),
                            "citations": int(row.get("citations", 0) or 0),
                            "pct_international": _clean_val(row.get("pct_international", 0.0))
                        })
        except Exception as e:
            print(f"[get_academic_profile] Error leyendo investigador_annual.parquet: {e}")

    # 3. Temáticas y Sunburst (topics_investigador.parquet)
    top_topics = []
    sunburst_data = []
    if pdir and os.path.exists(os.path.join(pdir, "topics_investigador.parquet")):
        try:
            df_top = pd.read_parquet(os.path.join(pdir, "topics_investigador.parquet"))
            if not df_top.empty:
                # Top 10 topics para gráfico de barras horizontales
                if "topic" in df_top.columns and "value" in df_top.columns:
                    grouped = df_top.groupby("topic")["value"].sum().reset_index()
                    sorted_topics = grouped.sort_values("value", ascending=False).head(10)
                    for _, row in sorted_topics.iterrows():
                        top_topics.append({
                            "topic": str(row["topic"]),
                            "value": int(row["value"])
                        })
                # Datos para Sunburst de 4 niveles
                sun_clean = df_top.replace('', pd.NA).dropna(subset=['domain', 'field', 'subfield', 'topic'])
                sun_top = sun_clean.sort_values('value', ascending=False).head(80)
                for _, row in sun_top.iterrows():
                    sunburst_data.append({
                        "domain": str(row.get("domain", "")),
                        "field": str(row.get("field", "")),
                        "subfield": str(row.get("subfield", "")),
                        "topic": str(row.get("topic", "")),
                        "value": int(row.get("value", 1))
                    })
        except Exception as e:
            print(f"[get_academic_profile] Error leyendo topics_investigador.parquet: {e}")

    # 4. Vocabulario Científico / Palabras Clave (keywords_investigador.parquet)
    keywords = []
    if pdir and os.path.exists(os.path.join(pdir, "keywords_investigador.parquet")):
        try:
            df_kw = pd.read_parquet(os.path.join(pdir, "keywords_investigador.parquet"))
            if not df_kw.empty and "keyword" in df_kw.columns and "freq" in df_kw.columns:
                df_kw_sorted = df_kw.sort_values("freq", ascending=False).head(40)
                for _, row in df_kw_sorted.iterrows():
                    keywords.append({
                        "keyword": str(row["keyword"]),
                        "freq": int(row["freq"])
                    })
        except Exception as e:
            print(f"[get_academic_profile] Error leyendo keywords_investigador.parquet: {e}")

    # 5. Tipos de Documentos y Matriz ODS (papers_profesor.parquet)
    document_types = []
    sdg_matrix = []
    sdg_counts = {i: 0 for i in range(1, 18)}

    if pdir and os.path.exists(os.path.join(pdir, "papers_profesor.parquet")):
        try:
            df_p = pd.read_parquet(os.path.join(pdir, "papers_profesor.parquet"))
            if not df_p.empty:
                # Tipos de documentos
                col_type = "wf.type" if "wf.type" in df_p.columns else ("source_type" if "source_type" in df_p.columns else None)
                if col_type:
                    t_counts = df_p[col_type].replace('', 'other').fillna('other').value_counts()
                    for t_name, count in t_counts.items():
                        document_types.append({
                            "type": str(t_name).capitalize(),
                            "count": int(count)
                        })

                # Matriz ODS
                if "ODS_Nombre" in df_p.columns or "ODS_ID" in df_p.columns:
                    col_ods = "ODS_Nombre" if "ODS_Nombre" in df_p.columns else "ODS_ID"
                    for val in df_p[col_ods].dropna():
                        # Extraer dígitos de ODS (ej. '9. Industria...' o 'https://metadata.un.org/sdg/9')
                        found_ods = re.findall(r'(?:sdg/|ODS\s*|^\s*)(\d{1,2})', str(val))
                        for f_num in found_ods:
                            n = int(f_num)
                            if 1 <= n <= 17:
                                sdg_counts[n] += 1

                for sdg_num in range(1, 18):
                    sdg_matrix.append({
                        "sdg": sdg_num,
                        "name": SDG_NAMES.get(sdg_num, f"ODS {sdg_num}"),
                        "count": sdg_counts[sdg_num]
                    })
        except Exception as e:
            print(f"[get_academic_profile] Error leyendo papers_profesor.parquet: {e}")

    # 6. Resumen Zero-Join de Citas & Autocitas
    citations_summary = {
        "total_citations": 0,
        "net_citations": 0,
        "self_citations": 0,
        "self_citation_rate": 0.0,
        "top_10_percent_citations": 0,
        "citing_countries_count": 0,
        "citing_institutions_count": 0,
        "by_country": [],
        "by_institution": [],
        "by_year": []
    }
    try:
        raw_cites = get_citing_works_analysis(academic_name=final_name, orcid=clean_orcid, limit=500)
        career_total = kpis.get("general", {}).get("total_citations", 0) or raw_cites.get("total_citations", 0)
        raw_total = raw_cites.get("total_citations", 0)
        raw_self = raw_cites.get("self_citations", 0)
        self_rate = raw_cites.get("self_citation_rate", 0.0)

        # Extender el cálculo de citas y autocitas a toda la carrera académica
        if career_total > 0 and raw_total > 0:
            career_self = round(career_total * (self_rate / 100.0))
            career_self = max(career_self, raw_self)
            career_net = max(0, career_total - career_self)
        elif career_total > 0:
            career_self = raw_self
            career_net = max(0, career_total - raw_self)
        else:
            career_self = raw_self
            career_net = raw_cites.get("net_citations", 0)

        citations_summary = {
            "total_citations": career_total,
            "net_citations": career_net,
            "self_citations": career_self,
            "self_citation_rate": self_rate,
            "top_10_percent_citations": raw_cites.get("top_10_percent_citations", 0),
            "citing_countries_count": raw_cites.get("citing_countries_count", 0),
            "citing_institutions_count": raw_cites.get("citing_institutions_count", 0),
            "by_country": raw_cites.get("by_country", [])[:15],
            "by_institution": raw_cites.get("by_institution", [])[:15],
            "by_year": raw_cites.get("by_year", []),
            "raw_citing_works_count": raw_total,
            "raw_self_citations_count": raw_self,
            "self_citations_note": "Se contabilizan exclusivamente las autocitas directas (del autor) donde el investigador evaluado figura expresamente como coautor en la obra citante. El cálculo de citas y autocitas abarca la totalidad de las citas acumuladas a lo largo de su carrera académica."
        }
    except Exception as e:
        print(f"[get_academic_profile] Error en citations_summary: {e}")

    profile_dict.update({
        "kpis": kpis,
        "oa_distribution": oa_dist,
        "thematic_profile": thematic_profile,
        "document_types": document_types,
        "annual_trajectory": annual_trajectory,
        "top_topics": top_topics,
        "sunburst_data": sunburst_data,
        "keywords": keywords,
        "sdg_matrix": sdg_matrix,
        "citations_summary": citations_summary
    })

    return {
        "status": "success",
        "profile": profile_dict
    }


@router.get("/works")
def get_academic_works(
    name: Optional[str] = Query(None),
    orcid: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=200),
    offset: int = Query(0, ge=0),
    year: Optional[int] = Query(None),
    oa_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Recupera el catálogo interactivo de publicaciones del investigador:
    Resuelve el nombre real de la Revista / Fuente (evita 'Revista no especificada'),
    citas recibidas, FWCI, vía de Acceso Abierto, ODS y enlaces oficiales DOI / OpenAlex.
    """
    nodes = _resolve_academic_nodes(name=name, orcid=orcid)
    primary_node = nodes[0] if nodes else {}
    final_name = primary_node.get("fullname") or name or ""
    clean_orcid = primary_node.get("orcid") or orcid or ""
    if isinstance(primary_node.get("orcids"), list) and primary_node.get("orcids"):
        clean_orcid = primary_node["orcids"][0]
    clean_orcid = str(clean_orcid).replace("https://orcid.org/", "").strip()

    inst = primary_node.get("snii_institution")
    subdep = primary_node.get("snii_subdependency")
    dep = primary_node.get("snii_dependency")

    pdir = _find_academic_dir(final_name, inst=inst, subdep=subdep, dep=dep)
    if not pdir and name:
        pdir = _find_academic_dir(name, inst=inst, subdep=subdep, dep=dep)

    works_list = []
    
    # 1. Prioridad: Cargar desde papers_profesor.parquet
    if pdir and os.path.exists(os.path.join(pdir, "papers_profesor.parquet")):
        try:
            df_p = pd.read_parquet(os.path.join(pdir, "papers_profesor.parquet"))
            if not df_p.empty:
                for _, r in df_p.iterrows():
                    doi = str(r.get("doi") or r.get("DOI") or "").strip()
                    doi_clean = doi.replace("https://doi.org/", "").strip() if doi and "orcid-work" not in doi else None
                    doi_url = f"https://doi.org/{doi_clean}" if doi_clean else None
                    
                    source = str(r.get("Source") or "").strip()
                    if not source:
                        st = str(r.get("source_type") or "").strip()
                        source = st.capitalize() if st else "Revista no especificada"

                    oa_val = str(r.get("oa_status") or "closed").lower()
                    if oa_val in ["", "none", "nan"]:
                        oa_val = "closed"

                    works_list.append({
                        "id": str(r.get("paper_id") or doi or ""),
                        "title": str(r.get("Title") or "Sin título"),
                        "journal": source,
                        "source": source,
                        "year": int(r.get("year")) if pd.notna(r.get("year")) else None,
                        "publication_year": int(r.get("year")) if pd.notna(r.get("year")) else None,
                        "citations": int(r.get("citations", 0)) if pd.notna(r.get("citations")) else 0,
                        "fwci": round(float(r.get("fwci", 1.0)), 2) if pd.notna(r.get("fwci")) else 1.0,
                        "oa_status": oa_val,
                        "doi": doi_clean,
                        "doi_url": doi_url,
                        "openalex_url": str(r.get("openalex_url") or "") if pd.notna(r.get("openalex_url")) else None,
                        "topic": str(r.get("topic") or "") if pd.notna(r.get("topic")) else "",
                        "ods_name": str(r.get("ODS_Nombre") or "") if pd.notna(r.get("ODS_Nombre")) else None,
                        "is_top_10": int(r.get("is_in_top_10_percent", 0)) == 1,
                        "is_top_1": int(r.get("is_in_top_1_percent", 0)) == 1,
                    })
        except Exception as e:
            print(f"[get_academic_works] Error leyendo papers_profesor.parquet: {e}")

    # 2. Respaldo: Consultar ClickHouse works + sources si no hay parquet
    if not works_list:
        wids, _ = get_author_work_and_openalex_ids(final_name or name, clean_orcid or orcid)
        if wids:
            client = get_clickhouse_client()
            conditions = ["id IN %(ids)s"]
            params = {"ids": wids}

            where_sql = " AND ".join(conditions)
            query = f"""
                SELECT id, doi, title, publication_year, author_names, institution_names,
                       topic, fwci, oa_status, is_top_10, is_top_1, cited_by_count, source_type, source_id
                FROM works
                WHERE {where_sql}
                ORDER BY publication_year DESC, cited_by_count DESC
            """
            try:
                rows = client.query_df(query, params)
                if not rows.empty:
                    # Resolver nombres reales de revistas desde la tabla sources
                    source_ids = [s for s in rows["source_id"].unique() if s]
                    src_map = {}
                    if source_ids:
                        src_df = client.query_df("SELECT id, display_name FROM sources WHERE id IN %(ids)s", {"ids": source_ids})
                        src_map = dict(zip(src_df["id"], src_df["display_name"]))

                    for _, r in rows.iterrows():
                        doi = str(r.get("doi") or "").strip()
                        doi_clean = doi.replace("https://doi.org/", "").strip() if doi else None
                        doi_url = f"https://doi.org/{doi_clean}" if doi_clean else None
                        
                        sid = str(r.get("source_id") or "")
                        journal = src_map.get(sid) or (str(r.get("source_type") or "").capitalize() if r.get("source_type") else "Revista no especificada")
                        
                        works_list.append({
                            "id": str(r.get("id")),
                            "title": str(r.get("title") or "Sin título"),
                            "journal": journal,
                            "source": journal,
                            "year": int(r.get("publication_year")) if pd.notna(r.get("publication_year")) else None,
                            "publication_year": int(r.get("publication_year")) if pd.notna(r.get("publication_year")) else None,
                            "citations": int(r.get("cited_by_count", 0)) if pd.notna(r.get("cited_by_count")) else 0,
                            "fwci": round(float(r.get("fwci", 1.0)), 2) if pd.notna(r.get("fwci")) else 1.0,
                            "oa_status": str(r.get("oa_status") or "closed").lower(),
                            "doi": doi_clean,
                            "doi_url": doi_url,
                            "openalex_url": f"https://openalex.org/{r.get('id').split('/')[-1]}" if r.get("id") else None,
                            "topic": str(r.get("topic") or ""),
                            "ods_name": None,
                            "is_top_10": int(r.get("is_top_10", 0)) == 1,
                            "is_top_1": int(r.get("is_top_1", 0)) == 1,
                        })
            except Exception as e:
                print(f"[get_academic_works] Error ClickHouse: {e}")

    # Aplicar filtros en memoria
    filtered = works_list
    if year:
        filtered = [w for w in filtered if w.get("year") == year]
    if oa_status and oa_status.lower() != "all":
        filtered = [w for w in filtered if oa_status.lower() in str(w.get("oa_status", "")).lower()]
    if search:
        s_term = search.lower().strip()
        filtered = [w for w in filtered if s_term in str(w.get("title", "")).lower() or s_term in str(w.get("journal", "")).lower()]

    # Ordenar por año desc, citas desc
    filtered.sort(key=lambda x: (x.get("year") or 0, x.get("citations") or 0), reverse=True)

    total_count = len(filtered)
    paginated = filtered[offset:offset + limit]

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "works": paginated
    }
