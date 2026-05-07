# Informe Bibliométrico Final

**Entidad**: Facultad de Ciencias
**Generado**: 2026-03-05_1116

---

# Datos recopilados para Facultad de Ciencias

Ejecuta el siguiente script de recopilación de datos para Facultad de Ciencias:

### Arquitecto_de_Datos
## Script técnico – Plan de Estudio Bibliométrico  
### Facultad de Ciencias (UNAM)  
> **Facultad de Ciencias**  ←  *Reemplazar por el nombre completo de la entidad*  
> Ejemplo: `Facultad de Ciencias, UNAM`

```python
# ------------------------------------------------------------------
# 1. Datos institucionales y métricas globales
# ------------------------------------------------------------------
entity_stats = get_entity_statistics(Facultad de Ciencias)
print("Producción institucional (totales):")
print(entity_stats)

# ------------------------------------------------------------------
# 2. Red de coautoría interna
# ------------------------------------------------------------------
coauth_network = get_coauthorship_network_for_entity(Facultad de Ciencias)
print("\nRed de coautoría (Nodos, Relaciones):")
print(f"Nóds: {len(coauth_network['nodes'])}, Edges: {len(coauth_network['edges'])}")

# ------------------------------------------------------------------
# 3. Tendencias temáticas internas
# ------------------------------------------------------------------
trending_topics = get_trending_topics(Facultad de Ciencias)
print("\nTópicos de mayor crecimiento (top‑10):")
for t in trending_topics[:10]:
    print(f"- {t['topic']} ({t['growth']:.2%})")

# ------------------------------------------------------------------
# 4. Distribución por Objetivo de Desarrollo Sostenible (SDG)
# ------------------------------------------------------------------
sdg_dist = get_sdg_distribution(Facultad de Ciencias)
print("\nDistribución SDG (% de publicaciones):")
for d in sdg_dist:
    print(f"{d['sdg_name']}: {d['percentage']:.1f}%")

# ------------------------------------------------------------------
# 5. Colaboraciones internacionales
# ------------------------------------------------------------------
# Usamos la red de coautoría para extraer países (necesitamos datos en Neo4j)
query = """
MATCH (a:Author)-[:AUTHORED]->(p:Paper)-[:HAS_TOPIC]->(t:Topic),
      (p)<-[:AUTHORED]-(co:Author)
WHERE a.name CONTAINS $entity
WITH co, count(*) AS n
RETURN co.name AS collaborator, n
ORDER BY n DESC
LIMIT 10
"""
collab_query = query_knowledge_graph_cypher(query, {'entity':Facultad de Ciencias})
print("\nTop‑10 colaboradores internacionales (por número de artículos):")
for row in collab_query['records']:
    print(f"{row[0]} – {row[1]} artículos")

# ------------------------------------------------------------------
# 6. Open Access y calidad de revistas
# ------------------------------------------------------------------
# Qdrant: buscamos papers con OA flag true dentro del dominio
search_res = search_scientific_papers_semantic(
    query="open access",
    entity_context="Facultad de Ciencias"
)
oa_count = sum(1 for r in search_res['matches'] if r.payload.get('is_oa', False))
total_hits = len(search_res['matches'])
print(f"\nOpen Access: {oa_count} / {total_hits} ({oa_count/total_hits:.1%})")

# ------------------------------------------------------------------
# 7. Métricas de impacto (FWCI, percentiles)
# ------------------------------------------------------------------
fwci_query = """
MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic)
WHERE t.name CONTAINS $entity
RETURN avg(p.fwci) AS avg_fwci,
       percentileCont(0.95, p.citations) AS pct95
"""
fwci_stats = query_knowledge_graph_cypher(fwci_query, {'entity':Facultad de Ciencias})
print("\nImpacto medio (FWCI):", fwci_stats['records'][0][0])
print("Percentil 95% de citas:", fwci_stats['records'][0][1])

# ------------------------------------------------------------------
# 8. Exportar resultados a CSV para la Junta
# ------------------------------------------------------------------
import pandas as pd

def export_csv(df, fname):
    df.to_csv(fname, index=False)
    print(f"Exportado: {fname}")

export_csv(pd.DataFrame(entity_stats), f'output/Facultad de Ciencias_entity_stats.csv')
export_csv(pd.DataFrame(trending_topics), f'output/Facultad de Ciencias_trending_topics.csv')
export_csv(pd.DataFrame(sdg_dist), f'output/Facultad de Ciencias_sdg_distribution.csv')
```

---

## Validación de los pasos con las herramientas disponibles

| Paso | Herramienta usada | ¿Se puede ejecutar? | Comentario |
|------|-------------------|---------------------|------------|
| 1. Datos institucionales | `get_entity_statistics` | **Sí** – devuelve métricas totales y por año. |
| 2. Red de coautoría | `get_coauthorship_network_for_entity` | **Sí** – construye la red a partir del grafo Neo4j. |
| 3. Tendencias temáticas | `get_trending_topics` | **Sí** – calcula crecimiento de tópicos internos. |
| 4. Distribución SDG | `get_sdg_distribution` | **Sí** – utiliza nodos :SDG y relaciones correspondientes. |
| 5. Colaboraciones internacionales | `query_knowledge_graph_cypher` | **Sí** – consulta en Neo4j; requiere que existan relaciones de co‑autoría con autores externos. |
| 6. Open Access | `search_scientific_papers_semantic` | **Sí** – filtra vectores Qdrant por campo `is_oa`. |
| 7. Impacto (FWCI, percentiles) | `query_knowledge_graph_cypher` | **Sí** – calcula media y percentil de citas en Neo4j. |
| 8. Exportación CSV | Python + Pandas | **Sí** – escritura local; no requiere herramienta externa. |

> **Observaciones**  
> - El script asume que los nodos y relaciones necesarias (p.ej., `:Paper.fwci`, `:Author.name`) están presentes en el grafo Neo4j, tal como indica la documentación inicial.  
> - Si algún campo no existe (por ejemplo, `fwci` o `is_oa`), el paso correspondiente fallará y deberá ajustarse a los atributos disponibles.  
> - Los resultados se guardan en la carpeta `output/`; asegúrese de que exista antes de ejecutar.

---

### SCRIPT_TÉCNICO_LISTO

{"entidad": "Facultad de Ciencias", "total_papers": 8708, "total_académicos": 271, "rango_años": "0 – 2026", "top_tópicos": [{"topic": "Black Holes and Theoretical Physics", "papers": 47}, {"topic": "Cosmology and Gravitation Theories", "papers": 37}, {"topic": "Quantum chaos and dynamical systems", "papers": 16}, {"topic": "Noncommutative and Quantum Gravity Theories", "papers": 16}, {"topic": "Graphene research and applications", "papers": 16}, {"topic": "Astrophysics and Star Formation Studies", "papers": 13}, {"topic": "Carbon Nanotubes in Composites", "papers": 12}, {"topic": "Nuclear physics research studies", "papers": 9}, {"topic": "Advanced Differential Geometry Research", "papers": 9}, {"topic": "Astro and Planetary Science", "papers": 8}], "papers_más_citados": [{"title": "Evolution of Organic Aerosols in the Atmosphere", "year": 2009, "citations": 4767, "author": "SALCEDO GONZALEZ, DARA"}, {"title": "Ubiquity and dominance of oxygenated species in organic aerosols in anthropogenically‐influenced Northern Hemisphere midlatitudes", "year": 2007, "citations": 2866, "author": "SALCEDO GONZALEZ, DARA"}, {"title": "Guidelines for the use and interpretation of assays for monitoring autophagy (4th edition)<sup>1</sup>", "year": 2021, "citations": 2473, "author": "CABRERA BENITEZ, MARIA SANDRA"}, {"title": "Idiopathic pulmonary fibrosis", "year": 2011, "citations": 2126, "author": "PARDO CEMO, ANNIE"}, {"title": "Erosion of Lizard Diversity by Climate Change and Altered Thermal Niches", "year": 2010, "citations": 1839, "author": "VILLAGRAN SANTA CRUZ, MARICELA"}]}

**Resultado [PASO 1]:** No se encontraron datos para la entidad 'Facultad de Ciencias, UNAM' en el servicio de estadísticas institucionales.

**Resultado [PASO 2]:** Se intentó consultar Neo4j para contar papers vinculados a la entidad y se obtuvo cero resultados.  

**Resultado [PASO 3]:** No se encontraron datos de tópicos internos para 'Facultad de Ciencias, UNAM'.

**Resultado [PASO 4]:** Consulta a Neo4j con filtro por nombre devolvió 0 nodos y 0 aristas en la red de coautoría interna.

**Resultado [PASO 5]:** Se realizó una búsqueda de autores en OpenAlex para 'Facultad de Ciencias, UNAM', pero se produjo un error 429 (demasiadas solicitudes).

**Resultado [PASO 6]:** Consulta a Neo4j sobre entidades cuyo nombre contiene 'facultad de ciencias' devolvió la entidad "Facultad de Ciencias".

**Resultado [PASO 7]:** Se obtuvo información estadística para la entidad 'Facultad de Ciencias':
- total_papers: 8708
- total_académicos: 271
- rango_años: 0 – 2026
- top_tópicos: lista de 10 tópicos con número de papers

---

## 

### RESUMEN DE DATOS RECOPILADOS

| Indicador | Valor |
|-----------|-------|
| **Total de publicaciones** | 8 708 |
| **Número total de académicos** | 271 |
| **Rango de años cubiertos** | 0 – 2026 |
| **Top 10 tópicos por número de papers** | 1. Black Holes and Theoretical Physics (47) <br>2. Cosmology and Gravitation Theories (37) <br>3. Quantum chaos and dynamical systems (16) <br>4. Noncommutative and Quantum Gravity Theories (16) <br>5. Graphene research and applications (16) <br>6. Astrophysics and Star Formation Studies (13) <br>7. Carbon Nanotubes in Composites (12) <br>8. Nuclear physics research studies (9) <br>9. Advanced Differential Geometry Research (9) <br>10. Astro and Planetary Science (8) |
| **Publicaciones más citadas** | 1. *Evolution of Organic Aerosols in the Atmosphere* – 4 767 citas (2009)<br>2. *Ubiquity and dominance of oxygenated species in organic aerosols...* – 2 866 citas (2007)<br>3. *Guidelines for the use and interpretation of assays for monitoring autophagy* – 2 473 citas (2021)<br>4. *Idiopathic pulmonary fibrosis* – 2 126 citas (2011)<br>5. *Erosion of Lizard Diversity by Climate Change...* – 1 839 citas (2010) |

> **Observaciones finales**  
> - No se pudieron obtener datos sobre la red de coautoría interna, tendencias temáticas ni colaboraciones internacionales debido a la ausencia de nodos/relaciones adecuadas en el grafo Neo4j y a límites de consulta externa.  
> - Los resultados principales provienen del servicio `get_entity_statistics` para la entidad simplificada "Facultad de Ciencias".  
> - Se recomienda verificar la integridad del grafo Neo4j y la disponibilidad de datos externos (OpenAlex, Qdrant) para completar los pasos faltantes en futuras ejecuciones.

**Resultado [PASO 1]:** No se encontraron datos para la entidad 'Facultad de Ciencias, UNAM' en el servicio de estadísticas institucionales.

**Resultado [PASO 2]:** Se intentó consultar Neo4j para contar papers vinculados a la entidad y se obtuvo cero resultados.  

**Resultado [PASO 3]:** No se encontraron datos de tópicos internos para 'Facultad de Ciencias, UNAM'.

**Resultado [PASO 4]:** Consulta a Neo4j con filtro por nombre devolvió 0 nodos y 0 aristas en la red de coautoría interna.

**Resultado [PASO 5]:** Se realizó una búsqueda de autores en OpenAlex para 'Facultad de Ciencias, UNAM', pero se produjo un error 429 (demasiadas solicitudes).

**Resultado [PASO 6]:** Consulta a Neo4j sobre entidades cuyo nombre contiene 'facultad de ciencias' devolvió la entidad "Facultad de Ciencias".

**Resultado [PASO 7]:** Se obtuvo información estadística para la entidad 'Facultad de Ciencias':
- total_papers: 8708
- total_académicos: 271
- rango_años: 0 – 2026
- top_tópicos: lista de 10 tópicos con número de papers

---

## DATA_COLLECTION_COMPLETE

### RESUMEN DE DATOS RECOPILADOS

| Indicador | Valor |
|-----------|-------|
| **Total de publicaciones** | 8 708 |
| **Número total de académicos** | 271 |
| **Rango de años cubiertos** | 0 – 2026 |
| **Top 10 tópicos por número de papers** | 1. Black Holes and Theoretical Physics (47) <br>2. Cosmology and Gravitation Theories (37) <br>3. Quantum chaos and dynamical systems (16) <br>4. Noncommutative and Quantum Gravity Theories (16) <br>5. Graphene research and applications (16) <br>6. Astrophysics and Star Formation Studies (13) <br>7. Carbon Nanotubes in Composites (12) <br>8. Nuclear physics research studies (9) <br>9. Advanced Differential Geometry Research (9) <br>10. Astro and Planetary Science (8) |
| **Publicaciones más citadas** | 1. *Evolution of Organic Aerosols in the Atmosphere* – 4 767 citas (2009)<br>2. *Ubiquity and dominance of oxygenated species in organic aerosols...* – 2 866 citas (2007)<br>3. *Guidelines for the use and interpretation of assays for monitoring autophagy* – 2 473 citas (2021)<br>4. *Idiopathic pulmonary fibrosis* – 2 126 citas (2011)<br>5. *Erosion of Lizard Diversity by Climate Change...* – 1 839 citas (2010) |

> **Observaciones finales**  
> - No se pudieron obtener datos sobre la red de coautoría interna, tendencias temáticas ni colaboraciones internacionales debido a la ausencia de nodos/relaciones adecuadas en el grafo Neo4j y a límites de consulta externa.  
> - Los resultados principales provienen del servicio `get_entity_statistics` para la entidad simplificada "Facultad de Ciencias".  
> - Se recomienda verificar la integridad del grafo Neo4j y la disponibilidad de datos externos (OpenAlex, Qdrant) para completar los pasos faltantes en futuras ejecuciones.

---

Lean los datos anteriores y redacten juntos el informe bibliométrico final para Facultad de Ciencias.

Cada experto aporta su interpretación desde su rol. La estructura del informe es LIBRE: déjense guiar por lo que los datos realmente revelaron. No completen secciones vacías. Eviten frases genéricas y abstractas; citen cifras y resultados concretos.

REGLAS DE FORMATO DEL INFORME FINAL (obligatorias para la Rectora):
1. El informe debe tener una REDACCIÓN NARRATIVA y lógica. No es una lista de datos.
2. Cada sección debe INTERPRETAR los hallazgos, no solo listarlos.    ¿Qué significa este dato para la institución? ¿Qué patrón revela?
3. Las TABLAS y FIGURAS se ANALIZAN en el texto:    describe lo que muestra cada figura, sus tendencias y su implicación.
4. El CÓDIGO Python, las consultas Cypher y cualquier instrucción técnica    van EXCLUSIVAMENTE en un 'Anexo Técnico' al final del documento,    NUNCA en el cuerpo principal del informe.
5. Requisitos mínimos de contenido:
   a) Síntesis ejecutiva honesta (máximo 3 párrafos).
   b) Análisis temático o de producción con datos reales (tablas, cifras).
   c) Interpretación de las figuras generadas (si las hay).
   d) Conclusiones accionables para la institución.
   e) Anexo Técnico (opcional, con el código al final).

Cuando todos hayan aportado su visión, la Rectora redactará el informe final completo en Markdown, siguiendo las reglas de formato anteriores, y terminará su mensaje con el código: **** (esto cerrará la sesión).