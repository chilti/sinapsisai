# Procedimiento: Mapeo de Instituciones del SNII a ROR

Este documento describe el procedimiento que implementamos para asociar cada institución del padrón del SNII con su identificador ROR (_Research Organization Registry_) correspondiente.

## Objetivo

Enriquecer el padrón del SNII con el identificador ROR de cada institución y subdependencia de acreditación, de modo que sea posible consultar su producción científica directamente desde OpenAlex usando dicho identificador.

---

## Paso 1 – Extracción del Catálogo de RORs Mexicanos

**Script:** `extract_mexican_rors.py`

Se consulta la base de datos de instituciones de OpenAlex almacenada en **ClickHouse** para extraer todas las instituciones con código de país `MX` y un campo `ror` no vacío.

Los campos extraídos por institución son:
- `openalex_id`: Identificador interno de OpenAlex.
- `name`: Nombre oficial de la institución.
- `ror`: URL del ROR (p. ej. `https://ror.org/04a0j6x13`).
- `country_code`: Siempre `MX` en este contexto.
- `type`: Tipo de organización (education, government, healthcare, etc.).
- `lineage`: Cadena de IDs padre para trazar la jerarquía institucional.

El resultado se guarda en `ROR/mexican_institutions_rors.json`.

```bash
python ROR/extract_mexican_rors.py
```

---

## Paso 2 – Mapeo Fuzzy + Validación con LLM

**Script:** `map_snii_to_ror.py`

A partir de los matches SNII previamente verificados (`data/snii_llm_verified_matches.json`), se extraen las combinaciones únicas de `(Institución, Subdependencia)` del padrón.

Para cada par se realiza:

1. **Búsqueda fuzzy**: Se usa `thefuzz` con `token_sort_ratio` contra los nombres del catálogo `mexican_institutions_rors.json` para generar hasta 10 candidatos ROR.

2. **Validación con LLM**: Se construye un prompt con los candidatos y se le pide al modelo local (vía API OpenAI-compatible, p. ej. LM Studio) que elija el ROR más apropiado, distinguiendo el nivel de institución del de subdependencia cuando ambos tienen ROR propio.

3. **Persistencia incremental**: Cada 5 registros se escribe el progreso en `ROR/snii_ror_mapping.json` para evitar pérdida de trabajo ante interrupciones.

```bash
python ROR/map_snii_to_ror.py
```

El archivo de salida `snii_ror_mapping.json` tiene como clave la cadena `"Institución || Subdependencia"` con la estructura:
```json
{
  "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM) || FACULTAD DE CIENCIAS": {
    "best_match_ror": "https://ror.org/02crff812",
    "confidence": 92,
    "reason": "Match exacto de nombre con registro ROR de UNAM"
  }
}
```

---

## Paso 3 – Ingesta de Documentos por ROR

**Script:** `ingest_ror_docs.py`

Con el mapeo `snii_ror_mapping.json` listo, se itera sobre cada entrada con confianza ≥ 70 y se descarga toda la producción científica de esa institución directamente desde **OpenAlex** usando el filtro `institutions.ror`.

Por cada trabajo encontrado se realiza:
1. **Verificación de existencia**: Se consulta Neo4j para no procesar artículos duplicados.
2. **Vectorización**: Los nuevos artículos (título + abstract) se vectorizan con el modelo de embeddings configurado en `.env` y se almacenan en Qdrant.
3. **Materialización en Neo4j**: Se hace un merge del nodo `:APIPaper` con sus autores y relaciones `[:HAS_PAPER]` hacia la entidad/institución.
4. **Doble enlace institucional**: El paper queda ligado tanto a la institución padre como a la subdependencia con `add_entity_paper_link`.

```bash
python ROR/ingest_ror_docs.py
# Con límite para pruebas:
python ROR/ingest_ror_docs.py --limit 5
```

---

## Resumen del Flujo

```
ClickHouse (OpenAlex institutions)
        ↓
extract_mexican_rors.py  →  mexican_institutions_rors.json
        ↓
snii_llm_verified_matches.json (pares Institución/Subdependencia únicos)
        ↓
map_snii_to_ror.py  →  snii_ror_mapping.json
        ↓
ingest_ror_docs.py  →  Neo4j + Qdrant
```

## Notas y Limitaciones

- **Umbrales de confianza**: Solo se ingestan instituciones con `confidence >= 70` en el mapeo LLM. Los registros con menor confianza requieren revisión manual.
- **Dependencia de ClickHouse**: El Paso 1 requiere que la tabla de instituciones de OpenAlex esté materializada en ClickHouse. Si no se cuenta con ella, se puede descargar el [dump público de OpenAlex](https://openalex.org/data-dump).
- **Cobertura parcial de RORs**: No toda institución en el padrón SNII tiene un registro ROR propio, especialmente subdependencias pequeñas. En esos casos se usa el ROR de la institución padre.
