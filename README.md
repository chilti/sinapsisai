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

### 3. Materialización de `works_academic_all`

Después de cualquier ingesta (SNII, ROR o manual), ejecuta este paso para sincronizar la tabla analítica `works_academic_all` con los nuevos papers incorporados en `paper_author_map` y `paper_entity_map`. Sin este paso, `compute_scholar_metrics_ch.py` no encontrará los papers recién ingestados.

```bash
python ingestion/materialize_works_academic.py
```

- Busca todos los DOIs en `paper_author_map` y `paper_entity_map` que existen en `works_flat` (569M papers OpenAlex).
- Inserta los nuevos papers en `works_academic_all` sin duplicar los ya existentes.
- Es idempotente: puede correrse múltiples veces sin problema.

```bash
# Solo contar cuántos papers nuevos hay pendientes (sin insertar):
python ingestion/materialize_works_academic.py --dry-run
```

> **Nota arquitectural:** `works_flat` es la fuente de verdad del bulk de OpenAlex (solo lectura). `works_academic_all` es la tabla pre-materializada que contiene únicamente los papers de los investigadores del sistema, optimizada para el cómputo de métricas.

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

## 📂 Documentación Histórica
El proceso legacy (basado en scrapers SIIA manuales y Neo4j puro) ha sido movido a:
👉 [**LEGACY_README.md**](docs/LEGACY_README.md)
