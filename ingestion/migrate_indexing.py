
import os
import sys
import json
import pandas as pd
import unicodedata
import re
from dotenv import load_dotenv
from Levenshtein import jaro_winkler

# Añadir path raíz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database.knowledge_graph import Neo4jGraphStore

def normalize_text(text):
    if not text or pd.isna(text): return ""
    text = unicodedata.normalize('NFD', str(text)).encode('ascii', 'ignore').decode('utf-8')
    text = text.lower().strip()
    text = re.sub(r'\b(dr|dra|msc|phd|mtro|mtra|lic|ing|profr?|profra)\.?\s*', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_token_sorted_name(name_str):
    clean = normalize_text(name_str).replace(',', ' ')
    tokens = sorted([t for t in clean.split() if len(t) > 1])
    return " ".join(tokens)

def migrate_indexing():
    load_dotenv()
    graph = Neo4jGraphStore()
    
    print("🚀 Iniciando migración de indización...")
    
    # 1. Marcar Papers actuales como IndexedWoS
    print("📦 Marcando Papers actuales como :IndexedWoS...")
    query_papers = """
    MATCH (p:Paper)
    SET p:IndexedWoS, p.in_wos = true
    RETURN count(p) as count
    """
    
    with graph.driver.session() as session:
        result = session.run(query_papers).single()
        print(f"✅ {result['count']} papers marcados como :IndexedWoS.")
        
    # 2. Marcar Académicos como SNII cruzando con Excel
    snii_excel_path = os.path.join("SNII", "Investigadores_vigentes_2025.xlsx")
    
    if os.path.exists(snii_excel_path):
        print(f"🧬 Procesando Excel SNII desde {snii_excel_path}...")
        df_snii = pd.read_excel(snii_excel_path)
        
        # Asumimos columnas estándar del padrón 2025
        name_col = 'NOMBRE DEL INVESTIGADOR'
        # A veces el Excel enriquecido tiene ORCID, si no, usaremos nombres
        orcid_col = 'ORCID' if 'ORCID' in df_snii.columns else None
        
        snii_data = []
        for _, row in df_snii.iterrows():
            name = str(row[name_col])
            snii_data.append({
                "name": name,
                "norm_name": get_token_sorted_name(name),
                "orcid": str(row[orcid_col]) if orcid_col and pd.notna(row[orcid_col]) else None
            })
        
        print(f"   {len(snii_data)} investigadores cargados del Excel.")

        # Obtener académicos existentes en Neo4j
        print("🔗 Recuperando académicos de Neo4j...")
        query_acads = "MATCH (a:Academic) RETURN id(a) as id, a.name as name, a.orcid as orcid"
        with graph.driver.session() as session:
            acads_neo4j = list(session.run(query_acads))
        
        print(f"   {len(acads_neo4j)} académicos encontrados en Neo4j.")
        
        snii_updates = []
        for acad in acads_neo4j:
            node_id = acad['id']
            a_name = acad['name']
            a_orcid = acad['orcid']
            a_norm = get_token_sorted_name(a_name)
            
            is_match = False
            for snii in snii_data:
                # Prioridad 1: ORCID
                if a_orcid and snii['orcid'] and a_orcid == snii['orcid']:
                    is_match = True
                    break
                # Prioridad 2: Nombre (Jaro-Winkler alto)
                if jaro_winkler(a_norm, snii['norm_name']) > 0.95:
                    is_match = True
                    break
            
            if is_match:
                snii_updates.append(node_id)
        
        print(f"   {len(snii_updates)} académicos coinciden con el padrón SNII.")
        
        if snii_updates:
            query_update = """
            UNWIND $ids as target_id
            MATCH (a) WHERE id(a) = target_id
            SET a:SNII, a.is_snii = true
            RETURN count(a) as count
            """
            with graph.driver.session() as session:
                res = session.run(query_update, ids=snii_updates).single()
                print(f"✅ {res['count']} académicos marcados como :SNII.")
        else:
            print("⚠️ No se encontraron coincidencias para marcar.")
            
    else:
        print(f"⚠️ No se encontró el Excel del SNII en {snii_excel_path}.")

    graph.close()
    print("✨ Migración completada.")

if __name__ == "__main__":
    migrate_indexing()
