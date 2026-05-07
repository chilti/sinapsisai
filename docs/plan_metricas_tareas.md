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

- [ ] **Tarea 5.1**: Actualizar `dashboard_analytics.py` para soportar filtros de "Censo Total" vs "Solo SNII".
- [ ] **Tarea 5.2**: Modificar la UI para mostrar claramente la distinción entre **Capacidad Instalada** y **Producción Institucional**.
