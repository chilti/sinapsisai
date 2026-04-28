# Identificación de ORCID para Investigadores del SNII

## Contexto

El Sistema Nacional de Investigadores e Investigadoras (SNII) de México publica anualmente un padrón de investigadores activos. Este padrón contiene los nombres completos de los investigadores, su nivel, institución de adscripción y otros atributos administrativos, pero **carece de identificadores persistentes y verificables de autor** como [ORCID](https://orcid.org/).

> 📥 **Archivo de datos:** [Investigadores_vigentes_2025.xlsx](https://secihti.mx/wp-content/uploads/snii/archivo_historico/Investigadores_vigentes_2025.xlsx)

ORCID (_Open Researcher and Contributor ID_) es el estándar internacional para identificar de manera inequívoca a autores científicos, evitando la ambigüedad que generan los homónimos, cambios de nombre, variaciones en la transcripción y trasliteración de apellidos. Contar con el ORCID de cada investigador del SNII es el primer paso para vincular su producción científica con bases de datos abiertas como OpenAlex, Crossref o ORCID pública.

## El Problema

Dada la lista de investigadores vigentes del SNII, **¿cómo identificar automáticamente el ORCID que corresponde a cada investigador con la mayor precisión y cobertura posible?**

Retos inherentes:

1. **Ambigüedad de nombres**: Múltiples investigadores pueden compartir nombre y apellidos; las variaciones de puntuación, acentuación y orden son frecuentes.
2. **Datos de entrada limitados**: El padrón solo asegura el nombre completo y la institución. Otros campos pueden estar incompletos.
3. **Escala**: El padrón comprende decenas de miles de registros activos.
4. **Verificación cruzada**: Un ORCID candidato debe ser *validado* confirmando que sus trabajos son coherentes con la institución y área del padrón.
5. **Cobertura parcial**: Una fracción de investigadores no tienen perfil ORCID público, o su perfil está vacío.

## Entradas Disponibles

| Campo disponible en el padrón | Descripción |
|---|---|
| `NOMBRE DEL INVESTIGADOR` | Nombre completo en formato APELLIDO, NOMBRE |
| `INSTITUCIÓN DE ACREDITACIÓN` | Universidad o centro de investigación |
| `DEPENDENCIA DE ACREDITACIÓN` | Facultad, Instituto o Centro |
| `SUBDEPENDENCIA DE ACREDITACIÓN` | Departamento o Programa |
| `NIVEL SNII` | Candidato, I, II, III, Emérito |
| `ÁREA DEL CONOCIMIENTO` | Área general (Física, Biología, etc.) |
| `DISCIPLINA` | Disciplina específica dentro del área |

---

## Pipeline Implementado

El proceso se divide en dos etapas ejecutadas por scripts independientes.

### Arquitectura general

```
Investigadores_vigentes_2025.xlsx
        │
        ▼
┌──────────────────────────────────┐
│  snii_llm_identity_resolver.py   │  ← Paso 1: Resolución de identidad
└────────────┬─────────────────────┘
             │ data/snii_llm_verified_matches.json
             ▼
┌──────────────────────────────────┐
│  ingest_snii_apis.py             │  ← Paso 2: Ingesta de publicaciones
└────────────┬─────────────────────┘
             │
      ┌──────┴───────┐
      ▼              ▼
   Neo4j          Qdrant
 (APIPaper)    (api_papers)
```

---

### Paso 1 — `snii_llm_identity_resolver.py`: Resolución de identidad

Resuelve la identidad de cada investigador del padrón SNII asignándole un **ORCID**, un **OpenAlex Author ID** y **Scopus IDs** cuando existen, mediante búsqueda semántica multi-fuente con verificación final por LLM.

#### Flujo interno

Para cada investigador en el Excel:

1. **Embedding semántico** del perfil textual `"Nombre | Institución | Subdependencia"`.
2. **Búsqueda de candidatos en múltiples fuentes** (en orden de prioridad):
   - **OpenAlex Authors** (ClickHouse local): búsqueda lexicográfica por apellido + ranking Jaro-Winkler. Fuente prioritaria porque provee OpenAlex ID y Scopus IDs directamente.
   - **Qdrant `local_authors`** (Neo4j/SIIA): priorizado para UNAM cuando OpenAlex no arroja resultados de alta calidad (score ≥ 0.95).
   - **Qdrant `orcid_authors_vec`** (dump ORCID): búsqueda vectorial para el resto de instituciones.
   - **ClickHouse text-search fuzzy** (dump ORCID): fallback SQL con Jaro-Winkler.
3. **Verificación LLM**: los candidatos se presentan a un LLM local con un prompt estructurado. El LLM devuelve JSON con `match`, `candidate_index`, `orcid` y `reason`.
4. **Persistencia incremental**: resultados guardados en `data/snii_llm_verified_matches.json` cada 10 registros. Los registros ya confirmados (`match: true`) se saltan en ejecuciones subsecuentes.

#### Salida: `data/snii_llm_verified_matches.json`

```jsonc
[
  {
    "snii_author": "APELLIDO, NOMBRE",
    "snii_institution": "UNAM",
    "snii_subdependency": "Instituto de Astronomia",
    "match": true,
    "matched_author": "Nombre Apellido",
    "matched_orcid": "0000-0001-2345-6789",
    "matched_openalex_id": "A1234567890",
    "scopus_ids": ["12345678"],
    "source": "OpenAlex DB Local",
    "reason": "Nombre e institucion coinciden plenamente.",
    "discarded_candidates": []
  }
]
```

#### Uso

```bash
# Procesar todo el padron
python SNII/snii_llm_identity_resolver.py

# Buscar un investigador especifico por nombre (parcial, insensible a mayusculas)
python SNII/snii_llm_identity_resolver.py --name "GARCIA LOPEZ"
python SNII/snii_llm_identity_resolver.py --name "Maria Elena"
python SNII/snii_llm_identity_resolver.py --name "GARC"   # encuentra todos los Garcia*

# Modo prueba (primeros N registros del padron completo)
python SNII/snii_llm_identity_resolver.py --limit 50
```

> **Nota sobre `--name`:** La búsqueda es un `contains` sobre la columna `NOMBRE DEL INVESTIGADOR` del Excel SNII.
> Si el fragmento coincide con varios registros (por ejemplo, un apellido común), todos serán procesados.
> El resultado se guarda/actualiza en `data/snii_llm_verified_matches.json` igual que en el modo completo.

---

### Paso 2 — `ingest_snii_apis.py`: Ingesta de publicaciones

Lee `snii_llm_verified_matches.json` y para cada investigador con `match: true` extrae su producción científica desde múltiples APIs, enriquece los metadatos y los ingesta en Neo4j y Qdrant.

#### Fuentes de publicaciones (en orden de prioridad)

| Fuente | Identificador usado | Qué provee |
|---|---|---|
| **Scopus** (pybliometrics) | `scopus_ids` | DOI, título, año, resumen, citas |
| **ORCID pública** | `matched_orcid` | Lista de works con DOI/put-code |
| **OpenAlex Author API** | `matched_openalex_id` | Todos los trabajos del autor por su ID |

Los artículos de las tres fuentes se **fusionan y deduplican por DOI y título** (normalizado) antes de procesarse.

#### Enriquecimiento por artículo

Para cada DOI recuperado, se consulta OpenAlex (API local o `pyalex` oficial) para obtener:
- Autores completos (`authorships`)
- Abstract reconstruido (desde el `abstract_inverted_index`)
- Keywords de OpenAlex
- Conteo de citas actualizado
- OpenAlex Work ID (para vincular con el grafo de citas)
- Financiadores y números de award

#### Destinos de ingesta

- **Neo4j**: nodo `APIPaper` ligado al nodo `Academic` con la cadena de afiliación `Academic → Subdependencia → Institución`. Persiste también `orcid`, `openalex_id` del autor, veredicto de auditoría y timestamp.
- **Qdrant** (colección `api_papers`): embedding de `título + abstract` por artículo, con payload que incluye `academic_name`, `doi`, `year`, `source` y entidad de adscripción.

#### Condiciones de salto

El script **no** recolecta publicaciones cuando:
- `match: false`
- `audit.verdict == 'FALSE_POSITIVE'`
- No hay ni ORCID ni OpenAlex Author ID disponible
- El investigador ya tiene publicaciones en Neo4j (a menos que se use `--force`)

#### Uso

```bash
# Ingesta completa
python SNII/ingest_snii_apis.py

# Solo investigadores auditados como CONFIRMED
python SNII/ingest_snii_apis.py --confirmed-only

# Forzar re-ingesta de un investigador especifico
python SNII/ingest_snii_apis.py --name "GARCIA" --force

# Modo local (sin limites de API externa), con offset y limite
python SNII/ingest_snii_apis.py --local --offset 500 --limit 200

# Especificar archivo de entrada distinto
python SNII/ingest_snii_apis.py --input data/snii_llm_verified_matches.json
```

---

## Scripts del Directorio

| Script | Descripción |
|---|---|
| `snii_llm_identity_resolver.py` | **Paso 1.** Resuelve identidades SNII → ORCID / OpenAlex ID mediante búsqueda semántica + LLM. |
| `ingest_snii_apis.py` | **Paso 2.** Ingesta publicaciones de los investigadores identificados en Neo4j y Qdrant. |
| `vectorize_researchers.py` | Script original multi-paso (pasos 1–4 de vectorización). Referencia histórica; `snii_llm_identity_resolver.py` es la versión producción del paso 4. |
| `match_snii_orcid.py` | Utilidades compartidas: normalización de texto, clientes ClickHouse, constantes de rutas y bases de datos. |

---

## Campos del JSON de Salida

Un registro en `snii_llm_verified_matches.json` extiende el padrón original con:

| Campo | Descripción |
|---|---|
| `matched_orcid` | Identificador ORCID en formato `XXXX-XXXX-XXXX-XXXX`, o `null`. |
| `matched_openalex_id` | OpenAlex Author ID (p. ej. `A1234567890`), o `null`. |
| `scopus_ids` | Lista de Scopus Author IDs, o lista vacía. |
| `match` | `true` si el LLM confirmó un candidato. |
| `source` | Fuente que proveyó el candidato ganador (`OpenAlex DB Local`, `ORCID Dump (Qdrant)`, etc.). |
| `reason` | Justificación breve del LLM. |
| `discarded_candidates` | Lista de candidatos descartados con su razón. |

---

## Licencia y Datos

El padrón del SNII es un documento de acceso público publicado por el CONAHCYT. Los datos de ORCID están sujetos a los términos de uso de [ORCID Public Data File](https://support.orcid.org/hc/en-us/articles/360006897174). Cualquier uso de APIs externas debe respetar sus condiciones de servicio y cuotas de uso.

---
*Última actualización: refleja el pipeline implementado con `snii_llm_identity_resolver.py` + `ingest_snii_apis.py`.*
