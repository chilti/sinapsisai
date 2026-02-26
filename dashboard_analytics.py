import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import sys

# Paths
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_PATH, 'data', 'cache')

@st.cache_data
def load_cached_data(filename):
    path = os.path.join(CACHE_DIR, filename)
    if os.path.exists(path):
        return pd.read_parquet(path)
    return None

def render_institucion_view(entity_name):
    st.header(f"🏢 Vista de la Institución: {entity_name}")
    st.markdown(f"Panorama Analítico de la Producción de **{entity_name}**")

    df_annual = load_cached_data("institucion_annual.parquet")
    df_total = load_cached_data("institucion_total.parquet")
    df_topics = load_cached_data("topics_institucion.parquet")

    if df_total is not None and not df_total.empty:
        df_total = df_total[df_total['entity_name'] == entity_name]
        if df_total.empty:
            st.warning(f"No hay métricas institucionales pre-calculadas para {entity_name}.")
            return
            
        total = df_total.iloc[0]
        # KPIs
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Doc. Totales", f"{int(total.get('num_documents',0)):,}")
        c2.metric("Citas Acumuladas", f"{int(total.get('citations',0)):,}")
        c3.metric("FWCI Promedio", f"{total.get('fwci_avg',0):.2f}")
        c4.metric("% Top 10%", f"{total.get('pct_top_10',0):.1f}%")

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
                path=['Institución', 'domain', 'field', 'subfield', 'topic'], 
                values='value',
                color='value', 
                color_continuous_scale='Blues',
                title="Concentración Temática"
            )
            fig_sun.update_layout(margin=dict(t=50, l=0, r=0, b=10), height=700)
            st.plotly_chart(fig_sun, width="stretch")

def render_investigador_view(entity_name):
    st.header(f"👤 Vista por Investigador ({entity_name})")
    st.markdown("Perfil Evolutivo y Desempeño Multivariado")

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
    selected_inv = st.selectbox("Seleccione un Académico:", investigadores)

    # 1. KPIs del Investigador
    inv_data = df_inv_tot[df_inv_tot['academic_name'] == selected_inv].iloc[0]
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Doc. Totales", f"{int(inv_data.get('num_documents',0))}")
    c2.metric("Índice H", f"{int(inv_data.get('h_index',0))}")
    c3.metric("Total Citas", f"{int(inv_data.get('citations',0)):,}")
    c4.metric("FWCI Prom.", f"{inv_data.get('fwci_avg', 0):.2f}")

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

    # 4. Mapa UMAP
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
