/**
 * frontend/src/i18n/en.js
 * English strings dictionary (EN)
 */

export const en = {
  // Bar & Navigation
  appName: "SNII Info TlachIA",
  appSubtitle: "Scientific Intelligence for SNII Registry and Academic Output",
  tabs: {
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
    knowledgeArea: "SNII Knowledge Area",
    sniiLevel: "SNII Level",
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
      sniiDistribution: "Distribution by SNII Level (Candidate to Level III / Emeritus)",
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
      sniiBadge: "SNII",
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
      citations: "Citation Analysis (Zero-Join)",
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
    generateDossier: "Generate SNII / PRIDE Evaluation Dossier"
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
    noPending: "No pending requests at this time."
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
  }
};
