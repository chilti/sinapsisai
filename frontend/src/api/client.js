/**
 * frontend/src/api/client.js
 * Cliente de Conexión HTTP y Streaming con el Servidor FastAPI (Puerto 5016 / Proxy /api)
 */

import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
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
  getHierarchyMetrics: async (institution, dependency, subdependency, period = 'all') => {
    const res = await api.get('/hierarchy/metrics', {
      params: { institution, dependency, subdependency, period }
    });
    return res.data;
  },

  // Académicos & Producción
  searchAcademics: async (q) => {
    const res = await api.get('/academics/search', { params: { q } });
    return res.data;
  },
  getAcademicProfile: async (name, orcid) => {
    const res = await api.get('/academics/profile', { params: { name, orcid } });
    return res.data;
  },
  getAcademicWorks: async (orcid, name) => {
    const res = await api.get('/academics/works', { params: { orcid, name } });
    return res.data;
  },

  // Citas Zero-Join
  getCitationsSummary: async (orcid, name) => {
    const res = await api.get('/citations/summary', { params: { orcid, name } });
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

  // Curación y Acreditación
  submitAccreditation: async (payload) => {
    const res = await api.post('/auth/accreditation/request', payload);
    return res.data;
  },
  getExcludedWorks: async (orcid) => {
    const res = await api.get('/auth/works/excluded', { params: { orcid } });
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

  // Reportes y Descargas
  downloadDossierMarkdown: async (academic_name, orcid) => {
    const res = await api.post('/reports/dossier/markdown', { academic_name, orcid }, { responseType: 'blob' });
    return res.data;
  },
  downloadDossierPdf: async (academic_name, orcid) => {
    const res = await api.post('/reports/dossier/pdf', { academic_name, orcid }, { responseType: 'blob' });
    return res.data;
  }
};

export default apiClient;
