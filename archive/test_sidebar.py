import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(initial_sidebar_state="collapsed")

with st.sidebar:
    st.write("This is the sidebar")

tab1, tab2 = st.tabs(["Inicio", "Otra pestaña"])

with tab1:
    st.write("Estoy en inicio. La barra debe estar oculta.")

with tab2:
    st.write("Estoy en otra. La barra debe aparecer.")

components.html("""
<script>
    const parentDoc = window.parent.document;
    parentDoc.addEventListener('click', function(e) {
        let tab = e.target.closest('button[role="tab"]');
        if (tab) {
            let tabText = tab.innerText;
            let sidebar = parentDoc.querySelector('[data-testid="stSidebar"]');
            let isExpanded = sidebar ? sidebar.getAttribute('aria-expanded') === 'true' : false;
            let btn = parentDoc.querySelector('[data-testid="collapsedControl"]');
            
            if (tabText.includes("Inicio") && isExpanded) {
                btn.click();
            } else if (!tabText.includes("Inicio") && !isExpanded) {
                btn.click();
            }
        }
    });
</script>
""", height=0)
