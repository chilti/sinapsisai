/**
 * frontend/src/i18n/pt.js
 * Dicionário de cadeias em Português (PT)
 */

export const pt = {
  // Franja & Navegação
  appName: "SNII Info TlachIA",
  appSubtitle: "Inteligência Científica do Registro SNII e Produção Acadêmica",
  tabs: {
    panorama: "Panorama Institucional",
    researchers: "Pesquisadores",
    maps: "Mapas da Ciência",
    mySpace: "Meu Espaço",
    governance: "Administração",
    assistant: "Assistente IA"
  },
  
  // Módulo 1: Panorama Institucional
  panorama: {
    title: "Panorama Institucional e Cartografia de Desempenho",
    institutionSelect: "Instituição",
    dependencySelect: "Dependência / Faculdade",
    subdependencySelect: "Subdependência / Centro",
    knowledgeArea: "Área de Conhecimento SNII",
    sniiLevel: "Nível SNII",
    periodFilter: "Período Temporal",
    allInstitutions: "Todas as Instituições",
    allDependencies: "Todas as Dependências",
    allSubdependencies: "Todas as Subdependências",
    allAreas: "Todas as Áreas",
    allLevels: "Todos os Níveis",
    metrics: {
      totalResearchers: "Pesquisadores Ativos",
      totalWorks: "Publicações Indexadas",
      totalCitations: "Citações Recebidas",
      fwciMean: "FWCI Médio",
      top10Percent: "Produção Top 10%",
      oaRatio: "Taxa de Acesso Aberto"
    },
    charts: {
      sniiDistribution: "Distribuição por Nível SNII (Candidato a Nível III / Emérito)",
      genderBalance: "Equidade de Gênero por Área Científica",
      temporalEvolution: "Evolução Temporal de Produção e Citações",
      sdgImpact: "Contribuição aos Objetivos de Desenvolvimento Sustentável (ODS)"
    },
    exportReport: "Exportar Relatório Executivo"
  },

  // Módulo 2: Perfis de Pesquisadores
  researchers: {
    searchPlaceholder: "Buscar por nome de pesquisador ou identificador ORCID...",
    searching: "Buscando pesquisadores...",
    noResults: "Nenhum pesquisador encontrado correspondente à busca.",
    profile: {
      sniiBadge: "SNII",
      active2026: "Registro 2026 Confirmado",
      area: "Área Científica",
      subdiscipline: "Subdisciplina",
      institution: "Instituição de Vinculação",
      dependency: "Dependência",
      subdependency: "Subdependência",
      orcid: "ORCID",
      hIndex: "Índice H",
      worksCount: "Publicações",
      citationsCount: "Citações Totais",
      netCitations: "Citações Líquidas",
      selfCitations: "Autocitações",
      top10Percent: "Artigos no Top 10%",
      fwci: "FWCI Médio",
      citingCountries: "Países Citantes"
    },
    tabs: {
      production: "Produção Acadêmica",
      citations: "Análise de Citações (Zero-Join)",
      coauthors: "Rede de Coautorias",
      topics: "Evolução Temática"
    },
    table: {
      title: "Título da Obra",
      journal: "Revista / Fonte",
      year: "Ano",
      citations: "Citações",
      fwci: "FWCI",
      quartile: "Quartil",
      oa: "Acesso Aberto",
      role: "Papel de Autoria",
      viewWork: "Ver Obra",
      disclaim: "Desvincular"
    },
    downloadDossier: "Baixar Dossier (PDF)",
    downloadMarkdown: "Baixar Relatório (Markdown)"
  },

  // Módulo 3: Mapas da Ciência
  maps: {
    title: "Cartografia do Conhecimento e Espaços Semânticos",
    spaceSelect: "Modelo de Embedding",
    nomicModel: "Nomic Embed v1.5 (Multidisciplinar Geral)",
    specterModel: "SPECTER2 (Representação Científica Especializada)",
    previewModel: "Amostra Preliminar Rápida",
    totalParticles: "Artigos Projetados",
    clusterLegend: "Clusters Temáticos",
    filterByCluster: "Filtrar por Grupo Temático",
    searchParticle: "Buscar artigo no mapa...",
    resetZoom: "Redefinir Visualização"
  },

  // Módulo 4: Meu Espaço
  mySpace: {
    title: "Meu Espaço de Pesquisador",
    loginWithOrcid: "Entrar com ORCID",
    connectedAs: "Sessão ativa como",
    logout: "Sair",
    accreditationTitle: "Solicitar Credenciamento como Administrador Institucional",
    accreditationNotice: "Por diretriz de governança, a solicitação é restrita ao nível institucional mais baixo de sua hierarquia oficial.",
    requestAccreditationBtn: "Enviar Solicitação de Credenciamento",
    positionPlaceholder: "Cargo institucional (ex. Secretário Acadêmico, Coordenador de Biblioteca)",
    emailPlaceholder: "E-mail institucional oficial (@unam.mx, etc.)",
    curationTitle: "Gestão e Curadoria de Produção Científica",
    disclaimedWorks: "Obras Desvinculadas",
    restoreWork: "Reincorporar Obra",
    addCustomWork: "Carregar Obra Manualmente (.bib / RIS)",
    generateDossier: "Gerar Dossier de Avaliação SNII / PRIDE"
  },

  // Módulo 5: Administração & Governança
  governance: {
    title: "Console de Governança e Administração",
    pendingRequests: "Solicitações de Credenciamento Pendentes",
    activeAdmins: "Administradores Institucionais Ativos",
    institutionalAliases: "Mapeamento de Aliases Institucionais (ROR / UNAM)",
    auditLogs: "Registro de Auditoria",
    approve: "Aprovar",
    reject: "Rejeitar",
    reasonPlaceholder: "Motivo da decisão (opcional)...",
    noPending: "Não há solicitações pendentes no momento."
  },

  // Módulo 6: Assistente IA
  assistant: {
    title: "Assistente de Inteligência Científica",
    modelSelect: "Modelo de Linguagem (LLM)",
    inputPlaceholder: "Digite sua consulta sobre pesquisadores, indicadores ou publicações...",
    send: "Enviar Consulta",
    streaming: "Gerando resposta analítica...",
    clearHistory: "Limpar Conversa",
    sourcesTitle: "Fontes e Evidências Citadas",
    suggestionsTitle: "Consultas Frequentes",
    suggestions: [
      "Quais são as linhas de pesquisa mais citadas da Faculdade de Ciências?",
      "Compare o desempenho e índice H de pesquisadores de Física e Matemática.",
      "Identifique os artigos com maior impacto no ODS 13 (Ação Climática).",
      "Calcule a taxa média de autocitações da dependência selecionada."
    ]
  },

  // Comuns & Botões
  common: {
    loading: "Carregando dados...",
    error: "Ocorreu um erro ao processar a solicitação.",
    retry: "Tentar novamente",
    save: "Salvar",
    cancel: "Cancelar",
    search: "Buscar",
    export: "Exportar",
    language: "Idioma",
    total: "Total",
    all: "Todos"
  }
};
