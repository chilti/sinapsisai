import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime

# Configuración de página
st.set_page_config(page_title="Auditoría SNII-ORCID", layout="wide", page_icon="🛡️")

# Paths
MATCHED_PATH = "../data/snii_llm_verified_matches.json"

def load_data():
    if not os.path.exists(MATCHED_PATH):
        return []
    with open(MATCHED_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

# --- UI ---
st.title("🛡️ Panel de Auditoría / Validación SNII-ORCID")
st.markdown("""
Esta interfaz permite supervisar los resultados de la **Búsqueda Vectorial** y el **Challenge de Auditoría**.
Los datos incluyen a los investigadores del SNII 2025 y sus perfiles de ORCID validados por IA.
""")

data = load_data()

if not data:
    st.warning(f"No se encontró el archivo de resultados en `{MATCHED_PATH}`. Por favor, ejecuta primero `vectorize_researchers.py`.")
    st.stop()

# --- Filtros en el sidebar ---
st.sidebar.header("🕹️ Filtros de Auditoría")

# Estadísticas rápidas
total_matches = sum(1 for d in data if d.get('match'))
total_audited = sum(1 for d in data if d.get('audit'))

st.sidebar.metric("Candidatos Identificados", total_matches)
st.sidebar.metric("Auditorías Completadas", total_audited)

filter_match = st.sidebar.radio("Mostrar:", ["Todos", "Solo Matches (ORCID hallado)", "Sin Match"], index=1)
filter_audit = st.sidebar.selectbox("Filtro por Veredicto:", 
    ["Todos", "CONFIRMED", "DOUBTFUL", "FALSE_POSITIVE", "Sin Auditoría"]
)

# Aplicar filtros
filtered_data = data
if filter_match == "Solo Matches (ORCID hallado)":
    filtered_data = [d for d in filtered_data if d.get('match')]
elif filter_match == "Sin Match":
    filtered_data = [d for d in filtered_data if not d.get('match')]

if filter_audit != "Todos":
    if filter_audit == "Sin Auditoría":
        filtered_data = [d for d in filtered_data if not d.get('audit')]
    else:
        filtered_data = [d for d in filtered_data if d.get('audit') and d['audit']['verdict'] == filter_audit]

# Buscador por nombre
search_name = st.sidebar.text_input("🔍 Buscar por nombre:", "")
if search_name:
    filtered_data = [d for d in filtered_data if search_name.lower() in d['snii_author'].lower()]

st.sidebar.divider()
st.sidebar.info(f"Mostrando **{len(filtered_data)}** registros de los {len(data)} totales.")

if not filtered_data:
    st.info("No hay registros que coincidan con los filtros seleccionated.")
else:
    # Navegación
    if 'curr_idx' not in st.session_state:
        st.session_state.curr_idx = 0
    
    # Ajustar índice si el filtro reduce la lista
    if st.session_state.curr_idx >= len(filtered_data):
        st.session_state.curr_idx = 0

    # Botones de navegación arriba
    col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
    if col_nav1.button("⬅️ Anterior"):
        st.session_state.curr_idx = max(0, st.session_state.curr_idx - 1)
        st.rerun()
    if col_nav3.button("Siguiente ➡️"):
        st.session_state.curr_idx = min(len(filtered_data) - 1, st.session_state.curr_idx + 1)
        st.rerun()

    item = filtered_data[st.session_state.curr_idx]
    
    st.divider()
    
    # Renderizado de Ficha
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📍 Datos de SNII")
        st.write(f"**Nombre:** `{item['snii_author']}`")
        st.write(f"**Institución:** {item.get('snii_institution', 'N/A')}")
        st.write(f"**Subdependencia:** {item.get('snii_subdependency', 'N/A')}")
        
    with col2:
        st.subheader("🔗 Identidad Hallada")
        if item.get('match'):
            st.success(f"**Nombre Match:** {item.get('matched_author', 'Verificado por LLM')}")
            st.write(f"**ORCID:** [{item['matched_orcid']}](https://orcid.org/{item['matched_orcid']})")
            st.write(f"**Fuente Original:** `{item.get('source', 'N/A')}`")
        else:
            st.error("❌ No se encontró coincidencia clara.")
            st.write(f"**Razón del LLM:** {item.get('reason', 'N/A')}")

    # Bloque de Auditoría (EL CHALLENGE)
    st.divider()
    if item.get('audit'):
        aud = item['audit']
        v = aud['verdict']
        if v == "CONFIRMED":
            st.success(f"### ✅ Auditoría: {v} ({aud['confidence']}%)")
        elif v == "DOUBTFUL":
            st.warning(f"### ❓ Auditoría: {v} ({aud['confidence']}%)")
        else:
            st.error(f"### 💀 Auditoría: {v} ({aud['confidence']}%)")
        
        st.write(f"**Análisis del Auditor IA:**")
        st.info(aud['reason'])
        st.caption(f"Auditado el: {aud.get('timestamp', 'N/A')}")
    else:
        st.info("🕒 Este registro aún no ha sido procesado por el script de Auditoría (Challenge).")

    # Tabla de resumen si se desea ver el contexto
    st.divider()
    with st.expander("Ver lista completa filtrada (Tabla)"):
        df_view = pd.DataFrame(filtered_data)
        st.dataframe(df_view, use_container_width=True)

    st.progress((st.session_state.curr_idx + 1) / len(filtered_data))
    st.write(f"Registro **{st.session_state.curr_idx + 1}** de **{len(filtered_data)}**")
