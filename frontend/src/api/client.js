/**
 * frontend/src/api/client.js
 * Cliente de Conexión HTTP y Streaming con el Servidor FastAPI (Puerto 5016 / Proxy /api)
 */

import axios from 'axios';

export const getBaseApiUrl = () => {
  if (typeof window !== 'undefined') {
    const path = window.location.pathname;
    if (path.includes('/sinapsisai_dev')) return '/sinapsisai_dev/api';
    if (path.includes('/sinapsisai')) return '/sinapsisai/api';
    if (path.includes('/infotlachia')) return '/infotlachia/api';
  }
  return '/api';
};

const api = axios.create({
  baseURL: getBaseApiUrl(),
  timeout: 45000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// Interceptor para agregar token si existe
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('tlachia_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const apiClient = {
  // Jerarquía Institucional
  getInstitutions: async () => {
    const res = await api.get('/hierarchy/institutions');
    return res.data;
  },
  getDependencies: async (institution) => {
    const res = await api.get('/hierarchy/dependencies', { params: { institution } });
    return res.data;
  },
  getSubdependencies: async (institution, dependency) => {
    const res = await api.get('/hierarchy/subdependencies', { params: { institution, dependency } });
    return res.data;
  },
  getHierarchyMetrics: async (institution, dependency, subdependency, period = 'all', viewMode = 'capacidad_instalada') => {
    const res = await api.get('/hierarchy/metrics', {
      params: { institution, dependency, subdependency, period, view_mode: viewMode }
    });
    return res.data;
  },
  getHierarchyPapers: async (params) => {
    const res = await api.get('/hierarchy/papers', { params });
    return res.data;
  },

  // Académicos & Producción
  searchAcademics: async (q) => {
    const res = await api.get('/academics/search', { params: { q } });
    return res.data;
  },
  getAcademicsList: async (institution, dependency, subdependency, viewMode = 'capacidad_instalada') => {
    const res = await api.get('/academics/list', {
      params: { institution, dependency, subdependency, view_mode: viewMode }
    });
    return res.data;
  },
  getAcademicProfile: async (name, orcid) => {
    const res = await api.get('/academics/profile', { params: { name, orcid } });
    return res.data;
  },
  getAcademicWorks: async (orcid, name, extra = {}) => {
    const params = typeof orcid === 'object' && orcid !== null ? orcid : { orcid, name, ...extra };
    const res = await api.get('/academics/works', { params });
    return res.data;
  },
  getAcademicUmap: async (name, entity, institution, viewMode = 'capacidad_instalada') => {
    const params = { name, view_mode: viewMode };
    if (entity) params.entity = entity;
    if (institution) params.institution = institution;
    const res = await api.get('/academics/umap', { params });
    return res.data;
  },

  // Citas Zero-Join
  getCitationsSummary: async (orcid, name) => {
    const res = await api.get('/citations/summary', { params: { orcid, name } });
    return res.data;
  },
  getCitingWorks: async (name, orcid, limit = 250) => {
    const res = await api.get('/citations/citing-works', { params: { name, orcid, limit } });
    return res.data;
  },

  // Mapas de la Ciencia
  getMapSpaces: async () => {
    const res = await api.get('/maps/spaces');
    return res.data;
  },
  getMapClusters: async (space = 'preview') => {
    const res = await api.get('/maps/clusters', { params: { space } });
    return res.data;
  },
  getResearchersUmap: async (limit = 1200, institution = '', domain = '') => {
    const params = { limit };
    if (institution) params.institution = institution;
    if (domain) params.domain = domain;
    const res = await api.get('/maps/researchers-umap', { params });
    return res.data;
  },

  // Curación, Acreditación & Auth
  getOrcidLoginUrl: async (redirectUri) => {
    const params = redirectUri ? { redirect_uri: redirectUri } : {};
    const res = await api.get('/auth/orcid/login-url', { params });
    return res.data;
  },
  exchangeOrcidToken: async (code, redirectUri) => {
    const payload = { code };
    if (redirectUri) payload.redirect_uri = redirectUri;
    const res = await api.post('/auth/orcid/token', payload);
    return res.data;
  },
  submitAccreditation: async (payload) => {
    const res = await api.post('/auth/accreditation/request', payload);
    return res.data;
  },
  getPendingAccreditations: async () => {
    const res = await api.get('/auth/accreditation/requests');
    return res.data;
  },
  getActiveAdmins: async () => {
    const res = await api.get('/auth/accreditation/admins');
    return res.data;
  },
  approveAccreditation: async (payload) => {
    const res = await api.post('/auth/accreditation/approve', payload);
    return res.data;
  },
  rejectAccreditation: async (payload) => {
    const res = await api.post('/auth/accreditation/reject', payload);
    return res.data;
  },
  revokeAccreditation: async (payload) => {
    const res = await api.post('/auth/accreditation/revoke', payload);
    return res.data;
  },
  getInstitutionalAliases: async (institution) => {
    const res = await api.get('/auth/institutions/aliases', { params: { institution } });
    return res.data;
  },
  createInstitutionalAlias: async (payload) => {
    const res = await api.post('/auth/institutions/aliases', payload);
    return res.data;
  },
  getExcludedWorks: async (orcid) => {
    const res = await api.get('/auth/works/excluded', { params: { orcid } });
    return res.data;
  },
  getCustomWorks: async (orcid) => {
    const res = await api.get('/auth/works/custom', { params: { orcid } });
    return res.data;
  },
  disclaimWork: async (payload) => {
    const res = await api.post('/auth/works/disclaim', payload);
    return res.data;
  },
  restoreWork: async (payload) => {
    const res = await api.post('/auth/works/restore', payload);
    return res.data;
  },
  importBibtex: async (payload) => {
    const res = await api.post('/auth/works/import-bibtex', payload);
    return res.data;
  },
  triggerPipeline: async (payload) => {
    const res = await api.post('/auth/pipeline/trigger', payload);
    return res.data;
  },

  // Reportes y Descargas
  getDossierData: async (academic_name, orcid) => {
    const res = await api.post('/reports/dossier/data', { academic_name, orcid });
    return res.data;
  },
  downloadDossierMarkdown: async (academic_name, orcid) => {
    const res = await api.post('/reports/dossier/markdown', { academic_name, orcid }, { responseType: 'blob' });
    return res.data;
  },
  downloadDossierPdf: async (academic_name, orcid) => {
    const res = await api.post('/reports/dossier/pdf', { academic_name, orcid }, { responseType: 'blob' });
    return res.data;
  },
  getSniiRorStats: async () => {
    const res = await api.get('/reports/snii-ror-stats');
    return res.data;
  },
  getSniiAuditReportUrl: (download = false) => {
    const base = getBaseApiUrl();
    return `${base}/reports/snii-audit${download ? '?download=true' : ''}`;
  },
  requestAIReportJob: async (payload) => {
    const res = await api.post('/reports/ai-report/request-job', payload);
    return res.data;
  },
  getAIReportJobStatus: async (jobId) => {
    const res = await api.get(`/reports/ai-report/job-status/${jobId}`);
    return res.data;
  },
  getAIReportJobResultUrl: (jobId, download = false) => {
    const base = getBaseApiUrl();
    return `${base}/reports/ai-report/job-result/${jobId}${download ? '?download=true' : ''}`;
  },

  // Asistente IA
  clearChatSession: async (session_id = 'default_session') => {
    const res = await api.post('/assistant/clear', null, { params: { session_id } });
    return res.data;
  }
};

export default apiClient;

