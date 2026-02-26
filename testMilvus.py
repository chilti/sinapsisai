# search_client.py

import openai
from pymilvus import MilvusClient
from rich.console import Console
from rich.panel import Panel
from unidecode import unidecode
import sys
import re

# --- CONFIGURACIÓN ---
# Asegúrate de que estos valores coincidan con tu entorno
MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"
COLLECTION_NAME = "Ciencias_08_25_InCitesRecords_Milvus_JSON_COS"

LMSTUDIO_BASE_URL = "http://localhost:1234/v1"
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-mpnet-base-v2"



# --- INICIALIZACIÓN DE CLIENTES ---
console = Console()
try:
    # Cliente para la API de LM Studio (openai)
    lmstudio_client = openai.OpenAI(base_url=LMSTUDIO_BASE_URL, api_key="not-needed")
    
    # Cliente para Milvus (NUEVA FORMA)
    milvus_client = MilvusClient(
        uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}"
    )
except Exception as e:
    console.print(f"[bold red]❌ Error de inicialización:[/bold red] No se pudo conectar a los servicios.")
    console.print(f"Detalle: {e}")
    console.print("Asegúrate de que Milvus y el servidor local de LM Studio estén en ejecución.")
    sys.exit(1)


def get_embedding(text: str) -> list:
    """Obtiene el embedding de un texto usando el servidor de LM Studio."""
    try:
        response = lmstudio_client.embeddings.create(model=EMBEDDING_MODEL_NAME, input=[text])
        return response.data[0].embedding
    except openai.APIConnectionError as e:
        console.print(f"[bold red]❌ Error de LM Studio:[/bold red] No se pudo obtener el embedding.")
        console.print("Verifica que el servidor local de LM Studio esté activo y que el modelo esté cargado.")
        return None

def normalizar_apellido(apellido: str) -> str:
    """Convierte a minúsculas y elimina acentos."""
    return unidecode(apellido.lower())

def search_milvus(query_text: str, search_field: str, TOP_K: int = 5) -> list:
    """Realiza la búsqueda vectorial en la colección de Milvus usando MilvusClient."""
    console.print(f"\n[cyan]🧠 Generando vector para la consulta...[/cyan]")
    query_vector = get_embedding(query_text)
    
    if query_vector is None:
        return []

    vector_field_name = f"{search_field}_vector"
    search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}

    console.print(f"[cyan]🛰️  Buscando en Milvus en el campo '{vector_field_name}'...[/cyan]")
    
    # --- BÚSQUEDA CON MilvusClient (NUEVA FORMA) ---
    results = milvus_client.search(
        collection_name=COLLECTION_NAME,
        data=[query_vector],
        anns_field=vector_field_name,
        search_params=search_params,
        limit=TOP_K,
        output_fields=["row_data"]
    )

    # --- PROCESAMIENTO DE RESULTADOS (LIGERAMENTE DIFERENTE) ---
    cleaned_results = []
    # El resultado ya es una lista de diccionarios para la primera (y única) consulta
    for hit in results[0]:
        cleaned_results.append({
            "distance": hit['distance'],
            "metadata": hit['entity'].get("row_data", {})
        })
    
    return cleaned_results


def parse_author_name(raw_name: str) -> list:
    """Divide un nombre compuesto por espacios, guiones o comas."""
    # Reemplaza guiones, comas y puntos por espacios, luego divide
    normalized_string = re.sub(r'[-,\.]', ' ', raw_name)
    # .split() sin argumentos maneja múltiples espacios y los elimina
    parts = normalized_string.split()
    return parts

def build_filter_expression(name_parts: list, operator: str) -> str:
    """Construye una expresión de filtro de Milvus con AND u OR."""
    if not name_parts:
        return ""
    # Crea una cláusula 'like' para cada parte del nombre
    clauses = [f"(authors like '%{part}%')" for part in name_parts]
    # Une las cláusulas con el operador lógico
    return f" {operator} ".join(clauses)


def search_by_author_exact(author_name: str):
    """Usa client.query para una búsqueda exacta por autor."""
    console.print(f"\n[cyan]🔍 Buscando trabajos exactos del autor: '{author_name}'...[/cyan]")
    author_name=normalizar_apellido(author_name)
    # Usamos 'like' para búsquedas flexibles. Para coincidencia exacta, usa '=='
    # OJO: Las comillas simples y dobles dentro del string son importantes.
     # Procesar el nombre y construir la expresión
    name_parts = parse_author_name(author_name)
    expr = build_filter_expression(name_parts, "AND")
    print(expr)

    #expr = f"authors like '%{author_name}%'"
    
    results = milvus_client.query(
        collection_name=COLLECTION_NAME,
        filter=expr,
        output_fields=["row_data"] # Pedimos los metadatos
    )
    display_results(results, is_query=True)

def search_hybrid(topic: str, author_name: str):
    """Usa client.search con un filtro para una búsqueda híbrida."""
    console.print(f"\n[cyan]🧠 Generando vector para el tema: '{topic}'...[/cyan]")
    query_vector = get_embedding(topic)
    if query_vector is None: return

    expr = f"authors like '%{author_name}%'"
    
    console.print(f"[cyan]🛰️  Buscando semánticamente con filtro de autor: '{author_name}'...[/cyan]")
    results = milvus_client.search(
        collection_name=COLLECTION_NAME,
        data=[query_vector],
        filter=expr,
        limit=TOP_K,
        anns_field="content_vector",
        output_fields=["row_data"]
    )
    display_results(results[0])


def display_results(results: list, is_query=False):
    # ... (código similar, pero adaptado para el formato de 'query' y 'search')
    if not results:
        console.print(Panel("[yellow]No se encontraron resultados.[/yellow]", title="Resultados"))
        return
    console.print(Panel(f"[bold green]Se encontraron {len(results)} resultados:[/bold green]", title="Resultados"))
    for i, res in enumerate(results):
        #metadata = res.get('entity', res).get('row_data', res)
        metadata = res.get("row_data", {})
        #print(res)
        title = metadata.get("Article Title", "N/A")
        authors = metadata.get("Authors", "N/A")
        distance_str = f"[dim]Distancia: {res.get('distance', 'N/A'):.4f}[/dim]" if not is_query else ""
        panel = Panel(f"[bold]Título:[/] {title}\n[bold]Autores:[/] {authors}", title=f"Resultado {i+1}", subtitle=distance_str, border_style="blue")
        console.print(panel)

def main():
    """Función principal para ejecutar el proceso de búsqueda."""
    try:
        # 1. Comprobar si la colección existe (NUEVA FORMA)
        if not milvus_client.has_collection(collection_name=COLLECTION_NAME):
            console.print(f"[bold red]❌ Error:[/bold red] La colección '{COLLECTION_NAME}' no existe en Milvus.")
            sys.exit(1)
        
        # 2. Cargar la colección en memoria para búsquedas más rápidas (NUEVA FORMA)
        console.print(f"⏳ Cargando colección '[bold green]{COLLECTION_NAME}[/bold green]' en memoria...")
        milvus_client.load_collection(collection_name=COLLECTION_NAME)
        console.print("✅ Colección cargada.")

    except Exception as e:
        console.print(f"[bold red]❌ Error al preparar la colección de Milvus:[/bold red] {e}")
        sys.exit(1)

    # 3. Bucle de interacción con el usuario (sin cambios)
    while True:
        console.print("\n" + "="*50)
        query = console.input("[bold yellow]📝 Ingresa tu consulta de búsqueda (o escribe 'salir' para terminar): [/bold yellow]")
        if query.lower() == 'salir':
            break

        console.print("\nSelecciona el campo en el que deseas buscar:")
        console.print("  [1] Título")
        console.print("  [2] Autores")
        console.print("  [3] Resumen (Abstract)")
        console.print("  [4] Área de Investigación")
        console.print("  [5] author exact")
        
        field_map = {"1": "title", "2": "authors", "3": "abstract", "4": "research_area", '5':'author exact'}
        
        choice = console.input("[bold yellow]Escribe el número del campo: [/bold yellow]")
        
        if choice in field_map:
            if field_map[choice] == 'author exact':
                search_results = search_by_author_exact(query)
            else:
                search_field = field_map[choice]
                search_results = search_milvus(query, search_field)
            display_results(search_results)
        else:
            console.print("[bold red]Opción no válida. Inténtalo de nuevo.[/bold red]")
    
    
    # 4. Liberar la colección y cerrar la conexión
    console.print(f"\n🔌 Liberando colección y cerrando conexión...")
    milvus_client.release_collection(collection_name=COLLECTION_NAME)
    milvus_client.close()
    console.print("¡Hasta pronto!")


if __name__ == "__main__":
    main()