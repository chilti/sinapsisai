import os
import json
import numpy as np
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import markdown
from dotenv import load_dotenv
from pyvis.network import Network
import httpx
import dashboard_analytics as da
from lib import viz_ods
from database.knowledge_graph import Neo4jGraphStore

load_dotenv()
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_PATH, 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)

from lib.llm_utils import LLMConfig

def get_llm_analysis(prompt: str, system_prompt: str = "Eres un analista bibliométrico experto. Escribe siempre en un tono formal, objetivo y académico, evitando adjetivos exagerados. Sé conciso.") -> str:
    try:
        auth_url = LLMConfig.get_auth_url()
        api_key = LLMConfig.get_api_key()
        llm_model = LLMConfig.get_model_name()

        url = auth_url.rstrip("/") + "/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2, # Lower temperature for more factual reporting
            "max_tokens": 1200
        }
        
        with httpx.Client(verify=False, timeout=180.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
            
    except Exception as e:
        return f"*(Error al generar análisis con el LLM: {str(e)})*"

def get_report_path(entity_type: str, entity_name: str, view_mode: str = "capacidad_instalada") -> tuple[str, str]:
    safe_name = "".join([c if c.isalnum() else "_" for c in entity_name])
    suffix = f"_{view_mode}" if entity_type == "inst" else ""
    return os.path.join(REPORTS_DIR, f"report_{entity_type}{suffix}_{safe_name}.html"), safe_name

def fig_to_html(fig):
    if not fig: return ""
    # Injecting the plotly lib via CDN unconditionally since this HTML isn't tied to a JS framework header
    return "<div class='chart'>" + pio.to_html(fig, full_html=False, include_plotlyjs='cdn') + "</div>"

def generate_html_report(entity_type: str, entity_name: str, entity_context: str = None, institution_name: str = None, view_mode: str = "capacidad_instalada") -> str:
    """Generates a comprehensive HTML report for an institution or researcher."""
    file_path, safe_name = get_report_path(entity_type, entity_name, view_mode)
    print(f"Iniciando generación de reporte para {entity_name}...")
    
    # 1. Fetch ALL relevant data
    col_name = 'entity_name' if entity_type == "inst" else 'academic_name'
    
    # Resolver los parámetros para el cache jerárquico
    ent_param = entity_name if entity_type == "inst" else entity_context
    ac_param  = None if entity_type == "inst" else entity_name

    df_tot = da.get_cached_data("institucion_total.parquet" if entity_type == "inst" else "investigador_total.parquet", entity_name=ent_param, academic_name=ac_param, institution_name=institution_name, view_mode=view_mode)
    df_ann = da.get_cached_data("institucion_annual.parquet" if entity_type == "inst" else "investigador_annual.parquet", entity_name=ent_param, academic_name=ac_param, institution_name=institution_name, view_mode=view_mode)
    df_pap = da.get_cached_data("papers_institucion.parquet" if entity_type == "inst" else "papers_profesor.parquet", entity_name=ent_param, academic_name=ac_param, institution_name=institution_name, view_mode=view_mode)
    df_top = da.get_cached_data("topics_institucion.parquet" if entity_type == "inst" else "topics_investigador.parquet", entity_name=ent_param, academic_name=ac_param, institution_name=institution_name, view_mode=view_mode)
    df_kw = da.get_cached_data("keywords_institucion.parquet" if entity_type == "inst" else "keywords_investigador.parquet", entity_name=ent_param, academic_name=ac_param, institution_name=institution_name, view_mode=view_mode)
    
    if df_tot is None or df_tot.empty:
        raise ValueError("Datos totales no disponibles en caché para esta entidad/académico.")
        
    data = df_tot.iloc[0].to_dict()
    df_ann_ent = df_ann.sort_values('year') if df_ann is not None else pd.DataFrame()
    df_pap_ent = df_pap if df_pap is not None else pd.DataFrame()

    sections_html = ""

    # -------------------------------------------------------------------------
    # SECCIÓN 1: Resumen Ejecutivo
    # -------------------------------------------------------------------------
    print("Generando SubReporte 1/8: Resumen Ejecutivo...")
    m_docs = data.get('num_documents', 0)
    m_cites = data.get('citations', 0)
    m_fwci = data.get('fwci_avg', 0)
    m_oa = data.get('pct_open_access', 0)
    
    p_exec = f"Basado en los siguientes indicadores globales de {entity_type} ({entity_name}): Documentos: {m_docs}, Citas Totales: {m_cites}, FWCI Promedio: {m_fwci:.2f}, Open Access: {m_oa:.1f}%. Redacta un Resumen Ejecutivo analítico muy breve (1-2 párrafos) con tono formal, destacando su volumen y alcance."
    llm_exec = markdown.markdown(get_llm_analysis(p_exec))
    
    sections_html += f"""
    <h2>1. Resumen Ejecutivo</h2>
    <div class="summary-box">{llm_exec}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{int(m_docs):,}</div><div class="metric-label">Documentos</div></div>
        <div class="metric-card"><div class="metric-value">{int(m_cites):,}</div><div class="metric-label">Citas Totales</div></div>
        <div class="metric-card"><div class="metric-value">{m_fwci:.2f}</div><div class="metric-label">FWCI Promedio</div></div>
        <div class="metric-card"><div class="metric-value">{m_oa:.1f}%</div><div class="metric-label">Open Access</div></div>
    </div>
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 2: Desempeño General e Histórico
    # -------------------------------------------------------------------------
    print("Generando SubReporte 2/8: Desempeño Histórico...")
    html_hist_fig = ""
    if not df_ann_ent.empty:
        # Rango temporal: max(1950, año mínimo) → año en curso
        _cur_year = datetime.now().year
        _yr_min = int(df_ann_ent['year'].min())
        _x_min = max(1950, _yr_min)
        if entity_type == 'inst':
            fig_hist = px.area(df_ann_ent, x='year', y='num_documents',
                               title="Documentos Publicados por Año",
                               color_discrete_sequence=['#ff7f0e'],
                               range_x=[_x_min, _cur_year])
        else:
            fig_hist = px.bar(df_ann_ent, x='year', y='num_documents',
                              title="Documentos Publicados por Año",
                              color_discrete_sequence=['#ff7f0e'],
                              range_x=[_x_min - 0.5, _cur_year + 0.5])
        fig_hist.update_xaxes(tickformat='d', dtick=5)
        html_hist_fig = fig_to_html(fig_hist)
        
    p_hist = f"El {entity_type} ({entity_name}) produjo {m_docs} documentos históricos. Redacta un párrafo formal observando la importancia de mantener una producción sostenida."
    llm_hist = markdown.markdown(get_llm_analysis(p_hist))
    
    sections_html += f"<h2>2. Producción Anual</h2><div class='markdown-text'>{llm_hist}</div>{html_hist_fig}"

    # -------------------------------------------------------------------------
    # SECCIÓN 3: Excelencia e Impacto
    # -------------------------------------------------------------------------
    print("Generando SubReporte 3/8: Excelencia e Impacto...")
    m_perc = data.get('percentile_avg', 0) * 100
    m_top10 = data.get('pct_top_10', 0)
    m_top1 = data.get('pct_1', 0)
    
    html_fwci_fig = ""
    if not df_ann_ent.empty and 'fwci_avg' in df_ann_ent.columns:
        _cur_year_f = datetime.now().year
        _x_min_f = max(1950, int(df_ann_ent['year'].min()))
        fig_fwci = px.line(df_ann_ent, x='year', y='fwci_avg', markers=True,
                           title="Evolución FWCI Promedio Histórico",
                           range_x=[_x_min_f, _cur_year_f])
        fig_fwci.add_hline(y=1.0, line_dash="dash", line_color="red", annotation_text="Base Mundial (1.0)")
        fig_fwci.update_xaxes(tickformat='d', dtick=5)
        html_fwci_fig = fig_to_html(fig_fwci)
        
    p_exc = f"La calidad del impacto de {entity_name} se resume en: Percentil Promedio (posicionamiento global de citas) = {m_perc:.1f}, % Top 10% más citado = {m_top10:.1f}%, % Top 1% = {m_top1:.1f}%, FWCI (impacto normalizado) = {m_fwci:.2f} donde 1.0 es la media mundial. Redacta un párrafo estricto analizando la excelencia de este impacto métrico."
    llm_exc = markdown.markdown(get_llm_analysis(p_exc))
    
    sections_html += f"""
    <h2>3. Excelencia e Impacto Científico</h2><div class='markdown-text'>{llm_exc}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{m_perc:.1f}</div><div class="metric-label">Percentil Promedio</div></div>
        <div class="metric-card"><div class="metric-value">{m_top10:.1f}%</div><div class="metric-label">% Top 10%</div></div>
        <div class="metric-card"><div class="metric-value">{m_top1:.1f}%</div><div class="metric-label">% Top 1%</div></div>
    </div>
    {html_fwci_fig}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 4: Dinámica de Citación
    # -------------------------------------------------------------------------
    print("Generando SubReporte 4/8: Dinámica de Citación...")
    m_vel = data.get('velocity_avg', 0)
    m_intl = data.get('pct_international', 0)

    html_vel_fig = ""
    if not df_pap_ent.empty:
        # Velocidad Sparkline NATIVA
        try:
            df_vel = df_pap_ent.copy()
            df_vel['age'] = datetime.now().year - df_vel['year']
            df_vel['age'] = df_vel['age'].replace(0, 1)
            df_vel['velocity'] = df_vel['citations'] / df_vel['age']
            top_vel = df_vel.sort_values('velocity', ascending=False).head(20).sort_values('year')
            fig_vel = go.Figure()
            fig_vel.add_trace(go.Scatter(
                x=top_vel['year'], y=top_vel['velocity'],
                mode='lines+markers',
                line=dict(color='#8B0000', width=2),
                marker=dict(size=4, color='#E39918')
            ))
            fig_vel.update_layout(
                height=200, margin=dict(t=30, b=10, l=10, r=10),
                title="Desempeño Acelerado: Artículos con captura rápida de citas",
                template="plotly_white"
            )
            html_vel_fig = fig_to_html(fig_vel)
        except Exception as e:
            print("Error vel: ", e)

    p_col = (
        f"La entidad ({entity_name}) tiene una velocidad promedio de captura de citas de "
        f"{m_vel:.1f} citas/año por artículo. Redacta un párrafo formal evaluando "
        f"cómo esta métrica refleja la visibilidad y el impacto temprano de su producción científica."
    )
    llm_col = markdown.markdown(get_llm_analysis(p_col))

    sections_html += f"""
    <h2>4. Dinámica de Citación</h2><div class='markdown-text'>{llm_col}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{m_vel:.1f}</div><div class="metric-label">Velocidad (Citas/Año)</div></div>
    </div>
    {html_vel_fig}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 5: Acceso Abierto
    # -------------------------------------------------------------------------
    print("Generando SubReporte 5/8: Acceso Abierto...")
    m_apc = data.get('apc_paid_usd', 0)
    
    html_oa_figs = ""
    
    # Donut NATIVO
    try:
        oa_vals = [data.get(k,0) for k in ['pct_oa_gold','pct_oa_green','pct_oa_hybrid','pct_oa_bronze','pct_oa_closed']]
        labels = ['Gold', 'Green', 'Hybrid', 'Bronze', 'Closed']
        colors = ['#FFD700', '#2ECC71', '#3498DB', '#CD7F32', '#95A5A6']
        fig_oa = go.Figure(data=[go.Pie(labels=labels, values=oa_vals, hole=.4, marker=dict(colors=colors))])
        fig_oa.update_layout(height=280, margin=dict(t=10, b=10, l=10, r=10), showlegend=True, title="Distribución OA Global")
        html_oa_figs += fig_to_html(fig_oa)
    except Exception as e: print("Error donut:", e)

    if not df_ann_ent.empty:
        oa_cols = [c for c in ['pct_oa_gold','pct_oa_green','pct_oa_hybrid','pct_oa_bronze','pct_oa_closed'] if c in df_ann_ent.columns]
        if oa_cols:
            df_oa_melt = df_ann_ent[['year'] + oa_cols].melt(id_vars='year', var_name='tipo_oa', value_name='pct')
            df_oa_melt['tipo_oa'] = df_oa_melt['tipo_oa'].str.replace('pct_oa_','').str.capitalize()
            color_map = {'Gold':'#FFD700','Green':'#2ECC71','Hybrid':'#3498DB','Bronze':'#CD7F32','Closed':'#95A5A6'}
            _cur_year_oa = datetime.now().year
            _x_min_oa = max(1950, int(df_ann_ent['year'].min()))
            fig_stack = px.bar(df_oa_melt, x='year', y='pct', color='tipo_oa',
                               color_discrete_map=color_map, barmode='stack',
                               title="Evolución Distribución OA (%)",
                               range_x=[_x_min_oa - 0.5, _cur_year_oa + 0.5])
            fig_stack.update_xaxes(tickformat='d', dtick=5)
            html_oa_figs += fig_to_html(fig_stack)

    p_oa = f"En acceso abierto, {entity_name} alcanza un {m_oa:.1f}% de apertura global, estimando un costo de APC (Article Processing Charges) de lista de todos los papers en los que figura por ${m_apc:,.0f} USD. Redacta un párrafo puramente descriptivo sobre su adopción de vías abiertas y la inversión relacionada al modelo APC."
    llm_oa = markdown.markdown(get_llm_analysis(p_oa))

    sections_html += f"""
    <h2>5. Acceso Abierto y Publicimetría Comercial</h2><div class='markdown-text'>{llm_oa}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{m_oa:.1f}%</div><div class="metric-label">Open Access Global</div></div>
        <div class="metric-card"><div class="metric-value">${m_apc:,.0f}</div><div class="metric-label">Costo APC Lista (Referencial)</div></div>
    </div>
    {html_oa_figs}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 6: Perfil Temático + Nube de Palabras
    # -------------------------------------------------------------------------
    print("Generando SubReporte 6/8: Perfil Temático...")
    m_gini = data.get('gini_topics', 0)
    m_dom = data.get('top_domain', 'Desconocido')

    html_top_figs = ""

    # ── Sunburst taxonómico ───────────────────────────────────────────────────
    if df_top is not None and not df_top.empty:
        df_top_ent = df_top
        if not df_top_ent.empty:
            top_topics = df_top_ent.sort_values('value', ascending=False).head(100)
            fig_sun = px.sunburst(top_topics, path=['domain', 'field', 'subfield', 'topic'],
                                  values='value', color='value',
                                  color_continuous_scale='Blues', title="Concentración Taxonómica")
            fig_sun.update_layout(height=600)
            html_top_figs += fig_to_html(fig_sun)

    # ── Nube de palabras ─────────────────────────────────────────────────────
    top_kw_list = []   # Para el prompt del LLM
    html_wordcloud = ""
    if df_kw is not None and not df_kw.empty and col_name in df_kw.columns:
        df_k = df_kw[df_kw[col_name] == entity_name].sort_values("freq", ascending=False).head(50)
        if not df_k.empty:
            freq_dict = dict(zip(df_k["keyword"], df_k["freq"]))
            top_kw_list = [kw for kw in list(freq_dict.keys())[:20]]

            # Intentar generar WordCloud como imagen base64
            try:
                from lib import wordcloud_helper as _wc
                img_bytes = _wc.generate_wordcloud_image(freq_dict, width=900, height=380)
                if img_bytes:
                    import base64
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    html_wordcloud = (
                        "<div style='text-align:center; margin: 18px 0;'>"
                        f"<img src='data:image/png;base64,{b64}' "
                        "style='max-width:100%; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.10);' "
                        "alt='Nube de palabras clave'/>"
                        "<p style='font-size:12px;color:#888;margin-top:6px;'>Vocabulario científico más frecuente</p>"
                        "</div>"
                    )
            except Exception as e:
                print(f"WordCloud no disponible en reporte: {e}")

            # Fallback a gráfica de barras si no hay wordcloud
            if not html_wordcloud:
                try:
                    fig_kw = da._render_keywords_section(df_kw, col_name, entity_name, return_fig=True)
                    if fig_kw:
                        html_top_figs += fig_to_html(fig_kw)
                except Exception:
                    pass

    # ── LLM: descripción enriquecida con keywords ─────────────────────────────
    kw_snippet = (", ".join(top_kw_list[:20]) + ".") if top_kw_list else "No disponible."
    p_top = (
        f"El investigador o institución ({entity_name}) presenta un enfoque principalmente en el dominio "
        f"'{m_dom}' y posee un Índice de Gini de concentración temática de {m_gini:.3f} "
        f"(donde cercano a 0 es foco puro, y 1 es amplia diversidad/dispersión temática). "
        f"Las 20 palabras clave más frecuentes en su producción son: {kw_snippet} "
        f"Genera un análisis formal que integre el dominio principal, el índice de Gini y las "
        f"palabras clave para describir la identidad temática de investigación."
    )
    llm_top = markdown.markdown(get_llm_analysis(p_top))

    sections_html += f"""
    <h2>6. Identidad Temática de Investigación</h2><div class='markdown-text'>{llm_top}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{m_gini:.3f}</div><div class="metric-label">Índice de Gini Temático</div></div>
        <div class="metric-card"><div class="metric-value" style="font-size:16px;">{m_dom}</div><div class="metric-label">Dominio Principal</div></div>
    </div>
    {html_wordcloud}
    {html_top_figs}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 7: Visibilidad
    # -------------------------------------------------------------------------
    print("Generando SubReporte 7/8: Visibilidad...")
    
    # Radar NATIVO
    html_rad = ""
    try:
        vis_cols = ['pct_pubmed','pct_doaj_indexed','pct_core_journal','pct_repository','pct_english','pct_cc_by']
        labels = ['PubMed', 'DOAJ', 'Core Journal', 'Repositorios', 'Inglés', 'CC-BY']
        vals = [data.get(c, 0) for c in vis_cols]
        if any(vals):
            fig_rad = go.Figure()
            fig_rad.add_trace(go.Scatterpolar(r=vals + [vals[0]], theta=labels + [labels[0]], fill='toself', name='Visibilidad', line=dict(color='#E39918')))
            fig_rad.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%")), height=350, margin=dict(t=30,b=30,l=30,r=30), title="Perfil de Indexación y Formato", template="plotly_white")
            html_rad = fig_to_html(fig_rad)
    except Exception as e: print("Error radar:", e)
    
    m_pub = data.get('pct_pubmed', 0)
    m_doaj = data.get('pct_doaj_indexed', 0)
    p_vis = f"Para ({entity_name}), el {m_pub:.1f}% de iteraciones se indiza en PubMed y {m_doaj:.1f}% reside en revistas DOAJ. Analiza muy objetivamente y de manera formal cómo estos medios de indexación y bases de datos contribuyen a la ubicuidad del conocimiento."
    llm_vis = markdown.markdown(get_llm_analysis(p_vis))

    sections_html += f"<h2>7. Visibilidad e Indización</h2><div class='markdown-text'>{llm_vis}</div>{html_rad}"

    # -------------------------------------------------------------------------
    # SECCIÓN 8: ODS
    # -------------------------------------------------------------------------
    print("Generando SubReporte 8/8: ODS...")
    html_ods = ""
    if not df_pap_ent.empty:
        try:
            html_ods = viz_ods.render_sdg_matrix(df_pap_ent, col_ods='ODS_ID')
        except: pass
        
    p_ods = f"En cuanto a los Objetivos de Desarrollo Sostenible (ODS), {entity_name} tiene publicaciones detectadas algorítmicamente en varias metas de la ONU. Ofrece un párrafo objetivo describiendo la creciente relevancia institucional de alinearse con los ODS."
    llm_ods = markdown.markdown(get_llm_analysis(p_ods))
    
    sections_html += f"<h2>8. Contribución al Desarrollo Sostenible (ODS)</h2><div class='markdown-text'>{llm_ods}</div>{html_ods}"
    
    # -------------------------------------------------------------------------
    # SECCIÓN 9: UMAP (Solo Investigador)
    # -------------------------------------------------------------------------
    if entity_type == 'inv':
        print("Generando SubReporte UMAP...")
        html_umap = ""
        df_umap = da.get_cached_data("umap_investigadores.parquet", entity_name=entity_context, institution_name=institution_name)
        if df_umap is None or df_umap.empty:
            df_umap = da.get_cached_data("umap_investigadores.parquet", institution_name=institution_name)
        if df_umap is not None and not df_umap.empty:
            fig_umap = go.Figure()
            otros = df_umap[df_umap['academic_name'] != entity_name]
            sel_row = df_umap[df_umap['academic_name'] == entity_name]
            
            max_docs = df_umap['num_documents'].max() if 'num_documents' in df_umap.columns else 1
            sizeref = 2.0 * max(max_docs, 1) / (50. ** 2)

            if not otros.empty:
                fig_umap.add_trace(go.Scatter(x=otros['umap_x'], y=otros['umap_y'], mode='markers', name='Resto del padrón', text=otros['academic_name'], marker=dict(size=otros['num_documents'].fillna(0).clip(lower=0.1), sizemode='area', sizeref=sizeref, sizemin=2, color='#003D64', opacity=0.3, line=dict(width=1, color='darkgray'))))
            if not sel_row.empty:
                fig_umap.add_trace(go.Scatter(x=sel_row['umap_x'], y=sel_row['umap_y'], mode='markers', name=entity_name, text=sel_row['academic_name'], marker=dict(size=sel_row['num_documents'].fillna(0).clip(lower=0.1), sizemode='area', sizeref=sizeref, sizemin=2, color='#E8442A', symbol='circle', line=dict(width=2, color='#E8442A'))))
                
            fig_umap.update_layout(title="Mapa de Desempeño Cuantitativo (UMAP)", hovermode="closest", template="plotly_white")
            html_umap = fig_to_html(fig_umap)
            
        p_umap = f"Describe formalmente que la proyección de reducción de dimensionalidad UMAP nos ayuda a comparar visualmente al investigador {entity_name} con sus pares, tomando en cuenta las métricas de volumen, FWCI, Citas y Excelencia (%Top10)."
        llm_umap = markdown.markdown(get_llm_analysis(p_umap))
        
        sections_html += f"<h2>9. Posicionamiento en el Padrón (UMAP)</h2><div class='markdown-text'>{llm_umap}</div>{html_umap}"

    # -------------------------------------------------------------------------
    # SECCIÓN FINAL: Redes de Colaboración Internacional
    # -------------------------------------------------------------------------
    sec_num = 10 if entity_type == 'inv' else 9
    print(f"Generando SubReporte {sec_num}: Colaboración Internacional...")
    m_intl = data.get('pct_international', 0)

    html_collab_figs = ""

    # ── Mapa mundi de países colaboradores ──────────────────────────────────
    top_countries = []
    if not df_pap_ent.empty:
        try:
            import pytz
            from collections import Counter
            cnt = Counter()
            col_countries = 'countries' if 'countries' in df_pap_ent.columns else 'all_country_codes'
            if col_countries in df_pap_ent.columns:
                for val in df_pap_ent[col_countries]:
                    if isinstance(val, (list, np.ndarray)):
                        cnt.update(c for c in val if c and c not in ('MX', ''))
            if cnt:
                df_cnt = pd.DataFrame(cnt.most_common(80), columns=["iso_a2", "papers"])
                # Convertir ISO-2 → ISO-3 (Plotly necesita ISO-3 para choropleth)
                df_cnt['iso_a3'] = df_cnt['iso_a2'].map(da.ISO2_TO_ISO3).fillna(df_cnt['iso_a2'])
                df_cnt['País'] = df_cnt['iso_a2'].apply(lambda x: pytz.country_names.get(x, x))
                top_countries = df_cnt.head(10)['País'].tolist()
                fig_choro = px.choropleth(
                    df_cnt, locations="iso_a3", locationmode="ISO-3",
                    color="papers",
                    color_continuous_scale="Blues",
                    title="Países Colaboradores (Excluyendo México)",
                    hover_name="País",
                    labels={"papers": "Papers conjuntos"},
                )
                fig_choro.update_layout(
                    height=420, margin=dict(t=40, b=0, l=0, r=0),
                    geo=dict(showframe=False, showcoastlines=True,
                             bgcolor="rgba(0,0,0,0)",
                             showland=True, landcolor="#f0f0f0")
                )
                html_collab_figs += fig_to_html(fig_choro)
        except Exception as e:
            print("Error choropleth:", e)

    # ── Gráfica temporal % Colaboración Internacional ───────────────────────
    if not df_ann_ent.empty and 'pct_international' in df_ann_ent.columns:
        try:
            _cur_yr_c = datetime.now().year
            _x_min_c = max(1950, int(df_ann_ent['year'].min()))
            df_intl_ann = df_ann_ent.dropna(subset=['pct_international']).sort_values('year')
            if not df_intl_ann.empty:
                fig_intl = px.line(
                    df_intl_ann, x='year', y='pct_international',
                    markers=True,
                    title="Evolución Anual: % Colaboración Internacional",
                    range_x=[_x_min_c, _cur_yr_c],
                    labels={'pct_international': '% Colaboración Intl.', 'year': 'Año'}
                )
                fig_intl.update_traces(line=dict(color='#003F8A', width=2), marker=dict(color='#E39918', size=7))
                fig_intl.update_xaxes(tickformat='d', dtick=5)
                fig_intl.update_layout(template='plotly_white', height=280, margin=dict(t=40, b=10))
                html_collab_figs += fig_to_html(fig_intl)
        except Exception as e:
            print("Error intl temporal:", e)

    # ── Red Neo4j ────────────────────────────────────────────────────────────
    html_network = ""
    try:
        neo = Neo4jGraphStore()
        graph_data = None
        if entity_type == "inst":
            if entity_name == "FACULTAD DE CIENCIAS":
                graph_data = neo.get_collaboration_sample_graph(
                    "FACULTAD DE CIENCIAS", "INSTITUTO DE CIENCIAS NUCLEARES", limit=100
                )
            else:
                graph_data = neo.get_funder_sample_graph(entity_name, limit=100)
        neo.close()

        if graph_data and graph_data.get("nodes"):
            net = Network(height="400px", width="100%", bgcolor="#ffffff", font_color="black", notebook=False)
            node_ids = set()
            for n in graph_data["nodes"]:
                node_id = n["id"]
                node_ids.add(node_id)
                node_class = n.get("label", "Unknown")
                visible_name = n.get("title", str(node_id))
                color_map_net = {"Academic": "#FFC0CB", "Paper": "#ADD8E6",
                                  "Institution": "#E39918", "Entity": "#E39918", "Funder": "#8FBC8F"}
                color = color_map_net.get(node_class, "#97C2FC")
                net.add_node(node_id, label=visible_name, title=f"{node_class}: {visible_name}",
                             color=color, group=node_class)
            for e in graph_data["edges"]:
                if e["source"] in node_ids and e["target"] in node_ids:
                    net.add_edge(e["source"], e["target"], title=e.get("label", ""))
            net.set_options('{"physics": {"forceAtlas2Based": {"springLength": 100}, "minVelocity": 0.75, "solver": "forceAtlas2Based"}}')
            safe_html = __import__('html').escape(net.generate_html())
            html_network = (
                "<div class='chart'><h3>Red Topológica de Colaboración</h3>"
                f"<iframe srcdoc='{safe_html}' width='100%' height='420px' "
                "style='border:1px solid #ddd; border-radius: 8px;'></iframe></div>"
            )
    except Exception as e:
        print(f"Error red Neo4j: {e}")

    # ── LLM con datos reales ─────────────────────────────────────────────────
    countries_snippet = ", ".join(top_countries[:10]) if top_countries else "No disponible"
    p_collab = (
        f"La entidad ({entity_name}) tiene un {m_intl:.1f}% de publicaciones co-autorizadas "
        f"internacionalmente. Sus principales países colaboradores son: {countries_snippet}. "
        f"Genera un párrafo formal analizando la red de colaboración internacional, "
        f"destacando los países con mayor vínculo y lo que esto implica para su posicionamiento global."
    )
    llm_collab = markdown.markdown(get_llm_analysis(p_collab))

    sections_html += f"""
    <h2>{sec_num}. Redes de Colaboración Internacional</h2><div class='markdown-text'>{llm_collab}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{m_intl:.1f}%</div><div class="metric-label">Colaboración Internacional</div></div>
    </div>
    {html_collab_figs}
    {html_network}
    """

    # 4. Assemble HTML
    # 4. Assemble HTML
    print("Ensamblando HTML final...")
    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Reporte Bibliométrico: {entity_name}</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Merriweather:ital,wght@0,300;0,400;0,700;1,300&family=Open+Sans:wght@400;600&display=swap');
            body {{ font-family: 'Merriweather', Georgia, serif; margin: 40px auto; max-width: 1000px; line-height: 1.7; color: #222; background-color: #fbfbfb; }}
            h1 {{ font-family: 'Open Sans', Arial, sans-serif; color: #111; border-bottom: 3px double #111; padding-bottom: 15px; font-size: 32px; text-align: center; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }}
            h2 {{ font-family: 'Open Sans', Arial, sans-serif; color: #333; margin-top: 40px; border-bottom: 1px solid #ccc; padding-bottom: 5px; font-size: 20px; text-transform: uppercase; letter-spacing: 0.5px; }}
            
            /* Journal Text Layout */
            .markdown-text {{ font-size: 15px; text-align: justify; margin-bottom: 30px; column-count: 2; column-gap: 40px; }}
            .markdown-text p {{ margin: 0 0 15px 0; text-indent: 1.5em; }}
            .markdown-text p:first-of-type {{ text-indent: 0; }}
            .markdown-text ul {{ text-align: left; margin: 0 0 15px 0; padding-left: 20px; }}
            .markdown-text strong {{ color: #111; font-family: 'Open Sans', sans-serif; }}
            
            /* Dropcap for Executive Summary */
            .summary-box {{ padding: 20px; margin: 25px 0; font-size: 16px; border-top: 2px solid #E39918; border-bottom: 2px solid #E39918; text-align: justify; }}
            .summary-box p:first-of-type::first-letter {{ color: #003D64; float: left; font-size: 55px; line-height: 45px; padding-top: 4px; padding-right: 8px; padding-left: 3px; font-family: 'Georgia', serif; }}
            
            /* Minimalist Metrics Grid */
            .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-bottom: 40px; margin-top: 10px; }}
            .metric-card {{ background: transparent; padding: 15px 5px; text-align: center; border-bottom: 1px dashed #ccc; }}
            .metric-value {{ font-family: 'Open Sans', sans-serif; font-size: 26px; font-weight: 600; color: #003D64; }}
            .metric-label {{ font-family: 'Open Sans', sans-serif; font-size: 12px; color: #555; text-transform: uppercase; letter-spacing: 0.5px; }}
            
            .chart {{ margin-top: 20px; margin-bottom: 40px; width: 100%; overflow: hidden; background: #fff; border: 1px solid #eaeaea; box-shadow: 0 1px 3px rgba(0,0,0,0.05); padding: 15px; box-sizing: border-box; }}
            
            /* Print adjustments for PDF export */
            @media print {{ 
                body {{ background-color: #fff; }}
                .chart {{ page-break-inside: avoid; box-shadow: none; border: none; }}
                h2 {{ page-break-after: avoid; }}
            }}
        </style>
    </head>
    <body>
        <div style="text-align: right; color: #666; font-size: 12px;">Generado por Inteligencia Artificial (SNII Info TlachIA)</div>
        <h1>Informe Bibliométrico</h1>
        <p style="background:none; border:none; padding:0; font-size:18px;"><strong>Perfil Analizado:</strong> {entity_name} ({'Institución (Capacidad Instalada)' if (entity_type == 'inst' and view_mode == 'capacidad_instalada') else 'Institución (Producción Institucional)' if entity_type == 'inst' else 'Investigador'})</p>

        {sections_html}
        
    </body>
    </html>
    """
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    print("Reporte generado exitosamente.")
    return file_path

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=['inst', 'inv'], required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--entity", required=False, help="Contexto institucional para cargar la caché del investigador.")
    parser.add_argument("--institution", required=False, help="Institución de acreditación.")
    parser.add_argument("--view_mode", default="capacidad_instalada", choices=["capacidad_instalada", "produccion_institucional"], help="Modo de vista.")
    args = parser.parse_args()
    try:
        path = generate_html_report(args.type, args.name, args.entity, args.institution, args.view_mode)
        print(f"Ruta: {path}")
    except Exception as e:
        print(f"Error fatal generando reporte: {e}")
        import traceback
        traceback.print_exc()
