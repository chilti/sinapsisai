/**
 * frontend/src/App.jsx
 * Componente Principal de la Aplicación SNII Info TlachIA
 */

import React from 'react';
import { useAppStore } from './store/useAppStore.js';
import { SuiteBar } from './components/layout/SuiteBar.jsx';
import { Navbar } from './components/layout/Navbar.jsx';

// Módulos
import { InstitutionalPanorama } from './components/modules/InstitutionalPanorama.jsx';
import { ResearcherProfiles } from './components/modules/ResearcherProfiles.jsx';
import { ScienceMaps } from './components/modules/ScienceMaps.jsx';
import { MyResearcherSpace } from './components/modules/MyResearcherSpace.jsx';
import { GovernanceAdmin } from './components/modules/GovernanceAdmin.jsx';
import { AIAssistant } from './components/modules/AIAssistant.jsx';

import './App.css';

export function App() {
  const activeTab = useAppStore((state) => state.activeTab);
  const t = useAppStore((state) => state.t)();

  return (
    <div className="app-root">
      {/* Luz Ambiental de Fondo */}
      <div className="ambient-glow" />

      {/* 1. Franja del Ecosistema Científico TlachIA (Fase 2.1) */}
      <SuiteBar />

      {/* 2. Barra de Navegación de la Aplicación (6 Pestañas + Selector de Idioma) */}
      <Navbar />

      {/* 3. Área de Contenido Dinámico */}
      <main className="main-content-area" role="main">
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
          <a href="/revistaslatam/" className="footer-link" target="_blank" rel="noreferrer">Revistas LATAM</a>
          <a href="/knomap/" className="footer-link" target="_blank" rel="noreferrer">KnoMap</a>
          <a href="/tlachia-metrics/" className="footer-link" target="_blank" rel="noreferrer">TlachIA Metrics</a>
          <span style={{ color: 'var(--text-dim)' }}>|</span>
          <span>Padrón SNII 2025/2026</span>
        </div>
      </footer>
    </div>
  );
}

export default App;
