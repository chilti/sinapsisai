"""
materialize_paper_author_map.py
================================
Refactored version (v5): 
- Uses the official SNII 2025 Excel as the primary source for researcher identity and hierarchy.
- Links researchers to their papers in Neo4j using the CVU as the join key.
- Populates paper_author_map in ClickHouse.
- Sheet: "4T_2025 (44,794)" with corrected headers (CVU, INSTITUCION DE ACREDITACION, etc.)
"""
import os
import sys
import pandas as pd
import re
from pathlib import Path
from dotenv import load_dotenv

# Path setup
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))
load_dotenv(str(_THIS.parent / '.env'))

from database.knowledge_graph import Neo4jGraphStore
from database.clickhouse_db import ch_client

TABLE = 'paper_author_map'
EXCEL_PATH = 'data/Investigadores_vigentes_2025.xlsx'
SHEET_NAME = "4T_2025 (44,794)"

def normalize_paper_id(pid: str) -> str:
    if not pid: return None
    s = str(pid).strip()
    if re.match(r'^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$', s): return None
    short = s.rstrip('/').split('/')[-1].upper()
    if short.startswith('W') and short[1:].isdigit():
        return f'https://openalex.org/{short}'
    if 'openalex.org/W' in s:
        return s.replace('http://', 'https://')
    return None

def materialize():
    print(f"🚀 Starting materialization from Excel: {EXCEL_PATH} (Sheet: {SHEET_NAME})")
    
    # 1. Load Excel
    try:
        df_snii = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
        print(f"✅ Loaded {len(df_snii)} researchers from Excel.")
    except Exception as e:
        print(f"❌ Error loading Excel: {e}")
        return

    # 2. Prepare ClickHouse
    client = ch_client.get_client()
    
    # DDL with CVU support and hierarchy from Excel
    DDL = f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        paper_id          String,
        academic_name     String,
        cvu               String,
        orcid             String,
        openalex_id       String,
        institution       String,
        institution_ror   String,
        dependency        String,
        subdependency     String,
        paper_title       String,
        paper_year        UInt16,
        citations         UInt32,
        is_wos            UInt8,
        is_scopus         UInt8,
        is_pubmed         UInt8,
        is_openalex       UInt8,
        is_doaj           UInt8,
        is_semantic_scholar UInt8,
        is_dimensions     UInt8,
        is_lens           UInt8,
        is_snii           UInt8,
        source            String,
        audit_verdict     String
    )
    ENGINE = ReplacingMergeTree()
    ORDER BY (institution, paper_id, cvu)
    """
    client.command(DDL)

    # 3. Process in batches
    gs = Neo4jGraphStore()
    batch_size = 500
    rows_to_insert = []
    total_processed = 0
    total_relations = 0

    # Column Mapping based on specific sheet
    col_cvu = 'CVU'
    col_name = 'NOMBRE DEL INVESTIGADOR'
    col_inst = 'INSTITUCION DE ACREDITACION' # No accent in this sheet
    col_dep = 'DEPENDENCIA DE ACREDITACIÓN'
    col_sub = 'SUBDEPENDENCIA DE ACREDITACIÓN'

    # Ensure CVUs are strings
    df_snii[col_cvu] = df_snii[col_cvu].astype(str).str.strip()

    for i in range(0, len(df_snii), batch_size):
        batch_df = df_snii.iloc[i : i + batch_size]
        cvus = batch_df[col_cvu].tolist()
        
        # Query Neo4j for all papers by these CVUs
        query = """
        MATCH (a:Author)
        WHERE a.cvu IN $cvus
        MATCH (a)-[:AUTHORED]->(p:Paper)
        RETURN a.cvu as cvu, p.id as paper_id, a.orcid as orcid, a.openalex_id as openalex_id, 
               a.audit_verdict as audit_verdict, a.name as matched_name
        """
        
        with gs.driver.session() as session:
            results = session.run(query, cvus=cvus)
            neo_data = {}
            for r in results:
                c = r['cvu']
                if c not in neo_data: neo_data[c] = []
                neo_data[c].append(r)

        # Map Excel data to ClickHouse rows using Neo4j matches
        for _, row_excel in batch_df.iterrows():
            cvu = row_excel[col_cvu]
            matches = neo_data.get(cvu, [])
            
            for m in matches:
                p_id = normalize_paper_id(m['paper_id'])
                if not p_id: continue
                
                rows_to_insert.append({
                    'paper_id': p_id,
                    'academic_name': row_excel[col_name],
                    'cvu': cvu,
                    'orcid': m['orcid'] or '',
                    'openalex_id': m['openalex_id'] or '',
                    'institution': str(row_excel[col_inst] or ''),
                    'institution_ror': '',
                    'dependency': str(row_excel[col_dep] or ''),
                    'subdependency': str(row_excel[col_sub] or ''),
                    'paper_title': m.get('title') or '',
                    'paper_year': int(m.get('year') or 0),
                    'citations': int(m.get('citations') or 0),
                    'is_wos': 1 if m.get('is_wos') else 0,
                    'is_scopus': 1 if m.get('is_scopus') else 0,
                    'is_pubmed': 1 if m.get('is_pubmed') else 0,
                    'is_openalex': 1,
                    'is_doaj': 1 if m.get('is_doaj') else 0,
                    'is_semantic_scholar': 0, # Reservado para enriquecimiento
                    'is_dimensions': 0,
                    'is_lens': 0,
                    'is_snii': 1,
                    'source': 'Official SNII Census + Neo4j',
                    'audit_verdict': m['audit_verdict'] or ''
                })
                total_relations += 1

        # Insert into ClickHouse periodically
        if len(rows_to_insert) >= 5000:
            client.insert_df(TABLE, pd.DataFrame(rows_to_insert))
            rows_to_insert = []
            print(f"   Processed {i + len(batch_df)} researchers... ({total_relations} relations inserted)")

    # Final insert
    if rows_to_insert:
        client.insert_df(TABLE, pd.DataFrame(rows_to_insert))
    
    print(f"✅ Finished. Total researchers processed: {len(df_snii)}. Total paper-author relations: {total_relations}.")
    gs.close()

if __name__ == "__main__":
    materialize()
