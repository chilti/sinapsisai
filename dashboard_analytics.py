import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit.components.v1 as components
import os
import sys
import json
import numpy as np
import viz_ods  # Nuevo módulo para pintar la matriz de ODS

try:
    import wordcloud_helper as _wc_helper
    _HAS_WORDCLOUD = True
except ImportError:
    _wc_helper = None
    _HAS_WORDCLOUD = False

# Paths
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_PATH, 'data', 'cache')

@st.cache_data
def load_cached_data(filename, _mtime=None):
    """Carga un parquet del cache. _mtime se usa como cache buster (ignorado internamente)."""
    path = os.path.join(CACHE_DIR, filename)
    if os.path.exists(path):
        return pd.read_parquet(path)
    return None

def get_cached_data(filename):
    """Wrapper que pasa el mtime del archivo para invalidar el cache de Streamlit automáticamente."""
    path = os.path.join(CACHE_DIR, filename)
    mtime = os.path.getmtime(path) if os.path.exists(path) else None
    return load_cached_data(filename, _mtime=mtime)

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

# ══════════════════════════════════════════════════════════════════════════
# Helpers de visualización para indicadores nuevos
# ══════════════════════════════════════════════════════════════════════════

def _render_oa_donut(data_row, key_suffix="", return_fig=False):
    """Mini donut de distribución OA (gold/green/hybrid/bronze/closed)."""
    labels = ["Gold", "Green", "Hybrid", "Bronze", "Closed"]
    cols_  = ["pct_oa_gold","pct_oa_green","pct_oa_hybrid","pct_oa_bronze","pct_oa_closed"]
    values = [float(data_row.get(c, 0) or 0) for c in cols_]
    colors = ["#FFD700","#2ECC71","#3498DB","#CD7F32","#95A5A6"]
    total_oa = float(data_row.get("pct_open_access", sum(v for v in values if v > 0)) or 0)
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=.55,
        marker=dict(colors=colors),
        hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
        textinfo="percent", textposition="outside",
    )])
    fig.update_layout(
        height=260, margin=dict(t=10,b=30,l=10,r=10),
        showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.3),
        annotations=[dict(text=f"{total_oa:.0f}%<br><span style='font-size:11px'>OA</span>",
                          x=0.5, y=0.5, font_size=16, showarrow=False)],
    )
    if return_fig:
        return fig
    st.plotly_chart(fig, use_container_width=True, key=f"donut_oa_{key_suffix}")


def _render_velocity_sparkline(df_papers, name_col, name_val, key_suffix="", return_fig=False):
    """Sparkline de trayectoria de citas acumuladas por año."""
    from collections import defaultdict
    df_p = df_papers[df_papers[name_col] == name_val].copy()
    if df_p.empty or "counts_by_year" not in df_p.columns:
        st.info("Sin datos de trayectoria de citas.")
        return
    year_cites: dict = defaultdict(int)
    for val in df_p["counts_by_year"]:
        if isinstance(val, list):
            for entry in val:
                if isinstance(entry, dict):
                    year_cites[int(entry.get("year", 0))] += int(entry.get("cited_by_count", 0))
    if not year_cites:
        st.info("Sin datos de citas por año.")
        return
    years = sorted(k for k in year_cites if k > 1990)
    cites = [year_cites[y] for y in years]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years, y=cites, mode="lines+markers",
        line=dict(color="#002B5C", width=2.5),
        marker=dict(size=5, color="#D4AF37", line=dict(width=1, color="#b6932b")),
        fill="tozeroy", fillcolor="rgba(0,43,92,0.07)",
        hovertemplate="%{x}: <b>%{y:,}</b> citas<extra></extra>",
    ))
    fig.update_layout(
        height=200, margin=dict(t=5,b=5,l=40,r=10),
        xaxis=dict(showgrid=False, tickformat="d"),
        yaxis=dict(showgrid=True, gridcolor="#eee"),
        template="plotly_white",
    )
    if return_fig:
        return fig
    st.plotly_chart(fig, use_container_width=True, key=f"spark_{key_suffix}")


def _render_choropleth_collab(df_papers, name_col, name_val, title="Países colaboradores", key_suffix="", return_fig=False):
    """Choropleth world map de países colaboradores (ISO-alpha-2 en campo 'countries')."""
    from collections import Counter
    df_p = df_papers[df_papers[name_col] == name_val].copy()
    if df_p.empty or "countries" not in df_p.columns:
        st.info("Sin datos de colaboración internacional.")
        return
    cnt: Counter = Counter()
    for val in df_p["countries"]:
        if isinstance(val, list):
            cnt.update(c for c in val if c and c != "MX")
    if not cnt:
        st.info("No se detectó colaboración internacional registrada.")
        return
    df_cnt = pd.DataFrame(cnt.most_common(80), columns=["iso_a2", "papers"])
    # Plotly choropleth acepta locationmode='ISO-3' natively; convertir si es alpha-2
    fig = px.choropleth(
        df_cnt, locations="iso_a2", locationmode="ISO-3",
        color="papers",
        color_continuous_scale="Blues",
        title=title,
        labels={"papers": "Papers conjuntos"},
        hover_name="iso_a2",
    )
    # Fallback: si los códigos son alpha-2, usar country_iso_alpha nativo
    fig.update_traces(locationmode="geojson-id",
                      geojson=None,
                      selector=dict(type="choropleth"))
    fig_alt = px.choropleth(
        df_cnt, locations="iso_a2",
        color="papers",
        color_continuous_scale="Blues",
        title=title,
        labels={"papers": "Papers conjuntos"},
        hover_name="iso_a2",
    )
    fig_alt.update_layout(
        height=380, margin=dict(t=30,b=0,l=0,r=0),
        geo=dict(showframe=False, showcoastlines=True, bgcolor="rgba(0,0,0,0)",
                 showland=True, landcolor="#f0f0f0"),
        coloraxis_colorbar=dict(title="Papers", len=0.6),
    )
    if return_fig:
        return fig_alt
    st.plotly_chart(fig_alt, use_container_width=True, key=f"choro_{key_suffix}")


def _render_keywords_section(df_kw, name_col, name_val, title="Keywords principales", key_suffix="", return_fig=False):
    """Nube de palabras o barras horizontales de keywords."""
    df_k = df_kw[df_kw[name_col] == name_val].sort_values("freq", ascending=False).head(50)
    if df_k.empty:
        st.info("Sin keywords registrados.")
        return
    freq_dict = dict(zip(df_k["keyword"], df_k["freq"]))
    if _HAS_WORDCLOUD and _wc_helper is not None:
        img_bytes = _wc_helper.generate_wordcloud_image(freq_dict)
        if img_bytes:
            st.markdown(f"**{title}**")
            st.image(img_bytes, use_container_width=True)
            return
    # Fallback: barras horizontales
    top20 = df_k.head(20)
    fig = px.bar(top20, x="freq", y="keyword", orientation="h",
                 color="freq", color_continuous_scale="Blues",
                 title=title, labels={"freq": "Frecuencia", "keyword": ""})
    fig.update_layout(height=420, margin=dict(t=30,b=10),
                      yaxis=dict(categoryorder="total ascending"),
                      showlegend=False, coloraxis_showscale=False)
    if return_fig:
        return fig
    st.plotly_chart(fig, use_container_width=True, key=f"kw_bar_{key_suffix}")


def _render_radar_visibilidad(data_row, title="Perfil de Visibilidad", key_suffix="", return_fig=False):
    """Radar chart con 6 ejes de visibilidad e indexación."""
    metrics = {
        "PubMed":       float(data_row.get("pct_pubmed",        0) or 0),
        "DOAJ":         float(data_row.get("pct_doaj_indexed",  0) or 0),
        "Revista Core": float(data_row.get("pct_core_journal",  0) or 0),
        "Repositorio":  float(data_row.get("pct_repository",    0) or 0),
        "Inglés":       float(data_row.get("pct_english",       0) or 0),
        "CC-BY":        float(data_row.get("pct_cc_by",         0) or 0),
    }
    cats   = list(metrics.keys()) + [list(metrics.keys())[0]]
    values = list(metrics.values()) + [list(metrics.values())[0]]
    fig = go.Figure(data=go.Scatterpolar(
        r=values, theta=cats, fill="toself",
        fillcolor="rgba(0,43,92,0.12)",
        line=dict(color="#002B5C", width=2),
        marker=dict(color="#D4AF37", size=7),
    ))
    fig.update_layout(
        title=dict(text=title, font_size=14, x=0.5),
        polar=dict(radialaxis=dict(visible=True, range=[0,100],
                                   ticksuffix="%", tickfont_size=10)),
        height=320, margin=dict(t=50,b=10,l=30,r=30),
        template="plotly_white",
    )
    if return_fig:
        return fig
    st.plotly_chart(fig, use_container_width=True, key=f"radar_{key_suffix}")


def _render_thematic_evolution(df_evol, name_col, name_val, key_suffix=""):
    """Renderiza la tabla de evolución temática histórica."""
    st.markdown("---")
    st.subheader("📈 Evolución Histórica de Perfiles de Conocimiento")
    st.markdown("Distribución anual del número de artículos por nivel temático de OpenAlex.")

    if df_evol is None or df_evol.empty:
        st.info("Datos de evolución temática no disponibles en el caché.")
        return

    df_p = df_evol[df_evol[name_col] == name_val].copy()
    if df_p.empty:
        st.info("No se encontraron registros de evolución temática para esta selección.")
        return

    # Selección del Nivel Temático
    st.markdown("**Selección del Nivel Temático:**")
    nivel = st.radio(
        "Ver por:",
        ["Dominio", "Campo", "Subcampo", "Tópico"],
        horizontal=True,
        key=f"nivel_evol_{key_suffix}"
    )
    
    nivel_map = {
        "Dominio": "domain",
        "Campo": "field",
        "Subcampo": "subfield",
        "Tópico": "topic"
    }
    col_tema = nivel_map[nivel]

    # Agrupar por nivel y año para obtener el conteo de artículos
    df_pivot = df_p.groupby([col_tema, 'year'])['value'].sum().reset_index()
    
    # Pivotar para tener años en columnas
    df_pivot = df_pivot.pivot(index=col_tema, columns='year', values='value').fillna(0).astype(int)
    
    # Ordenar por el total para mostrar los más relevantes arriba
    df_pivot['Total'] = df_pivot.sum(axis=1)
    df_pivot = df_pivot.sort_values('Total', ascending=False)
    
    # Mostrar la tabla
    st.dataframe(df_pivot, use_container_width=True)


def render_institucion_view(entity_name):
    # Inyectar CSS global para estilizar st.metric como las tarjetas doradas del reporte
    st.markdown("""
        <style>
        [data-testid="stMetric"] {
            background-color: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
            text-align: center;
            border-top: 4px solid #D4AF37;
            border-bottom: 1px solid #eaeaea;
            border-left: 1px solid #eaeaea;
            border-right: 1px solid #eaeaea;
        }
        [data-testid="stMetricLabel"] {
            justify-content: center;
            font-size: 13px !important;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        [data-testid="stMetricValue"] {
            font-size: 30px !important;
            font-weight: 700;
            color: #002B5C;
        }
        /* Ajustar el delta si existe para que quede centrado también */
        [data-testid="stMetricDelta"] {
            justify-content: center;
        }
        </style>
    """, unsafe_allow_html=True)

    st.header(f"🏢 Vista de la Institución: {entity_name}")
    st.markdown(f"Panorama Analítico de la Producción de **{entity_name}**. La producción fué descargada desde Web of Science. Los indicaddores fueron extraidos de la base de datos abierta OpenAlex.")

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
        c5.metric("Percentil Promedio", f"{100*total.get('percentile_avg',50):.1f}")
        c6.metric("% Top 10%", f"{total.get('pct_top_10',0):.1f}%")
        c7.metric("% Top 1%", f"{total.get('pct_1',0):.1f}%")

        # ── Velocidad y Colaboración ──────────────────────────────────────────────
        st.markdown("##### Velocidad de Citas y Colaboración")
        cv1, cv2, cv3, cv4, cv5 = st.columns(5)
        cv1.metric("Citas/año (avg)",       f"{total.get('velocity_avg',0):.1f}")
        cv2.metric("Citas últ. 3 años",     f"{int(total.get('recent_cites_3yr',0)):,}")
        cv3.metric("% Internacional",       f"{total.get('pct_international',0):.1f}%")
        cv4.metric("Países/paper (avg)",    f"{total.get('avg_countries',0):.1f}")
        cv5.metric("Autores/paper (avg)",   f"{total.get('avg_author_count',0):.1f}")

        # ── APC ───────────────────────────────────────────────────────────────────
        st.markdown("##### Acceso Abierto y Costos")
        ca1, ca2, ca3 = st.columns(3)
        apc_total = total.get('apc_paid_usd', 0) or 0
        ca1.metric("APC Total",     f"${apc_total:,.0f} USD")
        ca2.metric("% Papers con APC",     f"{total.get('pct_apc',0):.1f}%")
        ca3.metric("Vida Media Citas",     f"{total.get('half_life_avg',0):.1f} años")

        # ── OA Donut ──────────────────────────────────────────────────────────────
        col_donut, col_gini = st.columns(2)
        with col_donut:
            st.markdown("**Distribución Open Access**")
            _render_oa_donut(total, key_suffix=f"inst_{entity_name}")
        with col_gini:
            st.markdown("**Perfil Temático**")
            gini_val = total.get('gini_topics')
            n_dom    = int(total.get('domain_diversity', 0) or 0)
            n_top    = int(total.get('unique_topics', 0) or 0)
            top_dom  = total.get('top_domain', '—') or '—'
            st.markdown(f"""
| Indicador | Valor |
|---|---|
| Índice de Gini temático | `{gini_val:.3f}` |
| Dominios de investigación | **{n_dom}** |
| Tópicos únicos | **{n_top}** |
| Dominio principal | {top_dom} |
            """.strip()) if gini_val and not np.isnan(gini_val) else st.info("Sin datos de Gini temático.")

        # Glosario Metodológico
        with st.expander("ℹ️ ¿Qué significan estos indicadores?"):
            st.markdown("""
            - **FWCI (Field-Weighted Citation Impact):** Relación entre las citas recibidas y el promedio esperado para el mismo año y disciplina (Mundial = 1.0).
            - **Percentil Promedio:** Posición promedio global de los artículos respecto a sus citas (donde 99 es el decil de mayor impacto).
            - **% Top 10% / Top 1%:** Porcentaje de la producción científica que se ubica entre el 10% o 1% más citado a nivel mundial.
            - **% Open Access:** Porcentaje de documentos en acceso abierto (Vía Dorada, Verde, Híbrida o Bronce).
            - **Citas/año (avg):** Velocidad promedio de citación; cuántas citas recibe un artículo cada año calendario desde su publicación.
            - **Citas últ. 3 años:** Citas frescas recolectadas en los tres años más recientes.
            - **% Internacional:** Porcentaje de artículos donde participa al menos una institución extranjera.
            - **Países/paper (avg):** Promedio de países involucrados por publicación.
            - **Autores/paper (avg):** Promedio de autores individuales por publicación.
            - **APC Total:** Suma del costo histórico de las Cuotas por Procesamiento de Artículo (Article Processing Charges) de todos los artículos en los que participó al menos un académico de la Institución. Este valor es referencial al "precio de lista de OA de la revista" y no significa que la Facultad lo haya pagado, ya que pudo ser cubierto por fondos de investigación, otras universidades o consorcios.
            - **Vida Media Citas:** Años que tarda en promedio un artículo en acumular el 50% de sus citas totales actuales.
            - **Gini temático:** 0 = enfocado en un solo tema, 1 = producción totalmente dispersa.
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
            fig_sun = px.sunburst(
                top_topics,
                path=['domain', 'field', 'subfield', 'topic'],
                values='value',
                color='value',
                color_continuous_scale='Blues',
                title="Concentración Temática"
            )
            fig_sun.update_layout(margin=dict(t=50, l=0, r=0, b=10), height=700)
            st.plotly_chart(fig_sun, width="stretch")

            # --- Evolución Histórica Institucional ---
            df_evol_inst = get_cached_data("thematic_evolution_institucion.parquet")
            _render_thematic_evolution(df_evol_inst, 'entity_name', entity_name, key_suffix=f"inst_{entity_name}")

    # ── Vocabulario Científico (WordCloud) ────────────────────────────────────────
    df_kw_inst = get_cached_data("keywords_institucion.parquet")
    if df_kw_inst is not None and not df_kw_inst.empty:
        st.markdown("---")
        st.subheader("🔑 Vocabulario Científico Institucional")
        _render_keywords_section(df_kw_inst, "entity_name", entity_name,
                                 title="", key_suffix=f"inst_{entity_name}")

    # ── Colaboración Internacional (Choropleth) ───────────────────────────────────
    df_inst_papers = get_cached_data("papers_institucion.parquet")
    if df_inst_papers is not None and not df_inst_papers.empty:
        df_ip = df_inst_papers[df_inst_papers['entity_name'] == entity_name]
        if not df_ip.empty and "countries" in df_ip.columns:
            st.markdown("---")
            st.subheader("🌍 Colaboración Internacional")
            df_annual_inst = get_cached_data("institucion_annual.parquet")
            if df_annual_inst is not None and not df_annual_inst.empty:
                df_ia = df_annual_inst[df_annual_inst['entity_name'] == entity_name].sort_values('year')
                if 'pct_international' in df_ia.columns and not df_ia.empty:
                    fig_intl = go.Figure()
                    fig_intl.add_trace(go.Scatter(
                        x=df_ia['year'], y=df_ia['pct_international'],
                        mode='lines+markers', name='% Internacional',
                        line=dict(color='#002B5C', width=2.5),
                        marker=dict(size=6, color='#D4AF37'),
                        fill='tozeroy', fillcolor='rgba(0,43,92,0.07)',
                        hovertemplate="%{x}: <b>%{y:.1f}%</b><extra></extra>",
                    ))
                    fig_intl.update_layout(
                        height=220, margin=dict(t=5,b=5,l=40,r=10),
                        yaxis=dict(ticksuffix="%", range=[0,100]),
                        xaxis=dict(showgrid=False, tickformat="d"),
                        template="plotly_white",
                        title="Evolución de Colaboración Internacional (%)",
                    )
                    st.plotly_chart(fig_intl, use_container_width=True, key=f"intl_evol_{entity_name}")
            _render_choropleth_collab(df_ip, 'entity_name', entity_name,
                                      title="Países colaboradores",
                                      key_suffix=f"inst_{entity_name}")

    # ── Stacked Bar OA anual ──────────────────────────────────────────────
    df_annual_oa = get_cached_data("institucion_annual.parquet")
    if df_annual_oa is not None and not df_annual_oa.empty:
        df_oa_ann = df_annual_oa[df_annual_oa['entity_name'] == entity_name].sort_values('year')
        oa_cols = [c for c in ['pct_oa_gold','pct_oa_green','pct_oa_hybrid','pct_oa_bronze','pct_oa_closed']
                   if c in df_oa_ann.columns]
        if oa_cols and not df_oa_ann.empty:
            st.markdown("---")
            st.subheader("📊 Evolución del Acceso Abierto por Año")
            df_oa_melt = df_oa_ann[['year'] + oa_cols].melt(id_vars='year', var_name='tipo_oa', value_name='pct')
            df_oa_melt['tipo_oa'] = df_oa_melt['tipo_oa'].str.replace('pct_oa_','').str.capitalize()
            color_map = {'Gold':'#FFD700','Green':'#2ECC71','Hybrid':'#3498DB','Bronze':'#CD7F32','Closed':'#95A5A6'}
            fig_stack = px.bar(df_oa_melt, x='year', y='pct', color='tipo_oa',
                               color_discrete_map=color_map,
                               labels={'pct':'%','tipo_oa':'Tipo OA'},
                               barmode='stack',
                               title="Distribución OA por año (%)",
                               text_auto=False)
            fig_stack.update_layout(height=320, margin=dict(t=30,b=10), template='plotly_white',
                                     xaxis=dict(tickformat='d'))
            st.plotly_chart(fig_stack, use_container_width=True, key=f"oa_stack_{entity_name}")

    # ── Perfil de Visibilidad e Indexación (Radar) ────────────────────────────────
    if df_total is not None:
        total_row = df_total.iloc[0] if not df_total.empty else None
        if total_row is not None:
            vis_cols = ['pct_pubmed','pct_doaj_indexed','pct_core_journal',
                        'pct_repository','pct_english','pct_cc_by']
            has_vis = any(total_row.get(c, 0) != 0 for c in vis_cols)
            if has_vis:
                st.markdown("---")
                with st.expander("🔭 Perfil de Visibilidad e Indexación", expanded=False):
                    col_rad, col_idx = st.columns([1, 1])
                    with col_rad:
                        _render_radar_visibilidad(total_row,
                                                  title="Perfil de Visibilidad",
                                                  key_suffix=f"inst_{entity_name}")
                    with col_idx:
                        st.markdown("")
                        st.markdown(f"""
| Indicador | Valor |
|---|---|
| % en PubMed | `{total_row.get('pct_pubmed',0):.1f}%` |
| % en DOAJ | `{total_row.get('pct_doaj_indexed',0):.1f}%` |
| % en revista Core | `{total_row.get('pct_core_journal',0):.1f}%` |
| % en repositorio | `{total_row.get('pct_repository',0):.1f}%` |
| % en inglés | `{total_row.get('pct_english',0):.1f}%` |
| % con licencia CC-BY | `{total_row.get('pct_cc_by',0):.1f}%` |
| Papers retractados | `{total_row.get('pct_retracted',0):.2f}%` |
                        """.strip())

    df_institucion_papers = load_cached_data("papers_institucion.parquet")
    if df_institucion_papers is not None and not df_institucion_papers.empty:
        df_inst_p = df_institucion_papers[df_institucion_papers['entity_name'] == entity_name]
        
        st.markdown("---")
        st.header("🌍 Impacto Global Institucional en Sostenibilidad (ODS)")
        st.write("Distribución consolidada de toda la producción científica de la institución respecto a los Objetivos de Desarrollo Sostenible.")
        html_code_inst = viz_ods.render_sdg_matrix(df_inst_p, col_ods='ODS_ID')
        st.markdown(html_code_inst, unsafe_allow_html=True)
        
        st.markdown("---")
        st.subheader("📜 Publicaciones")
        
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
            
        if "openalex_url" not in df_display_inst.columns:
            df_display_inst["openalex_url"] = None
            
        df_display_inst = df_display_inst[[
            "year", "Title", "Source", "citations", "DOI", "openalex_url", "ODS_Nombre"
        ]].rename(columns={
            "year": "Año",
            "Title": "Título",
            "Source": "Revista/Publicación",
            "citations": "Citas",
            "DOI": "DOI",
            "openalex_url": "OpenAlex",
            "ODS_Nombre": "ODS"
        }).sort_values(by="Año", ascending=False)
        
        st.dataframe(df_display_inst, width="stretch", hide_index=True, column_config={
            "DOI": st.column_config.LinkColumn("Enlace DOI", display_text="Ver Link"),
            "OpenAlex": st.column_config.LinkColumn("OpenAlex", display_text="Ver en OpenAlex")
        })

        # ── Reporte Bibliométrico IA ──────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("📄 Reporte Bibliométrico con Inteligencia Artificial")
        st.markdown("Genera o descarga un reporte analítico consolidado, interpretado por LLM, incluyendo las gráficas interactivas mostradas arriba.")
        import re
        safe_name = "".join([c if c.isalnum() else "_" for c in entity_name])
        report_path = os.path.join(BASE_PATH, 'reports', f"report_inst_{safe_name}.html")
        
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                html_data = f.read()
            
            c_rep1, c_rep2 = st.columns([1, 1])
            with c_rep1:
                st.download_button("⬇️ Descargar Reporte (HTML)", data=html_data, file_name=f"Reporte_Institucion_{safe_name}.html", mime="text/html")
            with c_rep2:
                if st.button("🔄 Regenerar Reporte con IA", key=f"btn_regen_inst_{safe_name}"):
                    with st.spinner("Regenerando análisis y reporte con el modelo LLM local... Esto tomará algunos segundos."):
                        import subprocess
                        subprocess.run([sys.executable, "report_generator.py", "--type", "inst", "--name", entity_name])
                    st.rerun()
        else:
            if st.button("✨ Generar Reporte con IA", key=f"btn_gen_inst_{safe_name}"):
                with st.spinner("Generando análisis y reporte con el modelo LLM local... Esto tomará algunos segundos."):
                    import subprocess
                    subprocess.run([sys.executable, "report_generator.py", "--type", "inst", "--name", entity_name])
                st.rerun()

def render_investigador_view(entity_name):
    # Inyectar CSS global para estilizar st.metric como las tarjetas doradas del reporte
    st.markdown("""
        <style>
        [data-testid="stMetric"] {
            background-color: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
            text-align: center;
            border-top: 4px solid #D4AF37;
            border-bottom: 1px solid #eaeaea;
            border-left: 1px solid #eaeaea;
            border-right: 1px solid #eaeaea;
        }
        [data-testid="stMetricLabel"] {
            justify-content: center;
            font-size: 13px !important;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        [data-testid="stMetricValue"] {
            font-size: 30px !important;
            font-weight: 700;
            color: #002B5C;
        }
        [data-testid="stMetricDelta"] {
            justify-content: center;
        }
        </style>
    """, unsafe_allow_html=True)
    st.header(f"👤 Vista por Investigador ({entity_name})")

    df_inv_tot = get_cached_data("investigador_total.parquet")
    df_inv_ann = get_cached_data("investigador_annual.parquet")
    df_umap    = get_cached_data("umap_investigadores.parquet")
    df_topics  = get_cached_data("topics_investigador.parquet")

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
    st.markdown("Aquí aparecen los investigadores registrados en el SNII. Los indicadores se calcularon a partir de la producción académica que se pudo recoger de Scopus y ORCID, lo cual implica que puede haber trabajos faltantes y trabajos con afiliaciones distintas a la actual.")
    selected_inv = st.selectbox("Seleccione un Académico:", investigadores)

    # 4. Enlaces de Perfil Externo
    inv_data = df_inv_tot[df_inv_tot['academic_name'] == selected_inv].iloc[0]
    academicos_dict = cargar_lista_academicos()
    academico_info = academicos_dict.get(selected_inv, {})
    
    # Priorizar IDs del DataFrame (Neo4j/Parquet) sobre el JSON institucional (obsoleto)
    inv_orcid = inv_data.get('orcid') or academico_info.get("orcid")
    inv_scopus = inv_data.get('scopus_id') or academico_info.get("scopus")
    inv_siia = inv_data.get('siia_url') or academico_info.get("siia")

    st.markdown("---")
    st.subheader("🔗 Enlaces de Perfil Académico")
    col_links1, col_links2 = st.columns([3, 1])
    with col_links1:
        if inv_siia and "http" in str(inv_siia) and "No encont" not in str(inv_siia):
            st.markdown(f"- **SIIA-UNAM:** [Ver Perfil de {selected_inv}]({inv_siia})")
        
        if inv_orcid:
            orcid_link = inv_orcid if "http" in inv_orcid else f"https://orcid.org/{inv_orcid}"
            st.markdown(f"- **ORCID:** [Ver Perfil]({orcid_link})")
        
        if inv_scopus:
            # Extraer todos los IDs numéricos de forma robusta
            import re
            all_ids = re.findall(r'\d+', str(inv_scopus))
            if all_ids:
                for sid in all_ids:
                    scopus_link = f"https://www.scopus.com/authid/detail.uri?authorId={sid}"
                    st.markdown(f"- **Scopus ({sid}):** [Ver Perfil]({scopus_link})")
            elif "http" in str(inv_scopus):
                st.markdown(f"- **Scopus:** [Ver Perfil]({inv_scopus})")
            
    

    # 1. KPIs del Investigador
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

    # ── Velocidad y Colaboración ────────────────────────────────────────────────
    st.markdown("##### Velocidad de Citas y Colaboración")
    cv1, cv2, cv3, cv4, cv5 = st.columns(5)
    vel = inv_data.get('velocity_avg', 0) or 0
    rec = int(inv_data.get('recent_cites_3yr', 0) or 0)
    delta_txt = f"↑ {rec} últ. 3 años" if rec > vel else None
    cv1.metric("Citas/año (prom.)",      f"{vel:.1f}", delta=delta_txt)
    cv2.metric("Citas últ. 3 años",      f"{rec:,}")
    cv3.metric("% Internacional",        f"{inv_data.get('pct_international',0):.1f}%")
    cv4.metric("Países/paper (prom.)",   f"{inv_data.get('avg_countries',0):.1f}")
    cv5.metric("Autores/paper (prom.)",  f"{inv_data.get('avg_author_count',0):.1f}")

    # ── APC ──────────────────────────────────────────────────────────────────────
    st.markdown("##### Acceso Abierto y Costos")
    ca1, ca2, ca3 = st.columns(3)
    apc_inv = inv_data.get('apc_paid_usd', 0) or 0
    ca1.metric("APC Total",  f"${apc_inv:,.0f} USD")
    ca2.metric("% Papers con APC", f"{inv_data.get('pct_apc',0):.1f}%")
    ca3.metric("Vida Media Citas", f"{inv_data.get('half_life_avg',0):.1f} años")

    # ── OA Donut ──────────────────────────────────────────────────────────────────
    col_donut_inv, col_gini_inv = st.columns(2)
    with col_donut_inv:
        st.markdown("**Distribución Open Access**")
        _render_oa_donut(inv_data, key_suffix=f"inv_{selected_inv}")
    with col_gini_inv:
        st.markdown("**Perfil Temático**")
        gini_inv = inv_data.get('gini_topics')
        if gini_inv is not None and not (isinstance(gini_inv, float) and np.isnan(gini_inv)):
            st.markdown(f"""
| Indicador | Valor |
|---|---|
| Índice de Gini temático | `{gini_inv:.3f}` |
| Dominios cubiertos | **{int(inv_data.get('domain_diversity',0) or 0)}** |
| Tópicos únicos | **{int(inv_data.get('unique_topics',0) or 0)}** |
| Dominio principal | {inv_data.get('top_domain','—') or '—'} |
            """.strip())
        else:
            st.info("Sin datos de diversidad temática.")

    with st.expander("ℹ️ ¿Qué significan estos indicadores?"):
        st.markdown("""
        - **FWCI:** Relación citas recibidas / promedio mundial para el mismo año y disciplina (1.0 = media mundial).
        - **Percentil / Top 10% / Top 1%:** Posición global en citación dentro del campo de conocimiento.
        - **Citas/año (avg):** Velocidad promedio de citación anual que mantienen los artículos desde su fecha de publicación.
        - **Citas últ. 3 años:** Sumatoria total de citas recientes acumuladas en los últimos 36 meses.
        - **% Internacional:** Proporción de papers co-escritos con al menos un autor de otro país.
        - **Países/paper y Autores/paper:** Densidad de colaboración geográfica y de red por publicación.
        - **APC Total:** Costo de lista estimado (USD) de las Cuotas de Acceso Abierto (Article Processing Charges) de los artículos en los que participó el académico. Este valor es referencial y no significa que la Facultad lo haya pagado; los costos pudieron ser cubiertos por fondos internacionales, universidades o consorcios.
        - **% Papers con APC:** Porcentaje de la producción que fue publicada en revistas que manejan cuotas.
        - **Vida Media Citas:** Años tras la publicación hasta que el paper recaba el 50% de su impacto.
        - **Gini temático:** 0 = muy enfocado en un puro tema, 1 = producción en múltiples frentes diversos.
        - **% Open Access / Tipos OA:** Gold (revista OA), Green (repositorio intermedio), Hybrid (revista de paga que libera el pdf por petición del autor), Bronze (libre disponibilidad sin licencia explícita).
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

            # --- Evolución Histórica Investigador ---
            df_evol_inv = get_cached_data("thematic_evolution_investigador.parquet")
            _render_thematic_evolution(df_evol_inv, 'academic_name', selected_inv, key_suffix=f"inv_{selected_inv}")

    # ── WordCloud de Keywords ─────────────────────────────────────────────────────
    df_kw_inv = get_cached_data("keywords_investigador.parquet")
    if df_kw_inv is not None and not df_kw_inv.empty:
        st.markdown("---")
        st.subheader("🔑 Vocabulario Científico")
        _render_keywords_section(df_kw_inv, "academic_name", selected_inv,
                                 title="", key_suffix=f"inv_{selected_inv}")

    # ── Colaboración Internacional (Choropleth) ───────────────────────────────────
    df_profesores_papers = load_cached_data("papers_profesor.parquet")
    if df_profesores_papers is not None and not df_profesores_papers.empty:
        df_prof = df_profesores_papers[df_profesores_papers['academic_name'] == selected_inv]

        if not df_prof.empty and "countries" in df_prof.columns:
            st.markdown("---")
            st.subheader("🌍 Colaboración Internacional")
            # Sparkline de citas
            _render_velocity_sparkline(df_prof, 'academic_name', selected_inv,
                                       key_suffix=f"inv_{selected_inv}")
            _render_choropleth_collab(df_prof, 'academic_name', selected_inv,
                                      title="Países colaboradores",
                                      key_suffix=f"inv_{selected_inv}")

        # ── Indexación y Visibilidad ──────────────────────────────────────────────
        vis_cols_inv = ['pct_pubmed','pct_doaj_indexed','pct_core_journal',
                        'pct_repository','pct_english','pct_cc_by']
        has_vis_inv = any(inv_data.get(c, 0) != 0 for c in vis_cols_inv)
        if has_vis_inv:
            st.markdown("---")
            with st.expander("🔭 Visibilidad e Indexación", expanded=False):
                col_r, col_t = st.columns([1, 1])
                with col_r:
                    _render_radar_visibilidad(inv_data, title="Perfil de Visibilidad",
                                             key_suffix=f"inv_{selected_inv}")
                with col_t:
                    st.markdown("")
                    st.markdown(f"""
| Indicador | Valor |
|---|---|
| % en PubMed | `{inv_data.get('pct_pubmed',0):.1f}%` |
| % en DOAJ | `{inv_data.get('pct_doaj_indexed',0):.1f}%` |
| % en revista Core | `{inv_data.get('pct_core_journal',0):.1f}%` |
| % en repositorio | `{inv_data.get('pct_repository',0):.1f}%` |
| % en inglés | `{inv_data.get('pct_english',0):.1f}%` |
| % con licencia CC-BY | `{inv_data.get('pct_cc_by',0):.1f}%` |
                    """.strip())

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
            
        if "openalex_url" not in df_display_prof.columns:
            df_display_prof["openalex_url"] = None
            
        df_display_prof = df_display_prof[[
            "year", "Title", "Source", "citations", "DOI", "openalex_url", "ODS_Nombre"
        ]].rename(columns={
            "year": "Año",
            "Title": "Título",
            "Source": "Revista/Publicación",
            "citations": "Citas",
            "DOI": "DOI",
            "openalex_url": "OpenAlex",
            "ODS_Nombre": "ODS"
        }).sort_values(by="Año", ascending=False)
        
        st.dataframe(df_display_prof, width="stretch", hide_index=True, column_config={
            "DOI": st.column_config.LinkColumn("Enlace DOI", display_text="Ver Link"),
            "OpenAlex": st.column_config.LinkColumn("OpenAlex", display_text="Ver en OpenAlex")
        })
    
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

    # ── Reporte Bibliométrico IA ──────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📄 Reporte Bibliométrico con Inteligencia Artificial")
    st.markdown("Genera o descarga un reporte analítico consolidado del investigador, interpretado por LLM, incluyendo las gráficas interactivas.")
    
    import re
    safe_name = "".join([c if c.isalnum() else "_" for c in selected_inv])
    report_path = os.path.join(BASE_PATH, 'reports', f"report_inv_{safe_name}.html")
    
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            html_data = f.read()
            
        c_repA, c_repB = st.columns([1, 1])
        with c_repA:
            st.download_button("⬇️ Descargar Reporte (HTML)", data=html_data, file_name=f"Reporte_Investigador_{safe_name}.html", mime="text/html")
        with c_repB:
            if st.button("🔄 Regenerar Reporte con IA", key=f"btn_regen_inv_{safe_name}"):
                with st.spinner("Regenerando análisis y reporte con el modelo LLM local... Esto tomará un par de minutos."):
                    import subprocess
                    subprocess.run([sys.executable, "report_generator.py", "--type", "inv", "--name", selected_inv])
                st.rerun()
    else:
        if st.button("✨ Generar Reporte con IA", key=f"btn_gen_inv_{safe_name}"):
            with st.spinner("Generando análisis y reporte con el modelo LLM local... Esto tomará un par de minutos."):
                import subprocess
                subprocess.run([sys.executable, "report_generator.py", "--type", "inv", "--name", selected_inv])
            st.rerun()
