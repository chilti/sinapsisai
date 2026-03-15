import streamlit as st
import json
import os
import pandas as pd
from datetime import datetime

# Configuración de página
st.set_page_config(page_title="Validador SNII-ORCID", layout="wide", page_icon="🧬")

# Paths
MATCHED_PATH = "../data/authors_matched_orcid.json"
VALIDATED_PATH = "../data/authors_validated_orcid.json"

def load_data():
    if not os.path.exists(MATCHED_PATH):
        return []
    with open(MATCHED_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_validated():
    if not os.path.exists(VALIDATED_PATH):
        return {}
    with open(VALIDATED_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_validated(validated_dict):
    with open(VALIDATED_PATH, 'w', encoding='utf-8') as f:
        json.dump(validated_dict, f, ensure_ascii=False, indent=2)

# --- UI ---
st.title("🧬 Validador de Identidad Académica (SNII-ORCID)")
st.markdown("""
Esta herramienta permite validar manualmente los emparejamientos realizados por el algoritmo estricto. 
Los datos provienen de **SNII 2025** y el **Seed de Neo4j**, cruzados contra un dump de **ORCID** en ClickHouse.
""")

data = load_data()
validated = load_validated()

if not data:
    st.warning("No se encontraron datos emparejados. Por favor, ejecuta primero el script `match_snii_orcid.py`.")
    st.stop()

# Filtros en el sidebar
st.sidebar.header("Filtros")
min_score = st.sidebar.slider("Score mínimo a mostrar", 0.0, 1.0, 0.90)
show_already_validated = st.sidebar.checkbox("Mostrar ya validados", value=False)

# Filtrar datos
filtered_data = [d for d in data if d['score'] >= min_score]
if not show_already_validated:
    filtered_data = [d for d in filtered_data if d['source_name'] not in validated]

st.sidebar.metric("Total candidatos", len(data))
st.sidebar.metric("Por validar", len(filtered_data))

if not filtered_data:
    st.success("¡Todo validado o no hay candidatos con ese score!")
else:
    # Mostrar por páginas o uno por uno
    idx = st.session_state.get('current_idx', 0)
    if idx >= len(filtered_data):
        idx = 0
        st.session_state.current_idx = 0
    
    item = filtered_data[idx]
    
    st.divider()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📍 Datos de Origen")
        st.info(f"**Nombre:** {item['source_name']}")
        st.write(f"**Origen:** `{item['source_origin']}`")
        st.write(f"**Afiliación:** {item.get('source_aff', 'No disponible')}")
        
    with col2:
        st.subheader("🔍 Candidato ORCID")
        color = "green" if item['score'] >= 0.95 else "orange"
        st.markdown(f"**Nombre:** {item['matched_name']}")
        st.markdown(f"**ORCID:** [{item['matched_orcid']}](https://orcid.org/{item['matched_orcid']})")
        st.markdown(f"**Score:** :{color}[{item['score']}] (`{item.get('match_type', 'N/A')}`)")
        st.write(f"**Email:** `{item.get('matched_emails', 'No encontrado')}`")
        st.write(f"**Institución:** {item.get('matched_institution', 'N/A')}")
        st.write(f"**Sub-afiliación:** `{item.get('sub_affiliation', 'No detectada')}`")
        st.write(f"**País:** {item.get('matched_country', 'N/A')} ({item.get('matched_city', '')})")

    st.subheader("📚 Actividad Reciente (Últimos 3 años)")
    dois = item.get('dois_last_3yr', [])
    if dois:
        df_dois = pd.DataFrame(dois)
        st.table(df_dois[['year', 'doi', 'title']])
    else:
        st.warning("No se encontraron publicaciones recientes en OpenAlex para este ORCID.")

    # Botones de acción
    c1, c2, c3, c4 = st.columns(4)
    
    def validate_action(status):
        validated[item['source_name']] = {
            "orcid": item['matched_orcid'],
            "status": status,
            "validated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "score": item['score']
        }
        save_validated(validated)
        st.session_state.current_idx = st.session_state.get('current_idx', 0) + 1
        st.toast(f"Investigador {status}: {item['source_name']}")

    if c1.button("✅ Aprobar", use_container_width=True, type="primary"):
        validate_action("APPROVED")
        st.rerun()
        
    if c2.button("❌ Rechazar", use_container_width=True):
        validate_action("REJECTED")
        st.rerun()
        
    if c3.button("❓ Dudoso", use_container_width=True):
        validate_action("DOUBTFUL")
        st.rerun()
        
    if c4.button("⏭️ Omitir", use_container_width=True):
        st.session_state.current_idx = st.session_state.get('current_idx', 0) + 1
        st.rerun()

    st.progress((idx + 1) / len(filtered_data))
    st.write(f"Registro {idx + 1} de {len(filtered_data)}")

# Mostrar estadísticas de validación al final del sidebar
if validated:
    st.sidebar.divider()
    st.sidebar.subheader("Estadísticas de Validación")
    df_val = pd.DataFrame.from_dict(validated, orient='index')
    st.sidebar.write(df_val['status'].value_counts())
