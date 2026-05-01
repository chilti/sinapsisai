import pandas as pd

df = pd.read_parquet(r'data/cache/UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)/FACULTAD DE CIENCIAS/PARDO CEMO, ANNIE/papers_profesor.parquet')

audit_cols = ['audit_verdict','audit_confidence','audit_reason','audit_timestamp',
              'match_reason','siia_url','discarded_candidates']

print('=== Audit columns in OLD papers_profesor ===')
for col in audit_cols:
    if col in df.columns:
        nn = df[col].notna().sum()
        sample = df[col].dropna().head(2).tolist()
        try:
            print(f'{col} ({nn} non-null): {str(sample)[:120]}')
        except Exception:
            print(f'{col} ({nn} non-null): <unprintable>')
    else:
        print(f'{col}: MISSING')

print()
print('=== Neo4j Cypher query needed ===')
print('These columns come from: AUTHORED relationship properties or Academic/Paper nodes')
print('paper_id sample:', df['paper_id'].head(3).tolist())
print('siia_url sample:', df['siia_url'].dropna().head(2).tolist() if 'siia_url' in df.columns else 'N/A')
