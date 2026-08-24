"""
tools_interpreter.py - Safe & Deterministic Structured Analytical Tools (Tier 1)
Replaces raw exec() with typed, safe queries over cached Parquet data and ClickHouse.
"""
import os
import sys
import json
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List
from langchain_core.tools import Tool, tool

BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CACHE_DIR = os.path.join(BASE_PATH, 'data', 'cache')

# Clickhouse connection
try:
    from database.clickhouse_db import ch_client
    HAS_CH = True
except Exception:
    HAS_CH = False

def find_parquet_table(filename: str, institution: Optional[str] = None, academic: Optional[str] = None) -> Optional[str]:
    """Resolves hierarchical cache path."""
    if institution:
        safe_inst = str(institution).replace('/', '_').replace('\\', '_')
        if academic:
            safe_ac = str(academic).replace('/', '_').replace('\\', '_')
            p = os.path.join(CACHE_DIR, safe_inst, safe_ac, filename)
            if os.path.exists(p): return p
        p = os.path.join(CACHE_DIR, safe_inst, filename)
        if os.path.exists(p): return p
    p = os.path.join(CACHE_DIR, filename)
    if os.path.exists(p): return p
    return None

@tool
def query_academic_cache(
    table_type: str,
    institution: Optional[str] = None,
    academic: Optional[str] = None,
    sort_by: Optional[str] = None,
    ascending: bool = False,
    top_n: int = 10
) -> str:
    """
    Consulta segura de tablas estructuradas en caché (Parquet).
    Args:
        table_type: Tipo de tabla ('institucion_annual', 'investigador_annual', 'papers_profesor', 'topics', 'umap_investigadores').
        institution: Nombre de la institución/entidad (ej. 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO').
        academic: Nombre del académico/investigador (opcional).
        sort_by: Columna para ordenar resultados (ej. 'fwci', 'num_documents', 'citations', 'publication_year').
        ascending: True para orden ascendente, False para descendente.
        top_n: Número máximo de registros a devolver (default: 10).
    """
    table_map = {
        'institucion_annual': 'institucion_annual.parquet',
        'institucion_total': 'institucion_total.parquet',
        'investigador_annual': 'investigador_annual.parquet',
        'investigador_total': 'investigador_total.parquet',
        'papers_profesor': 'papers_profesor.parquet',
        'papers_institucion': 'papers_institucion.parquet',
        'topics': 'topics_institucion.parquet',
        'umap_investigadores': 'umap_investigadores.parquet'
    }
    
    fname = table_map.get(table_type, f"{table_type}.parquet")
    path = find_parquet_table(fname, institution, academic)
    
    if not path or not os.path.exists(path):
        return f"Información no encontrada en caché para '{table_type}' (Institución: {institution}, Académico: {academic})."
        
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return f"La tabla '{table_type}' está vacía."
            
        if sort_by and sort_by in df.columns:
            df = df.sort_values(by=sort_by, ascending=ascending)
            
        df_sub = df.head(top_n)
        # Select concise columns
        cols_to_drop = [c for c in df_sub.columns if c.startswith('embedding') or 'vector' in c]
        if cols_to_drop:
            df_sub = df_sub.drop(columns=cols_to_drop)
            
        return df_sub.to_json(orient='records', force_ascii=False, date_format='iso')
    except Exception as e:
        return f"Error leyendo datos estructurados: {str(e)}"

@tool
def query_clickhouse_safe_sql(sql_query: str) -> str:
    """
    Ejecuta una consulta SQL de solo lectura sobre ClickHouse para analítica masiva (OpenAlex / SNII).
    La consulta DEBE comenzar con SELECT. Operaciones destructivas están bloqueadas.
    """
    if not HAS_CH:
        return "Servicio ClickHouse no configurado localmente."
        
    clean_q = sql_query.strip()
    # Safety checks
    forbidden = ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE", "CREATE", "GRANT", "REVOKE"]
    first_word = clean_q.split()[0].upper() if clean_q else ""
    if first_word != "SELECT" and first_word != "WITH":
        return "Error de seguridad: Solo se permiten consultas de lectura (SELECT / WITH)."
        
    for kw in forbidden:
        if f" {kw} " in f" {clean_q.upper()} ":
            return f"Error de seguridad: Palabra reservada '{kw}' no permitida."
            
    # Add LIMIT if missing
    if "LIMIT" not in clean_q.upper():
        clean_q = f"{clean_q} LIMIT 50"
        
    try:
        client = ch_client.get_client()
        df = client.query_df(clean_q)
        if df.empty:
            return "La consulta no devolvió registros."
        return df.head(50).to_json(orient='records', force_ascii=False)
    except Exception as e:
        return f"Error ejecutando SQL en ClickHouse: {str(e)}"

@tool
def get_scientometric_summary(academic_name: str, institution_name: Optional[str] = None) -> str:
    """
    Obtiene un resumen cienciométrico integral de un investigador (FWCI, H-index, Total Citas, % OA Diamante, Top Topics).
    """
    # 1. Search in umap_investigadores
    umap_path = os.path.join(CACHE_DIR, 'umap_investigadores.parquet')
    if os.path.exists(umap_path):
        try:
            df_u = pd.read_parquet(umap_path)
            match = df_u[df_u['academic_name'].str.contains(academic_name, case=False, na=False)]
            if not match.empty:
                row = match.iloc[0]
                summary = {
                    'investigador': row.get('academic_name'),
                    'institucion': row.get('institution', institution_name),
                    'documentos_totales': int(row.get('num_documents', 0)),
                    'citas_totales': int(row.get('citations', 0)),
                    'fwci_promedio': round(float(row.get('fwci_avg', 0)), 2),
                    'h_index': int(row.get('h_index', 0)) if 'h_index' in row else None,
                    'oa_diamante_pct': round(float(row.get('pct_oa_diamond', 0)), 1) if 'pct_oa_diamond' in row else None
                }
                return json.dumps(summary, ensure_ascii=False)
        except Exception:
            pass
            
    return f"No se encontró resumen consolidado para el investigador '{academic_name}'."

# Deterministic tools list for Tier 1
structured_analytics_tools = [
    query_academic_cache,
    query_clickhouse_safe_sql,
    get_scientometric_summary
]
