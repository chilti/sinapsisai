# Guía de Migración y Copia del Servidor SINAPSIS

Este documento describe el procedimiento recomendado para levantar una copia funcional del sistema SINAPSIS en una nueva máquina.

Dado que la aplicación principal (Dashboard de Streamlit) ha sido diseñada para tener un "degradado elegante", es posible levantar el sistema sin necesidad de reinstalar o migrar las bases de datos pesadas (Neo4j, Qdrant o ClickHouse). El sistema desactivará automáticamente aquellas funciones que dependan de estos servicios.

## Procedimiento de Copia

Lo que tenías en mente es correcto en esencia. Los pasos detallados son los siguientes:

### 1. Clonar el Código Fuente
En la nueva máquina, descarga la versión más reciente del código desde el repositorio:
```bash
git clone git@github.com:chilti/sinapsisai.git
cd sinapsisai
```
*(Si ya habías clonado el repositorio, simplemente ejecuta `git pull origin main`)*

### 2. Copiar los Datos y Archivos Generados
Para que el dashboard tenga la información precalculada de métricas, gráficas interactivas y mapas, debes copiar (mediante `rsync`, `scp` o un disco externo) las siguientes carpetas desde el servidor original hacia la nueva máquina:

- **`data/`**: Contiene la base de datos DuckDB (`analytics_cache.duckdb`), los archivos `.parquet` de fallback, y los cachés de embeddings. Es la parte más importante para que las métricas funcionen rápido.
- **`public/`**: Contiene los archivos estáticos y los datos exportados (`.json` y otros) necesarios para que el mapa espacial de Deepscatter (pestaña de Inicio) se renderice correctamente en el frontend.
- **`reports/`**: Contiene los reportes PDF o de texto que ya se han generado para las dependencias.

> [!TIP]
> Si vas a transferir los archivos por red, es muy recomendable usar `rsync`, ya que la carpeta `data/` puede contener miles de archivos:
> `rsync -avz usuario@servidor_original:/home/sinapsisai/data/ /ruta/local/sinapsisai/data/`

### 3. Copiar las Variables de Entorno (IMPORTANTE)
El archivo `.env` **no se sube a GitHub** por seguridad, pero es fundamental para que el Asistente Inteligente (y las APIs de OpenAlex) funcionen. 
Debes copiar el archivo `.env` del servidor original a la raíz del nuevo proyecto.

```bash
# Ejemplo:
scp usuario@servidor_original:/home/sinapsisai/.env /ruta/local/sinapsisai/.env
```

### 4. Configurar el Entorno de Python
Debes replicar el entorno de Python que utiliza el proyecto e instalar sus dependencias.

1. Crea un entorno virtual.
2. Actívalo.
3. Instala los requerimientos:
   ```bash
   pip install -r requirements.txt
   ```
*(Asegúrate de instalar DuckDB si no estuviese listado: `pip install duckdb pandas`)*

### 5. Ejecutar la Aplicación
Una vez que el código, los datos y el entorno están listos, puedes levantar el dashboard:

```bash
streamlit run dashboard_v2.py
```

## Consideraciones sobre Funciones Deshabilitadas (Modo Degradado)

Si en el nuevo servidor **no instalas ni conectas Neo4j ni Qdrant**, ocurrirá lo siguiente de manera automática:

- **Inicio de Sesión y Perfiles**: El botón de "Identifícate con ORCID" estará deshabilitado visualmente, ya que la vinculación del usuario requiere escribir en el Grafo (Neo4j).
- **Asistente Híbrido**: El orquestador inteligente dejará de intentar consultar las bases locales y utilizará de forma prioritaria la API de **OpenAlex** y búsquedas web para responder las dudas del usuario.
- **Buscador Nacional**: El buscador predictivo (barra lateral) no realizará la búsqueda directa sobre la jerarquía, indicando al usuario que la funcionalidad está limitada.
- Las estadísticas precalculadas (de DuckDB y los Parquets de la carpeta `data/`) **seguirán funcionando con total normalidad** en las vistas institucionales.
