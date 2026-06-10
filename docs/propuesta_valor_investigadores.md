# Propuesta de Valor: Atracción de Investigadores a Sinapsis AI

Para lograr que los investigadores del SNII (Sistema Nacional de Investigadoras e Investigadores) se registren de forma proactiva en **Sinapsis AI**, la plataforma debe enfocarse en resolver la burocracia de sus evaluaciones, dar visibilidad a sus métricas clave y ofrecerles un proceso de ingreso sin fricciones.

Aquí se presentan las funcionalidades estratégicas actualizadas para la plataforma:

## 1. Automatización y Proyección para Evaluaciones del SNII (El "Killer Feature")
El mayor dolor de cabeza de un investigador mexicano es monitorear su avance frente a los criterios del CONAHCYT.

*   **Simulador de Nivel SNII:** Un panel que, basado en los criterios vigentes por Área de Conocimiento (I a IX), analice su producción y le indique qué tan cerca está de mantener o subir de nivel (ej. "Te faltan 2 artículos Q1/Q2 para ser competitivo para el Nivel 2").
*   **Métricas de "Incidencia Social" y Acceso Abierto (Fase Avanzada):** Aunque representa un reto técnico mayor, a futuro Sinapsis AI podría rastrear y visualizar menciones en políticas públicas, noticias, o su porcentaje de cumplimiento con los mandatos de Ciencia Abierta de CONAHCYT (vía repositorios institucionales y OpenAlex), métricas cada vez más valoradas por el SNII.

## 2. Onboarding sin Fricciones y Enlace Automático
El proceso de registro e identificación debe ser automático y transparente para el investigador.

*   **Autenticación y Vinculación vía ORCID:** El registro y login se realizará de manera estandarizada mediante ORCID.
    * Si el ORCID del usuario logueado ya está identificado previamente en nuestra base de datos, se le vinculará de forma automática y directa a su perfil.
    * Si su ORCID no estaba identificado previamente, se activará la funcionalidad (ya existente) para que el investigador busque su perfil en el sistema y se asocie a él.
    * *Restricciones actuales:* Por el momento, no se cuenta con la funcionalidad para registrar a perfiles completamente nuevos (ej. que no pertenezcan al SNII), ni para registrar investigadores extranjeros. En estos casos, temporalmente, no se agregarán como nodos nuevos en Neo4j.

## 3. Dashboard Personalizado de "Salud Académica"
Más allá de las métricas institucionales, el investigador quiere ver una radiografía detallada de su propia producción.

*   **Análisis Detallado de Citas (Tipo A y Tipo B):** Desglose claro entre las Citas Tipo A (citas de investigadores independientes) y Citas Tipo B (autocitas), las cuales son fundamentales para las comisiones evaluadoras del SNII.
*   **Trayectoria de Citas en Tiempo Real:** Gráficas atractivas mostrando la evolución histórica de sus citas, el *Citation Half-Life*, y alertas de "Nuevo artículo referenciando tu trabajo".
*   **Alineación con ODS (Objetivos de Desarrollo Sostenible):** Un gráfico radial (Spider chart) mostrando cómo su investigación impacta los ODS de la ONU. Esto es muy útil para informes institucionales y para justificar solicitudes de financiamiento (*grants*).

## 4. Redes de Colaboración Semánticas
Sabiendo que la plataforma ya cuenta con visualizaciones interactivas de la red de coautoría (Mapa de Colaboradores), el siguiente paso es potenciar el descubrimiento activo:

*   **Recomendación de Colaboradores ("Matchmaking" con Embeddings):** Un sistema de recomendación que, utilizando perfiles semánticos basados en los embeddings de los textos de sus publicaciones, sugiera conexiones estratégicas. El sistema le indicará: *"Investigadores en tu universidad o ecosistema trabajando en temas semánticamente similares a los tuyos con los que nunca has publicado"*.

## 5. Gamificación, Visibilidad y Reconocimiento
*   **Insignias (Badges) Institucionales y Difusión Pública:** Reconocimientos como "Top 5% de investigadores más citados en la Facultad de Ciencias este año" o "Investigador con mayor impacto en ODS 3". Estas insignias no solo se mostrarán en su perfil privado, sino que **se publicarán en la página principal de Sinapsis AI y en redes sociales**, además de enviarles un reconocimiento formal que puedan usar en su currículum.
*   **Reportes Anuales Automatizados:** Enviarles un correo atractivo a final de año (estilo "Spotify Wrapped") con un resumen visual de sus logros: "Este año publicaste X artículos, fuiste citado en Y países, y tu trabajo impactó en Z campos semánticos".
