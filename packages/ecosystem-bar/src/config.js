/**
 * packages/ecosystem-bar/src/config.js
 * Configuración unificada de las 4 aplicaciones del Ecosistema Científico TlachIA
 */

export const ECOSYSTEM_APPS = [
  {
    id: "sinapsisai",
    name: "Info TlachIA",
    shortName: "Info TlachIA",
    tagline: {
      es: "Trayectoria y Producción Académica",
      pt: "Trajetória e Produção Acadêmica",
      en: "Academic Trajectory & Output"
    },
    badge: "Trayectoria",
    badgeColor: "#00f2fe",
    path: "/sinapsisai/",
    devUrl: "http://localhost:3006",
    prodUrl: "/sinapsisai/",
    icon: "GraduationCap",
    accentColor: "linear-gradient(135deg, #00f2fe 0%, #4facfe 100%)",
    glowColor: "rgba(0, 242, 254, 0.35)",
    activeBorder: "#00f2fe"
  },
  {
    id: "revistaslatam",
    name: "Revistas LATAM",
    shortName: "Revistas LATAM",
    tagline: {
      es: "Cartografía de 7,494 Revistas Científicas Iberoamericanas",
      pt: "Cartografia de 7.494 Revistas Científicas Ibero-Americanas",
      en: "Cartography of 7,494 Ibero-American Scientific Journals"
    },
    badge: "Revistas & Cartografía",
    badgeColor: "#38ef7d",
    path: "/revistaslatam/",
    devUrl: "https://dinamica1.fciencias.unam.mx/revistaslatam/",
    prodUrl: "https://dinamica1.fciencias.unam.mx/revistaslatam/",
    icon: "BookOpen",
    accentColor: "linear-gradient(135deg, #11998e 0%, #38ef7d 100%)",
    glowColor: "rgba(56, 239, 125, 0.35)",
    activeBorder: "#38ef7d"
  },
  {
    id: "knomap",
    name: "KnoMap",
    shortName: "KnoMap SOM",
    tagline: {
      es: "Mapas Autoorganizados (SOM) y Topología de la Ciencia",
      pt: "Mapas Auto-Organizados (SOM) e Topologia da Ciência",
      en: "Self-Organizing Maps (SOM) & Science Topology"
    },
    badge: "SOM & Topología",
    badgeColor: "#f39c12",
    path: "/knomap/",
    devUrl: "https://dinamica1.fciencias.unam.mx/knomap/",
    prodUrl: "https://dinamica1.fciencias.unam.mx/knomap/",
    icon: "Network",
    accentColor: "linear-gradient(135deg, #f12711 0%, #f5af19 100%)",
    glowColor: "rgba(243, 156, 18, 0.35)",
    activeBorder: "#f39c12"
  },
  {
    id: "tlachia_metrics",
    name: "TlachIA Metrics",
    shortName: "TlachIA Metrics",
    tagline: {
      es: "Motor Cienciométrico, FWCI, Percentiles e Impacto ODS",
      pt: "Motor Cienciométrico, FWCI, Percentis e Impacto ODS",
      en: "Scientometric Engine, FWCI, Percentiles & SDG Impact"
    },
    badge: "Métricas Avanzadas",
    badgeColor: "#c084fc",
    path: "/tlachiametrics/",
    devUrl: "https://dinamica1.fciencias.unam.mx/tlachiametrics/",
    prodUrl: "https://dinamica1.fciencias.unam.mx/tlachiametrics/",
    icon: "Activity",
    accentColor: "linear-gradient(135deg, #7928ca 0%, #c084fc 100%)",
    glowColor: "rgba(192, 132, 252, 0.35)",
    activeBorder: "#c084fc"
  }
];

export const SUITE_I18N = {
  es: {
    suiteTitle: "Info TlachIA: Infraestructura para la Ciencia Abierta",
    suiteSubtitle: "Plataformas Integradas de Inteligencia Científica y Bibliometría",
    currentApp: "Aplicación Activa",
    switchApp: "Cambiar de aplicación",
    exploreEcosystem: "Explorar Ecosistema",
    version: "v2.0"
  },
  pt: {
    suiteTitle: "Info TlachIA: Infraestrutura para a Ciência Aberta",
    suiteSubtitle: "Plataformas Integradas de Inteligência Científica e Bibliometria",
    currentApp: "Aplicação Ativa",
    switchApp: "Trocar de aplicação",
    exploreEcosystem: "Explorar Ecossistema",
    version: "v2.0"
  },
  en: {
    suiteTitle: "Info TlachIA: Infrastructure for Open Science",
    suiteSubtitle: "Integrated Scientific Intelligence & Bibliometrics Platforms",
    currentApp: "Active Application",
    switchApp: "Switch application",
    exploreEcosystem: "Explore Ecosystem",
    version: "v2.0"
  }
};
