import streamlit as st
import streamlit.components.v1 as components
import os

def render_coauthra(author_id=None, height=900):
    """
    Renderiza la aplicación CoAuthra dentro de Sinapsis AI.
    
    Args:
        author_id (str, optional): OpenAlex ID del investigador (ej: A5012345678). 
                                   Si se proporciona, se intentará cargar su red automáticamente.
        height (int): Altura del componente en píxeles. default 900.
    """
    
    # --- Estilo y Atribución ---
    st.markdown("""
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #002B5C; margin-bottom: 20px;">
            <h4 style="margin: 0; color: #002B5C;">🕸️ Red de Colaboración Científica</h4>
            <p style="margin: 10px 0; font-size: 14px; color: #475569;">
                Esta visualización interactiva es proporcionada por <b>CoAuthra</b>.
                Sinapsis AI integra esta herramienta para potenciar el análisis de grafos de colaboración en la UNAM.
            </p>
            <p style="margin: 0; font-size: 12px; color: #64748b;">
                Tecnología original desarrollada por <b>Joe Barnier</b>. 
                Licencia: <a href="https://creativecommons.org/licenses/by-nc-nd/4.0/" target="_blank">CC BY-NC-ND 4.0</a>. 
                Sitio oficial: <a href="https://coauthra.com" target="_blank">coauthra.com</a>
            </p>
        </div>
    """, unsafe_allow_html=True)

    # --- Cargar HTML Local ---
    static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "coauthra.html")
    
    if not os.path.exists(static_path):
        st.error(f"Error: No se encontró el archivo de CoAuthra en `{static_path}`")
        return

    try:
        with open(static_path, "r", encoding="utf-8") as f:
            html_content = f.read()
            
        # --- PARCHE DE COMPATIBILIDAD (EN MEMORIA) ---
        # Resolvemos el error de SecurityError: replaceState en iframes sin tocar el archivo en disco
        # Respetando la licencia ND (No Derivadas) al no distribuir una versión modificada del archivo.
        html_content = html_content.replace(
            "history.replaceState(null,'',`?author=${aid}`);",
            "try { history.replaceState(null,'',`?author=${aid}`); } catch(e) { console.warn('History API blocked in iframe'); }"
        )

        # --- Inyección de búsqueda automática (Deep Link) ---
        if author_id:
            # Extraer solo el ID si viene como URI completa
            clean_id = author_id.replace("https://openalex.org/", "")
            
            # Script para inyectar la carga automática (Deep Link mejorado)
            injection_script = f"""
            <script>
                window.addEventListener('load', function() {{
                    const checkState = setInterval(() => {{
                        if (typeof loadAuthor === 'function' && typeof doSearch === 'function') {{
                            const authorId = '{clean_id}';
                            // Si detectamos un OpenAlex ID (empieza con A seguido de números)
                            if (authorId.startsWith('A') && /^[A-Z]?\\d+/.test(authorId)) {{
                                console.log('Sinapsis AI: Detectado OpenAlex ID. Cargando directamente.');
                                loadAuthor({{ 
                                    id: 'https://openalex.org/' + authorId, 
                                    display_name: 'Investigador (ID: ' + authorId + ')' 
                                }});
                            }} else {{
                                // Fallback para ORCID o nombres (usa el buscador interno)
                                console.log('Sinapsis AI: Usando buscador de CoAuthra.');
                                document.getElementById('qinput').value = authorId;
                                setMode('orcid'); 
                                doSearch();
                            }}
                            clearInterval(checkState);
                        }}
                    }}, 500);
                }});
            </script>
            """
            html_content = html_content.replace("</body>", f"{injection_script}</body>")

        # --- Renderizar componente ---
        components.html(html_content, height=height, scrolling=True)
        
    except Exception as e:
        st.error(f"Error al cargar la integración de CoAuthra: {e}")
