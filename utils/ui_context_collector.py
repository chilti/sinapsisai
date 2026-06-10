import streamlit as st

def get_current_ui_context():
    """Recopila el estado de la UI (entidad seleccionada y selecciones de gráficas) en un string."""
    context = []
    
    # Entidad Seleccionada (Globales de la barra lateral de dashboard_v2)
    inst = st.session_state.get('selected_institution_sidebar', '')
    dep = st.session_state.get('selected_dep_sidebar', '')
    sub = st.session_state.get('selected_sub_sidebar', '')
    
    context.append(f"El usuario está navegando en el Dashboard. La entidad seleccionada actualmente es: Institución: {inst}, Dependencia: {dep}, Subdependencia: {sub}.")
    
    # Interacciones con gráficas (Plotly on_select state)
    interactions = []
    
    docs_sel = st.session_state.get("inst_annual_docs", {}) or st.session_state.get("inv_annual_docs", {})
    if docs_sel and docs_sel.get("selection", {}).get("points"):
        points = docs_sel["selection"]["points"]
        years = [p.get("x") for p in points if "x" in p]
        if years:
            interactions.append(f"- Hizo clic en la gráfica de 'Documentos Publicados por Año' en los años: {years}.")

    fwci_sel = st.session_state.get("inst_annual_fwci", {})
    if fwci_sel and fwci_sel.get("selection", {}).get("points"):
        points = fwci_sel["selection"]["points"]
        years = [p.get("x") for p in points if "x" in p]
        if years:
            interactions.append(f"- Hizo clic en la gráfica de 'Evolución FWCI' en los años: {years}.")
            
    sunburst_sel = st.session_state.get("inst_sunburst", {}) or st.session_state.get("inv_sunburst", {})
    if sunburst_sel and sunburst_sel.get("selection", {}).get("points"):
        points = sunburst_sel["selection"]["points"]
        topics = [p.get("id") or p.get("label") for p in points]
        if topics:
            interactions.append(f"- Hizo clic en la gráfica 'Sunburst (Temáticas)' en los temas: {topics}.")

    if interactions:
        context.append("Interacciones recientes del usuario en las gráficas:")
        context.extend(interactions)
    else:
        context.append("El usuario no tiene ninguna gráfica seleccionada en este momento.")
        
    return "\n".join(context)
