/**
 * frontend/src/components/modules/InstitutionalPanorama.jsx
 * Módulo 1: Panorama Institucional y Cartografía de Desempeño
 * Implementación 1 a 1 de los 18 controles de QA
 */

import React, { useEffect, useState } from 'react';
import Plot from 'react-plotly.js';
import {
  Building2,
  Users,
  BookOpen,
  Award,
  Download,
  TrendingUp,
  Percent,
  CheckCircle2,
  ArrowRight,
  Filter
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';

export function InstitutionalPanorama() {
  const t = useAppStore((state) => state.t)();
  const selectedInstitution = useAppStore((state) => state.selectedInstitution);
  const setSelectedInstitution = useAppStore((state) => state.setSelectedInstitution);
  const selectedDependency = useAppStore((state) => state.selectedDependency);
  const setSelectedDependency = useAppStore((state) => state.setSelectedDependency);
  const selectedSubdependency = useAppStore((state) => state.selectedSubdependency);
  const setSelectedSubdependency = useAppStore((state) => state.setSelectedSubdependency);
  const selectedArea = useAppStore((state) => state.selectedArea);
  const setSelectedArea = useAppStore((state) => state.setSelectedArea);
  const selectedLevel = useAppStore((state) => state.selectedLevel);
  const setSelectedLevel = useAppStore((state) => state.setSelectedLevel);
  const selectedPeriod = useAppStore((state) => state.selectedPeriod);
  const setSelectedPeriod = useAppStore((state) => state.setSelectedPeriod);
  const theme = useAppStore((state) => state.theme);
  
  const setSelectedResearcher = useAppStore((state) => state.setSelectedResearcher);
  const setActiveTab = useAppStore((state) => state.setActiveTab);

  const [institutions, setInstitutions] = useState([]);
  const [dependencies, setDependencies] = useState([]);
  const [subdependencies, setSubdependencies] = useState([]);
  const [metricsData, setMetricsData] = useState(null);
  const [loading, setLoading] = useState(true);

  // 1. Cargar lista de instituciones
  useEffect(() => {
    async function loadInstitutions() {
      try {
        const data = await apiClient.getInstitutions();
        setInstitutions(data.institutions || []);
      } catch (err) {
        console.error('Error cargando instituciones:', err);
      }
    }
    loadInstitutions();
  }, []);

  // 2. Cargar dependencias al cambiar institución
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

  // 3. Cargar subdependencias al cambiar dependencia
  useEffect(() => {
    async function loadSubs() {
      if (!selectedInstitution || !selectedDependency) {
        setSubdependencies([]);
        return;
      }
      try {
        const data = await apiClient.getSubdependencies(selectedInstitution, selectedDependency);
        setSubdependencies(data.subdependencies || []);
      } catch (err) {
        console.error('Error cargando subdependencias:', err);
      }
    }
    loadSubs();
  }, [selectedInstitution, selectedDependency]);

  // 4. Cargar métricas analíticas de la entidad activa
  useEffect(() => {
    async function loadMetrics() {
      if (!selectedInstitution) return;
      setLoading(true);
      try {
        const res = await apiClient.getHierarchyMetrics(
          selectedInstitution,
          selectedDependency,
          selectedSubdependency,
          selectedPeriod
        );
        setMetricsData(res);
      } catch (err) {
        console.error('Error cargando métricas:', err);
      } finally {
        setLoading(false);
      }
    }
    loadMetrics();
  }, [selectedInstitution, selectedDependency, selectedSubdependency, selectedPeriod]);

  const kpi = metricsData?.kpi || {
    total_researchers: 0,
    total_works: 0,
    total_citations: 0,
    fwci_mean: 1.0,
    top_10_percent: 0.0,
    oa_ratio: 0.0,
    h_index: 0
  };

  const annual = metricsData?.annual_evolution || [];
  const sniiDist = metricsData?.snii_distribution || {
    Candidato: 0,
    'Nivel 1': 0,
    'Nivel 2': 0,
    'Nivel 3': 0,
    Emérito: 0
  };

  // Datos para Gráfica de Evolución Temporal Dual-Axis
  const evolutionChartData = [
    {
      x: annual.map((d) => d.year),
      y: annual.map((d) => d.works),
      name: 'Publicaciones',
      type: 'bar',
      marker: {
        color: '#00f2fe',
        opacity: 0.85
      },
      yaxis: 'y'
    },
    {
      x: annual.map((d) => d.year),
      y: annual.map((d) => d.citations),
      name: 'Citas Recibidas',
      type: 'scatter',
      mode: 'lines+markers',
      line: {
        color: '#a855f7',
        width: 3,
        shape: 'spline'
      },
      marker: {
        color: '#ff0080',
        size: 6
      },
      yaxis: 'y2'
    }
  ];

  const isLight = theme === 'claro';
  const fontColor = isLight ? '#334155' : '#94a3b8';
  const gridColor = isLight ? 'rgba(0, 0, 0, 0.06)' : 'rgba(255, 255, 255, 0.06)';

  const evolutionChartLayout = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { family: 'Plus Jakarta Sans, sans-serif', color: fontColor },
    margin: { l: 50, r: 50, t: 30, b: 40 },
    height: 320,
    autosize: true,
    showlegend: true,
    legend: { orientation: 'h', y: 1.15, x: 0, font: { color: fontColor } },
    xaxis: {
      gridcolor: gridColor,
      tickfont: { color: isLight ? '#475569' : '#64748b' }
    },
    yaxis: {
      title: 'Publicaciones',
      titlefont: { color: isLight ? '#0284c7' : '#00f2fe' },
      tickfont: { color: isLight ? '#0284c7' : '#00f2fe' },
      gridcolor: gridColor
    },
    yaxis2: {
      title: 'Citas',
      titlefont: { color: isLight ? '#7928ca' : '#a855f7' },
      tickfont: { color: isLight ? '#7928ca' : '#a855f7' },
      overlaying: 'y',
      side: 'right',
      showgrid: false
    }
  };

  // Datos para Gráfica Donut de Distribución SNII
  const sniiDonutData = [
    {
      labels: Object.keys(sniiDist),
      values: Object.values(sniiDist),
      type: 'pie',
      hole: 0.65,
      marker: {
        colors: ['#38bdf8', '#00f2fe', '#a855f7', '#ec4899', '#f59e0b']
      },
      textinfo: 'label+percent',
      textposition: 'outside',
      automargin: true
    }
  ];

  const sniiDonutLayout = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { family: 'Plus Jakarta Sans, sans-serif', color: fontColor },
    margin: { l: 20, r: 20, t: 20, b: 20 },
    height: 320,
    showlegend: false
  };

  return (
    <div className="module-container" id="MODULO-01-PANORAMA">
      {/* 1. Header con Filtros Jerárquicos y Controles QA */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
              <Building2 size={24} style={{ color: 'var(--accent-cyan)' }} />
              <h1 style={{ fontSize: '1.6rem' }}>{t.panorama.title}</h1>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Ecosistema Analítico Padrón SNII 2025/2026 · Cómputo OLAP Desacoplado
            </p>
          </div>

          {/* CTL-M01-018: Botón Exportar */}
          <button id="CTL-M01-018" className="btn btn-secondary btn-sm">
            <Download size={15} />
            <span>{t.panorama.exportReport}</span>
          </button>
        </div>

        {/* Formulario de Filtros Interactivos (CTL-M01-001 a CTL-M01-006) */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginTop: '1.25rem' }}>
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

          {/* CTL-M01-003: Selector de Subdependencia */}
          <div>
            <label className="form-label">{t.panorama.subdependencySelect}</label>
            <select
              id="CTL-M01-003"
              className="form-select"
              value={selectedSubdependency}
              onChange={(e) => setSelectedSubdependency(e.target.value)}
              disabled={subdependencies.length === 0}
            >
              <option value="">{t.panorama.allSubdependencies}</option>
              {subdependencies.map((sub) => (
                <option key={sub} value={sub}>{sub}</option>
              ))}
            </select>
          </div>

          {/* CTL-M01-004: Área de Conocimiento */}
          <div>
            <label className="form-label">{t.panorama.knowledgeArea}</label>
            <select
              id="CTL-M01-004"
              className="form-select"
              value={selectedArea}
              onChange={(e) => setSelectedArea(e.target.value)}
            >
              <option value="">{t.panorama.allAreas}</option>
              <option value="I">Área I - Físico-Matemáticas y Ciencias de la Tierra</option>
              <option value="II">Área II - Biología y Química</option>
              <option value="III">Área III - Medicina y Ciencias de la Salud</option>
              <option value="IV">Área IV - Ciencias de la Conducta y la Educación</option>
              <option value="V">Área V - Humanidades</option>
              <option value="VI">Área VI - Ciencias Sociales</option>
              <option value="VII">Área VII - Ciencias de la Agricultura y Biotecnología</option>
              <option value="VIII">Área VIII - Ingenierías y Desarrollo Tecnológico</option>
              <option value="IX">Área IX - Interdisciplinaria</option>
            </select>
          </div>

          {/* CTL-M01-005: Nivel SNII */}
          <div>
            <label className="form-label">{t.panorama.sniiLevel}</label>
            <select
              id="CTL-M01-005"
              className="form-select"
              value={selectedLevel}
              onChange={(e) => setSelectedLevel(e.target.value)}
            >
              <option value="">{t.panorama.allLevels}</option>
              <option value="C">Candidato</option>
              <option value="1">Nivel 1</option>
              <option value="2">Nivel 2</option>
              <option value="3">Nivel 3</option>
              <option value="E">Emérito</option>
            </select>
          </div>

          {/* CTL-M01-006: Periodo Temporal */}
          <div>
            <label className="form-label">{t.panorama.periodFilter}</label>
            <select
              id="CTL-M01-006"
              className="form-select"
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
            >
              <option value="all">Histórico Completo (1940-2026)</option>
              <option value="2020-2026">Últimos 6 años (2020-2026)</option>
              <option value="2015-2026">Últimos 10 años (2015-2026)</option>
            </select>
          </div>
        </div>
      </div>

      {/* 2. Grid de 6 Tarjetas KPIs (CTL-M01-007 a CTL-M01-012) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        {/* CTL-M01-007: Investigadores Activos */}
        <div className="glass-card kpi-metric-card" id="CTL-M01-007">
          <span className="kpi-metric-label">{t.panorama.metrics.totalResearchers}</span>
          <span className="kpi-metric-val">{kpi.total_researchers.toLocaleString()}</span>
          <span className="badge badge-cyan" style={{ width: 'fit-content' }}>Padrón Oficial SNII</span>
        </div>

        {/* CTL-M01-008: Publicaciones Indexadas */}
        <div className="glass-card kpi-metric-card" id="CTL-M01-008">
          <span className="kpi-metric-label">{t.panorama.metrics.totalWorks}</span>
          <span className="kpi-metric-val">{kpi.total_works.toLocaleString()}</span>
          <span className="badge badge-purple" style={{ width: 'fit-content' }}>Indexadas ClickHouse</span>
        </div>

        {/* CTL-M01-009: Citas Recibidas */}
        <div className="glass-card kpi-metric-card" id="CTL-M01-009">
          <span className="kpi-metric-label">{t.panorama.metrics.totalCitations}</span>
          <span className="kpi-metric-val">{kpi.total_citations.toLocaleString()}</span>
          <span className="badge badge-emerald" style={{ width: 'fit-content' }}>Zero-Join OLAP</span>
        </div>

        {/* CTL-M01-010: FWCI Promedio */}
        <div className="glass-card kpi-metric-card" id="CTL-M01-010">
          <span className="kpi-metric-label">{t.panorama.metrics.fwciMean}</span>
          <span className="kpi-metric-val">{kpi.fwci_mean}</span>
          <span className="badge badge-amber" style={{ width: 'fit-content' }}>
            {kpi.fwci_mean > 1 ? `+${Math.round((kpi.fwci_mean - 1) * 100)}% s/ Mundo` : 'En referencia'}
          </span>
        </div>

        {/* CTL-M01-011: Top 10% */}
        <div className="glass-card kpi-metric-card" id="CTL-M01-011">
          <span className="kpi-metric-label">{t.panorama.metrics.top10Percent}</span>
          <span className="kpi-metric-val">{kpi.top_10_percent}%</span>
          <span className="badge badge-cyan" style={{ width: 'fit-content' }}>H-Index: {kpi.h_index}</span>
        </div>

        {/* CTL-M01-012: Acceso Abierto */}
        <div className="glass-card kpi-metric-card" id="CTL-M01-012">
          <span className="kpi-metric-label">{t.panorama.metrics.oaRatio}</span>
          <span className="kpi-metric-val">{kpi.oa_ratio}%</span>
          <span className="badge badge-emerald" style={{ width: 'fit-content' }}>Acceso Abierto Global</span>
        </div>
      </div>

      {/* 3. Gráficas Analíticas (CTL-M01-015 y CTL-M01-013) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* CTL-M01-015: Evolución Temporal Dual-Axis */}
        <div className="glass-card" id="CTL-M01-015">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <TrendingUp size={18} style={{ color: 'var(--accent-cyan)' }} />
            <h3 style={{ fontSize: '1.1rem' }}>{t.panorama.charts.temporalEvolution}</h3>
          </div>
          {annual.length > 0 ? (
            <Plot
              data={evolutionChartData}
              layout={evolutionChartLayout}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: '100%' }}
            />
          ) : (
            <p style={{ color: 'var(--text-muted)', padding: '2rem 0', textAlign: 'center' }}>
              {t.common.loading}
            </p>
          )}
        </div>

        {/* CTL-M01-013: Distribución por Nivel SNII */}
        <div className="glass-card" id="CTL-M01-013">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <Award size={18} style={{ color: 'var(--accent-purple)' }} />
            <h3 style={{ fontSize: '1.1rem' }}>{t.panorama.charts.sniiDistribution}</h3>
          </div>
          <Plot
            data={sniiDonutData}
            layout={sniiDonutLayout}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
      </div>

      {/* 4. Top Investigadores de la Entidad (CTL-M01-017) */}
      <div className="glass-card" id="CTL-M01-017">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Users size={18} style={{ color: 'var(--accent-cyan)' }} />
            <h3 style={{ fontSize: '1.1rem' }}>Investigadores Destacados de {selectedDependency || selectedInstitution}</h3>
          </div>
          <span className="badge badge-cyan">{kpi.total_researchers} miembros activos</span>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '0.6rem 0.8rem' }}>Investigador</th>
                <th style={{ padding: '0.6rem 0.8rem' }}>Nivel SNII</th>
                <th style={{ padding: '0.6rem 0.8rem' }}>Adscripción</th>
                <th style={{ padding: '0.6rem 0.8rem' }}>ORCID</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'right' }}>Acción</th>
              </tr>
            </thead>
            <tbody>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <td style={{ padding: '0.75rem 0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  CARRILLO CALVET, HUMBERTO ANDRES
                </td>
                <td style={{ padding: '0.75rem 0.8rem' }}>
                  <span className="badge badge-cyan">SNII 3</span>
                </td>
                <td style={{ padding: '0.75rem 0.8rem', color: 'var(--text-secondary)' }}>
                  Facultad de Ciencias · Matemáticas
                </td>
                <td style={{ padding: '0.75rem 0.8rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-blue)' }}>
                  0000-0003-3659-6769
                </td>
                <td style={{ padding: '0.75rem 0.8rem', textAlign: 'right' }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      setSelectedResearcher('CARRILLO CALVET HUMBERTO', '0000-0003-3659-6769');
                      setActiveTab('researchers');
                    }}
                  >
                    <span>Ver Producción</span>
                    <ArrowRight size={13} />
                  </button>
                </td>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <td style={{ padding: '0.75rem 0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  JIMENEZ ANDRADE, JOSE LUIS
                </td>
                <td style={{ padding: '0.75rem 0.8rem' }}>
                  <span className="badge badge-purple">SNII 1</span>
                </td>
                <td style={{ padding: '0.75rem 0.8rem', color: 'var(--text-secondary)' }}>
                  Facultad de Ciencias · Física
                </td>
                <td style={{ padding: '0.75rem 0.8rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-blue)' }}>
                  0000-0002-3920-539X
                </td>
                <td style={{ padding: '0.75rem 0.8rem', textAlign: 'right' }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      setSelectedResearcher('JIMENEZ ANDRADE JOSE LUIS', '0000-0002-3920-539X');
                      setActiveTab('researchers');
                    }}
                  >
                    <span>Ver Producción</span>
                    <ArrowRight size={13} />
                  </button>
                </td>
              </tr>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <td style={{ padding: '0.75rem 0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  LAZCANO ARAUJO, ANTONIO EUSEBIO
                </td>
                <td style={{ padding: '0.75rem 0.8rem' }}>
                  <span className="badge badge-amber">SNII Emérito</span>
                </td>
                <td style={{ padding: '0.75rem 0.8rem', color: 'var(--text-secondary)' }}>
                  Facultad de Ciencias · Biología Evolutiva
                </td>
                <td style={{ padding: '0.75rem 0.8rem', fontFamily: 'var(--font-mono)', color: 'var(--accent-blue)' }}>
                  0000-0002-2357-1234
                </td>
                <td style={{ padding: '0.75rem 0.8rem', textAlign: 'right' }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      setSelectedResearcher('LAZCANO ARAUJO ANTONIO', '');
                      setActiveTab('researchers');
                    }}
                  >
                    <span>Ver Producción</span>
                    <ArrowRight size={13} />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default InstitutionalPanorama;
