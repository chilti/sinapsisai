# Manual Maestro de Procedimientos de Mantenimiento y Actualización del Sistema
**SinapsisAI — Plataforma de Inteligencia Científica y Bibliométrica de México**  
*Documento Operativo y Arquitectura de Datos*

---

## 1. Visión General y Ciclo de Vida de los Datos

El ecosistema de SinapsisAI integra cuatro almacenes de datos interconectados:
1. **Neo4j (Grafo de Conocimiento):** Entidades canónicas (`:Person`, `:Institution`, `:Dependency`, `:Subdependency`, `:Award`, `:Work`).
2. **ClickHouse (Motor Analítico Masivo):** 569M de publicaciones de OpenAlex, `authors_seed_mexico`, y tablas de mapeo materializadas (`paper_author_map`, `paper_entity_map`, `works_academic`).
3. **Qdrant (Base Vectorial):** Embeddings semánticos de perfiles de investigadores y obras.
4. **DuckDB (`analytics_cache.duckdb`):** Almacén columnar embebido de alto rendimiento que sirve los tableros analíticos y métricas del dashboard Streamlit.

### Los 4 Procedimientos del Ciclo de Mantenimiento:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FUENTES DE ACTUALIZACIÓN                        │
├──────────────────────────┬─────────────────────────────┬───────────────┤
│  A. Nuevo Padrón SNII    │  B. Snapshot OpenAlex / ROR │ C. Dumps ORCID│
│  (Excel Conahcyt/Secihti)│  (Borromeo -> ClickHouse)   │ (API / Dump)  │
└────────────┬─────────────┴──────────────┬──────────────┴───────┬───────┘
             │                            │                      │
             ▼                            ▼                      ▼
┌──────────────────────────┐┌───────────────────────────┐┌───────────────┐
│ PROCEDIMIENTO 1: SNII    ││ PROCEDIMIENTO 2: ROR      ││ PROCEDIMIENTO 3:
│ - Diff 2025 vs 2026      ││ - extract_mexican_rors.py ││ - Barrido de  │
│ - update_neo4j_snii.py   ││ - snii_ror_resolver2.py   ││   NoMatch     │
│ - resolve_identities.py  ││ - sync_and_fuse_neo4j.py  ││ - web_orcid   │
│ - Buffer Matches JSON    ││ - ClickHouse ROR update   ││ - LLM Rerank  │
└────────────┬─────────────┘└─────────────┬─────────────┘└───────┬───────┘
             │                            │                      │
             └───────────────────┬────────┴──────────────────────┘
                                 │
                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│ PROCEDIMIENTO 4: PIPELINE INTEGRAL 1-CLIC (AUTOMATIZADO EN DASHBOARD)  │
│ 1. Validación de RORs (Paso 0 de control)                              │
│ 2. Cosecha Externa (sync_works.py)                                     │
│ 3. Sincronización Grafo -> Mapas CH (sync_analytics_pipeline.py)        │
│ 4. Cómputo de Métricas Cienciométricas (compute_scholar_metrics_ch.py) │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Procedimiento 1: Ingesta y Actualización de un Nuevo Padrón SNII

> **Frecuencia:** Cada que se publica una convocatoria o corte trimestral del SNII (anual o semestral).  
> **Modalidad:** Manual-supervisada en terminal con puntos de control de calidad.

### Paso 1.1: Recepción y Auditoría de Diferencias (Diff)
1. Colocar el archivo oficial en `data/` con nomenclatura: `data/Padron-YYYY-XT.xlsx`.
2. Ejecutar la auditoría comparativa contra la historia institucional:
   ```bash
   /home/ambientesPy/revistaslatam/bin/python3 scripts/audit_snii_diff_2025_2026.py \
       --excel data/Padron-2026-2T.xlsx \
       --output data/snii/snii_audit_diff_2026.json
   ```
   *Qué hace:* Genera `snii_audit_diff_2026.json` y `snii_2026_nuevos_pendientes.json`, clasificando a los investigadores en continuos (mismo CVU y membresía), promociones de nivel, cambios institucionales y nuevos ingresos.

### Paso 1.2: Actualización de Membresías y Distinciones en Neo4j
```bash
/home/ambientesPy/revistaslatam/bin/python3 scripts/update_neo4j_snii_2026.py \
    --excel data/Padron-2026-2T.xlsx
```
*Qué hace:* Crea o actualiza en Neo4j los nodos `(:Person {id: cvu})`, nodos `(:Award {year: 2026, level: ...})` y relaciones `[:RECEIVED_AWARD]`, así como los vínculos institucionales `[:AFFILIATED_TO]`.

### Paso 1.3: Resolución de Identidad (ORCID / OpenAlex ID / Scopus ID)
```bash
/home/ambientesPy/revistaslatam/bin/python3 SNII/resolve_snii_2026_identities.py
```
*Características clave del resolver:*
* **Fase A:** Cruce instantáneo contra 107,000 registros verificados previos en `data/snii_llm_verified_matches.json`.
* **Fase B:** Auto-match heurístico en ClickHouse (`authors_seed_mexico`) con Jaro-Winkler >= 0.98 y validación institucional estricta.
* **Fase C:** Desambiguación con LLM local (`openai/gpt-oss-20b` en LM Studio) usando **Structured Outputs (`json_schema`)** y *Chain-of-Thought* (`analysis` $\rightarrow$ `match`).
* Checkpoints atómicos cada 25 registros e inyección directa en Neo4j.

### Paso 1.4: Auditoría Humana (Opcional)
Si existen casos dudosos o empates de candidatos con puntuaciones idénticas:
```bash
streamlit run SNII/validator_app.py
```

---

## Procedimiento 2: Reprocesamiento y Sincronización Institucional de RORs

> **Frecuencia:** Tras descargar un nuevo snapshot de OpenAlex (Borromeo) o cuando se detectan fusiones de instituciones.  
> **Modalidad:** Semi-automatizada con validación cienciométrica asistida por LLM.

### Paso 2.1: Extracción del Catálogo Oficial de RORs Mexicanos
```bash
/home/ambientesPy/revistaslatam/bin/python3 ROR/extract_mexican_rors.py
```
*Qué hace:* Consulta `rag.institutions` en ClickHouse con filtros nativos (`country_code = 'MX'`, `ror IS NOT NULL`). Actualiza `ROR/mexican_institutions_rors.json` con los RORs canónicos reconocidos internacionalmente (actualmente 746 instituciones).

### Paso 2.2: Resolución Jerárquica de Instituciones SNII a ROR
```bash
/home/ambientesPy/revistaslatam/bin/python3 ROR/snii_ror_resolver2.py
```
*Qué hace:* Resuelve la relación jerárquica Institución Padre $\rightarrow$ Dependencia $\rightarrow$ Subdependencia contra el catálogo de RORs. Omite automáticamente las 343 instituciones ya verificadas, y solo recurre al LLM local si surge una entidad nueva. Salida: `data/snii_ror_verified_matches_v2.json`.

### Paso 2.3: Sincronización a Neo4j y Fusión Asistida por LLM
```bash
/home/ambientesPy/revistaslatam/bin/python3 scripts/tools/sync_and_fuse_institutions_neo4j.py
```
*Qué hace:*
1. Sincroniza `ror` y `openalex_id` en nodos `(:Institution)`, `(:Dependency)` y `(:Subdependency)`.
2. Identifica nodos huérfanos o marcados como `Deleted Institution` en OpenAlex (ej. `I4389424196`).
3. Consulta al LLM local para validar si corresponde a una fusión legítima o a un *tombstone bucket* internacional para no contaminar el historial.

### Paso 2.4: Propagación Masiva a ClickHouse
*Qué hace:* Ejecuta mutaciones atómicas (`ALTER TABLE ... UPDATE` en `rag.paper_author_map` y migración selectiva en `rag.paper_entity_map`) para garantizar que el 100% de los registros con autor mexicano tengan su `institution_ror` poblado.

---

## Procedimiento 3: Barrido Periódico de Investigadores sin ORCID

> **Frecuencia:** Trimestral o bajo demanda.  
> **Objetivo:** Recuperar investigadores que antes carecían de ORCID y que lo tramitaron recientemente o que indexaron sus primeras publicaciones.

### Pasos Operativos:
1. **Extracción de CVUs sin ORCID activo:**
   ```bash
   /home/ambientesPy/revistaslatam/bin/python3 -c "
   import json
   with open('data/snii_llm_verified_matches.json') as f:
       data = json.load(f)
   unresolved = [m for m in data if m.get('match') is False or not m.get('matched_orcid')]
   print(f'Pendientes por ORCID: {len(unresolved):,}')
   "
   ```
2. **Cruce Multi-Fuente:**
   * **Fuente Local:** Re-escaneo en la base ClickHouse `orcid` (especialmente tras actualizar el dump oficial anual de ORCID).
   * **API Pública Oficial de ORCID:** Búsqueda por API `https://pub.orcid.org/v3.0/search/` con token `ORCID_CLIENT_ID` y `ORCID_CLIENT_SECRET`.
   * **Web Scraper Institucional:** Ejecución de `SNII/web_orcid_finder.py` sobre directorios públicos de facultades (UNAM, Cinvestav, IPN, UAM).
3. **Re-evaluación con LLM:** Reranking con `openai/gpt-oss-20b` (modo `json_schema`) y persistencia directa en Neo4j y `data/snii_llm_verified_matches.json`.

---

## Procedimiento 4: Pipeline Integral End-to-End (1-Clic)

> **Frecuencia:** Tras ejecutar los Procedimientos de RORs/ORCID, o tras refrescar el snapshot de publicaciones en ClickHouse.  
> **Ubicación:** Accesible desde el Dashboard ([`dashboard_v2.py`](file:///home/sinapsisai/dashboard_v2.py) $\rightarrow$ Pestaña **⚙️ Administración**) o por CLI.

### Flujo Automatizado de 4 Fases:
0. **Fase 0: Pre-validación de Prerrequisitos y RORs (`validate_pipeline_prerequisites.py`):**
   Valida en 1.5s la conectividad de ClickHouse (`rag`), Neo4j y la cobertura de RORs institucionales en `paper_author_map`.
1. **Fase 1: Cosecha Externa de Publicaciones (`sync_works.py`):**
   Descarga obras desde OpenAlex, ORCID y Scopus para los autores identificados.
2. **Fase 2: Sincronización ClickHouse (`sync_analytics_pipeline.py`):**
   Alinea relaciones de coautoría, citas y entidades desde Neo4j hacia `paper_author_map` y `paper_entity_map`.
3. **Fase 3: Recálculo Atómico de Métricas Cienciométricas (`compute_scholar_metrics_ch.py`):**
   Calcula indicadores a 4 niveles (Nacional, Institucional, Subdependencia, Académico) hacia DuckDB (`analytics_cache.duckdb`).

---

## 2. Nueva Disposición de la Pestaña de Administración en el Dashboard

Para optimizar la experiencia de usuario (UX), la pestaña **⚙️ Administración** en [`dashboard_v2.py`](file:///home/sinapsisai/dashboard_v2.py) se organizó en 3 bloques por frecuencia de uso:

1. **🔄 Procedimientos Periódicos (HASTA ARRIBA):**
   * **⚡ 1. Pipeline Integral End-to-End (1-Clic):** Validación + Cosecha + Sync + Métricas.
   * **🏛️ 2. Catálogo y Sincronización Institucional de RORs:** Extracción de catálogo, resolución y fusión a Neo4j.
   * **🔍 3. Barrido Periódico de Investigadores sin ORCID:** Rescate de altas recientes en ClickHouse, API ORCID y scraper.
2. **🛠️ Herramientas Modulares de Mantenimiento (INTERMEDIO):**
   * Cosecha puntual de obras, sincronización específica a ClickHouse, recálculo granular de métricas y Mapas Espaciales UMAP 2D.
3. **📋 Ingesta y Actualización de Nuevo Padrón SNII (HASTA ABAJO):**
   * **File Uploader:** Arrastrar y soltar el archivo `.xlsx` oficial (o seleccionar uno existente).
   * **Pasos independientes y botón maestro:** Auditoría Diff $\rightarrow$ Grafo Neo4j $\rightarrow$ Resolver con IA local.

---

## 2. Diagnóstico del Pipeline 1-Clic: ¿Qué le hace falta?

| Componente | Problema Actual | Consecuencia | Solución Técnica |
|---|---|---|---|
| **Paso 0 (Pre-validación)** | No valida si las instituciones tienen ROR poblado en `paper_author_map`. | Si una institución no tiene ROR, `compute_scholar_metrics_ch.py` la omite silenciosamente en las métricas agregadas. | Crear `scripts/tools/validate_pipeline_prerequisites.py` como paso previo obligatorio. |
| **DuckDB Lock (`IO Error`)** | Concurrencia con Streamlit: si el usuario navega el dashboard mientras corre el pipeline, DuckDB bloquea el archivo. | El paso 3 se aborta con `IO Error: Could not set lock on file "data/analytics_cache.duckdb"`. | Modificar `compute_scholar_metrics_ch.py` para escribir a `analytics_cache.duckdb.tmp` y reemplazar atómicamente al concluir. |
| **Resumabilidad (*Resume*)** | No hay registro de estado intermedio si se interrumpe la red en la cosecha externa. | El usuario tiene que reiniciar el pipeline desde el primer académico. | Implementar `.pipeline_state.json` con guardado de último autor/fase procesada. |
| **Visibilidad en Dashboard** | La UI solo muestra un botón general sin opción de verificar RORs o forzar actualización de DuckDB. | Falta de control granular para el administrador. | Añadir toggles en `dashboard_v2.py`: `[x] Validar RORs antes de métricas` y `[x] Escritura atómica sin colisión DuckDB`. |

---

## 3. Plan de Reorganización y Archivo de Scripts Obsoletos

Actualmente el repositorio tiene **más de 120 scripts**, de los cuales **38 son código temporal, parches obsoletos o versiones v1 superadas**.

### Propuesta de Estructura Limpia con Directorios `archive/`:

```
sinapsisai/
├── SNII/
│   ├── resolve_snii_2026_identities.py     # Script maestro de resolución
│   ├── validator_app.py                    # Interfaz de auditoría Streamlit
│   ├── web_orcid_finder.py                 # Scraper de directorios
│   ├── enrich_snii_oa_ids.py               # Enriquecimiento con OpenAlex
│   ├── vectorize_researchers.py            # Generación de embeddings Qdrant
│   └── archive/                            # [NUEVO] Scripts obsoletos
├── ROR/
│   ├── extract_mexican_rors.py             # Extractor de catálogo CH
│   ├── snii_ror_resolver2.py               # Resolver jerárquico v2
│   ├── ingest_ror_docs2.py                 # Indexador de documentos v2
│   ├── generate_ror_stats.py               # Reporte de métricas ROR
│   ├── mexican_institutions_rors.json      # Catálogo canónico 746 RORs
│   └── archive/                            # [NUEVO] Scripts v1 y pruebas
├── ingestion/
│   ├── sync_works.py                       # Cosecha de publicaciones
│   ├── sync_analytics_pipeline.py          # Sincronización Grafo -> CH
│   ├── compute_scholar_metrics_ch.py       # Motor de métricas ClickHouse
│   ├── build_snii_parquet.py               # Exportación analítica
│   ├── openalex_utils.py                   # Utilidades de OpenAlex
│   └── archive/                            # [NUEVO] Scripts reemplazados
├── scripts/
│   ├── audit_snii_diff_2025_2026.py        # Diff entre padrones
│   ├── update_neo4j_snii_2026.py           # Actualizador de grafo SNII
│   ├── tools/
│   │   ├── sync_and_fuse_institutions_neo4j.py # Fusión y RORs Neo4j
│   │   ├── materialize_paper_author_map.py     # Materializador autor CH
│   │   ├── materialize_paper_entity_map.py     # Materializador entidad CH
│   │   ├── materialize_works_academic.py       # Materializador obras CH
│   │   └── setup_clickhouse_indices.py         # Índices analíticos CH
│   └── archive/                            # [NUEVO] Parches viejos y temporales
├── docs/
│   └── PROCEDIMIENTOS_MANTENIMIENTO.md      # Este manual maestro
└── archive/                                # [NUEVO] Scripts temporales de raíz
```

### Inventario de Scripts a Mover a `archive/`:

#### 1. En `scripts/tools/archive/` (15 archivos):
* `tmp_script.txt` (130 KB, script temporal sin uso).
* `temp_delete_uren.py`, `temp_find_uren.py` (inspecciones puntuales de un autor).
* `check_cols.py`, `check_ch_schema.py`, `get_dois.py`, `get_schemas.py`, `list_ch_databases.py` (inspecciones breves de terminal).
* `qdrant_methods.txt` (texto plano no ejecutable).
* `cleanup_db.py`, `cleanup_paper_entity_map.py`, `cleanup_sdg_flags.py` (parches puntuales ya ejecutados).
* `patch_entity_ids.py`, `patch_all_openalex_fields.py`, `patch_openalex_metadata.py` (parches superados).
* `map_snii_to_ror.py` (reemplazado por `ROR/snii_ror_resolver2.py`).

#### 2. En `ROR/archive/` (4 archivos):
* `snii_ror_resolver.py` (v1 superado por `snii_ror_resolver2.py`).
* `inspect_authors_json.py`, `investigate_affiliations.py`, `investigate_mexican_affiliations.py` (scripts de análisis preliminar).
*(Nota: `ROR/ingest_ror_docs.py` permanece activo como biblioteca base requerida por `ROR/ingest_ror_docs2.py` y `sync_works.py`).*

#### 3. En `ingestion/archive/` (6 archivos):
* `load_orcid_sample.py`, `extract_sample.py`, `test_mixed_ingestion.py` (pruebas de muestreo).
* `siia_scraper.py`, `siia_scraper_snii.py`, `retry_missing_siia.py` (scrapers de la plataforma SIIA obsoletos).
*(Nota: `ingestion/compute_scholar_metrics.py` permanece activo como biblioteca matemática base requerida dinámicamente por `compute_scholar_metrics_ch.py`).*

#### 4. En `SNII/archive/` (1 archivo):
* `patch_snii_json.py` (parche de corrección de un archivo corrupto).
*(Nota: `SNII/ingest_snii_apis.py` permanece activo como biblioteca de cosecha de APIs requerida por `ingestion/sync_works.py` y `lib/auth.py`).*

#### 5. En Raíz `archive/` (10 archivos):
* `scratch_ch.py`, `scratch_neo.py`, `scratch_neo4j.py`, `scratch_neo_academic.py`, `scratch_neo_sdg.py`
* `test_neo4j_count.py`, `test_neo4j_http.py`, `test_neo4j_merge.py`, `test_sidebar.py`
* `delete_node.py`, `debug_ch.py`, `query.py`, `query_neo4j.py`
* `dashboard_analytics1.py`, `dashboard_v1.py`
* Directorio erróneo `{path}` (creado por error en terminal).

---

## 4. Guía Rápida de Comandos para el Administrador

| Tarea de Mantenimiento | Comando Principal | Frecuencia |
|---|---|---|
| **Nuevo Padrón SNII** | `python scripts/audit_snii_diff_2025_2026.py` $\rightarrow$ `python scripts/update_neo4j_snii_2026.py` $\rightarrow$ `python SNII/resolve_snii_2026_identities.py` | Anual / Semestral |
| **Nuevo Snapshot OpenAlex** | `python ROR/extract_mexican_rors.py` $\rightarrow$ `python ROR/snii_ror_resolver2.py` $\rightarrow$ `python scripts/tools/sync_and_fuse_institutions_neo4j.py` | Tras cada snapshot |
| **Barrido de Investigadores sin ORCID** | `python scripts/tools/extract_unresolved_snii_researchers.py` $\rightarrow$ `python SNII/resolve_snii_2026_identities.py` | Trimestral |
| **Actualización Global 1-Clic** | Dashboard Streamlit $\rightarrow$ Botón **"Ejecutar Pipeline Completo"** (o vía CLI: `sync_works.py` + `sync_analytics_pipeline.py` + `compute_scholar_metrics_ch.py`) | Mensual / Demanda |
