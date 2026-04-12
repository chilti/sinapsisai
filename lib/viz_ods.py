import streamlit as st
import pandas as pd
import re

def procesar_datos_ods(df, col_ods='ODS_ID'):
    # 1. Crear estructura base
    df_final = pd.DataFrame({'ODS': range(1, 18)})
    
    if df is None or df.empty or col_ods not in df.columns:
        df_final['Frecuencia'] = 0
        df_final['Porcentaje'] = 0.0
        return df_final
    
    # 2. Extraer números
    def extraer_numero(val):
        if pd.isna(val) or str(val).lower() == 'null':
            return None
        match = re.search(r'\d+', str(val))
        return int(match.group()) if match else None

    df_temp = df.copy()
    df_temp['ods_num'] = df_temp[col_ods].apply(extraer_numero)
    
    # 3. Contar y Merge
    conteo_real = df_temp['ods_num'].value_counts().reset_index()
    conteo_real.columns = ['ODS', 'Frecuencia']
    
    df_merged = pd.merge(df_final, conteo_real, on='ODS', how='left')
    df_merged['Frecuencia'] = df_merged['Frecuencia'].fillna(0)
    
    # 4. Porcentajes
    total_papers = len(df)
    if total_papers > 0:
        df_merged['Porcentaje'] = (df_merged['Frecuencia'] / total_papers) * 100
    else:
        df_merged['Porcentaje'] = 0.0
        
    return df_merged

def render_sdg_matrix(df_papers, col_ods='ODS_ID'):
    
    df_viz = procesar_datos_ods(df_papers, col_ods)
    base_img_url = "https://open-sdg.github.io/sdg-translations/assets/img/goals/es"

    # IMPORTANTE: El CSS y el HTML están pegados al margen izquierdo
    # para evitar que Markdown los interprete como bloques de código.
    
    css_style = """
<style>
    .sdg-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
        gap: 12px;
        padding: 10px 0;
        margin-bottom: 20px;
    }
    .sdg-card {
        position: relative;
        aspect-ratio: 1 / 1;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        transition: transform 0.2s;
        background-color: #f4f4f4;
        margin: 0; /* Asegura que no haya margen externo inesperado */
    }
    .sdg-card:hover {
        transform: scale(1.03);
        z-index: 5;
        box-shadow: 0 6px 10px rgba(0,0,0,0.2);
    }
    .sdg-img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
    }
    .sdg-overlay {
        position: absolute;
        bottom: 0; left: 0; right: 0;
        background: rgba(0, 0, 0, 0.75);
        color: white;
        padding: 5px 0;
        text-align: center;
        line-height: 1.2;
    }
    .sdg-perc {
        font-size: 1.1rem;
        font-weight: bold;
        display: block;
    }
    .sdg-inactive {
        filter: grayscale(100%) opacity(0.3);
    }
    .sdg-inactive:hover {
        filter: grayscale(0%) opacity(1);
    }
</style>
"""

    html_content = '<div class="sdg-grid">'
    
    for index, row in df_viz.iterrows():
        ods_id = int(row['ODS'])
        pct = row.get('Porcentaje', 0.0) 
        count = int(row.get('Frecuencia', 0))
        
        active_class = "sdg-inactive" if count == 0 else ""
        img_src = f"{base_img_url}/{ods_id}.png"
        tooltip = f"ODS {ods_id}: {count} artículos ({pct:.1f}%)"
        
        # HTML sin indentación para evitar bug de Markdown
        html_content += f"""
<div class="sdg-card {active_class}" title="{tooltip}">
<img src="{img_src}" class="sdg-img" loading="lazy">
<div class="sdg-overlay">
<span class="sdg-perc">{pct:.1f}%</span>
</div>
</div>"""
        
    html_content += "</div>"
    
    # Renderizado final combinando CSS + HTML
    full_html = css_style + html_content
    return full_html
    #st.markdown(full_html, unsafe_allow_html=True)