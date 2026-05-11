# Plan de Ejecución: Reestructuración de Métricas y Jerarquías

Este documento desglosa las tareas necesarias para implementar el [Plan de Métricas](file:///mnt/expansion/desplegados/sinapsisai/docs/plan_metricas.md) en fases lógicas.

## Fase 1: Estandarización de Identidad (La Capa de Académicos)
Objetivo: Asegurar que el 100% de los académicos (SNII y No-SNII) estén registrados y vinculados mediante CVU.

- [ ] **Tarea 1.1**: Modificar `SNII/snii_llm_identity_resolver.py` para que guarde registros en `data/snii_llm_verified_matches.json` incluso si no se encuentran identificadores externos.
- [ ] **Tarea 1.2**: Crear la estructura para `data/extra_academics_matches.json` (Académicos No-SNII).
- [ ] **Tarea 1.3**: Actualizar `ingestion/ingest_apis.py` para detectar si un académico es SNII y, de lo contrario, enviarlo al flujo de `extra_academics`.
- [ ] **Tarea 1.4**: Modificar `SNII/ingest_snii_apis.py` para respetar la jerarquía de 3 niveles, guardar CVU y crear nodos sin IDs externos.
- [ ] **Tarea 1.5**: Verificar que `SNII/ingest_snii_apis.py` admita investigadores que no son SNIIs (Censo Total).
- [ ] **Tarea 1.6**: Verificar funcionalidad para cargar trabajos institucionales de una entidad (ej. UNAM) asegurando que se sincronicen en `paper_entity_map`.

## Fase 2: Alineación de Entidades y Jerarquía
Objetivo: Garantizar que las facultades y departamentos estén correctamente ubicados y tengan sus identificadores globales (ROR).

- [ ] **Tarea 2.1**: Actualizar `ROR/ingest_ror_docs.py` para que use el contexto jerárquico (Institución + Dependencia) al asignar IDs de ROR, evitando colisiones de nombres comunes (ej. "Facultad de Ciencias").
- [ ] **Tarea 2.2**: Validar en Neo4j que la relación `[:PART_OF]` refleje fielmente la estructura Institución -> Dependencia -> Subdependencia definida en el Padrón.

## Fase 3: Materialización en ClickHouse
Objetivo: Crear las tablas optimizadas para el cálculo de indicadores a gran escala.

- [x] **Tarea 3.1**: Refactorizar `ingestion/materialize_paper_author_map.py` (Completada vía Ingesta Dual en `ingest_snii_apis.py`).
- [x] **Tarea 3.2**: Crear la tabla `paper_entity_map` en ClickHouse con flags de indización (Completada vía Ingesta Dual en `ingest_ror_docs.py`).
- [x] **Tarea 3.3**: Definir `works_installed_capacity_full` (Consolidada en `paper_author_map`, capturando producción global).
- [ ] **Tarea 3.4**: Materializar `works_academic_all` cruzando `paper_author_map` con `works_flat` (Post-ingesta).

## Fase 4: Lógica de Cálculo de Indicadores
Objetivo: Migrar el motor de métricas a la nueva lógica basada en el Padrón.

- [x] **Tarea 4.1**: Modificar `ingestion/compute_scholar_metrics_ch.py` para que cargue la jerarquía desde el Excel en lugar de Neo4j.
- [x] **Tarea 4.2**: Implementar la agregación de indicadores "bottom-up" (de Académico -> Subdependencia -> Dependencia -> Institución).
- [/] **Tarea 4.3**: Integrar el cálculo de métricas institucionales (Producción) usando la tabla `paper_entity_map` y sus flags de indexación.

## Fase 5: Visualización y Dashboard
Objetivo: Exponer las nuevas métricas y filtros al usuario final.

- [ ] **Tarea 5.1**: Actualizar `dashboard_analytics.py` para soportar filtros de "Censo Total" vs "Solo SNII" y limpiar selectores de instituciones extranjeras.
- [ ] **Tarea 5.2**: Modificar la UI para mostrar claramente la distinción entre **Capacidad Instalada** y **Producción Institucional**.

## Fase 6: Inteligencia Bibliométrica (Embeddings y Clustering)
Objetivo: Generar representaciones vectoriales multidimensionales para proyecciones atlas y análisis semántico.

- [ ] **Tarea 6.1**: Completar Grafo Nacional (Neo4j 7687). Finalizar la ingesta de la producción mexicana total para asegurar que el FastRP refleje la red completa.
- [ ] **Tarea 6.2**: Motor de Embeddings Multimodal. Desarrollar el orquestador que consolide:
    - **Semántico (Nomic)**: Recuperar desde Qdrant.
    - **Científico (SPECTER2)**: Generar para el 100% de la producción en ClickHouse.
    - **Estructural (FastRP)**: Calcular en Neo4j (7687) y sincronizar.
- [ ] **Tarea 6.3**: Perfiles Semánticos de Académicos. Calcular el vector promedio (centroide) para cada investigador basado en su producción individual.
- [ ] **Tarea 6.4**: Proyección y Clustering Atlas. Implementar la reducción de dimensionalidad (UMAP) para visualizar el mapa de la ciencia mexicana y los clusters de expertise académica.
- [ ] **Tarea 6.5**: Sincronización Maestra a ClickHouse. Poblar las columnas de embeddings en `works_academic_all` y `academics_all` para su explotación en el Dashboard.

## Fase 7: Autenticación y Registro vía ORCID
Objetivo: Habilitar la verificación de identidad de los investigadores y el registro de nuevos académicos mediante la autenticación oficial de ORCID.

- [ ] **Tarea 7.1**: Infraestructura de OAuth. Registrar la aplicación en ORCID (Public API) y configurar variables de entorno (`ORCID_CLIENT_ID`, `ORCID_CLIENT_SECRET`).
- [ ] **Tarea 7.2**: Módulo de Autenticación. Desarrollar `lib/auth.py` para gestionar el flujo de OAuth 2.0 (Authorization Code Flow) y las sesiones en Streamlit.
- [ ] **Tarea 7.3**: Persistencia de Usuarios. Crear nodos `User` en Neo4j para almacenar perfiles autenticados, vinculándolos directamente a los nodos `Academic` mediante relaciones de verificación.
- [ ] **Tarea 7.4**: Integración en el Dashboard. Implementar el botón "Identifícate con ORCID" en `dashboard_v2.py` y gestionar el redireccionamiento de retorno.
- [ ] **Tarea 7.5**: Flujo de Verificación (Claiming). Permitir que un investigador autenticado vincule su ORCID real con un nodo `Academic` existente, marcándolo como `verified`.
- [ ] **Tarea 7.6**: Registro de Nuevos Académicos. Implementar un formulario de registro para investigadores que no están en el padrón inicial, permitiendo que ingresen sus datos base tras autenticarse con ORCID.
- [ ] **Tarea 7.7**: Sincronización de Identidad. Actualizar el grafo (Neo4j) y los archivos de mapeo (`snii_llm_verified_matches.json`) con el estado verificado para mejorar la precisión de las métricas.
