# Prompts del Reporte Bibliométrico (IA)

A continuación se presentan las plantillas de *prompts* que el sistema (`report_generator.py`) envía al LLM local (Ollama) para redactar automáticamente cada una de las secciones narrativas del reporte HTML generado para las Instituciones e Investigadores.

Las variables entre llaves `{...}` se inyectan dinámicamente con las métricas cuantitativas pre-calculadas antes de ser enviadas al modelo.

---

### Sección 1: Resumen Ejecutivo
> Basado en los siguientes indicadores globales de `{entity_type}` (`{entity_name}`): Documentos: `{m_docs}`, Citas Totales: `{m_cites}`, FWCI Promedio: `{m_fwci:.2f}`, Open Access: `{m_oa:.1f}%`. Redacta un Resumen Ejecutivo analítico muy breve (1-2 párrafos) con tono formal, destacando su volumen y alcance.

### Sección 2: Trayectoria Histórica de Producción
> El `{entity_type}` (`{entity_name}`) produjo `{m_docs}` documentos históricos. Redacta un párrafo formal observando la importancia de mantener una producción sostenida.

### Sección 3: Excelencia e Impacto Científico
> La calidad del impacto de `{entity_name}` se resume en: Percentil Promedio (posicionamiento global de citas) = `{m_perc:.1f}`, % Top 10% más citado = `{m_top10:.1f}%`, % Top 1% = `{m_top1:.1f}%`, FWCI (impacto normalizado) = `{m_fwci:.2f}` donde 1.0 es la media mundial. Redacta un párrafo estricto analizando la excelencia de este impacto métrico.

### Sección 4: Dinámica de Citación y Redes de Colaboración
> La entidad (`{entity_name}`) tiene una velocidad de captura de citas de `{m_vel:.1f}` citas/año y un `{m_intl:.1f}%` de sus publicaciones se co-autorizan internacionalmente. Redacta un párrafo formal evaluando cómo estas dos métricas impulsan la visibilidad de su obra en redes de colaboración mundial.

### Sección 5: Acceso Abierto y Publicimetría Comercial
> En acceso abierto, `{entity_name}` alcanza un `{m_oa:.1f}%` de apertura global, estimando un costo de APC (Article Processing Charges) de lista de todos los papers en los que figura por `${m_apc:,.0f}` USD. Redacta un párrafo puramente descriptivo sobre su adopción de vías abiertas y la inversión relacionada al modelo APC.

### Sección 6: Identidad Temática de Investigación
> El investigador o institución (`{entity_name}`) presenta un enfoque principalmente en el dominio `'{m_dom}'` y posee un Índice de Gini de concentración temática de `{m_gini:.3f}` (donde cercano a 0 es foco puro, y 1 es amplia diversidad/dispersión temática). Genera un breve análisis formal sobre qué significa que tengan esta distribución y dominio central.

### Sección 7: Visibilidad e Indización
> Para (`{entity_name}`), el `{m_pub:.1f}%` de iteraciones se indiza en PubMed y `{m_doaj:.1f}%` reside en revistas DOAJ. Analiza muy objetivamente y de manera formal cómo estos medios de indexación y bases de datos contribuyen a la ubicuidad del conocimiento.

### Sección 8: Contribución al Desarrollo Sostenible (ODS)
> En cuanto a los Objetivos de Desarrollo Sostenible (ODS), `{entity_name}` tiene publicaciones detectadas algorítmicamente en varias metas de la ONU. Ofrece un párrafo objetivo describiendo la creciente relevancia institucional de alinearse con los ODS.

### Sección 9: Posicionamiento en el Padrón (UMAP) — Solo Investigadores
> Describe formalmente que la proyección de reducción de dimensionalidad UMAP nos ayuda a comparar visualmente al investigador `{entity_name}` con sus pares, tomando en cuenta las métricas de volumen, FWCI, Citas y Excelencia (%Top10).
