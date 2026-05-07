# Script de Ejecución Bibliométrica

**Entidad por defecto**: Facultad de Ciencias
**Fecha**: 2026-03-05
**Re-uso**: reemplaza {ENTITY} con otra entidad al ejecutar.

---

### Arquitecto_de_Datos
## Script técnico – Plan de Estudio Bibliométrico  
### Facultad de Ciencias (UNAM)  
> **{ENTITY}**  ←  *Reemplazar por el nombre completo de la entidad*  
> Ejemplo: `Facultad de Ciencias, UNAM`

```python
# ------------------------------------------------------------------
# 1. Datos institucionales y métricas globales
# ------------------------------------------------------------------
entity_stats = get_entity_statistics({ENTITY})
print("Producción institucional (totales):")
print(entity_stats)

# ------------------------------------------------------------------
# 2. Red de coautoría interna
# ------------------------------------------------------------------
coauth_network = get_coauthorship_network_for_entity({ENTITY})
print("\nRed de coautoría (Nodos, Relaciones):")
print(f"Nóds: {len(coauth_network['nodes'])}, Edges: {len(coauth_network['edges'])}")

# ------------------------------------------------------------------
# 3. Tendencias temáticas internas
# ------------------------------------------------------------------
trending_topics = get_trending_topics({ENTITY})
print("\nTópicos de mayor crecimiento (top‑10):")
for t in trending_topics[:10]:
    print(f"- {t['topic']} ({t['growth']:.2%})")

# ------------------------------------------------------------------
# 4. Distribución por Objetivo de Desarrollo Sostenible (SDG)
# ------------------------------------------------------------------
sdg_dist = get_sdg_distribution({ENTITY})
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
collab_query = query_knowledge_graph_cypher(query, {'entity':{ENTITY}})
print("\nTop‑10 colaboradores internacionales (por número de artículos):")
for row in collab_query['records']:
    print(f"{row[0]} – {row[1]} artículos")

# ------------------------------------------------------------------
# 6. Open Access y calidad de revistas
# ------------------------------------------------------------------
# Qdrant: buscamos papers con OA flag true dentro del dominio
search_res = search_scientific_papers_semantic(
    query="open access",
    entity_context="{ENTITY}"
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
fwci_stats = query_knowledge_graph_cypher(fwci_query, {'entity':{ENTITY}})
print("\nImpacto medio (FWCI):", fwci_stats['records'][0][0])
print("Percentil 95% de citas:", fwci_stats['records'][0][1])

# ------------------------------------------------------------------
# 8. Exportar resultados a CSV para la Junta
# ------------------------------------------------------------------
import pandas as pd

def export_csv(df, fname):
    df.to_csv(fname, index=False)
    print(f"Exportado: {fname}")

export_csv(pd.DataFrame(entity_stats), f'output/{ENTITY}_entity_stats.csv')
export_csv(pd.DataFrame(trending_topics), f'output/{ENTITY}_trending_topics.csv')
export_csv(pd.DataFrame(sdg_dist), f'output/{ENTITY}_sdg_distribution.csv')
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