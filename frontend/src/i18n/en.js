/**
 * frontend/src/i18n/en.js
 * English strings dictionary (EN)
 */

export const en = {
  // Bar & Navigation
  appName: "Info TlachIA",
  appSubtitle: "Scientific Intelligence & Academic Output",
  tabs: {
    home: "Home",
    national: "National Overview",
    panorama: "Institutional Overview",
    researchers: "Researchers",
    maps: "Science Maps",
    mySpace: "My Space",
    governance: "Administration",
    assistant: "AI Assistant"
  },
  
  // Module 1: Institutional Overview
  panorama: {
    title: "Institutional Overview & Performance Mapping",
    institutionSelect: "Institution",
    dependencySelect: "Dependency / School",
    subdependencySelect: "Subdependency / Department",
    knowledgeArea: "Knowledge Area",
    sniiLevel: "Career Level",
    periodFilter: "Time Period",
    allInstitutions: "All Institutions",
    allDependencies: "All Dependencies",
    allSubdependencies: "All Subdependencies",
    allAreas: "All Areas",
    allLevels: "All Levels",
    metrics: {
      totalResearchers: "Active Researchers",
      totalWorks: "Indexed Publications",
      totalCitations: "Citations Received",
      fwciMean: "Mean FWCI",
      top10Percent: "Top 10% Output",
      oaRatio: "Open Access Rate"
    },
    charts: {
      sniiDistribution: "Distribution by Career Level",
      genderBalance: "Gender Balance by Scientific Area",
      temporalEvolution: "Temporal Evolution of Output and Citations",
      sdgImpact: "Contribution to UN Sustainable Development Goals (SDGs)"
    },
    exportReport: "Export Executive Report"
  },

  // Module 2: Researcher Profiles
  researchers: {
    searchPlaceholder: "Search by researcher name or ORCID identifier...",
    searching: "Searching researchers...",
    noResults: "No researchers matched your search query.",
    profile: {
      sniiBadge: "Researcher",
      active2026: "2026 Registry Confirmed",
      area: "Scientific Area",
      subdiscipline: "Subdiscipline",
      institution: "Affiliated Institution",
      dependency: "Dependency",
      subdependency: "Subdependency",
      orcid: "ORCID",
      hIndex: "H-Index",
      worksCount: "Publications",
      citationsCount: "Total Citations",
      netCitations: "Net Citations",
      selfCitations: "Self-Citations",
      top10Percent: "Top 10% Papers",
      fwci: "Average FWCI",
      citingCountries: "Citing Countries"
    },
    tabs: {
      production: "Academic Output",
      citations: "Citations and Self-Citations",
      coauthors: "Co-authorship Network",
      topics: "Thematic Evolution"
    },
    table: {
      title: "Work Title",
      journal: "Journal / Source",
      year: "Year",
      citations: "Cites",
      fwci: "FWCI",
      quartile: "Quartile",
      oa: "Open Access",
      role: "Authorship Role",
      viewWork: "View Work",
      disclaim: "Disclaim"
    },
    downloadDossier: "Download Dossier (PDF)",
    downloadMarkdown: "Download Report (Markdown)"
  },

  // Module 3: Science Maps
  maps: {
    title: "Knowledge Cartography & Semantic Spaces",
    spaceSelect: "Embedding Model",
    nomicModel: "Nomic Embed v1.5 (General Multidisciplinary)",
    specterModel: "SPECTER2 (Specialized Scientific Representation)",
    previewModel: "Fast Preliminary Sample",
    totalParticles: "Projected Works",
    clusterLegend: "Thematic Clusters",
    filterByCluster: "Filter by Thematic Group",
    searchParticle: "Search article on map...",
    resetZoom: "Reset View"
  },

  // Module 4: My Space
  mySpace: {
    title: "My Researcher Space",
    loginWithOrcid: "Sign In with ORCID",
    connectedAs: "Active session as",
    logout: "Sign Out",
    accreditationTitle: "Request Institutional Admin Accreditation",
    accreditationNotice: "By governance policy, accreditation requests are restricted to the lowest hierarchy unit of your affiliation.",
    requestAccreditationBtn: "Submit Accreditation Request",
    positionPlaceholder: "Institutional title (e.g. Academic Secretary, Library Coordinator)",
    emailPlaceholder: "Official institutional email (@unam.mx, etc.)",
    curationTitle: "Scientific Output Management & Curation",
    disclaimedWorks: "Disclaimed Works",
    restoreWork: "Restore Work",
    addCustomWork: "Upload Custom Work (.bib / RIS)",
    generateDossier: "Generate Academic Career Dossier",
    subtabs: {
      identity: "Identity Summary",
      accreditation: "Institutional Accreditation",
      citations: "Citations & Self-Citations",
      dossier: "Career Dossier Generator",
      curation: "Publications Curation"
    },
    btn_orcid_login: "Sign In with ORCID",
    btn_logout: "Sign Out",
    radio_identity_match: "Do you confirm your identity in the Official Census?",
    search_padron_placeholder: "Search my name in the census...",
    btn_confirm_profile: "This is me (Link profile)",
    form_register_submit: "Register and Synchronize My Profile",
    btn_view_in_dashboard: "View My Output in Dashboard",
    btn_sync_apis: "Synchronize Output (Background)",
    badge_verified_orcid: "Digital Identity Verified with ORCID",
    accreditation_hierarchy: "Institutional Affiliation Hierarchy",
    input_locked_entity: "Assigned Entity / Department (Governance Directive)",
    input_institutional_email: "Official Institutional Email",
    input_position: "Official Title or Role",
    input_justification: "Justification or additional notes",
    btn_submit_accreditation: "Submit Accreditation Request",
    kpi_net_citations: "Net Citations (Excluding Self-Citations)",
    kpi_self_rate: "% Direct Self-Citations",
    table_citing_works: "Citing Articles for this Researcher",
    dossier_period: "Evaluation Period for Dossier",
    dossier_preview: "Academic Career Preview",
    btn_download_pdf: "Download Report in PDF",
    btn_download_md: "Download Report in Markdown (.md)",
    filter_claim_placeholder: "Filter works by title or year...",
    btn_disclaim_work: "Not Mine (Disclaim)",
    btn_restore_work: "Restore work",
    btn_import_bibtex: "Import BibTeX (.bib)"
  },

  // Module 5: Governance & Administration
  governance: {
    title: "Governance & Administration Console",
    pendingRequests: "Pending Accreditation Requests",
    activeAdmins: "Active Institutional Admins",
    institutionalAliases: "Institutional Alias Mapping (ROR / UNAM)",
    auditLogs: "Audit Trail",
    approve: "Approve",
    reject: "Reject",
    reasonPlaceholder: "Resolution note (optional)...",
    noPending: "No pending requests at this time.",
    tab_pending_requests: "Pending Requests",
    tab_active_admins: "Active Admins",
    tab_aliases: "Alias Management",
    tab_pipelines: "Operations & Maintenance",
    btn_approve: "Approve",
    btn_reject: "Reject",
    table_active_admins: "Accredited Institutional Admins Table",
    btn_revoke_role: "Revoke Permissions",
    input_canonical_name: "Official Canonical Name",
    input_alias_variant: "Alias or Lexical Variant",
    btn_save_alias: "Save Institutional Alias",
    table_aliases: "Registered Aliases Catalog",
    btn_cancel_task: "Stop / Cancel Process",
    btn_refresh_log: "Refresh Log",
    btn_clear_history: "Clear History",
    input_e2e_academic: "Filter by specific Academic",
    input_e2e_institution: "Parent institution required",
    check_local_llm: "Use local resources / LM Studio",
    btn_run_pipeline_e2e: "Execute Full E2E Pipeline",
    btn_ror_extract: "2.1 Extract ROR Catalog",
    btn_ror_resolve: "2.2 Resolve Researchers to ROR",
    btn_ror_neo4j_sync: "2.3 Sync & Merge Neo4j",
    btn_run_missing_orcids: "Start Missing ORCID Sweep",
    check_sync_academics: "Sync by Academics",
    check_sync_clickhouse: "Sync with ClickHouse (--ch)",
    btn_harvest_works: "Start Works Harvesting",
    select_sync_phase: "ClickHouse Execution Phase",
    btn_run_ch_sync: "Start CH Synchronization",
    btn_compute_metrics: "Start Metrics Computation",
    status: {
      pending: "Pending",
      approved: "Approved",
      rejected: "Rejected"
    }
  },

  // Module 6: AI Assistant
  assistant: {
    title: "Scientific Intelligence AI Assistant",
    modelSelect: "Language Model (LLM)",
    inputPlaceholder: "Ask anything about researchers, metrics, or scientific outputs...",
    send: "Send Query",
    streaming: "Generating analytical response...",
    clearHistory: "Clear Chat",
    sourcesTitle: "Cited Sources & Evidence",
    suggestionsTitle: "Suggested Prompts",
    select_model: "LLM Model (LM Studio / API)",
    mode_selection: "Mode: Direct Query vs Swarm Agent",
    modes: {
      direct: "Scientometric Direct Chat",
      agent: "Hybrid Autonomous Agent"
    },
    skills_filter: "Active Skills (ClickHouse, Neo4j, Registry)",
    btn_send: "Send Query",
    btn_clear: "New Conversation",
    btn_copy: "Copy to Clipboard",
    btn_regenerate: "Regenerate Response",
    btn_export_chat: "Export Chat (.md)",
    thinking_process: "Reasoning Steps and Executed Tools",
    copied_alert: "Copied to clipboard!",
    suggestions: [
      "What are the most cited research topics in the School of Sciences?",
      "Compare the performance and H-index of Physics and Mathematics researchers.",
      "Identify the articles with highest impact on SDG 13 (Climate Action).",
      "Calculate the average self-citation rate of the selected dependency."
    ]
  },

  // Common & Buttons
  common: {
    loading: "Loading data...",
    error: "An error occurred while processing the request.",
    retry: "Retry",
    save: "Save",
    cancel: "Cancel",
    search: "Search",
    export: "Export",
    language: "Language",
    total: "Total",
    all: "All"
  },

  theme: {
    title: "Visual Theme",
    light: "Light",
    dark: "Dark",
    navy: "Navy"
  }
};
