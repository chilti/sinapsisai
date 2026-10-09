/**
 * frontend/src/store/useAppStore.js
 * Store Global de Estado de la Aplicación (Zustand)
 */

import { create } from 'zustand';
import { getDictionary } from '../i18n/index.js';

export const isUserAdmin = (userSession) => {
  if (!userSession) return false;
  if (userSession.is_admin === true) return true;
  const role = String(userSession.role || '').toLowerCase();
  return (
    role === 'super_admin' ||
    role === 'admin' ||
    role === 'administrador' ||
    role === 'admin_institucional' ||
    role === 'institutional_admin' ||
    role === 'curator' ||
    role.includes('admin')
  );
};

export const canViewAllResearchers = (userSession) => {
  if (!userSession || !userSession.isAuthenticated) return false;
  // Ningún usuario logeado mediante ORCID puede ver el directorio de todos los perfiles.
  // Es exclusivo para la sesión autenticada con las credenciales de SUPERUSER_USERNAME.
  if (userSession.orcid) return false;
  return userSession.can_view_all_researchers === true;
};

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
  selectedResearcherName: '',
  selectedResearcherOrcid: '',
  setSelectedResearcher: (name, orcid = '') => set({
    selectedResearcherName: name,
    selectedResearcherOrcid: orcid
  }),

  // Historial del Asistente Científico (Persistente entre pestañas)
  assistantMessages: [
    {
      role: 'assistant',
      content: '¡Hola! Soy el Asistente de Inteligencia Científica de Info TlachIA. Puedo responder preguntas sobre la producción académica de investigadoras e investigadores, indicadores de impacto, redes de coautoría o cartografía temática.',
      thoughts: 'Inicialización de memoria conversacional y registro de herramientas cienciométricas (ClickHouse, Neo4j, Padrón de Investigadoras e Investigadores).'
    }
  ],
  setAssistantMessages: (updaterOrMsgs) => {
    set((state) => ({
      assistantMessages: typeof updaterOrMsgs === 'function' ? updaterOrMsgs(state.assistantMessages) : updaterOrMsgs
    }));
  },
  resetAssistantMessages: () => {
    set({
      assistantMessages: [
        {
          role: 'assistant',
          content: '¡Hola! Soy el Asistente de Inteligencia Científica de Info TlachIA. Puedo responder preguntas sobre la producción académica de investigadoras e investigadores, indicadores de impacto, redes de coautoría o cartografía temática.',
          thoughts: 'Inicialización de memoria conversacional y registro de herramientas cienciométricas (ClickHouse, Neo4j, Padrón de Investigadoras e Investigadores).'
        }
      ]
    });
  },

  // Modelo de Lenguaje Activo (C3 GPT-OSS 120B preferido por defecto para admins)
  selectedLlmModel: typeof window !== 'undefined' ? (localStorage.getItem('tlachia_selected_model') || 'gpt-oss-120b') : 'gpt-oss-120b',
  setSelectedLlmModel: (model) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('tlachia_selected_model', model);
    }
    set({ selectedLlmModel: model });
  },

  // Sesión y Autenticación
  userSession: (() => {
    if (typeof window !== 'undefined') {
      try {
        const saved = localStorage.getItem('tlachia_user');
        if (saved) {
          const parsed = JSON.parse(saved);
          if (isUserAdmin(parsed)) {
            parsed.is_admin = true;
          }
          return parsed;
        }
      } catch (e) {}
    }
    return {
      isAuthenticated: false,
      orcid: null,
      name: null,
      role: 'guest',
      institution: null,
      token: null,
      is_admin: false
    };
  })(),
  setUserSession: (session) => {
    const updated = { ...get().userSession, ...session };
    if (isUserAdmin(updated)) {
      updated.is_admin = true;
    }
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
        token: null,
        is_admin: false
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
