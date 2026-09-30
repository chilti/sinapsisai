/**
 * frontend/src/App.jsx
 * Componente Principal de la Aplicación Info TlachIA
 */

import React from 'react';
import { useAppStore } from './store/useAppStore.js';
import { SuiteBar } from './components/layout/SuiteBar.jsx';
import { Navbar } from './components/layout/Navbar.jsx';
import { ErrorBoundary } from './components/common/ErrorBoundary.jsx';

// Módulos
import { HomeGalaxy } from './components/modules/HomeGalaxy.jsx';
import { NationalPanorama } from './components/modules/NationalPanorama.jsx';
import { InstitutionalPanorama } from './components/modules/InstitutionalPanorama.jsx';
import { ResearcherProfiles } from './components/modules/ResearcherProfiles.jsx';
import { ScienceMaps } from './components/modules/ScienceMaps.jsx';
import { MyResearcherSpace } from './components/modules/MyResearcherSpace.jsx';
import { GovernanceAdmin } from './components/modules/GovernanceAdmin.jsx';
import { AIAssistant } from './components/modules/AIAssistant.jsx';
import { AboutView } from './components/modules/AboutView.jsx';

import { apiClient } from './api/client.js';

import './App.css';

export function App() {
  const activeTab = useAppStore((state) => state.activeTab);
  const theme = useAppStore((state) => state.theme);
  const t = useAppStore((state) => state.t)();
  const setUserSession = useAppStore((state) => state.setUserSession);
  const setNotification = useAppStore((state) => state.setNotification);

  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Interceptar callback de autorización OAuth de ORCID (?code=...)
  React.useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const code = params.get('code');
      if (code) {
        // Puente OAuth para otros módulos del ecosistema (ej. Revistas LATAM, TlachIA Metrics)
        const stateRaw = params.get('state') || '';
        const stateClean = stateRaw.toLowerCase().trim();

        if (stateClean.includes('revistas') || stateClean.includes('latam')) {
          const targetUrl = `https://dinamica1.fciencias.unam.mx/revistaslatam/?code=${encodeURIComponent(code)}`;
          window.location.href = targetUrl;
          return;
        }
        if (stateClean.includes('tlachia') || stateClean.includes('metric')) {
          const targetUrl = `https://dinamica1.fciencias.unam.mx/tlachiametrics/?code=${encodeURIComponent(code)}`;
          window.location.href = targetUrl;
          return;
        }

        const basePath = window.location.pathname.startsWith('/sinapsisai_dev')
          ? '/sinapsisai_dev/'
          : (window.location.pathname.startsWith('/infotlachia') ? '/infotlachia/' : '/sinapsisai/');
        const redirectUri = `${window.location.origin}${basePath}`;

        apiClient.exchangeOrcidToken(code, redirectUri)
          .then((data) => {
            if (data && data.orcid) {
              const sessionData = {
                isAuthenticated: true,
                orcid: data.orcid,
                name: data.name || data.orcid,
                role: data.role || 'investigador',
                is_admin: Boolean(data.is_admin || data.role === 'super_admin' || data.role === 'admin_institucional' || data.role === 'admin'),
                institution: data.institution || null,
                token: data.access_token || null
              };
              setUserSession(sessionData);
              setNotification({
                type: 'success',
                message: `Bienvenido, ${sessionData.name}. Sesión iniciada con ORCID ${sessionData.orcid}`
              });
              // Limpiar parámetro ?code= de la URL sin recargar la página
              const cleanUrl = window.location.pathname;
              window.history.replaceState({}, document.title, cleanUrl);
            }
          })
          .catch((err) => {
            console.error('Error al intercambiar código ORCID:', err);
            setNotification({
              type: 'error',
              message: 'No se pudo completar el inicio de sesión con ORCID.'
            });
          });
      }
    } catch (e) {
      console.error(e);
    }
  }, [setUserSession, setNotification]);

  // 1. Inicialización de Permalinks al cargar la aplicación (?academic=..., ?orcid=..., ?institution=..., ?tab=...)
  React.useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const code = params.get('code');
      if (code) return; // Permitir que el flujo OAuth se procese primero

      const academicParam = params.get('academic');
      const orcidParam = params.get('orcid');
      const institutionParam = params.get('institution');
      const dependencyParam = params.get('dependency');
      const subdependencyParam = params.get('subdependency');
      const tabParam = params.get('tab');

      if (academicParam || orcidParam || tabParam === 'researchers') {
        useAppStore.getState().setActiveTab('researchers');
        if (academicParam || orcidParam) {
          useAppStore.getState().setSelectedResearcher(academicParam || '', orcidParam || '');
        }
        if (institutionParam) useAppStore.getState().setSelectedInstitution(institutionParam);
        if (dependencyParam) useAppStore.getState().setSelectedDependency(dependencyParam);
        if (subdependencyParam) useAppStore.getState().setSelectedSubdependency(subdependencyParam);
      } else if (institutionParam || tabParam === 'panorama') {
        useAppStore.getState().setActiveTab('panorama');
        if (institutionParam) useAppStore.getState().setSelectedInstitution(institutionParam);
        if (dependencyParam) useAppStore.getState().setSelectedDependency(dependencyParam);
        if (subdependencyParam) useAppStore.getState().setSelectedSubdependency(subdependencyParam);
      } else if (tabParam) {
        const validTabs = ['home', 'national', 'panorama', 'researchers', 'maps', 'mySpace', 'governance', 'assistant', 'about'];
        if (validTabs.includes(tabParam)) {
          useAppStore.getState().setActiveTab(tabParam);
        }
      }
    } catch (err) {
      console.error('Error inicializando permalink:', err);
    }
  }, []);

  // 2. Sincronización reactiva del estado actual en la URL del navegador (Permalink)
  const selectedInstitution = useAppStore((state) => state.selectedInstitution);
  const selectedDependency = useAppStore((state) => state.selectedDependency);
  const selectedSubdependency = useAppStore((state) => state.selectedSubdependency);
  const selectedResearcherName = useAppStore((state) => state.selectedResearcherName);
  const selectedResearcherOrcid = useAppStore((state) => state.selectedResearcherOrcid);

  React.useEffect(() => {
    try {
      const searchParams = new URLSearchParams(window.location.search);
      if (searchParams.get('code')) return; // No sobreescribir callback OAuth

      const newParams = new URLSearchParams();
      if (activeTab === 'researchers') {
        newParams.set('tab', 'researchers');
        if (selectedResearcherName) newParams.set('academic', selectedResearcherName);
        if (selectedResearcherOrcid) newParams.set('orcid', selectedResearcherOrcid);
      } else if (activeTab === 'panorama') {
        newParams.set('tab', 'panorama');
        if (selectedInstitution) newParams.set('institution', selectedInstitution);
        if (selectedDependency) newParams.set('dependency', selectedDependency);
        if (selectedSubdependency) newParams.set('subdependency', selectedSubdependency);
      } else if (activeTab === 'national') {
        newParams.set('tab', 'national');
      } else {
        newParams.set('tab', activeTab);
      }

      const newQuery = newParams.toString();
      const currentQuery = window.location.search.replace(/^\?/, '');
      if (newQuery !== currentQuery) {
        const cleanUrl = `${window.location.pathname}?${newQuery}`;
        window.history.replaceState({}, '', cleanUrl);
      }
    } catch (err) {
      console.error('Error sincronizando URL permalink:', err);
    }
  }, [
    activeTab,
    selectedResearcherName,
    selectedResearcherOrcid,
    selectedInstitution,
    selectedDependency,
    selectedSubdependency
  ]);

  return (
    <div className="app-root">
      {/* Luz Ambiental de Fondo */}
      <div className="ambient-glow" />

      {/* 1. Franja del Ecosistema Científico TlachIA (Fase 2.1) */}
      <SuiteBar />

      {/* 2. Barra de Navegación de la Aplicación (Pestaña Inicio + Módulos Analíticos) */}
      <Navbar />

      {/* 3. Área de Contenido Dinámico */}
      <main className="main-content-area" role="main">
        <ErrorBoundary>
          {activeTab === 'home' && <HomeGalaxy />}
          {activeTab === 'national' && <NationalPanorama />}
          {activeTab === 'panorama' && <InstitutionalPanorama />}
          {activeTab === 'researchers' && <ResearcherProfiles />}
          {activeTab === 'maps' && <ScienceMaps />}
          {activeTab === 'mySpace' && <MyResearcherSpace />}
          {activeTab === 'governance' && <GovernanceAdmin />}
          {activeTab === 'assistant' && <AIAssistant />}
          {activeTab === 'about' && <AboutView />}
        </ErrorBoundary>
      </main>

      {/* 4. Pie de Página */}
      <footer className="app-footer">
        <div>
          <span>© 2026 Ecosistema TlachIA · Universidad Nacional Autónoma de México (UNAM)</span>
        </div>
        <div className="footer-credits">
          <a href="https://dinamica1.fciencias.unam.mx/revistaslatam/" className="footer-link" target="_blank" rel="noreferrer">Revistas LATAM</a>
          <a href="https://dinamica1.fciencias.unam.mx/knomap/" className="footer-link" target="_blank" rel="noreferrer">KnoMap</a>
          <a href="https://dinamica1.fciencias.unam.mx/tlachiametrics/" className="footer-link" target="_blank" rel="noreferrer">TlachIA Metrics</a>
          <span style={{ color: 'var(--text-dim)' }}>|</span>
          <span>Padrón de Investigadores 2025/2026</span>
        </div>
      </footer>
    </div>
  );
}

export default App;
