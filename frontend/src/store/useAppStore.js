/**
 * frontend/src/store/useAppStore.js
 * Store Global de Estado de la Aplicación (Zustand)
 */

import { create } from 'zustand';
import { getDictionary } from '../i18n/index.js';

export const useAppStore = create((set, get) => ({
  // Pestaña Activa (Inicio desactivada/oculta; Panorama Nacional por defecto)
  activeTab: 'national', // 'national', 'panorama', 'researchers', 'maps', 'mySpace', 'governance', 'assistant'
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
  selectedDependency: 'SECRETARIA GENERAL',
  selectedSubdependency: 'FACULTAD DE CIENCIAS',
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
  userSession: (() => {
    if (typeof window !== 'undefined') {
      try {
        const saved = localStorage.getItem('tlachia_user');
        if (saved) return JSON.parse(saved);
      } catch (e) {}
    }
    return {
      isAuthenticated: false,
      orcid: null,
      name: null,
      role: 'guest',
      institution: null,
      token: null
    };
  })(),
  setUserSession: (session) => {
    const updated = { ...get().userSession, ...session };
    if (typeof window !== 'undefined') {
      localStorage.setItem('tlachia_user', JSON.stringify(updated));
      if (updated.token) {
        localStorage.setItem('tlachia_token', updated.token);
      }
    }
    set({ userSession: updated });
  },
  logout: () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('tlachia_user');
      localStorage.removeItem('tlachia_token');
    }
    set({
      userSession: {
        isAuthenticated: false,
        orcid: null,
        name: null,
        role: 'guest',
        institution: null,
        token: null
      }
    });
  },

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
