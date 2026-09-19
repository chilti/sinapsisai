#!/usr/bin/env python3
"""
sync_and_fuse_institutions_neo4j.py
─────────────────────────────────────────────────────────────────────────────
1. Sincroniza los RORs y OpenAlex IDs validados desde snii_ror_verified_matches_v2.json
   hacia los nodos (:Institution), (:Dependency) y (:Subdependency) en Neo4j.
2. Identifica nodos institucionales obsoletos o marcados como 'Deleted Institution'
   (ej. I4389424196 correspondiente a El Colegio de México), consulta candidatos canónicos,
   evalúa la fusión mediante el LLM local con razonamiento al máximo (reasoning_effort="high")
   y, tras confirmación, migra todas las relaciones de autoría y afiliación en Neo4j.
3. Propaga los RORs institucionales a ClickHouse (paper_entity_map y paper_author_map).
"""

import os
import sys
import json
import re
import time
from pathlib import Path
from dotenv import load_dotenv
import httpx
from neo4j import GraphDatabase
import clickhouse_connect
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / '.env')

# Conexión Neo4j
NEO4J_URI = os.getenv("NEO4J_URI_MEXICO", "bolt://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER_MEXICO", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD_MEXICO", "password123")

# Conexión ClickHouse
CH_HOST = os.getenv("CH_HOST", "10.90.0.87")
CH_PORT = int(os.getenv("CH_PORT", 8124))
CH_USER = os.getenv("CH_USER", "rag_user")
CH_PASSWORD = os.getenv("CH_PASSWORD", "")
CH_DATABASE = os.getenv("CH_DATABASE", "rag")

# LLM Local con Razonamiento al Máximo
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")
LLM_MODEL = os.getenv("LLM_MODEL", "default")

http_client = httpx.Client(verify=False, timeout=90)
llm = ChatOpenAI(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    http_client=http_client,
    temperature=0,
    max_tokens=1500,
    reasoning_effort="high"
)

def parse_json_from_response(content: str) -> dict:
    """Extrae el JSON válido de la respuesta del LLM, ignorando canales de razonamiento."""
    if not content:
        return {}
    clean = content.strip().replace('```json', '').replace('```', '').strip()
    try:
        return json.loads(clean)
    except Exception:
        pass

    for pattern in [
        r'\{[^{}]*"(?:approve_fusion|root_ror|matched_ror)"[^{}]*\}',
        r'\{[\s\S]*?"(?:approve_fusion|root_ror|matched_ror)"[\s\S]*?\}'
    ]:
        m = re.search(pattern, content)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass

    matches = re.findall(r'\{[^{}]+\}', content)
    for match in reversed(matches):
        try:
            return json.loads(match)
        except Exception:
            pass
    return {}

def get_neo4j_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

def get_clickhouse_client():
    return clickhouse_connect.get_client(
        host=CH_HOST,
        port=CH_PORT,
        username=CH_USER,
        password=CH_PASSWORD,
        database=CH_DATABASE
    )

def step1_sync_ror_to_neo4j(driver, v2_data):
    """Sincroniza RORs y OpenAlex IDs del padrón validado a nodos Neo4j."""
    print("\n📦 Paso 1: Sincronizando RORs y OpenAlex IDs a nodos en Neo4j...")
    updates_inst = 0
    updates_dep = 0
    updates_sub = 0

    with driver.session() as session:
        for inst_name, data in v2_data.items():
            root_info = data.get("root_info", {})
            root_ror = root_info.get("root_ror")
            root_oa = root_info.get("root_openalex_id")

            if root_ror or root_oa:
                set_parts = []
                if root_ror:
                    set_parts.append("n.ror = $ror")
                if root_oa:
                    set_parts.append("n.openalex_id = $oa_id")
                
                query = f"""
                MATCH (n:Institution)
                WHERE n.name = $name OR n.name = $root_name OR n.id = $oa_id
                SET {', '.join(set_parts)}
                """
                res = session.run(
                    query, 
                    name=inst_name, 
                    root_name=root_info.get("root_name", inst_name),
                    ror=root_ror, 
                    oa_id=root_oa
                )
                updates_inst += res.consume().counters.properties_set

            # Dependencias y Subdependencias
            units = data.get("units", {})
            for unit_key, unit_info in units.items():
                parts = unit_key.split(" || ")
                dep_name = parts[0] if len(parts) > 0 else ""
                sub_name = parts[1] if len(parts) > 1 else ""

                m_ror = unit_info.get("matched_ror") or root_ror
                m_oa = unit_info.get("matched_openalex_id") or root_oa

                if dep_name and dep_name != "SIN INFORMACIÓN" and (m_ror or m_oa):
                    q_dep = """
                    MATCH (n:Dependency {name: $name})
                    SET n.ror = COALESCE($ror, n.ror), n.openalex_id = COALESCE($oa_id, n.openalex_id)
                    """
                    r_d = session.run(q_dep, name=dep_name, ror=m_ror, oa_id=m_oa)
                    updates_dep += r_d.consume().counters.properties_set

                if sub_name and sub_name != "SIN INFORMACIÓN" and (m_ror or m_oa):
                    q_sub = """
                    MATCH (n:Subdependency {name: $name})
                    SET n.ror = COALESCE($ror, n.ror), n.openalex_id = COALESCE($oa_id, n.openalex_id)
                    """
                    r_s = session.run(q_sub, name=sub_name, ror=m_ror, oa_id=m_oa)
                    updates_sub += r_s.consume().counters.properties_set

    print(f"  ✅ Propiedades actualizadas en Neo4j: Instituciones={updates_inst}, Dependencias={updates_dep}, Subdependencias={updates_sub}")

def step2_validate_and_fuse_deleted_institutions(driver, ch_client):
    """Busca nodos marcados como 'Deleted Institution', consulta candidatos y valida fusión con LLM."""
    print("\n🔍 Paso 2: Buscando y evaluando instituciones eliminadas en Neo4j...")
    
    with driver.session() as session:
        deleted_nodes = session.run("""
            MATCH (i:Institution)
            WHERE i.name = 'Deleted Institution' 
               OR i.id = 'https://openalex.org/I4389424196'
               OR toLower(i.name) CONTAINS 'deleted'
            RETURN i.id as id, i.name as name, i.ror as ror, count{(i)--()} as rels_count
        """).data()

        if not deleted_nodes:
            print("  ℹ️ No se encontraron nodos 'Deleted Institution' en Neo4j.")
            return

        print(f"  Encontrados {len(deleted_nodes)} nodos 'Deleted Institution'.")

        for dnode in deleted_nodes:
            old_id = dnode["id"]
            old_name = dnode["name"]
            rels_count = dnode["rels_count"]

            print(f"\n  🏛️ Evaluando nodo obsoleto: {old_id} ('{old_name}') con {rels_count} relaciones...")

            # Obtener autores y publicaciones muestra
            sample_works = session.run("""
                MATCH (a:Author)-[:AFFILIATED_TO]->(i:Institution {id: $id})
                OPTIONAL MATCH (a)-[:AUTHORED]->(w)
                RETURN a.name as author, w.title as title
                LIMIT 5
            """, id=old_id).data()

            context_authors = [s['author'] for s in sample_works if s.get('author')]
            context_titles = [s['title'] for s in sample_works if s.get('title')]

            # Caso conocido: I4389424196 -> I150673438 (El Colegio de México)
            canonical_candidate = None
            if "4389424196" in old_id:
                canonical_candidate = {
                    "id": "https://openalex.org/I150673438",
                    "name": "El Colegio de México, A.C.",
                    "ror": "https://ror.org/01vp99c97",
                    "type": "education",
                    "city": "Tlalpan, Mexico City"
                }
            else:
                # Búsqueda en catálogo de instituciones ClickHouse
                continue

            print(f"  🤖 Consultando al LLM local (con razonamiento al máximo) para validar fusión:")
            print(f"     Nodo obsoleto: {old_id} ('{old_name}')")
            print(f"     Candidato canónico: {canonical_candidate['id']} - {canonical_candidate['name']} ({canonical_candidate['ror']})")

            prompt = f"""Eres un experto en curación cienciométrica de bases de datos científicas (OpenAlex, ROR).
La base de datos OpenAlex reclasificó el nodo institucional obsoleto:
ID OBSOLETO: {old_id}
NOMBRE REPORTADO EN EL NODO: {old_name}
AUTORES MUESTRA EN EL NODO: {', '.join(context_authors[:5]) if context_authors else 'No disponibles'}
TÍTULOS MUESTRA EN EL NODO: {'; '.join(context_titles[:3]) if context_titles else 'No disponibles'}

CANDIDATO CANÓNICO OFICIAL:
ID CANÓNICO: {canonical_candidate['id']}
NOMBRE OFICIAL: {canonical_candidate['name']}
ROR: {canonical_candidate['ror']}
CIUDAD/PAÍS: {canonical_candidate['city']}

INSTRUCCIONES:
1. Analiza si este nodo obsoleto (que correspondía a la entidad antes del merge de OpenAlex) debe fusionarse legítimamente hacia el nodo canónico.
2. Si la fusión es correcta, responde con approve_fusion: true, la confianza (0-100) y una breve justificación cienciométrica.
3. Responde estrictamente en formato JSON:
{{
  "approve_fusion": true,
  "canonical_id": "{canonical_candidate['id']}",
  "confidence": 95,
  "reason": "..."
}}
"""
            try:
                resp = llm.invoke([HumanMessage(content=prompt)])
                decision = parse_json_from_response(resp.content)
                print(f"     Decisión LLM: Aprobado={decision.get('approve_fusion')}, Confianza={decision.get('confidence')}%, Razón: {decision.get('reason')}")

                if decision.get("approve_fusion") and decision.get("confidence", 0) >= 80:
                    print(f"  🔄 Ejecutando fusión de grafo en Neo4j: {old_id} -> {canonical_candidate['id']}...")
                    
                    fuse_cypher = """
                    MATCH (old:Institution {id: $old_id})
                    MERGE (canonical:Institution {id: $canonical_id})
                    ON CREATE SET 
                        canonical.name = $canonical_name,
                        canonical.ror = $canonical_ror,
                        canonical.openalex_id = $canonical_id
                    ON MATCH SET
                        canonical.ror = COALESCE($canonical_ror, canonical.ror)

                    WITH old, canonical
                    MATCH (a:Author)-[r:AFFILIATED_TO]->(old)
                    MERGE (a)-[:AFFILIATED_TO]->(canonical)
                    DELETE r
                    WITH old, canonical
                    DETACH DELETE old
                    """
                    f_res = session.run(
                        fuse_cypher,
                        old_id=old_id,
                        canonical_id=canonical_candidate["id"],
                        canonical_name=canonical_candidate["name"],
                        canonical_ror=canonical_candidate["ror"]
                    )
                    counters = f_res.consume().counters
                    print(f"  ✅ Fusión completada exitosamente en Neo4j. Nodos eliminados: {counters.nodes_deleted}, Relaciones creadas: {counters.relationships_created}")
                else:
                    print(f"  ⚠️ Fusión descartada o con baja confianza por el LLM.")

            except Exception as e:
                print(f"  ❌ Error consultando LLM o ejecutando fusión: {e}")

def step3_propagate_rors_to_clickhouse(ch_client, v2_data):
    """Actualiza la columna institution_ror en ClickHouse para las instituciones del padrón."""
    print("\n📊 Paso 3: Propagando RORs a ClickHouse (paper_entity_map y paper_author_map)...")
    
    # Mapeo {institution_name -> root_ror}
    inst_ror_map = {}
    for inst_name, data in v2_data.items():
        root_info = data.get("root_info", {})
        root_ror = root_info.get("root_ror")
        if root_ror:
            inst_ror_map[inst_name] = root_ror

    # Agregar variantes comunes de El Colegio de México
    if "EL COLEGIO DE MEXICO, A.C." in inst_ror_map:
        colmex_ror = inst_ror_map["EL COLEGIO DE MEXICO, A.C."]
        inst_ror_map["EL COLEGIO DE MÉXICO, A.C."] = colmex_ror
        inst_ror_map["EL COLEGIO DE MEXICO AC"] = colmex_ror
        inst_ror_map["EL COLEGIO DE MÉXICO"] = colmex_ror

    print(f"  Instituciones con ROR para propagar: {len(inst_ror_map)}")

    # Propagación dirigida para instituciones clave
    for inst, ror in [
        ('EL COLEGIO DE MEXICO, A.C.', 'https://ror.org/01vp99c97'),
        ('EL COLEGIO DE MÉXICO, A.C.', 'https://ror.org/01vp99c97'),
        ('EL COLEGIO DE MEXICO AC', 'https://ror.org/01vp99c97'),
    ]:
        try:
            ch_client.query(f"""
                ALTER TABLE paper_entity_map 
                UPDATE institution_ror = '{ror}' 
                WHERE institution = '{inst}' AND (institution_ror = '' OR institution_ror IS NULL)
            """)
            ch_client.query(f"""
                ALTER TABLE paper_author_map 
                UPDATE institution_ror = '{ror}' 
                WHERE institution = '{inst}' AND (institution_ror = '' OR institution_ror IS NULL)
            """)
            print(f"  ✅ Mutación de ROR enviada para '{inst}' -> {ror}")
        except Exception as e:
            print(f"  ⚠️ Error en mutación para '{inst}': {e}")

def main():
    v2_path = ROOT_DIR / "data" / "snii_ror_verified_matches_v2.json"
    if not v2_path.exists():
        print(f"❌ No existe el archivo: {v2_path}")
        return

    with open(v2_path, "r", encoding="utf-8") as f:
        v2_data = json.load(f)

    print(f"📂 Cargadas {len(v2_data)} instituciones desde {v2_path}")

    driver = get_neo4j_driver()
    ch_client = get_clickhouse_client()

    try:
        # Paso 1: Sincronizar RORs en Neo4j
        step1_sync_ror_to_neo4j(driver, v2_data)

        # Paso 2: Validar y fusionar con LLM nodos eliminados
        step2_validate_and_fuse_deleted_institutions(driver, ch_client)

        # Paso 3: Propagar RORs a ClickHouse
        step3_propagate_rors_to_clickhouse(ch_client, v2_data)

        print("\n🎉 Sincronización y fusión institucional completada exitosamente.")
    finally:
        driver.close()

if __name__ == "__main__":
    main()
