# Identificación de ORCID para Investigadores del SNII

## Contexto

El Sistema Nacional de Investigadores e Investigadoras (SNII) de México publica anualmente un padrón de investigadores activos. Este padrón contiene los nombres completos de los investigadores, su nivel, institución de adscripción y otros atributos administrativos, pero **carece de identificadores persistentes y verificables de autor** como [ORCID](https://orcid.org/).

ORCID (_Open Researcher and Contributor ID_) es el estándar internacional para identificar de manera inequívoca a autores científicos, evitando la ambigüedad que generan los homónimos, cambios de nombre, variaciones en la transcripción y trasliteración de apellidos. Contar con el ORCID de cada investigador del SNII es el primer paso para poder vincular su producción científica con bases de datos abiertas como OpenAlex, Crossref o ORCID pública.

## El Problema

Dada la lista de investigadores vigentes del SNII (archivo `Investigadores_vigentes_2025.xlsx`), **¿cómo identificar automáticamente el ORCID que corresponde a cada investigador con la mayor precisión y cobertura posible?**

El problema presenta los siguientes retos inherentes:

1. **Ambigüedad de nombres**: Múltiples investigadores pueden compartir nombre y apellidos; las variaciones de puntuación, acentuación y orden de apellidos son frecuentes.
2. **Datos de entrada limitados**: El padrón solo asegura el nombre completo y la institución de adscripción. Otros campos como área de conocimiento o disciplina pueden estar incompletos.
3. **Escala**: El padrón comprende decenas de miles de registros activos, por lo que cualquier solución debe ser eficiente y paralizable.
4. **Verificación cruzada**: Un ORCID candidato encontrado por alguna heurística debe ser *validado*: es necesario confirmar que sus trabajos registrados en ORCID.org son coherentes con la institución y área de conocimiento reportadas en el padrón, y no simplemente que el nombre sea similar.
5. **Cobertura parcial**: Una fracción de investigadores simplemente no tienen un perfil ORCID público, o su perfil está vacío. El sistema debe distinguir "no ORCID encontrado" de "ORCID incorrecto asignado".

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

## Salida Esperada

Un archivo (CSV, JSON, Parquet o similar) que extienda el padrón original con al menos:

- `orcid`: El identificador ORCID en formato `XXXX-XXXX-XXXX-XXXX`, o vacío si no se encontró.
- `orcid_confidence`: Puntuación o nivel de confianza del match (numérico o categórico: alto/medio/bajo).
- `orcid_source`: Método o fuente que proveyó el ORCID (p. ej. API ORCID, OpenAlex, búsqueda semántica, LLM, manual).
- `orcid_validated`: Booleano indicando si el ORCID fue validado cruzando publicaciones con institución/disciplina del padrón.

## Enfoques Posibles a Explorar

El problema es abierto y admite el uso de diversas herramientas y técnicas. A continuación se enumeran algunas sin preferencia de orden ni de enfoque:

- **APIs abiertas**: Consulta directa a la API pública de [ORCID](https://pub.orcid.org/), [OpenAlex](https://docs.openalex.org/) o [Crossref](https://api.crossref.org/) usando el nombre e institución como query.
- **Búsqueda semántica / embeddings**: Representar el perfil textual del investigador (nombre + institución + área) como vector y buscar similitudes contra registros de ORCID u OpenAlex vectorizados.
- **LLMs como agentes de verificación**: Usar modelos de lenguaje (GPT-4, Llama, Gemini, etc.) para razonar sobre si un candidato ORCID es plausible dado el contexto del padrón, actuando como "juez" en casos ambiguos.
- **Matching difuso**: Algoritmos de similitud de cadenas (Jaro-Winkler, Levenshtein, n-gramas) sobre nombres normalizados para generar candidatos de alta similitud.
- **Grafos de conocimiento**: Construir un grafo que relacione investigadores con co-autores, instituciones y publicaciones, y usar la estructura del grafo para desambiguar identidades.
- **Fuentes secundarias**: Portales web institucionales (páginas de investigadores), Google Scholar, ResearchGate, Scopus Author IDs, como fuentes complementarias de validación.
- **Aprendizaje automático supervisado**: Si existe una muestra de pares (investigador, ORCID confirmado), entrenar un clasificador que aprenda a distinguir matches correctos de falsos positivos.

## Criterios de Evaluación

Para medir la calidad de cualquier solución propuesta, se sugiere construir un conjunto de evaluación (_gold set_) con al menos 200 casos cuyo ORCID sea conocido manualmente, y reportar:

- **Precisión** (Precision): ¿Qué fracción de los ORCIDs asignados son correctos?
- **Cobertura** (Recall): ¿Qué fracción del total de investigadores con ORCID existente fue identificada?
- **F1-score**: Media armónica de precisión y cobertura.
- **Tasa de abstención**: ¿Qué porcentaje del padrón quedó sin ORCID asignado? (Puede ser deseable tener alta cobertura o alta precisión según el caso de uso).

## Licencia y Datos

El padrón del SNII es un documento de acceso público publicado por el CONAHCYT. Los datos de ORCID están sujetos a los términos de uso de [ORCID Public Data File](https://support.orcid.org/hc/en-us/articles/360006897174). Cualquier uso de APIs externas debe respetar sus condiciones de servicio y cuotas de uso.

---
*Documento generado como punto de partida para motivar la exploración de soluciones al problema de identificación de autores científicos a escala nacional.*
