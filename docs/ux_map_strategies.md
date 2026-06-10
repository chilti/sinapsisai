# Estrategias de Experiencia de Usuario (UX) para Mapas de la Ciencia

Este documento recopila las ideas estratégicas para maximizar el impacto visual y la interacción del usuario final utilizando los mapas vectoriales WebGL (`regl-scatterplot`) como pieza central de la interfaz de Sinapsis AI.

## 1. El "Héroe" a Pantalla Completa (Full-Screen Hero)
- **Concepto:** Utilizar el mapa de Artículos (Semántica) con más de medio millón de puntos como el fondo interactivo de toda la pantalla de bienvenida (Landing Page).
- **Ejecución:**
  - Configurar el layout de Streamlit a `wide`.
  - Incrustar el `iframe` del mapa cubriendo el 100% del alto y ancho (`100vh`, `100vw`).
  - Superponer el título de "Sinapsis AI" y un buscador central flotando encima del mapa.
  - Añadir una rotación o paneo automático y muy lento (simulando el espacio exterior) mientras el usuario no interactúe con el mapa.

## 2. Onboarding "Encuéntrate a ti mismo" (Vuelo de Cámara)
- **Concepto:** Una transición animada desde la vista macro hasta el clúster específico de un investigador. Ideal para el momento de Login o al abrir la Vista de Perfil.
- **Ejecución:**
  - El usuario busca su nombre o hace clic en su perfil.
  - El backend calcula el centroide `(x, y)` de sus artículos en el mapa.
  - Se envía un comando a `regl-scatterplot` utilizando la API `.zoomToPoints()` o `.lookAt()`.
  - El motor WebGL renderiza un "vuelo de pájaro" fluido atravesando los cientos de miles de puntos hasta aterrizar en los artículos del investigador resaltados.

## 3. "Scrollytelling" de Entidades y Facultades
- **Concepto:** Hacer que la página cuente una historia de la institución mientras el usuario hace scroll hacia abajo. Ideal para la Vista Institucional.
- **Ejecución:**
  - El mapa se queda fijo (`position: fixed`) en el fondo de la pantalla.
  - Conforme el usuario hace scroll por las métricas de distintas facultades (ej. "Facultad de Ciencias", "Instituto de Biología"), se intercepta el evento de scroll.
  - La cámara del mapa se mueve automáticamente y resalta distintos clústeres temáticos asociados a cada entidad leída.

## 4. Transiciones Interactivas (Morphing)
- **Concepto:** Intercambiar entre capas de datos sin recargar la página, aprovechando la aceleración por hardware.
- **Ejecución:**
  - Colocar botones grandes: *"Ver Artículos"*, *"Ver Personas"*, *"Ver Desempeño"*.
  - Al hacer clic, enviar la nueva matriz de coordenadas `[x,y]` al mismo canvas de `regl-scatterplot`.
  - Observar cómo los puntos colapsan y se reordenan visualmente (morphing) para formar la nueva red.

## 5. Pulso en Tiempo Real (Gamificación)
- **Concepto:** Añadir sutiles animaciones o "destellos" sobre el mapa que simulen actividad en vivo en la plataforma.
- **Ejecución:**
  - Pequeños pulsos de luz que representen artículos recién indexados hoy.
  - Notificaciones flotantes sobre el mapa (ej. *"Acaban de citar a la Dra. Pérez"*) disparando un destello temporal en su zona geográfica del mapa de conocimiento.
