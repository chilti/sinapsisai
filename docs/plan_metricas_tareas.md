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

## Fase 6: Mapas de la Ciencia y Desempeño Institucional
Objetivo: Generar representaciones vectoriales multidimensionales y visualizaciones interactivas a gran escala. Estos mapas se cargarán **bajo demanda** (mediante un botón de "Cargar Mapa") y contarán con un selector para alternar entre ellos en la interfaz.

- [ ] **Tarea 6.1**: Extracción de Vectores de Personas (Neo4j). Ejecutar FastRP en la base de datos para generar los embeddings de los nodos `Person` o `Academic` utilizando la mayor dimensionalidad posible. Exportar una tabla o archivo (CSV/Parquet) con el ID del académico y su vector.
- [ ] **Tarea 6.2**: Extracción de Vectores de Artículos (Qdrant). Extraer los embeddings de los artículos que ya se encuentran vectorizados en Qdrant (usando el embedder de Nomic) y exportarlos en formato tabular (CSV/Parquet).
- [ ] **Tarea 6.3**: Creación de Vectores de Desempeño (Métricas). Extraer para cada académico un vector de 4 dimensiones correspondiente a sus métricas de desempeño: `% Top 10`, `FWCI`, `% Top 1%`, y `Percentil Promedio`.
- [ ] **Tarea 6.4**: Reducción a 2D de los mapas (Python). Importar los conjuntos de vectores (Personas, Artículos y Desempeño) a Python y calcular UMAP utilizando una librería dedicada (`umap-learn` o `cuML` de NVIDIA RAPIDS). El resultado serán archivos con las nuevas columnas: `x` y `y`. Para el Mapa de Desempeño, se generarán tres versiones o niveles de proyección: País, Institución y Dependencia/Subdependencia.
- [ ] **Tarea 6.5**: Clustering de Artículos (HDBSCAN). Aplicar un algoritmo de agrupamiento basado en densidad (como HDBSCAN, si es viable paralelizarlo o procesarlo eficientemente) sobre los artículos para definir los "continentes" o constelaciones temáticas de la galaxia.
- [ ] **Tarea 6.6**: Etiquetado Semántico de Clústeres. Implementar un algoritmo de etiquetado para cada clúster generado (inspirado en la aproximación de Nomic), extrayendo los tópicos o palabras clave representativas que darán nombre a las regiones del mapa.
- [ ] **Tarea 6.7**: Teselación con Quadfeather. Utilizar la herramienta `quadfeather` para procesar los archivos con las columnas `x` e `y`. Esto generará conjuntos de archivos `.feather` pequeños (baldosas) para cada uno de los mapas (Personas, Artículos y los 3 niveles de Desempeño).
- [ ] **Tarea 6.8**: Visualización Institucional (Deepscatter). Integrar [Deepscatter](https://github.com/nomic-ai/deepscatter.git) en la vista institucional con un selector para alternar entre mapas:
    - **Mapa de Personas**: Mostrar a todos los académicos de la entidad seleccionada a color, y el resto del país en gris claro.
    - **Mapa de Artículos**: Mostrar los papers de la institución a color, y el resto en gris.
    - **Mapa de Desempeño Institucional**: Visualizar únicamente a los académicos. Permitir alternar entre las proyecciones de País, Institución y Dependencia/Subdependencia usando el selector.
- [ ] **Tarea 6.9**: Visualización del Investigador (Deepscatter). Integrar los mapas en la vista individual del investigador.
    - **Mapa de Personas**: Ubicar al investigador en el mapa nacional.
    - **Mapa de Artículos**: Resaltar los artículos del investigador con un color distintivo frente al resto del corpus.

## Fase 7: Autenticación y Registro vía ORCID
Objetivo: Habilitar la verificación de identidad de los investigadores y el registro de nuevos académicos mediante la autenticación oficial de ORCID.

- [ ] **Tarea 7.1**: Infraestructura de OAuth. Registrar la aplicación en ORCID (Public API) y configurar variables de entorno (`ORCID_CLIENT_ID`, `ORCID_CLIENT_SECRET`).
- [ ] **Tarea 7.2**: Módulo de Autenticación. Desarrollar `lib/auth.py` para gestionar el flujo de OAuth 2.0 (Authorization Code Flow) y las sesiones en Streamlit.
- [ ] **Tarea 7.3**: Persistencia de Usuarios. Crear nodos `User` en Neo4j para almacenar perfiles autenticados, vinculándolos directamente a los nodos `Academic` mediante relaciones de verificación.
- [ ] **Tarea 7.4**: Integración en el Dashboard. Implementar el botón "Identifícate con ORCID" en `dashboard_v2.py` y gestionar el redireccionamiento de retorno.
- [ ] **Tarea 7.5**: Flujo de Verificación (Claiming). Permitir que un investigador autenticado vincule su ORCID real con un nodo `Academic` existente, marcándolo como `verified`.
- [ ] **Tarea 7.6**: Registro de Nuevos Académicos. Implementar un formulario de registro para investigadores que no están en el padrón inicial, permitiendo que ingresen sus datos base tras autenticarse con ORCID.
- [ ] **Tarea 7.7**: Sincronización de Identidad. Actualizar el grafo (Neo4j) y los archivos de mapeo (`snii_llm_verified_matches.json`) con el estado verificado para mejorar la precisión de las métricas.
