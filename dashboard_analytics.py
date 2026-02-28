import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import sys
import json
import numpy as np
import viz_ods  # Nuevo módulo para pintar la matriz de ODS

# Paths
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_PATH, 'data', 'cache')

@st.cache_data
def load_cached_data(filename):
    path = os.path.join(CACHE_DIR, filename)
    if os.path.exists(path):
        return pd.read_parquet(path)
    return None

def cargar_lista_academicos(ruta_json="ingestion/profesores_Instituto_de_Ciencias_Nucleares.json"):
    path = os.path.join(BASE_PATH, ruta_json)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def mostrar_banners_destacados(df):
    st.subheader("Publicaciones Destacadas")
    
    if df.empty:
        st.info("Sin publicaciones para mostrar.")
        return

    # Preparamos los datos
    df_sorted_citas = df.sort_values(by="citations", ascending=False).head(10)
    df_sorted_recientes = df.sort_values(by="year", ascending=False).head(10)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🔥 Artículos Más Citados")
        for _, row in df_sorted_citas.iterrows():
            Title = f"[{row['Title']}]({row['DOI']})" if row['DOI'] else row['Title']
            st.markdown(f"**{int(row['citations'])} citas** - {Title} ({int(row['year']) if pd.notna(row['year']) else 'N/A'})")

    with col2:
        st.markdown("#### 🚀 Artículos Más Recientes")
        for _, row in df_sorted_recientes.iterrows():
            Title = f"[{row['Title']}]({row['DOI']})" if row['DOI'] else row['Title']
            st.markdown(f"**{int(row['year']) if pd.notna(row['year']) else 'N/A'}** - {Title}")

def render_institucion_view(entity_name):
    st.header(f"🏢 Vista de la Institución: {entity_name}")
    st.markdown(f"Panorama Analítico de la Producción de **{entity_name}**. La producción de la institución fué descargada desde Web of Sciencei. Los indicaddores fueron ectraidos de la base de datos abierta OpenAlex.")

    df_annual = load_cached_data("institucion_annual.parquet")
    df_total = load_cached_data("institucion_total.parquet")
    df_topics = load_cached_data("topics_institucion.parquet")

    if df_total is not None and not df_total.empty:
        df_total = df_total[df_total['entity_name'] == entity_name]
        if df_total.empty:
            st.warning(f"No hay métricas institucionales pre-calculadas para {entity_name}.")
            return
            
        total = df_total.iloc[0]
        # KPIs (Fila 1)
        st.markdown("##### Métricas Generales")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Doc. Totales", f"{int(total.get('num_documents',0)):,}")
        c2.metric("Citas Acumuladas", f"{int(total.get('citations',0)):,}")
        c3.metric("FWCI Promedio", f"{total.get('fwci_avg',0):.2f}")
        c4.metric("% Open Access", f"{total.get('pct_open_access',0):.1f}%")
        
        # KPIs (Fila 2)
        st.markdown("##### Métricas de Excelencia")
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Percentil Promedio", f"{total.get('percentile_avg',50):.1f}")
        c6.metric("% Top 10%", f"{total.get('pct_top_10',0):.1f}%")
        c7.metric("% Top 1%", f"{total.get('pct_1',0):.1f}%")
        
        # Glosario Metodológico
        with st.expander("ℹ️ ¿Qué significan estos indicadores?"):
            st.markdown("""
            - **FWCI (Field-Weighted Citation Impact):** Relación entre las citas recibidas y el promedio mundial esperado para el mismo año, disciplina y tipo de documento (Mundial = 1.0).
            - **Percentil Promedio:** Posición promedio global de los artículos respecto a sus citas (donde 99 es el decil de mayor impacto).
            - **% Top 10% / Top 1%:** Porcentaje de la producción científica que se ubica entre el 10% o 1% más citado a nivel mundial en su campo.
            - **% Open Access:** Porcentaje de documentos disponibles en acceso abierto (Vía Dorada, Verde, Híbrida o Bronce).
            """)

    if df_annual is not None and not df_annual.empty:
        df_annual = df_annual[df_annual['entity_name'] == entity_name].sort_values('year')
        if not df_annual.empty:
            st.markdown("---")
            st.subheader("Evolución de Producción e Impacto")
            
            # Ordenamos los anios
            df_annual = df_annual.sort_values('year')

            fig = px.area(df_annual, x='year', y='num_documents', 
                          title="Documentos Publicados por Año",
                          color_discrete_sequence=['#ff7f0e'])
            st.plotly_chart(fig, width="stretch")

            # Gráfico FWCI
            fig_fwci = px.line(df_annual, x='year', y='fwci_avg', markers=True, 
                               title="Evolución FWCI Promedio Institucional")
            fig_fwci.add_hline(y=1.0, line_dash="dash", line_color="red", annotation_text="Base Mundial (1.0)")
            st.plotly_chart(fig_fwci, width="stretch")
        
    if df_topics is not None and not df_topics.empty:
        df_topics = df_topics[df_topics['entity_name'] == entity_name]
        if not df_topics.empty:
            st.markdown("---")
            st.subheader("Temáticas de Investigación Institucional (Sunburst)")
            top_topics = df_topics.sort_values('value', ascending=False).head(100)
            # Adding a root node column for the sunburst path
            top_topics['Institución'] = entity_name
            
            fig_sun = px.sunburst(
                top_topics, 
                path=[ 'domain', 'field', 'subfield', 'topic'], 
                values='value',
                color='value', 
                color_continuous_scale='Blues',
                title="Concentración Temática"
            )
            fig_sun.update_layout(margin=dict(t=50, l=0, r=0, b=10), height=700)
            st.plotly_chart(fig_sun, width="stretch")

    df_institucion_papers = load_cached_data("papers_institucion.parquet")
    if df_institucion_papers is not None and not df_institucion_papers.empty:
        df_inst_p = df_institucion_papers[df_institucion_papers['entity_name'] == entity_name]
        
        st.markdown("---")
        st.header("🌍 Impacto Global Institucional en Sostenibilidad (ODS)")
        st.write("Distribución consolidada de toda la producción científica de la institución respecto a los Objetivos de Desarrollo Sostenible.")
        html_code_inst = viz_ods.render_sdg_matrix(df_inst_p, col_ods='ODS_ID')
        st.markdown(html_code_inst, unsafe_allow_html=True)
        
        st.markdown("---")
        st.subheader("📜 Repositorio de Publicaciones (Institucional)")
        
        col_filtro1, col_filtro2 = st.columns(2)
        with col_filtro1:
            years_inst = np.flip(np.unique(df_inst_p['year'].dropna()))
            s_year_inst = st.selectbox("Filtrar por año:", options=["Todos"] + list(years_inst), key="inst_year")
        with col_filtro2:
            ods_options_inst = sorted([str(ods) for ods in df_inst_p['ODS_Nombre'].dropna().unique() if str(ods).lower() != "null" and "x" not in str(ods).lower()])
            s_ods_inst = st.selectbox("Filtrar por ODS:", options=["Todos"] + ods_options_inst, key="inst_ods")
        
        df_display_inst = df_inst_p.copy()
        if s_year_inst != "Todos":
            df_display_inst = df_display_inst[df_display_inst['year'] == s_year_inst]
        if s_ods_inst != "Todos":
            df_display_inst = df_display_inst[df_display_inst['ODS_Nombre'] == s_ods_inst]
            
        df_display_inst = df_display_inst[[
            "year", "Title", "Source", "citations", "DOI", "ODS_Nombre"
        ]].rename(columns={
            "year": "Año",
            "Title": "Título",
            "Source": "Revista/Publicación",
            "citations": "Citas",
            "DOI": "DOI",
            "ODS_Nombre": "ODS"
        }).sort_values(by="Año", ascending=False)
        
        st.dataframe(df_display_inst, width="stretch", hide_index=True, column_config={"DOI": st.column_config.LinkColumn("Enlace DOI")})

def render_investigador_view(entity_name):
    st.header(f"👤 Vista por Investigador ({entity_name})")

    df_inv_tot = load_cached_data("investigador_total.parquet")
    df_inv_ann = load_cached_data("investigador_annual.parquet")
    df_umap = load_cached_data("umap_investigadores.parquet")
    df_topics = load_cached_data("topics_investigador.parquet")

    if df_inv_tot is None or df_inv_tot.empty:
        st.warning("Aún no hay métricas de investigadores calculadas.")
        return

    # Filtrar investigadores pertenecientes a la entidad
    # Como df_inv_tot['entities'] contiene multiples separadas por ;
    # usamos df_inv_tot[entities].str.contains(entity_name)
    df_inv_tot = df_inv_tot[df_inv_tot['entities'].fillna("").str.contains(entity_name, case=False, na=False)]
    
    if df_inv_tot.empty:
        st.info(f"No hay investigadores registrados para {entity_name}.")
        return

    # Selector
    investigadores = sorted(df_inv_tot['academic_name'].unique())
    st.markdown("La información corresponde a la producción académica que se pudo recoger de las fuentes de información disponibles, lo cual implica que puede haber trabajos con afiliciaciones distintas a la actual.")
    selected_inv = st.selectbox("Seleccione un Académico:", investigadores)

    # 4. Enlaces de Perfil Externo
    academicos_dict = cargar_lista_academicos()
    academico_info = academicos_dict.get(selected_inv, {})
    
    st.markdown("---")
    st.subheader("🔗 Enlaces de Perfil Académico")
    col_links1, col_links2 = st.columns([3, 1])
    with col_links1:
        if academico_info.get("siia") and "No encont" not in academico_info["siia"]:
            st.markdown(f"- **SIIA-UNAM:** [Ver Perfil de {selected_inv}]({academico_info['siia']})")
        if academico_info.get("orcid"):
            st.markdown(f"- **ORCID:** [Ver Perfil]({academico_info['orcid']})")
        
        lista_scopus_id = academico_info.get("scopus", "")
        if lista_scopus_id and "http" in lista_scopus_id:
            st.markdown(f"- **Scopus:** [Ver Perfil]({lista_scopus_id})")
            
    

    # 1. KPIs del Investigador
    inv_data = df_inv_tot[df_inv_tot['academic_name'] == selected_inv].iloc[0]
    st.markdown("---")
    
    st.markdown("##### Métricas Generales")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Doc. Totales", f"{int(inv_data.get('num_documents',0)):,}")
    c2.metric("Índice H", f"{int(inv_data.get('h_index',0))}")
    c3.metric("Total Citas", f"{int(inv_data.get('citations',0)):,}")
    c4.metric("% Open Access", f"{inv_data.get('pct_open_access',0):.1f}%")
    
    st.markdown("##### Métricas de Excelencia")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("FWCI Promedio", f"{inv_data.get('fwci_avg', 0):.2f}")
    c6.metric("Percentil Promedio", f"{inv_data.get('percentile_avg',50):.1f}")
    c7.metric("% Top 10%", f"{inv_data.get('pct_top_10',0):.1f}%")
    c8.metric("% Top 1%", f"{inv_data.get('pct_1',0):.1f}%")
    
    with st.expander("ℹ️ ¿Qué significan estos indicadores?"):
        st.markdown("""
        - **FWCI (Field-Weighted Citation Impact):** Relación entre las citas recibidas y el promedio mundial esperado para el mismo año y disciplina (Mundial = 1.0).
        - **Percentil Promedio:** Posición promedio de los artículos respecto a sus citas (99 es el mejor decil).
        - **% Top 10% / Top 1%:** Porcentaje de la producción que se ubica en la cúspide mundial de citación.
        - **% Open Access:** Porcentaje de documentos publicados bajo estándares de ciencia abierta.
        """)


    colizq, colder = st.columns([1, 1])

    

    # 2. Trayectoria Anual
    with colizq:
        st.subheader("Trayectoria Histórica (Docs)")
        if df_inv_ann is not None:
            ann_data = df_inv_ann[df_inv_ann['academic_name'] == selected_inv].sort_values('year')
            fig_hist = px.bar(ann_data, x='year', y='num_documents', title="Producción Anual", text_auto=True)
            st.plotly_chart(fig_hist, width="stretch")
        else:
            st.info("Sin datos anuales.")

    # 3. Temáticas
    with colder:
        st.subheader("Foco Temático (Top 10)")
        if df_topics is not None:
            conc_data = df_topics[df_topics['academic_name'] == selected_inv]
            if not conc_data.empty:
                conc_data = conc_data.groupby('topic')['value'].sum().reset_index()
                top_c = conc_data.sort_values('value', ascending=False).head(10)
                fig_bar = px.bar(top_c, x='value', y='topic', orientation='h', title="Áreas de Expertise")
                fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_bar, width="stretch")
            else:
                st.info("Sin información temática.")
        else:
            st.info("No hay caché temático.")

    # 3.5 Sunburst Temático
    if df_topics is not None:
        conc_data = df_topics[df_topics['academic_name'] == selected_inv]
        if not conc_data.empty:
            st.markdown("---")
            st.subheader("Concentración Temática (Sunburst)")
            top_topics_inv = conc_data.sort_values('value', ascending=False).head(100)
            
            fig_sun_inv = px.sunburst(
                top_topics_inv, 
                path=['domain', 'field', 'subfield', 'topic'], 
                values='value',
                color='value', 
                color_continuous_scale='Blues',
            )
            fig_sun_inv.update_layout(margin=dict(t=10, l=0, r=0, b=10), height=600)
            st.plotly_chart(fig_sun_inv, width="stretch")

    

    df_profesores_papers = load_cached_data("papers_profesor.parquet")
    if df_profesores_papers is not None and not df_profesores_papers.empty:
        df_prof = df_profesores_papers[df_profesores_papers['academic_name'] == selected_inv]
        
        st.markdown("---")
        mostrar_banners_destacados(df_prof)
        
        st.markdown("---")
        st.header("🌍 Panorama General de Sostenibilidad (ODS)")
        st.write("Distribución de la producción científica en base a Objetivos de Desarrollo Sostenible (Asignados por LLM).")
        html_code = viz_ods.render_sdg_matrix(df_prof, col_ods='ODS_ID')
        st.markdown(html_code, unsafe_allow_html=True)
        
        st.markdown("---")
        st.subheader("📜 Lista Completa de Publicaciones")
        
        col_fil_prof1, col_fil_prof2 = st.columns(2)
        with col_fil_prof1:
            years_prof = np.flip(np.unique(df_prof['year'].dropna()))
            s_year_prof = st.selectbox("Filtrar por año:", options=["Todos"] + list(years_prof), key="prof_year")
        with col_fil_prof2:
            ods_options_prof = sorted([str(ods) for ods in df_prof['ODS_Nombre'].dropna().unique() if str(ods).lower() != "null" and "x" not in str(ods).lower()])
            s_ods_prof = st.selectbox("Filtrar por ODS:", options=["Todos"] + ods_options_prof, key="prof_ods")
        
        df_display_prof = df_prof.copy()
        if s_year_prof != "Todos":
            df_display_prof = df_display_prof[df_display_prof['year'] == s_year_prof]
        if s_ods_prof != "Todos":
            df_display_prof = df_display_prof[df_display_prof['ODS_Nombre'] == s_ods_prof]
            
        df_display_prof = df_display_prof[[
            "year", "Title", "Source", "citations", "DOI", "ODS_Nombre"
        ]].rename(columns={
            "year": "Año",
            "Title": "Título",
            "Source": "Revista/Publicación",
            "citations": "Citas",
            "DOI": "DOI",
            "ODS_Nombre": "ODS"
        }).sort_values(by="Año", ascending=False)
        
        st.dataframe(df_display_prof, width="stretch", hide_index=True, column_config={"DOI": st.column_config.LinkColumn("Enlace DOI")})
    
    # 5. Mapa UMAP
    st.markdown("---")
    st.subheader("Mapa de Desempeño Institucional (UMAP)")
    st.markdown("Cálculo multidimensional comparando Doc, %Top 10, FWCI y Citas normalizadas frente al resto del padrón.")

    if df_umap is not None and not df_umap.empty:
        fig_umap = go.Figure()

        # Otros investigadores (Puntos grises)
        otros = df_umap[df_umap['academic_name'] != selected_inv]
        if not otros.empty:
            fig_umap.add_trace(go.Scatter(
                x=otros['umap_x'], y=otros['umap_y'],
                mode='markers',
                name='Resto del padrón',
                text=otros['academic_name'],
                marker=dict(size=8, color='#002B5C', opacity=0.3, line=dict(width=1, color='darkgray')),
                hovertemplate="<b>%{text}</b><br>Doc: %{customdata[0]}<br>FWCI: %{customdata[1]:.2f}",
                customdata=otros[['num_documents', 'fwci_avg']]
            ))

        # Investigador seleccionado (Punto destacado)
        sel_row = df_umap[df_umap['academic_name'] == selected_inv]
        if not sel_row.empty:
            fig_umap.add_trace(go.Scatter(
                x=sel_row['umap_x'], y=sel_row['umap_y'],
                mode='markers',
                name=selected_inv,
                text=sel_row['academic_name'],
                marker=dict(size=14, color='#D4AF37', symbol='star', line=dict(width=2, color='#b6932b')),
                hovertemplate="<b>%{text}</b><br>Doc: %{customdata[0]}<br>FWCI: %{customdata[1]:.2f}",
                customdata=sel_row[['num_documents', 'fwci_avg']]
            ))

        fig_umap.update_layout(
            hovermode="closest",
            height=500,
            template="plotly_white",
            margin=dict(l=0,r=0,t=30,b=0),
            xaxis_title="Dimensión 1",
            yaxis_title="Dimensión 2"
        )
        st.plotly_chart(fig_umap, width="stretch")
    else:
        st.info("El mapa UMAP no está disponible o faltan datos base calculados.")
