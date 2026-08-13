import time
import streamlit as st
import pandas as pd

def render_explain_button(context_name: str, key_suffix: str, context_data=None):
    """
    Renderiza un botón 💡 (Ilumíname).
    Al presionarlo, guarda el nombre y los datos (si los hay) en session_state y relanza la app
    para abrir el diálogo modal de explicación. Incluye protección de Cooldown (3s).
    """
    if st.button("💡", help=f"¡Ilumíname sobre: {context_name}!", key=f"btn_explain_{key_suffix}", type="tertiary"):
        now = time.time()
        last_click = st.session_state.get("last_bulb_click_time", 0)
        
        # Protección Cooldown de 3 segundos contra clics repetitivos
        if now - last_click < 3:
            st.toast("⏳ Por favor espera un momento antes de solicitar otro análisis.", icon="⚠️")
            return
            
        st.session_state.last_bulb_click_time = now
        st.session_state.trigger_explain_chart = context_name
        
        # Formatear dataframes a markdown para no colapsar tokens
        if isinstance(context_data, pd.DataFrame):
            # Limitar a las primeras 30 filas para no exceder tokens y usar csv
            st.session_state.trigger_explain_data = context_data.head(30).to_csv(index=False)
        else:
            st.session_state.trigger_explain_data = str(context_data) if context_data is not None else None
            
        st.rerun()
