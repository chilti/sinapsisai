
Fuentes de datos para los asistentes:
    Neo4j
    Qdrant
    
Fuentes de datos institucionales (para los gráficos y tablas de métricas):
    Padrón de Investigadores data/Investigadores_vigentes_2025.xlsx, hoja "4T_2025 (44,794)"
    Clickhouse (10.90.0.87)
        Tablas: works_seed_mexico, paper_author_map, works_flat
        

¿Podemos hacer que las tablas paper_author_map tengan la propiedad de actualizarse automaticamente cuando se actualiza clickhouse? Similar a como se actualizan works_seed_mexico y works_flat.

INVESTIGADORES
    
Revisar que el script SNII/snii_llm_identity_resolver.py agregue un registro en el archivo json data/snii_llm_verified_matches.json incluso si no encontró ningín identificador.

Revisar y modificar SNII/ingest_snii_apis.py para que respete la jerarquía de tres niveles: institución -> dependencia -> subdependencia en los nodos de neo4j. Debe agregar nodos de investigadores aunque no tenga un identificador ORCID o openalex id (si no tiene identificadores, tampo tendrá articulos pero queremos que el nodo del investigador exista)). Muy importante que agregue el cvu al nodo.

**Académicos No-SNII**: Crear un flujo paralelo para académicos que no pertenecen al padrón oficial del SNII. 
- Actualizar el flujo original (`python ingestion/ingest_apis.py ingestion/entidad.json`) para que verifique si el académico ya existe en el padrón SNII.
- Si no es SNII, agregarlo al nuevo archivo JSON de soporte (ej. `data/extra_academics_matches.json`) para registrar técnicos, profesores y otros investigadores, permitiendo su medición en el dashboard bajo un filtro de "Personal Académico Total".

ENTIDADES ACADÉMICAS

El script ROR/snii_ror_resolver.py ya agrega todos los niveles de las entidades a data/snii_ror_verified_matches.json. Es importante que el script ROR/ingest_ror_docs.py respete la jerarquía al agregar los identificadores a los nodos de las entidades para que se equivoque y asigne, por ejemplo, un ror la facultad de ciencias de la unam a la facultad de otra unviersidad. Si tenemos un identificador, este escript también enlaza los nodos de las entidades con los nodos de los articulos identificados por ROR o openalex id. Para las entidades no cubiertas por ROR o openalex id, es decir, que no tienen un identificador de estas fuentes, no se crearán enlaces a artículos, y por lo tanto no tendremos producción institucional, sólo capacidad instalada a partir de los articulos de sus investigadores.


Producción institucional. Para ligar la producción institucional de entidades académicas utilizaremos scripts especiales como script ingestion/ingest_wos.py, ingestion/ingest_incites.py, ingestion/ingest_scopus.py, ingestion/ingest_apis.py y los nuevos ingestion/ingest_dimensions.py, ingestion/ingest_semantic.py e ingestion/ingest_scopus.py. Debemos revisar que estos scripts respeten la jerarquía y que etiqueten correctamente los artículos a las entidades correspondientes (creo que tenemos algo como wos_indexed o scopus_indexed, etc). Se puede marcar en el nodo de la entidad qué tipo de fuente tiene indexada para que se calculen los indicadres para cada conjunto de articulos (scopus_indexed, wos_indexed, etc).


Para que la tabla paper_author_map sea correcta, debemos crearla a partir del archivo data/Investigadores_vigentes_2025.xlsx. Los papers de cada investigador deben ser extraidos de neo4j usando el cvu. Modificar el script ingestion/materialize_paper_author_map.py para que lea de data/Investigadores_vigentes_2025.xlsx y extraiga los papers de neo4j usando el cvu.  



CALCULO DE INDICADORES con ingestion/compute_scholar_metrics_ch.py

En lugar de crear la jerarquía usando neo4j utilizar el archivo data/Investigadores_vigentes_2025.xlsx


Para los investigadores. Dado que los investigadores pueden tener articulos con afiliación diferente a México, debemos decidir si para calcular los indicadores cabiamos de la tabla works_seed_mexico a works_flat o bien, si crearmos una nueva tabla que sea works_installed_capacity_mexico. Esta última opción me gusta porque sería más eficiente. También podriamos optar por crear una tabla works_installed_capacity_not_mexico que tenga los trabajos de los ivestigadores que no pertenecen a México (y que no estarán en works_seed_mexico).

Capacidad instalada de las entidades (institución, depedencia, subdependencia). Se calcula en el bucle del cálculo de los indicadores de los investigadores. Los trabajos se van agregando  desde el nivel de investigadores hasta la institución. Se calculan los indicadores de la capacidad instalada para los niveles que existan en la institución.

Para la producción institucional de las entidades académicas (institución, depedencia, subdependencia).  Podemos crear una tabla que mapee los trabajos de las entidades, `paper_entity_map` (similar a `paper_author_map`) con los siguientes campos:
- Jerarquía completa (Institución, Dependencia, Subdependencia).
- Flags de indexación: `is_wos`, `is_scopus`, `is_openalex`, `is_dimensions`, etc., para permitir métricas multi-fuente sin duplicar registros.
- **Atribución por Nivel (Tentativo)**: Un mismo artículo podrá tener múltiples entradas en esta tabla si la afiliación identifica varios niveles (ej. una fila para la UNAM y otra para la Facultad de Ciencias). Se está evaluando si es preferible este esquema o una agregación "bottom-up" (de abajo hacia arriba) en los casos donde falten identificadores de nivel superior.

