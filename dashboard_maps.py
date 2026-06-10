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
                "📄 Artículos (Semántica - Qdrant)",
                "📄 Artículos (Semántica - Nomic)", 
                "📄 Artículos (Semántica - SPECTER2)", 
                "🧑‍🤝‍🧑 Académicos (Semántica SPECTER2)",
                "🧑‍🤝‍🧑 Personas (Estructura Social)", 
                "🧑‍🤝‍🧑 Personas (Estructura + Temas + ODS)",
                "📊 Personas (Desempeño)",
                "🕸️ Red de Coautoría (WebGL - Comunidad/PageRank)",
                "🕸️ Red Institucional (WebGL - Louvain)",
                "🕸️ Red Bipartita Autor-Tema/ODS (WebGL)"
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

    # ── Descripciones de cada mapa ────────────────────────────────────────
    MAP_DESCRIPTIONS = {
        "📄 Artículos (Semántica - Qdrant)": {
            "emoji": "📄",
            "title": "Mapa de Artículos — Semántica (Qdrant / Legacy)",
            "desc": (
                "Visualización del corpus de artículos académicos de investigadores mexicanos "
                "proyectados en 2D según su similitud semántica de contenido, usando embeddings "
                "almacenados en la base vectorial <strong>Qdrant</strong> (versión heredada). "
                "Los artículos con temáticas afines aparecen agrupados en regiones contiguas del mapa."
            ),
            "tech": "Embeddings locales → UMAP coseno → WebGL",
            "uses": [
                "Exploración libre del corpus nacional de publicaciones.",
                "Identificar grupos temáticos emergentes sin búsqueda previa.",
                "Comparar la distribución geográfica del mapa con versiones más recientes (Nomic/SPECTER2).",
            ],
        },
        "📄 Artículos (Semántica - Nomic)": {
            "emoji": "🔬",
            "title": "Mapa de Artículos — Semántica Nomic",
            "desc": (
                "Cerca de un millón de artículos académicos proyectados en un plano 2D según su "
                "<strong>similitud semántica de contenido</strong> (embeddings Nomic de 768 dimensiones). "
                "Los artículos de temáticas parecidas aparecen en el mismo 'continente' del mapa; "
                "cada región lleva una etiqueta temática generada automáticamente por IA "
                "(p. ej. <em>Oncología Molecular</em>, <em>Educación Matemática</em>)."
            ),
            "tech": "Nomic 768d → UMAP coseno → HDBSCAN + LLM etiquetas → WebGL",
            "uses": [
                "Identificar vacíos de conocimiento en la ciencia mexicana para orientar convocatorias.",
                "Descubrir intersecciones temáticas entre departamentos para investigación interdisciplinaria.",
                "Localizar investigadores activos en enfermedades o tecnologías estratégicas.",
                "Contextualizar la línea de investigación de un académico dentro del mapa nacional.",
            ],
        },
        "📄 Artículos (Semántica - SPECTER2)": {
            "emoji": "🔭",
            "title": "Mapa de Artículos — Semántica SPECTER2",
            "desc": (
                "El mismo corpus de artículos pero proyectado con embeddings <strong>SPECTER2</strong> (Allen Institute for AI), "
                "un modelo pre-entrenado específicamente en literatura científica. "
                "Aquí la proximidad enfatiza la <strong>similitud disciplinar y metodológica</strong>: artículos que comparten "
                "enfoque experimental o computacional quedan juntos aunque usen vocabulario diferente."
            ),
            "tech": "SPECTER2 768d → UMAP coseno → HDBSCAN + LLM etiquetas → WebGL",
            "uses": [
                "Detectar grupos con metodologías compartidas entre disciplinas aparentemente distintas.",
                "Evaluar si proyectos financiados en áreas diversas comparten base técnica común.",
                "Identificar afinidades metodológicas entre cuerpos académicos de distintas IES.",
                "Comparar el perfil metodológico de la ciencia mexicana con otros países de la región.",
            ],
        },
        "🧑‍🤝‍🧑 Académicos (Semántica SPECTER2)": {
            "emoji": "🎓",
            "title": "Mapa de Investigadores — Perfil Semántico (SPECTER2)",
            "desc": (
                "Investigadores posicionados según el <strong>centroide semántico de toda su obra publicada</strong>, "
                "calculado con SPECTER2. A diferencia del mapa de red, aquí la posición refleja "
                "<em>qué investiga</em> el académico —no <em>con quién colabora</em>—. "
                "Dos investigadores de instituciones distintas que publican sobre temas similares quedan cerca."
            ),
            "tech": "Perfil SPECTER2 por académico → UMAP coseno → WebGL",
            "uses": [
                "Identificar investigadores con líneas afines para consolidar cuerpos académicos virtuales.",
                "Vincular necesidades tecnológicas de empresas con el investigador más pertinente.",
                "Reclutar sinodales o directores de tesis por afinidad semántica real, no por departamento.",
                "Preseleccionar evaluadores de proyectos alineados genuinamente con el área convocada.",
            ],
        },
        "🧑‍🤝‍🧑 Personas (Estructura Social)": {
            "emoji": "🕸️",
            "title": "Mapa de Investigadores — Red Estructural (FastRP)",
            "desc": (
                "Investigadores posicionados según su <strong>lugar dentro de la red de coautoría y filiación institucional</strong>, "
                "calculado mediante <strong>FastRP</strong> sobre el grafo de Neo4j (nodos: Person, Institution, Paper; "
                "relaciones: AUTHOR_OF, AFFILIATED_TO). "
                "Investigadores con colaboradores o instituciones comunes aparecen cerca. "
                "Revela la <em>estructura social</em> de la ciencia mexicana: comunidades, brokers y nodos aislados."
            ),
            "tech": "Neo4j GDS FastRP 128d → UMAP coseno → WebGL",
            "uses": [
                "Identificar investigadores puente (brokers) entre comunidades científicas.",
                "Detectar académicos aislados estructuralmente para diseñar políticas de mentoría.",
                "Visualizar el peso relativo de universidades estatales dentro de la red nacional.",
                "Priorizar becas de movilidad para investigadores en la periferia de la red internacional.",
            ],
        },
        "🧑‍🤝‍🧑 Personas (Estructura + Temas + ODS)": {
            "emoji": "🌍",
            "title": "Mapa de Investigadores — Perfil Temático y ODS",
            "desc": (
                "Investigadores posicionados según su <strong>perfil temático y contribución a los Objetivos de Desarrollo Sostenible (ODS)</strong>. "
                "El grafo de Neo4j incluye nodos Topic y SDG con relaciones HAS_TOPIC y CONTRIBUTES_TO. "
                "FastRP con este grafo ampliado produce embeddings que mezclan estructura de red con orientación temática. "
                "Responde: <em>¿quién investiga qué, y en qué ODS impacta?</em>"
            ),
            "tech": "Neo4j GDS FastRP (Person + Topic + SDG) → UMAP coseno → WebGL",
            "uses": [
                "Identificar investigadores que contribuyen a cada ODS para reportes ante la ONU.",
                "Localizar expertos en ODS 13 (Clima), 3 (Salud) o 2 (Hambre Cero) para consejos técnicos.",
                "Alinear la investigación regional con cadenas de valor productivas locales.",
                "Establecer alianzas de investigación-acción con OSC en ODS sociales.",
            ],
        },
        "📊 Personas (Desempeño)": {
            "emoji": "📊",
            "title": "Mapa de Desempeño Institucional",
            "desc": (
                "Investigadores agrupados según un <strong>vector de métricas bibliométricas de impacto</strong>: "
                "<code>pct_top_10</code> (% artículos en el top 10% de revistas más citadas), "
                "<code>fwci_avg</code> (Field-Weighted Citation Impact), "
                "<code>pct_1</code> (% artículos en el 1% más citado globalmente) y "
                "<code>percentile_avg</code> (percentil de citación promedio). "
                "Los investigadores con perfiles similares quedan cerca, independientemente de su temática o institución."
            ),
            "tech": "Vector 4D de métricas → UMAP euclidiano → WebGL",
            "uses": [
                "Comparar el perfil de impacto de candidatos al SNII con una visión multidimensional.",
                "Detectar investigadores de alto impacto sin apoyos suficientes para retención de talento.",
                "Demostrar masa crítica de alto impacto en procesos de acreditación (CIEES, COPAES).",
                "Comparar el perfil de investigadores estatales con el promedio nacional para políticas de atracción.",
            ],
        },
        "🕸️ Red de Coautoría (WebGL - Comunidad/PageRank)": {
            "emoji": "🕸️",
            "title": "Red de Coautoría — Comunidades y PageRank",
            "desc": (
                "Grafo interactivo de colaboración científica entre investigadores mexicanos. "
                "Los nodos representan académicos y las aristas indican coautorías. "
                "El color identifica <strong>comunidades de colaboración</strong> (Louvain/Leiden) y "
                "el tamaño del nodo refleja su <strong>PageRank</strong> (influencia estructural en la red)."
            ),
            "tech": "Neo4j → WebGL (sigma.js/force-directed) → comunidades Louvain",
            "uses": [
                "Visualizar clústeres de colaboración y detectar comunidades científicas consolidadas.",
                "Identificar investigadores con alta influencia (PageRank alto) para articulación de redes.",
                "Detectar nodos puente entre comunidades disciplinarias o institucionales.",
                "Analizar la evolución de la colaboración nacional a lo largo del tiempo.",
            ],
        },
        "🕸️ Red Institucional (WebGL - Louvain)": {
            "emoji": "🏛️",
            "title": "Red Institucional — Comunidades Louvain",
            "desc": (
                "Grafo de colaboración a <strong>nivel institucional</strong>: cada nodo es una institución y "
                "cada arista refleja coautorías agregadas entre sus investigadores. "
                "El algoritmo <strong>Louvain</strong> detecta comunidades de instituciones que colaboran frecuentemente entre sí."
            ),
            "tech": "Coautorías agregadas por institución → Louvain → WebGL",
            "uses": [
                "Identificar clusters de IES con alta colaboración para proponer redes formales de investigación.",
                "Visualizar el posicionamiento de una universidad dentro del ecosistema científico nacional.",
                "Detectar instituciones periféricas con periférica integración a redes más grandes.",
                "Diseñar políticas de fomento a la colaboración interinstitucional basadas en evidencia.",
            ],
        },
        "🕸️ Red Bipartita Autor-Tema/ODS (WebGL)": {
            "emoji": "🌐",
            "title": "Red Bipartita Autor–Tema/ODS",
            "desc": (
                "Red bipartita que conecta <strong>investigadores</strong> con los <strong>temas de OpenAlex</strong> y <strong>ODS</strong> "
                "a los que contribuyen sus publicaciones. "
                "Permite ver en un solo grafo quién trabaja en qué tema y cómo los temas y los ODS se relacionan "
                "a través de los investigadores que los comparten."
            ),
            "tech": "Relaciones HAS_TOPIC + CONTRIBUTES_TO de Neo4j → WebGL bipartito",
            "uses": [
                "Identificar qué investigadores son centrales para un tema o ODS específico.",
                "Descubrir temas 'puente' que conectan ODS distintos a través de investigadores compartidos.",
                "Apoyar la construcción de equipos multidisciplinarios orientados a un ODS concreto.",
                "Generar reportes de alineación de la investigación nacional con la Agenda 2030.",
            ],
        },
    }

    # ── Mostrar descripción del mapa seleccionado ─────────────────────────
    if map_type in MAP_DESCRIPTIONS:
        info = MAP_DESCRIPTIONS[map_type]
        uses_html = "".join(f"<li style='margin:2px 0;'>{u}</li>" for u in info["uses"])
        st.markdown(
            f"""
<div style="
    background: linear-gradient(135deg, #0f2027, #1a3a5c);
    border-left: 4px solid #D4AF37;
    border-radius: 8px;
    padding: 16px 20px;
    margin: 8px 0 12px 0;
    color: #f0f4f8;
    font-size: 0.92rem;
    line-height: 1.6;
">
    <div style="font-size:1.05rem; font-weight:700; color:#D4AF37; margin-bottom:6px;">
        {info['emoji']} {info['title']}
    </div>
    <div style="margin-bottom:8px;">{info['desc']}</div>
    <div style="font-size:0.82rem; color:#a0b4c8; margin-bottom:8px;">
        <strong style="color:#7ecfff;">⚙️ Tecnología:</strong> {info['tech']}
    </div>
    <div style="font-size:0.88rem;">
        <strong style="color:#7ecfff;">💡 Casos de uso principales:</strong>
        <ul style="margin:4px 0 0 0; padding-left:18px;">{uses_html}</ul>
    </div>
</div>
""",
            unsafe_allow_html=True,
        )

    # ── Mapa a ancho completo debajo de los controles ──
    if st.session_state.get("load_map", False):
        data_urls = {
            "📄 Artículos (Semántica - Qdrant)": "https://dinamica1.fciencias.unam.mx/tiles/articles_data.json",
            "📄 Artículos (Semántica - Nomic)": "https://dinamica1.fciencias.unam.mx/tiles/articles_nomic_data.json",
            "📄 Artículos (Semántica - SPECTER2)": "https://dinamica1.fciencias.unam.mx/tiles/articles_specter_data.json",
            "🧑‍🤝‍🧑 Académicos (Semántica SPECTER2)": "https://dinamica1.fciencias.unam.mx/tiles/people_semantic_data.json",
            "🧑‍🤝‍🧑 Personas (Estructura Social)": "https://dinamica1.fciencias.unam.mx/tiles/people_data.json",
            "🧑‍🤝‍🧑 Personas (Estructura + Temas + ODS)": "https://dinamica1.fciencias.unam.mx/tiles/people_topics_data.json",
            "📊 Personas (Desempeño)": "https://dinamica1.fciencias.unam.mx/tiles/performance_data.json",
            "🕸️ Red de Coautoría (WebGL - Comunidad/PageRank)": "https://dinamica1.fciencias.unam.mx/tiles/network_coauthorship_data.json",
            "🕸️ Red Institucional (WebGL - Louvain)": "https://dinamica1.fciencias.unam.mx/tiles/network_institutional_data.json",
            "🕸️ Red Bipartita Autor-Tema/ODS (WebGL)": "https://dinamica1.fciencias.unam.mx/tiles/network_bipartite_data.json"
        }
        url = data_urls[map_type]
        
        # Agregar parámetro de color por comunidad para visualizaciones de red
        color_by_param = ""
        if "network_" in url:
            color_by_param = "&color_by=cluster"
            
        iframe_src = f"https://dinamica1.fciencias.unam.mx/tiles/map_test.html?v=28&data={url}?v=28{color_by_param}"

        
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
                components.html(map_html, height=1080, scrolling=False)
                
        except Exception as e:
            st.error(f"Error al cargar el componente Deepscatter: {e}")