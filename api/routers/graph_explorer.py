"""
api/routers/graph_explorer.py - Explorador Interactivo de Grafos de Conocimiento Neo4j (SECIHTI Ejes 1 y 2)
Proporciona endpoints optimizados para redes de colaboración de CPIs, flujos interestatales, 
alineación con ODS y detección de evaluadores sin conflicto de interés.
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import re
import math

from api.db import get_neo4j_store

router = APIRouter(prefix="/api/graph", tags=["Explorador de Grafos y Redes"])

# Modelos Pydantic para el Explorador General
class SubgraphQuery(BaseModel):
    entity_ids: List[str]
    depth: int = 1
    node_types: Optional[List[str]] = None
    min_weight: int = 1
    snii_levels: Optional[List[str]] = None
    limit: int = 100

# Paleta de colores estándar para nodos del grafo
NODE_COLORS = {
    "cpi": "#f59e0b",           # Ámbar CPI SECIHTI
    "university": "#38bdf8",    # Azul Universidad
    "institution": "#0284c7",   # Azul Institución General
    "person": "#818cf8",        # Índigo Investigador
    "state": "#c084fc",         # Púrpura Entidad Federativa
    "sdg": "#10b981",           # Verde Esmeralda ODS
    "topic": "#14b8a6",         # Teal Tema
    "conflict": "#ef4444",      # Rojo Conflicto de interés
    "no_conflict": "#10b981",   # Verde Sin conflicto
}

def interpolate_gradient_color(val: float, min_val: float, max_val: float, palette: str = "plasma") -> str:
    """
    Interpola un color continuo a lo largo de un gradiente cromático usando escala logarítmica.
    Ideal para redes bibliométricas donde la coautoría sigue distribuciones de ley de potencia.
    """
    min_v = max(1.0, float(min_val))
    max_v = max(min_v + 1.0, float(max_val))
    v = max(min_v, min(float(val), max_v))
    
    # Normalización logarítmica t en [0.0, 1.0]
    t = (math.log(v) - math.log(min_v)) / (math.log(max_v) - math.log(min_v))
    t = max(0.0, min(1.0, t))
    
    if palette == "emerald":
        # Para ODS: Gris azulado -> Cian -> Verde Esmeralda -> Esmeralda Intenso
        stops = [
            (0.0, (148, 163, 184)),   # #94a3b8
            (0.33, (56, 189, 248)),   # #38bdf8
            (0.66, (16, 185, 129)),   # #10b981
            (1.0, (5, 150, 105))      # #059669
        ]
    else:
        # Paleta Principal (Plasma / Spectral): Slate -> Cyan -> Indigo -> Magenta -> Ámbar Dorado
        stops = [
            (0.0, (148, 163, 184)),   # #94a3b8 (base / baja)
            (0.25, (56, 189, 248)),   # #38bdf8 (cyan)
            (0.50, (129, 140, 248)),  # #818cf8 (indigo)
            (0.75, (217, 70, 239)),   # #d946ef (magenta / fucsia)
            (1.0, (245, 158, 11))     # #f59e0b (ámbar dorado incandescente)
        ]
        
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t <= t1:
            ratio = (t - t0) / (t1 - t0)
            r = int(c0[0] + ratio * (c1[0] - c0[0]))
            g = int(c0[1] + ratio * (c1[1] - c0[1]))
            b = int(c0[2] + ratio * (c1[2] - c0[2]))
            return f"#{r:02x}{g:02x}{b:02x}"
            
    last = stops[-1][1]
    return f"#{last[0]:02x}{last[1]:02x}{last[2]:02x}"

# Metadatos de los presets institucionales SECIHTI
PRESETS_METADATA = [
    {
        "id": "cpis_collab",
        "title": "Red de Colaboración de los 26 CPIs SECIHTI y Universidades",
        "axis": "Eje 1: Fortalecimiento del Sistema Nacional de CTI",
        "description": "Visualiza los puentes de coautoría científica entre los Centros Públicos de Investigación (CPIs) de SECIHTI y las principales universidades nacionales y estatales.",
        "default_limit": 80,
        "controls": {
            "has_threshold": True,
            "threshold_label": "Mínimo de publicaciones conjuntas",
            "default_threshold": 5
        }
    },
    {
        "id": "regional_flows",
        "title": "Cooperación Interestatal y Descentralización Científica",
        "axis": "Eje 1: Federalización y Descentralización de la Ciencia",
        "description": "Cartografía de enlaces de cooperación interinstitucional entre las 32 entidades federativas de México, evidenciando articulación regional y polos científicos descentralizados.",
        "default_limit": 60,
        "controls": {
            "has_threshold": True,
            "threshold_label": "Mínimo de colaboraciones interestatales",
            "default_threshold": 50
        }
    },
    {
        "id": "sdg_capacities",
        "title": "Atlas de Capacidades Científicas y Alineación con ODS 1-17",
        "axis": "Eje 2: Ciencia con Incidencia en Retos Nacionales",
        "description": "Bipartición analítica que vincula a cada CPI y sus investigadores con las metas globales de los Objetivos de Desarrollo Sostenible (Agua, Energía, Salud, Biodiversidad).",
        "default_limit": 100,
        "controls": {
            "has_threshold": True,
            "threshold_label": "Mínimo de aportes al ODS",
            "default_threshold": 20
        }
    },
    {
        "id": "snii_topic_landscape",
        "title": "Paisaje Temático del SNII: Áreas Científicas y sus Tópicos de Investigación",
        "axis": "Eje 1: Cartografía del Conocimiento Científico Nacional",
        "description": "Red bipartita que vincula las 9 grandes Áreas del SNII con los 4,098 Tópicos OpenAlex de México. Cada arista representa el número de investigadores que conectan ambos mundos, revelando las constelaciones temáticas del sistema de ciencia nacional.",
        "default_limit": 5000,
        "controls": {
            "has_threshold": True,
            "threshold_label": "Mínimo de investigadores por arista",
            "default_threshold": 10
        }
    }
]

@router.get("/presets")
def get_presets_list() -> List[Dict[str, Any]]:
    """Retorna el catálogo de demos y vistas preconfiguradas para los Ejes 1 y 2 de SECIHTI."""
    return PRESETS_METADATA


@router.get("/preset/{preset_id}")
def get_preset_graph(
    preset_id: str,
    limit: int = Query(80, ge=10, le=35000),
    threshold: int = Query(1, ge=1, le=500),
    state_filter: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Ejecuta la consulta Cypher específica para el preset seleccionado y 
    formatea los nodos y aristas en la estructura canónica de Reagraph.
    """
    store = get_neo4j_store()

    if preset_id == "cpis_collab":
        # Red de coautoría entre CPIs y Universidades
        cypher = """
        MATCH (i1:Institution)<-[:AFFILIATED_TO]-(p1:Person)-[:AUTHOR_OF]->(w:Paper)<-[:AUTHOR_OF]-(p2:Person)-[:AFFILIATED_TO]->(i2:Institution)
        WHERE elementId(i1) < elementId(i2)
          AND (p1.is_cpi_secihti = true OR p2.is_cpi_secihti = true)
          AND i1.name <> 'SIN INSTITUCION' AND i2.name <> 'SIN INSTITUCION'
          AND i1.name <> 'SECRETARIA DE CIENCIAS, HUMANIDADES, TECNOLOGIA E INNOVACION'
          AND i2.name <> 'SECRETARIA DE CIENCIAS, HUMANIDADES, TECNOLOGIA E INNOVACION'
        WITH i1, i2, count(distinct w) as weight,
             count(distinct case when p1.is_cpi_secihti = true then p1 end) as cpi_p1,
             count(distinct case when p2.is_cpi_secihti = true then p2 end) as cpi_p2
        WHERE weight >= $threshold
        RETURN i1.name as inst1, i2.name as inst2, weight,
               (cpi_p1 > 0) as is_cpi1,
               (cpi_p2 > 0) as is_cpi2
        ORDER BY weight DESC
        LIMIT $limit
        """
        nodes_dict = {}
        edges = []

        with store.driver.session() as s:
            result = list(s.run(cypher, parameters={"threshold": threshold, "limit": limit}))
            min_w = min((rec["weight"] for rec in result), default=threshold)
            max_w = max((rec["weight"] for rec in result), default=100)

            for rec in result:
                inst1 = rec["inst1"]
                inst2 = rec["inst2"]
                weight = rec["weight"]
                is_cpi1 = rec["is_cpi1"]
                is_cpi2 = rec["is_cpi2"]

                if inst1 not in nodes_dict:
                    nodes_dict[inst1] = {
                        "id": f"inst_{inst1}",
                        "label": inst1[:28] + ("..." if len(inst1) > 28 else ""),
                        "subLabel": "CPI SECIHTI" if is_cpi1 else "Universidad / Inst.",
                        "fill": NODE_COLORS["cpi"] if is_cpi1 else NODE_COLORS["university"],
                        "size": 18 if is_cpi1 else 13,
                        "data": {
                            "type": "institution",
                            "full_name": inst1,
                            "is_cpi": is_cpi1,
                            "category": "CPI SECIHTI" if is_cpi1 else "Universidad"
                        }
                    }

                if inst2 not in nodes_dict:
                    nodes_dict[inst2] = {
                        "id": f"inst_{inst2}",
                        "label": inst2[:28] + ("..." if len(inst2) > 28 else ""),
                        "subLabel": "CPI SECIHTI" if is_cpi2 else "Universidad / Inst.",
                        "fill": NODE_COLORS["cpi"] if is_cpi2 else NODE_COLORS["university"],
                        "size": 18 if is_cpi2 else 13,
                        "data": {
                            "type": "institution",
                            "full_name": inst2,
                            "is_cpi": is_cpi2,
                            "category": "CPI SECIHTI" if is_cpi2 else "Universidad"
                        }
                    }

                edge_id = f"e_{inst1}_{inst2}"
                fill_color = interpolate_gradient_color(weight, min_w, max_w, "plasma")
                edges.append({
                    "id": edge_id,
                    "source": f"inst_{inst1}",
                    "target": f"inst_{inst2}",
                    "label": f"{weight} papers",
                    "size": 1,
                    "fill": fill_color,
                    "data": {
                        "weight": weight,
                        "description": f"Coautoría conjunta en {weight} artículos científicos indexados"
                    }
                })

        return {
            "preset_id": preset_id,
            "title": "Red de Colaboración CPIs SECIHTI y Universidades",
            "nodes": list(nodes_dict.values()),
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes_dict),
                "total_edges": len(edges),
                "cpis_count": sum(1 for n in nodes_dict.values() if n["data"].get("is_cpi")),
                "edge_range": {"min": min_w, "max": max_w}
            }
        }

    elif preset_id == "regional_flows":
        # Flujos interestatales de cooperación descentralizada
        cypher = """
        MATCH (p1:Person)-[:AUTHOR_OF]->(w:Paper)<-[:AUTHOR_OF]-(p2:Person)
        WHERE elementId(p1) < elementId(p2)
          AND p1.entidad_final IS NOT NULL AND p2.entidad_final IS NOT NULL
          AND p1.entidad_final <> p2.entidad_final
          AND p1.entidad_final <> 'SIN INSTITUCION' AND p2.entidad_final <> 'SIN INSTITUCION'
        WITH CASE WHEN p1.entidad_final < p2.entidad_final THEN p1.entidad_final ELSE p2.entidad_final END AS edo1,
             CASE WHEN p1.entidad_final < p2.entidad_final THEN p2.entidad_final ELSE p1.entidad_final END AS edo2,
             w
        WITH edo1, edo2, count(distinct w) as weight
        WHERE weight >= $threshold
        RETURN edo1, edo2, weight
        ORDER BY weight DESC
        LIMIT $limit
        """
        nodes_dict = {}
        edges = []

        with store.driver.session() as s:
            result = list(s.run(cypher, parameters={"threshold": threshold, "limit": limit}))
            min_w = min((rec["weight"] for rec in result), default=threshold)
            max_w = max((rec["weight"] for rec in result), default=2000)

            for rec in result:
                edo1 = rec["edo1"].title()
                edo2 = rec["edo2"].title()
                weight = rec["weight"]

                for edo in (edo1, edo2):
                    if edo not in nodes_dict:
                        is_hub = edo in ["Ciudad De Mexico", "Puebla", "Jalisco", "Nuevo Leon", "Sonora", "Baja California"]
                        nodes_dict[edo] = {
                            "id": f"state_{edo}",
                            "label": edo,
                            "subLabel": "Polo Científico" if is_hub else "Entidad Federativa",
                            "fill": "#a855f7" if is_hub else NODE_COLORS["state"],
                            "size": 22 if is_hub else 14,
                            "data": {
                                "type": "state",
                                "state_name": edo,
                                "is_hub": is_hub
                            }
                        }

                fill_color = interpolate_gradient_color(weight, min_w, max_w, "plasma")
                edges.append({
                    "id": f"e_{edo1}_{edo2}",
                    "source": f"state_{edo1}",
                    "target": f"state_{edo2}",
                    "label": f"{weight} enlaces",
                    "size": 1,
                    "fill": fill_color,
                    "data": {
                        "weight": weight,
                        "description": f"Flujo de {weight} publicaciones inter-entidades federativas"
                    }
                })

        return {
            "preset_id": preset_id,
            "title": "Cooperación Interestatal y Descentralización Científica",
            "nodes": list(nodes_dict.values()),
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes_dict),
                "total_edges": len(edges),
                "edge_range": {"min": min_w, "max": max_w}
            }
        }

    elif preset_id == "sdg_capacities":
        # Atlas de Capacidades de los CPIs hacia los 17 ODS
        cypher = """
        MATCH (i:Institution)<-[:AFFILIATED_TO]-(p:Person {is_cpi_secihti: true})-[:AUTHOR_OF]->(w:Paper)-[:CONTRIBUTES_TO]->(s:SDG)
        WHERE i.name <> 'SIN INSTITUCION' 
          AND i.name <> 'SECRETARIA DE CIENCIAS, HUMANIDADES, TECNOLOGIA E INNOVACION'
        WITH i.name as cpi, s.name as sdg, count(distinct w) as papers, count(distinct p) as investigadores
        WHERE papers >= $threshold
        RETURN cpi, sdg, papers, investigadores
        ORDER BY papers DESC
        LIMIT $limit
        """
        nodes_dict = {}
        edges = []

        with store.driver.session() as s:
            result = list(s.run(cypher, parameters={"threshold": threshold, "limit": limit}))
            min_p = min((rec["papers"] for rec in result), default=threshold)
            max_p = max((rec["papers"] for rec in result), default=400)

            for rec in result:
                cpi = rec["cpi"]
                sdg = rec["sdg"]
                papers = rec["papers"]
                investigadores = rec["investigadores"]

                # Nodo CPI
                if cpi not in nodes_dict:
                    nodes_dict[cpi] = {
                        "id": f"cpi_{cpi}",
                        "label": cpi[:26] + ("..." if len(cpi) > 26 else ""),
                        "subLabel": "CPI SECIHTI",
                        "fill": NODE_COLORS["cpi"],
                        "size": 18,
                        "data": {
                            "type": "cpi",
                            "full_name": cpi,
                            "category": "Centro Público de Investigación SECIHTI"
                        }
                    }

                # Nodo SDG
                if sdg not in nodes_dict:
                    nodes_dict[sdg] = {
                        "id": f"sdg_{sdg}",
                        "label": sdg,
                        "subLabel": "Objetivo de Desarrollo Sostenible",
                        "fill": NODE_COLORS["sdg"],
                        "size": 22,
                        "data": {
                            "type": "sdg",
                            "sdg_name": sdg,
                            "category": "ODS ONU 2030"
                        }
                    }

                fill_color = interpolate_gradient_color(papers, min_p, max_p, "emerald")
                edges.append({
                    "id": f"e_{cpi}_{sdg}",
                    "source": f"cpi_{cpi}",
                    "target": f"sdg_{sdg}",
                    "label": f"{papers} art.",
                    "size": 1,
                    "fill": fill_color,
                    "data": {
                        "weight": papers,
                        "investigadores": investigadores,
                        "description": f"Capacidad instalada: {papers} artículos y {investigadores} investigadores SNII en este ODS"
                    }
                })

        return {
            "preset_id": preset_id,
            "title": "Atlas de Capacidades Científicas y Alineación con ODS 1-17",
            "nodes": list(nodes_dict.values()),
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes_dict),
                "total_edges": len(edges),
                "sdgs_covered": sum(1 for n in nodes_dict.values() if n["data"].get("type") == "sdg"),
                "edge_range": {"min": min_p, "max": max_p}
            }
        }

    elif preset_id == "snii_topic_landscape":
        # ── Red Bipartita: Áreas SNII ↔ Tópicos OpenAlex ─────────────────────
        import hashlib
        # Paleta de colores por área SNII — Brillante para área, Pastel para tópico
        AREA_COLORS = {
            "I. FISICO-MATEMATICAS Y CIENCIAS DE LA TIERRA":  "#6366f1",  # Índigo
            "II. BIOLOGIA Y QUIMICA":                          "#10b981",  # Esmeralda
            "III. MEDICINA Y CIENCIAS DE LA SALUD":            "#ef4444",  # Rojo
            "IV. CIENCIAS DE LA CONDUCTA Y LA EDUCACION":      "#f59e0b",  # Ámbar
            "V. HUMANIDADES":                                   "#8b5cf6",  # Violeta
            "VI. CIENCIAS SOCIALES":                            "#3b82f6",  # Azul
            "VII. CIENCIAS DE AGRICULTURA, AGROPECUARIAS, FORESTALES Y DE ECOSISTEMAS": "#84cc16",  # Lima
            "VIII. INGENIERIAS Y DESARROLLO TECNOLOGICO":       "#f97316",  # Naranja
            "IX. INTERDISCIPLINARIA":                           "#06b6d4",  # Cian
        }
        # Colores de alta visibilidad y contraste para los nodos de Tópico (claros y oscuros)
        TOPIC_COLORS = {
            "I. FISICO-MATEMATICAS Y CIENCIAS DE LA TIERRA":  "#4f46e5",  # Índigo vibrante
            "II. BIOLOGIA Y QUIMICA":                          "#059669",  # Esmeralda vivo
            "III. MEDICINA Y CIENCIAS DE LA SALUD":            "#dc2626",  # Carmesí vibrante
            "IV. CIENCIAS DE LA CONDUCTA Y LA EDUCACION":      "#d97706",  # Ámbar intenso
            "V. HUMANIDADES":                                   "#7c3aed",  # Violeta eléctrico
            "VI. CIENCIAS SOCIALES":                            "#2563eb",  # Azul eléctrico
            "VII. CIENCIAS DE AGRICULTURA, AGROPECUARIAS, FORESTALES Y DE ECOSISTEMAS": "#65a30d",  # Verde lima vivo
            "VIII. INGENIERIAS Y DESARROLLO TECNOLOGICO":       "#ea580c",  # Naranja encendido
            "IX. INTERDISCIPLINARIA":                           "#0891b2",  # Cian profundo
        }
        AREA_SHORT = {
            "I. FISICO-MATEMATICAS Y CIENCIAS DE LA TIERRA":   "Fís-Mat y Tierra",
            "II. BIOLOGIA Y QUIMICA":                          "Biología y Química",
            "III. MEDICINA Y CIENCIAS DE LA SALUD":            "Medicina y Salud",
            "IV. CIENCIAS DE LA CONDUCTA Y LA EDUCACION":      "Conducta y Educación",
            "V. HUMANIDADES":                                   "Humanidades",
            "VI. CIENCIAS SOCIALES":                            "Ciencias Sociales",
            "VII. CIENCIAS DE AGRICULTURA, AGROPECUARIAS, FORESTALES Y DE ECOSISTEMAS": "Agro y Ecosistemas",
            "VIII. INGENIERIAS Y DESARROLLO TECNOLOGICO":       "Ingenierías y Tec.",
            "IX. INTERDISCIPLINARIA":                           "Interdisciplinaria",
        }

        cypher = """
        MATCH (p:Person)-[:AUTHOR_OF]->(w:Paper)-[:HAS_TOPIC]->(t:Topic)
        WHERE p.snii_area IS NOT NULL
          AND t.name IS NOT NULL
          AND t.name <> 'Unknown Topic'
          AND ($area_filter IS NULL OR p.snii_area = $area_filter)
        WITH p.snii_area AS area, 
             trim(t.name) AS topic_name,
             count(DISTINCT p) AS researchers
        WHERE researchers >= $threshold
        RETURN area, topic_name, researchers
        ORDER BY researchers DESC
        LIMIT $limit
        """

        # Si state_filter coincide con un área SNII o se provee un filtro de área
        selected_area = state_filter if (state_filter and state_filter in AREA_COLORS) else None

        nodes_dict = {}
        edges = []
        max_researchers = 1

        with store.driver.session() as s:
            results = s.run(
                cypher, 
                threshold=threshold, 
                limit=limit, 
                area_filter=selected_area
            ).data()

        if results:
            max_researchers = max(r["researchers"] for r in results)

        # Precalcular conteos totales por área y área primaria dominante por tópico
        area_totals: dict = {}
        topic_totals: dict = {}
        topic_primary_area: dict = {}
        topic_area_breakdown: dict = {}

        for r in results:
            area = r["area"]
            topic_name = r["topic_name"]
            r_cnt = r["researchers"]

            area_totals[area] = area_totals.get(area, 0) + r_cnt
            topic_totals[topic_name] = topic_totals.get(topic_name, 0) + r_cnt

            if topic_name not in topic_area_breakdown:
                topic_area_breakdown[topic_name] = []
            topic_area_breakdown[topic_name].append({"area": area, "researchers": r_cnt})

            if topic_name not in topic_primary_area or r_cnt > topic_primary_area[topic_name][1]:
                topic_primary_area[topic_name] = (area, r_cnt)

        max_area = max(area_totals.values()) if area_totals else 1
        max_topic_total = max(topic_totals.values()) if topic_totals else 1

        for r in results:
            area        = r["area"]
            topic_name  = r["topic_name"]
            researchers = r["researchers"]

            area_color = AREA_COLORS.get(area, "#94a3b8")
            area_label = AREA_SHORT.get(area, area[:20])

            # ── Nodo de Área SNII (central, grande y prominente) ─────────────
            area_node_id = f"area_{area[:6].strip().replace(' ', '_')}"
            if area_node_id not in nodes_dict:
                area_size = 28 + int(34 * area_totals.get(area, 0) / max_area)
                nodes_dict[area_node_id] = {
                    "id": area_node_id,
                    "label": area_label,
                    "subLabel": f"{area_totals.get(area, 0):,} investigadores vinculados",
                    "fill": area_color,
                    "size": area_size,
                    "data": {
                        "type": "snii_area",
                        "full_name": area,
                        "total_researchers": area_totals.get(area, 0),
                        "description": f"Área {area} del SNII — nodo central de la constelación temática nacional"
                    }
                }

            # ── Nodo de Tópico Canónico (satélite temático) ─────────────────
            # Identificador determinista basado en el nombre canónico del tema
            topic_node_id = "topic_" + hashlib.md5(topic_name.encode('utf-8')).hexdigest()[:12]
            if topic_node_id not in nodes_dict:
                primary_area_name, primary_cnt = topic_primary_area.get(topic_name, (area, researchers))
                topic_color = TOPIC_COLORS.get(primary_area_name, "#3b82f6")
                total_t_cnt = topic_totals.get(topic_name, researchers)
                t_size = 8 + int(16 * total_t_cnt / max_topic_total)

                nodes_dict[topic_node_id] = {
                    "id": topic_node_id,
                    "label": topic_name[:34] + ("…" if len(topic_name) > 34 else ""),
                    "subLabel": f"{total_t_cnt:,} inv. SNII",
                    "fill": topic_color,
                    "size": t_size,
                    "data": {
                        "type": "topic",
                        "full_name": topic_name,
                        "total_researchers": total_t_cnt,
                        "primary_area": primary_area_name,
                        "areas_breakdown": topic_area_breakdown.get(topic_name, []),
                        "description": f"Tópico OpenAlex abordado por {total_t_cnt:,} investigadores del SNII (Masa principal en: {AREA_SHORT.get(primary_area_name, primary_area_name)})"
                    }
                }

            # ── Arista Área ↔ Tópico (grosor = masa crítica de investigadores)
            edge_id = f"e_{area_node_id}_{topic_node_id}"
            edge_size = max(1, min(8, int(1 + 7 * researchers / max_researchers)))
            edges.append({
                "id": edge_id,
                "source": area_node_id,
                "target": topic_node_id,
                "size": edge_size,
                "fill": area_color,
                "data": {
                    "researchers": researchers,
                    "area": area,
                    "topic": topic_name,
                    "description": f"{researchers:,} investigadores del SNII en {area_label} publican activamente en '{topic_name}'"
                }
            })

        area_nodes  = sum(1 for n in nodes_dict.values() if n["data"].get("type") == "snii_area")
        topic_nodes = sum(1 for n in nodes_dict.values() if n["data"].get("type") == "topic")

        return {
            "preset_id": preset_id,
            "title": "Paisaje Temático del SNII: Áreas Científicas y sus Tópicos de Investigación",
            "nodes": list(nodes_dict.values()),
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes_dict),
                "total_edges": len(edges),
                "area_nodes": area_nodes,
                "topic_nodes": topic_nodes,
                "threshold_applied": threshold,
                "edge_range": {
                    "min": min((r["researchers"] for r in results), default=threshold) if results else threshold,
                    "max": max_researchers
                }
            }
        }

    else:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' no encontrado.")


@router.get("/search-entities")
def search_entities(
    q: str = Query(..., min_length=2, description="Término de búsqueda de investigadores, instituciones u ODS"),
    limit: int = Query(15, ge=1, le=50)
) -> List[Dict[str, Any]]:
    """
    Buscador de entidades para el modo libre de creación de subgrafos.
    Permite autocompletar investigadores (Person), instituciones (Institution) y temas (Topic/SDG).
    """
    store = get_neo4j_store()
    term = q.strip()
    term_upper = term.upper()
    term_regex = f"(?i).*{re.escape(term)}.*"

    results = []

    with store.driver.session() as s:
        # 1. Buscar en Person
        q_person = """
        MATCH (p:Person)
        WHERE p.fullname =~ $regex OR p.orcid =~ $regex
        RETURN p.id as id, p.fullname as name, p.snii_level as level, p.snii_area as area,
               p.is_cpi_secihti as is_cpi, p.entidad_final as entidad
        LIMIT $limit
        """
        r_p = s.run(q_person, parameters={"regex": term_regex, "limit": limit})
        for rec in r_p:
            results.append({
                "id": f"person_{rec['id']}",
                "raw_id": rec["id"],
                "name": rec["name"],
                "type": "person",
                "label": f"{rec['name']} (SNII {rec['level'] or 'S/N'})",
                "badge": "CPI SECIHTI" if rec["is_cpi"] else "Investigador",
                "area": rec["area"],
                "entidad": rec["entidad"]
            })

        # 2. Buscar en Institution si quedan slots
        remaining = limit - len(results)
        if remaining > 0:
            q_inst = """
            MATCH (i:Institution)
            WHERE i.name =~ $regex
              AND i.name <> 'SIN INSTITUCION'
            RETURN i.name as name
            LIMIT $remaining
            """
            r_i = s.run(q_inst, parameters={"regex": term_regex, "remaining": remaining})
            for rec in r_i:
                name = rec["name"]
                is_cpi = "CENTRO" in name or "COLEGIO" in name or "INSTITUTO" in name or "CIAD" in name or "INAOE" in name
                results.append({
                    "id": f"inst_{name}",
                    "raw_id": name,
                    "name": name,
                    "type": "institution",
                    "label": name,
                    "badge": "CPI SECIHTI" if is_cpi else "Institución",
                    "area": None,
                    "entidad": None
                })

        # 3. Buscar en SDG si coincide
        remaining = limit - len(results)
        if remaining > 0:
            q_sdg = """
            MATCH (s:SDG)
            WHERE s.name =~ $regex
            RETURN s.name as name
            LIMIT $remaining
            """
            r_s = s.run(q_sdg, parameters={"regex": term_regex, "remaining": remaining})
            for rec in r_s:
                results.append({
                    "id": f"sdg_{rec['name']}",
                    "raw_id": rec["name"],
                    "name": rec["name"],
                    "type": "sdg",
                    "label": f"ODS: {rec['name']}",
                    "badge": "ODS ONU 2030",
                    "area": "Desarrollo Sostenible",
                    "entidad": None
                })

    return results


@router.post("/subgraph")
def generate_subgraph(query: SubgraphQuery = Body(...)) -> Dict[str, Any]:
    """
    Genera un subgrafo dinámico a partir de entidades seleccionadas por el usuario,
    con control estricto de profundidad y límite de nodos para garantizar fluidez WebGL.
    """
    if not query.entity_ids:
        raise HTTPException(status_code=400, detail="Debe proporcionar al menos un entity_id.")

    store = get_neo4j_store()
    limit = min(query.limit, 250) # Cota dura de seguridad

    nodes_dict = {}
    edges = []

    # Extraer personas e instituciones solicitadas
    person_ids = []
    inst_names = []
    sdg_names = []

    for eid in query.entity_ids:
        if eid.startswith("person_"):
            person_ids.append(eid.replace("person_", "", 1))
        elif eid.startswith("inst_"):
            inst_names.append(eid.replace("inst_", "", 1))
        elif eid.startswith("sdg_"):
            sdg_names.append(eid.replace("sdg_", "", 1))
        else:
            # Fallback
            person_ids.append(eid)

    with store.driver.session() as s:
        # Caso A: Si hay personas, expandir sus coautores y afiliaciones
        if person_ids:
            cypher_person = """
            MATCH (p1:Person)
            WHERE p1.id IN $person_ids
            OPTIONAL MATCH (p1)-[:AFFILIATED_TO]->(inst:Institution)
            WHERE inst.name <> 'SIN INSTITUCION'
            OPTIONAL MATCH (p1)-[:AUTHOR_OF]->(w:Paper)<-[:AUTHOR_OF]-(p2:Person)
            WHERE p2.id <> p1.id AND p2.fullname IS NOT NULL
            WITH p1, inst, p2, count(distinct w) as coauth_weight
            WHERE p2 IS NULL OR coauth_weight >= $min_weight
            RETURN p1.id as p1_id, p1.fullname as p1_name, p1.snii_level as p1_lvl,
                   p1.snii_area as p1_area, p1.is_cpi_secihti as p1_cpi,
                   inst.name as inst_name,
                   p2.id as p2_id, p2.fullname as p2_name, p2.snii_level as p2_lvl,
                   p2.snii_area as p2_area, p2.is_cpi_secihti as p2_cpi,
                   coauth_weight
            ORDER BY coauth_weight DESC
            LIMIT $limit
            """
            res = s.run(cypher_person, parameters={
                "person_ids": person_ids,
                "min_weight": query.min_weight,
                "limit": limit
            })

            for rec in res:
                # Nodo focal P1
                p1_nid = f"person_{rec['p1_id']}"
                if p1_nid not in nodes_dict:
                    nodes_dict[p1_nid] = {
                        "id": p1_nid,
                        "label": rec["p1_name"][:25] + ("..." if len(rec["p1_name"]) > 25 else ""),
                        "subLabel": f"Focal (SNII {rec['p1_lvl'] or 'S/N'})",
                        "fill": "#3b82f6",
                        "size": 22,
                        "data": {
                            "type": "person",
                            "full_name": rec["p1_name"],
                            "snii_level": rec["p1_lvl"],
                            "snii_area": rec["p1_area"],
                            "is_cpi": rec["p1_cpi"]
                        }
                    }

                # Institución de P1
                if rec["inst_name"]:
                    inst_nid = f"inst_{rec['inst_name']}"
                    if inst_nid not in nodes_dict:
                        nodes_dict[inst_nid] = {
                            "id": inst_nid,
                            "label": rec["inst_name"][:26] + ("..." if len(rec["inst_name"]) > 26 else ""),
                            "subLabel": "Institución",
                            "fill": NODE_COLORS["cpi"] if rec["p1_cpi"] else NODE_COLORS["university"],
                            "size": 16,
                            "data": {
                                "type": "institution",
                                "full_name": rec["inst_name"]
                            }
                        }
                    edges.append({
                        "id": f"e_{p1_nid}_{inst_nid}",
                        "source": p1_nid,
                        "target": inst_nid,
                        "label": "Adscripción",
                        "size": 1,
                        "data": {"relation": "AFFILIATED_TO"}
                    })

                # Coautor P2
                if rec["p2_id"]:
                    p2_nid = f"person_{rec['p2_id']}"
                    if p2_nid not in nodes_dict:
                        nodes_dict[p2_nid] = {
                            "id": p2_nid,
                            "label": rec["p2_name"][:22] + ("..." if len(rec["p2_name"]) > 22 else ""),
                            "subLabel": f"Coautor (SNII {rec['p2_lvl'] or 'S/N'})",
                            "fill": NODE_COLORS["cpi"] if rec["p2_cpi"] else NODE_COLORS["person"],
                            "size": 14,
                            "data": {
                                "type": "person",
                                "full_name": rec["p2_name"],
                                "snii_level": rec["p2_lvl"],
                                "snii_area": rec["p2_area"],
                                "is_cpi": rec["p2_cpi"]
                            }
                        }
                    edges.append({
                        "id": f"e_{p1_nid}_{p2_nid}",
                        "source": p1_nid,
                        "target": p2_nid,
                        "label": f"{rec['coauth_weight']} arts.",
                        "size": 1,
                        "fill": interpolate_gradient_color(rec["coauth_weight"], 1, 100, "plasma"),
                        "data": {"relation": "COAUTHOR", "weight": rec["coauth_weight"]}
                    })

        # Caso B: Si hay instituciones seleccionadas
        if inst_names:
            cypher_inst = """
            MATCH (i1:Institution)<-[:AFFILIATED_TO]-(p1:Person)-[:AUTHOR_OF]->(w:Paper)<-[:AUTHOR_OF]-(p2:Person)-[:AFFILIATED_TO]->(i2:Institution)
            WHERE i1.name IN $inst_names AND i1.name <> i2.name AND i2.name <> 'SIN INSTITUCION'
            WITH i1, i2, count(distinct w) as weight
            WHERE weight >= $min_weight
            RETURN i1.name as inst1, i2.name as inst2, weight
            ORDER BY weight DESC
            LIMIT $limit
            """
            res_i = s.run(cypher_inst, parameters={
                "inst_names": inst_names,
                "min_weight": query.min_weight,
                "limit": limit
            })
            for rec in res_i:
                inst1 = rec["inst1"]
                inst2 = rec["inst2"]
                w = rec["weight"]

                for inst in (inst1, inst2):
                    inid = f"inst_{inst}"
                    if inid not in nodes_dict:
                        is_cpi = "CENTRO" in inst or "CIAD" in inst or "INAOE" in inst or "CICESE" in inst
                        nodes_dict[inid] = {
                            "id": inid,
                            "label": inst[:26] + ("..." if len(inst) > 26 else ""),
                            "subLabel": "CPI SECIHTI" if is_cpi else "Institución",
                            "fill": NODE_COLORS["cpi"] if is_cpi else NODE_COLORS["university"],
                            "size": 18 if is_cpi else 14,
                            "data": {
                                "type": "institution",
                                "full_name": inst,
                                "is_cpi": is_cpi
                            }
                        }
                edges.append({
                    "id": f"e_{inst1}_{inst2}",
                    "source": f"inst_{inst1}",
                    "target": f"inst_{inst2}",
                    "label": f"{w} papers",
                    "size": 1,
                    "fill": interpolate_gradient_color(w, 1, 100, "plasma"),
                    "data": {"relation": "INTER_INSTITUTIONAL", "weight": w}
                })

    return {
        "nodes": list(nodes_dict.values()),
        "edges": edges,
        "stats": {
            "total_nodes": len(nodes_dict),
            "total_edges": len(edges)
        }
    }


@router.get("/node-details/{node_id}")
def get_node_details(node_id: str) -> Dict[str, Any]:
    """Retorna la ficha técnica y métricas cienciométricas completas para el nodo seleccionado en el canvas."""
    store = get_neo4j_store()

    if node_id.startswith("person_"):
        pid = node_id.replace("person_", "", 1)
        cypher = """
        MATCH (p:Person {id: $pid})
        OPTIONAL MATCH (p)-[:AFFILIATED_TO]->(i:Institution)
        OPTIONAL MATCH (p)-[:AUTHOR_OF]->(w:Paper)
        OPTIONAL MATCH (p)-[:AUTHOR_OF]->(:Paper)-[:CONTRIBUTES_TO]->(s:SDG)
        RETURN p.fullname as name, p.snii_level as level, p.snii_area as area,
               p.entidad_final as entidad, p.is_cpi_secihti as is_cpi, p.orcid as orcid,
               i.name as institution,
               count(distinct w) as papers_count,
               collect(distinct s.name)[0..5] as top_sdgs
        """
        with store.driver.session() as s:
            r = s.run(cypher, parameters={"pid": pid}).single()
            if not r:
                raise HTTPException(status_code=404, detail="Persona no encontrada.")
            data = r.data()
            return {
                "type": "person",
                "id": node_id,
                "title": data["name"],
                "subtitle": f"SNII {data['level'] or 'S/N'} · {data['area'] or 'Área no asignada'}",
                "properties": {
                    "Institución": data["institution"] or "No registrada",
                    "Entidad Federativa": data["entidad"] or "Nacional",
                    "Es CPI SECIHTI": "Sí" if data["is_cpi"] else "No",
                    "ORCID": data["orcid"] or "No registrado",
                    "Total de Publicaciones en Grafo": data["papers_count"],
                    "ODS Principales": ", ".join(data["top_sdgs"]) if data["top_sdgs"] else "Sin alineación directa"
                }
            }

    elif node_id.startswith("inst_"):
        iname = node_id.replace("inst_", "", 1)
        cypher = """
        MATCH (i:Institution {name: $name})
        OPTIONAL MATCH (p:Person)-[:AFFILIATED_TO]->(i)
        OPTIONAL MATCH (p)-[:AUTHOR_OF]->(w:Paper)
        RETURN i.name as name,
               count(distinct p) as researchers_count,
               count(distinct w) as papers_count
        """
        with store.driver.session() as s:
            r = s.run(cypher, parameters={"name": iname}).single()
            if not r:
                return {
                    "type": "institution",
                    "id": node_id,
                    "title": iname,
                    "subtitle": "Institución Científica",
                    "properties": {"Nombre": iname}
                }
            data = r.data()
            return {
                "type": "institution",
                "id": node_id,
                "title": data["name"],
                "subtitle": "Institución de Educación Superior o CPI",
                "properties": {
                    "Investigadores SNII Registrados": data["researchers_count"],
                    "Publicaciones Totales en Grafo": data["papers_count"]
                }
            }

    elif node_id.startswith("sdg_"):
        sdg_name = node_id.replace("sdg_", "", 1)
        cypher = """
        MATCH (s:SDG {name: $name})<-[:CONTRIBUTES_TO]-(w:Paper)<-[:AUTHOR_OF]-(p:Person)
        RETURN s.name as name, count(distinct w) as papers, count(distinct p) as researchers
        """
        with store.driver.session() as s:
            r = s.run(cypher, parameters={"name": sdg_name}).single()
            papers = r["papers"] if r else 0
            researchers = r["researchers"] if r else 0
            return {
                "type": "sdg",
                "id": node_id,
                "title": f"ODS: {sdg_name}",
                "subtitle": "Objetivo de Desarrollo Sostenible (Agenda ONU 2030)",
                "properties": {
                    "Publicaciones Vinculadas": papers,
                    "Investigadoras e Investigadores": researchers
                }
            }

    elif node_id.startswith("state_"):
        st_name = node_id.replace("state_", "", 1)
        return {
            "type": "state",
            "id": node_id,
            "title": f"Entidad Federativa: {st_name}",
            "subtitle": "Descentralización y Cooperación Interestatal",
            "properties": {
                "Estado": st_name,
                "Rol en Red": "Nodo Regional de Cooperación Científica"
            }
        }

    elif node_id.startswith("area_"):
        cypher = """
        MATCH (p:Person)
        WHERE p.snii_area IS NOT NULL
        WITH p.snii_area as area, count(DISTINCT p) as total_researchers
        WHERE f"area_{area[:6].strip().replace(' ', '_')}" = $node_id OR area CONTAINS $node_id
        RETURN area, total_researchers
        LIMIT 1
        """
        with store.driver.session() as s:
            r = s.run(cypher, parameters={"node_id": node_id}).single()
            if r:
                return {
                    "type": "snii_area",
                    "id": node_id,
                    "title": r["area"],
                    "subtitle": "Gran Área del Conocimiento del SNII",
                    "properties": {
                        "Clasificación": "Eje Central SNII",
                        "Investigadores SNII Padrón 2026": f"{r['total_researchers']:,}"
                    }
                }

    return {
        "type": "generic",
        "id": node_id,
        "title": node_id,
        "subtitle": "Entidad del Grafo",
        "properties": {}
    }
