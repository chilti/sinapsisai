"""
rebuild_neo4j_hierarchy.py
==========================
Reconstruye la jerarquía de Neo4j usando las columnas de Acreditación del SNII 2025.
Lógica: Institución -> Dependencia -> Subdependencia.
Maneja casos de "SIN INSTITUCIÓN" y valores nulos/SIN INFORMACIÓN.
"""
import sys, os, json
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, '.')
load_dotenv()

from database.knowledge_graph import Neo4jGraphStore

# ── Configuración ──────────────────────────────────────────────────────────
EXCEL_PATH    = 'data/Investigadores_vigentes_2025.xlsx'
ACADEMIC_JSON = 'data/snii_llm_verified_matches.json'
ROR_JSON      = 'data/snii_ror_verified_matches.json'

# Valores que consideramos como "vacíos"
NULL_VALUES = ['SIN INFORMACIÓN', 'NO APLICA', 'SIN INSTITUCION', 'nan', 'None', '', 'SIN INFORMACIN', 'SIN INFORMACIÃ“N']

def normalize(val):
    s = str(val).strip()
    if s.upper() in [v.upper() for v in NULL_VALUES] or not s:
        return None
    return s

def rebuild():
    gs = Neo4jGraphStore()
    
    print("⛓️ Fase 1: Configurando restricciones...")
    with gs.driver.session() as session:
        session.run("CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
        session.run("CREATE CONSTRAINT institution_id_unique IF NOT EXISTS FOR (i:Institution) REQUIRE i.id IS UNIQUE")
        session.run("CREATE CONSTRAINT author_cvu_unique IF NOT EXISTS FOR (a:Author) REQUIRE a.cvu IS UNIQUE")
        print("   ✅ Restricciones configuradas.")

    print("\n📂 Fase 2: Cargando archivos...")
    
    # Cargar primero solo el header para mapear columnas dinámicamente
    header_df = pd.read_excel(EXCEL_PATH, sheet_name='4T_2025 (44,794)', nrows=0)
    original_cols = header_df.columns.tolist()
    
    # Mapeo de búsqueda (normalizado)
    target_map = {
        'NOMBRE': ['NOMBRE DEL INVESTIGADOR', 'NOMBRE', 'INVESTIGADOR'],
        'CVU': ['CVU', 'NUMERO DE CVU', 'NÚMERO DE CVU', 'ID_CVU'],
        'INSTITUCION': ['INSTITUCION DE ACREDITACION', 'INSTITUCIÓN DE ACREDITACIÓN', 'INSTITUCION'],
        'DEPENDENCIA': ['DEPENDENCIA DE ACREDITACION', 'DEPENDENCIA DE ACREDITACIÓN', 'DEPENDENCIA'],
        'SUBDEPENDENCIA': ['SUBDEPENDENCIA DE ACREDITACION', 'SUBDEPENDENCIA DE ACREDITACIÓN', 'SUBDEPENDENCIA'],
        'ENTIDAD_FINAL': ['ENTIDAD FINAL']
    }
    
    actual_cols_to_read = []
    rename_dict = {}
    
    for canonical, variations in target_map.items():
        found = False
        for var in variations:
            for col in original_cols:
                if col.strip().upper() == var.upper():
                    actual_cols_to_read.append(col)
                    rename_dict[col] = canonical
                    found = True
                    break
            if found: break
        if not found and canonical != 'CVU': # CVU es opcional pero altamente recomendado
            print(f"⚠️ Advertencia: No se encontró columna para '{canonical}'")

    df_snii = pd.read_excel(EXCEL_PATH, usecols=actual_cols_to_read, sheet_name='4T_2025 (44,794)')
    df_snii = df_snii.rename(columns=rename_dict)
    
    # Asegurar existencia de CVU
    if 'CVU' not in df_snii.columns:
        df_snii['CVU'] = None
    
    with open(ACADEMIC_JSON, 'r', encoding='utf-8') as f:
        academic_matches = json.load(f)
    with open(ROR_JSON, 'r', encoding='utf-8') as f:
        ror_matches = json.load(f)

    def normalize_hierarchy(row):
        inst = normalize(row['INSTITUCION']) or "SIN INSTITUCION"
        dep = normalize(row['DEPENDENCIA']) or "SIN INFORMACION"
        sub = normalize(row['SUBDEPENDENCIA']) or "SIN INFORMACION"
        
        if inst.upper() in ["SIN INSTITUCION", "DESCONOCIDO", ""]:
            return "SIN INSTITUCION", "NO APLICA", "NO APLICA"
        
        if dep.upper() in ["SIN INFORMACION", "NO APLICA", ""]:
            dep = "NO APLICA"
        if sub.upper() in ["SIN INFORMACION", "NO APLICA", ""]:
            sub = "NO APLICA"
            
        return inst, dep, sub

    print("\n🏗️ Fase 3: Reconstruyendo Jerarquía (Incremental)...")
    
    df_snii[['INSTITUCION', 'DEPENDENCIA', 'SUBDEPENDENCIA']] = df_snii.apply(
        lambda x: pd.Series(normalize_hierarchy(x)), axis=1
    )

    # Pre-calcular mapeo de Institución -> ROR
    inst_to_ror = {}
    for key, meta in ror_matches.items():
        p_name = meta.get('parent_name')
        p_ror = meta.get('parent_ror')
        if p_name and p_ror:
            inst_to_ror[normalize(p_name)] = p_ror
    
    if "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)" not in inst_to_ror:
        inst_to_ror["UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)"] = "https://ror.org/01tmp8f25"

    groups = df_snii.groupby([
        'INSTITUCION', 
        'DEPENDENCIA', 
        'SUBDEPENDENCIA'
    ], dropna=False)

    print(f"📊 Grupos jerárquicos identificados: {len(groups)}")

    with gs.driver.session() as session:
        total = len(groups)
        for i, (hierarchy, group) in enumerate(groups, 1):
            raw_inst, raw_dep, raw_sub = hierarchy
            inst_name = normalize(raw_inst) or "SIN INSTITUCION"
            
            # 1. Institución
            ror_id = inst_to_ror.get(inst_name) or f"manual:{inst_name}"
            session.run("""
                MERGE (i:Institution {id: $id})
                SET i.name = $name, i.ror = coalesce(i.ror, $ror)
            """, id=ror_id, name=inst_name, ror=inst_to_ror.get(inst_name))
            
            curr_parent_id = ror_id
            curr_parent_label = "Institution"
            
            dep_name = normalize(raw_dep)
            sub_name = normalize(raw_sub)
            
            # 2. Dependencia
            if dep_name and dep_name != "NO APLICA":
                key_dep = f"{inst_name} || {dep_name}"
                meta_dep = ror_matches.get(key_dep, {})
                dep_ror = meta_dep.get('matched_ror')
                dep_uid = dep_ror if dep_ror else f"dep:{dep_name}@{ror_id}"
                
                session.run(f"""
                    MATCH (p:{curr_parent_label} {{id: $p_id}})
                    MERGE (d:Dependency {{id: $id}})
                    SET d.name = $name, d.ror = coalesce(d.ror, $ror), d.openalex_id = coalesce(d.openalex_id, $oa)
                    MERGE (d)-[:PART_OF]->(p)
                """, id=dep_uid, name=dep_name, ror=dep_ror, 
                   oa=meta_dep.get('matched_openalex_id'), p_id=curr_parent_id)
                
                curr_parent_id = dep_uid
                curr_parent_label = "Dependency"
            
            # 3. Subdependencia
            if sub_name and sub_name != "NO APLICA" and sub_name != dep_name:
                key_sub = f"{inst_name} || {sub_name}"
                meta_sub = ror_matches.get(key_sub, {})
                sub_ror = meta_sub.get('matched_ror')
                sub_uid = sub_ror if sub_ror else f"subdep:{sub_name}@{curr_parent_id}"
                
                session.run(f"""
                    MATCH (p:{curr_parent_label} {{id: $p_id}})
                    MERGE (s:Subdependency {{id: $id}})
                    SET s.name = $name, s.ror = coalesce(s.ror, $ror), s.openalex_id = coalesce(s.openalex_id, $oa)
                    MERGE (s)-[:PART_OF]->(p)
                """, id=sub_uid, name=sub_name, ror=sub_ror,
                   oa=meta_sub.get('matched_openalex_id'), p_id=curr_parent_id)
                
                curr_parent_id = sub_uid
                curr_parent_label = "Subdependency"

            # 4. Vincular Académicos
            ent_final = normalize(group['ENTIDAD_FINAL'].iloc[0]) or ""
            
            for _, row in group.iterrows():
                cvu = str(row['CVU']).strip() if pd.notna(row['CVU']) else None
                name = str(row['NOMBRE']).strip()
                
                # Vinculación robusta: CVU > Nombre
                if cvu:
                    session.run(f"""
                        MATCH (target:{curr_parent_label} {{id: $target_id}})
                        MERGE (a:Academic {{cvu: $cvu}})
                        ON CREATE SET a.name = $name
                        SET a.entidad_final = $ent_final
                        MERGE (a)-[:AFFILIATED_TO]->(target)
                    """, target_id=curr_parent_id, cvu=cvu, name=name, ent_final=ent_final)
                else:
                    session.run(f"""
                        MATCH (target:{curr_parent_label} {{id: $target_id}})
                        MATCH (a:Academic {{name: $name}})
                        SET a.entidad_final = $ent_final
                        MERGE (a)-[:AFFILIATED_TO]->(target)
                    """, target_id=curr_parent_id, name=name, ent_final=ent_final)

            if i % 100 == 0:
                print(f"   Procesados {i}/{total} grupos...", end='\r')

    print(f"\n   ✅ Estructura jerárquica actualizada.")

    print("\n🧬 Fase 4: Sincronizando metadatos LLM...")
    with gs.driver.session() as session:
        updated = 0
        for m in academic_matches:
            name = m.get('snii_author')
            cvu = m.get('snii_cvu')
            oa_id = m.get('matched_openalex_id')
            if not oa_id: continue
            
            if cvu:
                session.run("""
                    MATCH (a:Academic {cvu: $cvu})
                    SET a.openalex_id = $oa_id, a.orcid = $orcid, a.is_snii = true, a.name = $name
                """, cvu=cvu, name=name, oa_id=oa_id, orcid=m.get('matched_orcid'))
            else:
                session.run("""
                    MATCH (a:Academic {name: $name})
                    SET a.openalex_id = $oa_id, a.orcid = $orcid, a.is_snii = true
                """, name=name, oa_id=oa_id, orcid=m.get('matched_orcid'))
            updated += 1
        print(f"   ✅ {updated} académicos sincronizados con metadatos de auditoría.")

    print("\n✨ Proceso de reconstrucción jerárquica finalizado.")

if __name__ == "__main__":
    rebuild()

if __name__ == "__main__":
    rebuild()
