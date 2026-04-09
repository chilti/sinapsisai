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

## Procedimiento de Vinculación de Investigadores SNII

El script `SNII/vectorize_researchers.py` implementa una estrategia de búsqueda híbrida y validación por IA para encontrar el identificador ORCID de los investigadores en el padrón del SNII 2025.

```mermaid
graph TD
    A[Excel SNII 2025] --> B[Normalizar Nombres e Instituciones]
    B --> C{Búsqueda Híbrida de Candidatos}
    
    subgraph Búsqueda Semántica (Qdrant)
        C --> D1[Colección: local_authors <br/>Neo4j Mexico/SIIA]
        C --> D2[Colección: orcid_authors_vec <br/>Dump ORCID Global/MX]
    end
    
    subgraph Búsqueda Textual (ClickHouse)
        C --> E1[OpenAlex authors <br/>Búsqueda por Apellido/Nombre]
        C --> E2[orcid_records <br/>Fuzzy Search en ClickHouse]
    end
    
    D1 & D2 & E1 & E2 --> F[Recopilar Top 5-10 Candidatos]
    F --> G[Prompt Detallado al LLM <br/>Reranking & Contexto de Afiliación]
    
    G --> H{¿Match Confirmado?}
    H -- Sí --> I[Extraer ORCID y Scopus IDs]
    H -- No --> J[Marcar como NINGUNO / Error]
    
    I & J --> K[Guardar en snii_llm_verified_matches.json]
    K --> L[Ingesta en Grafo de Conocimiento Neo4j]
```

### Detalles Técnicos del Script
1.  **Triple Vectorización**: Se generan embeddings para autores locales, autores del dump de ORCID y los investigadores del SNII para permitir búsquedas semánticas resilientes a variaciones de nombre.
2.  **Validación LLM**: Se utiliza un modelo de lenguaje (GPT-OSS o similar) para actuar como verificador final, comparando la jerarquía de instituciones (Nivel 1 y Nivel 2) entre el SNII y los metadatos de OpenAlex/ORCID.
3.  **Manejo de Casos Especiales**: El prompt del LLM está instruido para ignorar discrepancias de afiliación cuando el SNII marca al investigador como "SIN INSTITUCIÓN", priorizando la coincidencia onomástica.

## Plan de Verificación

### Pruebas Manuales
1.  Verificar que los campos se guarden en Neo4j.
2.  Ejecutar el recálculo de métricas para un académico de prueba.
3.  Observar el dashboard para confirmar la aparición de los mensajes informativos.
