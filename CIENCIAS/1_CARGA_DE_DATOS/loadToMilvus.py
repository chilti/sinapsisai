import pandas as pd
import time
import json # <--- 1. Importar la librería JSON
import pyalex
from pyalex import Works
from pymilvus import connections, utility, FieldSchema, CollectionSchema, DataType, Collection
import openai
import pandas as pd
from pymilvus import Collection
from unidecode import unidecode


# --- Configuración Inicial (sin cambios) ---
pyalex.config.email = "jlja@ciencias.unam.mx"
MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"
COLLECTION_NAME = "Ciencias_08_25_InCitesRecords_Milvus_JSON_COS" # Nuevo nombre para la colección
EXCEL_FILENAME = 'wosDocsCiencias08-25.xlsx'
EMBEDDING_DIM = 768

# 1. Configura el cliente de OpenAI para que apunte a tu LM Studio
client = openai.OpenAI(
    base_url="http://localhost:1234/v1",  # La URL de tu servidor local
    api_key="not-needed"                  # LM Studio no requiere una API key
)

# 2. Crea una función para obtener los embeddings
def get_embedding(text: str, model: str = "paraphrase-multilingual-mpnet-base-v2"):
    """Obtiene el embedding de un texto usando el servidor de LM Studio."""
    # LM Studio ignora el nombre del modelo, pero el parámetro es requerido por la API
    response = client.embeddings.create(model=model, input=[text])
    return response.data[0].embedding
       
    
# --- Funciones Auxiliares de OpenAlex (sin cambios) ---
def undo_index(rev_index):
    if not rev_index: return ""
    word_index = []
    for word, v in rev_index.items():
        for word_position in v: word_index.append([word, word_position])
    word_index = sorted(word_index, key=lambda x: x[1])
    return " ".join([word[0] for word in word_index])

def get_abs_and_keywords_from_openalex(doi):
    try:
        work = Works()["https://doi.org/" + doi]
        time.sleep(0.2)
        if work:
            abstract = undo_index(work.get('abstract_inverted_index', {}))
            keywords = ', '.join([k['display_name'] for k in work.get('keywords', [])])
            return abstract, keywords
    except Exception as e:
        print(f"No se pudo obtener datos de OpenAlex para el DOI {doi}: {e}")
    return "", ""


def normalizar_apellido(apellido: str) -> str:
    """Convierte a minúsculas y elimina acentos."""
    return unidecode(apellido.lower())

# --- Funciones Principales de Milvus (con modificaciones) ---

def create_milvus_collection_with_json():
    """Define el esquema y crea la colección en Milvus con un campo JSON."""
    if utility.has_collection(COLLECTION_NAME):
        print(f"La colección '{COLLECTION_NAME}' ya existe.")
        return Collection(COLLECTION_NAME)

    # Definir los campos
    accession_number_field = FieldSchema(name="accession_number", dtype=DataType.VARCHAR, is_primary=True, max_length=100)
    doi_field = FieldSchema(name="doi", dtype=DataType.VARCHAR, max_length=200)
    authors_field = FieldSchema(name="authors", dtype=DataType.VARCHAR, max_length=10024) 
    
    # --- 2. Añadir un campo de tipo JSON para los metadatos ---
    row_data_field = FieldSchema(name="row_data", dtype=DataType.JSON, description="Fila completa del DataFrame como JSON")

    # Campos vectoriales
    title_vector_field = FieldSchema(name="title_vector", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
    authors_vector_field = FieldSchema(name="authors_vector", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
    abstract_vector_field = FieldSchema(name="abstract_vector", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)    
    research_area_vector_field = FieldSchema(name="research_area_vector", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)

    # Crear el esquema incluyendo el nuevo campo JSON
    schema = CollectionSchema(
        fields=[
            accession_number_field, 
            doi_field,
            authors_field,
            row_data_field, # <--- 3. Incluir el campo en el esquema
            title_vector_field, 
            authors_vector_field, 
            abstract_vector_field,            
            research_area_vector_field
        ],
        description="Registros con vectores separados y metadatos completos en JSON"
    )
    
    collection = Collection(name=COLLECTION_NAME, schema=schema)
    print(f"Colección '{COLLECTION_NAME}' creada exitosamente.")
    
    # Crear índices para los campos vectoriales (sin cambios)
    print("Creando índices para los campos vectoriales...")
    index_params = {"metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 128}}
    collection.create_index(field_name="title_vector", index_params=index_params)
    collection.create_index(field_name="authors_vector", index_params=index_params)
    collection.create_index(field_name="authors", index_name="idx_authors") #Campo  no vectorial
    collection.create_index(field_name="abstract_vector", index_params=index_params)
    collection.create_index(field_name="research_area_vector", index_params=index_params)
    print("Índices creados.")
    
    return collection

def add_to_milvus_with_json(filename, collection):
    """Lee un archivo Excel y añade los datos a la colección de Milvus, incluyendo la fila como JSON."""
    df = pd.read_excel(filename).fillna('') # Rellenar NaNs para evitar errores en JSON
    
    for index, row in df.iterrows():
        # Extraer datos y generar embeddings (igual que antes)
        accession_number = row['Accession Number']
        title = str(row['Article Title'])
        doi = str(row['DOI'])
        authors = normalizar_apellido(str(row['Authors']))
        research_areas = str(row['Research Area'])
        abstract, keywords = get_abs_and_keywords_from_openalex(doi)
        
        # MILVUS SÓLO ACEPTA CUATRO CAMPOS DE TEXTO PARA VECTORIZAR
        title_vector = get_embedding(title)
        authors_vector = get_embedding(authors)
        abstract_vector = get_embedding(abstract)
        research_area_vector = get_embedding(research_areas)

        # --- 4. Preparar el diccionario con los datos de la fila ---
        # Asegúrate de que todos los datos son compatibles con JSON (ej. no hay NaNs)
        row_dict = row.to_dict()

        # Preparar los datos para la inserción, incluyendo el diccionario
        entities = [
            [accession_number],
            [doi],
            [authors],
            [row_dict], # <--- 5. Añadir el diccionario directamente
            [title_vector],
            [authors_vector],
            [abstract_vector],
            [research_area_vector]
        ]
        
        try:
            mutation_result = collection.insert(entities)
            print(f"Registro insertado: {accession_number} "+ str(mutation_result))
        except Exception as e:
            print(f"Error al insertar el registro {accession_number}: {e}")

    collection.flush()
    print("Proceso de inserción completado y datos 'flusheados' a disco.")


# --- Ejecución del Script ---
if __name__ == "__main__":
    connections.connect("default", host=MILVUS_HOST, port=MILVUS_PORT)
    print(f"Conectado a Milvus en {MILVUS_HOST}:{MILVUS_PORT}")

    # Llamar a la nueva función para crear la colección
    milvus_collection = create_milvus_collection_with_json()
    print("Colección creada")

    # Cargar datos en la colección
    add_to_milvus_with_json(EXCEL_FILENAME, milvus_collection)

    connections.disconnect("default")
    print("Desconectado de Milvus.")
