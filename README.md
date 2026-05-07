# Sinapsis AI - Hub de Inteligencia Bibliométrica (SNII-First)

Sistema de Inteligencia Bibliométrica Híbrida y Orquestador RAG para entidades académicas mexicanas. Esta versión del sistema prioriza la identificación de investigadores nacionales mediante el padrón oficial del SNII (Sistema Nacional de Investigadoras e Investigadores) y una arquitectura de datos distribuida (Neo4j + ClickHouse + Qdrant).

### 📍 Acceso al Sistema
El sistema se encuentra desplegado para la comunidad UNAM en:
👉 [**https://dinamica1.fciencias.unam.mx/sinapsisai/**](https://dinamica1.fciencias.unam.mx/sinapsisai/)

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
    Crea un archivo `.env` basado en la arquitectura actual:
    ```env
    NEO4J_URI=bolt://localhost:7687
    NEO4J_USER=neo4j
    NEO4J_PASSWORD=password123
    
    CH_HOST=localhost
    CH_PORT=8123
    CH_USER=default
    CH_PASSWORD=
    
    LLM_BASE_URL=http://localhost:1234/v1/
    ```

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

### Dashboard Principal
Lanza la interfaz de analítica basada en ClickHouse y Neo4j:
```bash
streamlit run dashboard_analytics.py
```

### Generación de Métricas
Para actualizar el caché analítico de una entidad:
```bash
python ingestion/compute_scholar_metrics_ch.py --entity "Facultad de Ciencias"
```

---

## 📂 Documentación Histórica
El proceso legacy (basado en scrapers SIIA manuales y Neo4j puro) ha sido movido a:
👉 [**LEGACY_README.md**](docs/LEGACY_README.md)
