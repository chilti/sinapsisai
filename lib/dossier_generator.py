"""
lib/dossier_generator.py - Generador de Dossier Ejecutivo de Trayectoria Académica
Genera informes probatorios estructurados de trayectoria e impacto científico para comisiones dictaminadoras
y evaluación académica integral.
Soporta formatos:
- Markdown estructurado descargable (.md)
- PDF formal de calidad ejecutiva con WeasyPrint
"""

import os
import re
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

import weasyprint

from lib.citations_explorer import get_author_works
from lib.curation_service import get_curation_service
from database.knowledge_graph import Neo4jGraphStore


SDG_NAMES = {
    1: "Fin de la Pobreza",
    2: "Hambre Cero",
    3: "Salud y Bienestar",
    4: "Educación de Calidad",
    5: "Igualdad de Género",
    6: "Agua Limpia y Saneamiento",
    7: "Energía Asequible y No Contaminante",
    8: "Trabajo Decente y Crecimiento Económico",
    9: "Industria, Innovación e Infraestructura",
    10: "Reducción de las Desigualdades",
    11: "Ciudades y Comunidades Sostenibles",
    12: "Producción y Consumo Responsables",
    13: "Acción por el Clima",
    14: "Vida Submarina",
    15: "Vida de Ecosistemas Terrestres",
    16: "Paz, Justicia e Instituciones Sólidas",
    17: "Alianzas para Lograr los Objetivos"
}


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _normalize_tokens(name: str) -> List[str]:
    """Extrae tokens significativos de un nombre (minúsculas, sin acentos ni signos)."""
    import unicodedata
    if not name:
        return []
    n = unicodedata.normalize('NFKD', str(name)).encode('ASCII', 'ignore').decode('utf-8')
    tokens = [t.lower() for t in re.findall(r'\b[a-zA-Z]{3,}\b', n)]
    return tokens


def _determine_authorship_role(work_dict: Dict[str, Any], academic_name: str) -> Dict[str, Any]:
    """
    Determina si el investigador fungió como primer autor, autor de correspondencia o coautor.
    """
    role = "Coautor"
    is_first = False
    is_corr = False

    target_tokens = set(_normalize_tokens(academic_name))

    raw_str = work_dict.get("raw_data") or ""
    if raw_str:
        try:
            raw_j = json.loads(raw_str) if isinstance(raw_str, str) else raw_str
            authorships = raw_j.get("authorships", [])
            for au in authorships:
                author_name = au.get("author", {}).get("display_name") or au.get("raw_author_name") or ""
                au_tokens = set(_normalize_tokens(author_name))
                # Coincidencia si comparten al menos 2 tokens (apellido + nombre)
                if len(target_tokens.intersection(au_tokens)) >= 2 or (len(target_tokens) == 1 and target_tokens.issubset(au_tokens)):
                    pos = au.get("author_position", "").lower()
                    corr = au.get("is_corresponding", False)
                    if pos == "first":
                        is_first = True
                    if corr is True:
                        is_corr = True
                    break
        except Exception:
            pass

    # Fallback si no hay raw_data pero sí lista de nombres
    if not is_first and not is_corr:
        author_list = work_dict.get("authors") or work_dict.get("author_names") or []
        if isinstance(author_list, list) and len(author_list) > 0:
            first_au = str(author_list[0])
            first_tokens = set(_normalize_tokens(first_au))
            if len(target_tokens.intersection(first_tokens)) >= 2:
                is_first = True

    if is_first and is_corr:
        role = "Primer Autor y Correspondencia"
    elif is_first:
        role = "Primer Autor"
    elif is_corr:
        role = "Autor de Correspondencia"

    return {
        "role": role,
        "is_first": is_first,
        "is_corresponding": is_corr,
        "is_lead": (is_first or is_corr)
    }


def _determine_tier(work_dict: Dict[str, Any]) -> str:
    """
    Determina el Tramo de Impacto Observado (Tier T1-T4) según percentiles normalizados,
    distinciones globales (Top 1%, Top 10%) o FWCI (estándares DORA / Leiden).
    """
    top10 = work_dict.get("is_top_10") or 0
    top1 = work_dict.get("is_top_1") or 0
    percentile = work_dict.get("percentile")

    if top1 or (percentile is not None and percentile >= 99):
        return "T1 (Top 1%)"
    if top10 or (percentile is not None and percentile >= 75):
        return "T1"
    if percentile is not None:
        if percentile >= 50:
            return "T2"
        elif percentile >= 25:
            return "T3"
        elif percentile >= 0:
            return "T4"

    # Heurística basada en FWCI
    fwci = work_dict.get("fwci")
    if fwci is not None:
        try:
            f = float(fwci)
            if f >= 1.5:
                return "T1 (Est.)"
            elif f >= 1.0:
                return "T2 (Est.)"
            elif f >= 0.6:
                return "T3 (Est.)"
            else:
                return "T4 (Est.)"
        except (ValueError, TypeError):
            pass

    return "T4 (Base)"


_determine_quartile = _determine_tier


def fetch_academic_works(academic_name: Optional[str] = None, orcid: Optional[str] = None) -> List[Dict[str, Any]]:
    """Recupera publicaciones de ClickHouse soportando tanto OpenAlex IDs como DOIs."""
    works = get_author_works(academic_name=academic_name, orcid=orcid)
    if works:
        return works

    from database.clickhouse_db import ch_client
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
        return []

    try:
        res = client.query(f"SELECT DISTINCT paper_id FROM paper_author_map WHERE {' OR '.join(conditions)} LIMIT 1000", params)
        raw_ids = [r[0] for r in res.result_rows if r[0]]
        if not raw_ids:
            return []

        dois = set()
        oa_ids = set()
        for p in raw_ids:
            p_str = str(p).strip()
            if "openalex.org" in p_str or (p_str.startswith("W") and p_str[1:].isdigit()):
                oa_ids.add(p_str if p_str.startswith("http") else f"https://openalex.org/{p_str}")
            else:
                clean_doi = p_str.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
                if clean_doi:
                    dois.add(f"https://doi.org/{clean_doi}")

        where_parts = []
        w_params = {}
        if oa_ids:
            where_parts.append("id IN %(oa_ids)s")
            w_params["oa_ids"] = list(oa_ids)
        if dois:
            where_parts.append("doi IN %(dois)s")
            w_params["dois"] = list(dois)

        if not where_parts:
            return []

        query = f"""
            SELECT 
                id, doi, title, publication_year, cited_by_count, 
                fwci, is_top_10, is_top_1, oa_status, topic, 
                author_names, all_country_codes, raw_data, percentile
            FROM works
            WHERE {" OR ".join(where_parts)}
            ORDER BY publication_year DESC, cited_by_count DESC
        """
        rows = client.query(query, w_params).result_rows
        fallback_works = []
        for r in rows:
            wid, doi, title, yr, cites, fwci, top10, top1, oa, topc, auts, countries, raw_str, perc = r
            journal = ""
            if raw_str:
                try:
                    raw_j = json.loads(raw_str)
                    journal = raw_j.get("primary_location", {}).get("source", {}).get("display_name") or ""
                except Exception:
                    pass
            fallback_works.append({
                "work_id": wid,
                "paper_id": wid,
                "doi": doi or "",
                "title": title or "Sin Título",
                "publication_year": yr,
                "year": yr,
                "journal": journal,
                "authors": auts or [],
                "author_names": auts or [],
                "cited_by_count": cites or 0,
                "citations": cites or 0,
                "fwci": fwci if fwci is not None else 1.0,
                "is_top_10": top10 or 0,
                "is_top_1": top1 or 0,
                "percentile": perc,
                "oa_status": oa or "Desconocido",
                "topic": topc or "",
                "raw_data": raw_str
            })
        return fallback_works
    except Exception as e:
        print(f"[dossier_generator] Error en fetch_academic_works fallback: {e}")
        return []


def generate_dossier_data(
    academic_name: str,
    orcid: Optional[str] = None,
    institution: Optional[str] = None,
    dependency: Optional[str] = None,
    snii_level: Optional[str] = None
) -> Dict[str, Any]:
    """
    Recopila y calcula todas las métricas requeridas para el Dossier de Trayectoria Académica.
    """
    curation = get_curation_service()
    clean_orc = _clean_str(orcid).replace("https://orcid.org/", "").replace("http://orcid.org/", "").strip()

    # 1. Recuperar perfil en Neo4j si faltan metadatos institucionales
    if not institution or not dependency:
        try:
            neo = Neo4jGraphStore()
            prof = neo.get_user_profile(clean_orc) if clean_orc else None
            if prof:
                institution = institution or prof.get("institution")
                dependency = dependency or prof.get("dependency")
                snii_level = snii_level or prof.get("snii_level")
            neo.close()
        except Exception:
            pass

    # 2. Obras canónicas desde ClickHouse (OpenAlex + DOIs)
    works = fetch_academic_works(academic_name=academic_name, orcid=clean_orc)

    # 3. Filtrar disclaimed works
    disclaimed_ids = set()
    if clean_orc:
        try:
            disclaimed_ids = {d.get("work_id") for d in curation.list_disclaimed_works(clean_orc) if d.get("work_id")}
        except Exception:
            pass

    valid_works = [w for w in works if w.get("work_id") not in disclaimed_ids and w.get("paper_id") not in disclaimed_ids]

    # 4. Integrar obras personalizadas cargadas por el usuario (.bib manual)
    if clean_orc:
        custom_works = curation.list_custom_works(clean_orc)
        for cw in custom_works:
            valid_works.append({
                "work_id": f"custom_{cw.get('id')}",
                "doi": cw.get("doi") or "",
                "title": cw.get("title") or "Sin Título",
                "publication_year": cw.get("year") or 0,
                "year": cw.get("year") or 0,
                "journal": cw.get("journal") or "Carga Manual (.bib)",
                "authors": [cw.get("authors")] if cw.get("authors") else [academic_name],
                "cited_by_count": 0,
                "citations": 0,
                "fwci": 1.0,
                "is_top_10": 0,
                "is_top_1": 0,
                "oa_status": "Sin especificar",
                "topic": "",
                "is_custom": True
            })

    # Ordenar cronológicamente (año desc, citas desc)
    valid_works.sort(key=lambda x: (int(x.get("year") or x.get("publication_year") or 0), int(x.get("citations") or x.get("cited_by_count") or 0)), reverse=True)

    # 5. Cálculo de Métricas Nucleares
    citations_list = [int(w.get("citations") or w.get("cited_by_count") or 0) for w in valid_works]
    citations_sorted = sorted(citations_list, reverse=True)
    total_citations = sum(citations_list)
    total_works = len(valid_works)

    # H-Index
    h_index = sum(1 for i, c in enumerate(citations_sorted) if c >= i + 1)

    # G-Index
    cum_cites = 0
    g_index = 0
    for i, c in enumerate(citations_sorted, 1):
        cum_cites += c
        if cum_cites >= i * i:
            g_index = i

    # Rango de años de trayectoria
    years = [int(w.get("year") or w.get("publication_year") or 0) for w in valid_works if (w.get("year") or w.get("publication_year"))]
    min_year = min(years) if years else None
    max_year = max(years) if years else None
    career_years = (max_year - min_year + 1) if (min_year and max_year) else 1

    # M-Quotient (H-index / años de carrera activa)
    m_quotient = round(h_index / career_years, 2) if career_years > 0 else 0.0

    # Promedios de impacto
    avg_citations = round(total_citations / total_works, 1) if total_works > 0 else 0.0
    fwci_values = [float(w.get("fwci")) for w in valid_works if w.get("fwci") is not None]
    avg_fwci = round(sum(fwci_values) / len(fwci_values), 2) if fwci_values else 1.0

    top_10_count = sum(1 for w in valid_works if w.get("is_top_10") == 1)
    top_1_count = sum(1 for w in valid_works if w.get("is_top_1") == 1)
    pct_top_10 = round((top_10_count / total_works) * 100, 1) if total_works > 0 else 0.0

    # 6. Desglose por Rol de Autoría
    role_counts = {
        "Primer Autor y Correspondencia": 0,
        "Primer Autor": 0,
        "Autor de Correspondencia": 0,
        "Coautor": 0
    }
    lead_count = 0

    catalog = []
    tiers_count = {"T1": 0, "T2": 0, "T3": 0, "T4": 0, "Sin Clasificar": 0}
    oa_counts = {"diamond": 0, "gold": 0, "green": 0, "hybrid": 0, "bronze": 0, "closed": 0, "otro": 0}
    sdg_counts = {k: 0 for k in range(1, 18)}

    for w in valid_works:
        # Rol de autoría
        auth_info = _determine_authorship_role(w, academic_name)
        role = auth_info["role"]
        if role in role_counts:
            role_counts[role] += 1
        else:
            role_counts["Coautor"] += 1
        if auth_info["is_lead"]:
            lead_count += 1

        # Tramo de Impacto Observado (Tier T1-T4)
        tier = _determine_tier(w)
        base_t = tier.split()[0]
        if base_t in tiers_count:
            tiers_count[base_t] += 1
        else:
            tiers_count["Sin Clasificar"] += 1

        # Acceso Abierto
        oa_st = str(w.get("oa_status") or "").lower().strip()
        if oa_st in oa_counts:
            oa_counts[oa_st] += 1
        elif oa_st in ["true", "open"]:
            oa_counts["gold"] += 1
        elif oa_st in ["false", "closed"]:
            oa_counts["closed"] += 1
        else:
            oa_counts["otro"] += 1

        # ODS
        w_sdgs = w.get("sdg_ids") or []
        for s in w_sdgs:
            try:
                num = int(str(s).split('/')[-1].replace("sdg", "").replace("SDG", "").strip())
                if 1 <= num <= 17:
                    sdg_counts[num] += 1
            except Exception:
                pass

        catalog.append({
            "title": w.get("title") or "Sin Título",
            "journal": w.get("journal") or "Revista no especificada",
            "year": w.get("year") or w.get("publication_year") or 0,
            "doi": w.get("doi") or "",
            "citations": int(w.get("citations") or w.get("cited_by_count") or 0),
            "fwci": round(float(w.get("fwci") or 1.0), 2),
            "tier": tier,
            "quartile": tier,
            "authorship_role": role,
            "oa_status": oa_st,
            "topic": w.get("topic") or ""
        })

    leadership_rate = round((lead_count / total_works) * 100, 1) if total_works > 0 else 0.0

    # Acceso Abierto y Ahorro Estimado en APC
    oa_open_total = oa_counts["diamond"] + oa_counts["gold"] + oa_counts["green"] + oa_counts["hybrid"] + oa_counts["bronze"]
    pct_oa = round((oa_open_total / total_works) * 100, 1) if total_works > 0 else 0.0
    
    # Ahorro estimado de publicar en Acceso Abierto Diamante y Verde (autoarchivo)
    # Valor de referencia internacional: $2,500 USD promedio por APC comercial evitado
    estimated_apc_savings_usd = (oa_counts["diamond"] + oa_counts["green"]) * 2500

    # Evolución anual
    annual_data = {}
    for w in valid_works:
        y = int(w.get("year") or w.get("publication_year") or 0)
        if y > 1900:
            if y not in annual_data:
                annual_data[y] = {"works": 0, "citations": 0}
            annual_data[y]["works"] += 1
            annual_data[y]["citations"] += int(w.get("citations") or w.get("cited_by_count") or 0)
    
    annual_timeline = sorted([{"year": k, "works": v["works"], "citations": v["citations"]} for k, v in annual_data.items()], key=lambda x: x["year"])

    return {
        "academic_name": academic_name,
        "orcid": clean_orc,
        "institution": institution or "Investigador Independiente / Sin Afiliación",
        "dependency": dependency or "",
        "snii_level": snii_level or "No registrado en padrón",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "metrics": {
            "total_works": total_works,
            "total_citations": total_citations,
            "h_index": h_index,
            "g_index": g_index,
            "m_quotient": m_quotient,
            "avg_citations": avg_citations,
            "avg_fwci": avg_fwci,
            "top_10_count": top_10_count,
            "pct_top_10": pct_top_10,
            "top_1_count": top_1_count,
            "min_year": min_year,
            "max_year": max_year,
            "career_years": career_years,
            "leadership_rate": leadership_rate,
            "lead_count": lead_count,
            "pct_oa": pct_oa,
            "estimated_apc_savings_usd": estimated_apc_savings_usd
        },
        "authorship_breakdown": role_counts,
        "tiers_breakdown": tiers_count,
        "quartiles_breakdown": tiers_count,
        "oa_breakdown": oa_counts,
        "sdg_breakdown": {f"SDG {k}: {SDG_NAMES[k]}": v for k, v in sdg_counts.items() if v > 0},
        "annual_timeline": annual_timeline,
        "catalog": catalog
    }


def generate_dossier_markdown(data: Dict[str, Any]) -> str:
    """Genera el contenido estructurado del dossier en formato Markdown."""
    m = data["metrics"]
    md = []
    md.append(f"# Trayectoria Académica")
    md.append(f"**Investigador(a):** {data['academic_name']}  ")
    if data.get('orcid'):
        md.append(f"**ORCID iD:** [{data['orcid']}](https://orcid.org/{data['orcid']})  ")
    md.append(f"**Institución:** {data['institution']}  ")
    if data.get('dependency'):
        md.append(f"**Dependencia:** {data['dependency']}  ")
    md.append(f"**Nivel:** {data['snii_level']}  ")
    md.append(f"**Fecha de Emisión:** {data['generated_at']}  ")
    md.append(f"**Plataforma de Auditoría:** Info TlachIA (UNAM)\n")

    md.append("---")
    md.append("## 1. Resumen Ejecutivo de Impacto Científico\n")
    md.append("| Indicador | Valor | Descripción / Estándar Internacional |")
    md.append("|---|---|---|")
    md.append(f"| **Total de Publicaciones** | **{m['total_works']}** | Artículos indizados y obras curadas |")
    md.append(f"| **Total de Citas Recibidas** | **{m['total_citations']}** | Citas globales verificadas (OpenAlex / Crossref / Fuentes Internacionales) |")
    md.append(f"| **Índice H (H-Index)** | **{m['h_index']}** | Al menos {m['h_index']} artículos con {m['h_index']} o más citas |")
    md.append(f"| **Índice G (G-Index)** | **{m['g_index']}** | Ponderación de citas en obras de mayor impacto |")
    md.append(f"| **Impacto Normalizado (FWCI)** | **{m['avg_fwci']}** | Promedio mundial = 1.0 (Valores > 1 superan el estándar global) |")
    md.append(f"| **Citas Promedio por Obra** | **{m['avg_citations']}** | Intensidad de citación promedio |")
    md.append(f"| **Artículos Top 10% Mundial** | **{m['top_10_count']} ({m['pct_top_10']}%)** | Obras en el decil superior de excelencia de su área |")
    md.append(f"| **Tasa de Liderazgo Científico** | **{m['leadership_rate']}%** | Porcentaje como Primer Autor o Autor de Correspondencia |")
    md.append(f"| **Acceso Abierto (OA)** | **{m['pct_oa']}%** | Proporción de producción en vías de libre acceso |")
    md.append(f"| **Ahorro Estimado en APC (USD)** | **${m['estimated_apc_savings_usd']:,} USD** | Ahorro público generado vía Acceso Abierto Diamante y Verde |\n")

    md.append("## 2. Clasificación por Tramos de Impacto Observado (Tiers T1–T4)")
    md.append("Distribución de publicaciones según su percentil de citación normalizado por campo y año (calidad e impacto real observado a nivel de artículo, en concordancia con los principios DORA y el Manifiesto de Leiden):\n")
    md.append("| Tramo (Tier) | Número de Obras | Proporción | Nivel de Excelencia Citacional Relativo |")
    md.append("|---|---|---|---|")
    tier_labels = {
        "T1": "Tier 1 (T1) - Alto Impacto Observado (Percentil superior 75%–100%)",
        "T2": "Tier 2 (T2) - Impacto Medio-Alto (Percentil 50%–74%)",
        "T3": "Tier 3 (T3) - Impacto Medio-Bajo (Percentil 25%–49%)",
        "T4": "Tier 4 (T4) - Impacto Base / Inicial (Percentil 0%–24%)",
        "Sin Clasificar": "Sin Clasificar"
    }
    for t_key in ["T1", "T2", "T3", "T4"]:
        cnt = data.get("tiers_breakdown", {}).get(t_key, 0)
        pct = round((cnt / m['total_works']) * 100, 1) if m['total_works'] > 0 else 0.0
        desc = tier_labels.get(t_key, "")
        md.append(f"| **{t_key}** | {cnt} | {pct}% | {desc} |")
    md.append("")

    md.append("## 3. Desglose de Liderazgo y Roles de Autoría\n")
    md.append("| Rol de Autoría | Número de Obras | Porcentaje |")
    md.append("|---|---|---|")
    for r, cnt in data["authorship_breakdown"].items():
        pct = round((cnt / m['total_works']) * 100, 1) if m['total_works'] > 0 else 0.0
        md.append(f"| **{r}** | {cnt} | {pct}% |")
    md.append("")

    md.append("## 4. Auditoría de Vías de Acceso Abierto\n")
    md.append("| Vía de Acceso Abierto | Cantidad | Descripción |")
    md.append("|---|---|---|")
    md.append(f"| **Diamante (Diamond)** | {data['oa_breakdown'].get('diamond', 0)} | Sin cobro de APC (Sostenibilidad académica pura) |")
    md.append(f"| **Dorada (Gold APC)** | {data['oa_breakdown'].get('gold', 0)} | Revista completamente abierta con pago de APC |")
    md.append(f"| **Verde (Green / Repositorio)** | {data['oa_breakdown'].get('green', 0)} | Autoarchivo en repositorios institucionales / temáticos |")
    md.append(f"| **Híbrida (Hybrid)** | {data['oa_breakdown'].get('hybrid', 0)} | Revista comercial de suscripción con opción OA |")
    md.append(f"| **Bronce (Bronze)** | {data['oa_breakdown'].get('bronze', 0)} | Acceso libre en sitio del editor sin licencia formal |")
    md.append(f"| **Cerrada (Closed)** | {data['oa_breakdown'].get('closed', 0)} | Bajo muro de pago (Paywall) |\n")

    if data.get("sdg_breakdown"):
        md.append("## 5. Alineación con los Objetivos de Desarrollo Sostenible (ODS de la ONU)\n")
        md.append("| Objetivo de Desarrollo Sostenible | Publicaciones Vinculadas |")
        md.append("|---|---|")
        for sdg, cnt in sorted(data["sdg_breakdown"].items(), key=lambda x: x[1], reverse=True):
            md.append(f"| **{sdg}** | {cnt} |")
        md.append("")

    md.append("## 6. Catálogo Detallado de Publicaciones Probatorias\n")
    md.append("| Año | Título de la Obra | Revista / Medio | Rol | Tramo (Tier) | Citas | FWCI | DOI |")
    md.append("|---|---|---|---|---|---|---|---|")
    for item in data["catalog"]:
        doi_link = f"[{item['doi']}](https://doi.org/{item['doi']})" if item['doi'] else "-"
        title_esc = item['title'].replace("|", "-")
        journal_esc = item['journal'].replace("|", "-")
        tier_str = item.get("tier") or item.get("quartile") or "T4"
        md.append(f"| {item['year']} | {title_esc} | {journal_esc} | {item['authorship_role']} | {tier_str} | {item['citations']} | {item['fwci']} | {doi_link} |")

    return "\n".join(md)


def generate_dossier_pdf(data: Dict[str, Any]) -> bytes:
    """
    Genera un informe formal en PDF listo para presentación ante comisiones dictaminadoras
    y evaluación integral de trayectoria académica.
    Utiliza WeasyPrint con maquetación ejecutiva.
    """
    m = data["metrics"]

    # Construir HTML estilizado con tipografía y diseño sobrio y elegante
    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Trayectoria Académica - {data['academic_name']}</title>
        <style>
            @page {{
                size: letter portrait;
                margin: 20mm 15mm 20mm 15mm;
                @top-left {{
                    content: "Info TlachIA • Trayectoria Académica";
                    font-size: 8pt;
                    color: #64748b;
                    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                }}
                @top-right {{
                    content: "{data['generated_at']}";
                    font-size: 8pt;
                    color: #64748b;
                    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                }}
                @bottom-right {{
                    content: "Página " counter(page) " de " counter(pages);
                    font-size: 8pt;
                    color: #64748b;
                    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                }}
            }}
            body {{
                font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                color: #1e293b;
                line-height: 1.4;
                font-size: 9pt;
            }}
            .header-box {{
                background: linear-gradient(135deg, #002B5C 0%, #003D64 100%);
                color: #ffffff;
                padding: 18px 24px;
                border-radius: 8px;
                margin-bottom: 20px;
                border-left: 6px solid #E39918;
            }}
            .header-box h1 {{
                margin: 0;
                font-size: 18pt;
                font-weight: 700;
                color: #ffffff;
                letter-spacing: -0.5px;
            }}
            .header-box .sub {{
                margin-top: 6px;
                font-size: 10pt;
                color: #cbd5e1;
            }}
            .grid-metrics {{
                display: table;
                width: 100%;
                margin-bottom: 20px;
            }}
            .metric-card {{
                display: table-cell;
                width: 25%;
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-top: 3px solid #003D64;
                border-radius: 6px;
                padding: 10px;
                text-align: center;
            }}
            .metric-val {{
                font-size: 16pt;
                font-weight: 700;
                color: #002B5C;
                margin: 2px 0;
            }}
            .metric-lbl {{
                font-size: 7.5pt;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                color: #64748b;
                font-weight: 600;
            }}
            h2 {{
                color: #002B5C;
                font-size: 12pt;
                border-bottom: 1.5px solid #003D64;
                padding-bottom: 4px;
                margin-top: 22px;
                margin-bottom: 10px;
                page-break-after: avoid;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 15px;
                font-size: 8pt;
            }}
            th {{
                background-color: #f1f5f9;
                color: #0f172a;
                font-weight: 600;
                text-align: left;
                padding: 6px 8px;
                border-bottom: 2px solid #cbd5e1;
            }}
            td {{
                padding: 5px 8px;
                border-bottom: 1px solid #e2e8f0;
            }}
            tr:nth-child(even) td {{
                background-color: #f8fafc;
            }}
            .badge {{
                display: inline-block;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 7pt;
                font-weight: 700;
            }}
            .badge-q1 {{ background-color: #dcfce7; color: #166534; }}
            .badge-q2 {{ background-color: #e0f2fe; color: #075985; }}
            .badge-q3 {{ background-color: #ffedd5; color: #9a3412; }}
            .badge-q4 {{ background-color: #f1f5f9; color: #475569; }}
            .badge-oa {{ background-color: #dbeafe; color: #1e40af; }}
            .doi-col {{
                font-family: monospace;
                font-size: 7pt;
                color: #2563eb;
            }}
            .footer-legal {{
                margin-top: 30px;
                border-top: 1px solid #e2e8f0;
                padding-top: 10px;
                font-size: 7pt;
                color: #94a3b8;
                text-align: justify;
            }}
        </style>
    </head>
    <body>
        <div class="header-box">
            <h1>Trayectoria Académica</h1>
            <div class="sub">
                <strong>Investigador(a):</strong> {data['academic_name']} &bull; 
                <strong>ORCID iD:</strong> {data.get('orcid') or 'No especificado'}<br>
                <strong>Afiliación:</strong> {data['institution']} {f"• {data['dependency']}" if data.get('dependency') else ""}<br>
                <strong>Distinción:</strong> {data['snii_level']} &bull; 
                <strong>Fecha de Generación:</strong> {data['generated_at']}
            </div>
        </div>

        <div class="grid-metrics">
            <div class="metric-card" style="margin-right: 8px;">
                <div class="metric-val">{m['total_works']}</div>
                <div class="metric-lbl">Publicaciones</div>
            </div>
            <div class="metric-card" style="margin-right: 8px;">
                <div class="metric-val">{m['total_citations']:,}</div>
                <div class="metric-lbl">Total Citas</div>
            </div>
            <div class="metric-card" style="margin-right: 8px;">
                <div class="metric-val">{m['h_index']}</div>
                <div class="metric-lbl">Índice H</div>
            </div>
            <div class="metric-card">
                <div class="metric-val">{m['avg_fwci']}</div>
                <div class="metric-lbl">FWCI Promedio</div>
            </div>
        </div>

        <div class="grid-metrics">
            <div class="metric-card" style="margin-right: 8px; border-top-color: #E39918;">
                <div class="metric-val">{m['pct_top_10']}%</div>
                <div class="metric-lbl">Top 10% Excelencia</div>
            </div>
            <div class="metric-card" style="margin-right: 8px; border-top-color: #E39918;">
                <div class="metric-val">{m['leadership_rate']}%</div>
                <div class="metric-lbl">Tasa Liderazgo</div>
            </div>
            <div class="metric-card" style="margin-right: 8px; border-top-color: #E39918;">
                <div class="metric-val">{m['pct_oa']}%</div>
                <div class="metric-lbl">Acceso Abierto (OA)</div>
            </div>
            <div class="metric-card" style="border-top-color: #E39918;">
                <div class="metric-val">${m['estimated_apc_savings_usd']:,}</div>
                <div class="metric-lbl">Ahorro APC (USD)</div>
            </div>
        </div>

        <h2>1. Indicadores de Liderazgo Científico y Roles de Autoría</h2>
        <table>
            <thead>
                <tr>
                    <th>Rol Evaluado</th>
                    <th style="text-align: center;">Obras</th>
                    <th style="text-align: center;">Porcentaje</th>
                    <th>Criterio Probatorio Institucional</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Primer Autor</strong></td>
                    <td style="text-align: center;">{data['authorship_breakdown'].get('Primer Autor', 0) + data['authorship_breakdown'].get('Primer Autor y Correspondencia', 0)}</td>
                    <td style="text-align: center;">{round(((data['authorship_breakdown'].get('Primer Autor', 0) + data['authorship_breakdown'].get('Primer Autor y Correspondencia', 0)) / max(m['total_works'], 1)) * 100, 1)}%</td>
                    <td>Concepción y liderazgo metodológico directo del artículo.</td>
                </tr>
                <tr>
                    <td><strong>Autor de Correspondencia</strong></td>
                    <td style="text-align: center;">{data['authorship_breakdown'].get('Autor de Correspondencia', 0) + data['authorship_breakdown'].get('Primer Autor y Correspondencia', 0)}</td>
                    <td style="text-align: center;">{round(((data['authorship_breakdown'].get('Autor de Correspondencia', 0) + data['authorship_breakdown'].get('Primer Autor y Correspondencia', 0)) / max(m['total_works'], 1)) * 100, 1)}%</td>
                    <td>Responsable principal ante la revista y la comunidad científica.</td>
                </tr>
                <tr>
                    <td><strong>Liderazgo Consolidado (1º o Corr.)</strong></td>
                    <td style="text-align: center;"><strong>{m['lead_count']}</strong></td>
                    <td style="text-align: center;"><strong>{m['leadership_rate']}%</strong></td>
                    <td>Total de obras bajo dirección intelectual verificada.</td>
                </tr>
                <tr>
                    <td><strong>Coautoría de Colaboración</strong></td>
                    <td style="text-align: center;">{data['authorship_breakdown'].get('Coautor', 0)}</td>
                    <td style="text-align: center;">{round((data['authorship_breakdown'].get('Coautor', 0) / max(m['total_works'], 1)) * 100, 1)}%</td>
                    <td>Participación en redes temáticas y proyectos colegiados.</td>
                </tr>
            </tbody>
        </table>

        <h2>2. Clasificación por Tramos de Impacto Observado (Tiers T1–T4)</h2>
        <p style="font-size: 8pt; color: #475569; margin-top: -6px; margin-bottom: 8px;">
            Distribución de publicaciones según el percentil de citación normalizado por disciplina y año (calidad e impacto observado a nivel de artículo según estándares DORA y Manifiesto de Leiden).
        </p>
        <table>
            <thead>
                <tr>
                    <th>Tramo (Tier)</th>
                    <th style="text-align: center;">Cantidad</th>
                    <th style="text-align: center;">Proporción</th>
                    <th>Nivel de Excelencia Relativo Observado</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><span class="badge badge-q1">Tier 1 (T1)</span></td>
                    <td style="text-align: center;">{data.get('tiers_breakdown', {}).get('T1', 0)}</td>
                    <td style="text-align: center;">{round((data.get('tiers_breakdown', {}).get('T1', 0) / max(m['total_works'], 1)) * 100, 1)}%</td>
                    <td>Percentil superior 75%–100% de la disciplina mundial (Alto Impacto Observado).</td>
                </tr>
                <tr>
                    <td><span class="badge badge-q2">Tier 2 (T2)</span></td>
                    <td style="text-align: center;">{data.get('tiers_breakdown', {}).get('T2', 0)}</td>
                    <td style="text-align: center;">{round((data.get('tiers_breakdown', {}).get('T2', 0) / max(m['total_works'], 1)) * 100, 1)}%</td>
                    <td>Percentil 50%–74% mundial de impacto medio-alto.</td>
                </tr>
                <tr>
                    <td><span class="badge badge-q3">Tier 3 (T3)</span></td>
                    <td style="text-align: center;">{data.get('tiers_breakdown', {}).get('T3', 0)}</td>
                    <td style="text-align: center;">{round((data.get('tiers_breakdown', {}).get('T3', 0) / max(m['total_works'], 1)) * 100, 1)}%</td>
                    <td>Percentil 25%–49% mundial de impacto medio-bajo.</td>
                </tr>
                <tr>
                    <td><span class="badge badge-q4">Tier 4 (T4)</span></td>
                    <td style="text-align: center;">{data.get('tiers_breakdown', {}).get('T4', 0)}</td>
                    <td style="text-align: center;">{round((data.get('tiers_breakdown', {}).get('T4', 0) / max(m['total_works'], 1)) * 100, 1)}%</td>
                    <td>Percentil 0%–24% mundial o publicaciones iniciales.</td>
                </tr>
            </tbody>
        </table>

        <h2>3. Catálogo de Artículos Probatorios</h2>
        <table>
            <thead>
                <tr>
                    <th style="width: 35px;">Año</th>
                    <th>Título y Revista</th>
                    <th style="width: 80px;">Rol</th>
                    <th style="width: 60px; text-align: center;">Tramo</th>
                    <th style="width: 35px; text-align: center;">Citas</th>
                    <th style="width: 35px; text-align: center;">FWCI</th>
                </tr>
            </thead>
            <tbody>
    """

    for item in data["catalog"][:60]:  # Limitar a las 60 obras principales para impresión formal
        t_val = item.get("tier") or item.get("quartile") or "T4"
        badge_cls = "badge-q1" if ("T1" in t_val or "Q1" in t_val) else "badge-q2" if ("T2" in t_val or "Q2" in t_val) else "badge-q3" if ("T3" in t_val or "Q3" in t_val) else "badge-q4"
        doi_display = f"<br><span class='doi-col'>https://doi.org/{item['doi']}</span>" if item.get('doi') else ""
        html_content += f"""
                <tr>
                    <td><strong>{item['year']}</strong></td>
                    <td>
                        <strong>{item['title']}</strong><br>
                        <em>{item['journal']}</em>
                        {doi_display}
                    </td>
                    <td>{item['authorship_role']}</td>
                    <td style="text-align: center;"><span class="badge {badge_cls}">{t_val}</span></td>
                    <td style="text-align: center;"><strong>{item['citations']}</strong></td>
                    <td style="text-align: center;">{item['fwci']}</td>
                </tr>
        """

    html_content += f"""
            </tbody>
        </table>

        <div class="footer-legal">
            <strong>Certificación de Datos:</strong> Este documento fue generado automáticamente por <em>Info TlachIA</em> 
            a partir de la sincronización de identificadores oficiales (ORCID, OpenAlex) y las tablas canónicas 
            de producción científica nacional e internacional alojadas en la infraestructura UNAM. 
            Los indicadores bibliométricos presentados se adhieren a la declaración DORA y a las mejores prácticas 
            internacionales de evaluación responsable de la trayectoria académica.
        </div>
    </body>
    </html>
    """

    return weasyprint.HTML(string=html_content).write_pdf()
