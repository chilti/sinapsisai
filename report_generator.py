import os
import json
import numpy as np
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
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

DEFAULT_SYSTEM_PROMPT = (
    "Eres un Analista Cienciométrico Senior. Tu función es redactar informes técnicos y diagnósticos "
    "analíticos de nivel ejecutivo para autoridades universitarias, directores de institutos y evaluadores. "
    "Criterios estrictos de redacción: "
    "1. Tono exclusivamente analítico, sobrio, neutro, descriptivo y académico sintético. "
    "2. Prohibido terminantemente el uso de adjetivos laudatorios, autocelebratorios o hiperbólicos "
    "(ej. 'extraordinario', 'notable', 'impresionante', 'fructífero', 'magnífico', 'sólido', 'relevante', 'pionero', 'vanguardista', 'brillante', 'espectacular'). "
    "3. Concisión absoluta: oraciones cortas, densas en información cuantitativa y libres de retórica introductoria. "
    "4. Todas las conclusiones deben estar directamente fundamentadas en las cifras provistas; no realices juicios de valor. "
    "5. Contextualiza los benchmarks: FWCI 1.0 representa la media mundial en la disciplina y año de publicación; deciles Top 10% y cuartiles Q1. "
    "6. Mantén una estructura sintética con párrafos concisos y directos."
)


def _safe_float(val, default: float = 0.0) -> float:
    try:
        if val is None or pd.isna(val) or np.isnan(float(val)):
            return default
        return float(val)
    except Exception:
        return default

def _safe_int(val, default: int = 0) -> int:
    try:
        if val is None or pd.isna(val) or np.isnan(float(val)):
            return default
        return int(float(val))
    except Exception:
        return default

def get_llm_analysis(prompt: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT, model: str = None) -> str:
    """Realiza la consulta al LLM (C3 vLLM GPT-OSS 120B o local) con fallback automático al modelo local."""
    import time
    import re

    raw_model = model or LLMConfig.get_model_name("gpt-oss-120b")
    fallback_model = LLMConfig.get_fallback_model_name("openai/default")

    models_to_try = [raw_model]
    if raw_model != fallback_model and LLMConfig.get_clean_model_name(raw_model) != LLMConfig.get_clean_model_name(fallback_model):
        models_to_try.append(fallback_model)

    last_err = None
    for current_model in models_to_try:
        try:
            auth_url = LLMConfig.get_auth_url(current_model)
            api_key = LLMConfig.get_api_key(current_model)
            llm_model = LLMConfig.get_clean_model_name(current_model)

            url = auth_url.rstrip("/") + "/chat/completions"

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            if LLMConfig.is_c3_gpt(current_model):
                host_hdr = os.getenv("C3_LLM_HOST_HEADER_GPT", "gptoss.c3.unam.mx")
                if host_hdr:
                    headers["Host"] = host_hdr
            elif LLMConfig.is_c3(current_model):
                host_hdr = os.getenv("C3_LLM_HOST_HEADER", "kimi.c3.unam.mx")
                if host_hdr:
                    headers["Host"] = host_hdr

            payload = {
                "model": llm_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,  # Máxima sobriedad y consistencia factual
                "max_tokens": 3500   # Margen amplio para modelos con reasoning tokens
            }

            for attempt in range(2):
                try:
                    with httpx.Client(verify=False, timeout=60.0) as client:
                        response = client.post(url, headers=headers, json=payload)
                        response.raise_for_status()
                        data = response.json()
                        choice = data["choices"][0]
                        msg_obj = choice["message"]
                        content = (msg_obj.get("content") or "").strip()

                        if content:
                            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                            content = re.sub(r'<thought>.*?</thought>', '', content, flags=re.DOTALL).strip()

                        if not content:
                            finish_reason = choice.get("finish_reason")
                            if finish_reason == "length" and attempt < 1:
                                payload["max_tokens"] = 4500
                                time.sleep(1.0)
                                continue
                            return "*(Interpretación analítica sintetizada en las métricas e indicadores de esta sección.)*"

                        return content
                except Exception as e_req:
                    if attempt < 1:
                        time.sleep(1.0)
                    else:
                        raise e_req
        except Exception as e_m:
            last_err = e_m
            print(f"[WARN] Error en get_llm_analysis con modelo '{current_model}': {e_m}. Intentando fallback...")
            continue

    return f"*(Análisis cuantitativo automático no disponible: {str(last_err)})*"


def get_report_path(entity_type: str, entity_name: str, view_mode: str = "capacidad_instalada") -> tuple[str, str]:
    safe_name = "".join([c if c.isalnum() else "_" for c in entity_name])
    suffix = f"_{view_mode}" if entity_type == "inst" else ""
    return os.path.join(REPORTS_DIR, f"report_{entity_type}{suffix}_{safe_name}.html"), safe_name


def fig_to_html(fig) -> str:
    if not fig: return ""
    return "<div class='chart'>" + pio.to_html(fig, full_html=False, include_plotlyjs='cdn') + "</div>"


def _notify_step(callback, step: int, total: int, msg: str):
    if callback:
        try:
            callback(step, total, msg)
        except Exception:
            pass


def generate_html_report(
    entity_type: str, 
    entity_name: str, 
    entity_context: str = None, 
    institution_name: str = None, 
    view_mode: str = "capacidad_instalada",
    save_to_disk: bool = True,
    progress_callback = None,
    model: str = None
) -> str:
    """Genera un reporte analítico exhaustivo y sobrio en formato HTML para institución o investigador."""
    # Wrapper local para que todas las llamadas de prompts en este reporte utilicen el modelo solicitado (o default) con fallback automático
    _orig_get_llm = get_llm_analysis
    get_llm_analysis = lambda p, s=DEFAULT_SYSTEM_PROMPT: _orig_get_llm(p, s, model=model)

    if str(entity_type).lower() in ["researcher", "investigador", "inv"]:
        entity_type = "inv"
    elif str(entity_type).lower() in ["institution", "institucion", "inst"]:
        entity_type = "inst"

    file_path, safe_name = get_report_path(entity_type, entity_name, view_mode)
    print(f"Iniciando generación de reporte para {entity_name} ({entity_type}) con LLM: {model or os.getenv('LLM_MODEL', 'gpt-oss-120b')}...")
    
    col_name = 'entity_name' if entity_type == "inst" else 'academic_name'
    ent_param = entity_name if entity_type == "inst" else entity_context
    ac_param  = None if entity_type == "inst" else entity_name

    # Normalización para entidad nacional 'MÉXICO' o 'MEXICO'
    if entity_type == "inst" and (str(entity_name).upper() in ["MEXICO", "MÉXICO"] or str(institution_name or "").upper() in ["MEXICO", "MÉXICO"]):
        institution_name = "MEXICO"
        ent_param = None

    df_tot = da.get_cached_data("institucion_total.parquet" if entity_type == "inst" else "investigador_total.parquet", entity_name=ent_param, academic_name=ac_param, institution_name=institution_name, view_mode=view_mode)
    df_ann = da.get_cached_data("institucion_annual.parquet" if entity_type == "inst" else "investigador_annual.parquet", entity_name=ent_param, academic_name=ac_param, institution_name=institution_name, view_mode=view_mode)
    df_pap = da.get_cached_data("papers_institucion.parquet" if entity_type == "inst" else "papers_profesor.parquet", entity_name=ent_param, academic_name=ac_param, institution_name=institution_name, view_mode=view_mode)
    df_top = da.get_cached_data("topics_institucion.parquet" if entity_type == "inst" else "topics_investigador.parquet", entity_name=ent_param, academic_name=ac_param, institution_name=institution_name, view_mode=view_mode)
    df_kw = da.get_cached_data("keywords_institucion.parquet" if entity_type == "inst" else "keywords_investigador.parquet", entity_name=ent_param, academic_name=ac_param, institution_name=institution_name, view_mode=view_mode)
    
    if df_tot is None or df_tot.empty:
        raise ValueError(f"Datos totales no disponibles en caché para: {entity_name}")
        
    data = df_tot.iloc[0].to_dict()
    df_ann_ent = df_ann.sort_values('year') if df_ann is not None and not df_ann.empty else pd.DataFrame()
    df_pap_ent = df_pap if df_pap is not None and not df_pap.empty else pd.DataFrame()

    cur_year = datetime.now().year
    m_docs = _safe_int(data.get('num_documents', 0))
    m_cites = _safe_int(data.get('citations', 0))
    m_fwci = _safe_float(data.get('fwci_avg', 0.0))
    raw_perc = _safe_float(data.get('percentile_avg', 0.0))
    m_perc = raw_perc * 100 if (0.0 < raw_perc <= 1.0) else raw_perc
    m_top10 = _safe_float(data.get('pct_top_10', 0.0))
    m_top1 = _safe_float(data.get('pct_1', 0.0))
    m_oa = _safe_float(data.get('pct_open_access', 0.0))
    m_intl = _safe_float(data.get('pct_international', 0.0))
    m_hindex = _safe_int(data.get('h_index', 0))
    m_cites_per_paper = _safe_float(data.get('citations_per_paper'), (m_cites / m_docs) if m_docs > 0 else 0.0)
    m_vel = _safe_float(data.get('velocity_avg', 0.0))
    m_apc = _safe_float(data.get('apc_paid_usd', 0.0))
    m_dom = str(data.get('top_domain') or 'No especificado')
    m_gini = _safe_float(data.get('gini_topics', 0.0))

    # Cuartiles / Tiers de Prestigio
    m_t1_count = _safe_int(data.get('t1_count', 0))
    m_t2_count = _safe_int(data.get('t2_count', 0))
    m_t3_count = _safe_int(data.get('t3_count', 0))
    m_t4_count = _safe_int(data.get('t4_count', 0))

    m_pct_t1 = _safe_float(data.get('pct_t1', 0.0))
    m_pct_t2 = _safe_float(data.get('pct_t2', 0.0))
    m_pct_t3 = _safe_float(data.get('pct_t3', 0.0))
    m_pct_t4 = _safe_float(data.get('pct_t4', 0.0))

    # Recalcular porcentajes de cuartiles si vienen en 0 pero existen counts
    total_tiers = m_t1_count + m_t2_count + m_t3_count + m_t4_count
    if (m_pct_t1 + m_pct_t2 + m_pct_t3 + m_pct_t4) == 0.0 and total_tiers > 0:
        m_pct_t1 = (m_t1_count / total_tiers) * 100
        m_pct_t2 = (m_t2_count / total_tiers) * 100
        m_pct_t3 = (m_t3_count / total_tiers) * 100
        m_pct_t4 = (m_t4_count / total_tiers) * 100

    # Dinámica temporal y madurez de citación
    m_half_life = _safe_float(data.get('half_life_avg', 0.0))
    m_recent_3yr = _safe_int(data.get('recent_cites_3yr', 0))
    m_early_impact = _safe_float(data.get('early_impact', 0.0))
    m_avg_authors = _safe_float(data.get('avg_author_count', 0.0))
    m_pct_apc = _safe_float(data.get('pct_apc', 0.0))

    # Rango temporal
    if not df_ann_ent.empty and 'year' in df_ann_ent.columns:
        yr_min = int(df_ann_ent['year'].min())
        yr_max = int(df_ann_ent['year'].max())
    else:
        yr_min, yr_max = 1990, cur_year

    sections_html = ""

    # -------------------------------------------------------------------------
    # SECCIÓN 1: Resumen Ejecutivo y Diagnóstico Global
    # -------------------------------------------------------------------------
    print("Generando SubReporte 1/12: Resumen Ejecutivo...")
    _notify_step(progress_callback, 1, 12, "Redactando Resumen Ejecutivo y Diagnóstico Global")
    
    p_exec = f"""
    Redacta un Resumen Ejecutivo analítico y sintético para {entity_name} ({'Institución / Dependencia' if entity_type == 'inst' else 'Investigador'}), basado en los siguientes datos consolidados:
    - Periodo registrado: {yr_min} a {yr_max}.
    - Producción total indexada: {m_docs:,} documentos.
    - Citas acumuladas: {m_cites:,} (densidad de {m_cites_per_paper:.2f} citas por documento).
    - Índice H: {m_hindex}.
    - FWCI Promedio (Impacto Ponderado por Campo): {m_fwci:.2f} (benchmark: 1.00 es la media mundial).
    - Concentración en decil de élite (% Top 10% global): {m_top10:.1f}%.
    - Proporción en Cuartil 1 (% Tier 1 / Q1): {m_pct_t1:.1f}%.
    - Acceso Abierto: {m_oa:.1f}%.
    - Colaboración internacional: {m_intl:.1f}% de las publicaciones.
    - Dominio disciplinar: {m_dom}.

    Instrucciones estrictas:
    - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
    - Estructura la respuesta en exactamente dos párrafos breves (máximo 4 líneas cada uno).
    - Párrafo 1: Descripción objetiva del volumen, trayectoria temporal y masa citacional.
    - Párrafo 2: Diagnóstico factual del impacto normalizado (FWCI), posicionamiento en cuartil Q1 y apertura científica, omitiendo juicios laudatorios o adjetivos grandilocuentes.
    """
    llm_exec = markdown.markdown(get_llm_analysis(p_exec))

    sections_html += f"""
    <h2>1. Resumen Ejecutivo y Diagnóstico Global</h2>
    <div class="summary-box markdown-text">{llm_exec}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{int(m_docs):,}</div><div class="metric-label">Documentos</div></div>
        <div class="metric-card"><div class="metric-value">{int(m_cites):,}</div><div class="metric-label">Citas Totales</div></div>
        <div class="metric-card"><div class="metric-value">{m_cites_per_paper:.1f}</div><div class="metric-label">Citas / Doc</div></div>
        <div class="metric-card"><div class="metric-value">{int(m_hindex)}</div><div class="metric-label">Índice H</div></div>
        <div class="metric-card"><div class="metric-value">{m_fwci:.2f}</div><div class="metric-label">FWCI Promedio</div></div>
        <div class="metric-card"><div class="metric-value">{m_top10:.1f}%</div><div class="metric-label">% Top 10% Global</div></div>
        <div class="metric-card"><div class="metric-value">{m_pct_t1:.1f}%</div><div class="metric-label">% Tier 1 (Q1)</div></div>
        <div class="metric-card"><div class="metric-value">{m_oa:.1f}%</div><div class="metric-label">Open Access</div></div>
    </div>
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 2: Trayectoria Temporal y Tipología Documental
    # -------------------------------------------------------------------------
    print("Generando SubReporte 2/12: Trayectoria y Tipología...")
    _notify_step(progress_callback, 2, 12, "Analizando Trayectoria Temporal y Tipología Documental")
    html_hist_fig = ""
    top_prod_years_str = "No disponible"
    docs_last_5 = 0
    pct_last_5 = 0.0

    if not df_ann_ent.empty:
        _x_min = max(1960, yr_min)
        df_sorted_prod = df_ann_ent.sort_values('num_documents', ascending=False)
        top_prod_years = df_sorted_prod.head(3)['year'].tolist()
        top_prod_years_str = ", ".join(str(int(y)) for y in top_prod_years)
        
        recent_5 = df_ann_ent[df_ann_ent['year'] >= (cur_year - 5)]
        if not recent_5.empty:
            docs_last_5 = int(recent_5['num_documents'].sum())
            pct_last_5 = (docs_last_5 / m_docs * 100) if m_docs > 0 else 0.0

        fig_hist = make_subplots(specs=[[{"secondary_y": True}]])
        fig_hist.add_trace(
            go.Bar(
                x=df_ann_ent['year'], y=df_ann_ent['num_documents'],
                name="Documentos", marker_color="#003D64", opacity=0.85
            ),
            secondary_y=False,
        )
        if 'citations' in df_ann_ent.columns:
            fig_hist.add_trace(
                go.Scatter(
                    x=df_ann_ent['year'], y=df_ann_ent['citations'],
                    name="Citas recibidas", mode="lines+markers",
                    line=dict(color="#E39918", width=2.5),
                    marker=dict(size=5, color="#B87300")
                ),
                secondary_y=True,
            )
        fig_hist.update_xaxes(title_text="Año de publicación", tickformat='d', dtick=5, range=[_x_min - 0.5, cur_year + 0.5])
        fig_hist.update_yaxes(title_text="Documentos publicados", secondary_y=False)
        fig_hist.update_yaxes(title_text="Citas totales del año", secondary_y=True)
        fig_hist.update_layout(
            title="Evolución Histórica de Publicaciones y Citaciones",
            template="plotly_white",
            height=360,
            margin=dict(t=40, b=10, l=10, r=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        html_hist_fig += fig_to_html(fig_hist)

    doc_types_str = "No disponible"
    if not df_pap_ent.empty:
        col_type = 'wf.type' if 'wf.type' in df_pap_ent.columns else ('source_type' if 'source_type' in df_pap_ent.columns else None)
        if col_type and col_type in df_pap_ent.columns:
            s_clean = df_pap_ent[col_type].dropna().astype(str).str.strip()
            s_clean = s_clean[s_clean != '']
            type_counts = s_clean.value_counts().head(6)
            if not type_counts.empty:
                doc_types_str = ", ".join(f"{k}: {v}" for k, v in type_counts.items())
                fig_types = px.pie(
                    names=type_counts.index, values=type_counts.values,
                    title="Distribución por Tipología Documental",
                    hole=0.4,
                    color_discrete_sequence=['#003D64', '#006699', '#E39918', '#8B9DC3', '#D0D7DE', '#57606A']
                )
                fig_types.update_layout(height=280, margin=dict(t=40, b=10, l=10, r=10))
                html_hist_fig += fig_to_html(fig_types)

    p_hist = f"""
    Sintetiza la trayectoria temporal de producción científica de {entity_name}.
    Datos:
    - Periodo: {yr_min} a {yr_max} ({max(1, yr_max - yr_min + 1)} años).
    - Total de documentos: {m_docs:,}.
    - Años con mayor volumen: {top_prod_years_str}.
    - Quinquenio reciente ({cur_year-5} a {cur_year}): {docs_last_5} documentos ({pct_last_5:.1f}% del corpus).
    - Promedio de autores por publicación: {m_avg_authors:.1f}.
    - Tipologías documentales: {doc_types_str}.

    Instrucciones estrictas:
    - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
    - Redacta un párrafo analítico y sintético (máximo 4 líneas) sobre la estabilidad temporal de la producción y la composición documental, sin retórica elogiosa.
    """
    llm_hist = markdown.markdown(get_llm_analysis(p_hist))

    sections_html += f"""
    <h2>2. Trayectoria Temporal y Tipología de Producción</h2>
    <div class='markdown-text'>{llm_hist}</div>
    {html_hist_fig}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 3: Excelencia, Impacto Normalizado y Cuartiles de Prestigio
    # -------------------------------------------------------------------------
    print("Generando SubReporte 3/12: Excelencia, FWCI y Cuartiles...")
    _notify_step(progress_callback, 3, 12, "Evaluando Excelencia, FWCI y Distribución por Cuartiles")
    html_fwci_fig = ""
    if not df_ann_ent.empty and 'fwci_avg' in df_ann_ent.columns:
        _x_min_f = max(1960, yr_min)
        df_fwci_clean = df_ann_ent.dropna(subset=['fwci_avg']).sort_values('year')
        if not df_fwci_clean.empty:
            fig_fwci = px.line(
                df_fwci_clean, x='year', y='fwci_avg', markers=True,
                title="Evolución del Impacto Ponderado por Campo (FWCI Anual)",
                range_x=[_x_min_f - 0.5, cur_year + 0.5],
                labels={'fwci_avg': 'FWCI Promedio', 'year': 'Año de publicación'}
            )
            fig_fwci.add_hline(y=1.0, line_dash="dash", line_color="#D73A49", annotation_text="Media Mundial (1.00)")
            fig_fwci.update_traces(line=dict(color='#003D64', width=2), marker=dict(color='#E39918', size=6))
            fig_fwci.update_xaxes(tickformat='d', dtick=5)
            fig_fwci.update_layout(template="plotly_white", height=300, margin=dict(t=40, b=10, l=10, r=10))
            html_fwci_fig = fig_to_html(fig_fwci)

    # Gráfica de Cuartiles / Tiers de Prestigio
    html_tiers_fig = ""
    try:
        tier_names = ['Tier 1 (Q1)', 'Tier 2 (Q2)', 'Tier 3 (Q3)', 'Tier 4 (Q4)']
        tier_pcts = [m_pct_t1, m_pct_t2, m_pct_t3, m_pct_t4]
        tier_counts = [m_t1_count, m_t2_count, m_t3_count, m_t4_count]
        if any(p > 0 for p in tier_pcts):
            fig_tiers = go.Figure(go.Bar(
                x=tier_pcts,
                y=tier_names,
                orientation='h',
                marker=dict(color=['#003D64', '#006699', '#8B9DC3', '#D0D7DE']),
                text=[f"{p:.1f}% ({c:,} docs)" for p, c in zip(tier_pcts, tier_counts)],
                textposition='auto'
            ))
            fig_tiers.update_layout(
                title="Distribución de Publicaciones por Cuartil de Impacto (Tiers Q1-Q4)",
                xaxis=dict(title="Porcentaje del total (%)", range=[0, max(100, max(tier_pcts) * 1.15)]),
                yaxis=dict(autorange="reversed"),
                height=240,
                margin=dict(t=40, b=10, l=10, r=10),
                template="plotly_white"
            )
            html_tiers_fig = fig_to_html(fig_tiers)
    except Exception as e:
        print("Error en gráfica de cuartiles:", e)

    p_exc = f"""
    Evalúa el perfil de impacto normalizado y prestigio editorial de {entity_name}.
    Datos:
    - FWCI Promedio (Impacto Ponderado por Campo): {m_fwci:.2f} (1.00 es la media mundial de citación disciplinar).
    - Percentil Promedio Normalizado: {m_perc:.1f}/100.
    - Obras en decil de excelencia (% Top 10% más citado del mundo): {m_top10:.1f}%.
    - Obras en percentil de élite (% Top 1% más citado del mundo): {m_top1:.1f}%.
    - Distribución por Cuartiles: Tier 1 (Q1) {m_pct_t1:.1f}%, Tier 2 (Q2) {m_pct_t2:.1f}%, Tier 3 (Q3) {m_pct_t3:.1f}%, Tier 4 (Q4) {m_pct_t4:.1f}%.

    Instrucciones estrictas:
    - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
    - Redacta un párrafo analítico sobrio y sintético (máximo 4 líneas) que interprete la concentración en el primer cuartil (Q1) y el desempeño del FWCI frente a la media mundial, con lenguaje neutral y moderado.
    """
    llm_exc = markdown.markdown(get_llm_analysis(p_exc))

    sections_html += f"""
    <h2>3. Excelencia, Impacto Normalizado y Cuartiles de Prestigio</h2>
    <div class='markdown-text'>{llm_exc}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{m_fwci:.2f}</div><div class="metric-label">FWCI Promedio</div></div>
        <div class="metric-card"><div class="metric-value">{m_perc:.1f}</div><div class="metric-label">Percentil Promedio</div></div>
        <div class="metric-card"><div class="metric-value">{m_top10:.1f}%</div><div class="metric-label">% Top 10% Global</div></div>
        <div class="metric-card"><div class="metric-value">{m_pct_t1:.1f}%</div><div class="metric-label">% Tier 1 (Q1)</div></div>
    </div>
    {html_tiers_fig}
    {html_fwci_fig}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 4: Ecosistema Editorial y Publicaciones Emblemáticas
    # -------------------------------------------------------------------------
    print("Generando SubReporte 4/12: Ecosistema Editorial e Hitos...")
    _notify_step(progress_callback, 4, 12, "Analizando Ecosistema Editorial e Hitos de Investigación")
    html_journals_fig = ""
    top_journals_list = []

    if not df_pap_ent.empty and 'Source' in df_pap_ent.columns:
        df_src = df_pap_ent['Source'].dropna()
        df_src = df_src[df_src != '']
        if not df_src.empty:
            j_counts = df_src.value_counts().head(12)
            top_journals_list = [f"{k} ({v} docs)" for k, v in j_counts.items()]
            
            fig_j = px.bar(
                x=j_counts.values, y=j_counts.index,
                orientation='h',
                title="Principales Revistas y Canales de Publicación (Top 12)",
                labels={'x': 'Número de Artículos', 'y': 'Revista / Fuente'},
                color=j_counts.values,
                color_continuous_scale="Blues"
            )
            fig_j.update_layout(yaxis={'categoryorder': 'total ascending'}, height=360, margin=dict(t=40, b=10, l=10, r=10), template="plotly_white")
            fig_j.update_coloraxes(showscale=False)
            html_journals_fig = fig_to_html(fig_j)

    # Tabla de las 5 publicaciones con mayor repercusión citacional
    html_top_papers = ""
    if not df_pap_ent.empty and 'Title' in df_pap_ent.columns:
        try:
            sort_col = 'citations' if 'citations' in df_pap_ent.columns else 'year'
            df_top_p = df_pap_ent.dropna(subset=['Title']).sort_values(sort_col, ascending=False).head(5)
            if not df_top_p.empty:
                rows_html = ""
                for _, pr in df_top_p.iterrows():
                    p_title = pr.get('Title', 'Sin título')
                    p_year = int(pr.get('year', 0)) if pd.notnull(pr.get('year')) else '-'
                    p_cites = int(pr.get('citations', 0)) if pd.notnull(pr.get('citations')) else 0
                    p_fwci = f"{float(pr.get('fwci', 0.0)):.2f}" if pd.notnull(pr.get('fwci')) else '-'
                    p_src = pr.get('Source', 'Fuente no especificada') or 'Fuente no especificada'
                    p_doi = pr.get('doi', '')
                    doi_link = f"<a href='{p_doi}' target='_blank' style='color:#003D64;text-decoration:underline;'>DOI</a>" if p_doi else ""
                    rows_html += f"""
                    <tr>
                        <td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;font-size:13px;line-height:1.4;'><strong>{p_title}</strong><br><span style='color:#6b7280;font-size:11.5px;'>{p_src} ({p_year}) {doi_link}</span></td>
                        <td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:center;font-weight:600;font-size:13px;'>{p_cites:,}</td>
                        <td style='padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:center;font-size:13px;'>{p_fwci}</td>
                    </tr>
                    """
                html_top_papers = f"""
                <div style='margin-top:20px;background:#ffffff;border:1px solid #e5e7eb;border-radius:6px;overflow:hidden;'>
                    <div style='padding:10px 14px;background:#f8fafc;border-bottom:1px solid #e5e7eb;font-weight:600;font-size:13px;color:#003D64;'>
                        Hitos de Investigación: Publicaciones con Mayor Repercusión Citacional
                    </div>
                    <table style='width:100%;border-collapse:collapse;'>
                        <thead>
                            <tr style='background:#f1f5f9;font-size:11.5px;color:#475569;text-transform:uppercase;'>
                                <th style='padding:6px 10px;text-align:left;'>Publicación y Fuente</th>
                                <th style='padding:6px 10px;text-align:center;width:80px;'>Citas</th>
                                <th style='padding:6px 10px;text-align:center;width:80px;'>FWCI</th>
                            </tr>
                        </thead>
                        <tbody>{rows_html}</tbody>
                    </table>
                </div>
                """
        except Exception as e:
            print("Error generando tabla top papers:", e)

    journals_snippet = "; ".join(top_journals_list[:6]) if top_journals_list else "Datos de revistas no disponibles."
    p_jour = f"""
    Analiza la concentración editorial y los canales de publicación de {entity_name}.
    Datos:
    - Principales cabeceras editoriales: {journals_snippet}.
    - Total de documentos evaluados: {m_docs:,}.

    Instrucciones estrictas:
    - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
    - Redacta un párrafo analítico y descriptivo (máximo 4 líneas) que evalúe si la producción se concentra en revistas núcleo de la disciplina o se distribuye ampliamente, manteniendo un lenguaje neutral y sobrio.
    """
    llm_jour = markdown.markdown(get_llm_analysis(p_jour))

    sections_html += f"""
    <h2>4. Ecosistema Editorial y Publicaciones Emblemáticas</h2>
    <div class='markdown-text'>{llm_jour}</div>
    {html_journals_fig}
    {html_top_papers}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 5: Dinámica, Velocidad de Citación y Madurez del Conocimiento
    # -------------------------------------------------------------------------
    print("Generando SubReporte 5/12: Dinámica y Vida Media de Citación...")
    _notify_step(progress_callback, 5, 12, "Calculando Dinámica y Vida Media de Citación")
    html_vel_fig = ""
    if not df_pap_ent.empty and 'citations' in df_pap_ent.columns and 'year' in df_pap_ent.columns:
        try:
            df_vel = df_pap_ent.copy()
            df_vel['age'] = cur_year - df_vel['year']
            df_vel['age'] = df_vel['age'].clip(lower=1)
            df_vel['velocity'] = df_vel['citations'] / df_vel['age']
            top_vel = df_vel.sort_values('velocity', ascending=False).head(20).sort_values('year')
            
            fig_vel = go.Figure()
            fig_vel.add_trace(go.Scatter(
                x=top_vel['year'], y=top_vel['velocity'],
                mode='lines+markers',
                line=dict(color='#003D64', width=2),
                marker=dict(size=6, color='#E39918'),
                text=top_vel.get('Title', ''),
                hoverinfo='text+x+y'
            ))
            fig_vel.update_layout(
                height=250, margin=dict(t=40, b=10, l=10, r=10),
                title="Tasa de Citas Anuales por Antigüedad (Top 20 Artículos)",
                xaxis_title="Año de publicación",
                yaxis_title="Citas / Año",
                template="plotly_white"
            )
            html_vel_fig = fig_to_html(fig_vel)
        except Exception as e:
            print("Error en gráfica de velocidad:", e)

    p_vel = f"""
    Evalúa la velocidad de citación y la madurez temporal del corpus de {entity_name}.
    Datos:
    - Velocidad promedio de citación: {m_vel:.2f} citas/año por documento.
    - Citas promedio totales: {m_cites_per_paper:.2f} citas/doc.
    - Vida Media de Citación (Cited Half-Life): {m_half_life:.1f} años (periodo requerido para acumular el 50% de las citas).
    - Citas recibidas en el último trienio: {m_recent_3yr:,}.

    Instrucciones estrictas:
    - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
    - Redacta un párrafo analítico y sintético (máximo 4 líneas) sobre si la captación de citas responde a un ciclo corto de obsolescencia rápida o a un impacto acumulativo y prolongado en el tiempo.
    """
    llm_vel = markdown.markdown(get_llm_analysis(p_vel))

    sections_html += f"""
    <h2>5. Dinámica, Velocidad de Citación y Madurez del Conocimiento</h2>
    <div class='markdown-text'>{llm_vel}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{m_vel:.2f}</div><div class="metric-label">Velocidad (Citas/Año)</div></div>
        <div class="metric-card"><div class="metric-value">{m_half_life:.1f}</div><div class="metric-label">Vida Media (Años)</div></div>
        <div class="metric-card"><div class="metric-value">{m_recent_3yr:,}</div><div class="metric-label">Citas Último Trienio</div></div>
        <div class="metric-card"><div class="metric-value">{m_cites_per_paper:.1f}</div><div class="metric-label">Densidad Citas/Doc</div></div>
    </div>
    {html_vel_fig}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 6: Acceso Abierto y Economía de la Publicación
    # -------------------------------------------------------------------------
    print("Generando SubReporte 6/12: Acceso Abierto y Costos APC...")
    _notify_step(progress_callback, 6, 12, "Examinando Vías de Acceso Abierto y Costos APC")
    html_oa_figs = ""
    
    pct_gold = data.get('pct_oa_gold', 0.0)
    pct_green = data.get('pct_oa_green', 0.0)
    pct_hybrid = data.get('pct_oa_hybrid', 0.0)
    pct_bronze = data.get('pct_oa_bronze', 0.0)
    pct_closed = data.get('pct_oa_closed', 0.0)

    try:
        oa_vals = [pct_gold, pct_green, pct_hybrid, pct_bronze, pct_closed]
        labels = ['Gold (Dorada)', 'Green (Repositorio)', 'Hybrid (Híbrida)', 'Bronze (Bronce)', 'Closed (Suscripción)']
        colors = ['#FFD700', '#2ECC71', '#3498DB', '#CD7F32', '#95A5A6']
        fig_oa = go.Figure(data=[go.Pie(labels=labels, values=oa_vals, hole=.4, marker=dict(colors=colors))])
        fig_oa.update_layout(height=280, margin=dict(t=30, b=10, l=10, r=10), showlegend=True, title="Distribución de Modalidades de Acceso Abierto")
        html_oa_figs += fig_to_html(fig_oa)
    except Exception as e:
        print("Error en gráfica donut OA:", e)

    if not df_ann_ent.empty:
        oa_cols = [c for c in ['pct_oa_gold','pct_oa_green','pct_oa_hybrid','pct_oa_bronze','pct_oa_closed'] if c in df_ann_ent.columns]
        if oa_cols:
            df_oa_melt = df_ann_ent[['year'] + oa_cols].melt(id_vars='year', var_name='tipo_oa', value_name='pct')
            df_oa_melt['tipo_oa'] = df_oa_melt['tipo_oa'].str.replace('pct_oa_','').str.capitalize()
            color_map = {'Gold':'#FFD700','Green':'#2ECC71','Hybrid':'#3498DB','Bronze':'#CD7F32','Closed':'#95A5A6'}
            _x_min_oa = max(1960, yr_min)
            fig_stack = px.bar(
                df_oa_melt, x='year', y='pct', color='tipo_oa',
                color_discrete_map=color_map, barmode='stack',
                title="Evolución Anual del Modelo de Acceso (%)",
                range_x=[_x_min_oa - 0.5, cur_year + 0.5],
                labels={'pct': 'Proporción (%)', 'year': 'Año'}
            )
            fig_stack.update_xaxes(tickformat='d', dtick=5)
            fig_stack.update_layout(template="plotly_white", height=320, margin=dict(t=40, b=10, l=10, r=10))
            html_oa_figs += fig_to_html(fig_stack)

    p_oa = f"""
    Evalúa el modelo de publicación y la economía de acceso abierto de {entity_name}.
    Datos cuantitativos:
    - Tasa global de Acceso Abierto: {m_oa:.1f}%.
    - Modalidades: Vía Verde (Repositorios) {pct_green:.1f}%, Dorada {pct_gold:.1f}%, Híbrida {pct_hybrid:.1f}%, Bronce {pct_bronze:.1f}%, Cerrada {pct_closed:.1f}%.
    - Proporción con cobro de procesamiento (APC): {m_pct_apc:.1f}%.
    - Gasto estimado acumulado en APC comercial: ${m_apc:,.0f} USD.

    Instrucciones estrictas:
    - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
    - Redacta un párrafo analítico y formal (máximo 4 líneas) que contraste la dependencia hacia cargos de procesamiento comercial (APC) frente al aprovechamiento de repositorios institucionales y vías no comerciales.
    """
    llm_oa = markdown.markdown(get_llm_analysis(p_oa))

    sections_html += f"""
    <h2>6. Acceso Abierto y Economía de la Publicación</h2>
    <div class='markdown-text'>{llm_oa}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{m_oa:.1f}%</div><div class="metric-label">Open Access Global</div></div>
        <div class="metric-card"><div class="metric-value">{pct_green:.1f}%</div><div class="metric-label">Vía Verde (Repositorios)</div></div>
        <div class="metric-card"><div class="metric-value">{pct_gold:.1f}%</div><div class="metric-label">Vía Dorada</div></div>
        <div class="metric-card"><div class="metric-value">${m_apc:,.0f}</div><div class="metric-label">Gasto APC Estimado (USD)</div></div>
    </div>
    {html_oa_figs}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 7: Identidad Temática y Concentración Disciplinar
    # -------------------------------------------------------------------------
    print("Generando SubReporte 7/12: Identidad Temática...")
    _notify_step(progress_callback, 7, 12, "Mapeando Identidad Temática y Concentración Disciplinar")
    html_top_figs = ""

    if df_top is not None and not df_top.empty:
        top_topics = df_top.sort_values('value', ascending=False).head(80)
        if not top_topics.empty:
            fig_sun = px.sunburst(
                top_topics, path=['domain', 'field', 'subfield', 'topic'],
                values='value', color='value',
                color_continuous_scale='Blues',
                title="Estructura Taxonómica de Investigación (Dominios, Campos y Tópicos)"
            )
            fig_sun.update_layout(height=550, margin=dict(t=40, b=10, l=10, r=10))
            html_top_figs += fig_to_html(fig_sun)

    # Nube de Palabras o Barras de Términos
    top_kw_list = []
    html_wordcloud = ""
    if df_kw is not None and not df_kw.empty and col_name in df_kw.columns:
        df_k = df_kw[df_kw[col_name] == entity_name].sort_values("freq", ascending=False).head(40)
        if not df_k.empty:
            freq_dict = dict(zip(df_k["keyword"], df_k["freq"]))
            top_kw_list = list(freq_dict.keys())[:20]
            try:
                from lib import wordcloud_helper as _wc
                img_bytes = _wc.generate_wordcloud_image(freq_dict, width=900, height=360)
                if img_bytes:
                    import base64
                    b64 = base64.b64encode(img_bytes).decode("utf-8")
                    html_wordcloud = (
                        "<div style='text-align:center; margin: 15px 0;'>"
                        f"<img src='data:image/png;base64,{b64}' "
                        "style='max-width:100%; border-radius:6px; border:1px solid #e1e4e8;' "
                        "alt='Nube de términos clave'/>"
                        "<p style='font-size:11px;color:#666;margin-top:4px;'>Términos científicos más recurrentes</p>"
                        "</div>"
                    )
            except Exception as e:
                print("WordCloud fallback:", e)

    kw_snippet = ", ".join(top_kw_list[:15]) if top_kw_list else "No disponibles."
    p_top = f"""
    Analiza la concentración disciplinar y la cohesión temática de {entity_name}.
    Datos:
    - Dominio científico predominante: '{m_dom}'.
    - Coeficiente de Gini temático: {m_gini:.3f} (0 indica especialización monodisciplinar; valores altos denotan dispersión interdisciplinar).
    - Descriptores científicos recurrentes: {kw_snippet}.

    Instrucciones estrictas:
    - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
    - Redacta un párrafo analítico y sintético (máximo 4 líneas) sobre la estabilidad y articulación de las líneas de investigación identificadas.
    """
    llm_top = markdown.markdown(get_llm_analysis(p_top))

    sections_html += f"""
    <h2>7. Identidad Temática y Concentración Disciplinar</h2>
    <div class='markdown-text'>{llm_top}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{m_gini:.3f}</div><div class="metric-label">Índice de Gini Temático</div></div>
        <div class="metric-card"><div class="metric-value" style="font-size:16px;">{m_dom}</div><div class="metric-label">Dominio Principal</div></div>
    </div>
    {html_wordcloud}
    {html_top_figs}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 8: Visibilidad e Indización en Repertorios Internacionales
    # -------------------------------------------------------------------------
    print("Generando SubReporte 8/12: Visibilidad e Indización...")
    _notify_step(progress_callback, 8, 12, "Verificando Visibilidad e Indización Internacional")
    html_rad = ""
    m_pub = data.get('pct_pubmed', 0.0)
    m_doaj = data.get('pct_doaj_indexed', 0.0)
    m_core = data.get('pct_core_journal', 0.0)
    m_repo = data.get('pct_repository', 0.0)
    m_eng = data.get('pct_english', 0.0)
    m_cc = data.get('pct_cc_by', 0.0)

    try:
        vis_cols = ['PubMed', 'DOAJ', 'Core Journal', 'Repositorios', 'Idioma Inglés', 'Licencia CC-BY']
        vals = [m_pub, m_doaj, m_core, m_repo, m_eng, m_cc]
        fig_rad = go.Figure()
        fig_rad.add_trace(go.Scatterpolar(
            r=vals + [vals[0]],
            theta=vis_cols + [vis_cols[0]],
            fill='toself',
            name='Visibilidad',
            line=dict(color='#003D64', width=2),
            fillcolor='rgba(0, 61, 100, 0.2)'
        ))
        fig_rad.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%")),
            height=340,
            margin=dict(t=30, b=30, l=30, r=30),
            title="Perfil de Indización y Formato de Difusión",
            template="plotly_white"
        )
        html_rad = fig_to_html(fig_rad)
    except Exception as e:
        print("Error en radar de visibilidad:", e)

    p_vis = f"""
    Evalúa la visibilidad e interoperabilidad internacional de {entity_name}.
    Datos:
    - Presencia en PubMed: {m_pub:.1f}%.
    - Publicaciones en revistas catalogadas en DOAJ: {m_doaj:.1f}%.
    - Publicaciones en revistas núcleo (Core Journals): {m_core:.1f}%.
    - Depósito en repositorios institucionales/temáticos: {m_repo:.1f}%.
    - Publicaciones en idioma inglés: {m_eng:.1f}%.
    - Licenciamiento abierto CC-BY: {m_cc:.1f}%.

    Instrucciones estrictas:
    - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
    - Redacta un párrafo analítico y sintético (máximo 4 líneas) que describa la presencia en repertorios internacionales de arbitraje estricto y la adopción de estándares técnicos abiertos.
    """
    llm_vis = markdown.markdown(get_llm_analysis(p_vis))

    sections_html += f"""
    <h2>8. Visibilidad e Indización en Repertorios Internacionales</h2>
    <div class='markdown-text'>{llm_vis}</div>
    {html_rad}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 9: Contribución al Desarrollo Sostenible (ODS)
    # -------------------------------------------------------------------------
    print("Generando SubReporte 9/12: ODS...")
    _notify_step(progress_callback, 9, 12, "Alineando con Objetivos de Desarrollo Sostenible (ODS)")
    html_ods = ""
    if not df_pap_ent.empty:
        try:
            html_ods = viz_ods.render_sdg_matrix(df_pap_ent, col_ods='ODS_ID')
        except Exception as e:
            print("Error en matriz ODS:", e)

    ods_summary_str = "Sin publicaciones con alineación explícita a ODS registrada."
    if not df_pap_ent.empty and 'ODS_Nombre' in df_pap_ent.columns:
        ods_counts = df_pap_ent['ODS_Nombre'].dropna().value_counts()
        if not ods_counts.empty:
            top_ods_list = [f"{nombre} ({cnt} doc{'s' if cnt > 1 else ''})" for nombre, cnt in ods_counts.head(5).items()]
            ods_summary_str = "; ".join(top_ods_list)

    p_ods = f"""
    Examina la contribución científica de {entity_name} a los Objetivos de Desarrollo Sostenible (ODS) de la Agenda 2030.
    Datos cuantitativos:
    - Corpus total: {m_docs:,} documentos.
    - Principales ODS con publicaciones identificadas: {ods_summary_str}.

    Instrucciones estrictas:
    - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
    - Redacta un párrafo analítico y sobrio (máximo 4 líneas) que determine la concentración o diversificación del impacto socioambiental hacia las metas de la Agenda 2030.
    """
    llm_ods = markdown.markdown(get_llm_analysis(p_ods))

    sections_html += f"""
    <h2>9. Contribución a los Objetivos de Desarrollo Sostenible (ODS)</h2>
    <div class='markdown-text'>{llm_ods}</div>
    {html_ods}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 10: Posicionamiento y Estructura (Investigador vs Institución)
    # -------------------------------------------------------------------------
    if entity_type == 'inv':
        print("Generando SubReporte 10/12: Posicionamiento UMAP y Coautores...")
        _notify_step(progress_callback, 10, 12, "Proyectando Topología y Redes de Coautoría")
        html_inv_extra = ""
        
        # 10.1 UMAP Scatter
        df_umap = da.get_cached_data("umap_investigadores.parquet", entity_name=entity_context, institution_name=institution_name)
        if df_umap is None or df_umap.empty:
            df_umap = da.get_cached_data("umap_investigadores.parquet", institution_name=institution_name)
        if df_umap is not None and not df_umap.empty:
            fig_umap = go.Figure()
            
            fwci_col = 'fwci_avg' if 'fwci_avg' in df_umap.columns else ('fwci' if 'fwci' in df_umap.columns else 'citations')
            raw_fwci = df_umap[fwci_col].fillna(0.5).clip(lower=0.01)
            p98 = raw_fwci.quantile(0.98) if len(raw_fwci) > 10 else raw_fwci.max()
            p98 = max(p98, 0.1)
            norm_fwci = (raw_fwci / p98).clip(lower=0.0, upper=1.0)
            r_min, r_max = 1.25, 3.75
            df_umap['_marker_size'] = r_min + (r_max - r_min) * np.sqrt(norm_fwci)

            otros = df_umap[df_umap['academic_name'] != entity_name]
            sel_row = df_umap[df_umap['academic_name'] == entity_name]

            if not otros.empty:
                hover_text_otros = otros['academic_name'] + "<br>FWCI: " + otros[fwci_col].round(2).astype(str) + "<br>Docs: " + otros.get('num_documents', 0).astype(str)
                fig_umap.add_trace(go.Scatter(
                    x=otros['umap_x'], y=otros['umap_y'], mode='markers',
                    name='Padrón Institucional', text=hover_text_otros, hoverinfo='text',
                    marker=dict(size=otros['_marker_size'], color='#003D64', opacity=0.40, line=dict(width=0.5, color='rgba(255,255,255,0.7)'))
                ))
            if not sel_row.empty:
                hover_text_sel = sel_row['academic_name'] + "<br>FWCI: " + sel_row[fwci_col].round(2).astype(str) + "<br>Docs: " + sel_row.get('num_documents', 0).astype(str)
                sel_size = max(float(sel_row['_marker_size'].iloc[0]) + 4.0, 11.0)
                fig_umap.add_trace(go.Scatter(
                    x=sel_row['umap_x'], y=sel_row['umap_y'], mode='markers',
                    name=entity_name, text=hover_text_sel, hoverinfo='text',
                    marker=dict(size=sel_size, color='#E8442A', symbol='circle', line=dict(width=2.5, color='#FFFFFF'))
                ))
            fig_umap.update_layout(
                title="Posicionamiento Cuantitativo en el Padrón (Tamaño proporcional a FWCI)",
                hovermode="closest", template="plotly_white", height=420, margin=dict(t=40, b=10, l=10, r=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            html_inv_extra += fig_to_html(fig_umap)

        # 10.2 Top Coautores
        top_coauthors_str = "No disponibles"
        if not df_pap_ent.empty:
            col_auth = 'author_names' if 'author_names' in df_pap_ent.columns else ('authors' if 'authors' in df_pap_ent.columns else None)
            if col_auth:
                from collections import Counter
                c_auth = Counter()
                for alist in df_pap_ent[col_auth]:
                    if isinstance(alist, (list, np.ndarray)):
                        for a in alist:
                            if a and str(a).upper() != entity_name.upper():
                                c_auth[str(a)] += 1
                if c_auth:
                    top_co = pd.DataFrame(c_auth.most_common(10), columns=['Coautor', 'Obras_Conjuntas'])
                    top_coauthors_str = ", ".join(f"{r['Coautor']} ({r['Obras_Conjuntas']})" for _, r in top_co.head(5).iterrows())
                    fig_co = px.bar(
                        top_co, x='Obras_Conjuntas', y='Coautor', orientation='h',
                        title="Principales Coautores y Colaboradores Frecuentes",
                        labels={'Obras_Conjuntas': 'Publicaciones conjuntas', 'Coautor': 'Investigador'},
                        color='Obras_Conjuntas', color_continuous_scale="Blues"
                    )
                    fig_co.update_layout(yaxis={'categoryorder': 'total ascending'}, height=320, margin=dict(t=40, b=10, l=10, r=10), template="plotly_white")
                    fig_co.update_coloraxes(showscale=False)
                    html_inv_extra += fig_to_html(fig_co)

        p_umap = f"""
        Analiza el posicionamiento relativo del investigador {entity_name} frente a sus pares institucionales y la conformación de su grupo de coautoría ({top_coauthors_str}).
        Indicadores: {m_docs} documentos, {m_cites} citas, FWCI {m_fwci:.2f}, {m_top10:.1f}% en Top 10% global.

        Instrucciones estrictas:
        - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
        - Redacta un párrafo descriptivo y riguroso (máximo 4 líneas) que examine su grado de centralidad respecto a la masa académica y la estabilidad de su red de colaboración interna.
        """
        llm_umap = markdown.markdown(get_llm_analysis(p_umap))

        sections_html += f"""
        <h2>10. Posicionamiento en el Padrón Institucional y Redes de Coautoría</h2>
        <div class='markdown-text'>{llm_umap}</div>
        {html_inv_extra}
        """

    else:
        print("Generando SubReporte 10/12: Composición del Personal Académico...")
        _notify_step(progress_callback, 10, 12, "Analizando Composición del Personal Académico")
        html_inst_extra = ""
        top_acad_str = "No disponible"
        if not df_pap_ent.empty and 'academic_name' in df_pap_ent.columns:
            acad_counts = df_pap_ent.groupby('academic_name').agg(
                documentos=('paper_id', 'count'),
                citas=('citations', 'sum'),
                fwci_prom=('fwci', 'mean')
            ).reset_index().sort_values('documentos', ascending=False).head(12)
            
            if not acad_counts.empty:
                top_acad_str = ", ".join(f"{r['academic_name']} ({r['documentos']} docs, {r['citas']} citas)" for _, r in acad_counts.head(5).iterrows())
                fig_acad = px.bar(
                    acad_counts, x='documentos', y='academic_name', orientation='h',
                    title="Investigadores con Mayor Volumen de Producción en la Entidad",
                    labels={'documentos': 'Documentos indexados', 'academic_name': 'Investigador'},
                    color='citas', color_continuous_scale="Viridis"
                )
                fig_acad.update_layout(yaxis={'categoryorder': 'total ascending'}, height=360, margin=dict(t=40, b=10, l=10, r=10), template="plotly_white")
                html_inst_extra = fig_to_html(fig_acad)

        p_inst_struct = f"""
        Analiza la distribución de la producción entre el personal académico de {entity_name}.
        Datos:
        - Total de obras institucionales: {m_docs:,}.
        - Investigadores con mayor concentración de producción: {top_acad_str}.

        Instrucciones estrictas:
        - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
        - Redacta un párrafo analítico y sintético (máximo 4 líneas) que evalúe si la producción científica descansa en un grupo nuclear específico o si presenta una distribución balanceada entre múltiples autores.
        """
        llm_inst_struct = markdown.markdown(get_llm_analysis(p_inst_struct))

        sections_html += f"""
        <h2>10. Composición del Personal Académico y Grupos de Investigación</h2>
        <div class='markdown-text'>{llm_inst_struct}</div>
        {html_inst_extra}
        """

    # -------------------------------------------------------------------------
    # SECCIÓN 11: Redes de Colaboración Internacional
    # -------------------------------------------------------------------------
    print("Generando SubReporte 11/12: Colaboración Internacional...")
    _notify_step(progress_callback, 11, 12, "Sintetizando Redes de Colaboración Internacional")
    html_collab_figs = ""
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
                df_cnt['iso_a3'] = df_cnt['iso_a2'].map(da.ISO2_TO_ISO3).fillna(df_cnt['iso_a2'])
                df_cnt['País'] = df_cnt['iso_a2'].apply(lambda x: pytz.country_names.get(x, x))
                top_countries = [f"{r['País']} ({r['papers']} papers)" for _, r in df_cnt.head(8).iterrows()]
                
                fig_choro = px.choropleth(
                    df_cnt, locations="iso_a3", locationmode="ISO-3",
                    color="papers",
                    color_continuous_scale="Blues",
                    title="Distribución Geográfica de Colaboraciones Internacionales",
                    hover_name="País",
                    labels={"papers": "Obras conjuntas"}
                )
                fig_choro.update_layout(
                    height=400, margin=dict(t=40, b=0, l=0, r=0),
                    geo=dict(showframe=False, showcoastlines=True, bgcolor="rgba(0,0,0,0)", showland=True, landcolor="#f6f8fa")
                )
                html_collab_figs += fig_to_html(fig_choro)
        except Exception as e:
            print("Error en choropleth de colaboración:", e)

    if not df_ann_ent.empty and 'pct_international' in df_ann_ent.columns:
        try:
            df_intl_ann = df_ann_ent.dropna(subset=['pct_international']).sort_values('year')
            if not df_intl_ann.empty:
                _x_min_c = max(1960, yr_min)
                fig_intl = px.line(
                    df_intl_ann, x='year', y='pct_international',
                    markers=True,
                    title="Evolución Anual del Porcentaje de Colaboración Internacional",
                    range_x=[_x_min_c - 0.5, cur_year + 0.5],
                    labels={'pct_international': '% Colaboración Internacional', 'year': 'Año'}
                )
                fig_intl.update_traces(line=dict(color='#003D64', width=2), marker=dict(color='#E39918', size=6))
                fig_intl.update_xaxes(tickformat='d', dtick=5)
                fig_intl.update_layout(template='plotly_white', height=280, margin=dict(t=40, b=10, l=10, r=10))
                html_collab_figs += fig_to_html(fig_intl)
        except Exception as e:
            print("Error en serie temporal intl:", e)

    # Red Topológica Neo4j
    html_network = ""
    try:
        neo = Neo4jGraphStore()
        graph_data = None
        if entity_type == "inst":
            graph_data = neo.get_funder_sample_graph(entity_name, limit=80)
        neo.close()

        if graph_data and graph_data.get("nodes"):
            net = Network(height="380px", width="100%", bgcolor="#ffffff", font_color="#333333", notebook=False)
            node_ids = set()
            for n in graph_data["nodes"]:
                node_id = n["id"]
                node_ids.add(node_id)
                node_class = n.get("label", "Unknown")
                visible_name = n.get("title", str(node_id))
                color_map_net = {"Academic": "#8B9DC3", "Paper": "#D0D7DE", "Institution": "#003D64", "Entity": "#003D64", "Funder": "#2ECC71"}
                color = color_map_net.get(node_class, "#97C2FC")
                net.add_node(node_id, label=visible_name, title=f"{node_class}: {visible_name}", color=color, group=node_class)
            for e in graph_data["edges"]:
                if e["source"] in node_ids and e["target"] in node_ids:
                    net.add_edge(e["source"], e["target"], title=e.get("label", ""))
            net.set_options('{"physics": {"forceAtlas2Based": {"springLength": 100}, "minVelocity": 0.75, "solver": "forceAtlas2Based"}}')
            safe_html = __import__('html').escape(net.generate_html())
            html_network = (
                "<div class='chart'><h3 style='font-size:15px;margin-top:0;color:#003D64;'>Red Topológica de Entidades</h3>"
                f"<iframe srcdoc='{safe_html}' width='100%' height='390px' "
                "style='border:1px solid #e1e4e8; border-radius: 6px;'></iframe></div>"
            )
    except Exception as e:
        print(f"Error en red Neo4j: {e}")

    countries_snippet = "; ".join(top_countries) if top_countries else "No disponible."
    p_collab = f"""
    Evalúa la proyección exterior y la red de colaboración internacional de {entity_name}.
    Datos:
    - Tasa de coautoría internacional: {m_intl:.1f}%.
    - Principales países con vinculación: {countries_snippet}.

    Instrucciones estrictas:
    - Responde directamente con el texto analítico final sin preámbulos ni meta-comentarios.
    - Redacta un párrafo analítico y sintético (máximo 4 líneas) que determine la diversificación geográfica de los vínculos externos y el grado de internacionalización del corpus.
    """
    llm_collab = markdown.markdown(get_llm_analysis(p_collab))

    sections_html += f"""
    <h2>11. Redes de Colaboración e Internacionalización</h2>
    <div class='markdown-text'>{llm_collab}</div>
    <div class="metrics-grid">
        <div class="metric-card"><div class="metric-value">{m_intl:.1f}%</div><div class="metric-label">Tasa Internacional</div></div>
    </div>
    {html_collab_figs}
    {html_network}
    """

    # -------------------------------------------------------------------------
    # SECCIÓN 12: Síntesis Diagnóstica: Fortalezas y Directrices Estratégicas
    # -------------------------------------------------------------------------
    print("Generando SubReporte 12/12: Síntesis Diagnóstica...")
    _notify_step(progress_callback, 12, 12, "Sintetizando Fortalezas y Directrices Estratégicas")

    p_diag = f"""
    A partir de los siguientes indicadores cuantitativos consolidados de {entity_name}:
    - Corpus: {m_docs:,} documentos, {m_cites:,} citas ({m_cites_per_paper:.2f} citas/doc).
    - FWCI Promedio: {m_fwci:.2f} (media mundial = 1.00).
    - Excelencia: {m_top10:.1f}% en Top 10% global, {m_pct_t1:.1f}% en Tier 1 (Q1).
    - Vida Media de Citación: {m_half_life:.1f} años.
    - Acceso Abierto: {m_oa:.1f}% ({pct_green:.1f}% repositorios, {pct_gold:.1f}% dorada, {m_pct_apc:.1f}% con APC).
    - Gasto APC estimado: ${m_apc:,.0f} USD.
    - Colaboración internacional: {m_intl:.1f}% de las obras.
    - Concentración temática (Gini): {m_gini:.3f} en dominio principal '{m_dom}'.

    Instrucciones estrictas:
    - Responde directamente con el texto en markdown sin preámbulos ni meta-comentarios.
    - Redacta una Síntesis Diagnóstica ejecutiva estructurada exactamente en dos bloques con viñetas:
    1. **Fortalezas Cienciométricas Factuales** (exactamente 3 viñetas concisas de 1 a 2 líneas cada una, fundamentadas en datos).
    2. **Áreas de Oportunidad y Directrices Estratégicas** (exactamente 3 viñetas concisas de 1 a 2 líneas cada una, orientadas a optimización de impacto, balance editorial o sostenibilidad).
    - Tono estrictamente moderado, neutro, académico sintético, sin adjetivos grandilocuentes.
    """
    llm_diag = markdown.markdown(get_llm_analysis(p_diag))

    sections_html += f"""
    <h2>12. Síntesis Diagnóstica: Fortalezas y Directrices Estratégicas</h2>
    <div class='markdown-text'>{llm_diag}</div>
    """

    # -------------------------------------------------------------------------
    # Ensamblaje HTML Final
    # -------------------------------------------------------------------------
    print("Ensamblando documento HTML final...")
    today_str = datetime.now().strftime("%d/%m/%Y")
    profile_type_label = (
        'Institución / Dependencia (Capacidad Instalada)' if (entity_type == 'inst' and view_mode == 'capacidad_instalada')
        else ('Institución / Dependencia (Producción Institucional)' if entity_type == 'inst' else 'Investigador')
    )

    html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Informe Bibliométrico: {entity_name}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 30px auto;
            max-width: 1040px;
            line-height: 1.65;
            color: #1f2937;
            background-color: #f9fafb;
            padding: 0 20px;
        }}
        
        .header-container {{
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-top: 4px solid #003D64;
            border-radius: 8px;
            padding: 24px 30px;
            margin-bottom: 25px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }}
        
        .header-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #f3f4f6;
            padding-bottom: 12px;
            margin-bottom: 15px;
        }}
        
        .header-brand {{
            font-size: 13px;
            font-weight: 700;
            letter-spacing: 0.5px;
            color: #003D64;
            text-transform: uppercase;
        }}
        
        .header-date {{
            font-size: 12px;
            color: #6b7280;
        }}
        
        h1 {{
            color: #111827;
            font-size: 24px;
            font-weight: 700;
            margin: 0 0 8px 0;
            letter-spacing: -0.3px;
        }}
        
        .profile-badge {{
            display: inline-block;
            background: #eef2f6;
            color: #003D64;
            font-size: 12px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 4px;
            margin-top: 4px;
        }}
        
        h2 {{
            color: #003D64;
            margin-top: 35px;
            border-bottom: 1.5px solid #e5e7eb;
            padding-bottom: 8px;
            font-size: 17px;
            font-weight: 600;
            letter-spacing: -0.2px;
            text-transform: uppercase;
        }}
        
        .summary-box {{
            background: #ffffff;
            border-left: 4px solid #E39918;
            border-radius: 4px;
            padding: 16px 20px;
            margin: 18px 0 25px 0;
            font-size: 14.5px;
            color: #374151;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
            border-top: 1px solid #f3f4f6;
            border-right: 1px solid #f3f4f6;
            border-bottom: 1px solid #f3f4f6;
        }}
        
        .summary-box p {{
            margin: 0 0 10px 0;
        }}
        .summary-box p:last-child {{
            margin-bottom: 0;
        }}
        
        .markdown-text {{
            font-size: 14.5px;
            color: #374151;
            margin-bottom: 20px;
            text-align: justify;
        }}
        
        .markdown-text p {{
            margin: 0 0 12px 0;
        }}
        
        .markdown-text ul {{
            margin: 0 0 14px 0;
            padding-left: 20px;
        }}
        
        .markdown-text strong {{
            color: #111827;
            font-weight: 600;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin: 15px 0 25px 0;
        }}
        
        .metric-card {{
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            padding: 14px 10px;
            text-align: center;
            box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }}
        
        .metric-value {{
            font-size: 22px;
            font-weight: 700;
            color: #003D64;
            margin-bottom: 4px;
            letter-spacing: -0.5px;
        }}
        
        .metric-label {{
            font-size: 11px;
            font-weight: 500;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.4px;
        }}
        
        .chart {{
            margin-top: 15px;
            margin-bottom: 25px;
            width: 100%;
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            padding: 14px;
            box-sizing: border-box;
        }}
        
        .footer-note {{
            margin-top: 50px;
            border-top: 1px solid #e5e7eb;
            padding-top: 15px;
            font-size: 11px;
            color: #9ca3af;
            text-align: center;
        }}

        @media print {{
            body {{
                background-color: #ffffff;
                max-width: 100%;
                margin: 0;
                padding: 10px;
            }}
            .header-container {{
                box-shadow: none;
                border: 1px solid #ccc;
            }}
            .chart {{
                page-break-inside: avoid;
                box-shadow: none;
                border: 1px solid #eee;
            }}
            h2 {{
                page-break-after: avoid;
            }}
            .summary-box {{
                box-shadow: none;
            }}
        }}
    </style>
</head>
<body>
    <div class="header-container">
        <div class="header-top">
            <div class="header-brand">Sinapsis AI &bull; Sistema de Inteligencia Bibliométrica</div>
            <div class="header-date">Fecha de emisión: {today_str}</div>
        </div>
        <h1>{entity_name}</h1>
        <div class="profile-badge">{profile_type_label}</div>
    </div>

    {sections_html}

    <div class="footer-note">
        Informe generado automáticamente por el motor analítico de Sinapsis AI sobre datos estructurados de OpenAlex, Scopus, ORCID y Neo4j.
    </div>
</body>
</html>"""
    
    if save_to_disk:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Reporte generado exitosamente en: {file_path}")
        return file_path
    else:
        print(f"Reporte efímero generado en memoria para {entity_name}")
        return html_content


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generador de Reportes Bibliométricos Ejecutivos")
    parser.add_argument("--type", choices=['inst', 'inv'], required=True, help="Tipo de entidad: inst (Institución/Dependencia) o inv (Investigador)")
    parser.add_argument("--name", required=True, help="Nombre exacto de la entidad o académico")
    parser.add_argument("--entity", required=False, help="Contexto institucional para cargar la caché del investigador.")
    parser.add_argument("--institution", required=False, help="Institución de acreditación.")
    parser.add_argument("--view_mode", default="capacidad_instalada", choices=["capacidad_instalada", "produccion_institucional"], help="Modo de vista.")
    args = parser.parse_args()
    try:
        path = generate_html_report(args.type, args.name, args.entity, args.institution, args.view_mode)
        print(f"✅ Reporte disponible en: {path}")
    except Exception as e:
        print(f"❌ Error fatal generando reporte: {e}")
        import traceback
        traceback.print_exc()
