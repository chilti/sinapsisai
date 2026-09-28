/**
 * frontend/src/i18n/es.js
 * Diccionario de cadenas en Español (ES)
 */

export const es = {
  // Franja & Navegación
  appName: "SNII Info TlachIA",
  appSubtitle: "Inteligencia Científica del Padrón SNII y Producción Académica",
  tabs: {
    panorama: "Panorama Institucional",
    researchers: "Investigadores",
    maps: "Mapas de la Ciencia",
    mySpace: "Mi Espacio",
    governance: "Administración",
    assistant: "Asistente IA"
  },
  
  // Módulo 1: Panorama Institucional
  panorama: {
    title: "Panorama Institucional y Cartografía de Desempeño",
    institutionSelect: "Institución",
    dependencySelect: "Dependencia / Facultad",
    subdependencySelect: "Subdependencia / Centro",
    knowledgeArea: "Área de Conocimiento SNII",
    sniiLevel: "Nivel SNII",
    periodFilter: "Periodo Temporal",
    allInstitutions: "Todas las Instituciones",
    allDependencies: "Todas las Dependencias",
    allSubdependencies: "Todas las Subdependencias",
    allAreas: "Todas las Áreas",
    allLevels: "Todos los Niveles",
    metrics: {
      totalResearchers: "Investigadores Activos",
      totalWorks: "Publicaciones Indexadas",
      totalCitations: "Citas Recibidas",
      fwciMean: "FWCI Promedio",
      top10Percent: "Producción Top 10%",
      oaRatio: "Tasa de Acceso Abierto"
    },
    charts: {
      sniiDistribution: "Distribución por Nivel SNII (Candidato a Nivel III / Emérito)",
      genderBalance: "Equidad de Género por Área Científica",
      temporalEvolution: "Evolución Temporal de Producción y Citas",
      sdgImpact: "Contribución a los Objetivos de Desarrollo Sostenible (ODS)"
    },
    exportReport: "Exportar Reporte Ejecutivo"
  },

  // Módulo 2: Perfiles de Investigadores
  researchers: {
    searchPlaceholder: "Buscar por nombre de investigador o identificador ORCID...",
    searching: "Buscando investigadores...",
    noResults: "No se encontraron investigadores que coincidan con la búsqueda.",
    profile: {
      sniiBadge: "SNII",
      active2026: "Padrón 2026 Confirmado",
      area: "Área Científica",
      subdiscipline: "Subdisciplina",
      institution: "Institución de Adscripción",
      dependency: "Dependencia",
      subdependency: "Subdependencia",
      orcid: "ORCID",
      hIndex: "Índice H",
      worksCount: "Publicaciones",
      citationsCount: "Citas Totales",
      netCitations: "Citas Netas",
      selfCitations: "Autocitas",
      top10Percent: "Artículos en Top 10%",
      fwci: "FWCI Promedio",
      citingCountries: "Países Citantes"
    },
    tabs: {
      production: "Producción Académica",
      citations: "Análisis de Citas (Zero-Join)",
      coauthors: "Red de Coautorías",
      topics: "Evolución Temática"
    },
    table: {
      title: "Título de la Obra",
      journal: "Revista / Fuente",
      year: "Año",
      citations: "Citas",
      fwci: "FWCI",
      quartile: "Cuartil",
      oa: "Acceso Abierto",
      role: "Rol de Autoría",
      viewWork: "Ver Obra",
      disclaim: "Desvincular"
    },
    downloadDossier: "Descargar Dossier (PDF)",
    downloadMarkdown: "Descargar Reporte (Markdown)"
  },

  // Módulo 3: Mapas de la Ciencia
  maps: {
    title: "Cartografía de Conocimiento y Espacios Semánticos",
    spaceSelect: "Modelo de Embedding",
    nomicModel: "Nomic Embed v1.5 (Multidisciplinario General)",
    specterModel: "SPECTER2 (Representación Científica Especializada)",
    previewModel: "Muestra Preliminar Rápida",
    totalParticles: "Artículos Proyectados",
    clusterLegend: "Clusters Temáticos",
    filterByCluster: "Filtrar por Grupo Temático",
    searchParticle: "Buscar artículo en el mapa...",
    resetZoom: "Restablecer Vista"
  },

  // Módulo 4: Mi Espacio
  mySpace: {
    title: "Mi Espacio de Investigador",
    loginWithOrcid: "Iniciar Sesión con ORCID",
    connectedAs: "Sesión activa como",
    logout: "Cerrar Sesión",
    accreditationTitle: "Solicitar Acreditación como Administrador Institucional",
    accreditationNotice: "Por directriz de gobernanza, la solicitud se limita al nivel institucional más bajo de su jerarquía oficial.",
    requestAccreditationBtn: "Enviar Solicitud de Acreditación",
    positionPlaceholder: "Cargo institucional (ej. Secretario Académico, Coordinador de Biblioteca)",
    emailPlaceholder: "Correo institucional oficial (@unam.mx, etc.)",
    curationTitle: "Gestión y Curación de Producción Científica",
    disclaimedWorks: "Obras Desvinculadas",
    restoreWork: "Reincorporar Obra",
    addCustomWork: "Cargar Obra Manualmente (.bib / RIS)",
    generateDossier: "Generar Dossier de Evaluación SNII / PRIDE"
  },

  // Módulo 5: Administración & Gobernanza
  governance: {
    title: "Consola de Gobernanza y Administración",
    pendingRequests: "Solicitudes de Acreditación Pendientes",
    activeAdmins: "Administradores Institucionales Activos",
    institutionalAliases: "Mapeo de Alias Institucionales (ROR / UNAM)",
    auditLogs: "Bitácora de Auditoría",
    approve: "Aprobar",
    reject: "Rechazar",
    reasonPlaceholder: "Motivo de la resolución (opcional)...",
    noPending: "No hay solicitudes pendientes en este momento."
  },

  // Módulo 6: Asistente IA
  assistant: {
    title: "Asistente de Inteligencia Científica",
    modelSelect: "Modelo de Lenguaje (LLM)",
    inputPlaceholder: "Escribe tu consulta sobre investigadores, indicadores o publicaciones...",
    send: "Enviar Consulta",
    streaming: "Generando respuesta analítica...",
    clearHistory: "Limpiar Conversación",
    sourcesTitle: "Fuentes y Evidencia Citada",
    suggestionsTitle: "Consultas Frecuentes",
    suggestions: [
      "¿Cuáles son las líneas de investigación más citadas de la Facultad de Ciencias?",
      "Compara el desempeño e índice H de investigadores de Física y Matemáticas.",
      "Identifica los artículos con mayor impacto en ODS 13 (Acción por el Clima).",
      "Calcula la tasa de autocitas promedio de la dependencia seleccionada."
    ]
  },

  // Comunes & Botones
  common: {
    loading: "Cargando datos...",
    error: "Ha ocurrido un error al procesar la solicitud.",
    retry: "Reintentar",
    save: "Guardar",
    cancel: "Cancelar",
    search: "Buscar",
    export: "Exportar",
    language: "Idioma",
    total: "Total",
    all: "Todos"
  }
};
