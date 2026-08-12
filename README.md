# SNII Info TlachIA - Hub de Inteligencia Bibliométrica (SNII-First)

Sistema de Inteligencia Bibliométrica Híbrida y Orquestador RAG para entidades académicas mexicanas. Esta versión del sistema prioriza la identificación de investigadores nacionales mediante el padrón oficial del SNII (Sistema Nacional de Investigadoras e Investigadores) y una arquitectura de datos distribuida (Neo4j + ClickHouse + Qdrant).

### 📍 Acceso al Sistema
El sistema se encuentra desplegado para la comunidad UNAM en:
- **Instalación principal:** 👉 [https://dinamica1.fciencias.unam.mx/sinapsisai/](https://dinamica1.fciencias.unam.mx/sinapsisai/)
- **Instalación alternativa:** 👉 [https://www.dynamics.unam.mx/sinapsisai/](https://www.dynamics.unam.mx/sinapsisai/)

---

## 🛠 Arquitectura de Datos
El sistema utiliza un enfoque de **Triple Almacenamiento**:
1.  **ClickHouse (Fuente de Verdad)**: Analítica masiva y métricas de producción académica sincronizada (OpenAlex/ORCID).
2.  **Neo4j (Grafo de Conocimiento)**: Relaciones de coautoría, jerarquías institucionales y redes de citación.
3.  **Qdrant (Vector Store)**: Búsqueda semántica, descubrimiento de expertos y RAG.

---

## 🚀 Instalación Básica

1.  **Clonar el Repositorio**
    ```bash
    git clone https://github.com/chilti/sinapsisai.git
    cd sinapsisai
    ```

2.  **Configurar Entorno**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configurar Credenciales**
    Copia el archivo de ejemplo y completa con tus valores:
    ```bash
    cp .env.example .env
    ```
    El archivo `.env.example` contiene todas las variables necesarias con descripciones. Las principales a configurar son:
    - `CH_HOST` / `CH_PORT` / `CH_USER` / `CH_PASSWORD` — ClickHouse (OpenAlex bulk)
    - `NEO4J_URI_MEXICO` / `NEO4J_PASSWORD_MEXICO` — Neo4j
    - `LLM_BASE_URL` / `LLM_MODEL` / `EMBEDDING_MODEL` — servidor LLM local
    - `OPENALEX_LOCAL_API` — API local de OpenAlex (opcional)

---

## 🔄 Pipeline Principal (SNII Ingestion)

El flujo actual se basa en el padrón oficial del SNII. El orquestador principal utiliza LLMs para resolver identidades y evitar homónimos.

### 1. Resolución de Identidades e Ingesta Dual
Para procesar un investigador o una institución completa del padrón SNII:

```bash
# Ejemplo: Procesar investigadores de la Facultad de Ciencias de la UNAM
python SNII/snii_llm_identity_resolver.py --institution "UNAM" --dependency "CIENCIAS" --ingest --ch
```

*   **`--ingest`**: Descarga automáticamente los trabajos desde OpenAlex/ORCID.
*   **`--ch`**: Sincroniza simultáneamente los datos con ClickHouse para métricas en tiempo real.
*   **`--force`**: Fuerza la re-verificación mediante LLM (útil si los IDs previos están corruptos).

### 2. Procesamiento de Académicos No-SNII / Institucionales
Si necesitas agregar académicos que no están en el SNII o producción institucional específica (e.g. SIIA UNAM):

1.  **Generar JSON de perfiles**:
    ```bash
    python ingestion/siia_scraper.py --file "data/Lista_Institucional.xlsx" --entity "Nombre de Entidad"
    ```
2.  **Ingesta Masiva**:
    ```bash
    python ingestion/ingest_apis.py ingestion/profesores_Entidad.json --ch
    ```

---

## 📊 Visualización y Analítica

### 3. Sincronización del Pipeline de Analítica (`sync_analytics_pipeline.py`)

Después de realizar cualquier ingesta de datos (mediante SNII, ROR o de forma manual), es **indispensable** sincronizar los grafos e identidades de Neo4j hacia ClickHouse para recalcular las tablas de analítica. Sin este paso, `compute_scholar_metrics_ch.py` no encontrará los papers recién ingestados.

El script `sync_analytics_pipeline.py` es el orquestador unificado que realiza de forma automática las siguientes fases:
1. **Fase 1 (Firma)**: Sincroniza `paper_entity_map` en ClickHouse con la relación `CREDITED_TO` de Neo4j.
2. **Fase 2 (Talento)**: Sincroniza `paper_author_map` en ClickHouse con la relación `AUTHORED` de Neo4j.
3. **Fase 3 (Materialización)**: Sincroniza e inserta de forma incremental los nuevos papers en `works_academic_all` desde `works_flat` (569M papers de OpenAlex).

Ejecuta el pipeline completo de sincronización con:
```bash
python ingestion/sync_analytics_pipeline.py
```

También puedes ejecutar fases específicas si lo deseas:
```bash
# Sincronizar solo los mapas de afinidad (Fases 1 y 2):
python ingestion/sync_analytics_pipeline.py --phase maps

# Ejecutar solo la materialización de papers en works_academic_all (Fase 3):
python ingestion/sync_analytics_pipeline.py --phase works
```

> **Nota arquitectural:** `works_flat` es la fuente de verdad del bulk de OpenAlex (solo lectura). `works_academic_all` es la tabla pre-materializada que contiene únicamente los papers vinculados a investigadores del sistema, optimizada para el cómputo veloz de indicadores.

### Dashboard Principal
Lanza la interfaz de analítica basada en ClickHouse y Neo4j:
```bash
streamlit run dashboard_analytics.py
```

### Generación de Métricas
Para actualizar el caché analítico de una entidad o investigador:
```bash
# Por entidad (dependencia/subdependencia):
python ingestion/compute_scholar_metrics_ch.py --entity "Facultad de Ciencias"

# Por investigador individual:
python ingestion/compute_scholar_metrics_ch.py --academic "APELLIDO, NOMBRE"
```

---

## 🔁 Sincronización Continua de Producción (`sync_works.py`)

Para mantener el sistema actualizado, el script `ingestion/sync_works.py` actúa como un **orquestador de sincronización continua**. Su propósito principal es buscar y descargar periódicamente los artículos más recientes de los investigadores y entidades que ya se encuentran registrados en el Grafo de Conocimiento (Neo4j).

**Características principales:**
- **Sincronización de Académicos**: Lee los nodos `Person` en Neo4j y consulta de forma combinada ORCID y OpenAlex para obtener nuevas publicaciones.
- **Sincronización Institucional**: Lee los nodos jerárquicos (Institución, Dependencia, Subdependencia) validados con ROR y actualiza su producción.
- **Rendimiento Ultrarrápido**: Emplea comprobaciones en lote (Batch Checks) y consultas en memoria para saltarse de forma instantánea todos los trabajos que ya existen en el sistema, ahorrando cuotas de API y minimizando la escritura en disco.

**Ejemplos de uso:**
```bash
# 1. Sincronizar los trabajos de TODOS los académicos registrados en Neo4j
python ingestion/sync_works.py --all --local --no-resolve-oa

# 2. Sincronizar la producción de las dependencias de una institución específica
python ingestion/sync_works.py --sync-entities --name "UNAM" --limit 10

# Banderas de optimización:
# --no-resolve-oa : Evita la resolución pasiva/redundante de IDs de OpenAlex, acelerando masivamente el proceso para registros existentes.
```

**⚠️ Pasos Posteriores Obligatorios:**
Después de que `sync_works.py` termine de traer los nuevos artículos a Neo4j, es necesario sincronizar estos cambios hacia ClickHouse y recalcular las métricas del dashboard ejecutando en orden:

```bash
# 1. Sincronizar mapas de autoría e ingestar metadatos a ClickHouse
python ingestion/sync_analytics_pipeline.py

# 2. Recalcular las métricas e indicadores cacheados
python ingestion/compute_scholar_metrics_ch.py --all
```

---

## 📂 Documentación Histórica
El proceso legacy (basado en scrapers SIIA manuales y Neo4j puro) ha sido movido a:
👉 [**LEGACY_README.md**](docs/LEGACY_README.md)
