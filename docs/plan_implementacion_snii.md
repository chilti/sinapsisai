# Enriquecimiento de Perfiles Académicos en el Dashboard

Este plan detalla la integración de metadatos de validación por IA y fuentes de datos (SIIA/OpenAlex) para mostrar mensajes informativos en el perfil individual de los académicos.

## Cambios Propuestos

### Componente de Ingesta y Base de Datos

#### [MODIFY] [knowledge_graph.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/database/knowledge_graph.py)
Actualizar el método `add_api_paper` para aceptar y persistir en el nodo `Author/Academic`:
- `audit_verdict`, `audit_reason`, `audit_confidence`, `audit_timestamp`
- `match_reason` (el "argumento" de la IA de búsqueda)

#### [MODIFY] [ingest_snii_apis.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/SNII/ingest_snii_apis.py)
- Pasar los campos de auditoría y razonamiento de coincidencia desde el JSON de SNII a la base de datos de grafos.
- **Nueva Opción**: Agregar argumentos de línea de comandos para filtrar por estado de auditoría (ej: `--confirmed-only` o priorizar `CONFIRMED`).

#### [MODIFY] [compute_scholar_metrics.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/ingestion/compute_scholar_metrics.py)
Asegurar que estos nuevos campos se extraigan de Neo4j y se incluyan en el archivo `investigador_total.parquet`.

### Componente Visualización

#### [MODIFY] [dashboard_analytics.py](file:///c:/Users/jlja/Documents/Proyectos/RAGs/dashboard_analytics.py)
En la función `render_investigador_view`, dentro del expander "🔗 Ver Perfiles Académicos":
- Mostrar primero los perfiles (Normal).
- **Si es SNII + IA**: Mostrar mensaje "Buscado usando IA", el argumento de la coincidencia y el veredicto de la auditoría.
- **Si es UNAM + SIIA**: Mostrar mensaje indicando que el ORCID/Scopus IDs se extrajeron del sitio web del SIIA.

## Plan de Verificación

### Pruebas Manuales
1.  Verificar que los campos se guarden en Neo4j.
2.  Ejecutar el recálculo de métricas para un académico de prueba.
3.  Observar el dashboard para confirmar la aparición de los mensajes informativos.
