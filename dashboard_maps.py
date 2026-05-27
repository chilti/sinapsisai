import streamlit as st
import streamlit.components.v1 as components
import os

def render_maps_view():
     # ── Fila superior: Configuración (col izq) + Botones (col der) ──
    col_config, col_actions = st.columns([3, 1])
    
    with col_config:
        map_type = st.radio(
            "Selecciona la Capa:",
            [
                "📄 Artículos (Semántica - Nomic)", 
                "📄 Artículos (Semántica - SPECTER2)", 
                "🧑‍🤝‍🧑 Académicos (Semántica SPECTER2)",
                "🧑‍🤝‍🧑 Personas (Estructura Social)", 
                "🧑‍🤝‍🧑 Personas (Estructura + Temas + ODS)",
                "📊 Personas (Desempeño)"
            ],
            horizontal=True
        )
    
    with col_actions:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Cargar Mapa", type="primary", use_container_width=True):
                st.session_state.load_map = True
        with c2:
            if st.button("Ocultar Mapa", use_container_width=True):
                st.session_state.load_map = False

    # ── Mapa a ancho completo debajo de los controles ──
    if st.session_state.get("load_map", False):
        data_urls = {
            "📄 Artículos (Semántica - Nomic)": "https://dinamica1.fciencias.unam.mx/tiles/articles_nomic_data.json",
            "📄 Artículos (Semántica - SPECTER2)": "https://dinamica1.fciencias.unam.mx/tiles/articles_specter_data.json",
            "🧑‍🤝‍🧑 Académicos (Semántica SPECTER2)": "https://dinamica1.fciencias.unam.mx/tiles/people_semantic_data.json",
            "🧑‍🤝‍🧑 Personas (Estructura Social)": "https://dinamica1.fciencias.unam.mx/tiles/people_data.json",
            "🧑‍🤝‍🧑 Personas (Estructura + Temas + ODS)": "https://dinamica1.fciencias.unam.mx/tiles/people_topics_data.json",
            "📊 Personas (Desempeño)": "https://dinamica1.fciencias.unam.mx/tiles/performance_data.json"
        }
        url = data_urls[map_type]
        iframe_src = f"https://dinamica1.fciencias.unam.mx/tiles/map_test.html?v=13&data={url}"

        
        try:
            with st.spinner(f"Cargando {map_type}..."):
                map_html = f"""
                <div id="map-container-explore" style="width:100%; overflow:hidden;">
                    <iframe id="map-iframe-explore" src="{iframe_src}" 
                            style="width:100%; border:none; display:block;" 
                            scrolling="no">
                    </iframe>
                </div>
                <script>
                    function resizeExploreMap() {{
                        var iframe = document.getElementById('map-iframe-explore');
                        var container = document.getElementById('map-container-explore');
                        var rect = container.getBoundingClientRect();
                        var availableHeight = window.innerHeight - rect.top - 10;
                        if (availableHeight < 400) availableHeight = 400;
                        iframe.style.height = availableHeight + 'px';
                    }}
                    resizeExploreMap();
                    window.addEventListener('resize', resizeExploreMap);
                    setTimeout(resizeExploreMap, 300);
                    setTimeout(resizeExploreMap, 1000);
                </script>
                """
                components.html(map_html, height=900, scrolling=False)
                
        except Exception as e:
            st.error(f"Error al cargar el componente Deepscatter: {e}")