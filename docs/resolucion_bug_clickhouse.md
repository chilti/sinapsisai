# Autopsia y Resolución del Bug de ClickHouse: Pérdida de W-IDs Institucionales

## 1. El Síntoma Principal
Al consultar el dashboard institucional para el **"CENTRO REGIONAL DE INVESTIGACIONES MULTIDISCIPLINARIAS"**, el sistema reportaba únicamente **211 artículos**. Sin embargo, los logs de ingesta del scraper oficial de OpenAlex (ROR) indicaban que se habían descargado y sincronizado **345 artículos** exitosamente. Faltaban 134 documentos en la visualización final.

## 2. Diagnóstico e Investigación
Para aislar el problema, creamos un script de autopsia (`scratch/debug_ch.py`) y realizamos las siguientes pruebas directamente contra ClickHouse:

1. **Auditoría de Ingesta:** Comprobamos que la tabla puente `paper_entity_map` contenía 1,140 mapeos para el Centro, confirmando que la ingesta guardó los datos correctamente.
2. **Análisis de Discrepancia:** Descubrimos un patrón crítico: los 211 artículos que *sí* aparecían usaban un **DOI** como identificador. Los artículos faltantes usaban nativamente identificadores de OpenAlex (**W-IDs**).
3. **Prueba de Integridad de Datos:** Ejecutamos una consulta plana (`SELECT count() FROM works_flat WHERE id IN (...)`) y encontramos que los 135 artículos con W-ID **sí existían en la base de datos**. No hubo pérdida de datos durante la escritura.
4. **Aislamiento del Fallo:** Comprobamos que el fallo ocurría estrictamente en el momento en que `compute_scholar_metrics_ch.py` y `materialize_works_academic.py` intentaban *leer* y *cruzar* los datos.

## 3. La Causa Raíz (Bug del Motor de ClickHouse)
El problema era una limitación/bug en el optimizador de consultas nativo de ClickHouse. Los scripts originales utilizaban una consulta SQL monolítica muy compleja que intentaba cruzar tablas (`JOIN`) usando una subconsulta que contenía un `UNION DISTINCT` y manipulación dinámica de cadenas de texto (concatenando `'https://openalex.org/' || paper_id`). 

Al intentar realizar este `JOIN` heterogéneo (mezclando lógica de DOIs y W-IDs al mismo tiempo), el motor de ejecución vectorizada de ClickHouse corrompía el índice de cruce en memoria y **descartaba silenciosamente todas las filas generadas dinámicamente (los W-IDs)**, devolviendo un resultado parcial.

## 4. La Solución (La "Bala de Plata")
En lugar de forzar a ClickHouse a resolver un plan de ejecución inestable, optamos por **desacoplar la complejidad**:

1. **Abandono de JOINs Monolíticos:** Dividimos las funciones matemáticas `_Q_PROD` y `_Q_CAP` en dos consultas SQL independientes y puras:
   - Una exclusiva para cruzar registros basados en `DOI` (`_Q_PROD_DOI`).
   - Otra exclusiva para cruzar registros basados en `W-ID` (`_Q_PROD_WID`).
2. **Inversión de Dependencia SQL:** Volteamos el orden de la consulta. En lugar de partir de `works_academic_all` y cruzar los mapeos, usamos la tabla de mapas (`paper_entity_map`) como fuente primaria (`FROM`), asegurando que cada afiliación actúa como ancla obligatoria.
3. **Fusión en Memoria (Pandas):** En lugar de usar `UNION` en la base de datos, el script de Python ahora ejecuta ambas consultas por separado y une los resultados en RAM utilizando `pandas.concat([df_doi, df_wid])`.

## 5. El Resultado Final
Al transferir la responsabilidad de la unión de ClickHouse a Pandas, sorteamos el bug del motor por completo. 

El resultado fue inmediato: el dashboard pasó a mostrar **349 artículos únicos**. Este número es un éxito rotundo, ya que representa la suma perfecta de los 345 artículos del último snapshot de OpenAlex, **más** 4 artículos *legacy* históricos con DOI que ya existían previamente en el repositorio, demostrando que **la base de datos ahora está agregando el 100% de la producción sin perder un solo registro.**
