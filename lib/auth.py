import os
import requests
import urllib.parse
import streamlit as st

# Configuración de ORCID (Public API)
# Estas variables deben estar en el archivo .env
ORCID_CLIENT_ID = os.getenv("ORCID_CLIENT_ID")
ORCID_CLIENT_SECRET = os.getenv("ORCID_CLIENT_SECRET")
ORCID_REDIRECT_URI = os.getenv("ORCID_REDIRECT_URI")

# Endpoints de ORCID
ORCID_AUTH_URL = "https://orcid.org/oauth/authorize"
ORCID_TOKEN_URL = "https://orcid.org/oauth/token"

def get_orcid_login_url():
    """Genera la URL de redireccionamiento para iniciar el flujo OAuth con ORCID."""
    if not ORCID_CLIENT_ID or not ORCID_REDIRECT_URI:
        return None
        
    params = {
        "client_id": ORCID_CLIENT_ID,
        "response_type": "code",
        "scope": "/authenticate",
        "redirect_uri": ORCID_REDIRECT_URI
    }
    return f"{ORCID_AUTH_URL}?{urllib.parse.urlencode(params)}"

def exchange_code_for_token(code):
    """Intercambia el código de autorización por un token de acceso y el ORCID ID del usuario."""
    if not code:
        return None
        
    payload = {
        "client_id": ORCID_CLIENT_ID,
        "client_secret": ORCID_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": ORCID_REDIRECT_URI
    }
    
    headers = {"Accept": "application/json"}
    
    try:
        response = requests.post(ORCID_TOKEN_URL, data=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error al autenticar con ORCID: {e}")
        return None

import threading

def check_orcid_exists_in_neo4j(orcid_input: str) -> bool:
    """Verifica si el ORCID ya cuenta con publicaciones o registro en Neo4j."""
    if not orcid_input:
        return False
    orcid_id = str(orcid_input).rstrip('/').split('/')[-1]
    orcid_url = f"https://orcid.org/{orcid_id}"
    try:
        from database.knowledge_graph import Neo4jGraphStore
        graph_store = Neo4jGraphStore()
        query = "MATCH (a:Author) WHERE a.orcid = $orcid MATCH (a)-[:AUTHORED]->(w:Work) RETURN count(w) AS cnt"
        with graph_store.driver.session() as s:
            res = s.run(query, orcid=orcid_url)
            rec = res.single()
            graph_store.close()
            return (rec["cnt"] > 0) if rec else False
    except Exception as e:
        print(f"[WARN] Error verificando existencia de ORCID {orcid_input} en Neo4j: {e}")
        return False

def _run_sync_worker(orcid_input: str, user_name: str, force: bool):
    try:
        import subprocess
        from SNII.ingest_snii_apis import ingest_researcher_data
        orcid_id = str(orcid_input).rstrip('/').split('/')[-1]
        orcid_url = f"https://orcid.org/{orcid_id}"
        
        author_name = user_name or f"INVESTIGADOR_ORCID_{orcid_id}"
        data = {
            'snii_author': author_name,
            'matched_orcid': orcid_url,
            'match': True,
            'confidence': 'HIGH'
        }
        print(f"🚀 [Background Sync] Iniciando ingesta de publicaciones para {author_name} ({orcid_url})...")
        ingest_researcher_data(data, force=force, save_to_ch=True)
        
        # Regenerar parquets de métricas para el dashboard
        print(f"📊 [Background Sync] Regenerando archivos Parquet de caché para {author_name}...")
        base_dir = os.path.dirname(os.path.dirname(__file__))
        cmd = [sys.executable, "ingestion/compute_scholar_metrics_ch.py", "--academic", author_name]
        subprocess.run(cmd, cwd=base_dir, capture_output=True, text=True)
        
        print(f"✅ [Background Sync] Ingesta y actualización de Parquets completada con éxito para {author_name} ({orcid_url}).")
    except Exception as e:
        print(f"❌ [Background Sync] Error en ingesta para ORCID {orcid_input}: {e}")

def trigger_background_sync(orcid_input: str, user_name: str = "", force: bool = False):
    """Encola e inicia la sincronización de publicaciones en segundo plano mediante un hilo."""
    if not orcid_input:
        return
    t = threading.Thread(target=_run_sync_worker, args=(orcid_input, user_name, force), daemon=True)
    t.start()

def init_auth_session():
    """Inicializa las variables de estado de sesión para autenticación."""
    if "authenticated_user" not in st.session_state:
        st.session_state.authenticated_user = None

def handle_orcid_callback():
    """
    Procesa el callback de ORCID si detecta el parámetro 'code' en la URL.
    Debe llamarse al inicio del script de Streamlit.
    """
    query_params = st.query_params
    if "code" in query_params:
        code = query_params["code"]
        # Evitar procesar el mismo código varias veces si se refresca la página
        if not st.session_state.authenticated_user:
            token_data = exchange_code_for_token(code)
            if token_data:
                orcid_val = token_data.get("orcid")
                name_val = token_data.get("name") or ""
                
                st.session_state.authenticated_user = {
                    "orcid": orcid_val,
                    "name": name_val,
                    "access_token": token_data.get("access_token")
                }

                # Autodetección: Si el ORCID es NUEVO en el sistema, disparar sincronización inicial
                if orcid_val and not check_orcid_exists_in_neo4j(orcid_val):
                    print(f"✨ [Nuevo Registro ORCID] {orcid_val} no registrado previamente. Disparando ingesta en segundo plano...")
                    trigger_background_sync(orcid_val, name_val, force=True)

                # Limpiar el código de la URL para evitar re-procesamiento
                st.query_params.clear()
                st.rerun()
