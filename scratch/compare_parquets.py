import pandas as pd
import numpy as np
import os

BASE_OLD = r'data/cache/UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)/FACULTAD DE CIENCIAS/PARDO CEMO, ANNIE'
BASE_NEW = r'data/cache_ch/UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)/FACULTAD DE CIENCIAS/PARDO CEMO, ANNIE'

# ── papers_profesor ─────────────────────────────────────────────────────────
old_p = pd.read_parquet(f'{BASE_OLD}/papers_profesor.parquet')
new_p = pd.read_parquet(f'{BASE_NEW}/papers_profesor.parquet')

print('=== papers_profesor ===')
print(f'Filas: old={len(old_p)} | new={len(new_p)}')
print(f'has_oa_data old: {old_p["has_oa_data"].value_counts().to_dict()}')
print(f'has_oa_data new: {new_p["has_oa_data"].value_counts().to_dict() if "has_oa_data" in new_p.columns else "FALTA"}')

for col in ['fwci','citations','year','Title']:
    old_v = old_p[col].notna().sum() if col in old_p.columns else 'FALTA'
    new_v = new_p[col].notna().sum() if col in new_p.columns else 'FALTA'
    print(f'  {col} no-nulos: old={old_v} | new={new_v}')

missing = sorted(set(old_p.columns) - set(new_p.columns))
print(f'Cols faltantes en new papers_profesor: {missing}')
print()

# ── Parquets disponibles ─────────────────────────────────────────────────────
old_files = set(os.listdir(BASE_OLD))
new_files = set(os.listdir(BASE_NEW))
print('=== ARCHIVOS ===')
print(f'OLD ({len(old_files)}): {sorted(old_files)}')
print(f'NEW ({len(new_files)}): {sorted(new_files)}')
only_old = old_files - new_files
only_new = new_files - old_files
print(f'Solo en OLD: {sorted(only_old)}')
print(f'Solo en NEW: {sorted(only_new)}')
print()

# ── investigador_total ───────────────────────────────────────────────────────
if 'investigador_total.parquet' in new_files:
    old_t = pd.read_parquet(f'{BASE_OLD}/investigador_total.parquet')
    new_t = pd.read_parquet(f'{BASE_NEW}/investigador_total.parquet')
    print('=== investigador_total ===')
    key_cols = ['num_documents','citations','fwci_avg','percentile_avg',
                'pct_top_10','pct_open_access','h_index','avg_author_count']
    print('OLD:')
    print(old_t[[c for c in key_cols if c in old_t.columns]].to_string())
    print('NEW:')
    print(new_t[[c for c in key_cols if c in new_t.columns]].to_string())
    missing_t = sorted(set(old_t.columns) - set(new_t.columns))
    print(f'Cols faltantes en investigador_total: {missing_t}')
