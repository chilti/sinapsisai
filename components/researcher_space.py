"""
components/researcher_space.py - Espacio Personal del Investigador y Curación
Integra:
1. Resumen de Perfil, Vinculación y Acreditación Institucional.
2. Radar de Artículos Citantes (Zero-join ClickHouse via citations_explorer).
3. Exportación a KnoMap (.knomap ZIP, .bib enriquecido, .json y .parquet).
4. Curación y Carga Externa (.bib uploader, desmentir falsos positivos, claims).
5. Guía de Credenciales ORCID cifradas (Fernet).
"""

import os
import io
import re
import json
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from lib.citations_explorer import get_citing_works_analysis, get_author_works
from lib.knomap_bridge import (
    export_author_bibtex,
    export_author_json,
    export_author_knomap_bundle
)
from lib.curation_service import get_curation_service
from lib.orcid_sync import push_work_to_orcid, sync_curated_works_to_orcid
from lib.dossier_generator import generate_dossier_data, generate_dossier_markdown, generate_dossier_pdf
from database.knowledge_graph import Neo4jGraphStore

# Flag para habilitar/deshabilitar la sincronización bidireccional de escritura hacia ORCID
ENABLE_ORCID_WRITE_SYNC = False


def render_researcher_space(user_auth: dict, select_academic_callback=None, trigger_sync_callback=None):
    """
    Renderiza el espacio personal del investigador en 'Mi Espacio'.
    
    Args:
        user_auth: Diccionario con la sesión del usuario (orcid, name, access_token).
        select_academic_callback: Función para navegar al perfil en el dashboard.
        trigger_sync_callback: Función para lanzar la ingesta en segundo plano.
    """
    user_orcid = user_auth.get("orcid", "").strip()
    user_name = user_auth.get("name", "Investigador").strip()
    bare_orcid = user_orcid.replace("https://orcid.org/", "").replace("http://orcid.org/", "").strip()
    
    curation = get_curation_service()
    
    # 1. Obtener perfil de Neo4j
    neo = Neo4jGraphStore()
    profile = neo.get_user_profile(user_orcid)
    
    academic_id = profile.get("academic_id") if profile else None
    academic_name = profile.get("academic_name") if profile else user_name
    institution = profile.get("institution") if profile else None
    dependency = profile.get("dependency") if profile else None
    subdependency = profile.get("subdependency") if profile else None
    is_snii = profile.get("is_snii") if profile else False
    snii_level = profile.get("snii_level") if profile else None
    
    # Consultar jerarquía completa en el Grafo de Conocimiento (Neo4j)
    try:
        with neo.driver.session() as s:
            q_hierarchy = """
            MATCH (a:Person)
            WHERE a.id = $name OR a.fullname = $name
            OPTIONAL MATCH (a)-[:AFFILIATED_TO]->(node)
            OPTIONAL MATCH (node)-[:PART_OF*0..2]->(parent)
            RETURN labels(node) as node_labels, node.name as node_name, 
                   labels(parent) as parent_labels, parent.name as parent_name,
                   a.is_snii as is_snii, a.snii_level as snii_level
            """
            records = s.run(q_hierarchy, name=academic_name).data()
            for r in records:
                n_labels = r.get("node_labels") or []
                n_name = r.get("node_name")
                p_labels = r.get("parent_labels") or []
                p_name = r.get("parent_name")
                
                if "Institution" in n_labels: institution = n_name
                if "Dependency" in n_labels: dependency = n_name
                if "Subdependency" in n_labels: subdependency = n_name
                
                if "Institution" in p_labels: institution = p_name
                if "Dependency" in p_labels: dependency = p_name
                if "Subdependency" in p_labels: subdependency = p_name

                if r.get("is_snii") is not None and not is_snii:
                    is_snii = r["is_snii"]
                if r.get("snii_level") and not snii_level:
                    snii_level = r["snii_level"]
    except Exception as e_h:
        print(f"[researcher_space] Error consultando jerarquía: {e_h}")
    neo.close()

    # Nivel más bajo en la jerarquía (entidad directa a administrar)
    lowest_entity = subdependency or dependency or institution

    # Si hay token en sesión, asegurar que está almacenado de forma encriptada
    if user_auth.get("access_token") and bare_orcid:
        curation.store_user_token(
            user_orcid=bare_orcid,
            access_token=user_auth.get("access_token"),
            scope="/authenticate"
        )

    # ── Encabezado del Perfil con Estilo Moderno ──
    snii_html = (
        f" &bull; <span style='background-color: #166534; color: #4ade80; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;'>✅ SNII {snii_level or 'Miembro'}</span>"
        if is_snii else ""
    )
    inst_display = institution or "Investigador Independiente / Sin Afiliación"
    dep_display = f" &bull; 📂 {dependency}" if dependency and dependency != "SIN INFORMACIÓN" else ""
    sub_display = f" &bull; 🏫 {subdependency}" if subdependency and subdependency != dependency else ""

    header_html = (
        f"<div style='background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); "
        f"padding: 22px 24px; border-radius: 12px; margin-bottom: 20px; "
        f"box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2); border-left: 6px solid #3b82f6;'>"
        f"<div style='margin-bottom: 6px;'>"
        f"<span style='font-size: 24px; margin-right: 6px;'>👨‍🔬</span>"
        f"<span style='color: #ffffff !important; font-size: 22px; font-weight: 700; letter-spacing: -0.3px;'>"
        f"{academic_name}"
        f"</span>"
        f"</div>"
        f"<div style='color: #94a3b8; font-size: 14px; margin-bottom: 4px;'>"
        f"<strong style='color: #cbd5e1;'>ORCID iD:</strong> "
        f"<a href='https://orcid.org/{bare_orcid}' target='_blank' style='color: #60a5fa; text-decoration: none; font-weight: 500;'>"
        f"https://orcid.org/{bare_orcid}"
        f"</a>"
        f"{snii_html}"
        f"</div>"
        f"<div style='color: #cbd5e1; font-size: 14px;'>"
        f"🏛️ {inst_display}{dep_display}{sub_display}"
        f"</div>"
        f"</div>"
    )
    st.markdown(header_html, unsafe_allow_html=True)

    # Sub-pestañas operativas
    tab_titles = [
        "📊 Resumen & Perfil",
        "🎯 Radar de Citas Cualitativo",
        "📦 Exportar a KnoMap y Bibliografía",
        "📄 Generador de Reporte",
        "🛠️ Curación y Gestión de Obras"
    ]
    if ENABLE_ORCID_WRITE_SYNC:
        tab_titles.append("🔐 Integración y Credenciales ORCID")

    tabs_result = st.tabs(tab_titles)
    subtab_summary = tabs_result[0]
    subtab_radar = tabs_result[1]
    subtab_export = tabs_result[2]
    subtab_dossier = tabs_result[3]
    subtab_curation = tabs_result[4]
    subtab_orcid = tabs_result[5] if ENABLE_ORCID_WRITE_SYNC else None

    # =========================================================================
    # SUBTAB 1: RESUMEN & PERFIL
    # =========================================================================
    with subtab_summary:
        col_act1, col_act2 = st.columns([1, 1])
        with col_act1:
            if select_academic_callback and academic_name:
                if st.button("📊 Ver mi Producción y Métricas en el Dashboard", type="primary", use_container_width=True):
                    select_academic_callback(academic_name)
                    st.success("✅ Perfil seleccionado. Ve a la pestaña 'Perfil Académico'.")
        with col_act2:
            if trigger_sync_callback and academic_name:
                if st.button("🔄 Sincronizar Producción desde APIs (Background)", use_container_width=True):
                    trigger_sync_callback(academic_name, bare_orcid)
                    st.info("⏳ Sincronización iniciada en segundo plano. Los resultados se actualizarán en un momento.")

        st.markdown("---")
        
        # Estado de Roles del Usuario
        user_roles = curation.get_user_roles(bare_orcid)
        is_inst_admin = curation.is_user_institutional_admin(bare_orcid)
        
        c_r1, c_r2 = st.columns(2)
        with c_r1:
            st.metric("Identidad Digital", "Verificada con ORCID", "Pública")
        with c_r2:
            role_display = "Administrador Institucional" if is_inst_admin else "Investigador"
            st.metric("Rol en Plataforma", role_display)

        st.markdown("---")
        
        # Sección de Solicitud de Acreditación Institucional
        with st.expander("🏛️ Solicitar Acreditación como Administrador Institucional", expanded=False):
            st.write(
                "Los administradores institucionales (ej. bibliotecarios, directores de investigación o "
                "analistas cienciométricos) cuentan con herramientas avanzadas para auditar la producción de su institución, "
                "gestionar alias institucionales y monitorear la fuga de capital por APCs."
            )
            
            if is_inst_admin:
                st.success("✅ Ya cuentas con acreditación activa como Administrador Institucional.")
            else:
                with st.form("form_request_accreditation"):
                    st.write("**Formulario de Acreditación Institucional**")
                    
                    if subdependency:
                        st.markdown(
                            f"<div style='background: #f8fafc; border: 1px solid #e2e8f0; padding: 10px 14px; border-radius: 6px; font-size: 13px; margin-bottom: 12px; color: #334155;'>"
                            f"🏛️ <strong>Institución:</strong> {institution} &bull; "
                            f"📂 <strong>Dependencia:</strong> {dependency} &bull; "
                            f"🎯 <strong>Adscripción Directa:</strong> <span style='color: #0369a1; font-weight: 600;'>{subdependency}</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                    elif dependency:
                        st.markdown(
                            f"<div style='background: #f8fafc; border: 1px solid #e2e8f0; padding: 10px 14px; border-radius: 6px; font-size: 13px; margin-bottom: 12px; color: #334155;'>"
                            f"🏛️ <strong>Institución:</strong> {institution} &bull; "
                            f"🎯 <strong>Adscripción Directa:</strong> <span style='color: #0369a1; font-weight: 600;'>{dependency}</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                    f_target_entity = st.text_input(
                        "Entidad / Dependencia a administrar:",
                        value=lowest_entity or institution or "",
                        disabled=True,
                        help="Por políticas de gobernanza, la acreditación solo puede solicitarse para tu entidad de adscripción directa, no para entidades paraguas superiores."
                    )
                    st.caption("🔒 *Por políticas de gobernanza institucional, la acreditación se otorga exclusivamente para tu entidad de adscripción más específica en la jerarquía.*")
                    
                    f_email = st.text_input("Correo electrónico institucional:", placeholder="nombre@ciencias.unam.mx")
                    f_pos = st.text_input("Puesto o Cargo:", placeholder="Ej: Coordinador de Biblioteca / Analista Cienciométrico")
                    f_notes = st.text_area("Justificación o comentarios adicionales para el superadministrador:", placeholder="Detalla tu rol en la gestión bibliométrica...")
                    
                    submit_req = st.form_submit_button("Enviar Solicitud de Acreditación", type="primary")
                    if submit_req:
                        if not f_target_entity or not f_email or not f_pos:
                            st.error("Por favor completa los campos de Correo y Cargo.")
                        else:
                            ok, msg = curation.request_accreditation(
                                user_orcid=bare_orcid,
                                user_name=academic_name,
                                institution_name=f_target_entity,
                                institutional_email=f_email,
                                position=f_pos,
                                notes=f_notes
                            )
                            if ok:
                                st.success("🎉 " + msg)
                            else:
                                st.warning("⚠️ " + msg)

    # =========================================================================
    # SUBTAB 2: RADAR DE CITAS CUALITATIVO
    # =========================================================================
    with subtab_radar:
        st.subheader("🎯 Radar Cualitativo de Artículos Citantes")
        st.caption("Analiza quién cita tu producción, desde qué países, en qué instituciones y qué tan influyentes son las obras citantes.")

        with st.spinner("Consultando red de citas en ClickHouse (modo zero-joins)..."):
            analysis = get_citing_works_analysis(academic_name, bare_orcid, limit=200)

        if not analysis or analysis.get("total_citations", 0) == 0:
            st.info("💡 Aún no se han detectado citas registradas en la base local para tus trabajos indexados.")
        else:
            # KPIs del Radar
            k1, k2, k3, k4, k5, k6 = st.columns(6)
            with k1:
                st.metric("Total Citas", f"{analysis['total_citations']:,}")
            with k2:
                st.metric("Citas Netas", f"{analysis['net_citations']:,}", help="Citas provenientes de otros autores (sin autocitas)")
            with k3:
                sc_rate = analysis["self_citation_rate"]
                st.metric(
                    "Autocitas", 
                    f"{sc_rate:.1f}%", 
                    f"{analysis['self_citations']} citas",
                    help="Autocita directa: el autor evaluado figura entre los autores del artículo citante."
                )
            with k4:
                st.metric("En Top 10% Global", f"{analysis['top_10_percent_citations']:,}", help="Citas provenientes de artículos de alto impacto mundial")
            with k5:
                st.metric("Países Citantes", f"{analysis['citing_countries_count']}")
            with k6:
                st.metric("Instituciones", f"{analysis['citing_institutions_count']}")

            st.caption(
                "📌 **Nota metodológica sobre autocitas:** Se contabilizan exclusivamente las **autocitas directas** del autor evaluado "
                "(aquellas en donde el investigador participa como coautor en la obra citante). No incluye citas de coautores en trabajos independientes. "
                "Al basarse en coincidencia de tokens de firma, variaciones como abreviaturas extremas o iniciales podrían incidir en la detección."
            )
            st.markdown("---")

            # Gráficas de Países e Instituciones
            c_g1, c_g2 = st.columns(2)
            
            with c_g1:
                st.write("**Top 10 Países que Citan tu Producción**")
                country_dist = analysis.get("country_distribution", {})
                if country_dist:
                    df_c = pd.DataFrame(list(country_dist.items()), columns=["País", "Citas"]).head(10)
                    df_c = df_c.sort_values("Citas", ascending=True)
                    fig_c = px.bar(
                        df_c, 
                        x="Citas", 
                        y="País", 
                        orientation="h",
                        color="Citas",
                        color_continuous_scale="Blues",
                        text="Citas"
                    )
                    fig_c.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=320, coloraxis_showscale=False)
                    st.plotly_chart(fig_c, use_container_width=True)
                else:
                    st.write("Sin datos de países disponibles.")

            with c_g2:
                st.write("**Top 10 Instituciones Citantes**")
                inst_dist = analysis.get("institution_distribution", {})
                if inst_dist:
                    df_i = pd.DataFrame(list(inst_dist.items()), columns=["Institución", "Citas"]).head(10)
                    df_i = df_i.sort_values("Citas", ascending=True)
                    fig_i = px.bar(
                        df_i, 
                        x="Citas", 
                        y="Institución", 
                        orientation="h",
                        color="Citas",
                        color_continuous_scale="Viridis",
                        text="Citas"
                    )
                    fig_i.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=320, coloraxis_showscale=False)
                    st.plotly_chart(fig_i, use_container_width=True)
                else:
                    st.write("Sin datos de instituciones disponibles.")

            # Evolución Temporal de Citas
            year_dist = analysis.get("year_distribution", {})
            if year_dist:
                st.write("**Evolución Temporal de Citas Recibidas**")
                df_y = pd.DataFrame(list(year_dist.items()), columns=["Año", "Citas"]).sort_values("Año")
                df_y = df_y[(df_y["Año"] >= 1990) & (df_y["Año"] <= datetime.now().year)]
                fig_y = px.area(
                    df_y, 
                    x="Año", 
                    y="Citas", 
                    markers=True,
                    color_discrete_sequence=["#2563eb"]
                )
                fig_y.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=240)
                st.plotly_chart(fig_y, use_container_width=True)

            # Tabla de Artículos Citantes Destacados
            st.markdown("---")
            st.write("**Artículos Citantes Recientes o Destacados**")
            top_citing = analysis.get("top_citing_works", [])
            if top_citing:
                records = []
                for w in top_citing:
                    doi_val = w.get("doi") or ""
                    doi_link = f"https://doi.org/{doi_val}" if doi_val else ""
                    records.append({
                        "Año": w.get("publication_year"),
                        "Título de la Obra Citante": w.get("title") or "Sin Título",
                        "Revista / Fuente": w.get("journal") or "N/D",
                        "Autores": ", ".join(w.get("authors") or [])[:60],
                        "Citas Obra": w.get("cited_by_count", 0),
                        "Top 10%": "🌟 Sí" if w.get("is_top_10") else "No",
                        "DOI": doi_link
                    })
                df_citing_table = pd.DataFrame(records)
                st.dataframe(
                    df_citing_table,
                    column_config={
                        "DOI": st.column_config.LinkColumn("Enlace DOI")
                    },
                    use_container_width=True,
                    hide_index=True
                )

    # =========================================================================
    # SUBTAB 3: EXPORTAR A KNOMAP Y BIBLIOGRAFÍA
    # =========================================================================
    with subtab_export:
        st.subheader("📦 Exportación de Producción & Paquete KnoMap Hub")
        st.write(
            "Descarga tu producción científica normalizada y enriquecida con métricas de impacto, "
            "o exporta un paquete portable `.knomap` listo para analizar proyecciones neuronales (SOM/UMAP) "
            "y redes de coautoría en la plataforma KnoMap."
        )

        with st.spinner("Preparando corpus de publicaciones para exportación..."):
            works = get_author_works(academic_name, bare_orcid)
            
            # Filtrar obras desmentidas
            disclaimed_ids = set()
            try:
                disclaimed_list = curation.list_disclaimed_works(bare_orcid)
                disclaimed_ids = {d["work_id"] for d in disclaimed_list}
            except Exception:
                pass
            
            clean_works = [w for w in works if w.get("work_id") not in disclaimed_ids]
            df_export = pd.DataFrame(clean_works)

        if df_export.empty:
            st.warning("⚠️ No se encontraron publicaciones indexadas para este investigador.")
        else:
            st.info(f"📚 Total de publicaciones disponibles para exportación: **{len(df_export)}**")

            col_exp1, col_exp2 = st.columns(2)
            
            with col_exp1:
                st.markdown(
                    """
                    <div style="padding: 16px; border: 1px solid #3b82f6; border-radius: 8px; background: #f8fafc; margin-bottom: 12px;">
                        <h4 style="margin: 0; color: #1e3a8a;">🎓 Paquete de Proyecto .knomap</h4>
                        <p style="font-size: 13px; color: #475569; margin: 6px 0 12px 0;">
                            Archivo ZIP autocontenido con <code>corpus.parquet</code>, <code>author_network.json</code>, 
                            <code>topics_matrix.parquet</code> y manifiesto con SHA-256. Compatible 100% con KnoMap Hub.
                        </p>
                    """,
                    unsafe_allow_html=True
                )
                knomap_zip_bytes = export_author_knomap_bundle(df_export, academic_name)
                clean_filename = f"knomap_project_{bare_orcid or 'author'}.knomap"
                st.download_button(
                    label="⬇️ Descargar Paquete .knomap",
                    data=knomap_zip_bytes,
                    file_name=clean_filename,
                    mime="application/zip",
                    type="primary",
                    use_container_width=True
                )
                st.markdown("</div>", unsafe_allow_html=True)

            with col_exp2:
                st.markdown(
                    """
                    <div style="padding: 16px; border: 1px solid #10b981; border-radius: 8px; background: #f8fafc; margin-bottom: 12px;">
                        <h4 style="margin: 0; color: #065f46;">📑 BibTeX Enriquecido (.bib)</h4>
                        <p style="font-size: 13px; color: #475569; margin: 6px 0 12px 0;">
                            Referencias completas (author, title, journal, year, volume, pages, doi, url, abstract) 
                            más métricas en tag <code>annote</code> (FWCI, Citas, OA, ODS).
                        </p>
                    """,
                    unsafe_allow_html=True
                )
                bibtex_str = export_author_bibtex(df_export, academic_name)
                st.download_button(
                    label="⬇️ Descargar Archivo .bib",
                    data=bibtex_str.encode("utf-8"),
                    file_name=f"referencias_{bare_orcid or 'author'}.bib",
                    mime="application/x-bibtex",
                    use_container_width=True
                )
                st.markdown("</div>", unsafe_allow_html=True)

            col_exp3, col_exp4 = st.columns(2)
            with col_exp3:
                st.markdown(
                    """
                    <div style="padding: 16px; border: 1px solid #64748b; border-radius: 8px; background: #f8fafc;">
                        <h4 style="margin: 0; color: #1e293b;">📊 Formato JSON Canónico</h4>
                        <p style="font-size: 13px; color: #475569; margin: 6px 0 12px 0;">
                            Estructura estándar compatible con APIs de TlachIA Metrics y serialización ligera.
                        </p>
                    """,
                    unsafe_allow_html=True
                )
                json_str = export_author_json(df_export, academic_name)
                st.download_button(
                    label="⬇️ Descargar JSON Canónico",
                    data=json_str.encode("utf-8"),
                    file_name=f"corpus_{bare_orcid or 'author'}.json",
                    mime="application/json",
                    use_container_width=True
                )
                st.markdown("</div>", unsafe_allow_html=True)

            with col_exp4:
                st.markdown(
                    """
                    <div style="padding: 16px; border: 1px solid #64748b; border-radius: 8px; background: #f8fafc;">
                        <h4 style="margin: 0; color: #1e293b;">🗄️ Formato Parquet Binario</h4>
                        <p style="font-size: 13px; color: #475569; margin: 6px 0 12px 0;">
                            Tabla columnar de alta velocidad para análisis masivo en DuckDB, R o Python.
                        </p>
                    """,
                    unsafe_allow_html=True
                )
                parquet_buf = io.BytesIO()
                df_export.to_parquet(parquet_buf, index=False)
                st.download_button(
                    label="⬇️ Descargar Parquet",
                    data=parquet_buf.getvalue(),
                    file_name=f"corpus_{bare_orcid or 'author'}.parquet",
                    mime="application/octet-stream",
                    use_container_width=True
                )
                st.markdown("</div>", unsafe_allow_html=True)

    # =========================================================================
    # SUBTAB: GENERADOR DE REPORTE (1-CLIC)
    # =========================================================================
    with subtab_dossier:
        st.subheader("📄 Generador de Reporte")
        st.write(
            "Genera el informe probatorio completo de trayectoria académica e impacto científico. "
            "Incluye clasificación por cuartiles, roles de liderazgo de autoría y alineación con los ODS."
        )

        with st.spinner("Compilando indicadores cienciométricos y catálogo probatorio..."):
            dossier_data = generate_dossier_data(
                academic_name=academic_name,
                orcid=bare_orcid,
                institution=institution,
                dependency=dependency,
                snii_level=snii_level
            )
            dm = dossier_data["metrics"]

        # Métricas Ejecutivas del Dossier (2 filas de 4 columnas)
        c_d1, c_d2, c_d3, c_d4 = st.columns(4)
        c_d1.metric("📚 Publicaciones", f"{dm['total_works']}")
        c_d2.metric("🌟 Citas Totales", f"{dm['total_citations']:,}")
        c_d3.metric("📈 Índice H", f"{dm['h_index']}")
        c_d4.metric("🌐 FWCI Promedio", f"{dm['avg_fwci']}")

        c_d5, c_d6, c_d7, c_d8 = st.columns(4)
        c_d5.metric("🥇 Top 10% Mundial", f"{dm['pct_top_10']}%", f"{dm['top_10_count']} obras")
        c_d6.metric("🎯 Tasa de Liderazgo", f"{dm['leadership_rate']}%", f"{dm['lead_count']} obras")
        c_d7.metric("🔓 Acceso Abierto", f"{dm['pct_oa']}%")
        c_d8.metric("💰 Ahorro APC (USD)", f"${dm['estimated_apc_savings_usd']:,}")

        st.markdown("---")

        col_dos1, col_dos2 = st.columns(2)

        with col_dos1:
            st.markdown("##### 👥 Desglose de Roles y Liderazgo de Autoría")
            auth_df = pd.DataFrame([
                {"Rol": k, "Obras": v, "Proporción": f"{round((v / max(dm['total_works'], 1)) * 100, 1)}%"}
                for k, v in dossier_data["authorship_breakdown"].items()
            ])
            st.dataframe(auth_df, hide_index=True, use_container_width=True)

        with col_dos2:
            st.markdown("##### 🏆 Distribución por Cuartiles Internacionales")
            q_df = pd.DataFrame([
                {"Cuartil": k, "Cantidad": v, "Porcentaje": f"{round((v / max(dm['total_works'], 1)) * 100, 1)}%"}
                for k, v in dossier_data["quartiles_breakdown"].items()
            ])
            st.dataframe(q_df, hide_index=True, use_container_width=True)

        if dossier_data.get("sdg_breakdown"):
            st.markdown("##### 🌍 Alineación con Objetivos de Desarrollo Sostenible (ODS de la ONU)")
            sdg_cols = st.columns(min(len(dossier_data["sdg_breakdown"]), 4))
            for i, (sdg_name, count) in enumerate(sorted(dossier_data["sdg_breakdown"].items(), key=lambda x: x[1], reverse=True)[:8]):
                with sdg_cols[i % 4]:
                    st.caption(f"**{sdg_name}**: {count} obra(s)")

        st.markdown("---")
        st.markdown("#### 📥 Descarga de Documentos Probatorios")
        
        col_btn_pdf, col_btn_md = st.columns(2)
        with col_btn_pdf:
            try:
                pdf_bytes = generate_dossier_pdf(dossier_data)
                clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', academic_name)
                st.download_button(
                    label="📄 Descargar Reporte en PDF",
                    data=pdf_bytes,
                    file_name=f"Reporte_Trayectoria_{clean_name}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
            except Exception as e_pdf:
                st.error(f"Error generando PDF: {e_pdf}")

        with col_btn_md:
            md_text = generate_dossier_markdown(dossier_data)
            clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', academic_name)
            st.download_button(
                label="📝 Descargar Reporte en Markdown (.md)",
                data=md_text.encode("utf-8"),
                file_name=f"Reporte_Trayectoria_{clean_name}.md",
                mime="text/markdown",
                use_container_width=True
            )

        with st.expander("👁️ Vista Previa del Informe en Markdown", expanded=False):
            st.markdown(md_text)

    # =========================================================================
    # SUBTAB 4: CURACIÓN Y GESTIÓN DE OBRAS
    # =========================================================================
    with subtab_curation:
        st.subheader("🛠️ Curación de Producción y Gestión de Obras")
        st.write(
            "Mantén la máxima precisión en tu perfil. Puedes cargar archivos bibliográficos adicionales (.bib) "
            "o desmentir obras asignadas erróneamente por homonimia o ambigüedades en algoritmos de indexación."
        )

        # Cargar archivo .bib
        with st.expander("📥 Cargar Archivo .bib Externo (Nutrir Perfil)", expanded=False):
            st.write(
                "Sube un archivo BibTeX generado desde Zotero, Mendeley, Web of Science o Scopus. "
                "Las referencias se incorporarán a tu colección personal."
            )
            uploaded_bib = st.file_uploader("Selecciona archivo .bib:", type=["bib", "bibtex"], key="uploader_bib")
            if uploaded_bib:
                try:
                    content = uploaded_bib.read().decode("utf-8", errors="ignore")
                    if st.button("Procesar e Importar Obras"):
                        count, msg = curation.import_bibtex_file(bare_orcid, content)
                        if count > 0:
                            st.success(f"🎉 {msg}")
                            st.rerun()
                        else:
                            st.warning(f"⚠️ {msg}")
                except Exception as e:
                    st.error(f"Error al leer el archivo: {e}")

        # Listado de obras personalizadas cargadas
        custom_works = curation.list_custom_works(bare_orcid)
        if custom_works:
            st.write(f"**Obras Personales Cargadas Manualmente ({len(custom_works)}):**")
            df_custom = pd.DataFrame(custom_works)
            st.dataframe(
                df_custom[["title", "journal", "year", "doi", "source_file"]],
                use_container_width=True,
                hide_index=True
            )

        st.markdown("---")
        
        # Desmentir / Auditar Obras Indexadas
        st.write("#### 🛡️ Auditoría de Obras Indexadas (Eliminación de Homónimos)")
        st.caption("Si detectas un artículo que no fue escrito por ti, márcalo como 'No es mío'. Será excluido inmediatamente de tus métricas y exportaciones.")
        
        works = get_author_works(academic_name, bare_orcid)
        disclaimed_items = curation.list_disclaimed_works(bare_orcid)
        disclaimed_ids = {d["work_id"]: d for d in disclaimed_items}

        if disclaimed_items:
            with st.expander(f"🚫 Ver Obras Desmentidas ({len(disclaimed_items)})", expanded=False):
                for d in disclaimed_items:
                    c_d1, c_d2 = st.columns([4, 1])
                    with c_d1:
                        st.write(f"❌ **{d.get('title') or d['work_id']}**")
                        st.caption(f"ID: `{d['work_id']}` | Desmentido el: {d.get('created_at')}")
                    with c_d2:
                        if st.button("↩️ Reclamar (Restaurar)", key=f"restore_{d['work_id']}"):
                            curation.claim_work(bare_orcid, d["work_id"], title=d.get("title", ""))
                            st.success("Obra restaurada.")
                            st.rerun()

        # Lista de obras activas para desmentir
        active_works = [w for w in works if w.get("work_id") not in disclaimed_ids]
        if active_works:
            st.write(f"Mostrando **{len(active_works)}** obras activas vinculadas a tu perfil:")
            
            search_work = st.text_input("Filtrar obras por título o año:", placeholder="Ej: Quantum, 2023...")
            filtered_works = active_works
            if search_work:
                sw = search_work.lower()
                filtered_works = [w for w in active_works if sw in str(w.get("title", "")).lower() or sw in str(w.get("publication_year", ""))]

            for idx, w in enumerate(filtered_works[:25]): # Paginar primeras 25
                wid = w.get("work_id") or f"idx_{idx}"
                w_title = w.get("title") or "Sin título"
                w_year = w.get("publication_year") or "N/D"
                w_journal = w.get("journal") or "Revista"
                w_doi = w.get("doi") or ""
                
                c_w1, c_w2 = st.columns([4.2, 1.2])
                with c_w1:
                    doi_link = f" | [DOI](https://doi.org/{w_doi})" if w_doi else ""
                    st.markdown(f"**{w_title}** ({w_year}){doi_link}")
                    st.caption(f"📰 {w_journal} &bull; Citas: {w.get('cited_by_count', 0)} &bull; ID: `{wid}`")
                with c_w2:
                    if st.button("❌ No es mía", key=f"disclaim_{wid}"):
                        curation.disclaim_work(
                            bare_orcid, 
                            wid, 
                            title=w_title, 
                            reason="Marcado manualmente por el autor en Mi Espacio"
                        )
                        st.warning("Obra desmentida y excluida de tu perfil.")
                        st.rerun()
                st.markdown("<hr style='margin: 4px 0; border: none; border-top: 1px solid #f1f5f9;'>", unsafe_allow_html=True)
            
            if len(filtered_works) > 25:
                st.caption(f"Mostrando 25 de {len(filtered_works)} publicaciones. Usa el filtro de texto para buscar obras específicas.")

    # =========================================================================
    # SUBTAB 6: GUÍA & CONFIGURACIÓN DE CREDENCIALES ORCID (Oculta por defecto)
    # =========================================================================
    if ENABLE_ORCID_WRITE_SYNC and subtab_orcid:
        _render_orcid_sync_subtab(subtab_orcid, bare_orcid, academic_name, curation)


def _render_orcid_sync_subtab(subtab_orcid, bare_orcid, academic_name, curation):
    """Subpestaña para configuración de credenciales y sincronización de escritura hacia ORCID."""
    with subtab_orcid:
        st.subheader("🔐 Integración Bidireccional y Credenciales de ORCID")
        st.write(
            "SNII Info TlachIA se comunica con la API de ORCID para autenticar tu identidad digital. "
            "Para permitir la escritura y sincronización bidireccional de obras hacia tu registro en ORCID, "
            "se requiere configurar credenciales con los permisos correspondientes."
        )

        st.markdown(
            """
            <div style="background-color: #eff6ff; border-left: 4px solid #3b82f6; padding: 16px; border-radius: 6px; margin-bottom: 20px;">
                <h4 style="margin: 0; color: #1e40af;">🔒 Almacenamiento Cifrado en Reposo</h4>
                <p style="margin: 6px 0 0 0; color: #1e3a8a; font-size: 14px;">
                    Todos los tokens de acceso y actualización de ORCID se encriptan con <strong>Fernet (AES-128-CBC + HMAC-SHA256)</strong> 
                    utilizando una clave criptográfica de servidor. Nunca se almacenan en texto plano en la base de datos.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.write("### 📖 Guía Paso a Paso: Cómo Crear y Configurar Credenciales en ORCID")
        st.markdown(
            """
            1. **Accede a las Herramientas de Desarrollador de ORCID:**
               - Inicia sesión con tu cuenta en [https://orcid.org/developer-tools](https://orcid.org/developer-tools).
            
            2. **Registrar una Aplicación Cliente:**
               - Haz clic en **"Register a free public API client"** (o usa la API de Miembro si tu institución cuenta con membresía institucional).
               - Llena el formulario con:
                 - **Nombre de la Aplicación:** `SNII Info TlachIA`
                 - **Website URL:** `https://dinamica1.fciencias.unam.mx/sinapsis/`
                 - **Redirect URI:** `https://dinamica1.fciencias.unam.mx/sinapsis/`
            
            3. **Permisos y Scopes Disponibles:**
               - `/authenticate`: Permite autenticar tu identidad y leer tu ORCID iD verificado (activo actualmente).
               - `/read-limited`: Permite leer obras o información marcada como "de confianza" en tu perfil.
               - `/activities/update`: **Requerido para escribir obras hacia tu perfil de ORCID** (requiere membresía institucional de ORCID o Sandbox de desarrollo).
            
            4. **Obtención de Claves:**
               - ORCID te proporcionará un **Client ID** (formato `APP-XXXXXXXXXXXXXXXX`) y un **Client Secret**.
            """
        )

        # Formulario para registrar credenciales personalizadas si se desean
        with st.expander("⚙️ Configuración Avanzada de Token / Cliente ORCID Personal", expanded=False):
            st.write("Si tu institución te proporcionó credenciales de API de Miembro para escritura en ORCID, puedes ingresarlas aquí:")
            
            existing_token = curation.get_user_token(bare_orcid, scope="/activities/update")
            if existing_token:
                st.success("✅ Ya cuentas con un token de escritura `/activities/update` guardado y encriptado.")
            
            with st.form("form_orcid_custom_creds"):
                c_id = st.text_input("ORCID Client ID (Opcional):", placeholder="APP-XXXXXXXXXXXX")
                c_token = st.text_input("Access Token de Escritura (/activities/update):", type="password", placeholder="Ingresa el token emitido por ORCID...")
                submit_tok = st.form_submit_button("Guardar Credenciales Cifradas")
                if submit_tok:
                    if not c_token:
                        st.error("Por favor proporciona el token de acceso.")
                    else:
                        curation.store_user_token(
                            user_orcid=bare_orcid,
                            access_token=c_token.strip(),
                            scope="/activities/update",
                            client_id=c_id.strip() if c_id else None
                        )
                        st.success("🔒 Token cifrado y almacenado con éxito en el almacén de seguridad.")
                        st.rerun()

        st.write("---")
        st.subheader("🚀 Exportar y Sincronizar Obras Validadas a mi Perfil Oficial de ORCID")
        st.write(
            "Esta herramienta recorre tu producción validada en SNII Info TlachIA y la envía mediante "
            "la API REST v3.0 de ORCID. Detecta automáticamente las obras que ya existen para evitar duplicaciones."
        )

        existing_write_token = curation.get_user_token(bare_orcid, scope="/activities/update")
        col_sync1, col_sync2 = st.columns([1, 1])
        with col_sync1:
            dry_run_choice = st.checkbox("🧪 Modo Simulación (Dry Run / Prueba sin escribir)", value=not bool(existing_write_token))
        with col_sync2:
            use_sandbox = st.checkbox("🧪 Usar ORCID Sandbox", value=False)

        if not existing_write_token and not dry_run_choice:
            st.warning("⚠️ Se requiere un token con scope `/activities/update` para sincronizar en modo real. Puedes guardar uno arriba o activar el 'Modo Simulación'.")

        if st.button("🚀 Iniciar Sincronización con ORCID", type="primary", use_container_width=True):
            with st.spinner("Consultando publicaciones validadas y conectando con la API de ORCID..."):
                works_to_sync = get_author_works(academic_name, bare_orcid)
                sync_res = sync_curated_works_to_orcid(
                    orcid=bare_orcid,
                    works=works_to_sync,
                    token=existing_write_token,
                    is_sandbox=use_sandbox,
                    dry_run=dry_run_choice
                )

            st.write("### 📊 Resultado de la Sincronización")
            c_s1, c_s2, c_s3, c_s4 = st.columns(4)
            c_s1.metric("Total Procesadas", sync_res.get("total", 0))
            c_s2.metric("Exportadas / Listas", sync_res.get("pushed", 0))
            c_s3.metric("Ya Existían (Evitadas)", sync_res.get("already_exists", 0))
            c_s4.metric("Errores", sync_res.get("failed", 0))

            if sync_res.get("error"):
                st.error(f"Detalle: {sync_res['error']}")

            with st.expander("🔍 Ver Detalle de Respuestas por Obra", expanded=True):
                for item in sync_res.get("details", [])[:30]:
                    st_badge = "✅" if item.get("status") in ["CREATED", "DRY_RUN"] else "ℹ️" if item.get("status") == "ALREADY_EXISTS" else "❌"
                    st.write(f"{st_badge} **{item.get('title')}** (DOI: `{item.get('doi')}`) — Status: `{item.get('status')}`")
