/**
 * frontend/src/store/useAppStore.js
 * Store Global de Estado de la Aplicación (Zustand)
 */

import { create } from 'zustand';
import { getDictionary } from '../i18n/index.js';

export const useAppStore = create((set, get) => ({
  // Pestaña Activa
  activeTab: 'panorama', // 'panorama', 'researchers', 'maps', 'mySpace', 'governance', 'assistant'
  setActiveTab: (tab) => set({ activeTab: tab }),

  // Idioma (Persistente en localStorage)
  language: typeof window !== 'undefined' ? (localStorage.getItem('tlachia_lang') || 'es') : 'es',
  setLanguage: (lang) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('tlachia_lang', lang);
    }
    set({ language: lang });
  },

  // Tema Visual ('claro' | 'oscuro' | 'navy') - Blanco por defecto
  theme: typeof window !== 'undefined' ? (localStorage.getItem('tlachia_theme') || 'claro') : 'claro',
  setTheme: (theme) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('tlachia_theme', theme);
      document.documentElement.setAttribute('data-theme', theme);
    }
    set({ theme });
  },

  // Obtener diccionario actual reactivo
  t: () => getDictionary(get().language),

  // Filtros Institucionales Globales
  selectedInstitution: 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)',
  selectedDependency: 'FACULTAD DE CIENCIAS',
  selectedSubdependency: '',
  selectedArea: '',
  selectedLevel: '',
  selectedPeriod: 'all',

  setSelectedInstitution: (inst) => set({ 
    selectedInstitution: inst, 
    selectedDependency: '', 
    selectedSubdependency: '' 
  }),
  setSelectedDependency: (dep) => set({ 
    selectedDependency: dep, 
    selectedSubdependency: '' 
  }),
  setSelectedSubdependency: (sub) => set({ selectedSubdependency: sub }),
  setSelectedArea: (area) => set({ selectedArea: area }),
  setSelectedLevel: (level) => set({ selectedLevel: level }),
  setSelectedPeriod: (period) => set({ selectedPeriod: period }),

  // Investigador Seleccionado
  selectedResearcherName: 'PARDO CEMO, ANNIE',
  selectedResearcherOrcid: '0000-0003-2168-9073',
  setSelectedResearcher: (name, orcid = '') => set({
    selectedResearcherName: name,
    selectedResearcherOrcid: orcid
  }),

  // Sesión y Autenticación
  userSession: {
    isAuthenticated: false,
    orcid: null,
    name: null,
    role: 'guest', // 'guest', 'investigador', 'admin_institucional', 'super_admin'
    institution: null,
    token: null
  },
  setUserSession: (session) => set({ userSession: { ...get().userSession, ...session } }),
  logout: () => set({
    userSession: {
      isAuthenticated: false,
      orcid: null,
      name: null,
      role: 'guest',
      institution: null,
      token: null
    }
  }),

  // Notificaciones Flash
  notification: null,
  setNotification: (notif) => {
    set({ notification: notif });
    if (notif) {
      setTimeout(() => {
        set({ notification: null });
      }, 4000);
    }
  }
}));

export default useAppStore;
