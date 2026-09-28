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
    generateDossier: "Generar Dossier de Evaluación SNII / PRIDE",
    subtabs: {
      identity: "Resumen de Identidad",
      accreditation: "Acreditación Institucional",
      citations: "Citas & Autocitas",
      dossier: "Generador de Trayectoria",
      curation: "Curación de Publicaciones"
    },
    btn_orcid_login: "Iniciar Sesión con ORCID",
    btn_logout: "Cerrar Sesión",
    radio_identity_match: "¿Confirmas tu identidad en el Padrón Oficial?",
    search_padron_placeholder: "Buscar mi nombre en el padrón...",
    btn_confirm_profile: "Este soy yo (Vincular perfil)",
    form_register_submit: "Registrar y Sincronizar mi Perfil",
    btn_view_in_dashboard: "Ver mi Producción en el Dashboard",
    btn_sync_apis: "Sincronizar Producción (Background)",
    badge_verified_orcid: "Identidad Digital Verificada con ORCID",
    accreditation_hierarchy: "Jerarquía Institucional de Adscripción",
    input_locked_entity: "Entidad / Dependencia asignada (Directriz de Gobernanza)",
    input_institutional_email: "Correo electrónico institucional",
    input_position: "Puesto o Cargo Oficial",
    input_justification: "Justificación o notas adicionales",
    btn_submit_accreditation: "Enviar Solicitud de Acreditación",
    kpi_net_citations: "Citas Netas (Sin Autocitas)",
    kpi_self_rate: "% Autocitas Directas",
    table_citing_works: "Artículos Citantes del Investigador",
    dossier_period: "Periodo a Evaluar para el Dossier",
    dossier_preview: "Vista Previa de Trayectoria Académica",
    btn_download_pdf: "Descargar Reporte en PDF",
    btn_download_md: "Descargar Reporte en Markdown (.md)",
    filter_claim_placeholder: "Filtrar obras por título o año...",
    btn_disclaim_work: "No es mía (Desvincular)",
    btn_restore_work: "Restaurar obra",
    btn_import_bibtex: "Importar BibTeX (.bib)"
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
    noPending: "No hay solicitudes pendientes en este momento.",
    tab_pending_requests: "Solicitudes Pendientes",
    tab_active_admins: "Administradores Activos",
    tab_aliases: "Gestión de Alias",
    tab_pipelines: "Operaciones y Mantenimiento",
    btn_approve: "Aprobar",
    btn_reject: "Rechazar",
    table_active_admins: "Tabla de Administradores Acreditados",
    btn_revoke_role: "Revocar Permisos",
    input_canonical_name: "Nombre Canónico Oficial",
    input_alias_variant: "Alias o Variante Léxica",
    btn_save_alias: "Guardar Alias Institucional",
    table_aliases: "Lista de Alias Registrados",
    btn_cancel_task: "Detener / Cancelar Proceso",
    btn_refresh_log: "Actualizar Bitácora",
    btn_clear_history: "Limpiar Historial",
    input_e2e_academic: "Filtrar por Académico específico",
    input_e2e_institution: "Institución padre requerida",
    check_local_llm: "Usar recursos locales / LM Studio",
    btn_run_pipeline_e2e: "Ejecutar Pipeline Completo E2E",
    btn_ror_extract: "2.1 Extraer Catálogo ROR",
    btn_ror_resolve: "2.2 Resolver SNII a ROR",
    btn_ror_neo4j_sync: "2.3 Sincronizar y Fusionar Neo4j",
    btn_run_missing_orcids: "Iniciar Barrido sin ORCID",
    check_sync_academics: "Sincronizar por Académicos",
    check_sync_clickhouse: "Sincronizar con ClickHouse (--ch)",
    btn_harvest_works: "Iniciar Cosecha de Obras",
    select_sync_phase: "Fase a ejecutar en ClickHouse",
    btn_run_ch_sync: "Iniciar Sincronización CH",
    btn_compute_metrics: "Iniciar Cómputo de Métricas",
    status: {
      pending: "Pendiente",
      approved: "Aprobado",
      rejected: "Rechazado"
    }
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
    select_model: "Modelo LLM (LM Studio / API)",
    mode_selection: "Modo: Consulta Directa vs Agente Swarm",
    modes: {
      direct: "Chat Cienciométrico",
      agent: "Agente Autónomo Híbrido"
    },
    skills_filter: "Habilidades Activas (ClickHouse, Neo4j, SNII)",
    btn_send: "Enviar Consulta",
    btn_clear: "Nueva Conversación",
    btn_copy: "Copiar al Portapapeles",
    btn_regenerate: "Regenerar Respuesta",
    btn_export_chat: "Exportar Conversación (.md)",
    thinking_process: "Pasos de Razonamiento y Herramientas Ejecutadas",
    copied_alert: "¡Copiado al portapapeles!",
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
  },

  theme: {
    title: "Tema Visual",
    light: "Claro",
    dark: "Oscuro",
    navy: "Navy"
  }
};
