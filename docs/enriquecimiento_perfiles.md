# Enriquecimiento de Perfiles Académicos

Se ha implementado el enriquecimiento de los perfiles académicos en el dashboard para mostrar metadatos de validación por IA y fuentes de datos.

## Cambios Realizados

### [Persistencia en Base de Datos]
- **[knowledge_graph.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/database/knowledge_graph.py)**: Actualizado `add_api_paper` para guardar `match_reason` (IA de búsqueda) y datos de auditoría (`verdict`, `reason`, `confidence`, `timestamp`) en los nodos `Author/Academic`.

### [Ingesta y Procesamiento]
- **[ingest_snii_apis.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/SNII/ingest_snii_apis.py)**: 
    - Ahora envía la auditoría y el razonamiento del match a Neo4j.
    - **Nueva Funcionalidad**: Prioriza de forma automática a los investigadores con auditoría `CONFIRMED`.
    - **Nueva Opción**: Argumento `--confirmed-only` para procesar exclusivamente a los confirmados.
- **[compute_scholar_metrics.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/ingestion/compute_scholar_metrics.py)**: Exporta `match_reason` y la auditoría a los archivos Parquet `investigador_total.parquet`.

### [Dashboard]
- **[dashboard_analytics.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/dashboard_analytics.py)**: 
    - Muestra mensaje interactivo "🤖 Buscado usando IA" con el argumento correspondiente.
    - Presenta el veredicto de auditoría con colores (Verde/Amarillo/Rojo) y el razonamiento del auditor.
    - Incluye confirmación de origen "ℹ️ Extraímos ORCID y Scopus IDs de la página web del SIIA" para los académicos de la UNAM correspondientes.

## Verificación

Para ver los cambios reflejados:
1.  **Ingesta**: Ejecutar `python SNII/ingest_snii_apis.py --confirmed-only --limit 5` (para probar con pocos investigadores confirmados).
2.  **Métricas**: Ejecutar `python ingestion/compute_scholar_metrics.py --entity "Facultad de Ciencias"` (o la entidad que se esté probando).
3.  **Visualización**: Abrir `dashboard_v2.py` y consultar un académico procesado en el expander "🔗 Ver Perfiles Académicos".
- **[ingest_entity_docs.py](file:///C:/Users/jlja/Documents/Proyectos/RAGs/ingestion/ingest_entity_docs.py)**: Optimized batch lookup using `openalex_utils.get_works_batch`.
- **[ingest_ror_docs.py](file:///C:/Users/jlja/Documents/Proyectos/RAGs/ROR/ingest_ror_docs.py)**: Added a dynamic fallback by switching `pyalex.config.api_url` to the local address if the official count or fetch fails.
- **[ingest_snii_apis.py](file:///C:/Users/jlja/Documents/Proyectos/RAGs/SNII/ingest_snii_apis.py)**: Integrated the same `get_work` logic for SNII data collection.

## Verification Results
I performed a verification test (using a temporary script) where I intentionally pointed the official URL to a non-existent host.
- **Official API Failure**: The system correctly detected the error.
- **Local Fallback**: The logic immediately switched to `http://127.0.0.1:5009`.
- **Resilience**: Since the local API was not running on the current machine, the script logged a warning but did not crash, returning `None` as expected. This ensures that the ingestion pipe continues even if both sources are down.

> [!NOTE]
> All scripts now prioritize the "Premium" official API (with API Key and Email) and only use the local instance as a safety net.
