# Estrategia Híbrida de Búsqueda para Instituciones sin ROR
*(Documento de Referencia de Arquitectura y Extracción de Datos)*

**Objetivo:** Diseñar un mecanismo preciso y masivo para identificar e ingestar la producción científica histórica (papers) de instituciones y dependencias que carecen de identificador global ROR, combinando los datos empíricos de nuestros investigadores SNII con la potencia bruta de ClickHouse y el análisis semántico de Inteligencia Artificial (LLMs).

---

## El Problema Central
Las APIs externas como OpenAlex, Crossref o Scopus asocian la vasta mayoría de las instituciones a su identificador mundial **ROR**. Cuando una dependencia pertenece a un sistema no centralizado, es un instituto local, o es una subdivisión de una gran universidad, la ausencia de ROR provoca que todos sus artículos queden semánticamente "huérfanos" a nivel institucional.

Realizar búsquedas por texto libre en sus APIs está sujeto a **falsos positivos** (muchas instituciones se llaman parecido) y **falsos negativos** (autores escribiendo la afiliación de manera inusual o con errores de captura).

## La Solución Propuesta (Enfoque de 3 Fases)

Al contar con un **snapshot de OpenAlex localizado en ClickHouse**, se eliminan las limitaciones de paginación y cuotas de las APIs externas, lo que abre una ventana para una "Pesca de Arrastre Semántica".

### FASE 1: Recolección y Extracción de Semillas (ClickHouse)
Consiste en **partir de lo seguro** (los investigadores que sabemos que trabajan ahí) para entender empíricamente cómo firman su producción científica en el mundo real.

1.  **Input:** Usamos los DOIs (o `author.ids` ya descubiertos) del padrón validado de investigadores SNII adscritos a esa institución fantasma.
2.  **Consulta SQL de Extracción:**
    Lanzamos una consulta directa hacia el repositorio local de ClickHouse para extraer el campo en crudo en el que declaran su filiación.
    ```sql
    SELECT DISTINCT raw_affiliation_string, count() as freq
    FROM openalex.works
    WHERE id IN (lista_de_papers_snii)
    GROUP BY raw_affiliation_string 
    ORDER BY freq DESC
    LIMIT 100
    ```
3.  **Output:** Obtenemos una lista concreta de las formas reales y más frecuentes en las que dicha institución es citada en las publicaciones científicas.

### FASE 2: Minería Semántica y Extracción de Entidades Hijas (LLMs)
Enfrentarse a decenas de variaciones textuales con puras Expresiones Regulares es ineficiente y propenso a errores. Usaremos un LLM local (ej. LM Studio) para comprender estructuralmente los alias.

1.  Se envía la lista de `raw_affiliation_strings` recabada en la Fase 1 al LLM en un único prompt analítico.
2.  **Instrucción Central:**
    *"Analiza estas cadenas de afiliación crudas provenientes de artículos científicos. 1) Extrae el nombre canónico principal de la institución y sus N variaciones/alias más comunes. 2) Extrae todas las 'entidades hijas' (facultades, laboratorios, centros de investigación, departamentos) que detectes en el texto".*
3.  **Output Limpio (JSON):**
    El LLM responderá con una estructura lista para inyectar a una base de datos.
    ```json
    {
      "alias_principales": [
        "Instituto Tecnológico Superior de Xalapa", 
        "ITSX", 
        "Inst. Tec. Sup. Xalapa"
      ],
      "entidades_hijas": [
        "Laboratorio de Bioquímica Aplicada", 
        "Departamento de Sistemas Computacionales"
      ]
    }
    ```

### FASE 3: Pesca de Arrastre Local y Estructuración en Neo4j
Con los alias curados y agrupados jerárquicamente por la Inteligencia Artificial, procedemos a realizar la búsqueda exhaustiva en nuestra base local.

1.  Armamos una consulta optimizada para ClickHouse orientada a texto completo (`ILIKE` o la función `hasToken()` optimizada) buscando esos Alias a lo largo de toda la historia de base de OpenAlex.
    ```sql
    SELECT id, doi, title, raw_affiliation_string 
    FROM openalex.works 
    WHERE raw_affiliation_string ILIKE '%Inst Tecnol Superior de Xalapa%' 
       OR raw_affiliation_string ILIKE '%ITSX%'
    ```
2.  **Recepción y Procesamiento:**
    Con todos esos cientos o miles de papers masivos, se evalúa su `raw_affiliation_string` contra las **Entidades Hijas** descubiertas en la Fase 2.
3.  **Almacenamiento Conectado (Neo4j):**
    Si pertenece a la institución principal, se vincula. Si detectamos que la afiliación cruda menciona a una entidad hija ("Laboratorio de Bioquímica"), se crea el Sub-Nodo correspondiente en Neo4j, logrando un mapa organizacional interno profundo sin haber dependido nunca del padrón ROR global.

---
**Nota de Ejecución Futura:** Cuando se decida implementar, el script central sugerido para orquestar este flujo de principio a fin debería llamarse `ingestion/ingest_clickhouse_raw_affiliations.py`.
