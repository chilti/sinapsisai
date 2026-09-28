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
    generateDossier: "Gerar Dossier de Avaliação SNII / PRIDE",
    subtabs: {
      identity: "Resumo de Identidade",
      accreditation: "Credenciamento Institucional",
      citations: "Citações & Autocitações",
      dossier: "Gerador de Trajetória",
      curation: "Curadoria de Publicações"
    },
    btn_orcid_login: "Entrar com ORCID",
    btn_logout: "Encerrar Sessão",
    radio_identity_match: "Confirma sua identidade no Cadastro Oficial?",
    search_padron_placeholder: "Buscar meu nome no cadastro...",
    btn_confirm_profile: "Este sou eu (Vincular perfil)",
    form_register_submit: "Registrar e Sincronizar meu Perfil",
    btn_view_in_dashboard: "Ver minha Produção no Dashboard",
    btn_sync_apis: "Sincronizar Produção (Background)",
    badge_verified_orcid: "Identidade Digital Verificada com ORCID",
    accreditation_hierarchy: "Hierarquia Institucional de Adscrição",
    input_locked_entity: "Entidade / Dependência atribuída (Diretriz de Governança)",
    input_institutional_email: "E-mail institucional oficial",
    input_position: "Cargo ou Função Oficial",
    input_justification: "Justificativa ou observações adicionais",
    btn_submit_accreditation: "Enviar Solicitação de Credenciamento",
    kpi_net_citations: "Citações Líquidas (Sem Autocitações)",
    kpi_self_rate: "% Autocitações Diretas",
    table_citing_works: "Artigos Citantes do Pesquisador",
    dossier_period: "Período para Avaliação do Dossier",
    dossier_preview: "Pré-visualização da Trajetória Acadêmica",
    btn_download_pdf: "Baixar Relatório em PDF",
    btn_download_md: "Baixar Relatório em Markdown (.md)",
    filter_claim_placeholder: "Filtrar obras por título ou ano...",
    btn_disclaim_work: "Não é minha (Desvincular)",
    btn_restore_work: "Restaurar obra",
    btn_import_bibtex: "Importar BibTeX (.bib)"
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
    noPending: "Não há solicitações pendentes no momento.",
    tab_pending_requests: "Solicitações Pendentes",
    tab_active_admins: "Administradores Ativos",
    tab_aliases: "Gestão de Aliases",
    tab_pipelines: "Operações e Manutenção",
    btn_approve: "Aprovar",
    btn_reject: "Rejeitar",
    table_active_admins: "Tabela de Administradores Credenciados",
    btn_revoke_role: "Revogar Permissões",
    input_canonical_name: "Nome Canônico Oficial",
    input_alias_variant: "Alias ou Variante Léxica",
    btn_save_alias: "Salvar Alias Institucional",
    table_aliases: "Lista de Aliases Registrados",
    btn_cancel_task: "Interromper / Cancelar Processo",
    btn_refresh_log: "Atualizar Registro",
    btn_clear_history: "Limpar Histórico",
    input_e2e_academic: "Filtrar por Pesquisador específico",
    input_e2e_institution: "Instituição pai requerida",
    check_local_llm: "Usar recursos locais / LM Studio",
    btn_run_pipeline_e2e: "Executar Pipeline Completo E2E",
    btn_ror_extract: "2.1 Extrair Catálogo ROR",
    btn_ror_resolve: "2.2 Resolver SNII para ROR",
    btn_ror_neo4j_sync: "2.3 Sincronizar e Mesclar Neo4j",
    btn_run_missing_orcids: "Iniciar Varredura sem ORCID",
    check_sync_academics: "Sincronizar por Pesquisadores",
    check_sync_clickhouse: "Sincronizar com ClickHouse (--ch)",
    btn_harvest_works: "Iniciar Coleta de Obras",
    select_sync_phase: "Fase a executar no ClickHouse",
    btn_run_ch_sync: "Iniciar Sincronização CH",
    btn_compute_metrics: "Iniciar Cálculo de Métricas",
    status: {
      pending: "Pendente",
      approved: "Aprovado",
      rejected: "Rejeitado"
    }
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
    select_model: "Modelo LLM (LM Studio / API)",
    mode_selection: "Modo: Consulta Direta vs Agente Swarm",
    modes: {
      direct: "Chat Cienciométrico",
      agent: "Agente Autônomo Híbrido"
    },
    skills_filter: "Habilidades Ativas (ClickHouse, Neo4j, SNII)",
    btn_send: "Enviar Consulta",
    btn_clear: "Nova Conversa",
    btn_copy: "Copiar para Área de Transferência",
    btn_regenerate: "Regenerar Resposta",
    btn_export_chat: "Exportar Conversa (.md)",
    thinking_process: "Etapas de Raciocínio e Ferramentas Executadas",
    copied_alert: "Copiado para a área de transferência!",
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
  },

  theme: {
    title: "Tema Visual",
    light: "Claro",
    dark: "Escuro",
    navy: "Navy"
  }
};
