import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.ui_components import render_explain_button
import streamlit.components.v1 as components
import os
import sys
import json
import numpy as np
from scipy.ndimage import gaussian_filter
import base64
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as mcm
from datetime import datetime
from lib import viz_ods  # Nuevo módulo para pintar la matriz de ODS
from lib.coauthra_integration import render_coauthra

try:
    from lib import wordcloud_helper as _wc_helper
    _HAS_WORDCLOUD = True
except ImportError:
    from lib import wordcloud_helper as _wc_helper
    _HAS_WORDCLOUD = True
except Exception:
    _wc_helper = None
    _HAS_WORDCLOUD = False

# Paths
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_PATH, 'data', 'cache_ch')

ISO2_TO_ISO3 = {
    'AF': 'AFG', 'AX': 'ALA', 'AL': 'ALB', 'DZ': 'DZA', 'AS': 'ASM', 'AD': 'AND', 'AO': 'AGO', 'AI': 'AIA', 'AQ': 'ATA', 'AG': 'ATG',
    'AR': 'ARG', 'AM': 'ARM', 'AW': 'ABW', 'AU': 'AUS', 'AT': 'AUT', 'AZ': 'AZE', 'BS': 'BHS', 'BH': 'BHR', 'BD': 'BGD', 'BB': 'BRB',
    'BY': 'BLR', 'BE': 'BEL', 'BZ': 'BLZ', 'BJ': 'BEN', 'BM': 'BMU', 'BT': 'BTN', 'BO': 'BOL', 'BQ': 'BES', 'BA': 'BIH', 'BW': 'BWA',
    'BV': 'BVT', 'BR': 'BRA', 'IO': 'IOT', 'BN': 'BRN', 'BG': 'BGR', 'BF': 'BFA', 'BI': 'BDI', 'CV': 'CPV', 'KH': 'KHM', 'CM': 'CMR',
    'CA': 'CAN', 'KY': 'CYM', 'CF': 'CAF', 'TD': 'TCD', 'CL': 'CHL', 'CN': 'CHN', 'CX': 'CXR', 'CC': 'CCK', 'CO': 'COL', 'KM': 'COM',
    'CD': 'COD', 'CG': 'COG', 'CK': 'COK', 'CR': 'CRI', 'CI': 'CIV', 'HR': 'HRV', 'CU': 'CUB', 'CW': 'CUW', 'CY': 'CYP', 'CZ': 'CZE',
    'DK': 'DNK', 'DJ': 'DJI', 'DM': 'DMA', 'DO': 'DOM', 'EC': 'ECU', 'EG': 'EGY', 'SV': 'SLV', 'GQ': 'GNQ', 'ER': 'ERI', 'EE': 'EST',
    'SZ': 'SWZ', 'ET': 'ETH', 'FK': 'FLK', 'FO': 'FRO', 'FJ': 'FJI', 'FI': 'FIN', 'FR': 'FRA', 'GF': 'GUF', 'PF': 'PYF', 'TF': 'ATF',
    'GA': 'GAB', 'GM': 'GMB', 'GE': 'GEO', 'DE': 'DEU', 'GH': 'GHA', 'GI': 'GIB', 'GR': 'GRC', 'GL': 'GRL', 'GD': 'GRD', 'GP': 'GLP',
    'GU': 'GUM', 'GT': 'GTM', 'GG': 'GGY', 'GN': 'GIN', 'GW': 'GNB', 'GY': 'GUY', 'HT': 'HTI', 'HM': 'HMD', 'VA': 'VAT', 'HN': 'HND',
    'HK': 'HKG', 'HU': 'HUN', 'IS': 'ISL', 'IN': 'IND', 'ID': 'IDN', 'IR': 'IRN', 'IQ': 'IRQ', 'IE': 'IRL', 'IM': 'IMN', 'IL': 'ISR',
    'IT': 'ITA', 'JM': 'JAM', 'JP': 'JPN', 'JE': 'JEY', 'JO': 'JOR', 'KZ': 'KAZ', 'KE': 'KEN', 'KI': 'KIR', 'KP': 'PRK', 'KR': 'KOR',
    'KW': 'KWT', 'KG': 'KGZ', 'LA': 'LAO', 'LV': 'LVA', 'LB': 'LBN', 'LS': 'LSO', 'LR': 'LBR', 'LY': 'LBY', 'LI': 'LIE', 'LT': 'LTU',
    'LU': 'LUX', 'MO': 'MAC', 'MG': 'MDG', 'MW': 'MWI', 'MY': 'MYS', 'MV': 'MDV', 'ML': 'MLI', 'MT': 'MLT', 'MH': 'MHL', 'MQ': 'MTQ',
    'MR': 'MRT', 'MU': 'MUS', 'YT': 'MYT', 'MX': 'MEX', 'FM': 'FSM', 'MD': 'MDA', 'MC': 'MCO', 'MN': 'MNG', 'ME': 'MNE', 'MS': 'MSR',
    'MA': 'MAR', 'MZ': 'MOZ', 'MM': 'MMR', 'NA': 'NAM', 'NR': 'NRU', 'NP': 'NPL', 'NL': 'NLD', 'NC': 'NCL', 'NZ': 'NZL', 'NI': 'NIC',
    'NE': 'NER', 'NG': 'NGA', 'NU': 'NIU', 'NF': 'NFK', 'MP': 'MNP', 'NO': 'NOR', 'OM': 'OMN', 'PK': 'PAK', 'PW': 'PLW', 'PS': 'PSE',
    'PA': 'PAN', 'PG': 'PNG', 'PY': 'PRY', 'PE': 'PER', 'PH': 'PHL', 'PN': 'PCN', 'PL': 'POL', 'PT': 'PRT', 'PR': 'PRI', 'QA': 'QAT',
    'RE': 'REU', 'RO': 'ROU', 'RU': 'RUS', 'RW': 'RWA', 'BL': 'BLM', 'SH': 'SHN', 'KN': 'KNA', 'LC': 'LCA', 'MF': 'MAF', 'PM': 'SPM',
    'VC': 'VCT', 'WS': 'WSM', 'SM': 'SMR', 'ST': 'STP', 'SA': 'SAU', 'SN': 'SEN', 'RS': 'SRB', 'SC': 'SYC', 'SL': 'SLE', 'SG': 'SGP',
    'SX': 'SXM', 'SK': 'SVK', 'SI': 'SVN', 'SB': 'SLB', 'SO': 'SOM', 'ZA': 'ZAF', 'GS': 'SGS', 'SS': 'SSD', 'ES': 'ESP', 'LK': 'LKA',
    'SD': 'SDN', 'SR': 'SUR', 'SJ': 'SJM', 'SE': 'SWE', 'CH': 'CHE', 'SY': 'SYR', 'TW': 'TWN', 'TJ': 'TJK', 'TZ': 'TZA', 'TH': 'THA',
    'TL': 'TLS', 'TG': 'TGO', 'TK': 'TKL', 'TO': 'TON', 'TT': 'TTO', 'TN': 'TUN', 'TR': 'TUR', 'TM': 'TKM', 'TC': 'TCA', 'TV': 'TUV',
    'UG': 'UGA', 'UA': 'UKR', 'AE': 'ARE', 'GB': 'GBR', 'UM': 'UMI', 'US': 'USA', 'UY': 'URY', 'UZ': 'UZB', 'VU': 'VUT', 'VE': 'VEN',
    'VN': 'VNM', 'VG': 'VGB', 'VI': 'VIR', 'WF': 'WLF', 'EH': 'ESH', 'YE': 'YEM', 'ZM': 'ZMB', 'ZW': 'ZWE'
}

@st.cache_data
def load_official_snii_counts():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'official_snii_counts.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

import duckdb

_FILENAME_TO_TABLE = {
    'institucion_annual.parquet': 'institucion_annual',
    'investigador_annual.parquet': 'investigador_annual',
    'institucion_total.parquet': 'institucion_total',
    'investigador_total.parquet': 'investigador_total',
    'investigador_recent.parquet': 'investigador_recent',
    'keywords_institucion.parquet': 'keywords_institucion',
    'keywords_investigador.parquet': 'keywords_investigador',
    'papers_institucion.parquet': 'papers_institucion',
    'papers_profesor.parquet': 'papers_profesor',
    'thematic_evolution_institucion.parquet': 'thematic_evolution_institucion',
    'thematic_evolution_investigador.parquet': 'thematic_evolution_investigador',
    'topics_institucion.parquet': 'topics_institucion',
    'topics_investigador.parquet': 'topics_investigador',
    'umap_investigadores.parquet': 'umap_investigadores'
}

def get_duckdb_con():
    db_path = os.path.join(BASE_PATH, 'data', 'analytics_cache.duckdb')
    if os.path.exists(db_path):
        try:
            return duckdb.connect(db_path, read_only=True)
        except Exception:
            return None
    return None

def load_cached_data(filename, entity_name=None, academic_name=None, institution_name=None, view_mode="capacidad_instalada", _mtime=None):
    """Carga datos desde DuckDB. Si falla o no hay datos, hace un fallback a leer el Parquet original.
    """
    table_name = _FILENAME_TO_TABLE.get(filename)
    con = get_duckdb_con()
    
    if con and table_name:
        try:
            level = "UNKNOWN"
            inst = None
            ent = None
            ac = None
            v_mode = view_mode
            
            if institution_name:
                inst = "MEXICO" if str(institution_name).upper() in ["MEXICO", "MÉXICO"] else str(institution_name).replace('/', '_').replace('\\', '_')
                level = "NATIONAL" if inst == "MEXICO" else "INSTITUTION"
            
            if entity_name and entity_name != institution_name:
                ent = str(entity_name).replace('/', '_').replace('\\', '_')
                level = "ENTITY"
            else:
                ent = inst
                
            if academic_name:
                ac = str(academic_name).replace('/', '_').replace('\\', '_')
                level = "RESEARCHER"

            where_clauses = ["db_level = ?"]
            params = [level]
            
            if inst:
                where_clauses.append("db_institution_name = ?")
                params.append(inst)
            if ent:
                where_clauses.append("db_entity_name = ?")
                params.append(ent)
            if ac:
                where_clauses.append("db_academic_name = ?")
                params.append(ac)
            
            if level != "RESEARCHER" and v_mode:
                where_clauses.append("db_view_mode = ?")
                params.append(v_mode)
                
            where_sql = " AND ".join(where_clauses)
            
            exists = con.execute(f"SELECT count(*) FROM information_schema.tables WHERE table_name = '{table_name}'").fetchone()[0] > 0
            if exists:
                df = con.execute(f"SELECT * FROM {table_name} WHERE {where_sql}", params).df()
                con.close()
                if not df.empty:
                    df = df.drop(columns=['db_level', 'db_view_mode', 'db_institution_name', 'db_entity_name', 'db_academic_name'], errors='ignore')
                    # Convert JSON strings back to lists
                    for col in df.columns:
                        if df[col].dtype == object:
                            try:
                                sample = df[col].dropna().iloc[0]
                                if isinstance(sample, str) and (sample.startswith('[') or sample.startswith('{')):
                                    df[col] = df[col].apply(lambda x: json.loads(x) if isinstance(x, str) and (x.startswith('[') or x.startswith('{')) else x)
                            except:
                                pass
                    return df
            con.close()
        except Exception as e:
            try:
                con.close()
            except:
                pass
            pass # Fallback to parquet

    path = None

    # Si se busca un académico, encontrar su archivo más reciente globalmente en el caché
    if academic_name:
        import glob
        safe_ac = str(academic_name).replace('/', '_').replace('\\', '_')
        matches = glob.glob(os.path.join(CACHE_DIR, "**", safe_ac, filename), recursive=True)
        if matches:
            matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            try:
                return pd.read_parquet(matches[0])
            except Exception:
                pass
    
    # 1. Intentar estructura jerárquica (Nacional)
    if institution_name:
        if str(institution_name).upper() in ["MEXICO", "MÉXICO"]:
            safe_inst = "MEXICO"
        else:
            safe_inst = str(institution_name).replace('/', '_').replace('\\', '_')

        # Directorio base de la vista
        view_dir = "capacidad_instalada" if view_mode == "capacidad_instalada" else "produccion_institucional"

        if entity_name and academic_name:
            safe_ent = str(entity_name).replace('/', '_').replace('\\', '_')
            safe_ac = str(academic_name).replace('/', '_').replace('\\', '_')
            path = os.path.join(CACHE_DIR, safe_inst, safe_ent, safe_ac, filename)
            # Fallback a carpeta de capacidad si no está en raíz (por compatibilidad)
            if not os.path.exists(path):
                 path = os.path.join(CACHE_DIR, safe_inst, safe_ent, safe_ac, "capacidad_instalada", filename)
        elif entity_name and entity_name != institution_name:
            safe_ent = str(entity_name).replace('/', '_').replace('\\', '_')
            # Intentar primero en la subcarpeta de la vista seleccionada
            path = os.path.join(CACHE_DIR, safe_inst, safe_ent, view_dir, filename)
            if not os.path.exists(path):
                # Fallback a raíz de entidad
                path = os.path.join(CACHE_DIR, safe_inst, safe_ent, filename)
        else:
            # Nivel Institución: Intentar en la carpeta de la vista
            path = os.path.join(CACHE_DIR, safe_inst, view_dir, filename)
            if not os.path.exists(path):
                # Fallback a raíz de institución
                path = os.path.join(CACHE_DIR, safe_inst, filename)
            
        if path and os.path.exists(path):
            return pd.read_parquet(path)

    # 2. Fallback a estructura original (Legacy / Académicos fuera de ROR)
    if entity_name and academic_name:
        safe_ent = str(entity_name).replace('/', '_').replace('\\', '_')
        safe_ac = str(academic_name).replace('/', '_').replace('\\', '_')
        path = os.path.join(CACHE_DIR, safe_ent, safe_ac, filename)
    elif entity_name:
        safe_ent = str(entity_name).replace('/', '_').replace('\\', '_')
        path = os.path.join(CACHE_DIR, safe_ent, filename)
    else:
        path = os.path.join(CACHE_DIR, filename)
        
    if path and os.path.exists(path):
        return pd.read_parquet(path)
    return None

def get_cached_data(filename, entity_name=None, academic_name=None, institution_name=None, view_mode="capacidad_instalada"):
    """Wrapper que pasa el mtime del archivo para invalidar el cache de Streamlit automáticamente."""
    path = None
    view_dir = "capacidad_instalada" if view_mode == "capacidad_instalada" else "produccion_institucional"
    
    if academic_name:
        import glob
        safe_ac = str(academic_name).replace('/', '_').replace('\\', '_')
        matches = glob.glob(os.path.join(CACHE_DIR, "**", safe_ac, filename), recursive=True)
        if matches:
            matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            path = matches[0]

    if not path and institution_name:
        if str(institution_name).upper() in ["MEXICO", "MÉXICO"]:
            safe_inst = "MEXICO"
        else:
            safe_inst = str(institution_name).replace('/', '_').replace('\\', '_')
        
        if entity_name and academic_name:
            safe_ent = str(entity_name).replace('/', '_').replace('\\', '_')
            safe_ac = str(academic_name).replace('/', '_').replace('\\', '_')
            path = os.path.join(CACHE_DIR, safe_inst, safe_ent, safe_ac, filename)
        elif entity_name:
            safe_ent = str(entity_name).replace('/', '_').replace('\\', '_')
            path = os.path.join(CACHE_DIR, safe_inst, safe_ent, view_dir, filename)
            if not os.path.exists(path):
                 path = os.path.join(CACHE_DIR, safe_inst, safe_ent, filename)
        else:
            path = os.path.join(CACHE_DIR, safe_inst, view_dir, filename)
            if not os.path.exists(path):
                path = os.path.join(CACHE_DIR, safe_inst, filename)
            
    if not path or not os.path.exists(path):
        mtime = None
    else:
        mtime = os.path.getmtime(path)
        
    return load_cached_data(filename, entity_name, academic_name, institution_name, view_mode=view_mode, _mtime=mtime)

def cargar_lista_academicos(ruta_json="ingestion/profesores_Instituto_de_Ciencias_Nucleares.json"):
    path = os.path.join(BASE_PATH, ruta_json)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

@st.cache_data(ttl=3600)
def load_snii_matches():
    """Carga el mapeo verificado por LLM de SNII a OpenAlex."""
    path = os.path.join(BASE_PATH, 'data', 'snii_llm_verified_matches.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Indexar por nombre para búsqueda rápida
            return {x['snii_author']: x for x in data if 'snii_author' in x}
    except Exception as e:
        print(f"Error cargando SNII matches: {e}")
        return {}

def _fix_enc(s: str) -> str:
    """Repara mojibake en el Excel del padr\u00f3n SNII 2025 (4T_2025).
    Algunos valores tienen un doble-encoding donde los bytes UTF-8 de caracteres
    acentuados espa\u00f1oles fueron re-interpretados como Latin-1/CP1252, resultando
    en pares como: \u00c3\u2018 (Ã+\u2018) en lugar de \u00d1 (\u00d1), o \u00c3\u0152 en lugar de \u00dc (\u00dc).
    """
    _MOJIBAKE_MAP = [
        ('\u00c3\u2018', '\u00d1'),   # c3 91 -> Ñ (capital N-tilde)
        ('\u00c3\u0152', '\u00dc'),   # c3 9c -> Ü (capital U-umlaut)
        ('\u00c3\u201c', '\u00d3'),   # c3 93 -> Ó (capital O-acute)
        ('\u00c3\u2020', '\u00c7'),   # c3 87 -> Ç (capital C-cedilla)
        ('\u00c3\x8d',   '\u00cd'),   # c3 8d -> Í (capital I-acute)
        ('\u00c3\xa9', '\u00e9'),     # c3 a9 -> é (small e-acute)
        ('\u00c3\xa1', '\u00e1'),     # c3 a1 -> á (small a-acute)
        ('\u00c3\xad', '\u00ed'),     # c3 ad -> í (small i-acute)
        ('\u00c3\xb3', '\u00f3'),     # c3 b3 -> ó (small o-acute)
        ('\u00c3\xba', '\u00fa'),     # c3 ba -> ú (small u-acute)
        ('\u00c3\xb1', '\u00f1'),     # c3 b1 -> ñ (small n-tilde)
        ('\u00c3\xbc', '\u00fc'),     # c3 bc -> ü (small u-umlaut)
        ('\u00c3\xb9', '\u00f9'),     # c3 b9 -> ù (small u-grave)
    ]
    for bad, good in _MOJIBAKE_MAP:
        if bad in s:
            s = s.replace(bad, good)
    return s

@st.cache_data(show_spinner=False, ttl=86400)
def load_hierarchy():
    """Carga jerarquía instituciones -> dependencias -> subdependencias
    exclusivamente desde el Padrón SNII 2025 (hoja 4T_2025).
    Esta fuente contiene únicamente instituciones mexicanas.
    """
    # Ruta al Excel del padrón 2025 (fuente de verdad)
    excel_paths = [
        os.path.join(BASE_PATH, 'data', 'Investigadores_vigentes_2025.xlsx'),
    ]
    sheet_name = '4T_2025 (44,794)'
    hierarchy = {}

    for excel_path in excel_paths:
        if not os.path.exists(excel_path):
            continue
        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)

            inst_col = 'INSTITUCION DE ACREDITACION'
            dep_col  = 'DEPENDENCIA DE ACREDITACIÓN'
            sub_col  = 'SUBDEPENDENCIA DE ACREDITACIÓN'

            for _, row in df.iterrows():
                inst = _fix_enc(str(row.get(inst_col, '') or '').strip())
                dep  = _fix_enc(str(row.get(dep_col,  '') or '').strip())
                sub  = _fix_enc(str(row.get(sub_col,  '') or '').strip())

                # Omitir filas sin institución real
                if not inst or inst.upper() in ('SIN INSTITUCION', 'NAN', ''):
                    continue

                if inst not in hierarchy:
                    hierarchy[inst] = {}

                dep_key = dep if dep and dep.upper() not in ('NAN', '', 'NO APLICA', 'SIN INFORMACIÓN', 'SIN INFORMACION') else inst
                if dep_key not in hierarchy[inst]:
                    hierarchy[inst][dep_key] = set()

                if sub and sub.upper() not in ('NAN', '', 'NO APLICA', 'SIN INFORMACIÓN', 'SIN INFORMACION'):
                    hierarchy[inst][dep_key].add(sub)

            # Convertir sets a listas ordenadas
            for inst in hierarchy:
                for dep in hierarchy[inst]:
                    hierarchy[inst][dep] = sorted(list(hierarchy[inst][dep]))

            # Agregador Nacional
            hierarchy["MÉXICO"] = {inst: [] for inst in hierarchy.keys() if inst != "MÉXICO"}
            print(f"[load_hierarchy] Jerarquía cargada desde padrón 2025: {len(hierarchy)-1} instituciones mexicanas.")
            return hierarchy

        except Exception as e:
            print(f"[load_hierarchy] Error procesando {excel_path}: {e}")
            continue

    # Fallback a hierarchy.json en cache si el Excel no está disponible
    json_path = os.path.join(CACHE_DIR, 'hierarchy.json')
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[load_hierarchy] Error leyendo hierarchy.json: {e}")

    return {}

# Alias de compatibilidad hacia atrás (dashboard_v2.py lo importa con el nombre anterior)
get_institution_hierarchy = load_hierarchy

def mostrar_banners_destacados(df):
    st.subheader("Publicaciones Destacadas")
    
    if df.empty:
        st.info("Sin publicaciones para mostrar.")
        return

    # Resolver nombres de columnas con tolerancia a mayúsculas/minúsculas
    cols = df.columns.tolist()
    title_col = next((c for c in cols if c.lower() == "title"), None)
    doi_col   = next((c for c in cols if c.lower() == "doi"), None)

    if title_col is None:
        st.info("Sin información de publicaciones para mostrar (columna de título no encontrada).")
        return

    # Preparamos los datos
    df_sorted_citas    = df.sort_values(by="citations", ascending=False).head(10)
    df_sorted_recientes = df.sort_values(by="year", ascending=False).head(10)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🔥 Artículos Más Citados")
        for _, row in df_sorted_citas.iterrows():
            doi_val = row[doi_col] if doi_col else None
            title_val = row[title_col]
            Title = f"[{title_val}]({doi_val})" if doi_val and str(doi_val).strip() not in ("", "nan", "None") else str(title_val)
            st.markdown(f"**{int(row['citations'])} citas** - {Title} ({int(row['year']) if pd.notna(row['year']) else 'N/A'})")

    with col2:
        st.markdown("#### 🚀 Artículos Más Recientes")
        for _, row in df_sorted_recientes.iterrows():
            doi_val = row[doi_col] if doi_col else None
            title_val = row[title_col]
            Title = f"[{title_val}]({doi_val})" if doi_val and str(doi_val).strip() not in ("", "nan", "None") else str(title_val)
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


@st.cache_data(ttl=3600)
def _get_sources_display_names_v3(source_ids):
    """Obtiene el display_name de las fuentes/revistas desde ClickHouse en lotes seguros."""
    if not source_ids:
        return {}
    
    try:
        from database.clickhouse_db import ch_client
    except ImportError:
        return {}

    valid_ids = []
    for sid in source_ids:
        if not sid:
            continue
        sid_str = str(sid).strip()
        if sid_str.startswith('https://openalex.org/S'):
            valid_ids.append(sid_str)
        elif sid_str.startswith('S') and sid_str[1:].isdigit():
            valid_ids.append(f'https://openalex.org/{sid_str}')
            
    if not valid_ids:
        return {}
        
    mapping = {}
    chunk_size = 500
    for i in range(0, len(valid_ids), chunk_size):
        chunk = valid_ids[i:i + chunk_size]
        query = "SELECT id, display_name FROM sources WHERE id IN %(ids)s"
        try:
            df_src = ch_client.query_df(query, {"ids": chunk})
            if not df_src.empty:
                for _, row in df_src.iterrows():
                    full_id = row['id']
                    name = row['display_name']
                    mapping[full_id] = name
                    short_id = full_id.split('/')[-1]
                    mapping[short_id] = name
        except Exception as e:
            st.warning(f"Error parcial al consultar revistas a ClickHouse: {str(e)}")
    return mapping


@st.cache_data(ttl=3600)
def _get_authors_display_names_v3(author_ids):
    """Obtiene el display_name de los autores desde ClickHouse en lotes seguros."""
    if not author_ids:
        return {}
    from database.clickhouse_db import ch_client
    valid_ids = []
    for aid in author_ids:
        if not aid:
            continue
        aid_str = str(aid).strip()
        if aid_str.startswith('https://openalex.org/A'):
            valid_ids.append(aid_str)
        elif aid_str.startswith('A') and aid_str[1:].isdigit():
            valid_ids.append(f'https://openalex.org/{aid_str}')
            
    if not valid_ids:
        return {}
        
    mapping = {}
    chunk_size = 500
    for i in range(0, len(valid_ids), chunk_size):
        chunk = valid_ids[i:i + chunk_size]
        query = "SELECT id, display_name FROM authors WHERE id IN %(ids)s"
        try:
            df_aut = ch_client.query_df(query, {"ids": chunk})
            if not df_aut.empty:
                for _, row in df_aut.iterrows():
                    full_id = row['id']
                    name = row['display_name']
                    mapping[full_id] = name
                    short_id = full_id.split('/')[-1]
                    mapping[short_id] = name
        except Exception as e:
            st.warning(f"Error parcial al consultar autores a ClickHouse: {str(e)}")
    return mapping


def _prepare_papers_table(df_papers):
    """Enriquece el DataFrame de artículos con nombres de revistas, autores y openalex_url (con fallback flexible y seguro)."""
    if df_papers.empty:
        return df_papers.copy()
    
    df = df_papers.copy()
    
    # 1. OpenAlex URL
    if 'paper_id' in df.columns:
        df['openalex_url'] = df['paper_id'].where(df['paper_id'].notna(), None)
    else:
        df['openalex_url'] = None

    # 2. Nombre de la revista
    source_col = 'Source' if 'Source' in df.columns else ('source' if 'source' in df.columns else None)
    if source_col:
        source_ids = df[source_col].dropna().unique().tolist()
        src_mapping = _get_sources_display_names_v3(source_ids)
        
        def translate_source(val):
            if not val:
                return val
            val_str = str(val).strip()
            if val_str in src_mapping:
                return src_mapping[val_str]
            if val_str.startswith('https://openalex.org/S'):
                short = val_str.split('/')[-1]
                return src_mapping.get(short, short)
            return val
            
        df[source_col] = df[source_col].apply(translate_source)

    # 3. Autores formateados
    author_col = 'author_names' if 'author_names' in df.columns else ('authors' if 'authors' in df.columns else None)
    if author_col:
        all_author_ids = set()
        for val in df[author_col].dropna():
            if isinstance(val, (list, np.ndarray)):
                for aid in val:
                    aid_str = str(aid).strip()
                    if aid_str:
                        all_author_ids.add(aid_str)
            elif isinstance(val, str):
                val_str = val.strip()
                if val_str.startswith('['):
                    try:
                        import ast
                        parsed = ast.literal_eval(val_str)
                        if isinstance(parsed, list):
                            for aid in parsed:
                                all_author_ids.add(str(aid).strip())
                            continue
                    except Exception:
                        pass
                if ',' in val_str:
                    parts = [p.strip() for p in val_str.split(',')]
                    for p in parts:
                        if p:
                            all_author_ids.add(p)
                else:
                    if val_str:
                        all_author_ids.add(val_str)
                        
        auth_mapping = _get_authors_display_names_v3(list(all_author_ids))
        
        def format_authors(val):
            if val is None:
                return ""
            if isinstance(val, (list, np.ndarray)):
                if len(val) == 0:
                    return ""
            else:
                if pd.isna(val) or str(val).strip() == "":
                    return ""
                    
            def resolve_name(aid):
                aid_str = str(aid).strip()
                if aid_str in auth_mapping:
                    return auth_mapping[aid_str]
                if aid_str.startswith('https://openalex.org/A'):
                    short = aid_str.split('/')[-1]
                    return auth_mapping.get(short, short)
                return aid_str
                
            if isinstance(val, (list, np.ndarray)):
                return ", ".join([resolve_name(aid) for aid in val if aid])
            elif isinstance(val, str):
                val_str = val.strip()
                if val_str.startswith('['):
                    try:
                        import ast
                        parsed = ast.literal_eval(val_str)
                        if isinstance(parsed, list):
                            return ", ".join([resolve_name(aid) for aid in parsed if aid])
                    except Exception:
                        pass
                if ',' in val_str:
                    parts = [p.strip() for p in val_str.split(',')]
                    return ", ".join([resolve_name(p) for p in parts if p])
                return resolve_name(val_str)
            return str(val)
            
        df['_formatted_authors'] = df[author_col].apply(format_authors)
    else:
        df['_formatted_authors'] = ""

    # 4. Asegurar tópicos
    if 'topic' not in df.columns:
        df['topic'] = None
        
    return df


def _compute_umap_kde(df, z_col, resolution=120, sigma_frac=0.06):
    """
    Puerto fiel del algoritmo de Gaussian Splatting de LabSOM/UmapHeatmap.tsx.
    
    Para cada punto (umap_x, umap_y, valor), irradia su valor a los píxeles
    vecinos con peso gaussiano. Produce:
      - value_grid: promedio ponderado del indicador por píxel
      - alpha_grid: densidad (opacidad) normalizada por píxel
    """
    xs = df['umap_x'].values
    ys = df['umap_y'].values
    vs = df[z_col].fillna(0).values

    if len(xs) == 0:
        return None, None, None, None, None, None

    # Rango con padding (igual que LabSOM)
    rng_x = xs.max() - xs.min() or 1.0
    rng_y = ys.max() - ys.min() or 1.0
    pad_x, pad_y = rng_x * 0.1, rng_y * 0.1
    min_x, max_x = xs.min() - pad_x, xs.max() + pad_x
    min_y, max_y = ys.min() - pad_y, ys.max() + pad_y
    safe_x = max_x - min_x
    safe_y = max_y - min_y

    # Sigma en píxeles (igual que LabSOM: sigma * resolution)
    s = max(sigma_frac, 0.01) * resolution
    radius = int(np.ceil(3 * s))

    density_map   = np.zeros((resolution, resolution), dtype=np.float64)
    value_map     = np.zeros((resolution, resolution), dtype=np.float64)
    weight_sum    = np.zeros((resolution, resolution), dtype=np.float64)

    for x, y, v in zip(xs, ys, vs):
        gx = ((x - min_x) / safe_x) * resolution
        gy = ((y - min_y) / safe_y) * resolution
        cx = int(round(gx))
        cy = int(round(gy))
        x0, x1 = max(0, cx - radius), min(resolution - 1, cx + radius)
        y0, y1 = max(0, cy - radius), min(resolution - 1, cy + radius)

        # Vectorizado sobre el parche (mucho más rápido que el doble loop Python)
        pxs = np.arange(x0, x1 + 1)
        pys = np.arange(y0, y1 + 1)
        PX, PY = np.meshgrid(pxs, pys)
        d2 = (gx - PX) ** 2 + (gy - PY) ** 2
        mask = d2 <= 9 * s * s
        w = np.exp(-d2 / (2 * s * s)) * mask
        density_map[y0:y1+1, x0:x1+1] += w
        weight_sum [y0:y1+1, x0:x1+1] += w
        value_map  [y0:y1+1, x0:x1+1] += w * v

    # Promedio ponderado del valor (igual que LabSOM)
    nonzero = weight_sum > 0
    value_map[nonzero] /= weight_sum[nonzero]

    # Normalizar densidad: opacidad plena al 8% de la densidad máxima (igual que LabSOM)
    max_density = density_map.max()
    alpha_norm = max_density * 0.08 if max_density > 0 else 1.0
    alpha_grid = np.clip(density_map / alpha_norm, 0, 1)

    # Umbral de densidad mínima: corta las colas débiles de la gaussiana.
    # Con threshold=4% del máximo, un punto aislado es visible hasta ~2.5σ,
    # mostrando la forma de campana claramente sin extenderse al borde.
    density_threshold = max_density * 0.04  # 4% del máximo
    visible = nonzero & (density_map >= density_threshold)

    # Recorte percentil 2-98 para la escala de color (igual que LabSOM)
    vals_valid = value_map[visible]
    clip_min = np.percentile(vals_valid, 2) if len(vals_valid) > 0 else 0
    clip_max = np.percentile(vals_valid, 98) if len(vals_valid) > 0 else 1
    value_map_clipped = np.clip(value_map, clip_min, clip_max)

    # Aplicar máscara: NaN en zonas sin densidad suficiente (plotly las omite)
    value_map_clipped[~visible] = np.nan
    alpha_grid[~visible] = np.nan

    # Ejes en el espacio original para plotly
    x_axis = np.linspace(min_x, max_x, resolution)
    y_axis = np.linspace(min_y, max_y, resolution)

    return value_map_clipped, alpha_grid, x_axis, y_axis, clip_min, clip_max


def _create_umap_heatmap_fig(df, z_col, title, show_contour_lines=True):
    """
    Genera un mapa de calor UMAP con Gaussian Splatting idéntico al de LabSOM.
    El KDE se renderiza como imagen RGBA (control per-pixel de alpha) via
    matplotlib, se codifica en base64 y se incrusta en Plotly como layout_image.
    El go.Scatter invisible encima mantiene el hover interactivo.
    """
    fig = go.Figure()

    value_grid, alpha_grid, x_axis, y_axis, clip_min, clip_max = _compute_umap_kde(df, z_col)
    if value_grid is None:
        return fig

    res = value_grid.shape[0]
    min_x, max_x = x_axis[0], x_axis[-1]
    min_y, max_y = y_axis[0], y_axis[-1]

    # --- Renderizar imagen RGBA con matplotlib (igual que el Canvas de LabSOM) ---
    cmap = mcm.get_cmap('Blues')
    v_range = clip_max - clip_min if clip_max > clip_min else 1.0
    norm_grid = np.clip((value_grid - clip_min) / v_range, 0, 1)

    # RGBA: (R, G, B) del colormap + Alpha de la densidad
    rgba = cmap(norm_grid)  # shape (res, res, 4)
    # Aplicar alpha de densidad pixel a pixel (igual que LabSOM)
    alpha_safe = np.where(np.isnan(alpha_grid), 0.0, np.clip(alpha_grid, 0, 1))
    rgba[..., 3] = alpha_safe  # sobreescribir canal alpha
    # Donde value es NaN (sin datos), forzar transparente
    nan_mask = np.isnan(value_grid)
    rgba[nan_mask, 3] = 0.0

    # Exportar a PNG en memoria
    buf = io.BytesIO()
    # La imagen matplotlib tiene origen en la esquina superior izquierda,
    # Plotly usa el sistema de ejes (y crece hacia arriba), así que invertimos Y
    fig_mpl, ax_mpl = plt.subplots(figsize=(res / 72, res / 72), dpi=72)
    ax_mpl.imshow(
        rgba[::-1],  # Invertir eje Y para que coincida con Plotly
        extent=[min_x, max_x, min_y, max_y],
        aspect='auto', interpolation='bilinear'
    )
    ax_mpl.axis('off')
    fig_mpl.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig_mpl.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0)
    plt.close(fig_mpl)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode('utf-8')
    img_src = f'data:image/png;base64,{img_b64}'

    # Curvas de nivel como traza Plotly separada (toggleable)
    if show_contour_lines:
        fig.add_trace(go.Contour(
            z=value_grid,
            x=x_axis,
            y=y_axis,
            showscale=False,
            name='',
            showlegend=False,
            contours=dict(coloring='none', showlabels=False),
            line=dict(width=0.8, color='rgba(0,43,92,0.35)'),
            hoverinfo='skip',
        ))

    # Scatter invisible encima para el hover interactivo
    z_vals = df[z_col].fillna(0).clip(lower=0)
    fig.add_trace(go.Scatter(
        x=df['umap_x'], y=df['umap_y'],
        mode='markers',
        text=df['academic_name'],
        marker=dict(
            size=5,
            color=z_vals,
            colorscale='Blues',
            cmin=clip_min,
            cmax=clip_max,
            opacity=0.9,
            line=dict(width=0.5, color='rgba(0,43,92,0.4)')
        ),
        hovertemplate="<b>%{text}</b><br>Doc: %{customdata[0]}<br>FWCI: %{customdata[1]:.2f}<br>% Top 10: %{customdata[2]:.1f}%<br>% Top 1%: %{customdata[3]:.1f}%",
        customdata=df[['num_documents', 'fwci_avg', 'pct_top_10', 'pct_1']],
        showlegend=False
    ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        hovermode='closest',
        height=300,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(visible=False, range=[min_x, max_x]),
        yaxis=dict(visible=False, range=[min_y, max_y]),
        template='plotly_white',
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        images=[dict(
            source=img_src,
            xref='x', yref='y',
            x=min_x, y=max_y,
            sizex=max_x - min_x,
            sizey=max_y - min_y,
            sizing='stretch',
            opacity=1.0,
            layer='below'
        )]
    )
    return fig


def _render_umap_plot(df_umap, selected_inv, title_context, key_suffix=""):
    """
    Renderiza un gráfico de Plotly go.Scatter con el UMAP de desempeño
    comparando al investigador seleccionado contra sus pares.
    """
    if df_umap is None or df_umap.empty:
        st.info(f"El mapa UMAP ({title_context}) no está disponible o faltan datos base calculados.")
        return

    # Evitamos mutar el dataframe original en caché
    df_umap = df_umap.copy()
    if 'academic_name' in df_umap.columns:
        mask = df_umap['academic_name'] == 'SERKIN, LEONID'
        if mask.any():
            for col in ['num_documents', 'fwci_avg', 'pct_top_10', 'pct_1', 'citations']:
                if col in df_umap.columns:
                    df_umap.loc[mask, col] = 1.0

    metrics_map = {
        "Documentos": "num_documents",
        "Impacto (FWCI)": "fwci_avg",
        "Excelencia (% Top 10)": "pct_top_10",
        "Citas Totales": "citations"
    }
    
    available_metrics = {k: v for k, v in metrics_map.items() if v in df_umap.columns}
    if not available_metrics:
        available_metrics = {"Documentos": "num_documents"}
        df_umap["num_documents"] = 1
        
    default_idx = 0
    if "Documentos" in available_metrics:
        default_idx = list(available_metrics.keys()).index("Documentos")
        
    size_metric_label = st.selectbox(
        "Métrica para el tamaño de la burbuja:", 
        options=list(available_metrics.keys()),
        index=default_idx,
        key=f"umap_size_metric_{key_suffix}"
    )
    size_metric_col = available_metrics[size_metric_label]

    fig_umap = go.Figure()

    # Configurar escalado de burbujas basado en la métrica seleccionada
    max_metric = df_umap[size_metric_col].max() if size_metric_col in df_umap.columns else 1
    sizeref = 2.0 * max(max_metric, 0.001) / (50. ** 2)

    # Otros investigadores (Puntos grises)
    otros = df_umap[df_umap['academic_name'] != selected_inv]
    if not otros.empty:
        fig_umap.add_trace(go.Scatter(
            x=otros['umap_x'], y=otros['umap_y'],
            mode='markers',
            name='Resto de investigadores',
            text=otros['academic_name'],
            marker=dict(
                size=otros[size_metric_col].fillna(0).clip(lower=0.1),
                sizemode='area',
                sizeref=sizeref,
                sizemin=2,
                color='#003D64', opacity=0.3, line=dict(width=1, color='darkgray')
            ),
            hovertemplate="<b>%{text}</b><br>Doc: %{customdata[0]}<br>Citas: %{customdata[1]}<br>FWCI: %{customdata[2]:.2f}<br>% Top 10: %{customdata[3]:.1f}%<br>% Top 1%: %{customdata[4]:.1f}%",
            customdata=otros[['num_documents', 'citations', 'fwci_avg', 'pct_top_10', 'pct_1']]
        ))

    # Investigador seleccionado (Punto destacado como una estrella dorada)
    sel_row = df_umap[df_umap['academic_name'] == selected_inv]
    if not sel_row.empty:
        fig_umap.add_trace(go.Scatter(
            x=sel_row['umap_x'], y=sel_row['umap_y'],
            mode='markers',
            name=selected_inv,
            text=sel_row['academic_name'],
            marker=dict(
                size=16,
                color='#E8442A', symbol='circle', line=dict(width=2, color='#FFFFFF')
            ),
            hovertemplate="<b>%{text}</b><br>Doc: %{customdata[0]}<br>Citas: %{customdata[1]}<br>FWCI: %{customdata[2]:.2f}<br>% Top 10: %{customdata[3]:.1f}%<br>% Top 1%: %{customdata[4]:.1f}%",
            customdata=sel_row[['num_documents', 'citations', 'fwci_avg', 'pct_top_10', 'pct_1']]
        ))

    fig_umap.update_layout(
        hovermode="closest",
        height=450,
        template="plotly_white",
        margin=dict(l=0,r=0,t=30,b=0),
        xaxis_title="Dimensión 1",
        yaxis_title="Dimensión 2",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_umap, use_container_width=True, key=f"umap_chart_{key_suffix}")

    # --- Lazy-loading de Mapas de Calor ---
    # st.expander siempre ejecuta su contenido en Python aunque esté cerrado.
    # Usamos session_state para que el cálculo KDE+matplotlib solo ocurra
    # cuando el usuario lo solicite explícitamente.
    hm_state_key = f"heatmaps_loaded_{key_suffix}"
    hm_contour_key = f"contour_lines_{key_suffix}"

    if hm_state_key not in st.session_state:
        st.session_state[hm_state_key] = False

    with st.expander("Ver Mapas de Calor por Indicador (Densidad)", expanded=False):
        if not st.session_state[hm_state_key]:
            if st.button(
                "📊 Generar Mapas de Calor",
                key=f"load_hm_btn_{key_suffix}",
                help="Los mapas de calor requieren un cálculo adicional. Haz clic para generarlos.",
                use_container_width=True
            ):
                st.session_state[hm_state_key] = True
                st.rerun()
        else:
            chart_container = st.container()

            st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
            col_chk, col_reset = st.columns([4, 1])
            with col_chk:
                show_contour_lines = st.checkbox(
                    "Mostrar curvas de nivel", value=True, key=hm_contour_key
                )
            with col_reset:
                if st.button("↺ Limpiar", key=f"clear_hm_{key_suffix}", help="Descarga los mapas de la memoria"):
                    st.session_state[hm_state_key] = False
                    st.rerun()

            with chart_container:
                col1, col2 = st.columns(2)
                heatmaps = []
                for name, col_name in metrics_map.items():
                    if col_name in df_umap.columns:
                        fig_hm = _create_umap_heatmap_fig(df_umap, col_name, name, show_contour_lines)
                        heatmaps.append(fig_hm)

                for i, fig_hm in enumerate(heatmaps):
                    if i % 2 == 0:
                        with col1:
                            st.plotly_chart(fig_hm, use_container_width=True, key=f"hm_{i}_{key_suffix}")
                    else:
                        with col2:
                            st.plotly_chart(fig_hm, use_container_width=True, key=f"hm_{i}_{key_suffix}")



def _render_document_types_pie(df_papers, key_suffix=""):
    """
    Dibuja un gráfico de pastel con la distribución de tipos de documentos.
    El campo en el DataFrame es 'wf.type'.
    """
    if df_papers is None or df_papers.empty or 'wf.type' not in df_papers.columns:
        st.info("Sin información de tipos de documentos.")
        return

    # Contar frecuencias y filtrar nulos
    type_counts = df_papers['wf.type'].fillna('other').value_counts()
    
    # Filtrar estrictamente categorías con conteo > 0
    type_counts = type_counts[type_counts > 0]
    
    if type_counts.empty:
        st.info("Sin información de tipos de documentos.")
        return

    # Diccionario de traducción al español para todos los tipos de OpenAlex
    translation = {
        'article': 'Artículo',
        'book': 'Libro',
        'book-chapter': 'Capítulo de Libro',
        'dataset': 'Conjunto de Datos',
        'dissertation': 'Tesis',
        'editorial': 'Editorial',
        'erratum': 'Fe de Erratas',
        'letter': 'Carta',
        'libguides': 'Guía Temática',
        'other': 'Otro',
        'paratext': 'Paratexto',
        'peer-review': 'Revisión por Pares',
        'preprint': 'Preprint',
        'reference-entry': 'Entrada de Referencia',
        'report': 'Reporte / Informe',
        'retraction': 'Retractación',
        'review': 'Revisión (Review)',
        'standard': 'Estándar / Norma',
        'supplementary-materials': 'Material Suplementario'
    }

    labels = []
    values = []
    for raw_type, count in type_counts.items():
        translated = translation.get(str(raw_type).lower(), str(raw_type).capitalize())
        labels.append(translated)
        values.append(int(count))

    # Colores premium (paleta UNAM adaptada)
    colors = [
        "#003D64", "#E39918", "#1E6FB5", "#B6932B", 
        "#2ECC71", "#3498DB", "#E74C3C", "#9B59B6",
        "#1ABC9C", "#95A5A6", "#34495E"
    ]

    fig = go.Figure(data=[go.Pie(
        labels=labels, 
        values=values, 
        hole=0.4,
        marker=dict(colors=colors),
        hovertemplate="<b>%{label}</b><br>%{value:,} documentos<br>%{percent:.1f}%<extra></extra>",
        textinfo="percent", 
        textposition="auto",
    )])

    fig.update_layout(
        height=380, 
        margin=dict(t=30, b=30, l=10, r=10),
        showlegend=True, 
        legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.05),
    )

    st.plotly_chart(fig, use_container_width=True, key=f"pie_doc_types_{key_suffix}")



def _render_velocity_sparkline(df_papers, name_col, name_val, key_suffix="", return_fig=False):
    """Sparkline de trayectoria de citas acumuladas por año."""
    from collections import defaultdict
    df_p = df_papers[df_papers[name_col] == name_val].copy()
    if df_p.empty or "counts_by_year" not in df_p.columns:
        st.info("Sin datos de trayectoria de citas.")
        return
    year_cites: dict = defaultdict(int)
    for val in df_p["counts_by_year"]:
        if isinstance(val, (list, np.ndarray)):
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
        line=dict(color="#003D64", width=2.5),
        marker=dict(size=5, color="#E39918", line=dict(width=1, color="#b6932b")),
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
    import pytz
    df_p = df_papers[df_papers[name_col] == name_val].copy()
    if df_p.empty or "countries" not in df_p.columns:
        st.info("Sin datos de colaboración internacional.")
        return
    cnt: Counter = Counter()
    for val in df_p["countries"]:
        if isinstance(val, (list, np.ndarray)):
            cnt.update(c for c in val if c and c != "MX")
    if not cnt:
        st.info("No se detectó colaboración internacional registrada.")
        return
    df_cnt = pd.DataFrame(cnt.most_common(80), columns=["iso_a2", "papers"])
    
    # Mapeo de ISO2 a ISO3 para Plotly
    df_cnt['iso_a3'] = df_cnt['iso_a2'].map(ISO2_TO_ISO3).fillna(df_cnt['iso_a2'])
    df_cnt['País'] = df_cnt['iso_a2'].apply(lambda x: pytz.country_names.get(x, x))
    
    fig = px.choropleth(
        df_cnt, locations="iso_a3", locationmode="ISO-3",
        color="papers",
        color_continuous_scale="Blues",
        title=title,
        labels={"papers": "Papers conjuntos"},
        hover_name="País",
    )
    fig.update_layout(
        height=380, margin=dict(t=30,b=0,l=0,r=0),
        geo=dict(showframe=False, showcoastlines=True, bgcolor="rgba(0,0,0,0)",
                 showland=True, landcolor="#f0f0f0"),
        coloraxis_colorbar=dict(title="Papers", len=0.6),
    )
    if return_fig:
        return fig
    st.plotly_chart(fig, use_container_width=True, key=f"choro_{key_suffix}")


def _render_keywords_section(df_kw, name_col, name_val, title="Keywords principales", key_suffix="", return_fig=False):
    """Nube de palabras o barras horizontales de keywords."""
    if df_kw is None or df_kw.empty or name_col not in df_kw.columns:
        if df_kw is not None and not df_kw.empty:
            print(f"⚠️ Alerta: Columna {name_col} no encontrada en keywords. Columnas disponibles: {df_kw.columns}")
        return
    df_k = df_kw[df_kw[name_col] == name_val].sort_values("freq", ascending=False)
    if df_k.empty:
        st.info("Sin keywords registrados.")
        return
    freq_dict = dict(zip(df_k["keyword"], df_k["freq"]))
    if _HAS_WORDCLOUD and _wc_helper is not None:
        img_bytes = _wc_helper.generate_wordcloud_image(freq_dict, max_words=len(freq_dict))
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
        line=dict(color="#003D64", width=2),
        marker=dict(color="#E39918", size=7),
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


def render_institucion_view(entity_name, institution_name=None, view_mode="capacidad_instalada", parent_name=None):
    # Inyectar CSS global para estilizar st.metric como las tarjetas doradas del reporte
    st.markdown("""
        <style>
        [data-testid="stMetric"] {
            background-color: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
            text-align: center;
            border-top: 4px solid #E39918;
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
        /* Desactivar mayúsculas en la tercera columna para mostrar SNIIs correctamente */
        div[data-testid="column"]:nth-child(5) [data-testid="stMetricLabel"],
        [data-testid="stMetricLabel"]:has(button[aria-label*="SNII"]) {
            text-transform: none !important;
        }
        [data-testid="stMetricValue"] {
            font-size: 30px !important;
            font-weight: 700;
            color: #003D64;
        }
        /* Ajustar el delta si existe para que quede centrado también */
        [data-testid="stMetricDelta"] {
            justify-content: center;
        }
        </style>
    """, unsafe_allow_html=True)

    st.header(f"🏢 Vista de la Institución: {entity_name}")
    
    df_annual = load_cached_data("institucion_annual.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
    df_total = load_cached_data("institucion_total.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
    df_topics = load_cached_data("topics_institucion.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
    df_inst_papers = load_cached_data("papers_institucion.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)

    # 2. Fallback explícito: Comprobamos si existe físicamente el directorio de producción
    safe_inst = str(institution_name).replace('/', '_').replace('\\', '_') if institution_name else "MEXICO"
    safe_ent = str(entity_name).replace('/', '_').replace('\\', '_') if entity_name and entity_name != institution_name else ""
    prod_path = os.path.join(CACHE_DIR, safe_inst, safe_ent, "produccion_institucional") if safe_ent else os.path.join(CACHE_DIR, safe_inst, "produccion_institucional")

    if view_mode == "produccion_institucional" and not os.path.exists(prod_path):
        st.warning("⚠️ No se identificaron IDs institucionales (como ROR) para calcular la **Producción Institucional** estricta de esta entidad. Se muestran a continuación las métricas correspondientes a su **Capacidad Instalada** (producción de sus académicos).")
        view_mode = "capacidad_instalada"
        df_annual = load_cached_data("institucion_annual.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
        df_total = load_cached_data("institucion_total.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
        df_topics = load_cached_data("topics_institucion.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
        
    elif view_mode == "capacidad_instalada" and (df_total is None or df_total.empty):
        if os.path.exists(prod_path):
            st.warning("⚠️ No se encontraron papers asociados directamente a los perfiles de los académicos de esta entidad (**Capacidad Instalada**). Se muestran a continuación las métricas correspondientes a su **Producción Institucional** (papers firmados explícitamente a nombre de la entidad).")
            view_mode = "produccion_institucional"
            df_annual = load_cached_data("institucion_annual.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
            df_total = load_cached_data("institucion_total.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
            df_topics = load_cached_data("topics_institucion.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)

    # --- Identificadores Institucionales (Priorizar Cache para modo Offline) ---
    meta = None
    # Solo cargamos de la cache si la entidad es la institución raíz
    if entity_name == institution_name and df_total is not None and not df_total.empty:
        row = df_total.iloc[0]
        if row.get('ror_id') or row.get('institution_id'):
            meta = {
                'ror': row.get('ror_id'),
                'id': row.get('institution_id'),
                'type': row.get('institution_type'),
                'country_code': row.get('institution_country')
            }

    # Si no hay meta en el parquet cacheado, no se muestran los identificadores
    # (ClickHouse eliminado como dependencia del dashboard — todo debe estar pre-calculado)

    # Si no tenemos ror ni openalex id real para la entidad, no mostramos nada
    if meta:
        ror_val = meta.get('ror')
        id_val = meta.get('id')
        has_ror = ror_val and str(ror_val).strip() != '' and str(ror_val).upper() != 'N/A'
        has_oa = id_val and str(id_val).strip() != '' and str(id_val).upper() != 'N/A'
        if not (has_ror or has_oa):
            meta = None

    if meta:
        ror_url = meta.get('ror')
        oa_url = meta.get('id')
        # Estilizar etiquetas de identificación
        st.markdown(f"""
            <div style='display: flex; gap: 10px; margin-bottom: 5px; flex-wrap: wrap; align-items: center;'>
                <span style='background-color: #f8f9fa; padding: 4px 10px; border-radius: 20px; font-size: 11px; border: 1px solid #dee2e6; color: #495057;'>
                    <b>ROR:</b> <a href='{ror_url}' target='_blank' style='text-decoration: none; color: #007bff;'>{str(ror_url).replace("https://ror.org/", "") if ror_url else "N/A"}</a>
                </span>
                <span style='background-color: #f8f9fa; padding: 4px 10px; border-radius: 20px; font-size: 11px; border: 1px solid #dee2e6; color: #495057;'>
                    <b>OpenAlex:</b> <a href='{oa_url}' target='_blank' style='text-decoration: none; color: #007bff;'>{str(oa_url).replace("https://openalex.org/", "") if oa_url else "N/A"}</a>
                </span>
                <span style='background-color: #e9ecef; padding: 4px 10px; border-radius: 20px; font-size: 11px; border: 1px solid #ced4da; color: #495057;'>
                    <b>Tipo:</b> {str(meta.get('type','')).title()}
                </span>
                <span style='background-color: #e9ecef; padding: 4px 10px; border-radius: 20px; font-size: 11px; border: 1px solid #ced4da; color: #495057;'>
                    <b>País:</b> {meta.get('country_code','')}
                </span>
            </div>
        """, unsafe_allow_html=True)

    st.markdown(f"Panorama Analítico de la Producción de **{entity_name}**.")
    
    if view_mode == "produccion_institucional":
        st.info("ℹ️ **Nota sobre los datos:** Producción institucional según snapshot OpenAlex (Marzo 2026). Puede diferir ligeramente del portal oficial por actualización continua.")



    if df_total is not None and not df_total.empty:
        if df_total.empty:
            st.warning(f"No hay métricas institucionales pre-calculadas para {entity_name}.")
            return
            
        total = df_total.iloc[0]
        
        official_count = total.get('official_snii_count')
        if official_count is None or official_count == 0:
            official_counts = load_official_snii_counts()
            
            # 1. Intentar búsqueda jerárquica (la más precisa)
            if institution_name and entity_name:
                if parent_name and parent_name != entity_name:
                    hier_key = f"{institution_name} || {parent_name} || {entity_name}"
                else:
                    hier_key = f"{institution_name} || {entity_name}"
                official_count = official_counts.get(hier_key)
            
            # 2. Fallback al nombre de la entidad (flat) - útil para niveles superiores
            if official_count is None:
                official_count = official_counts.get(entity_name)
            
            # 3. Fallback al nombre de la institución (total)
            if official_count is None and institution_name:
                official_count = official_counts.get(institution_name)
                
        # ── Identificadores de Académicos ─────────────────────────────────────────
        pct_ac_orcid = total.get('pct_academic_orcid', 0.0)
        pct_ac_any_id = total.get('pct_academic_any_id', 0.0)
        pct_sn_orcid = total.get('pct_snii_orcid', 0.0)
        pct_sn_any_id = total.get('pct_snii_any_id', 0.0)

        datos_ids = f"""
        % Académicos con ORCID: {pct_ac_orcid:.1f}%
        % Académicos con algún ID: {pct_ac_any_id:.1f}%
        % SNII con ORCID: {pct_sn_orcid:.1f}%
        % SNII con algún ID: {pct_sn_any_id:.1f}%
        """
        c_btn, c_title = st.columns([0.3, 10])
        with c_btn: render_explain_button("Identificadores de Académicos", "kpi_ids", datos_ids)
        with c_title: st.markdown("##### Identificadores de Académicos")

        ci1, ci2, ci3, ci4 = st.columns(4)
        ci1.metric("% Académicos con ORCID", f"{pct_ac_orcid:.1f}%", help="Porcentaje de académicos afiliados en la institución que tienen registrado su ORCID en la base de datos.")
        ci2.metric("% Académicos con algún ID", f"{pct_ac_any_id:.1f}%", help="Porcentaje de académicos afiliados en la institución que cuentan con al menos un identificador (ORCID, OpenAlex ID, Scopus ID o CVU).")
        ci3.metric("% SNII con ORCID", f"{pct_sn_orcid:.1f}%", help="Porcentaje de investigadores SNII afiliados en la institución que tienen registrado su ORCID en la base de datos.")
        ci4.metric("% SNII con algún ID", f"{pct_sn_any_id:.1f}%", help="Porcentaje de investigadores SNII afiliados en la institución que cuentan con al menos un identificador (ORCID, OpenAlex ID, Scopus ID o CVU).")

        st.markdown("---")

        # Obtener el censo de Neo4j (Estrategia de Identidad Flexible)
        total_census = int(total.get('neo4j_total_papers', total.get('num_documents', 0)))
        indexed_count = int(total.get('num_documents', 0))
        official_val = f"{official_count:,}" if official_count is not None else "—"
        citas_por_articulo = int(total.get('citations', 0)) / indexed_count if indexed_count > 0 else 0.0

        # Construir datos para el asistente
        datos_generales = f"""
        Producción Total: {total_census}
        Indizada en OpenAlex: {indexed_count}
        No. de SNIIs 2025: {official_val}
        Citas Acumuladas: {int(total.get('citations',0))}
        Citas/artículo: {citas_por_articulo:.2f}
        FWCI Promedio: {total.get('fwci_avg',0):.2f}
        % Open Access: {total.get('pct_open_access',0):.1f}%
        """
        
        c_btn, c_title = st.columns([0.3, 10])
        with c_btn: render_explain_button("Métricas Generales", "kpi_gen", datos_generales)
        with c_title: st.markdown("##### Métricas Generales")
        
        c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
        
        c1.metric("Producción Total", f"{total_census:,}", help="Conteo total de artículos detectados en el Knowledge Graph (WoS, Scopus, BIB, etc).")
        c2.metric("Indizada en OpenAlex", f"{indexed_count:,}", help="Artículos con metadatos completos en OpenAlex usados para el cálculo de indicadores.")
        
        c3.metric("No. de SNIIs 2025", official_val, help="Total oficial de investigadores según el padrón del SNII 2025.")
        c4.metric("Citas Acumuladas", f"{int(total.get('citations',0)):,}", help="Suma total de citas recibidas por los artículos indizados en OpenAlex.")
        
        c5.metric("Citas/artículo", f"{citas_por_articulo:.2f}", help="Promedio de citas por artículo (Citas Acumuladas divididas entre artículos Indizados en OpenAlex).")
        
        c6.metric("FWCI Promedio", f"{total.get('fwci_avg',0):.2f}", help="Field-Weighted Citation Impact promedio: impacto de citación normalizado por disciplina y año (1.0 representa el promedio mundial).")
        c7.metric("% Open Access", f"{total.get('pct_open_access',0):.1f}%", help="Porcentaje de la producción científica indizada disponible en acceso abierto (Gold, Green, Hybrid, Bronze).")

        
        datos_excelencia = f"""
        Percentil Promedio: {total.get('percentile_avg',50):.1f}
        % Top 10%: {total.get('pct_top_10',0):.1f}%
        % Top 1%: {total.get('pct_1',0):.1f}%
        """
        c_btn, c_title = st.columns([0.3, 10])
        with c_btn: render_explain_button("Métricas de Excelencia", "kpi_excelencia", datos_excelencia)
        with c_title: st.markdown("##### Métricas de Excelencia")
        
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Percentil Promedio", f"{total.get('percentile_avg',50):.1f}", help="Percentil de citación promedio (un percentil menor indica que el trabajo está más citado, ej. Top 10% son percentiles <= 10).")
        c6.metric("% Top 10%", f"{total.get('pct_top_10',0):.1f}%", help="Porcentaje de artículos que se ubican en el 10% más citado a nivel mundial en sus respectivas áreas y años.")
        c7.metric("% Top 1%", f"{total.get('pct_1',0):.1f}%", help="Porcentaje de artículos que se ubican en el 1% más citado a nivel mundial en sus respectivas áreas y años.")

        # ── Velocidad y Colaboración ──────────────────────────────────────────────
        datos_velocidad = f"""
        Citas/año (avg): {total.get('velocity_avg',0):.1f}
        Citas últ. 3 años: {int(total.get('recent_cites_3yr',0)):,}
        % Colaboración Internacional: {total.get('pct_international',0):.1f}%
        Países/paper (avg): {total.get('avg_countries',0):.1f}
        Autores/paper (avg): {total.get('avg_author_count',0):.1f}
        """
        c_btn, c_title = st.columns([0.3, 10])
        with c_btn: render_explain_button("Velocidad de Citas y Colaboración", "kpi_velocidad", datos_velocidad)
        with c_title: st.markdown("##### Velocidad de Citas y Colaboración")
        
        cv1, cv2, cv3, cv4, cv5 = st.columns(5)
        cv1.metric("Citas/año (avg)",       f"{total.get('velocity_avg',0):.1f}", help="Velocidad promedio de acumulación de citas por artículo por año desde su fecha de publicación.")
        cv2.metric("Citas últ. 3 años",     f"{int(total.get('recent_cites_3yr',0)):,}", help="Total de citas recibidas en los últimos 36 meses.")
        cv3.metric("% Colaboración Internacional",       f"{total.get('pct_international',0):.1f}%", help="Porcentaje de artículos co-escritos con al menos un autor de una institución extranjera.")
        cv4.metric("Países/paper (avg)",    f"{total.get('avg_countries',0):.1f}", help="Número promedio de países distintos representados en las coautorías por publicación.")
        cv5.metric("Autores/paper (avg)",   f"{total.get('avg_author_count',0):.1f}", help="Número promedio de autores firmantes por artículo.")

        # ── APC ───────────────────────────────────────────────────────────────────
        apc_total = total.get('apc_paid_usd', 0) or 0
        datos_apc = f"""
        APC Total: ${apc_total:,.0f} USD
        % Papers con APC: {total.get('pct_apc',0):.1f}%
        Vida Media Citas: {total.get('half_life_avg',0):.1f} años
        """
        c_btn, c_title = st.columns([0.3, 10])
        with c_btn: render_explain_button("Acceso Abierto y Costos", "kpi_apc", datos_apc)
        with c_title: st.markdown("##### Acceso Abierto y Costos")
        
        ca1, ca2, ca3 = st.columns(3)
        ca1.metric("APC Total",     f"${apc_total:,.0f} USD", help="Monto estimado en USD por cargos de procesamiento de artículos (Article Processing Charges) en revistas de acceso abierto.")
        ca2.metric("% Papers con APC",     f"{total.get('pct_apc',0):.1f}%", help="Porcentaje de la producción publicada en revistas que requieren pago de cuotas (APC).")
        ca3.metric("Vida Media Citas",     f"{total.get('half_life_avg',0):.1f} años", help="Años transcurridos desde la publicación hasta que los artículos acumulan el 50% de su impacto total.")


        # ── Distribución Open Access y Perfil Temático ──────────────────────────────
        col_donut, col_gini = st.columns(2)
        with col_donut:
            c_btn, c_title = st.columns([0.6, 10])
            with c_btn: render_explain_button("Distribución Open Access", "oa_donut_inst", None)
            with c_title: st.markdown("**Distribución Open Access**")
            _render_oa_donut(total, key_suffix=f"inst_{entity_name}")
            
        with col_gini:
            gini_val = total.get('gini_topics')
            n_dom    = int(total.get('domain_diversity', 0) or 0)
            n_top    = int(total.get('unique_topics', 0) or 0)
            top_dom  = total.get('top_domain', '—') or '—'
            
            datos_perfil = f"""
            Índice de Gini temático: {gini_val:.3f} si existe
            Dominios de investigación: {n_dom}
            Tópicos únicos: {n_top}
            Dominio principal: {top_dom}
            """
            c_btn, c_title = st.columns([0.6, 10])
            with c_btn: render_explain_button("Perfil Temático", "perfil_tematico", datos_perfil)
            with c_title: st.markdown("**Perfil Temático**")
            
            st.markdown(f"""
| Indicador | Valor |
|---|---|
| Índice de Gini temático | `{gini_val:.3f}` |
| Dominios de investigación | **{n_dom}** |
| Tópicos únicos | **{n_top}** |
| Dominio principal | {top_dom} |
            """.strip()) if gini_val and not np.isnan(gini_val) else st.info("Sin datos de Gini temático.")

        # ── Tipos de Documentos (En nueva fila a ancho controlado) ─────────────────
        st.markdown("---")
        col_types, col_empty_types = st.columns([1.1, 0.9])
        with col_types:
            c_btn, c_title = st.columns([0.6, 10])
            with c_btn: render_explain_button("Tipos de Documentos", "types_pie_inst", "Distribución de la producción científica por tipo de documento según la clasificación de OpenAlex.")
            with c_title: st.markdown("**Tipos de Documentos**")
            _render_document_types_pie(df_inst_papers, key_suffix=f"inst_{entity_name}")

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
            - **% Académicos con ORCID / algún ID:** Porcentaje de académicos afiliados que cuentan con un ORCID o con al menos un identificador (ORCID, OpenAlex, Scopus o CVU) registrado en la base de datos, respectivamente.
            - **% SNII con ORCID / algún ID:** Porcentaje de investigadores SNII afiliados que cuentan con un ORCID o con al menos un identificador registrado en la base de datos, respectivamente.
            - **Gini temático:** 0 = enfocado en un solo tema, 1 = producción totalmente dispersa.
            """)

    if df_annual is not None and not df_annual.empty:
        df_annual = df_annual.sort_values('year')
        if not df_annual.empty:
            st.markdown("---")
            st.subheader("Evolución de Producción e Impacto")
            
            # Ordenamos los anios
            df_annual = df_annual.sort_values('year')

            # Rango temporal: de max(1950, año_mínimo) al año en curso
            _cur_year = datetime.now().year
            _yr_min = int(df_annual['year'].min()) if not df_annual.empty else 1950
            _x_min = max(1950, _yr_min)

            c_btn, c_title = st.columns([0.3, 10])
            with c_btn: render_explain_button("Producción Histórica Institucional", "inst_docs", df_annual[['year', 'num_documents']])
            with c_title: st.markdown("**Documentos Publicados por Año**")

            fig = px.area(df_annual, x='year', y='num_documents',
                          title="",
                          color_discrete_sequence=['#ff7f0e'],
                          range_x=[_x_min, _cur_year],
                          markers=True)
            fig.update_xaxes(tickformat='d', dtick=5)
            st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode=("points",), key="inst_annual_docs")

            # Gráfico FWCI
            c_btn, c_title = st.columns([0.3, 10])
            with c_btn: render_explain_button("Evolución FWCI Institucional", "inst_fwci", df_annual[['year', 'fwci_avg']])
            with c_title: st.markdown("**Evolución FWCI Promedio Institucional**")

            fig_fwci = px.line(df_annual, x='year', y='fwci_avg', markers=True,
                               title="",
                               range_x=[_x_min, _cur_year])
            fig_fwci.add_hline(y=1.0, line_dash="dash", line_color="red", annotation_text="Base Mundial (1.0)")
            fig_fwci.update_xaxes(tickformat='d', dtick=5)
            st.plotly_chart(fig_fwci, width="stretch", on_select="rerun", selection_mode=("points",), key="inst_annual_fwci")
        
    if df_topics is not None and not df_topics.empty:
        if not df_topics.empty:
            st.markdown("---")
            c_btn, c_title = st.columns([0.3, 10])
            with c_btn: render_explain_button("Sunburst Temático Institucional", "inst_sun", df_topics.head(15) if df_topics is not None else None)
            with c_title: st.subheader("Temáticas de Investigación Institucional (Sunburst)")
            # Filtrar valores vacíos para que el Sunburst no se corte
            clean_topics = df_topics.replace('', pd.NA).dropna(subset=['domain', 'field', 'subfield', 'topic'])
            top_topics = clean_topics.sort_values('value', ascending=False).head(100)
            fig_sun = px.sunburst(
                top_topics,
                path=['domain', 'field', 'subfield', 'topic'],
                values='value',
                color='value',
                color_continuous_scale='Blues',
                title=""
            )
            fig_sun.update_layout(margin=dict(t=50, l=0, r=0, b=10), height=700)
            st.plotly_chart(fig_sun, width="stretch", on_select="rerun", selection_mode=("points",), key="inst_sunburst")

            # --- Evolución Histórica Institucional ---
            df_evol_inst = get_cached_data("thematic_evolution_institucion.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
            if df_evol_inst is not None and not df_evol_inst.empty:
                _render_thematic_evolution(df_evol_inst, 'entity_name', entity_name, key_suffix=f"inst_{entity_name}")

    # ── Vocabulario Científico (WordCloud) ────────────────────────────────────────
    df_kw_inst = get_cached_data("keywords_institucion.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
    if df_kw_inst is not None and not df_kw_inst.empty:
        st.markdown("---")
        st.subheader("🔑 Vocabulario Científico Institucional (keywords)")
        _render_keywords_section(df_kw_inst, "entity_name", entity_name,
                                 title="", key_suffix=f"inst_{entity_name}")

    # ── Colaboración Internacional (Choropleth) ───────────────────────────────────
    df_inst_papers = get_cached_data("papers_institucion.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
    if df_inst_papers is not None and not df_inst_papers.empty:
        df_ip = df_inst_papers
        if not df_ip.empty and "countries" in df_ip.columns:
            st.markdown("---")
            st.subheader("🌍 % Colaboración Internacional")
            df_annual_inst = get_cached_data("institucion_annual.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
            if df_annual_inst is not None and not df_annual_inst.empty:
                df_ia = df_annual_inst.sort_values('year')
                if 'pct_international' in df_ia.columns and not df_ia.empty:
                    fig_intl = go.Figure()
                    fig_intl.add_trace(go.Scatter(
                        x=df_ia['year'], y=df_ia['pct_international'],
                        mode='lines+markers', name='% Internacional',
                        line=dict(color='#003D64', width=2.5),
                        marker=dict(size=6, color='#E39918'),
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
    df_annual_oa = get_cached_data("institucion_annual.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
    if df_annual_oa is not None and not df_annual_oa.empty:
        df_oa_ann = df_annual_oa.sort_values('year')
        oa_cols = [c for c in ['pct_oa_gold','pct_oa_green','pct_oa_hybrid','pct_oa_bronze','pct_oa_closed']
                   if c in df_oa_ann.columns]
        if oa_cols and not df_oa_ann.empty:
            st.markdown("---")
            st.subheader("📊 Evolución del Acceso Abierto por Año")
            df_oa_melt = df_oa_ann[['year'] + oa_cols].melt(id_vars='year', var_name='tipo_oa', value_name='pct')
            df_oa_melt['tipo_oa'] = df_oa_melt['tipo_oa'].str.replace('pct_oa_','').str.capitalize()
            color_map = {'Gold':'#FFD700','Green':'#2ECC71','Hybrid':'#3498DB','Bronze':'#CD7F32','Closed':'#95A5A6'}
            # Rango temporal OA
            _cur_year_oa = datetime.now().year
            _yr_min_oa = int(df_oa_ann['year'].min()) if not df_oa_ann.empty else 1950
            _x_min_oa = max(1950, _yr_min_oa)
            fig_stack = px.bar(df_oa_melt, x='year', y='pct', color='tipo_oa',
                               color_discrete_map=color_map,
                               labels={'pct':'%','tipo_oa':'Tipo OA'},
                               barmode='stack',
                               title="Distribución OA por año (%)",
                               range_x=[_x_min_oa - 0.5, _cur_year_oa + 0.5],
                               text_auto=False)
            fig_stack.update_layout(height=320, margin=dict(t=30,b=10), template='plotly_white')
            fig_stack.update_xaxes(tickformat='d', dtick=5)
            st.plotly_chart(fig_stack, use_container_width=True, key=f"oa_stack_{entity_name}")

    # ── Perfil de Visibilidad e Indexación (Radar) ────────────────────────────────
    if False: # df_total is not None:
        total_row = df_total.iloc[0] if not df_total.empty else None
        if total_row is not None:
            vis_cols = ['pct_pubmed','pct_doaj_indexed','pct_core_journal',
                        'pct_repository','pct_english','pct_cc_by']
            has_vis = any(
                (v := total_row.get(c)) is not None and not (isinstance(v, float) and np.isnan(v)) and v != 0
                for c in vis_cols
            )
            if has_vis:
                st.markdown("---")
                st.subheader("🔭 Perfil de Visibilidad e Indexación")

                def _fmt_pct(val, decimals=1):
                    """Formatea un porcentaje o devuelve N/A si es NaN/None."""
                    if val is None: return "N/A"
                    try:
                        f = float(val)
                        if np.isnan(f): return "N/A"
                        return f"{f:.{decimals}f}%"
                    except (TypeError, ValueError):
                        return "N/A"

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
| % en PubMed | `{_fmt_pct(total_row.get('pct_pubmed'))}` |
| % en DOAJ | `{_fmt_pct(total_row.get('pct_doaj_indexed'))}` |
| % en revista Core | `{_fmt_pct(total_row.get('pct_core_journal'))}` |
| % en repositorio | `{_fmt_pct(total_row.get('pct_repository'))}` |
| % en inglés | `{_fmt_pct(total_row.get('pct_english'))}` |
| % con licencia CC-BY | `{_fmt_pct(total_row.get('pct_cc_by'))}` |
| Papers retractados | `{_fmt_pct(total_row.get('pct_retracted'), decimals=2)}` |
                    """.strip())

    df_institucion_papers = load_cached_data("papers_institucion.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
    if df_institucion_papers is not None and not df_institucion_papers.empty:
        df_inst_p = df_institucion_papers
        
        st.markdown("---")
        st.header("🌍 Impacto Global Institucional en Sostenibilidad (ODS)")
        st.write("Distribución consolidada de toda la producción científica de la institución respecto a los Objetivos de Desarrollo Sostenible. En Openalex algunos trabajos han sido etiquetados con uno o más ODSs")
        html_code_inst = viz_ods.render_sdg_matrix(df_inst_p, col_ods='ODS_ID')
        st.markdown(html_code_inst, unsafe_allow_html=True)
        
        # --- Mapa Semántico (Artículos) ---
        import urllib.parse
        import json
        st.markdown("---")
        st.subheader("🗺️ Mapa Semántico de Producción")
        st.write(f"Exploración espacial de la producción científica. Los **{indexed_count:,} artículos** de la entidad están coloreados; el resto de la base nacional aparece en gris.")
        
        # Extraer DOIs y OpenAlex IDs de df_inst_p
        list_of_dois = []
        list_of_oa = []
        if 'doi' in df_inst_p.columns:
            list_of_dois = df_inst_p['doi'].dropna().astype(str).tolist()
        elif 'DOI' in df_inst_p.columns:
            list_of_dois = df_inst_p['DOI'].dropna().astype(str).tolist()
            
        if 'paper_id' in df_inst_p.columns:
            list_of_oa = df_inst_p['paper_id'].dropna().astype(str).tolist()
            
        list_of_dois = [d.replace('https://doi.org/', '').strip() for d in list_of_dois]
        # Mantenemos el prefijo completo de OpenAlex para que coincida con el JSON del mapa
        # (articles_data.json contiene 'https://openalex.org/W...')
        list_of_oa = [d.strip() for d in list_of_oa]
        dois_json = json.dumps(list_of_dois)
        oa_json = json.dumps(list_of_oa)
        
        # Parámetro URL para destacar a la institución (highlight_inst) - Fallback
        encoded_inst = urllib.parse.quote(entity_name)
        iframe_src = f"https://dinamica1.fciencias.unam.mx/tiles/map_test.html?v=28&data=https://dinamica1.fciencias.unam.mx/tiles/articles_specter_data.json?v=28&color_by=cluster&highlight_inst={encoded_inst}"
        safe_name_inst = "".join([c if c.isalnum() else "_" for c in entity_name])
        
        map_html = f"""
        <script>
            window._highlightDois_{safe_name_inst} = {dois_json};
            window._highlightOa_{safe_name_inst} = {oa_json};
            function sendDois_{safe_name_inst}(iframe) {{
                iframe.contentWindow.postMessage({{
                    type: 'HIGHLIGHT_DOIS',
                    dois: window._highlightDois_{safe_name_inst},
                    oa_ids: window._highlightOa_{safe_name_inst}
                }}, '*');
            }}
        </script>
        <div id="map-container-inst-{safe_name_inst}" style="width:100%; overflow:hidden;">
            <iframe id="map-iframe-inst-{safe_name_inst}" src="{iframe_src}" 
                    style="width:100%; border:none; display:block;" 
                    scrolling="no"
                    onload="sendDois_{safe_name_inst}(this)">
            </iframe>
        </div>
        <script>
            function resizeInstMap() {{
                var iframe = document.getElementById('map-iframe-inst-{safe_name_inst}');
                var container = document.getElementById('map-container-inst-{safe_name_inst}');
                if(!iframe || !container) return;
                var rect = container.getBoundingClientRect();
                var availableHeight = window.innerHeight - rect.top - 10;
                if (availableHeight < 500) availableHeight = 500;
                iframe.style.height = availableHeight + 'px';
            }}
            resizeInstMap();
            window.addEventListener('resize', resizeInstMap);
            setTimeout(resizeInstMap, 300);
            setTimeout(resizeInstMap, 1000);
        </script>
        """
        
        if st.toggle("Cargar mapa interactivo (WebGL)", key=f"toggle_map_inst_{safe_name_inst}"):
            with st.spinner("Cargando el mapa semántico..."):
                components.html(map_html, height=720, scrolling=False)

        st.markdown("---")
        st.subheader("📜 Publicaciones")
        
        # Seguridad: asegurar que existan las columnas para evitar KeyErrors
        for c in ['ODS_Nombre', 'openalex_url']:
            if c not in df_inst_p.columns:
                df_inst_p[c] = None

        col_filtro1, col_filtro2 = st.columns(2)
        with col_filtro1:
            years_inst = np.flip(np.unique(df_inst_p['year'].dropna()))
            s_year_inst = st.selectbox("Filtrar por año:", options=["Todos"] + list(years_inst), key="inst_year")
        with col_filtro2:
            ods_options_inst = sorted([str(ods) for ods in df_inst_p['ODS_Nombre'].dropna().unique() if ods and str(ods).lower() != "null" and "x" not in str(ods).lower()])
            s_ods_inst = st.selectbox("Filtrar por ODS:", options=["Todos"] + ods_options_inst, key="inst_ods")
        
        df_display_inst = df_inst_p.copy()
        if s_year_inst != "Todos":
            df_display_inst = df_display_inst[df_display_inst['year'] == s_year_inst]
        if s_ods_inst != "Todos":
            df_display_inst = df_display_inst[df_display_inst['ODS_Nombre'] == s_ods_inst]
            
        df_display_inst = _prepare_papers_table(df_display_inst)
        
        cols_to_show = ["year", "Title", "Source", "citations", "DOI", "openalex_url", "ODS_Nombre", "topic", "_formatted_authors"]
        df_display_inst = df_display_inst[[c for c in cols_to_show if c in df_display_inst.columns]].rename(columns={
            "year": "Año",
            "Title": "Título",
            "Source": "Revista",
            "citations": "Citas",
            "DOI": "Enlace DOI",
            "openalex_url": "OpenAlex",
            "ODS_Nombre": "ODS",
            "topic": "Tópico",
            "_formatted_authors": "Autores"
        }).sort_values(by="Año", ascending=False)
        
        st.dataframe(df_display_inst, width="stretch", hide_index=True, column_config={
            "Enlace DOI": st.column_config.LinkColumn("Enlace DOI", display_text="Ver paper"),
            "OpenAlex": st.column_config.LinkColumn("OpenAlex", display_text="Ver en OpenAlex")
        })

        # ── Reporte Bibliométrico IA ──────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("📄 Reporte Bibliométrico con Inteligencia Artificial")
        st.markdown("Genera o descarga un reporte analítico consolidado, interpretado por LLM, incluyendo las gráficas interactivas mostradas arriba.")
        import re
        safe_name = "".join([c if c.isalnum() else "_" for c in entity_name])
        suffix = f"_{view_mode}"
        report_path = os.path.join(BASE_PATH, 'reports', f"report_inst{suffix}_{safe_name}.html")
        
        if os.path.exists(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                html_data = f.read()
            
            show_report_inst_key = f"show_report_inst{suffix}_{safe_name}"
            show_state = st.session_state.get(show_report_inst_key, False)
            btn_text = "👁️ Ocultar Reporte" if show_state else "👁️ Ver Reporte en Pantalla"
            
            c_rep1, c_rep2, c_rep3 = st.columns([1.2, 1.2, 1])
            with c_rep1:
                if st.button(btn_text, key=f"btn_view_inst_{view_mode}_{safe_name}"):
                    st.session_state[show_report_inst_key] = not show_state
                    st.rerun()
            with c_rep2:
                view_label = "Capacidad_Instalada" if view_mode == "capacidad_instalada" else "Produccion_Institucional"
                st.download_button("⬇️ Descargar Reporte (HTML)", data=html_data, file_name=f"Reporte_Institucion_{view_label}_{safe_name}.html", mime="text/html")
            with c_rep3:
                admins_str = os.environ.get("admins", os.environ.get("ADMINS", ""))
                admin_orcids = [x.strip() for x in admins_str.split(",") if x.strip()]
                auth_user = st.session_state.get("authenticated_user")
                user_orcid = auth_user.get("orcid") if auth_user else None
                is_admin = user_orcid in admin_orcids

                if is_admin:
                    if st.button("🔄 Regenerar", key=f"btn_regen_inst_{view_mode}_{safe_name}"):
                        with st.spinner("Regenerando análisis y reporte con el modelo LLM local... Esto tomará algunos segundos."):
                            import subprocess
                            try:
                                subprocess.run([
                                    sys.executable, 
                                    os.path.join(BASE_PATH, "report_generator.py"), 
                                    "--type", "inst", 
                                    "--name", entity_name, 
                                    "--institution", institution_name, 
                                    "--view_mode", view_mode
                                ], check=True, capture_output=True, text=True)
                                st.rerun()
                            except subprocess.CalledProcessError as e:
                                st.error(f"Fallo al generar reporte:\n{e.stderr or e.stdout}")
                                st.stop()
                    
            if st.session_state.get(show_report_inst_key, False):
                st.markdown("---")
                components.html(html_data, height=900, scrolling=True)
        else:
            admins_str = os.environ.get("admins", os.environ.get("ADMINS", ""))
            admin_orcids = [x.strip() for x in admins_str.split(",") if x.strip()]
            auth_user = st.session_state.get("authenticated_user")
            user_orcid = auth_user.get("orcid") if auth_user else None
            is_admin = user_orcid in admin_orcids

            if is_admin:
                if st.button("✨ Generar Reporte con IA", key=f"btn_gen_inst_{view_mode}_{safe_name}"):
                    with st.spinner("Generando análisis y reporte con el modelo LLM local... Esto tomará algunos segundos."):
                        import subprocess
                        try:
                            subprocess.run([
                                sys.executable, 
                                os.path.join(BASE_PATH, "report_generator.py"), 
                                "--type", "inst", 
                                "--name", entity_name, 
                                "--institution", institution_name, 
                                "--view_mode", view_mode
                            ], check=True, capture_output=True, text=True)
                            st.rerun()
                        except subprocess.CalledProcessError as e:
                            st.error(f"Fallo al generar reporte:\n{e.stderr or e.stdout}")
                            st.stop()

    # Al final de la función, si no hay dataframes cargados, mostrar un mensaje de "En Proceso"
    if (df_total is None or df_total.empty) and (df_annual is None or df_annual.empty):
        st.warning(f"🕒 Los datos para **{entity_name}** están siendo procesados o no tienen registros en el snapshot actual. Por favor, vuelve a consultar más tarde.")

def render_investigador_view(entity_name, institution_name=None):
    # Inyectar CSS global para estilizar st.metric como las tarjetas doradas del reporte
    st.markdown("""
        <style>
        [data-testid="stMetric"] {
            background-color: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
            text-align: center;
            border-top: 4px solid #E39918;
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
            color: #003D64;
        }
        [data-testid="stMetricDelta"] {
            justify-content: center;
        }
        </style>
    """, unsafe_allow_html=True)
    st.header(f"👤 Vista por Investigador ({entity_name})")

def render_investigador_view(entity_name, institution_name=None, view_mode="capacidad_instalada"):
    # Reutilizar el CSS de métricas
    st.markdown("""
        <style>
        [data-testid="stMetric"] {
            background-color: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
            text-align: center;
            border-top: 4px solid #E39918;
            border-bottom: 1px solid #eaeaea;
            border-left: 1px solid #eaeaea;
            border-right: 1px solid #eaeaea;
        }
        </style>
    """, unsafe_allow_html=True)

    # Interceptar búsqueda global activa de investigadores
    search_inv = st.session_state.get("selected_academic_search")
    is_search_active = False

    if search_inv:
        real_inst = st.session_state.get("selected_academic_real_inst")
        real_dep = st.session_state.get("selected_academic_real_dep")
        real_sub = st.session_state.get("selected_academic_real_sub")

        if real_inst:
            is_search_active = True
            st.success(f"🎯 **Perfil Seleccionado:** {search_inv}")
            st.caption(f"Afiliación: **{real_inst}**" + 
                       (f" ➔ **{real_dep}**" if real_dep and real_dep != "SIN INFORMACIÓN" else "") + 
                       (f" ➔ **{real_sub}**" if real_sub and real_sub != "SIN INFORMACIÓN" else ""))
            
            if st.button("❌ Limpiar búsqueda y volver a la navegación normal"):
                del st.session_state["selected_academic_search"]
                if "selected_academic_real_inst" in st.session_state: del st.session_state["selected_academic_real_inst"]
                if "selected_academic_real_dep" in st.session_state: del st.session_state["selected_academic_real_dep"]
                if "selected_academic_real_sub" in st.session_state: del st.session_state["selected_academic_real_sub"]
                st.rerun()

            # Sobreescribir variables para la carga física de parquets
            institution_name = real_inst
            _INVALID_ENTITIES = {'SIN INFORMACIÓN', 'SIN INFORMACION', 'NO APLICA', 'NO APLICA.', ''}
            _ent_sub = real_sub if real_sub and real_sub.strip() not in _INVALID_ENTITIES else None
            _ent_dep = real_dep if real_dep and real_dep.strip() not in _INVALID_ENTITIES else None
            _candidate = _ent_sub or _ent_dep  # primera opción no nula/inválida

            # Validar que el candidato pertenezca a la jerarquía de la institución
            # (evita usar entidades de afiliaciones cruzadas con otras instituciones)
            if _candidate and real_inst:
                try:
                    _hierarchy = get_institution_hierarchy()
                    _inst_deps = _hierarchy.get(real_inst, {})
                    _valid_entities = set(_inst_deps.keys())
                    for _dep_subs in _inst_deps.values():
                        if isinstance(_dep_subs, list):
                            _valid_entities.update(_dep_subs)
                    if _candidate not in _valid_entities:
                        _candidate = None  # entidad de otra institución; usar la raíz
                except Exception:
                    pass  # si falla la jerarquía, conservar candidato

            entity_name = _candidate or real_inst
            investigadores = [search_inv]

    st.header(f"👤 Vista por Investigador: {entity_name if not is_search_active else search_inv}")

    # Validar la salida de la institución solo si no es búsqueda activa
    if not is_search_active and entity_name == institution_name:
        st.info(f"La vista por investigador individual no está disponible a nivel de toda la institución ({entity_name}). Por favor, seleccione una dependencia o subdependencia específica en la jerarquía de navegación de la barra lateral.")
        return

    # Si es búsqueda activa, omitimos la generación de la lista desde el sidebar
    if is_search_active:
        df_inst_tot = None
    else:
        df_inst_tot = get_cached_data("institucion_total.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)

    if not is_search_active:
        if df_inst_tot is None or df_inst_tot.empty:
            investigadores = []
        else:
            try:
                academics_json = df_inst_tot.iloc[0].get('academics_list', "[]")
                investigadores = sorted(json.loads(academics_json))
            except Exception:
                investigadores = []
            
    # Fallback físico si la lista está vacía (ideal para los SNIIs en "Sin Entidad")
    if not investigadores:
        safe_inst = str(institution_name).replace('/', '_').replace('\\', '_') if institution_name else ""
        safe_ent = str(entity_name).replace('/', '_').replace('\\', '_')
        
        test_paths = []
        if safe_inst:
            test_paths.append(os.path.join(CACHE_DIR, safe_inst, safe_ent))
        test_paths.append(os.path.join(CACHE_DIR, safe_ent))
        
        for path in test_paths:
            if os.path.exists(path):
                f_inv = [d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)) and d not in ['capacidad_instalada', 'produccion_institucional']]
                investigadores.extend(f_inv)
                break
        investigadores = sorted(list(set(investigadores)))

    # ── Fuente 3: Neo4j — todos los Person afiliados a la entidad (incluye no-SNII) ──
    # Determinar qué nivel jerárquico es entity_name para la consulta
    try:
        from database.knowledge_graph import Neo4jGraphStore as _Neo4jStore
        _neo = _Neo4jStore()

        # Intentar detectar si la entidad es Subdependency, Dependency o Institution
        _detect_q = """
        OPTIONAL MATCH (s:Subdependency {name: $ent})
        OPTIONAL MATCH (d:Dependency    {name: $ent})
        OPTIONAL MATCH (i:Institution   {name: $ent})
        RETURN
            s.name AS sub_name,
            s.id   AS sub_id,
            d.name AS dep_name,
            i.name AS inst_name
        LIMIT 1
        """
        with _neo.driver.session() as _sess:
            _row = _sess.run(_detect_q, ent=entity_name).single()

        _inst_param = institution_name or entity_name
        _dep_param  = None
        _sub_param  = None

        if _row:
            if _row.get("sub_name"):
                # Es subdependencia; extraer dep del id compuesto INST||DEP||SUB
                _parts = (_row.get("sub_id") or "").split("||")
                _dep_param = _parts[1] if len(_parts) >= 2 else None
                _sub_param = _row["sub_name"]
            elif _row.get("dep_name"):
                _dep_param = _row["dep_name"]
            elif _row.get("inst_name"):
                _inst_param = _row["inst_name"]

        _census = _neo.get_hierarchical_academic_census(
            inst_name=_inst_param,
            dep_name=_dep_param,
            sub_name=_sub_param
        )
        _neo.close()

        neo_names = [r["name"] for r in _census if r.get("name")]
        if neo_names:
            # Deduplicación inteligente: normalizamos comas y espacios, 
            # pero damos prioridad al string original del Parquet para no romper las rutas de caché.
            dedup_map = {}
            for inv in investigadores:
                norm = inv.replace(",", "").replace("  ", " ").strip().lower()
                dedup_map[norm] = inv
                
            for name in neo_names:
                norm = name.replace(",", "").replace("  ", " ").strip().lower()
                if norm not in dedup_map:
                    dedup_map[norm] = name
                    
            investigadores = sorted(list(dedup_map.values()))
    except Exception as _e:
        print(f"[render_investigador_view] Neo4j fallback error: {_e}")

    if not investigadores:
        st.info(f"La vista individual de investigadores no está disponible para {entity_name}.")
        return

    # Selector
    st.markdown("Los indicadores se calcularon a partir de la producción académica que se pudo recoger de Scopus y ORCID, lo cual implica que puede haber trabajos faltantes y trabajos con afiliaciones distintas a la actual.")
    default_idx = 0
    if "selected_academic_search" in st.session_state and st.session_state.selected_academic_search in investigadores:
        default_idx = investigadores.index(st.session_state.selected_academic_search)
        
    selected_inv = st.selectbox("Seleccione un Académico:", investigadores, index=default_idx)
    
    df_inv_tot = get_cached_data("investigador_total.parquet", entity_name=entity_name, academic_name=selected_inv, institution_name=institution_name, view_mode=view_mode)
    df_inv_ann = get_cached_data("investigador_annual.parquet", entity_name=entity_name, academic_name=selected_inv, institution_name=institution_name, view_mode=view_mode)
    df_topics  = get_cached_data("topics_investigador.parquet", entity_name=entity_name, academic_name=selected_inv, institution_name=institution_name, view_mode=view_mode)
    df_umap = None
    umap_source = None
    if entity_name:
        df_umap = get_cached_data("umap_investigadores.parquet", entity_name=entity_name, institution_name=institution_name, view_mode=view_mode)
        if df_umap is not None and not df_umap.empty:
            umap_source = f"la entidad ({entity_name})"
            
    df_umap_inst = get_cached_data("umap_investigadores.parquet", institution_name=institution_name, view_mode=view_mode)
    if df_umap_inst is None or df_umap_inst.empty:
        global_path = os.path.join(CACHE_DIR, "umap_investigadores.parquet")
        if os.path.exists(global_path):
            try:
                df_umap_inst = pd.read_parquet(global_path)
            except Exception:
                df_umap_inst = None
    
    # Cargar papers globales del investigador y preinicializar df_prof
    df_profesores_papers = load_cached_data("papers_profesor.parquet", entity_name=entity_name, academic_name=selected_inv, institution_name=institution_name, view_mode=view_mode)
    if df_profesores_papers is not None and not df_profesores_papers.empty:
        df_prof = df_profesores_papers
    else:
        df_prof = pd.DataFrame()

    # 4. Enlaces de Perfil Externo
    if df_inv_tot is None or df_inv_tot.empty:
        st.warning(
            f"⚠️ **{selected_inv}** está registrado en el padrón institucional pero aún no tiene "
            f"métricas bibliométricas computadas. Para generar su análisis, ejecuta el pipeline de "
            f"ingesta y cómputo para este investigador."
        )
        # Mostrar datos básicos desde Neo4j aunque no haya parquets
        try:
            from database.knowledge_graph import Neo4jGraphStore as _NgNeo
            _ng = _NgNeo()
            with _ng.driver.session() as _sess:
                _r = _sess.run(
                    "MATCH (a:Person) WHERE a.fullname = $n OR a.id = $n "
                    "RETURN a.orcid AS orcid, a.cvu AS cvu, a.is_snii AS is_snii, "
                    "a.siia AS siia LIMIT 1",
                    n=selected_inv
                ).single()
            _ng.close()
            if _r:
                _cols = st.columns(4)
                _cols[0].metric("ORCID", _r.get("orcid") or "—")
                _cols[1].metric("CVU", _r.get("cvu") or "—")
                _cols[2].metric("SNII", "✅ Sí" if _r.get("is_snii") else "No")
                _cols[3].metric("SIIA", _r.get("siia") or "—")
        except Exception:
            pass
        return
        
    inv_data = df_inv_tot.iloc[0]
    academicos_dict = cargar_lista_academicos()
    academico_info = academicos_dict.get(selected_inv, {})
    neo_orcid, neo_scopus, neo_openalex, neo_siia, neo_cvu, neo_is_snii, neo_snii_level = None, None, None, None, None, None, None
    try:
        from database.knowledge_graph import Neo4jGraphStore
        neo = Neo4jGraphStore()
        with neo.driver.session() as session:
            record = session.run("MATCH (a:Person) WHERE a.id = $name OR a.fullname = $name RETURN coalesce(a.orcids, []) as orcids, coalesce(a.scopus_ids, []) as scopus_ids, coalesce(a.openalex_ids, []) as openalex_ids, a.siia as siia, a.cvu as cvu, a.is_snii as is_snii, coalesce(a.snii_max_level, a.snii_level) as snii_level LIMIT 1", name=selected_inv).single()
            if record:
                o_ids = record.get("orcids")
                neo_orcid = ", ".join(o_ids) if o_ids else None
                
                sc_ids = record.get("scopus_ids")
                neo_scopus = ", ".join(sc_ids) if sc_ids else None
                
                oa_ids = record.get("openalex_ids")
                neo_openalex = ", ".join(oa_ids) if oa_ids else None
                
                neo_siia = record.get("siia")
                neo_cvu = record.get("cvu")
                neo_is_snii = record.get("is_snii")
                neo_snii_level = record.get("snii_level")
        neo.close()
    except Exception:
        pass
    
    # Priorizar IDs del Grafo de Conocimiento (Neo4j), luego del Parquet, y por último el JSON (obsoleto)
    inv_orcid = neo_orcid or inv_data.get('orcid') or academico_info.get("orcid")
    inv_scopus = neo_scopus or inv_data.get('scopus_id') or academico_info.get("scopus")
    inv_siia = neo_siia or inv_data.get('siia_url') or academico_info.get("siia")
    inv_cvu = neo_cvu or inv_data.get('cvu')
    is_snii_val = bool(neo_is_snii) if neo_is_snii is not None else (bool(inv_data.get('is_snii', False)) or bool(academico_info.get("is_snii", False)))
    inv_snii_level = neo_snii_level or inv_data.get('snii_level') or academico_info.get("snii_level") or academico_info.get("nivel")
    
    # Cargar info de SNII Verificado (IA)
    snii_matches = load_snii_matches()
    snii_info = snii_matches.get(selected_inv, {})
    inv_oa = neo_openalex or inv_data.get('openalex_id') or snii_info.get('matched_openalex_id')
    inv_reason = inv_data.get('match_reason') or snii_info.get('reason')

    st.markdown("---")
    
    # --- Enlaces y Acciones Principales ---
    # --- Enlaces de Perfiles Externos ---
    if inv_siia or inv_orcid or inv_scopus or inv_cvu:
        if inv_cvu:
            st.markdown(f"- **CVU SECIHTI:** `{inv_cvu}`")
            
        if inv_siia and "http" in str(inv_siia) and "No encont" not in str(inv_siia):
            st.markdown(f"- **SIIA-UNAM:** [Ver Perfil de {selected_inv}]({inv_siia})")
            if "unam.mx" in str(inv_siia):
                st.caption("ℹ️ Se extrajeron ORCID y Scopus IDs de la página web del SIIA.")
        
        if inv_orcid:
            orcids = [o.strip() for o in str(inv_orcid).split(',')]
            orcid_links = []
            for o in orcids:
                o_url = o if "http" in o else f"https://orcid.org/{o}"
                o_txt = o.split('/')[-1] if "http" in o else o
                orcid_links.append(f"[{o_txt}]({o_url})")
            st.markdown(f"- **ORCID:** {', '.join(orcid_links)}")
        
        if inv_scopus:
            import re
            all_ids = re.findall(r'\d+', str(inv_scopus))
            if all_ids:
                scopus_links = []
                for sid in all_ids:
                    scopus_url = f"https://www.scopus.com/authid/detail.uri?authorId={sid}"
                    scopus_links.append(f"[{sid}]({scopus_url})")
                st.markdown(f"- **Scopus:** {', '.join(scopus_links)}")
            elif "http" in str(inv_scopus):
                st.markdown(f"- **Scopus:** [Ver Perfil]({inv_scopus})")
        
        if inv_oa:
            oa_parts = [o.strip() for o in str(inv_oa).split(',')]
            oa_links = []
            for o_part in oa_parts:
                o_url = o_part if "http" in o_part else f"https://openalex.org/{o_part}"
                o_text = o_part.split('/')[-1] if "http" in o_part else o_part
                oa_links.append(f"[{o_text}]({o_url})")
            
            st.markdown(f"- **OpenAlex ID:** {', '.join(oa_links)}")
            
        # Pertenencia al SNII
        if is_snii_val:
            st.markdown("- **Miembro del SNII (SECIHTI):** Sí ✅")
            if inv_snii_level and str(inv_snii_level).strip() and str(inv_snii_level).strip() != "SIN NIVEL" and str(inv_snii_level).strip() != "None":
                st.markdown(f"- **Nivel SNII:** {inv_snii_level}")
        else:
            st.markdown("- **Miembro del SNII (SECIHTI):** No ❌")

    # --- Detalles Técnicos y Auditoría (LLM) ---
    with st.expander("🔍 Ver detalles de los perfiles académicos", expanded=False):
        # Mostrar Auditoría y Razonamiento IA
        audit_verdict = inv_data.get('audit_verdict')
        match_reason = inv_reason
        
        raw_is_snii = inv_data.get('is_snii', False)
        is_snii_flag = False if pd.isna(raw_is_snii) else bool(raw_is_snii)
        is_snii = is_snii_flag or bool(snii_info)
        
        if is_snii and match_reason:
            st.info(f"🤖 **Buscado usando IA**\n\n**Argumento de la IA:** {match_reason}")
            
            discarded = inv_data.get('discarded_candidates')
            if discarded and isinstance(discarded, str):
                import json
                try:
                    discarded_list = json.loads(discarded)
                    if discarded_list:
                        with st.expander("Ver otros perfiles analizados (Descartados)"):
                            for dc in discarded_list:
                                if isinstance(dc, dict):
                                    name = dc.get("name", "Desconocido")
                                    o_id = dc.get("orcid", "N/A")
                                    reason = dc.get("reason", "Sin razón provista")
                                    st.markdown(f"- **{name}** ({o_id}): {reason}")
                except Exception:
                    pass
            
        if audit_verdict:
            conf = int(inv_data.get('audit_confidence', 0))
            reason = inv_data.get('audit_reason', 'Sin detalle.')
            ts = inv_data.get('audit_timestamp', '')
            
            if audit_verdict == "CONFIRMED":
                st.success(f"✅ **Auditoría: ORCID Confirmado** ({conf}% confianza)\n\n{reason}")
            elif audit_verdict == "DOUBTFUL":
                st.warning(f"⚠️ **Auditoría: ORCID Dudoso** ({conf}% confianza)\n\n{reason}")
            elif audit_verdict == "FALSE_POSITIVE":
                st.error(f"❌ **Auditoría: Falso Positivo** ({conf}% confianza)\n\n{reason}")
            
            if ts: st.caption(f"Auditado el: {ts}")
            st.markdown("---")

            
    

    # ── WordCloud de Keywords ─────────────────────────────────────────────────────
    df_kw_inv = get_cached_data("keywords_investigador.parquet", entity_name=entity_name, academic_name=selected_inv, institution_name=institution_name, view_mode=view_mode)
    if df_kw_inv is not None and not df_kw_inv.empty:
        st.markdown("---")
        st.subheader("🔑 Vocabulario Científico (keywords)")
        _render_keywords_section(df_kw_inv, "academic_name", selected_inv,
                                 title="", key_suffix=f"inv_{selected_inv}")



    # 3.5 Sunburst Temático
    if df_topics is not None:
        conc_data = df_topics[df_topics['academic_name'] == selected_inv]
        if not conc_data.empty:
            st.markdown("---")
            c_btn, c_title = st.columns([0.3, 10])
            with c_btn: render_explain_button(f"Sunburst Temático de {selected_inv}", "inv_sun", df_topics[df_topics['academic_name'] == selected_inv].head(15) if df_topics is not None else None)
            with c_title: st.subheader("Concentración Temática (Sunburst)")
            # Filtrar valores vacíos para que el Sunburst no se corte
            clean_topics_inv = conc_data.replace('', pd.NA).dropna(subset=['domain', 'field', 'subfield', 'topic'])
            top_topics_inv = clean_topics_inv.sort_values('value', ascending=False).head(100)
            
            fig_sun_inv = px.sunburst(
                top_topics_inv, 
                path=['domain', 'field', 'subfield', 'topic'], 
                values='value',
                color='value', 
                color_continuous_scale='Blues',
            )
            fig_sun_inv.update_layout(margin=dict(t=10, l=0, r=0, b=10), height=600)
            st.plotly_chart(fig_sun_inv, width="stretch", on_select="rerun", selection_mode=("points",), key="inv_sunburst")

            # --- Evolución Histórica Investigador ---
            df_evol_inv = get_cached_data("thematic_evolution_investigador.parquet", entity_name=entity_name, academic_name=selected_inv, institution_name=institution_name, view_mode=view_mode)
            _render_thematic_evolution(df_evol_inv, 'academic_name', selected_inv, key_suffix=f"inv_{selected_inv}")



        st.markdown("---")
        st.header("🌍 Panorama General de Sostenibilidad (ODS)")
        st.write("Distribución de la producción científica en base a Objetivos de Desarrollo Sostenible (OpenAlex etiqueta algunos artículos con los ODSs)")
        html_code = viz_ods.render_sdg_matrix(df_prof, col_ods='ODS_ID')
        st.markdown(html_code, unsafe_allow_html=True)
        


        st.markdown("---")
        mostrar_banners_destacados(df_prof)
        


    # 1. KPIs del Investigador
    st.markdown("---")
    
    total_census = int(inv_data.get('neo4j_total_papers', inv_data.get('num_documents', 0)))
    indexed_count = int(inv_data.get('num_documents', 0))
    citas_por_articulo = int(inv_data.get('citations', 0)) / indexed_count if indexed_count > 0 else 0.0

    datos_gen_inv = f"""
    Investigador: {selected_inv}
    Producción Total (Censo): {total_census}
    IDENTIFICA EN OPENALEX (Analítica): {indexed_count}
    Índice H: {int(inv_data.get('h_index',0))}
    Total Citas: {int(inv_data.get('citations',0))}
    % Open Access: {inv_data.get('pct_open_access',0):.1f}%
    """
    c_btn, c_title = st.columns([0.3, 10])
    with c_btn: render_explain_button(f"Métricas Generales de {selected_inv}", "kpi_gen_inv", datos_gen_inv)
    with c_title: st.markdown("##### Métricas Generales")

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("Producción Total (Censo)", f"{total_census:,}", help="Conteo total de artículos en Neo4j (incluye WoS/BIB no indizados).")
    c2.metric("Indizada (Analítica)", f"{indexed_count:,}", help="Artículos en OpenAlex usados para el cálculo de métricas.")
    c3.metric("Índice H", f"{int(inv_data.get('h_index',0))}", help="Índice H: el investigador tiene H artículos que han recibido al menos H citas cada uno.")
    c4.metric("Total Citas", f"{int(inv_data.get('citations',0)):,}", help="Suma total de citas recibidas por las publicaciones del investigador indizadas en OpenAlex.")
    c5.metric("% Open Access", f"{inv_data.get('pct_open_access',0):.1f}%", help="Porcentaje de la producción científica del investigador disponible en acceso abierto.")
    
    datos_exc_inv = f"""
    Investigador: {selected_inv}
    Citas/artículo: {citas_por_articulo:.2f}
    FWCI Promedio: {inv_data.get('fwci_avg', 0):.2f}
    Percentil Promedio: {inv_data.get('percentile_avg',50):.1f}
    % Top 10%: {inv_data.get('pct_top_10',0):.1f}%
    % Top 1%: {inv_data.get('pct_1',0):.1f}%
    """
    c_btn, c_title = st.columns([0.3, 10])
    with c_btn: render_explain_button(f"Métricas de Excelencia de {selected_inv}", "kpi_exc_inv", datos_exc_inv)
    with c_title: st.markdown("##### Métricas de Excelencia")

    ce1, ce2, ce3, ce4, ce5 = st.columns(5)
    ce1.metric("Citas/artículo", f"{citas_por_articulo:.2f}", help="Promedio de citas recibidas por artículo publicado (Total Citas dividido entre producción Indizada).")
    ce2.metric("FWCI Promedio", f"{inv_data.get('fwci_avg', 0):.2f}", help="Field-Weighted Citation Impact promedio: impacto de citación normalizado por disciplina y año (1.0 representa el promedio mundial).")
    ce3.metric("Percentil Promedio", f"{inv_data.get('percentile_avg',50):.1f}", help="Percentil de citación promedio (un percentil menor indica que el trabajo está más citado, ej. Top 10% son percentiles <= 10).")
    ce4.metric("% Top 10%", f"{inv_data.get('pct_top_10',0):.1f}%", help="Porcentaje de artículos que se ubican en el 10% más citado a nivel mundial en sus respectivas áreas y años.")
    ce5.metric("% Top 1%", f"{inv_data.get('pct_1',0):.1f}%", help="Porcentaje de artículos que se ubican en el 1% más citado a nivel mundial en sus respectivas áreas y años.")

    # ── Velocidad y Colaboración ────────────────────────────────────────────────
    vel = inv_data.get('velocity_avg', 0) or 0
    rec = int(inv_data.get('recent_cites_3yr', 0) or 0)
    
    datos_vel_inv = f"""
    Investigador: {selected_inv}
    Citas/año (prom.): {vel:.1f}
    Citas últ. 3 años: {rec}
    % Colaboración Internacional: {inv_data.get('pct_international',0):.1f}%
    Países/paper (prom.): {inv_data.get('avg_countries',0):.1f}
    Autores/paper (prom.): {inv_data.get('avg_author_count',0):.1f}
    """
    c_btn, c_title = st.columns([0.3, 10])
    with c_btn: render_explain_button(f"Velocidad de Citas y Colaboración de {selected_inv}", "kpi_vel_inv", datos_vel_inv)
    with c_title: st.markdown("##### Velocidad de Citas y Colaboración")

    cv1, cv2, cv3, cv4, cv5 = st.columns(5)
    delta_txt = f"↑ {rec} últ. 3 años" if rec > vel else None
    cv1.metric("Citas/año (prom.)",      f"{vel:.1f}", delta=delta_txt, help="Velocidad promedio de acumulación de citas por artículo por año desde su fecha de publicación.")
    cv2.metric("Citas últ. 3 años",      f"{rec:,}", help="Total de citas recibidas en los últimos 36 meses.")
    cv3.metric("% Colaboración Internacional",        f"{inv_data.get('pct_international',0):.1f}%", help="Porcentaje de artículos co-escritos con al menos un autor de una institución extranjera.")
    cv4.metric("Países/paper (prom.)",   f"{inv_data.get('avg_countries',0):.1f}", help="Número promedio de países distintos representados en las coautorías por publicación.")
    cv5.metric("Autores/paper (prom.)",  f"{inv_data.get('avg_author_count',0):.1f}", help="Número promedio de autores firmantes por artículo.")

    # ── APC ──────────────────────────────────────────────────────────────────────
    apc_inv = inv_data.get('apc_paid_usd', 0) or 0
    
    datos_apc_inv = f"""
    Investigador: {selected_inv}
    APC Total: ${apc_inv:,.0f} USD
    % Papers con APC: {inv_data.get('pct_apc',0):.1f}%
    Vida Media Citas: {inv_data.get('half_life_avg',0):.1f} años
    """
    c_btn, c_title = st.columns([0.3, 10])
    with c_btn: render_explain_button(f"Acceso Abierto y Costos de {selected_inv}", "kpi_apc_inv", datos_apc_inv)
    with c_title: st.markdown("##### Acceso Abierto y Costos")

    ca1, ca2, ca3 = st.columns(3)
    ca1.metric("APC Total",  f"${apc_inv:,.0f} USD", help="Monto estimado en USD por cargos de procesamiento de artículos (Article Processing Charges) en revistas de acceso abierto.")
    ca2.metric("% Papers con APC", f"{inv_data.get('pct_apc',0):.1f}%", help="Porcentaje de la producción publicada en revistas que requieren pago de cuotas (APC).")
    ca3.metric("Vida Media Citas", f"{inv_data.get('half_life_avg',0):.1f} años", help="Años transcurridos desde la publicación hasta que los artículos acumulan el 50% de su impacto total.")

    # ── Distribución Open Access y Perfil Temático ─────────────────────────────────
    col_donut_inv, col_gini_inv = st.columns(2)
    with col_donut_inv:
        c_btn, c_title = st.columns([0.6, 10])
        with c_btn: render_explain_button(f"Distribución Open Access de {selected_inv}", "oa_donut_inv", None)
        with c_title: st.markdown("**Distribución Open Access**")
        _render_oa_donut(inv_data, key_suffix=f"inv_{selected_inv}")
        
    with col_gini_inv:
        gini_inv = inv_data.get('gini_topics')
        n_dom_inv = int(inv_data.get('domain_diversity',0) or 0)
        n_top_inv = int(inv_data.get('unique_topics',0) or 0)
        top_dom_inv = inv_data.get('top_domain','—') or '—'
        
        datos_perfil_inv = f"""
        Investigador: {selected_inv}
        Índice de Gini temático: {gini_inv:.3f} si existe
        Dominios cubiertos: {n_dom_inv}
        Tópicos únicos: {n_top_inv}
        Dominio principal: {top_dom_inv}
        """
        c_btn, c_title = st.columns([0.6, 10])
        with c_btn: render_explain_button(f"Perfil Temático de {selected_inv}", "perfil_tematico_inv", datos_perfil_inv)
        with c_title: st.markdown("**Perfil Temático**")
        
        if gini_inv is not None and not (isinstance(gini_inv, float) and np.isnan(gini_inv)):
            st.markdown(f"""
| Indicador | Valor |
|---|---|
| Índice de Gini temático | `{gini_inv:.3f}` |
| Dominios cubiertos | **{n_dom_inv}** |
| Tópicos únicos | **{n_top_inv}** |
| Dominio principal | {top_dom_inv} |
            """.strip())
        else:
            st.info("Sin datos de diversidad temática.")

    # ── Tipos de Documentos (En nueva fila a ancho controlado) ─────────────────────
    st.markdown("---")
    col_types_inv, col_empty_types_inv = st.columns([1.1, 0.9])
    with col_types_inv:
        c_btn, c_title = st.columns([0.6, 10])
        with c_btn: render_explain_button(f"Tipos de Documentos de {selected_inv}", "types_pie_inv", "Distribución de los documentos del investigador por tipo de documento según OpenAlex.")
        with c_title: st.markdown("**Tipos de Documentos**")
        _render_document_types_pie(df_profesores_papers, key_suffix=f"inv_{selected_inv}")

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
        if df_inv_ann is not None:
            ann_data = df_inv_ann[df_inv_ann['academic_name'] == selected_inv].sort_values('year')
            c_btn, c_title = st.columns([0.6, 10])
            with c_btn: render_explain_button(f"Producción Anual de {selected_inv}", "inv_docs", ann_data[['year', 'num_documents']])
            with c_title: st.subheader("Trayectoria Histórica (Docs)")
            
            # Rango temporal: de max(1950, año_mínimo) al año en curso
            _cur_year_inv = datetime.now().year
            _yr_min_inv = int(ann_data['year'].min()) if not ann_data.empty else 1950
            _x_min_inv = max(1950, _yr_min_inv)
            fig_hist = px.bar(ann_data, x='year', y='num_documents', title="",
                              text_auto=True, range_x=[_x_min_inv - 0.5, _cur_year_inv + 0.5])
            fig_hist.update_xaxes(tickformat='d', dtick=5)
            st.plotly_chart(fig_hist, width="stretch", on_select="rerun", selection_mode=("points",), key="inv_annual_docs")
        else:
            st.info("Sin datos anuales.")

    # 3. Temáticas
    with colder:
        if df_topics is not None:
            conc_data = df_topics[df_topics['academic_name'] == selected_inv]
            if not conc_data.empty:
                conc_data = conc_data.groupby('topic')['value'].sum().reset_index()
                top_c = conc_data.sort_values('value', ascending=False).head(10)
                
                c_btn, c_title = st.columns([0.6, 10])
                with c_btn: render_explain_button(f"Áreas de Expertise de {selected_inv}", "inv_expertise", top_c)
                with c_title: st.subheader("Foco Temático (Top 10 OpenAlex Topics)")
                
                fig_bar = px.bar(top_c, x='value', y='topic', orientation='h', title="")
                fig_bar.update_layout(yaxis={'categoryorder':'total ascending'})
                st.plotly_chart(fig_bar, width="stretch")
            else:
                st.info("Sin información temática.")
        else:
            st.info("No hay caché temático.")



    # 5. Mapa UMAP
    st.markdown("---")
    
    datos_umap = f"""
    Investigador: {selected_inv}
    Métricas proyectadas en el UMAP:
    Producción: {int(inv_data.get('num_documents', 0))}
    FWCI Promedio: {inv_data.get('fwci_avg', 0):.2f}
    % Top 10%: {inv_data.get('pct_top_10',0):.1f}%
    % Top 1%: {inv_data.get('pct_1',0):.1f}%
    Percentil Promedio: {inv_data.get('percentile_avg',50):.1f}
    """
    c_btn, c_title = st.columns([0.3, 10])
    with c_btn: render_explain_button(f"Mapa de Desempeño UMAP de {selected_inv}", "umap_inv", datos_umap)
    with c_title: st.subheader("Mapas de Desempeño (UMAP)")
    
    st.markdown("Cálculo multidimensional comparando %Top 10, FWCI, % Top 1% y Percentil Promedio frente a sus pares académicos.")
    
    # 1. Mapa en el contexto de su entidad (Dependencia / Subdependencia) si aplica
    if entity_name:
        st.markdown(f"#### 🏢 Contexto de la Entidad o Dependencia: **{entity_name}**")
        _render_umap_plot(df_umap, selected_inv, f"la entidad ({entity_name})", key_suffix="entidad")
        st.markdown("---")
        
    # 2. Mapa en el contexto de la Institución completa
    st.markdown(f"#### 🏛️ Contexto de la Institución completa: **{institution_name}**")
    _render_umap_plot(df_umap_inst, selected_inv, f"la institución ({institution_name})", key_suffix="institucion")
    # ── Colaboración Internacional (Choropleth) ───────────────────────────────────
    if not df_prof.empty and "countries" in df_prof.columns:
        st.markdown("---")
        st.subheader("🌍 % Colaboración Internacional")
        
        # Evolución de colaboración (%)
        if df_inv_ann is not None and not df_inv_ann.empty:
            df_ia = df_inv_ann.sort_values('year')
            if 'pct_international' in df_ia.columns and not df_ia.empty:
                fig_intl = go.Figure()
                fig_intl.add_trace(go.Scatter(
                    x=df_ia['year'], y=df_ia['pct_international'],
                    mode='lines+markers', name='% Internacional',
                    line=dict(color='#003D64', width=2.5),
                    marker=dict(size=6, color='#E39918'),
                    fill='tozeroy', fillcolor='rgba(0,43,92,0.07)',
                    hovertemplate="%{x}: <b>%{y:.1f}%</b><extra></extra>",
                ))
                fig_intl.update_layout(
                    height=250, margin=dict(t=40,b=5,l=40,r=10),
                    yaxis=dict(ticksuffix="%", range=[0,100]),
                    xaxis=dict(showgrid=False, tickformat="d"),
                    template="plotly_white",
                    title="Evolución de Colaboración Internacional (%)",
                )
                st.plotly_chart(fig_intl, use_container_width=True, key=f"intl_evol_inv_{selected_inv}")
        
        _render_choropleth_collab(df_prof, 'academic_name', selected_inv,
                                  title="Países colaboradores",
                                  key_suffix=f"inv_{selected_inv}")

    # ── Indexación y Visibilidad ──────────────────────────────────────────────
    vis_cols_inv = ['pct_pubmed','pct_doaj_indexed','pct_core_journal',
                    'pct_repository','pct_english','pct_cc_by']
    has_vis_inv = any(inv_data.get(c, 0) != 0 for c in vis_cols_inv)
    if False: # has_vis_inv:
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

    # 6. Mapa Semántico de Producción (Investigador)
    import urllib.parse
    import json
    st.markdown("---")
    st.subheader("🗺️ Mapa Semántico de Producción")
    num_docs_inv = int(inv_data.get('num_documents', 0))
    st.write(f"Exploración espacial de la producción científica. Los **{num_docs_inv:,} artículos** del investigador están coloreados; el resto de la base nacional aparece en gris.")
    
    # Extraer DOIs y OpenAlex IDs de df_prof
    list_of_dois_inv = []
    list_of_oa_inv = []
    if not df_prof.empty:
        if 'doi' in df_prof.columns:
            list_of_dois_inv = df_prof['doi'].dropna().astype(str).tolist()
        elif 'DOI' in df_prof.columns:
            list_of_dois_inv = df_prof['DOI'].dropna().astype(str).tolist()
        if 'paper_id' in df_prof.columns:
            list_of_oa_inv = df_prof['paper_id'].dropna().astype(str).tolist()
            
    list_of_dois_inv = [d.replace('https://doi.org/', '').strip() for d in list_of_dois_inv]
    # Mantenemos el prefijo completo de OpenAlex para que coincida con el JSON del mapa
    # (articles_data.json contiene 'https://openalex.org/W...')
    list_of_oa_inv = [d.strip() for d in list_of_oa_inv]
    dois_json_inv = json.dumps(list_of_dois_inv)
    oa_json_inv = json.dumps(list_of_oa_inv)
    
    # Parámetro URL para destacar al autor (highlight_author) - Fallback
    encoded_author = urllib.parse.quote(selected_inv)
    iframe_src_inv = f"https://dinamica1.fciencias.unam.mx/tiles/map_test.html?v=28&data=https://dinamica1.fciencias.unam.mx/tiles/articles_specter_data.json?v=28&color_by=cluster&highlight_author={encoded_author}"
    safe_name_inv = "".join([c if c.isalnum() else "_" for c in selected_inv])
    
    map_html_inv = f"""
    <script>
        window._highlightDois_{safe_name_inv} = {dois_json_inv};
        window._highlightOa_{safe_name_inv} = {oa_json_inv};
        function sendDois_{safe_name_inv}(iframe) {{
            iframe.contentWindow.postMessage({{
                type: 'HIGHLIGHT_DOIS',
                dois: window._highlightDois_{safe_name_inv},
                oa_ids: window._highlightOa_{safe_name_inv}
            }}, '*');
        }}
    </script>
    <div id="map-container-inv-{safe_name_inv}" style="width:100%; overflow:hidden;">
        <iframe id="map-iframe-inv-{safe_name_inv}" src="{iframe_src_inv}" 
                style="width:100%; border:none; display:block;" 
                scrolling="no"
                onload="sendDois_{safe_name_inv}(this)">
        </iframe>
    </div>
    <script>
        function resizeInvMap() {{
            var iframe = document.getElementById('map-iframe-inv-{safe_name_inv}');
            var container = document.getElementById('map-container-inv-{safe_name_inv}');
            if(!iframe || !container) return;
            var rect = container.getBoundingClientRect();
            var availableHeight = window.innerHeight - rect.top - 10;
            if (availableHeight < 500) availableHeight = 500;
            iframe.style.height = availableHeight + 'px';
        }}
        resizeInvMap();
        window.addEventListener('resize', resizeInvMap);
        setTimeout(resizeInvMap, 300);
        setTimeout(resizeInvMap, 1000);
    </script>
    """
    
    if st.toggle("Cargar mapa interactivo (WebGL)", key=f"toggle_map_inv_{safe_name_inv}"):
        with st.spinner("Cargando el mapa semántico..."):
            components.html(map_html_inv, height=720, scrolling=False)

    st.markdown("---")
    st.subheader("📜 Lista Completa de Publicaciones")
    
    # Validar si hay publicaciones reales
    is_empty = df_prof.empty or (len(df_prof) == 1 and (df_prof['paper_id'].isna().all() or df_prof['paper_id'].iloc[0] is None))
    
    if is_empty:
        st.info("No se encontraron publicaciones indizadas para este académico en las fuentes consultadas (OpenAlex, Scopus, WoS).")
    else:
        # Blindaje contra columnas faltantes
        doi_col = 'doi' if 'doi' in df_prof.columns else ('DOI' if 'DOI' in df_prof.columns else None)
        if 'ODS_Nombre' not in df_prof.columns:
            df_prof['ODS_Nombre'] = None
        if doi_col:
            df_prof['_doi_link'] = df_prof[doi_col].apply(
                lambda d: f"https://doi.org/{str(d).replace('https://doi.org/','').strip()}" if pd.notna(d) and str(d).strip() else None
            )
        else:
            df_prof['_doi_link'] = None

        col_fil_prof1, col_fil_prof2 = st.columns(2)
        with col_fil_prof1:
            years_prof = sorted(df_prof['year'].dropna().unique(), reverse=True)
            s_year_prof = st.selectbox("Filtrar por año:", options=["Todos"] + [int(y) for y in years_prof], key="prof_year")
        with col_fil_prof2:
            ods_options_prof = sorted([str(ods) for ods in df_prof['ODS_Nombre'].dropna().unique() if ods and str(ods).lower() != "null" and "x" not in str(ods).lower()])
            s_ods_prof = st.selectbox("Filtrar por ODS:", options=["Todos"] + ods_options_prof, key="prof_ods")
        
        df_display_prof = df_prof.copy()
        if s_year_prof != "Todos":
            df_display_prof = df_display_prof[df_display_prof['year'] == s_year_prof]
        if s_ods_prof != "Todos":
            df_display_prof = df_display_prof[df_display_prof['ODS_Nombre'] == s_ods_prof]
        
        df_display_prof = _prepare_papers_table(df_display_prof)
        
        cols_to_show = ["year", "Title", "Source", "citations", "_doi_link", "openalex_url", "ODS_Nombre", "topic", "_formatted_authors"]
        df_show = df_display_prof[[c for c in cols_to_show if c in df_display_prof.columns]].rename(columns={
            "year": "Año",
            "Title": "Título",
            "Source": "Revista",
            "citations": "Citas",
            "_doi_link": "Enlace DOI",
            "openalex_url": "OpenAlex",
            "ODS_Nombre": "ODS",
            "topic": "Tópico",
            "_formatted_authors": "Autores"
        }).sort_values(by="Año", ascending=False)
        
        col_config = {
            "Enlace DOI": st.column_config.LinkColumn("Enlace DOI", display_text="Ver paper"),
            "OpenAlex": st.column_config.LinkColumn("OpenAlex", display_text="Ver en OpenAlex")
        }
        
        st.caption(f"{len(df_show):,} publicaciones mostradas")
        st.dataframe(df_show, use_container_width=True, hide_index=True, column_config=col_config)
    

    # ── Red de Colaboración Científica ───────────────────────────────────────────
    # Detectar IDs habilitantes (OpenAlex ID o ORCID)
    coauthra_id_final = inv_data.get('id') or inv_data.get('openalex_id') or inv_orcid
    
    if coauthra_id_final:
        st.markdown("---")
        st.subheader("🕸️ Red de Colaboración Científica")
        st.markdown(f"Explora el mapa interactivo de coautorías y redes académicas de **{selected_inv}**.")
        st.caption("Esta visualización es proporcionada por CoAuthra y permite identificar patrones de colaboración, investigadores sugeridos y proximidad temática.")
        
        # Usar un estado para evitar carga automática pesada en cada renderizado
        safe_name_inv = "".join([c if c.isalnum() else "_" for c in selected_inv])
        collab_key = f"load_collab_{safe_name_inv}"
        
        if collab_key not in st.session_state:
            st.session_state[collab_key] = False
            
        if not st.session_state[collab_key]:
            if st.button("🕸️ Cargar Red de Colaboración", use_container_width=True, key=f"btn_load_{safe_name_inv}", help="Desplegar visualización interactiva de grafos"):
                st.session_state[collab_key] = True
                st.rerun()
        else:
            if st.button("🚫 Ocultar Red de Colaboración", use_container_width=True, key=f"btn_hide_{safe_name_inv}"):
                st.session_state[collab_key] = False
                st.rerun()
            
            # Renderizar el componente directamente aquí
            render_coauthra(coauthra_id_final, height=1100)


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
            
        show_report_inv_key = f"show_report_inv_{safe_name}"
        show_state = st.session_state.get(show_report_inv_key, False)
        btn_text = "👁️ Ocultar Reporte" if show_state else "👁️ Ver Reporte en Pantalla"
        
        c_repA, c_repB, c_repC = st.columns([1.2, 1.2, 1])
        with c_repA:
            if st.button(btn_text, key=f"btn_view_inv_{safe_name}"):
                st.session_state[show_report_inv_key] = not show_state
                st.rerun()
        with c_repB:
            st.download_button("⬇️ Descargar Reporte (HTML)", data=html_data, file_name=f"Reporte_Investigador_{safe_name}.html", mime="text/html")
        with c_repC:
            admins_str = os.environ.get("admins", os.environ.get("ADMINS", ""))
            admin_orcids = [x.strip() for x in admins_str.split(",") if x.strip()]
            auth_user = st.session_state.get("authenticated_user")
            user_orcid = auth_user.get("orcid") if auth_user else None
            is_admin = user_orcid in admin_orcids
            
            owner_orcids = []
            if inv_orcid:
                owner_orcids = [o.strip().split('/')[-1] for o in str(inv_orcid).split(',')]
            is_owner = user_orcid in owner_orcids if user_orcid else False
            
            if is_admin or is_owner:
                if st.button("🔄 Regenerar", key=f"btn_regen_inv_{safe_name}"):
                    with st.spinner("Regenerando análisis y reporte con el modelo LLM local... Esto tomará un par de minutos."):
                        import subprocess
                        try:
                            subprocess.run([
                                sys.executable, 
                                os.path.join(BASE_PATH, "report_generator.py"), 
                                "--type", "inv", 
                                "--name", selected_inv, 
                                "--entity", entity_name, 
                                "--institution", institution_name
                            ], check=True, capture_output=True, text=True)
                            st.rerun()
                        except subprocess.CalledProcessError as e:
                            st.error(f"Fallo al generar reporte:\n{e.stderr or e.stdout}")
                            st.stop()
                
        if st.session_state.get(show_report_inv_key, False):
            st.markdown("---")
            components.html(html_data, height=900, scrolling=True)
    else:
        admins_str = os.environ.get("admins", os.environ.get("ADMINS", ""))
        admin_orcids = [x.strip() for x in admins_str.split(",") if x.strip()]
        auth_user = st.session_state.get("authenticated_user")
        user_orcid = auth_user.get("orcid") if auth_user else None
        is_admin = user_orcid in admin_orcids
        
        owner_orcids = []
        if inv_orcid:
            owner_orcids = [o.strip().split('/')[-1] for o in str(inv_orcid).split(',')]
        is_owner = user_orcid in owner_orcids if user_orcid else False
        
        if is_admin or is_owner:
            if st.button("✨ Generar Reporte con IA", key=f"btn_gen_inv_{safe_name}"):
                with st.spinner("Generando análisis y reporte con el modelo LLM local... Esto tomará un par de minutos."):
                    import subprocess
                    try:
                        subprocess.run([
                            sys.executable, 
                            os.path.join(BASE_PATH, "report_generator.py"), 
                            "--type", "inv", 
                            "--name", selected_inv, 
                            "--entity", entity_name, 
                            "--institution", institution_name
                        ], check=True, capture_output=True, text=True)
                        st.rerun()
                    except subprocess.CalledProcessError as e:
                        st.error(f"Fallo al generar reporte:\n{e.stderr or e.stdout}")
                        st.stop()


