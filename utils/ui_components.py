import streamlit as st
import pandas as pd

def render_explain_button(context_name: str, key_suffix: str, context_data=None):
    """
    Renderiza un botón 💡 (Ilumíname).
    Al presionarlo, guarda el nombre y los datos (si los hay) en session_state y relanza la app
    para abrir el diálogo modal de explicación.
    
    Args:
        context_name (str): Nombre legible del elemento (ej. "Producción Histórica").
        key_suffix (str): Sufijo único para el key del botón (ej. "inst_docs").
        context_data (any, optional): Datos en crudo (DataFrame, lista, int) a inyectar al LLM.
    """
    if st.button("💡", help=f"¡Ilumíname sobre: {context_name}!", key=f"btn_explain_{key_suffix}", type="tertiary"):
        st.session_state.trigger_explain_chart = context_name
        
        # Formatear dataframes a markdown para no colapsar tokens
        if isinstance(context_data, pd.DataFrame):
            # Limitar a las primeras 30 filas para no exceder tokens y usar csv para no requerir tabulate
            st.session_state.trigger_explain_data = context_data.head(30).to_csv(index=False)
        else:
            st.session_state.trigger_explain_data = str(context_data) if context_data is not None else None
            
        st.rerun()
