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
CANDIDATE_CACHE_DIRS = [
    os.path.join(BASE_PATH, 'data', 'cache_ch'),
    os.path.join(BASE_PATH, 'data', 'cache'),
    '/mnt/expansion/desplegados/Topics/data/cache_temas',
    '/mnt/expansion/desplegados/revistaslatam/data_r'
]

# Clickhouse connection
try:
    from database.clickhouse_db import ch_client
    HAS_CH = True
except Exception:
    HAS_CH = False

def find_parquet_table(filename: str, institution: Optional[str] = None, academic: Optional[str] = None) -> Optional[str]:
    """Resolves hierarchical cache path across cache_ch and topic caches."""
    target_clean = filename if filename.endswith('.parquet') else f"{filename}.parquet"
    
    # 1. Search across candidate directories
    for base in CANDIDATE_CACHE_DIRS:
        if not os.path.exists(base):
            continue
            
        # Direct check
        direct = os.path.join(base, target_clean)
        if os.path.exists(direct):
            return direct
            
        q_inst = str(institution).upper().strip() if institution else ""
        q_ac = str(academic).upper().strip() if academic else ""
        
        try:
            # Sort directories to prioritize exact match on institution
            inst_list = sorted(os.listdir(base), key=lambda x: (q_inst not in x.upper() if q_inst else False, len(x)))
            for inst_name in inst_list:
                inst_dir = os.path.join(base, inst_name)
                if not os.path.isdir(inst_dir):
                    continue
                
                inst_match = (not q_inst) or (q_inst in inst_name.upper())
                
                if inst_match and not q_ac:
                    p = os.path.join(inst_dir, target_clean)
                    if os.path.exists(p):
                        return p
                        
                # Search inside subdependencies or researchers
                if inst_match or q_ac:
                    sub_list = sorted(os.listdir(inst_dir), key=lambda x: (q_inst not in x.upper() if q_inst else False, len(x)))
                    for sub_name in sub_list:
                        sub_dir = os.path.join(inst_dir, sub_name)
                        if not os.path.isdir(sub_dir):
                            continue
                            
                        # If matching subdependency
                        if q_inst and (q_inst in sub_name.upper()) and not q_ac:
                            p_sub = os.path.join(sub_dir, target_clean)
                            if os.path.exists(p_sub):
                                return p_sub
                                
                        # Match academic
                        if q_ac and (q_ac in sub_name.upper()):
                            p_ac = os.path.join(sub_dir, target_clean)
                            if os.path.exists(p_ac):
                                return p_ac
                                
                        # Level 3 check: inst -> subdep -> academic
                        for ac_name in os.listdir(sub_dir):
                            if q_ac and (q_ac in ac_name.upper()):
                                p_deep = os.path.join(sub_dir, ac_name, target_clean)
                                if os.path.exists(p_deep):
                                    return p_deep
        except Exception:
            continue
            
    return None

import duckdb

DUCKDB_PATH = '/home/sinapsisai/data/analytics_cache.duckdb'

@tool
def query_duckdb_safe_sql(sql_query: str) -> str:
    """
    Ejecuta consultas analíticas SQL ultrarrápidas de solo lectura sobre DuckDB (analytics_cache.duckdb).
    Contiene 14 tablas consolidadas de instituciones, facultades e investigadores:
    ('institucion_annual', 'institucion_total', 'investigador_annual', 'investigador_total',
     'papers_profesor', 'papers_institucion', 'topics_institucion', 'topics_investigador',
     'keywords_institucion', 'keywords_investigador', 'thematic_evolution_institucion',
     'thematic_evolution_investigador', 'umap_investigadores', 'investigador_recent').
    La consulta DEBE comenzar con SELECT o WITH.
    """
    if not os.path.exists(DUCKDB_PATH):
        return f"Base de datos DuckDB no encontrada en {DUCKDB_PATH}."
        
    clean_q = sql_query.strip()
    forbidden = ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE", "CREATE", "GRANT", "REVOKE"]
    first_word = clean_q.split()[0].upper() if clean_q else ""
    if first_word not in ["SELECT", "WITH", "DESCRIBE", "SHOW"]:
        return "Error de seguridad: Solo se permiten consultas de lectura (SELECT / WITH / DESCRIBE / SHOW)."
        
    for kw in forbidden:
        if f" {kw} " in f" {clean_q.upper()} ":
            return f"Error de seguridad: Palabra reservada '{kw}' no permitida en consultas analíticas."
            
    if "LIMIT" not in clean_q.upper() and first_word in ["SELECT", "WITH"]:
        clean_q = f"{clean_q} LIMIT 50"
        
    try:
        con = duckdb.connect(DUCKDB_PATH, read_only=True)
        df = con.execute(clean_q).df()
        con.close()
        if df.empty:
            return "La consulta en DuckDB no devolvió registros."
        cols_to_drop = [c for c in df.columns if c.startswith('embedding') or 'vector' in c]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)
        return df.head(50).to_json(orient='records', force_ascii=False, date_format='iso')
    except Exception as e:
        return f"Error ejecutando consulta en DuckDB: {str(e)}"

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
    Consulta segura de tablas estructuradas en caché (DuckDB acelerado / Parquet).
    Args:
        table_type: Tipo de tabla ('institucion_annual', 'institucion_total', 'investigador_annual', 'investigador_total', 'papers_profesor', 'papers_institucion', 'topics_institucion', 'umap_investigadores').
        institution: Nombre de la institución/entidad (ej. 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO', 'FACULTAD DE CIENCIAS').
        academic: Nombre del académico/investigador (opcional).
        sort_by: Columna para ordenar resultados (ej. 'fwci', 'fwci_avg', 'num_documents', 'citations', 'year', 'publication_year').
        ascending: True para orden ascendente, False para descendente.
        top_n: Número máximo de registros a devolver (default: 10).
    """
    clean_type = table_type.replace('.parquet', '').strip()
    
    # 1. INTENTO DE CONSULTA ACELERADA EN DUCKDB (Ultra-alta velocidad)
    if os.path.exists(DUCKDB_PATH):
        try:
            con = duckdb.connect(DUCKDB_PATH, read_only=True)
            tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
            
            # Normalizar nombre de tabla
            matched_table = clean_type if clean_type in tables else None
            if not matched_table and f"{clean_type}_institucion" in tables:
                matched_table = f"{clean_type}_institucion"
            elif not matched_table and f"{clean_type}_investigador" in tables:
                matched_table = f"{clean_type}_investigador"
                
            if matched_table:
                where_clauses = []
                params = []
                if institution:
                    q_i = f"%{institution.strip()}%"
                    where_clauses.append("(db_institution_name ILIKE ? OR db_entity_name ILIKE ?)")
                    params.extend([q_i, q_i])
                if academic:
                    q_a = f"%{academic.strip()}%"
                    where_clauses.append("db_academic_name ILIKE ?")
                    params.append(q_a)
                    
                where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
                order_sql = ""
                if sort_by:
                    order_dir = "ASC" if ascending else "DESC"
                    order_sql = f' ORDER BY "{sort_by}" {order_dir}'
                    
                query_sql = f'SELECT * FROM "{matched_table}" WHERE {where_sql}{order_sql} LIMIT {top_n}'
                df_duck = con.execute(query_sql, params).df()
                con.close()
                
                if not df_duck.empty:
                    cols_to_drop = [c for c in df_duck.columns if c.startswith('embedding') or 'vector' in c]
                    if cols_to_drop:
                        df_duck = df_duck.drop(columns=cols_to_drop)
                    return df_duck.to_json(orient='records', force_ascii=False, date_format='iso')
            else:
                con.close()
        except Exception:
            pass

    # 2. FALLBACK A ESCANEO DE ARCHIVOS PARQUET
    table_map = {
        'institucion_annual': 'institucion_annual.parquet',
        'institucion_total': 'institucion_total.parquet',
        'investigador_annual': 'investigador_annual.parquet',
        'investigador_total': 'investigador_total.parquet',
        'papers_profesor': 'papers_profesor.parquet',
        'papers_institucion': 'papers_institucion.parquet',
        'topics': 'topics_institucion.parquet',
        'topics_institucion': 'topics_institucion.parquet',
        'topics_investigador': 'topics_investigador.parquet',
        'umap_investigadores': 'umap_investigadores.parquet'
    }
    
    fname = table_map.get(clean_type, f"{clean_type}.parquet")
    path = find_parquet_table(fname, institution, academic)
    
    if not path or not os.path.exists(path):
        return f"Información no encontrada en caché ni en DuckDB para '{table_type}' (Institución: {institution}, Académico: {academic})."
        
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return f"La tabla '{table_type}' está vacía."
            
        if sort_by and sort_by in df.columns:
            df = df.sort_values(by=sort_by, ascending=ascending)
            
        df_sub = df.head(top_n)
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
    # 1. Búsqueda rápida en DuckDB
    if os.path.exists(DUCKDB_PATH):
        try:
            con = duckdb.connect(DUCKDB_PATH, read_only=True)
            q = """
            SELECT db_academic_name, db_institution_name, db_entity_name, num_documents, citations, fwci_avg, h_index, pct_oa_diamond 
            FROM investigador_total 
            WHERE db_academic_name ILIKE ?
            LIMIT 1
            """
            df_res = con.execute(q, [f"%{academic_name.strip()}%"]).df()
            con.close()
            if not df_res.empty:
                r = df_res.iloc[0]
                summary = {
                    'investigador': r.get('db_academic_name'),
                    'institucion': r.get('db_institution_name', institution_name),
                    'dependencia': r.get('db_entity_name'),
                    'documentos_totales': int(r.get('num_documents', 0)),
                    'citas_totales': int(r.get('citations', 0)),
                    'fwci_promedio': round(float(r.get('fwci_avg', 0)), 2),
                    'h_index': int(r.get('h_index', 0)) if pd.notnull(r.get('h_index')) else None,
                    'oa_diamante_pct': round(float(r.get('pct_oa_diamond', 0)), 1) if pd.notnull(r.get('pct_oa_diamond')) else None
                }
                return json.dumps(summary, ensure_ascii=False)
        except Exception:
            pass

    # 2. Fallback a parquet umap_investigadores
    umap_path = find_parquet_table('umap_investigadores.parquet')
    if umap_path and os.path.exists(umap_path):
        try:
            df_u = pd.read_parquet(umap_path)
            col_name = 'academic_name' if 'academic_name' in df_u.columns else ('db_academic_name' if 'db_academic_name' in df_u.columns else None)
            if col_name:
                match = df_u[df_u[col_name].astype(str).str.contains(academic_name, case=False, na=False)]
                if not match.empty:
                    row = match.iloc[0]
                    summary = {
                        'investigador': row.get(col_name),
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
    query_duckdb_safe_sql,
    query_clickhouse_safe_sql,
    get_scientometric_summary
]
