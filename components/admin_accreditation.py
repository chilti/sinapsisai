"""
components/admin_accreditation.py - Panel de Acreditación Institucional y Gobernanza
Herramientas para el Super-Administrador:
1. Bandeja de Solicitudes de Acreditación (Aprobar / Rechazar).
2. Padrón de Administradores Institucionales Activos.
3. Catálogo de Variantes y Alias Institucionales.
"""

import streamlit as st
import pandas as pd
from lib.curation_service import get_curation_service


def render_admin_accreditation_panel(admin_orcid: str = "super_admin"):
    """Renderiza la sección de gobernanza y acreditación institucional."""
    curation = get_curation_service()

    st.subheader("🏛️ Gobernanza Institucional y Acreditación de Bibliotecarios / Administradores")
    st.write(
        "Gestiona las acreditaciones para usuarios avanzados con privilegios de administración institucional "
        "(ej. coordinadores de bibliotecas, vicerrectorías de investigación o analistas cienciométricos)."
    )

    tab_pend, tab_active, tab_aliases = st.tabs([
        "📋 Solicitudes Pendientes",
        "👥 Administradores Acreditados",
        "🏷️ Catálogo de Alias Institucionales"
    ])

    # ── TAB 1: SOLICITUDES PENDIENTES ──
    with tab_pend:
        st.write("#### 📬 Bandeja de Solicitudes de Acreditación Institucional")
        pending_list = curation.list_pending_accreditations()

        if not pending_list:
            st.success("✅ No hay solicitudes pendientes de acreditación en este momento.")
        else:
            st.info(f"Tienes **{len(pending_list)}** solicitudes pendientes de revisión.")

            for req in pending_list:
                req_orcid = req.get("orcid")
                req_name = req.get("name") or "Investigador"
                req_email = req.get("email") or "Sin correo"
                req_inst = req.get("institution") or "Sin institución"
                req_pos = req.get("dependency") or "Sin cargo"
                req_date = req.get("created_at") or ""

                with st.container():
                    st.markdown(
                        f"""
                        <div style="background: #ffffff; padding: 16px; border-radius: 8px; 
                                    border: 1px solid #e2e8f0; border-left: 5px solid #3b82f6; margin-bottom: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                                <div>
                                    <h4 style="margin: 0; color: #1e293b;">{req_name}</h4>
                                    <p style="margin: 4px 0; color: #475569; font-size: 14px;">
                                        <strong>ORCID:</strong> <a href="https://orcid.org/{req_orcid}" target="_blank">{req_orcid}</a> &bull; 
                                        <strong>Correo:</strong> {req_email}
                                    </p>
                                    <p style="margin: 4px 0; color: #334155; font-size: 14px;">
                                        <strong>Institución:</strong> {req_inst} &bull; 
                                        <strong>Cargo / Rol:</strong> {req_pos}
                                    </p>
                                    <span style="font-size: 12px; color: #94a3b8;">Solicitado el: {req_date}</span>
                                </div>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    c_btn1, c_btn2, _ = st.columns([1.5, 1.5, 5])
                    with c_btn1:
                        if st.button("✅ Aprobar como Administrador", key=f"appr_{req_orcid}", type="primary"):
                            curation.decide_accreditation(req_orcid, "APPROVE", decided_by=admin_orcid)
                            st.success(f"Acreditación otorgada a {req_name}.")
                            st.rerun()
                    with c_btn2:
                        if st.button("❌ Rechazar", key=f"rej_{req_orcid}"):
                            curation.decide_accreditation(req_orcid, "REJECT", decided_by=admin_orcid)
                            st.warning(f"Solicitud rechazada para {req_name}.")
                            st.rerun()

                    st.markdown("---")

    # ── TAB 2: ADMINISTRADORES ACTIVOS ──
    with tab_active:
        st.write("#### 👥 Administradores Institucionales Acreditados")
        active_admins = curation.list_active_institutional_admins()

        if not active_admins:
            st.info("Aún no hay administradores institucionales acreditados en el sistema.")
        else:
            df_act = pd.DataFrame(active_admins)
            st.dataframe(
                df_act[["name", "orcid", "institution", "dependency", "email", "approved_at", "approved_by"]],
                column_config={
                    "name": "Nombre",
                    "orcid": "ORCID iD",
                    "institution": "Institución Asignada",
                    "dependency": "Cargo",
                    "email": "Correo Institucional",
                    "approved_at": "Fecha de Aprobación",
                    "approved_by": "Aprobado por"
                },
                use_container_width=True,
                hide_index=True
            )

    # ── TAB 3: CATÁLOGO DE ALIAS INSTITUCIONALES ──
    with tab_aliases:
        st.write("#### 🏷️ Normalización y Variantes de Nombres Institucionales")
        st.caption(
            "Registra alias o variantes tipográficas de instituciones (ej. 'Fac. de Ciencias UNAM' ➔ 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO') "
            "para garantizar que las consultas bibliométricas agreguen correctamente toda la producción."
        )

        with st.form("form_add_inst_alias"):
            c_al1, c_al2 = st.columns(2)
            with c_al1:
                can_name = st.text_input("Nombre Canónico Oficial:", placeholder="Ej: UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)")
            with c_al2:
                alias_name = st.text_input("Alias o Variante:", placeholder="Ej: UNAM - Facultad de Ciencias")

            submit_alias = st.form_submit_button("Guardar Alias Institucional")
            if submit_alias:
                if not can_name or not alias_name:
                    st.error("Por favor ingresa tanto el nombre canónico como el alias.")
                else:
                    ok = curation.add_institutional_alias(can_name, alias_name, created_by=admin_orcid)
                    if ok:
                        st.success("Alias registrado correctamente.")
                        st.rerun()
                    else:
                        st.warning("Este alias ya se encuentra registrado.")

        st.markdown("---")
        aliases = curation.get_institutional_aliases()
        if aliases:
            st.write(f"**Alias Registrados ({len(aliases)}):**")
            df_alias = pd.DataFrame(aliases)
            st.dataframe(
                df_alias[["canonical_entity", "alias", "created_by", "created_at"]],
                column_config={
                    "canonical_entity": "Institución Canónica",
                    "alias": "Variante / Alias",
                    "created_by": "Registrado por",
                    "created_at": "Fecha"
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No hay alias institucionales registrados aún.")
