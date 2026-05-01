import pandas as pd
import numpy as np
import os

BASE_OLD = r'data/cache/UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)/FACULTAD DE CIENCIAS/PARDO CEMO, ANNIE'
BASE_NEW = r'data/cache_ch/UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)/FACULTAD DE CIENCIAS/PARDO CEMO, ANNIE'

PARQUETS = [
    'papers_profesor.parquet',
    'investigador_total.parquet',
    'investigador_annual.parquet',
    'investigador_recent.parquet',
    'keywords_investigador.parquet',
    'topics_investigador.parquet',
    'thematic_evolution_investigador.parquet',
]

SEP = '=' * 70

for fname in PARQUETS:
    old_path = f'{BASE_OLD}/{fname}'
    new_path = f'{BASE_NEW}/{fname}'
    print(SEP)
    print(f'  {fname}')
    print(SEP)

    if not os.path.exists(old_path):
        print('  [FALTA EN OLD]'); continue
    if not os.path.exists(new_path):
        print('  [FALTA EN NEW]'); continue

    old = pd.read_parquet(old_path)
    new = pd.read_parquet(new_path)

    print(f'  Filas: old={len(old)} | new={len(new)}')
    only_old = sorted(set(old.columns) - set(new.columns))
    only_new = sorted(set(new.columns) - set(old.columns))
    if only_old:
        print(f'  Cols solo en OLD ({len(only_old)}): {only_old}')
    if only_new:
        print(f'  Cols solo en NEW ({len(only_new)}): {only_new}')

    # Comparar columnas numéricas clave
    if fname == 'papers_profesor.parquet':
        print(f'  has_oa_data  old={old["has_oa_data"].value_counts().to_dict()} | new={new["has_oa_data"].value_counts().to_dict()}')
        for col in ['citations', 'fwci', 'year']:
            o = old[col].notna().sum() if col in old.columns else 'N/A'
            n = new[col].notna().sum() if col in new.columns else 'FALTA'
            print(f'  {col} no-nulos: old={o} | new={n}')

    elif fname == 'investigador_total.parquet':
        key = ['num_documents','citations','fwci_avg','percentile_avg',
               'pct_top_10','pct_open_access','h_index']
        print('\n  OLD:')
        print(old[[c for c in key if c in old.columns]].to_string(index=False))
        print('\n  NEW:')
        print(new[[c for c in key if c in new.columns]].to_string(index=False))

    elif fname == 'investigador_annual.parquet':
        key = ['year','num_documents','citations','fwci_avg','h_index']
        common = [c for c in key if c in old.columns and c in new.columns]
        o_tail = old.sort_values('year').tail(3)[common] if 'year' in old.columns else old.tail(3)[common]
        n_tail = new.sort_values('year').tail(3)[common] if 'year' in new.columns else new.tail(3)[common]
        print('  OLD (últimos 3 años):')
        print(o_tail.to_string(index=False))
        print('  NEW (últimos 3 años):')
        print(n_tail.to_string(index=False))

    elif fname == 'keywords_investigador.parquet':
        print('  OLD top-5:')
        print(old.sort_values('freq', ascending=False).head(5)[['keyword','freq']].to_string(index=False) if 'freq' in old.columns else old.head(5))
        print('  NEW top-5:')
        print(new.sort_values('freq', ascending=False).head(5)[['keyword','freq']].to_string(index=False) if 'freq' in new.columns else new.head(5))

    elif fname == 'topics_investigador.parquet':
        print('  OLD top-5 topics:')
        print(old.sort_values('value', ascending=False).head(5)[['topic','value']].to_string(index=False) if 'value' in old.columns else old.head(5))
        print('  NEW top-5 topics:')
        print(new.sort_values('value', ascending=False).head(5)[['topic','value']].to_string(index=False) if 'value' in new.columns else new.head(5))

    print()
