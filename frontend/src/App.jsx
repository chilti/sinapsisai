/**
 * frontend/src/App.jsx
 * Componente Principal de la Aplicación SNII Info TlachIA
 */

import React from 'react';
import { useAppStore } from './store/useAppStore.js';
import { SuiteBar } from './components/layout/SuiteBar.jsx';
import { Navbar } from './components/layout/Navbar.jsx';

// Módulos
import { HomeGalaxy } from './components/modules/HomeGalaxy.jsx';
import { NationalPanorama } from './components/modules/NationalPanorama.jsx';
import { InstitutionalPanorama } from './components/modules/InstitutionalPanorama.jsx';
import { ResearcherProfiles } from './components/modules/ResearcherProfiles.jsx';
import { ScienceMaps } from './components/modules/ScienceMaps.jsx';
import { MyResearcherSpace } from './components/modules/MyResearcherSpace.jsx';
import { GovernanceAdmin } from './components/modules/GovernanceAdmin.jsx';
import { AIAssistant } from './components/modules/AIAssistant.jsx';

import './App.css';

export function App() {
  const activeTab = useAppStore((state) => state.activeTab);
  const theme = useAppStore((state) => state.theme);
  const t = useAppStore((state) => state.t)();

  React.useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

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
        {activeTab === 'home' && <HomeGalaxy />}
        {activeTab === 'national' && <NationalPanorama />}
        {activeTab === 'panorama' && <InstitutionalPanorama />}
        {activeTab === 'researchers' && <ResearcherProfiles />}
        {activeTab === 'maps' && <ScienceMaps />}
        {activeTab === 'mySpace' && <MyResearcherSpace />}
        {activeTab === 'governance' && <GovernanceAdmin />}
        {activeTab === 'assistant' && <AIAssistant />}
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
          <span>Padrón SNII 2025/2026</span>
        </div>
      </footer>
    </div>
  );
}

export default App;
