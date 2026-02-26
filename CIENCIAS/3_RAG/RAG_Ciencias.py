import streamlit as st
import requests
import json
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import random
from captcha.image import ImageCaptcha
import string

# --- Configuración de la Conexión a los Microservicios OpenAlex, Web Search y Wikipedia---
MICROSERVICES_BASE_URL = "http://127.0.0.1:8001/tools"
MICROSERVICES_MILVUS_BASE_URL = "http://localhost:8002/api/search/"

# --- Definición de Herramientas como Clientes de API de la base de datos vectorial ---


@tool
def buscar_articulos_cientificos_milvus(query: str, field: str, top_k: int=10) -> str:
    """
    Útil para buscar artículos científicos, investigaciones o papers en una base de datos local
    sobre temas específicos de ciencia y tecnología. La entrada debe ser el tema o
    la pregunta de investigación.
    """
    print(f"🕵️‍♂️ Buscando artículos con la consulta: '{query}'...")
    
    # URL del microservicio de búsqueda. Usamos el campo 'abstract' por ser el más general.
    url = MICROSERVICES_MILVUS_BASE_URL+"title"
    match field:
        case 'title':
            url = MICROSERVICES_MILVUS_BASE_URL+"title"
        case 'abstract':
            url = MICROSERVICES_MILVUS_BASE_URL+"abstract"
        case 'authors':
            url = MICROSERVICES_MILVUS_BASE_URL+"authors"
        case 'research_area':
            url = MICROSERVICES_MILVUS_BASE_URL+"research_area"
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "query": query,
        "top_k": top_k 
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Lanza un error si la respuesta no es 200 OK
        
        results = response.json().get("results", [])
        
        if not results:
            return "No se encontraron artículos para esa consulta."       
            
        return results

    except requests.exceptions.RequestException as e:
        return f"Error al contactar el servicio de búsqueda: {e}"

# --- NUEVA HERRAMIENTA 2: Búsqueda por Autor ---
@tool
def buscar_articulos_por_autor_basevectorialMilvus(author_name: str, top_k: int=10) -> str:
    """
    Útil para buscar artículos científicos cuando se conoce el NOMBRE de uno o varios AUTORES.
    La entrada debe ser el nombre completo o los apellidos de los autores que se desean buscar.
    """
    print(f"👤 Buscando por AUTOR con el nombre: '{author_name}'...")
    url = "http://127.0.0.1:8002/api/author/search"
    headers = {"Content-Type": "application/json" }
    # Para la búsqueda de autores, el operador AND es el más común y preciso
    payload = {
        "author_name": author_name,
        "operator": "AND",
        "top_k": top_k
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        results = response.json().get("results", [])

        if not results:
            return "No se encontraron artículos para el autor especificado."    

        formatted_output = f"Se encontraron los siguientes artículos del autor '{author_name}':\n"
        for i, res in enumerate(results):
            # El formato de respuesta de 'query' es un poco diferente
            metadata = res.get("metadata", {})
            title = metadata.get("row_data", {}).get("Article Title", "N/A")
            authors = metadata.get("authors", "N/A")
            formatted_output += f"{i+1}. Título: {title}\n   Autores: {authors}\n\n"
        return formatted_output
    except requests.exceptions.RequestException as e:
        return f"Error al contactar el servicio de búsqueda de autor: {e}"



 ### --- DEFINICIÓN DE HERRAMIENTAS COMO CLIENTES DE API ---
# Cada función @tool corresponde a un endpoint del microservicio.
# Las descripciones (docstrings) son VITALES para que el agente sepa cuándo usar cada herramienta.

# --- CONFIGURACIÓN ---
# Asegúrate de que esta URL coincida con la dirección donde corre tu servidor de microservicios.
MICROSERVICES_BASE_URL = "http://127.0.0.1:8001/tools"

@tool
def searchAuthorByName(fullname: str) -> str:
    """Busca perfiles de autor en OpenAlex por su nombre completo. Devuelve hasta 3 coincidencias con sus IDs, que pueden ser usados en otras herramientas."""
    try:
        response = requests.get(f"{MICROSERVICES_BASE_URL}/recover_author_from_openalex", params={"fullname": fullname})
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)
    except requests.exceptions.RequestException as e:
        return f"Error de red al buscar autor: {e}"


@tool
def getAuthorWorksCountByYear(author_id: str) -> str:
    """Obtiene la producción científica anual de un autor (número de trabajos por año). Requiere el ID de OpenAlex del autor."""
    try:
        response = requests.get(f"{MICROSERVICES_BASE_URL}/get_author_works_by_year", params={"author_id": author_id})
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)
    except requests.exceptions.RequestException as e:
        return f"Error de red al obtener producción anual de autor: {e}"



@tool
def findAuthorWorks(author_id: str='A5043129140', n: int = 10, sort_by: str = "recency") -> str:
    """Obtiene trabajos de un autor con ordenamiento flexible: recency o citations. Requiere el ID de OpenAlex del autor."""
    try:
        params = {"author_id": author_id, "n": n, "sort_by": sort_by}
        response = requests.get(f"{MICROSERVICES_BASE_URL}/findAuthorWorks", params=params)
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)
    except requests.exceptions.RequestException as e:
        return f"Error de red al obtener los trabajos más citados: {e}"

@tool
def getWorkByDOI(doi: str) -> str:
    """Recupera la información completa de un trabajo científico usando su DOI (Digital Object Identifier)."""
    try:
        response = requests.get(f"{MICROSERVICES_BASE_URL}/recover_from_openalex", params={"doi": doi})
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)
    except requests.exceptions.RequestException as e:
        return f"Error de red al buscar por DOI: {e}"

@tool
def searchInstitutionByName(name: str) -> str:
    """Busca perfiles de instituciones (universidades, centros de investigación) por nombre. Devuelve IDs que pueden ser usados en otras herramientas."""
    try:
        response = requests.get(f"{MICROSERVICES_BASE_URL}/search_institution", params={"name": name})
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)
    except requests.exceptions.RequestException as e:
        return f"Error de red al buscar institución: {e}"

@tool
def getInstitutionWorksByYear(institution_id: str) -> str:
    """Obtiene la producción científica anual de una institución (número de trabajos por año). Requiere el ID de OpenAlex o ROR de la institución."""
    try:
        response = requests.get(f"{MICROSERVICES_BASE_URL}/get_institution_works_by_year", params={"institution_id": institution_id})
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)
    except requests.exceptions.RequestException as e:
        return f"Error de red al obtener producción anual de institución: {e}"

@tool
def searchSourceByName(name: str) -> str:
    """Busca una fuente de publicación (revista, congreso) por su nombre para obtener su información y su ID."""
    try:
        response = requests.get(f"{MICROSERVICES_BASE_URL}/search_source", params={"name": name})
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)
    except requests.exceptions.RequestException as e:
        return f"Error de red al buscar fuente: {e}"

@tool
def searchConceptByTopic(topic: str) -> str:
    """Explora un concepto o área temática (ej. 'machine learning') para ver su descripción, nivel y conceptos relacionados."""
    try:
        response = requests.get(f"{MICROSERVICES_BASE_URL}/search_concept", params={"topic": topic})
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)
    except requests.exceptions.RequestException as e:
        return f"Error de red al buscar concepto: {e}"

@tool
def webSearch(query: str) -> str:
    """Útil para buscar información general, actual o no académica en internet."""
    try:
        response = requests.get(f"{MICROSERVICES_BASE_URL}/web_search", params={"query": query})
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)
    except requests.exceptions.RequestException as e:
        return f"Error de red en la búsqueda web: {e}"

@tool
def wikipediaSearch(query: str) -> str:
    """Útil para obtener definiciones y resúmenes concisos sobre temas bien establecidos desde Wikipedia."""
    try:
        response = requests.get(f"{MICROSERVICES_BASE_URL}/wikipedia_search", params={"query": query})
        response.raise_for_status()
        return json.dumps(response.json(), ensure_ascii=False)
    except requests.exceptions.RequestException as e:
        return f"Error de red en la búsqueda de Wikipedia: {e}"


# Lista de herramientas para el agente
tools = [
    buscar_articulos_cientificos_milvus,
    buscar_articulos_por_autor_basevectorialMilvus,
    searchAuthorByName,
    getAuthorWorksCountByYear,
    findAuthorWorks,
    getWorkByDOI,
    searchInstitutionByName,
    getInstitutionWorksByYear,
    searchSourceByName,
    searchConceptByTopic,
    webSearch,
    wikipediaSearch,
]

# --- El resto de tu aplicación Streamlit permanece prácticamente igual ---

# (Aquí va la lógica del captcha, que no necesita cambios)
session_id = random.randint(1,100)
length_captcha = 4
width = 200
height = 150

def captcha_control():
    if 'controllo' not in st.session_state or st.session_state['controllo'] == False:
        st.title("Control con captcha 🤗")
        st.session_state['controllo'] = False
        col1, col2 = st.columns(2)
        if 'Captcha' not in st.session_state:
                st.session_state['Captcha'] = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length_captcha))
        
        image = ImageCaptcha(width=width, height=height)
        data = image.generate(st.session_state['Captcha'])
        col1.image(data)
        capta2_text = col2.text_area('Ingresa la captcha', height=68)
        
        if st.button("Verificar el código"):
            capta2_text = capta2_text.replace(" ", "")
            if st.session_state['Captcha'].lower() == capta2_text.lower().strip():
                del st.session_state['Captcha']
                col1.empty()
                col2.empty()
                st.session_state['controllo'] = True
                st.rerun() 
            else:
                st.error("🚨 Error en la captcha")
                del st.session_state['Captcha']
                del st.session_state['controllo']
                st.rerun()
        else:
            st.stop()

if 'controllo' not in st.session_state or st.session_state['controllo'] == False:
    captcha_control()

# (Aquí va la lógica de la interfaz de Streamlit, que no necesita cambios)
st.header("Chat conversacional tipo RAG")

if st.button("Reiniciar sesión"):
    st.session_state.messages = [{"role": "assistant", "content": "Hola. Puede preguntarme por la producción científica de la Facultad de Ciencias de la UNAM."}]
    st.session_state.system_prompt = st.session_state.default_prompt
    st.rerun()

option_llm = "openai/gpt-oss-20b"
st.write("Modelo local seleccionado:", option_llm)

llm: ChatOpenAI = ChatOpenAI(
    model=option_llm,
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    temperature=0
)

@st.cache_resource
def generate_checkpointer():
    if 'checkpointer' not in st.session_state:
        st.session_state['checkpointer'] = MemorySaver()
    return st.session_state['checkpointer']

if 'default_prompt' not in st.session_state:
    st.session_state.default_prompt = """
Eres un asistente experto y eficiente. Tu objetivo es responder las preguntas del usuario de la manera más directa y con el menor número de pasos posible.

1.  **Primero, intenta responder usando tu conocimiento interno.** Solo si la información requerida es muy específica, en tiempo real o requiere una búsqueda en una base de datos, debes usar una herramienta.
2.  **Si debes usar una herramienta, elige la más específica para la tarea.** No uses una búsqueda web general si una herramienta de OpenAlex puede obtener la respuesta directamente.
3.  **Sé conciso.** Evita pasos innecesarios.

Tu especialidad es la producción científica de la Facultad de Ciencias de la UNAM. Prioriza la herramienta que recupera artículos de la Facultad de Ciencias de la UNAM. Si quieres completar el registro de los articulos, utiliza la información contenida en el campo metadata o bien utiliza la herramienta de búsqueda en openalex por doi. Si te preguntan por la producción de los departamentos, responde que no cuentas con datos desagregados a nivel departamento. Traduce las búsquedas al inglés a menos que se te indique que busques en español. Puedes utilizar las otras herramientas para afinar tus respuestas.
"""

if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = st.session_state.default_prompt
    
def actualizar_prompt():
    st.session_state.system_prompt = st.session_state.prompt_input
    
st.text_area(
    "Edita el prompt del sistema:",
    value=st.session_state.system_prompt,
    key='prompt_input', # Clave para referenciar este widget
    on_change=actualizar_prompt,
    height=400, max_chars=5000
)
def reset_prompt():
    st.session_state.system_prompt = st.session_state.default_prompt
    
st.button("Restablecer al prompt predeterminado", on_click=reset_prompt)

# Create a ChatPromptTemplate with a system message
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", st.session_state.system_prompt ),
        ("placeholder", "{messages}"), # This placeholder will be replaced by the conversation history
    ]
)


agent_executor = create_react_agent(llm, tools, checkpointer=generate_checkpointer(), prompt=prompt)

if "messages" not in st.session_state: 
    st.session_state.messages = [{"role": "assistant", "content": "Hola. Puede preguntarme sobre la producción científica de la Facultad de Ciencias de la UNAM."}]


results=''


messages = st.container()
for message in st.session_state.messages:
    messages.chat_message(message["role"]).markdown(message["content"], unsafe_allow_html=True)


if prompt_input := messages.chat_input("Pregunte sobre la producción científica de la Facultad de Ciencias"):
    st.session_state.messages.append({"role": "user", "content": prompt_input})
    messages.chat_message("user").markdown(prompt_input)
    config = {"configurable": {"thread_id": str(session_id)}}       
    with st.spinner("Pensando..."):
        results = agent_executor.invoke(
            {"messages": [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]},
            config=config
        )
    
    assistant_response = results['messages'][-1].content
    messages.chat_message("assistant").markdown(assistant_response)       

    st.session_state.messages.append({"role": "assistant", "content": assistant_response})
        
        
with st.expander("Ver cadena completa de acciones y mensajes"):
            st.write(results)



# (Aquí va el footer, que no necesita cambios)
st.markdown(
    """
    <style>
    .footer {
        position: fixed; left: 0; bottom: 0; width: 100%;
        background-color: #f9f9f9; text-align: center; padding: 10px;
        font-size: 14px; color: #555; border-top: 1px solid #ddd;
    }
    </style>
    <div class="footer">
        📊 Agente RAG de la Facultad de Ciencias - UNAM. Desarrollado por José Luis Jiménez Andrade.
        <br>
        Diseño: Humberto Carrillo Calvet, Ricardo Arencibia Jorge
    </div>
    """,
    unsafe_allow_html=True
)
