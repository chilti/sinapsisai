"""
rebuild_neo4j_hierarchy.py
==========================
Reconstruye la jerarquía de Neo4j usando las columnas de Acreditación del SNII 2025.
Lógica: Institución -> Dependencia -> Subdependencia.
Maneja casos de "SIN INSTITUCIÓN" y valores nulos/SIN INFORMACIÓN.
"""
import sys, os, json
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
NULL_VALUES = ['SIN INFORMACIÓN', 'NO APLICA', 'SIN INSTITUCION', 'nan', 'None', '']

def normalize(val):
    s = str(val).strip()
    if s.upper() in [v.upper() for v in NULL_VALUES] or not s:
        return None
    return s

def rebuild():
    gs = Neo4jGraphStore()
    
    print("🧹 Fase 1: Limpieza total de jerarquía antigua...")
    with gs.driver.session() as session:
        session.run("MATCH (n:Entity) DETACH DELETE n")
        session.run("MATCH (n:Institution) DETACH DELETE n")
        print("   ✅ Nodos Entity e Institution eliminados.")

    print("\n⛓️ Fase 2: Configurando nuevas restricciones...")
    with gs.driver.session() as session:
        try:
            # Eliminar cualquier restricción vieja que use el campo 'name'
            constraints = session.run("SHOW CONSTRAINTS").data()
            for c in constraints:
                props = c.get('properties', [])
                labels = c.get('labels_or_types', c.get('labelsOrTypes', [c.get('entityType', '')]))
                if ('Entity' in labels or 'Institution' in labels) and 'name' in props:
                    session.run(f"DROP CONSTRAINT {c['name']}")
                    print(f"   ✅ Restricción antigua {c['name']} eliminada.")
        except Exception as e:
            print(f"   ⚠️ Nota: No se pudo limpiar restricciones automáticamente: {e}")

        # Crear nuestras nuevas restricciones sobre el campo 'id'
        session.run("CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE")
        session.run("CREATE CONSTRAINT institution_id_unique IF NOT EXISTS FOR (i:Institution) REQUIRE i.id IS UNIQUE")
        print("   ✅ Restricciones de unicidad por ID configuradas.")

    print("\n📂 Fase 3: Cargando archivos...")
    
    # Cargar primero solo el header para mapear columnas dinámicamente
    header_df = pd.read_excel(EXCEL_PATH, sheet_name='4T_2025 (44,794)', nrows=0)
    original_cols = header_df.columns.tolist()
    
    # Mapeo de búsqueda (normalizado)
    target_map = {
        'NOMBRE': ['NOMBRE DEL INVESTIGADOR', 'NOMBRE'],
        'INSTITUCION': ['INSTITUCION DE ACREDITACION', 'INSTITUCIÓN DE ACREDITACIÓN'],
        'DEPENDENCIA': ['DEPENDENCIA DE ACREDITACION', 'DEPENDENCIA DE ACREDITACIÓN'],
        'SUBDEPENDENCIA': ['SUBDEPENDENCIA DE ACREDITACION', 'SUBDEPENDENCIA DE ACREDITACIÓN'],
        'ENTIDAD_FINAL': ['ENTIDAD FINAL']
    }
    
    actual_cols_to_read = []
    rename_dict = {}
    
    for canonical, variations in target_map.items():
        found = False
        for var in variations:
            # Buscar coincidencia exacta o normalizada
            for col in original_cols:
                if col.strip() == var or normalize(col).upper() == normalize(var).upper():
                    actual_cols_to_read.append(col)
                    rename_dict[col] = canonical
                    found = True
                    break
            if found: break
        if not found:
            print(f"⚠️ Advertencia: No se encontró columna para '{canonical}'")

    df_snii = pd.read_excel(EXCEL_PATH, usecols=actual_cols_to_read, sheet_name='4T_2025 (44,794)')
    df_snii = df_snii.rename(columns=rename_dict)
    
    with open(ACADEMIC_JSON, 'r', encoding='utf-8') as f:
        academic_matches = json.load(f)
    with open(ROR_JSON, 'r', encoding='utf-8') as f:
        ror_matches = json.load(f)
    # Pre-normalización de la jerarquía
    def normalize_hierarchy(row):
        inst = normalize(row['INSTITUCION']) or "SIN INSTITUCION"
        dep = normalize(row['DEPENDENCIA']) or "SIN INFORMACION"
        sub = normalize(row['SUBDEPENDENCIA']) or "SIN INFORMACION"
        
        # REGLA DE ORO: Si no hay institución, no hay sub-niveles
        if inst.upper() in ["SIN INSTITUCION", "SIN INSTITUCIN", "DESCONOCIDO", ""]:
            return "SIN INSTITUCION", "NO APLICA", "NO APLICA"
        
        # Normalizar SIN INFORMACION a NO APLICA si es necesario
        if dep.upper() in ["SIN INFORMACION", "SIN INFORMACIN", ""]:
            dep = "NO APLICA"
        if sub.upper() in ["SIN INFORMACION", "SIN INFORMACIN", ""]:
            sub = "NO APLICA"
            
        return inst, dep, sub

    print("\n🏗️ Fase 3: Reconstruyendo Jerarquía y Vinculando Académicos...")
    
    # Aplicar normalización a las columnas antes del groupby
    df_snii[['INSTITUCION', 'DEPENDENCIA', 'SUBDEPENDENCIA']] = df_snii.apply(
        lambda x: pd.Series(normalize_hierarchy(x)), axis=1
    )

    # Agrupamos para procesar por jerarquías únicas
    groups = df_snii.groupby([
        'INSTITUCION', 
        'DEPENDENCIA', 
        'SUBDEPENDENCIA'
    ], dropna=False)

    with gs.driver.session() as session:
        total = len(groups)
        for i, (hierarchy, group) in enumerate(groups, 1):
            raw_inst, raw_dep, raw_sub = hierarchy
            
            # 1. Normalizar Institución
            inst_name = normalize(raw_inst) or "SIN INSTITUCION"
            
            # Obtener ROR del JSON si existe
            ror_key = f"{inst_name} || SIN INFORMACIÓN"
            meta = ror_matches.get(ror_key, {})
            ror_id = meta.get('parent_ror') or f"manual:{inst_name}"
            
            # Crear Institución
            session.run("""
                MERGE (i:Institution {id: $id})
                SET i.name = $name, i.ror = $ror
            """, id=ror_id, name=inst_name, ror=meta.get('parent_ror'))

            # 2. Construir cadena de Entidades
            curr_parent_id = ror_id
            curr_parent_label = "Institution"
            
            dep_name = normalize(raw_dep)
            sub_name = normalize(raw_sub)
            
            # Nivel Dependencia
            if dep_name:
                dep_id = f"dep:{dep_name}@{ror_id}"
                session.run(f"""
                    MATCH (p:{curr_parent_label} {{id: $p_id}})
                    MERGE (e:Entity {{id: $uid}})
                    SET e.name = $name, e.type = 'Dependencia'
                    MERGE (e)-[:PART_OF]->(p)
                """, p_id=curr_parent_id, uid=dep_id, name=dep_name)
                curr_parent_id = dep_id
                curr_parent_label = "Entity"

            # Nivel Subdependencia
            if sub_name:
                sub_id = f"subdep:{sub_name}@{curr_parent_id}" # único respecto a su padre
                session.run(f"""
                    MATCH (p:{curr_parent_label} {{id: $p_id}})
                    MERGE (e:Entity {{id: $uid}})
                    SET e.name = $name, e.type = 'Subdependencia'
                    MERGE (e)-[:PART_OF]->(p)
                """, p_id=curr_parent_id, uid=sub_id, name=sub_name)
                curr_parent_id = sub_id
                curr_parent_label = "Entity"

            # 3. Vincular Académicos y guardar su Entidad Final
            # Tomamos la entidad final del primer registro del grupo (es la misma para todos en este grupo)
            ent_final = normalize(group['ENTIDAD_FINAL'].iloc[0]) or ""
            academic_names = group['NOMBRE'].tolist()
            
            session.run(f"""
                MATCH (target:{curr_parent_label} {{id: $target_id}})
                MATCH (a:Academic)
                WHERE a.name IN $names
                SET a.entidad_final = $ent_final
                MERGE (a)-[:AFFILIATED_TO]->(target)
            """, target_id=curr_parent_id, names=academic_names, ent_final=ent_final)

            if i % 100 == 0:
                print(f"   Procesados {i}/{total} grupos...", end='\r')

    print(f"\n   ✅ {total} combinaciones de jerarquía procesadas.")

    print("\n🧬 Fase 4: Sincronizando IDs de OpenAlex verificados...")
    with gs.driver.session() as session:
        updated = 0
        for m in academic_matches:
            name = m.get('snii_author')
            oa_id = m.get('matched_openalex_id')
            if not oa_id: continue
            
            session.run("""
                MATCH (a:Academic {name: $name})
                SET a.openalex_id = $oa_id, a.orcid = $orcid, a.is_snii = true
            """, name=name, oa_id=oa_id, orcid=m.get('matched_orcid'))
            updated += 1
        print(f"   ✅ {updated} académicos actualizados con meta LLM.")

    print("\n✨ Proceso finalizado con éxito.")

if __name__ == "__main__":
    rebuild()
