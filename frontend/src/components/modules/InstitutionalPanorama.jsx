/**
 * frontend/src/components/modules/InstitutionalPanorama.jsx
 * Módulo 1: Panorama Institucional y Cartografía de Desempeño
 */

import React, { useEffect, useState } from 'react';
import { Building2, Filter, Download, Users, BookOpen, Award, ArrowUpRight } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';

export function InstitutionalPanorama() {
  const t = useAppStore((state) => state.t)();
  const selectedInstitution = useAppStore((state) => state.selectedInstitution);
  const setSelectedInstitution = useAppStore((state) => state.setSelectedInstitution);
  const selectedDependency = useAppStore((state) => state.selectedDependency);
  const setSelectedDependency = useAppStore((state) => state.setSelectedDependency);

  const [institutions, setInstitutions] = useState([]);
  const [dependencies, setDependencies] = useState([]);
  const [loading, setLoading] = useState(true);

  // Cargar lista de instituciones desde la API FastAPI (Fase 1)
  useEffect(() => {
    async function loadInstitutions() {
      try {
        const data = await apiClient.getInstitutions();
        setInstitutions(data.institutions || []);
      } catch (err) {
        console.error('Error cargando instituciones:', err);
      } finally {
        setLoading(false);
      }
    }
    loadInstitutions();
  }, []);

  // Cargar dependencias de la institución seleccionada
  useEffect(() => {
    async function loadDeps() {
      if (!selectedInstitution) return;
      try {
        const data = await apiClient.getDependencies(selectedInstitution);
        setDependencies(data.dependencies || []);
      } catch (err) {
        console.error('Error cargando dependencias:', err);
      }
    }
    loadDeps();
  }, [selectedInstitution]);

  return (
    <div className="module-container" id="MODULO-01-PANORAMA">
      {/* Header del Módulo */}
      <div className="module-header glass-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h1 style={{ fontSize: '1.6rem', marginBottom: '0.25rem' }}>{t.panorama.title}</h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Padrón SNII 2025/2026 oficial · Cómputo Analítico Desacoplado
            </p>
          </div>
          <button id="CTL-M01-018" className="btn btn-secondary btn-sm">
            <Download size={15} />
            <span>{t.panorama.exportReport}</span>
          </button>
        </div>

        {/* Filtros de Jerarquía Institucional (Controles 1 a 1 de Módulo 1) */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', marginTop: '1.25rem' }}>
          {/* CTL-M01-001: Selector de Institución */}
          <div>
            <label className="form-label">{t.panorama.institutionSelect}</label>
            <select
              id="CTL-M01-001"
              className="form-select"
              value={selectedInstitution}
              onChange={(e) => setSelectedInstitution(e.target.value)}
            >
              {institutions.map((inst) => (
                <option key={inst} value={inst}>{inst}</option>
              ))}
            </select>
          </div>

          {/* CTL-M01-002: Selector de Dependencia */}
          <div>
            <label className="form-label">{t.panorama.dependencySelect}</label>
            <select
              id="CTL-M01-002"
              className="form-select"
              value={selectedDependency}
              onChange={(e) => setSelectedDependency(e.target.value)}
            >
              <option value="">{t.panorama.allDependencies}</option>
              {dependencies.map((dep) => (
                <option key={dep} value={dep}>{dep}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Grid de Métricas Principales (KPI Cards) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        <div className="glass-card kpi-metric-card" id="CTL-M01-007">
          <span className="kpi-metric-label">{t.panorama.metrics.totalResearchers}</span>
          <span className="kpi-metric-val">41,367</span>
          <span className="badge badge-cyan" style={{ width: 'fit-content' }}>+4.2% vs 2024</span>
        </div>

        <div className="glass-card kpi-metric-card" id="CTL-M01-008">
          <span className="kpi-metric-label">{t.panorama.metrics.totalWorks}</span>
          <span className="kpi-metric-val">386,412</span>
          <span className="badge badge-purple" style={{ width: 'fit-content' }}>Indexadas ClickHouse</span>
        </div>

        <div className="glass-card kpi-metric-card" id="CTL-M01-009">
          <span className="kpi-metric-label">{t.panorama.metrics.totalCitations}</span>
          <span className="kpi-metric-val">4.92M</span>
          <span className="badge badge-emerald" style={{ width: 'fit-content' }}>Zero-Join OLAP</span>
        </div>

        <div className="glass-card kpi-metric-card" id="CTL-M01-010">
          <span className="kpi-metric-label">{t.panorama.metrics.fwciMean}</span>
          <span className="kpi-metric-val">1.28</span>
          <span className="badge badge-amber" style={{ width: 'fit-content' }}>+28% s/ Mundo</span>
        </div>
      </div>
    </div>
  );
}

export default InstitutionalPanorama;
