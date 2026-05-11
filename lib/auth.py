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
                st.session_state.authenticated_user = {
                    "orcid": token_data.get("orcid"),
                    "name": token_data.get("name"),
                    "access_token": token_data.get("access_token")
                }
                # Limpiar el código de la URL para evitar re-procesamiento
                st.query_params.clear()
                st.rerun()
