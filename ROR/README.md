# Identificación del Identificador ROR de Instituciones de Investigación Mexicanas

## Contexto

El _Research Organization Registry_ ([ROR](https://ror.org/)) es un sistema global de identificadores persistentes para organizaciones de investigación. Un ROR funciona como el "ORCID de las instituciones": un código único, estable y abierto que representa de forma inequívoca a una universidad, instituto o centro de investigación, independientemente de cómo se escriba su nombre en distintas fuentes.

Contar con el ROR de cada institución en el padrón del SNII permite vincular automáticamente su producción científica con bases de datos abiertas como OpenAlex, Crossref y DataCite, sin depender de coincidencias exactas de nombre que suelen fallar por variaciones ortográficas, siglas o traducciones.

## El Problema

Dado el padrón de investigadores vigentes del SNII (`Investigadores_vigentes_2025.xlsx`), que incluye los campos de **Institución de Acreditación** y **Subdependencia de Acreditación** escritos en lenguaje natural, **¿cómo identificar automáticamente el ROR que corresponde a cada entidad con la mayor precisión y cobertura posible?**

> 📥 **Archivo de datos:** [Investigadores_vigentes_2025.xlsx](https://secihti.mx/wp-content/uploads/snii/archivo_historico/Investigadores_vigentes_2025.xlsx)

El problema presenta los siguientes retos:

1. **Variaciones en los nombres**: Una misma institución puede aparecer con distintas grafías, abreviaciones o idiomas a lo largo del padrón (ej. "UNAM", "Universidad Nacional Autónoma de México", "National Autonomous University of Mexico"). El catálogo ROR también mantiene sus propias variantes de nombres.
2. **Jerarquía institucional**: El padrón distingue entre institución padre (p. ej. una universidad) y subdependencia (un instituto o facultad). Cada nivel puede tener su propio ROR, o únicamente existir el ROR del nivel superior. Determinar el nivel correcto de resolución es parte del problema.
3. **Entidades sin ROR**: No todas las subdependencias del padrón tienen un registro en ROR, especialmente las de menor tamaño o antigüedad. El sistema debe distinguir "ROR no encontrado" de "ROR incorrecto asignado".

## Pipeline de Resolución (Nuevo)

Se ha implementado un pipeline de alto rendimiento inspirado en el resolver de identidades de investigadores:

1.  **Tabla Semilla Optimizada**: Se utiliza `rag.institutions_seed_mexico` en ClickHouse, que contiene ~450k registros de instituciones filtradas por país (MX), términos clave (UNAM, IPN, etc.) y registros con ROR asignado.
2.  **Búsqueda por Lotes (Batching)**: El script `snii_ror_resolver.py` procesa las entidades del SNII en lotes de 20, consultando ClickHouse mediante múltiples cláusulas `LIKE` para minimizar la latencia.
3.  **Verificación Jerárquica con LLM**: Para cada combinación de Institución/Subdependencia, el LLM evalúa los candidatos recuperados y decide:
    *   **Parent ROR**: El identificador de la universidad u organización principal.
    *   **Matched ROR**: El identificador más específico disponible (ej: el ROR de un instituto de investigación dentro de una universidad).

### Ejecución

Para iniciar el proceso de resolución:

```powershell
python ROR\snii_ror_resolver.py --limit 100
```

Los resultados se guardan incrementalmente en `data/snii_ror_verified_matches.json`.

4. **Escala**: El padrón contiene cientos de combinaciones únicas de institución/subdependencia. Cualquier solución debe ser eficiente y automatizable.
5. **Verificación cruzada**: Un ROR candidato debe ser validable: idealmente, la producción científica recuperada mediante ese ROR desde OpenAlex debe ser coherente con el área de conocimiento y los investigadores reportados en el padrón.

## Entradas Disponibles

| Fuente | Descripción |
|---|---|
| `Investigadores_vigentes_2025.xlsx` | Padrón SNII con campos de institución y subdependencia en texto libre |
| [ROR Public Data](https://ror.org/about/) | Dump público del registro global de organizaciones de investigación |
| [OpenAlex Institutions API](https://docs.openalex.org/api-entities/institutions) | API que expone instituciones con su ROR y metadatos adicionales |
| [Crossref](https://www.crossref.org/) | Base de metadatos de publicaciones que usa ROR en afiliaciones de autores |

## Salida Esperada

Un archivo de mapeo (JSON, CSV o similar) que asocie cada par único `(Institución, Subdependencia)` del padrón con:

- `ror`: URL del ROR identificado (p. ej. `https://ror.org/02crff812`), o `null` si no se encontró.
- `ror_name`: Nombre oficial en el catálogo ROR.
- `ror_level`: Si el ROR corresponde a la institución padre (`institution`) o a la subdependencia (`subdependency`).
- `confidence`: Puntuación de confianza del mapeo (0-100 o categórico).
- `source`: Método que proveyó el ROR (fuzzy matching, API, LLM, manual, etc.).

## Enfoques Posibles a Explorar

El problema es abierto y admite diversas técnicas. A continuación se enumeran algunas sin preferencia de orden:

- **Búsqueda Fuzzy**: Comparar los nombres del padrón contra el catálogo de ROR usando métricas de similitud de cadenas (Jaro-Winkler, token sort ratio, bigramas) para generar candidatos rankeados.
- **API ROR nativa**: La API pública de ROR (`https://api.ror.org/organizations?query=...`) permite búsquedas por nombre y devuelve candidatos con puntuación de relevancia.
- **OpenAlex como puente**: Buscar el nombre de la institución en OpenAlex Institutions, que ya resuelve el ROR de sus registros y expone adicionalmente la jerarquía lineage hacia instituciones padre.
- **LLMs como árbitros**: Usar modelos de lenguaje (locales o en la nube) para evaluar un conjunto de candidatos ROR y elegir el más plausible dado el contexto del padrón (institución padre, área del conocimiento, país).
- **Embeddings semánticos**: Representar los nombres de las entidades como vectores de significado y buscar similitudes en un espacio vectorial que compense variaciones de grafía.
- **Grafos de conocimiento**: Usar la estructura jerárquica del catálogo ROR (relaciones de parentesco entre organizaciones) para refinar la resolución al nivel correcto de subdependencia.
- **Enriquecimiento por producción científica**: Validar un ROR candidato descargando una muestra de sus trabajos en OpenAlex y verificando que los autores, temas e instituciones son coherentes con el padrón.

## Criterios de Evaluación

Se recomienda construir un conjunto de validación (_gold set_) con al menos 100 pares `(Institución SNII, ROR conocido)` validados manualmente para reportar:

- **Precisión** (Precision): ¿Qué fracción de los RORs asignados son correctos?
- **Cobertura** (Recall): ¿Qué fracción de las entidades con ROR existente fueron identificadas?
- **F1-score**: Media armónica de precisión y cobertura.
- **Tasa de abstención**: ¿Qué porcentaje de pares no recibió un ROR asignado?
- **Corrección de nivel** (extra): ¿Se asignó el ROR al nivel correcto (institución vs. subdependencia)?

## Licencia y Datos

Los datos del padrón SNII son públicos (CONAHCYT). El catálogo ROR es de acceso libre bajo licencia CC0. Los datos de OpenAlex se distribuyen bajo la licencia CC0 con atribución. Cualquier uso de APIs externas debe respetar sus términos de servicio y cuotas de uso.

---
*Documento generado como punto de partida para motivar la exploración de soluciones al problema de identificación de organizaciones de investigación a escala nacional.*
