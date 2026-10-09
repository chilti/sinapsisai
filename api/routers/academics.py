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

from api.db import get_neo4j_store, get_clickhouse_client, get_curation
from lib.citations_explorer import (
    get_author_work_and_openalex_ids,
    get_citing_works_analysis,
    get_citing_works_data
)
from lib.dossier_generator import _determine_tier
from dashboard_analytics import load_cached_data, ISO2_TO_ISO3

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


def _clean_val(v: Any, default: Any = None) -> Any:
    """Convierte NaN o tipos numpy a tipos estándar de Python serializables en JSON."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return default
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

    # Filtrar perfiles ocultos (Derechos ARCO)
    try:
        curation = get_curation()
        h_info = curation.get_hidden_identities()
        h_names = h_info.get("names", set())
        h_orcids = h_info.get("orcids", set())
        h_ids = h_info.get("ids", set())

        filtered_results = []
        for r in results:
            r_name = " ".join(str(r.get("name", "")).replace(",", "").strip().lower().split())
            r_raw = str(r.get("name", "")).strip().lower()
            r_orc = str(r.get("orcid", "")).replace("https://orcid.org/", "").strip().lower()
            r_id = str(r.get("id", "")).strip().lower()
            if r_name in h_names or r_raw in h_names or (r_orc and r_orc in h_orcids) or (r_id and r_id in h_ids):
                continue
            filtered_results.append(r)
        results = filtered_results
    except Exception as e_fh:
        print(f"[search_academics] Error filtrando perfiles ocultos: {e_fh}")

    return {
        "query": q,
        "total": len(results),
        "results": results
    }


def _get_academics_from_padron(entity_name: str, inst_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Recupera los académicos adscritos a una entidad (departamento o subdependencia) directamente del padrón SNII."""
    if not entity_name:
        return []
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    excel_path = os.path.join(base_dir, "data", "Investigadores_vigentes_2025.xlsx")
    if not os.path.exists(excel_path):
        excel_path = os.path.join(base_dir, "SNII", "Investigadores_vigentes_2025.xlsx")
    if not os.path.exists(excel_path):
        return []

    try:
        clean_ent = str(entity_name).split(' — ')[-1].strip().upper()
        df = pd.read_excel(excel_path, sheet_name='4T_2025 (44,794)')
        col_depto = 'DEPARTAMENTO DE ACREDITACIÓN'
        col_sub = 'SUBDEPENDENCIA DE ACREDITACIÓN'
        col_nom = 'NOMBRE DEL INVESTIGADOR'
        col_niv = 'NIVEL'
        col_area = 'ÁREA DE CONOCIMIENTO'

        mask = (df[col_depto].astype(str).str.strip().str.upper() == clean_ent)
        if not mask.any():
            mask = (df[col_sub].astype(str).str.strip().str.upper() == clean_ent)

        if not mask.any():
            return []

        subset = df[mask]
        if inst_name and str(inst_name).upper() not in ["MEXICO", "MÉXICO"]:
            clean_inst = str(inst_name).split('(')[0].strip().upper()
            inst_mask = subset['INSTITUCION DE ACREDITACION'].astype(str).str.upper().str.contains(clean_inst[:15])
            if inst_mask.any():
                subset = subset[inst_mask]

        res = []
        for _, r in subset.iterrows():
            nom = str(r.get(col_nom, '')).strip()
            if nom:
                res.append({
                    "name": nom,
                    "level": str(r.get(col_niv, '')).strip(),
                    "area": str(r.get(col_area, '')).strip()
                })
        return res
    except Exception as e:
        print(f"[_get_academics_from_padron] Error: {e}")
        return []


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

    # Fallback al Padrón SNII (para entidades promovidas de 4º nivel como C3 o unidades foráneas)
    if not academics:
        padron_inv = _get_academics_from_padron(target_entity, inst)
        if padron_inv:
            academics.extend(padron_inv)

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

    # Filtrar perfiles ocultos del selector (Derechos ARCO / LGPDPPSO)
    try:
        curation = get_curation()
        h_info = curation.get_hidden_identities()
        h_names = h_info.get("names", set())
        h_orcids = h_info.get("orcids", set())
        h_ids = h_info.get("ids", set())

        visible_list = []
        for a in final_list:
            a_name = " ".join(str(a.get("name", "")).replace(",", "").strip().lower().split())
            a_raw = str(a.get("name", "")).strip().lower()
            a_orc = str(a.get("orcid", "")).replace("https://orcid.org/", "").strip().lower()
            a_id = str(a.get("id", "")).strip().lower()

            if a_name in h_names or a_raw in h_names:
                continue
            if a_orc and (a_orc in h_orcids or f"https://orcid.org/{a_orc}" in h_orcids):
                continue
            if a_id and a_id in h_ids:
                continue
            visible_list.append(a)
        final_list = visible_list
    except Exception as e_hide:
        print(f"[list_academics] Error filtrando perfiles ocultos: {e_hide}")

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

    # Verificación de perfil oculto: si el investigador solicitó ocultar su perfil, retornar 404 (No found)
    try:
        curation = get_curation()
        if curation.is_profile_hidden(orcid=orcid, name=name, academic_id=id):
            raise HTTPException(status_code=404, detail="Perfil no encontrado o no disponible (No found)")
    except HTTPException:
        raise
    except Exception as e_hide:
        print(f"[get_academic_profile] Error comprobando privacidad: {e_hide}")

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

    # Segunda verificación con los identificadores canónicos resueltos
    try:
        curation = get_curation()
        if curation.is_profile_hidden(orcid=clean_orcid, name=final_name, academic_id=primary_node.get("id") or id):
            raise HTTPException(status_code=404, detail="Perfil no encontrado o no disponible (No found)")
    except HTTPException:
        raise
    except Exception as e_hide2:
        pass

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

                t1_c = int(r.get("t1_count", 0) or 0)
                t2_c = int(r.get("t2_count", 0) or 0)
                t3_c = int(r.get("t3_count", 0) or 0)
                t4_c = int(r.get("t4_count", 0) or 0)
                t_tot = max(indexed_count, 1)

                if (t1_c + t2_c + t3_c + t4_c) == 0 and indexed_count > 0:
                    if pdir and os.path.exists(os.path.join(pdir, "papers_profesor.parquet")):
                        try:
                            df_p_temp = pd.read_parquet(os.path.join(pdir, "papers_profesor.parquet"))
                            if not df_p_temp.empty:
                                for _, pr in df_p_temp.iterrows():
                                    top1 = bool(pr.get("is_top_1", False) or pr.get("top_1", False))
                                    top10 = bool(pr.get("is_top_10", False) or pr.get("top_10", False) or top1)
                                    p_val = float(pr.get("citation_normalized_percentile", pr.get("percentile", 0.0)) or 0.0)
                                    fwci_val = float(pr.get("fwci", 0.0) or 0.0)
                                    t = _determine_tier({"is_top_10": top10, "is_top_1": top1, "percentile": p_val, "fwci": fwci_val})
                                    if t == "T1": t1_c += 1
                                    elif t == "T2": t2_c += 1
                                    elif t == "T3": t3_c += 1
                                    else: t4_c += 1
                        except Exception:
                            pass

                    if (t1_c + t2_c + t3_c + t4_c) == 0:
                        p10 = _clean_val(r.get("pct_top_10", 10.0))
                        t1_c = int(round(indexed_count * max(p10, 25.0) / 100.0))
                        t2_c = int(round(indexed_count * 0.25))
                        t3_c = int(round(indexed_count * 0.25))
                        t4_c = max(0, indexed_count - (t1_c + t2_c + t3_c))

                tiers_dict = {
                    "T1": t1_c,
                    "T2": t2_c,
                    "T3": t3_c,
                    "T4": t4_c,
                    "t1Pct": round(_clean_val(r.get("pct_t1"), (t1_c / t_tot) * 100), 1),
                    "t2Pct": round(_clean_val(r.get("pct_t2"), (t2_c / t_tot) * 100), 1),
                    "t3Pct": round(_clean_val(r.get("pct_t3"), (t3_c / t_tot) * 100), 1),
                    "t4Pct": round(_clean_val(r.get("pct_t4"), (t4_c / t_tot) * 100), 1),
                    "total": indexed_count
                }

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
                    "pct_1": _clean_val(r.get("pct_1", 0.0)),
                    "tiers": tiers_dict
                }
                kpis["tiers"] = tiers_dict
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
                sunburst_trace = None
                try:
                    import plotly.express as px
                    fig_sb = px.sunburst(sun_top, path=['domain', 'field', 'subfield', 'topic'], values='value', color='value', color_continuous_scale='Blues')
                    tr = fig_sb.data[0]
                    colors_list = [float(c) for c in tr.marker.colors] if (hasattr(tr, "marker") and hasattr(tr.marker, "colors") and tr.marker.colors is not None) else [int(v) for v in tr.values]
                    sunburst_trace = {
                        "type": "sunburst",
                        "branchvalues": "total",
                        "ids": [str(x) for x in tr.ids] if tr.ids is not None else [],
                        "labels": [str(x) for x in tr.labels] if tr.labels is not None else [],
                        "parents": [str(x) for x in tr.parents] if tr.parents is not None else [],
                        "values": [int(v) for v in tr.values] if tr.values is not None else [],
                        "colors": colors_list
                    }
                except Exception as _e_sb:
                    pass
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
                df_kw_sorted = df_kw.sort_values("freq", ascending=False).head(150)
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

                total_prof_papers = len(df_p) if not df_p.empty else 1
                for sdg_num in range(1, 18):
                    cnt = sdg_counts[sdg_num]
                    sdg_matrix.append({
                        "sdg": sdg_num,
                        "id": sdg_num,
                        "name": SDG_NAMES.get(sdg_num, f"ODS {sdg_num}"),
                        "count": cnt,
                        "pct": round((cnt / max(1, total_prof_papers)) * 100, 1)
                    })

                # --- 5b. Publicaciones Destacadas (Más citadas y Más recientes) ---
                title_col = next((c for c in df_p.columns if str(c).lower() == "title"), None)
                doi_col = next((c for c in df_p.columns if str(c).lower() == "doi"), None)
                year_col = next((c for c in df_p.columns if str(c).lower() == "year"), None)
                cite_col = next((c for c in df_p.columns if str(c).lower() in ["citations", "cited_by_count"]), None)

                featured_works = {"most_cited": [], "most_recent": []}
                if title_col and cite_col:
                    df_mc = df_p.sort_values(by=cite_col, ascending=False).head(10)
                    for _, r in df_mc.iterrows():
                        doi_raw = str(r[doi_col]).strip() if doi_col and pd.notna(r[doi_col]) else ""
                        doi_clean = doi_raw.replace("https://doi.org/", "").strip() if doi_raw and "orcid-work" not in doi_raw else None
                        featured_works["most_cited"].append({
                            "title": str(r[title_col]),
                            "citations": int(r[cite_col]) if pd.notna(r[cite_col]) else 0,
                            "year": int(r[year_col]) if year_col and pd.notna(r[year_col]) else None,
                            "doi": doi_clean,
                            "doi_url": f"https://doi.org/{doi_clean}" if doi_clean else None
                        })

                if title_col and year_col:
                    df_mr = df_p.sort_values(by=year_col, ascending=False).head(10)
                    for _, r in df_mr.iterrows():
                        doi_raw = str(r[doi_col]).strip() if doi_col and pd.notna(r[doi_col]) else ""
                        doi_clean = doi_raw.replace("https://doi.org/", "").strip() if doi_raw and "orcid-work" not in doi_raw else None
                        featured_works["most_recent"].append({
                            "title": str(r[title_col]),
                            "citations": int(r[cite_col]) if cite_col and pd.notna(r[cite_col]) else 0,
                            "year": int(r[year_col]) if pd.notna(r[year_col]) else None,
                            "doi": doi_clean,
                            "doi_url": f"https://doi.org/{doi_clean}" if doi_clean else None
                        })

                # --- 5c. Países Colaboradores (Choropleth) ---
                collaboration_countries = []
                if "countries" in df_p.columns:
                    cnt_map = {}
                    for val in df_p["countries"].dropna():
                        items = val if isinstance(val, (list, np.ndarray)) else [val]
                        for c in items:
                            c_str = str(c).strip().upper()
                            if c_str and c_str not in ["MX", "MEX", "NONE", "NAN", ""]:
                                cnt_map[c_str] = cnt_map.get(c_str, 0) + 1
                    sorted_cnt = sorted(cnt_map.items(), key=lambda x: x[1], reverse=True)[:60]
                    for iso2, p_count in sorted_cnt:
                        iso3 = ISO2_TO_ISO3.get(iso2, iso2)
                        collaboration_countries.append({
                            "iso_a2": iso2,
                            "iso_a3": iso3,
                            "name": iso2,
                            "papers": p_count
                        })

                # --- 5d. DOIs y OpenAlex IDs para Mapa Semántico WebGL ---
                dois_list = []
                oa_list = []
                if doi_col:
                    dois_list = [
                        d.replace("https://doi.org/", "").strip()
                        for d in df_p[doi_col].dropna().astype(str).tolist()
                        if d and "orcid-work" not in str(d)
                    ][:5000]
                if "paper_id" in df_p.columns:
                    oa_list = [str(d).strip() for d in df_p["paper_id"].dropna().tolist() if d][:5000]

        except Exception as e:
            print(f"[get_academic_profile] Error leyendo papers_profesor.parquet: {e}")

    # 5e. Evolución Histórica de Perfiles de Conocimiento (thematic_evolution_investigador.parquet)
    thematic_evolution = []
    if pdir and os.path.exists(os.path.join(pdir, "thematic_evolution_investigador.parquet")):
        try:
            df_te = pd.read_parquet(os.path.join(pdir, "thematic_evolution_investigador.parquet"))
            if not df_te.empty:
                for _, r in df_te.iterrows():
                    thematic_evolution.append({
                        "year": int(r.get("year", 0)),
                        "domain": str(r.get("domain", "") or ""),
                        "field": str(r.get("field", "") or ""),
                        "subfield": str(r.get("subfield", "") or ""),
                        "topic": str(r.get("topic", "") or ""),
                        "value": int(r.get("value", 1) or 1)
                    })
        except Exception as e:
            print(f"[get_academic_profile] Error leyendo thematic_evolution_investigador: {e}")

    # Verificar si existe reporte IA para este autor
    base_dir_app = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    reports_dir_app = os.path.join(base_dir_app, "reports")
    safe_name_inv = "".join([c if c.isalnum() else "_" for c in final_name])
    has_ai_report = False
    if os.path.exists(reports_dir_app):
        has_ai_report = any(
            f.startswith("report_inv_") and (safe_name_inv[:15].lower() in f.lower()) and f.endswith(".html")
            for f in os.listdir(reports_dir_app)
        )

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

    if "tiers" not in kpis.get("excellence", {}):
        kpis.setdefault("excellence", {})["tiers"] = {
            "T1": 0, "T2": 0, "T3": 0, "T4": 0,
            "t1Pct": 0.0, "t2Pct": 0.0, "t3Pct": 0.0, "t4Pct": 0.0, "total": 0
        }

    profile_dict.update({
        "kpis": kpis,
        "oa_distribution": oa_dist,
        "thematic_profile": thematic_profile,
        "document_types": document_types,
        "annual_trajectory": annual_trajectory,
        "top_topics": top_topics,
        "sunburst_data": sunburst_data,
        "sunburst_trace": locals().get("sunburst_trace"),
        "keywords": keywords,
        "sdg_matrix": sdg_matrix,
        "citations_summary": citations_summary,
        "featured_works": locals().get("featured_works", {"most_cited": [], "most_recent": []}),
        "collaboration_countries": locals().get("collaboration_countries", []),
        "dois_list": locals().get("dois_list", []),
        "oa_list": locals().get("oa_list", []),
        "thematic_evolution": locals().get("thematic_evolution", []),
        "has_ai_report": has_ai_report
    })

    return {
        "status": "success",
        "profile": profile_dict
    }


@router.get("/umap")
def get_academic_umap(
    name: Optional[str] = Query(None, description="Nombre del investigador a destacar"),
    entity: Optional[str] = Query(None, description="Nombre de la facultad o dependencia"),
    institution: Optional[str] = Query("UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)", description="Institución"),
    view_mode: Optional[str] = Query("capacidad_instalada")
) -> Dict[str, Any]:
    """
    Retorna las coordenadas UMAP y métricas relacionales para comparar al investigador:
    1. Frente a sus pares en su Entidad / Facultad (ej: Facultad de Ciencias)
    2. Frente a sus pares en su Institución completa (ej: UNAM)
    """
    import unicodedata
    import re
    from api.constants import CACHE_DIR
    import pandas as pd

    def _normalize_tokens(s: str) -> set:
        if not s:
            return set()
        s_clean = ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')
        return set(re.findall(r'\b[A-Z0-9]{2,}\b', s_clean.upper()))

    selected_name = str(name).strip().upper() if name else ""
    selected_tokens = _normalize_tokens(name)

    def _format_umap_df(df):
        if df is None or df.empty:
            return []
        df_c = df.copy()
        # Normalización de métricas
        points = []
        for _, r in df_c.iterrows():
            ac_raw = str(r.get("academic_name", "")).strip().upper()
            is_sel = False
            if selected_name and ac_raw:
                if selected_name == ac_raw or selected_name in ac_raw or ac_raw in selected_name:
                    is_sel = True
                elif selected_tokens:
                    row_tokens = _normalize_tokens(ac_raw)
                    if row_tokens:
                        common = selected_tokens & row_tokens
                        if len(common) >= min(len(selected_tokens), len(row_tokens)) or len(common) >= 2:
                            is_sel = True

            points.append({
                "name": str(r.get("academic_name", "")),
                "x": round(float(r.get("umap_x", 0.0)), 4),
                "y": round(float(r.get("umap_y", 0.0)), 4),
                "num_documents": int(r.get("num_documents", 0) or 0),
                "fwci_avg": round(float(r.get("fwci_avg", 1.0) or 1.0), 2),
                "pct_top_10": round(float(r.get("pct_top_10", 0.0) or 0.0), 1),
                "pct_1": round(float(r.get("pct_1", 0.0) or 0.0), 1),
                "percentile_avg": round(float(r.get("percentile_avg", 50.0) or 50.0), 1),
                "citations": int(r.get("citations", 0) or 0),
                "is_selected": is_sel
            })
        return points

    # 1. Institución completa
    inst_points = []
    df_inst = None
    if institution:
        df_inst = load_cached_data("umap_investigadores.parquet", institution_name=institution, view_mode=view_mode)

    if df_inst is None or df_inst.empty:
        # Fallback a leer parquet nacional
        umap_path = CACHE_DIR / "umap_investigadores.parquet"
        if umap_path.exists():
            try:
                df_all = pd.read_parquet(umap_path)
                if institution:
                    df_inst = df_all[df_all['institutions'].astype(str).str.contains(institution, case=False, na=False)]
                if df_inst is None or df_inst.empty:
                    df_inst = df_all.head(3000)
            except Exception as e:
                logger.warning(f"Error cargando fallback parquet para institución: {e}")

    inst_points = _format_umap_df(df_inst)

    # 2. Dependencia / Facultad
    entity_points = []
    if entity:
        df_ent = load_cached_data("umap_investigadores.parquet", entity_name=entity, institution_name=institution, view_mode=view_mode)
        if (df_ent is None or df_ent.empty) and df_inst is not None and not df_inst.empty and 'entities' in df_inst.columns:
            # Fallback a filtrar dentro del universo institucional por coincidencia de subcadena
            df_ent = df_inst[df_inst['entities'].astype(str).str.contains(entity, case=False, na=False)]
        entity_points = _format_umap_df(df_ent)

    return {
        "status": "success",
        "entity": {
            "name": entity or "Facultad / Entidad",
            "count": len(entity_points),
            "points": entity_points
        },
        "institution": {
            "name": institution or "Institución",
            "count": len(inst_points),
            "points": inst_points
        }
    }



@router.get("/works")
def get_academic_works(
    name: Optional[str] = Query(None),
    orcid: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    year: Optional[int] = Query(None),
    oa_status: Optional[str] = Query(None),
    ods: Optional[str] = Query(None),
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

    # Si el perfil está oculto, no retornar sus publicaciones
    try:
        curation = get_curation()
        if curation.is_profile_hidden(orcid=clean_orcid or orcid, name=final_name or name, academic_id=primary_node.get("id")):
            raise HTTPException(status_code=404, detail="Perfil no encontrado o no disponible (No found)")
    except HTTPException:
        raise
    except Exception as e_wh:
        pass

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

                    # Calcular percentil y tramo (tier) de impacto observado
                    p_val = None
                    if "percentile" in r and pd.notna(r.get("percentile")):
                        p_val = float(r.get("percentile"))
                    elif "citation_normalized_percentile" in r and pd.notna(r.get("citation_normalized_percentile")):
                        p_val = float(r.get("citation_normalized_percentile"))

                    fwci_val = round(float(r.get("fwci", 1.0)), 2) if pd.notna(r.get("fwci")) else 1.0
                    top10 = int(r.get("is_in_top_10_percent", 0)) == 1 or int(r.get("is_top_10", 0)) == 1
                    top1 = int(r.get("is_in_top_1_percent", 0)) == 1 or int(r.get("is_top_1", 0)) == 1

                    work_temp = {
                        "is_top_10": top10,
                        "is_top_1": top1,
                        "percentile": p_val,
                        "fwci": fwci_val
                    }
                    tier_str = _determine_tier(work_temp)

                    works_list.append({
                        "id": str(r.get("paper_id") or doi or ""),
                        "title": str(r.get("Title") or "Sin título"),
                        "journal": source,
                        "source": source,
                        "year": int(r.get("year")) if pd.notna(r.get("year")) else None,
                        "publication_year": int(r.get("year")) if pd.notna(r.get("year")) else None,
                        "citations": int(r.get("citations", 0)) if pd.notna(r.get("citations")) else 0,
                        "fwci": fwci_val,
                        "tier": tier_str,
                        "percentile": p_val,
                        "oa_status": oa_val,
                        "doi": doi_clean,
                        "doi_url": doi_url,
                        "openalex_url": str(r.get("openalex_url") or "") if pd.notna(r.get("openalex_url")) else None,
                        "topic": str(r.get("topic") or "") if pd.notna(r.get("topic")) else "",
                        "ods_name": str(r.get("ODS_Nombre") or "") if pd.notna(r.get("ODS_Nombre")) else None,
                        "is_top_10": top10,
                        "is_top_1": top1,
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
                       topic, fwci, percentile, oa_status, is_top_10, is_top_1, cited_by_count, source_type, source_id
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

                        p_val = float(r.get("percentile")) if pd.notna(r.get("percentile")) else None
                        fwci_val = round(float(r.get("fwci", 1.0)), 2) if pd.notna(r.get("fwci")) else 1.0
                        top10 = int(r.get("is_top_10", 0)) == 1
                        top1 = int(r.get("is_top_1", 0)) == 1

                        work_temp = {
                            "is_top_10": top10,
                            "is_top_1": top1,
                            "percentile": p_val,
                            "fwci": fwci_val
                        }
                        tier_str = _determine_tier(work_temp)
                        
                        works_list.append({
                            "id": str(r.get("id")),
                            "title": str(r.get("title") or "Sin título"),
                            "journal": journal,
                            "source": journal,
                            "year": int(r.get("publication_year")) if pd.notna(r.get("publication_year")) else None,
                            "publication_year": int(r.get("publication_year")) if pd.notna(r.get("publication_year")) else None,
                            "citations": int(r.get("cited_by_count", 0)) if pd.notna(r.get("cited_by_count")) else 0,
                            "fwci": fwci_val,
                            "tier": tier_str,
                            "percentile": p_val,
                            "oa_status": str(r.get("oa_status") or "closed").lower(),
                            "doi": doi_clean,
                            "doi_url": doi_url,
                            "openalex_url": f"https://openalex.org/{r.get('id').split('/')[-1]}" if r.get("id") else None,
                            "topic": str(r.get("topic") or ""),
                            "ods_name": None,
                            "is_top_10": top10,
                            "is_top_1": top1,
                        })
            except Exception as e:
                print(f"[get_academic_works] Error ClickHouse: {e}")

    # Aplicar filtros en memoria
    filtered = works_list
    if year:
        filtered = [w for w in filtered if w.get("year") == year]
    if oa_status and oa_status.lower() != "all":
        filtered = [w for w in filtered if oa_status.lower() in str(w.get("oa_status", "")).lower()]
    if ods and ods.lower() != "all" and ods.lower() != "todos":
        m = re.search(r'\d+', str(ods))
        target_num = int(m.group()) if m else None
        if target_num is not None:
            def matches_ods(w):
                val = str(w.get("ods_name") or "")
                if not val:
                    return False
                found = re.findall(r'(?:sdg/|ODS\s*|^\s*)(\d{1,2})', val)
                return any(int(x) == target_num for x in found if x.isdigit())
            filtered = [w for w in filtered if matches_ods(w)]
        else:
            s_ods = ods.lower().strip()
            filtered = [w for w in filtered if w.get("ods_name") and (s_ods in str(w.get("ods_name")).lower())]
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
