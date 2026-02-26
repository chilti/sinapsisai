# Sinapsis AI - Hub de Ciencia Abierta
Sistema de Inteligencia Bibliométrica Híbrida y Orquestador RAG para entidades académicas.

## 🛠 Requisitos Previos

- **Python 3.10+** (Recomendado 3.12)
- **Docker y Docker Compose** (Para levantar las bases de datos locales: Neo4j y Qdrant)
- **Git**

## 🚀 Instalación y Configuración Básica

1. **Clonar el Repositorio**
   (Si vas a montarlo en un servidor donde los volúmenes de Docker están en un disco externo como `/mnt/expansion/dockers_drives/`, se recomienda clonar en el _Home_ `~` y ejecutar dockers desde ahí).
   ```bash
   git clone https://github.com/chilti/sinapsisai.git
   cd sinapsisai
   ```

2. **Crear y Activar un Entorno Virtual**
   En Windows:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate
   ```
   En Linux/Mac:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Instalar Dependencias**
   ```bash
   pip install -r requirements.txt
   ```
   *(Nota de solución de problemas: Si en Streamlit sale el error `ModuleNotFoundError: No module named 'numpy.rec'`, ajusta la versión de numpy con `pip install "numpy<2" pandas` dado que ciertas librerías aún no están migradas completamente a Numpy v2).*

4. **Levantar las Bases de Datos (Docker)**
   El sistema requiere Neo4j (Grafo de Conocimiento) y Qdrant (Base de datos vectorial).
   ```bash
   docker compose up -d
   ```
   *Nota sobre infraestructura: En el archivo `docker-compose.yml` los volúmenes están direccionados hacia `/mnt/expansion/dockers_drives/` para el ambiente en producción. Si se está corriendo en un entorno local, modificar a `./neo4j_data` etc. antes de levantar.*

5. **Configurar las Credenciales en `.env`**
   Configura las llaves del LLM y los endpoints.
   ```env
   # Ejemplo de archivo .env
   LLM_BASE_URL=http://localhost:1234/v1/
   EMBEDDING_MODEL=nomic-embed-text
   EMAIL_ADDRESS=correo_contacto_openalex@ejemplo.com
   ```

## 🔄 Flujo de Ingesta (Setup de una Entidad)

Para cargar información de una entidad, debes ejecutar de manera secuencial los siguientes scripts de ingesta:

1. **Ingestar Artículos Locales Iniciales**
   ```bash
   python .\ingestion\ingest_entity_docs.py --file "data/NombreEntidad.txt" --entity "Nombre Entidad"
   ```
2. **Scraping del Padrón de Investigadores (Por ejemplo: SIIA)**
   ```bash
   python .\ingestion\siia_scraper.py --file '.\data\Lista_Investigadores.xlsx' --entity "Nombre Entidad"
   ```
3. **Ingestar y Enriquecer con APIs Globales**
   Descarga la metadata rica, DOIs faltantes y métricas abstractas desde OpenAlex, Scopus, ORCID usando el JSON arrojado por el Scraping.
   ```bash
   python .\ingestion\ingest_apis.py .\ingestion\profesores_Entidad_Resultados.json 
   ```
4. **Computar las Métricas Analíticas y Tableros (Caché Parquet)**
   Precalcula el Sunburst, dimensiones UMAP y conteos históricos para alimentar el Dashboard sin demoras.
   ```bash
   python .\ingestion\compute_scholar_metrics.py
   ```

## 📊 Interfaz Dashboard

Finalmente, corre la interfaz basada en Streamlit:
```bash
streamlit run .\dashboard_v2.py
```
Accede desde el navegador al puerto especificado que aparezca en pantalla (usualmente 8501) para interactuar con la Base de Grafo, el Agente y el Hub Analítico completo.
