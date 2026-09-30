/**
 * frontend/src/components/modules/InstitutionalPanorama.jsx
 * Módulo 1: Panorama Institucional y Cartografía de Desempeño
 * Implementación al 100% de paridad con Streamlit (22 bloques analíticos y visualizadores)
 */

import React, { useEffect, useState, useMemo } from 'react';
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
  ExternalLink,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  Globe2,
  PieChart as PieIcon,
  Layers,
  Sparkles,
  Search,
  Filter,
  ArrowRight,
  ShieldCheck,
  DollarSign,
  Loader2
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import { apiClient } from '../../api/client.js';
import ThematicEvolutionTable from '../analytics/ThematicEvolutionTable.jsx';
import CollaborationWorldMap from '../analytics/CollaborationWorldMap.jsx';
import SemanticProductionMap from '../analytics/SemanticProductionMap.jsx';
import AIReportViewer from '../analytics/AIReportViewer.jsx';
import WordCloudInteractive from '../analytics/WordCloudInteractive.jsx';

export function InstitutionalPanorama() {
  const t = useAppStore((state) => state.t)();
  const selectedInstitution = useAppStore((state) => state.selectedInstitution);
  const setSelectedInstitution = useAppStore((state) => state.setSelectedInstitution);
  const selectedDependency = useAppStore((state) => state.selectedDependency);
  const setSelectedDependency = useAppStore((state) => state.setSelectedDependency);
  const selectedSubdependency = useAppStore((state) => state.selectedSubdependency);
  const setSelectedSubdependency = useAppStore((state) => state.setSelectedSubdependency);
  const selectedPeriod = useAppStore((state) => state.selectedPeriod);
  const setSelectedPeriod = useAppStore((state) => state.setSelectedPeriod);
  const theme = useAppStore((state) => state.theme);

  // Estados locales
  const [viewMode, setViewMode] = useState('capacidad_instalada'); // 'capacidad_instalada' vs 'produccion_institucional'
  const [institutions, setInstitutions] = useState([]);
  const [dependencies, setDependencies] = useState([]);
  const [subdependencies, setSubdependencies] = useState([]);
  const [metricsData, setMetricsData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showGlossary, setShowGlossary] = useState(true);

  const currentYear = new Date().getFullYear();
  const PAGE_SIZE = 10;
  // Estados para tabla de publicaciones y filtros
  const [selectedYear, setSelectedYear] = useState(String(currentYear));
  const [selectedOds, setSelectedOds] = useState('Todos');
  const [searchPaper, setSearchPaper] = useState('');
  const [papersPage, setPapersPage] = useState(0);
  const [papersData, setPapersData] = useState([]);
  const [totalPapers, setTotalPapers] = useState(0);
  const [loadingPapers, setLoadingPapers] = useState(false);

  const isLight = theme === 'claro';
  const fontColor = isLight ? '#334155' : '#94a3b8';
  const gridColor = isLight ? 'rgba(0, 0, 0, 0.06)' : 'rgba(255, 255, 255, 0.06)';

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
          selectedPeriod,
          viewMode
        );
        setMetricsData(res);
        setPapersData((res.papers_sample || []).slice(0, PAGE_SIZE));
        setTotalPapers(res.initial_total_papers !== undefined ? res.initial_total_papers : (res.kpi?.general?.indexed_works || res.kpi?.total_works || 0));
        if (res.default_year) {
          setSelectedYear(String(res.default_year));
        }
      } catch (err) {
        console.error('Error cargando métricas:', err);
      } finally {
        setLoading(false);
      }
    }
    loadMetrics();
  }, [selectedInstitution, selectedDependency, selectedSubdependency, selectedPeriod, viewMode]);

  // 5. Cargar publicaciones dinámicas al cambiar filtros de tabla
  useEffect(() => {
    if (!selectedInstitution || loading) return;

    // Si no hay filtros adicionales y coincide con el año inicial y página 0, usamos la muestra precargada
    const isInitialDefault = String(selectedYear) === String(metricsData?.default_year || currentYear) && selectedOds === 'Todos' && !searchPaper && papersPage === 0;
    if (isInitialDefault) {
      if (metricsData?.papers_sample) {
        setPapersData(metricsData.papers_sample.slice(0, PAGE_SIZE));
        setTotalPapers(metricsData.initial_total_papers !== undefined ? metricsData.initial_total_papers : (metricsData.kpi?.general?.indexed_works || 0));
      }
      return;
    }

    async function fetchFilteredPapers() {
      setLoadingPapers(true);
      try {
        const params = {
          institution: selectedInstitution,
          dependency: selectedDependency || undefined,
          subdependency: selectedSubdependency || undefined,
          view_mode: viewMode,
          year: selectedYear !== 'Todos' ? Number(selectedYear) : undefined,
          ods: selectedOds !== 'Todos' ? selectedOds : undefined,
          search: searchPaper.trim() || undefined,
          limit: PAGE_SIZE,
          offset: papersPage * PAGE_SIZE
        };
        const res = await apiClient.getHierarchyPapers(params);
        setPapersData(res.papers || []);
        setTotalPapers(res.total || 0);
      } catch (err) {
        console.error('Error cargando papers filtrados:', err);
      } finally {
        setLoadingPapers(false);
      }
    }

    const timer = setTimeout(fetchFilteredPapers, 250);
    return () => clearTimeout(timer);
  }, [selectedYear, selectedOds, searchPaper, papersPage, selectedInstitution, selectedDependency, selectedSubdependency, viewMode]);

  // Datos extraídos del backend
  const meta = metricsData?.metadata || {};
  const kpiIds = metricsData?.kpi?.academic_ids || {
    pct_academic_orcid: 0,
    pct_academic_any_id: 0,
    pct_snii_orcid: 0,
    pct_snii_any_id: 0
  };
  const kpiGen = metricsData?.kpi?.general || {
    total_census: 0,
    indexed_works: 0,
    official_snii_count: 0,
    total_citations: 0,
    citations_per_paper: 0,
    fwci_mean: 1.0,
    pct_open_access: 0
  };
  const kpiExcel = metricsData?.kpi?.excellence || {
    percentile_avg: 50,
    pct_top_10: 0,
    pct_top_1: 0,
    h_index: 0
  };
  const tiersInst = kpiExcel.tiers || metricsData?.kpi?.tiers;
  const kpiVel = metricsData?.kpi?.velocity || {
    velocity_avg: 0,
    recent_cites_3yr: 0,
    pct_international: 0,
    avg_countries: 0,
    avg_author_count: 0
  };
  const kpiCosts = metricsData?.kpi?.costs || {
    apc_paid_usd: 0,
    pct_apc: 0,
    half_life_avg: 0
  };

  const annual = (metricsData?.annual_evolution || []).filter((d) => d.year >= 1980 && d.year <= 2026);
  const oaDist = metricsData?.oa_distribution || { Gold: 0, Green: 0, Hybrid: 0, Bronze: 0, Closed: 100 };
  const thematic = metricsData?.thematic_profile || { gini_topics: null, domain_diversity: 0, unique_topics: 0, top_domain: '—' };
  const docTypes = metricsData?.document_types || [];
  const sdgMatrix = metricsData?.sdg_matrix || [];
  const sunburstTrace = metricsData?.sunburst_trace;
  const keywords = metricsData?.keywords || [];
  const availableYears = metricsData?.available_years || [];
  const availableOds = metricsData?.available_ods || [];

  // 1. Gráfica Donut Open Access
  const oaChartData = [
    {
      labels: Object.keys(oaDist),
      values: Object.values(oaDist),
      type: 'pie',
      hole: 0.65,
      marker: {
        colors: ['#FFD700', '#2ECC71', '#3498DB', '#CD7F32', '#94a3b8']
      },
      textinfo: 'label+percent',
      textposition: 'outside',
      automargin: true
    }
  ];

  // 2. Gráfica Donut Tipos de Documentos
  const docTypesChartData = [
    {
      labels: docTypes.map((d) => d.type),
      values: docTypes.map((d) => d.count),
      type: 'pie',
      hole: 0.6,
      marker: {
        colors: ['#0284c7', '#00f2fe', '#a855f7', '#ec4899', '#f59e0b', '#10b981', '#64748b']
      },
      textinfo: 'label+percent',
      textposition: 'inside',
      automargin: true
    }
  ];

  // 3. Gráfica Histórica de Documentos (Área)
  const annualDocsChartData = [
    {
      x: annual.map((d) => d.year),
      y: annual.map((d) => d.works),
      name: 'Documentos',
      type: 'scatter',
      mode: 'lines+markers',
      fill: 'tozeroy',
      line: { color: '#f59e0b', width: 2.5 },
      marker: { size: 5, color: '#d97706' }
    }
  ];

  // 4. Gráfica FWCI Anual con línea de referencia 1.0
  const annualFwciChartData = [
    {
      x: annual.map((d) => d.year),
      y: annual.map((d) => d.fwci),
      name: 'FWCI Promedio',
      type: 'scatter',
      mode: 'lines+markers',
      line: { color: '#0284c7', width: 2.5 },
      marker: { size: 5, color: '#00f2fe' }
    }
  ];

  // 5. Gráfica Evolución % Colaboración Internacional
  const annualIntlChartData = [
    {
      x: annual.map((d) => d.year),
      y: annual.map((d) => d.pct_international),
      name: '% Internacional',
      type: 'scatter',
      mode: 'lines+markers',
      fill: 'tozeroy',
      line: { color: '#7928ca', width: 2.5 },
      marker: { size: 5, color: '#a855f7' }
    }
  ];

  // 6. Gráfica Stacked Bar OA por Año
  const annualOaStackedData = [
    { x: annual.map((d) => d.year), y: annual.map((d) => d.pct_oa_gold), name: 'Gold', type: 'bar', marker: { color: '#FFD700' } },
    { x: annual.map((d) => d.year), y: annual.map((d) => d.pct_oa_green), name: 'Green', type: 'bar', marker: { color: '#2ECC71' } },
    { x: annual.map((d) => d.year), y: annual.map((d) => d.pct_oa_hybrid), name: 'Hybrid', type: 'bar', marker: { color: '#3498DB' } },
    { x: annual.map((d) => d.year), y: annual.map((d) => d.pct_oa_bronze), name: 'Bronze', type: 'bar', marker: { color: '#CD7F32' } },
    { x: annual.map((d) => d.year), y: annual.map((d) => d.pct_oa_closed), name: 'Closed', type: 'bar', marker: { color: '#94a3b8' } }
  ];

  return (
    <div className="module-container" id="MODULO-01-PANORAMA">
      {/* ── 1. Header con Perspectiva Analítica y Exportación ───────────────── */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.25rem' }}>
              <Building2 size={26} style={{ color: 'var(--accent-cyan)' }} />
              <h1 style={{ fontSize: '1.65rem', fontWeight: 700 }}>
                {selectedSubdependency || selectedDependency || selectedInstitution || 'Panorama Institucional'}
              </h1>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Ecosistema Analítico Cienciométrico · Computación OLAP Desacoplada (DuckDB / ClickHouse)
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            {/* Conmutador de Perspectiva (Capacidad vs Producción) */}
            <div style={{ display: 'flex', background: 'var(--bg-card)', padding: '0.25rem', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
              <button
                className={`btn btn-sm ${viewMode === 'capacidad_instalada' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}
                onClick={() => setViewMode('capacidad_instalada')}
                disabled={loading}
              >
                {loading && viewMode === 'capacidad_instalada' && <Loader2 size={13} className="animate-spin" />}
                Capacidad Instalada
              </button>
              <button
                className={`btn btn-sm ${viewMode === 'produccion_institucional' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}
                onClick={() => setViewMode('produccion_institucional')}
                disabled={loading}
              >
                {loading && viewMode === 'produccion_institucional' && <Loader2 size={13} className="animate-spin" />}
                Producción Institucional
              </button>
            </div>

            {/* Botón Exportar */}
            <button id="CTL-M01-018" className="btn btn-secondary btn-sm">
              <Download size={15} />
              <span>Exportar Reporte</span>
            </button>
          </div>
        </div>

        {/* Badges de Identificadores Institucionales */}
        {(meta.ror_url || meta.openalex_url) && (
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '1rem', alignItems: 'center' }}>
            {meta.ror_url && (
              <a
                href={meta.ror_url}
                target="_blank"
                rel="noreferrer"
                className="badge badge-cyan"
                style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.3rem', padding: '0.3rem 0.6rem' }}
              >
                <b>ROR:</b> {meta.ror_id.replace('https://ror.org/', '')}
                <ExternalLink size={11} />
              </a>
            )}
            {meta.openalex_url && (
              <a
                href={meta.openalex_url}
                target="_blank"
                rel="noreferrer"
                className="badge badge-purple"
                style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.3rem', padding: '0.3rem 0.6rem' }}
              >
                <b>OpenAlex:</b> {meta.openalex_id.replace('https://openalex.org/', '')}
                <ExternalLink size={11} />
              </a>
            )}
            {meta.institution_type && (
              <span className="badge badge-emerald" style={{ padding: '0.3rem 0.6rem' }}>
                <b>Tipo:</b> {meta.institution_type}
              </span>
            )}
            {meta.institution_country && (
              <span className="badge badge-amber" style={{ padding: '0.3rem 0.6rem' }}>
                <b>País:</b> {meta.institution_country}
              </span>
            )}
          </div>
        )}

        {/* Formulario de Filtros Jerárquicos */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginTop: '1.25rem' }}>
          <div>
            <label className="form-label">{t.panorama.institutionSelect}</label>
            <select
              className="form-select"
              value={selectedInstitution}
              onChange={(e) => setSelectedInstitution(e.target.value)}
            >
              {institutions.map((inst) => (
                <option key={inst} value={inst}>{inst}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="form-label">{t.panorama.dependencySelect}</label>
            <select
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

          <div>
            <label className="form-label">{t.panorama.subdependencySelect}</label>
            <select
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
        </div>
      </div>

      {/* ── 2. Impacto Global en Sostenibilidad (ODS 1–17) ──────────────────── */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Globe2 size={20} style={{ color: 'var(--accent-cyan)' }} />
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>Impacto Global Institucional en Sostenibilidad (ODS)</h3>
          </div>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Haz clic en un ODS para filtrar las publicaciones
          </span>
        </div>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          Distribución de la producción científica etiquetada con los 17 Objetivos de Desarrollo Sostenible de la Agenda 2030 de la ONU.
        </p>

        {/* Notificación de Filtro ODS Activo */}
        {selectedOds !== 'Todos' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
            <span
              className="badge badge-cyan"
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.35rem 0.75rem', fontSize: '0.82rem' }}
            >
              Filtrando publicaciones por: <b>{selectedOds}</b>
              <button
                onClick={() => { setSelectedOds('Todos'); setPapersPage(0); }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'inherit',
                  cursor: 'pointer',
                  fontWeight: 800,
                  fontSize: '0.9rem',
                  marginLeft: '4px',
                  display: 'flex',
                  alignItems: 'center'
                }}
                title="Limpiar filtro ODS"
              >
                ✕
              </button>
            </span>
          </div>
        )}

        {/* Matriz de Tarjetas ODS con Imágenes Oficiales */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: '0.85rem' }}>
          {sdgMatrix.map((sdg) => {
            const odsId = sdg.id || sdg.sdg_id;
            const odsKey = `${odsId}. ${sdg.name}`;
            const isSelected = selectedOds === odsKey || selectedOds === sdg.name || selectedOds === String(odsId);
            const count = sdg.count ?? sdg.papers_count ?? 0;
            const pct = sdg.pct ?? 0;

            return (
              <div
                key={odsId}
                onClick={() => {
                  setSelectedOds(isSelected ? 'Todos' : odsKey);
                  setPapersPage(0);
                }}
                className="sdg-card-hover"
                title={`ODS ${odsId}: ${sdg.name} — ${count.toLocaleString()} obras (${pct}%)`}
                style={{
                  position: 'relative',
                  aspectRatio: '1 / 1',
                  borderRadius: '12px',
                  overflow: 'hidden',
                  cursor: 'pointer',
                  background: isLight ? '#f1f5f9' : '#1e293b',
                  border: isSelected ? '3px solid var(--accent-cyan)' : '2px solid rgba(255,255,255,0.08)',
                  boxShadow: isSelected
                    ? '0 0 16px rgba(0, 242, 254, 0.45)'
                    : '0 2px 6px rgba(0,0,0,0.12)',
                  transform: isSelected ? 'scale(1.04)' : 'scale(1)',
                  transition: 'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
                  filter: count === 0 ? 'grayscale(85%) opacity(0.4)' : 'none'
                }}
              >
                {/* Imagen Oficial del ODS */}
                <img
                  src={`./img/ods/ods_${odsId}.png`}
                  alt={`ODS ${odsId}: ${sdg.name}`}
                  loading="lazy"
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    display: 'block'
                  }}
                  onError={(e) => {
                    e.target.onerror = null;
                    e.target.src = `https://open-sdg.org/sdg-translations/assets/img/goals/es/${odsId}.png`;
                  }}
                />

                {/* Indicador de Selección Activa */}
                {isSelected && (
                  <div
                    style={{
                      position: 'absolute',
                      top: '6px',
                      right: '6px',
                      background: 'var(--accent-cyan)',
                      color: '#000',
                      borderRadius: '50%',
                      width: '22px',
                      height: '22px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.4)',
                      zIndex: 3
                    }}
                  >
                    <CheckCircle2 size={16} />
                  </div>
                )}

                {/* Overlay Inferior con Estadísticas */}
                <div
                  style={{
                    position: 'absolute',
                    bottom: 0,
                    left: 0,
                    right: 0,
                    background: 'linear-gradient(to top, rgba(0, 0, 0, 0.92) 0%, rgba(0, 0, 0, 0.65) 70%, transparent 100%)',
                    padding: '0.45rem 0.3rem 0.25rem',
                    textAlign: 'center',
                    color: '#ffffff',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    pointerEvents: 'none',
                    zIndex: 2
                  }}
                >
                  <span style={{ fontSize: '0.88rem', fontWeight: 800, textShadow: '0 1px 3px rgba(0,0,0,0.9)', letterSpacing: '-0.02em', color: '#ffffff' }}>
                    {pct}%
                  </span>
                  <span style={{ fontSize: '0.68rem', fontWeight: 600, opacity: 0.9, textShadow: '0 1px 2px rgba(0,0,0,0.9)', color: '#e2e8f0' }}>
                    {count.toLocaleString()} {count === 1 ? 'obra' : 'obras'}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── 3. Vocabulario Científico Institucional (Keywords Word Cloud) ──── */}
      <WordCloudInteractive
        keywords={keywords}
        title="Vocabulario Científico Institucional (Word Cloud)"
        subtitle="Nube interactiva con eventos de cursor para explorar frecuencias y conceptos dominantes."
      />

      {/* ── 4. Temáticas de Investigación Institucional (Sunburst 4 Niveles) ── */}
      {sunburstTrace && sunburstTrace.labels.length > 0 && (
        <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Layers size={18} style={{ color: 'var(--accent-cyan)' }} />
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600 }}>Temáticas de Investigación Institucional (Sunburst Jerárquico)</h3>
            </div>
            <span className="badge badge-cyan">4 Niveles: Dominio ➔ Campo ➔ Subcampo ➔ Tópico</span>
          </div>
          <Plot
            data={[
              {
                type: 'sunburst',
                ids: sunburstTrace.ids,
                labels: sunburstTrace.labels,
                parents: sunburstTrace.parents,
                values: sunburstTrace.values,
                branchvalues: 'total',
                marker: {
                  colors: sunburstTrace.colors || sunburstTrace.values,
                  colorscale: 'Blues',
                  showscale: true,
                  colorbar: {
                    title: { text: 'value' },
                    len: 0.85,
                    thickness: 16
                  }
                },
                hoverinfo: 'label+value+percent parent',
                insidetextorientation: 'radial'
              }
            ]}
            layout={{
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: 'Plus Jakarta Sans, sans-serif', color: fontColor },
              margin: { l: 10, r: 10, t: 10, b: 10 },
              height: 540,
              autosize: true
            }}
            config={{ responsive: true, displayModeBar: true }}
            style={{ width: '100%' }}
          />
        </div>
      )}

      {/* ── 4b. Evolución Histórica de Perfiles de Conocimiento ─────────────── */}
      <ThematicEvolutionTable
        data={metricsData?.thematic_evolution}
        title="Evolución Histórica de Perfiles de Conocimiento"
      />

      {/* ── 4c. Mapa Semántico de Producción (WebGL) ────────────────────────── */}
      <SemanticProductionMap
        targetName={selectedSubdependency || selectedDependency || selectedInstitution || "Entidad"}
        type="institution"
        dois={metricsData?.dois_list}
        oaIds={metricsData?.oa_list}
        totalWorks={kpiGen.indexed_works || totalPapers || 0}
      />

      {/* ── 4d. Mapa Mundi de Países Colaboradores ─────────────────────────── */}
      <CollaborationWorldMap
        countries={metricsData?.collaboration_countries}
        title="Países Colaboradores"
      />

      {/* ── 5. Distribución OA, Perfil Temático (Gini) y Tipos de Documentos ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.25rem', marginBottom: '1.5rem' }}>
        {/* Donut OA */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <PieIcon size={18} style={{ color: 'var(--accent-cyan)' }} />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Distribución Open Access</h3>
          </div>
          <Plot
            data={oaChartData}
            layout={{
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: 'Plus Jakarta Sans, sans-serif', color: fontColor },
              margin: { l: 20, r: 20, t: 20, b: 20 },
              height: 250,
              showlegend: false
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>

        {/* Perfil Temático (Gini) */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <Layers size={18} style={{ color: 'var(--accent-purple)' }} />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Perfil Temático y Concentración</h3>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: '0.85rem', borderCollapse: 'collapse' }}>
              <tbody>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '0.5rem 0', color: 'var(--text-secondary)' }}>Índice de Gini temático</td>
                  <td style={{ padding: '0.5rem 0', textAlign: 'right', fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
                    {thematic.gini_topics !== null ? thematic.gini_topics : 'N/A'}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '0.5rem 0', color: 'var(--text-secondary)' }}>Dominios de investigación</td>
                  <td style={{ padding: '0.5rem 0', textAlign: 'right', fontWeight: 700 }}>{thematic.domain_diversity}</td>
                </tr>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '0.5rem 0', color: 'var(--text-secondary)' }}>Tópicos únicos detectados</td>
                  <td style={{ padding: '0.5rem 0', textAlign: 'right', fontWeight: 700 }}>{thematic.unique_topics.toLocaleString()}</td>
                </tr>
                <tr>
                  <td style={{ padding: '0.5rem 0', color: 'var(--text-secondary)' }}>Dominio principal</td>
                  <td style={{ padding: '0.5rem 0', textAlign: 'right', fontWeight: 700, color: 'var(--accent-blue)' }}>
                    {thematic.top_domain}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.75rem' }}>
            * Gini temático: 0 = producción concentrada en un tema, 1 = producción completamente diversificada.
          </div>
        </div>

        {/* Tipos de Documentos */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <BookOpen size={18} style={{ color: 'var(--accent-emerald)' }} />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Tipos de Documentos</h3>
          </div>
          {docTypes.length > 0 ? (
            <Plot
              data={docTypesChartData}
              layout={{
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: { family: 'Plus Jakarta Sans, sans-serif', color: fontColor },
                margin: { l: 20, r: 20, t: 20, b: 20 },
                height: 250,
                showlegend: false
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: '100%' }}
            />
          ) : (
            <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '3rem 0' }}>Sin datos de tipos de documento</p>
          )}
        </div>
      </div>

      {/* ── 6. Colaboración Internacional y Stacked Bar OA Anual ───────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* % Colaboración Internacional */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <Globe2 size={18} style={{ color: 'var(--accent-purple)' }} />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Evolución de Colaboración Internacional (%) (1980–2026)</h3>
          </div>
          <Plot
            data={annualIntlChartData}
            layout={{
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: 'Plus Jakarta Sans, sans-serif', color: fontColor },
              margin: { l: 50, r: 20, t: 20, b: 35 },
              height: 280,
              autosize: true,
              xaxis: { range: [1980, 2026], gridcolor: gridColor, tickformat: 'd' },
              yaxis: { gridcolor: gridColor, title: '%', range: [0, 100] }
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>

        {/* Stacked Bar OA por Año */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <Layers size={18} style={{ color: 'var(--accent-emerald)' }} />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Evolución del Acceso Abierto por Año (%) (1980–2026)</h3>
          </div>
          <Plot
            data={annualOaStackedData}
            layout={{
              barmode: 'stack',
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: 'Plus Jakarta Sans, sans-serif', color: fontColor },
              margin: { l: 50, r: 20, t: 20, b: 35 },
              height: 280,
              autosize: true,
              xaxis: { range: [1980, 2026], gridcolor: gridColor, tickformat: 'd' },
              yaxis: { gridcolor: gridColor, title: '%' },
              showlegend: true,
              legend: { orientation: 'h', y: 1.15, x: 0 }
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
      </div>

      {/* ── 7. Evolución Histórica de Producción e Impacto (2 Gráficos) ───── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* Documentos Anuales */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <BookOpen size={18} style={{ color: '#f59e0b' }} />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Documentos Publicados por Año (1980–2026)</h3>
          </div>
          <Plot
            data={annualDocsChartData}
            layout={{
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: 'Plus Jakarta Sans, sans-serif', color: fontColor },
              margin: { l: 50, r: 20, t: 20, b: 35 },
              height: 280,
              autosize: true,
              xaxis: { range: [1980, 2026], gridcolor: gridColor, tickformat: 'd' },
              yaxis: { gridcolor: gridColor, title: 'Documentos' }
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>

        {/* FWCI Anual */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
            <TrendingUp size={18} style={{ color: 'var(--accent-blue)' }} />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Evolución FWCI Promedio Institucional (1980–2026)</h3>
          </div>
          <Plot
            data={annualFwciChartData}
            layout={{
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: 'Plus Jakarta Sans, sans-serif', color: fontColor },
              margin: { l: 50, r: 20, t: 20, b: 35 },
              height: 280,
              autosize: true,
              xaxis: { range: [1980, 2026], gridcolor: gridColor, tickformat: 'd' },
              yaxis: { gridcolor: gridColor, title: 'FWCI' },
              shapes: [
                {
                  type: 'line',
                  xref: 'paper',
                  x0: 0,
                  x1: 1,
                  y0: 1.0,
                  y1: 1.0,
                  line: { color: '#ef4444', width: 2, dash: 'dash' }
                }
              ],
              annotations: [
                {
                  xref: 'paper',
                  yref: 'y',
                  x: 0.98,
                  y: 1.05,
                  text: 'Base Mundial (1.0)',
                  showarrow: false,
                  font: { color: '#ef4444', size: 10 }
                }
              ]
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
      </div>

      {/* ── 8. GRUPO 1: Identificadores de Académicos (4 Métricas) ──────────── */}
      <div style={{ marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.6rem' }}>
          <ShieldCheck size={17} style={{ color: 'var(--accent-cyan)' }} />
          <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Identificadores de Académicos</h3>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">% Académicos con ORCID</span>
            <span className="kpi-metric-val">{kpiIds.pct_academic_orcid}%</span>
            <span className="badge badge-cyan" style={{ width: 'fit-content', fontSize: '0.7rem' }}>ORCID Registrado</span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">% Académicos con algún ID</span>
            <span className="kpi-metric-val">{kpiIds.pct_academic_any_id}%</span>
            <span className="badge badge-purple" style={{ width: 'fit-content', fontSize: '0.7rem' }}>ORCID, OA o CVU</span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">% con ORCID</span>
            <span className="kpi-metric-val">{kpiIds.pct_snii_orcid}%</span>
            <span className="badge badge-emerald" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Padrón Oficial</span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">% con algún ID</span>
            <span className="kpi-metric-val">{kpiIds.pct_snii_any_id}%</span>
            <span className="badge badge-amber" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Multicatálogo</span>
          </div>
        </div>
      </div>

      {/* ── 9. GRUPO 2: Métricas Generales (7 Métricas) ─────────────────────── */}
      <div style={{ marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.6rem' }}>
          <Layers size={17} style={{ color: 'var(--accent-purple)' }} />
          <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Métricas Generales de Producción e Impacto</h3>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">Producción Total</span>
            <span className="kpi-metric-val">{kpiGen.total_census.toLocaleString()}</span>
            <span className="badge badge-cyan" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Censo Neo4j</span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">Indizada en OpenAlex</span>
            <span className="kpi-metric-val">{kpiGen.indexed_works.toLocaleString()}</span>
            <span className="badge badge-purple" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Metadatos Completos</span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">No. de Investigadoras e Investigadores</span>
            <span className="kpi-metric-val">{kpiGen.official_snii_count.toLocaleString()}</span>
            <span className="badge badge-emerald" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Padrón Oficial</span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">Citas Acumuladas</span>
            <span className="kpi-metric-val">{kpiGen.total_citations.toLocaleString()}</span>
            <span className="badge badge-amber" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Total Directo</span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">Citas/artículo</span>
            <span className="kpi-metric-val">{kpiGen.citations_per_paper}</span>
            <span className="badge badge-cyan" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Promedio</span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">FWCI Promedio</span>
            <span className="kpi-metric-val">{kpiGen.fwci_mean}</span>
            <span className="badge badge-emerald" style={{ width: 'fit-content', fontSize: '0.7rem' }}>
              {kpiGen.fwci_mean > 1 ? `+${Math.round((kpiGen.fwci_mean - 1) * 100)}% s/ Mundo` : 'Normalizado'}
            </span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">% Open Access</span>
            <span className="kpi-metric-val">{kpiGen.pct_open_access}%</span>
            <span className="badge badge-purple" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Acceso Abierto</span>
          </div>
        </div>
      </div>

      {/* ── 10. GRUPO 3: Métricas de Excelencia (4 Métricas) ─────────────────── */}
      <div style={{ marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.6rem' }}>
          <Award size={17} style={{ color: 'var(--accent-amber)' }} />
          <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Métricas de Excelencia Científica</h3>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem' }}>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">Percentil Promedio</span>
            <span className="kpi-metric-val">{kpiExcel.percentile_avg}</span>
            <span className="badge badge-cyan" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Impacto Relativo</span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">% Top 10%</span>
            <span className="kpi-metric-val">{kpiExcel.pct_top_10}%</span>
            <span className="badge badge-purple" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Decil Superior Mundial</span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">% Top 1%</span>
            <span className="kpi-metric-val">{kpiExcel.pct_top_1}%</span>
            <span className="badge badge-emerald" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Élite Mundial</span>
          </div>
          <div className="glass-card kpi-metric-card">
            <span className="kpi-metric-label">Índice H</span>
            <span className="kpi-metric-val">{kpiExcel.h_index}</span>
            <span className="badge badge-amber" style={{ width: 'fit-content', fontSize: '0.7rem' }}>Índice de Hirsch</span>
          </div>
        </div>

        {/* Distribución por Tramos de Impacto Observado (Tiers T1–T4) */}
        {tiersInst && (
          <div className="glass-card" style={{ marginTop: '0.75rem', padding: '0.85rem 1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.6rem' }}>
              <span style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                Distribución por Tramos de Impacto Observado (Tiers T1–T4):
              </span>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                Normalizado por disciplina y año (DORA / Leiden)
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.5rem' }}>
              <div style={{ padding: '0.5rem 0.75rem', borderRadius: '6px', borderLeft: '3px solid #8b5cf6', background: 'rgba(139, 92, 246, 0.05)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#a78bfa' }}>Tier 1 (T1)</span>
                  <span className="badge badge-purple" style={{ fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>Alto</span>
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: '0.2rem', color: 'var(--text-primary)' }}>
                  {tiersInst.t1Pct ?? 0}%
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                  {tiersInst.T1 ? `${tiersInst.T1.toLocaleString()} obras` : 'Top 25% mundial'}
                </div>
              </div>
              <div style={{ padding: '0.5rem 0.75rem', borderRadius: '6px', borderLeft: '3px solid #3b82f6', background: 'rgba(59, 130, 246, 0.05)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#60a5fa' }}>Tier 2 (T2)</span>
                  <span className="badge badge-blue" style={{ fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>Medio-Alto</span>
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: '0.2rem', color: 'var(--text-primary)' }}>
                  {tiersInst.t2Pct ?? 0}%
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                  {tiersInst.T2 ? `${tiersInst.T2.toLocaleString()} obras` : 'Percentil 50–74%'}
                </div>
              </div>
              <div style={{ padding: '0.5rem 0.75rem', borderRadius: '6px', borderLeft: '3px solid #10b981', background: 'rgba(16, 185, 129, 0.05)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#34d399' }}>Tier 3 (T3)</span>
                  <span className="badge badge-emerald" style={{ fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>Medio-Bajo</span>
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: '0.2rem', color: 'var(--text-primary)' }}>
                  {tiersInst.t3Pct ?? 0}%
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                  {tiersInst.T3 ? `${tiersInst.T3.toLocaleString()} obras` : 'Percentil 25–49%'}
                </div>
              </div>
              <div style={{ padding: '0.5rem 0.75rem', borderRadius: '6px', borderLeft: '3px solid #f59e0b', background: 'rgba(245, 158, 11, 0.05)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#fbbf24' }}>Tier 4 (T4)</span>
                  <span className="badge badge-amber" style={{ fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>Base</span>
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: '0.2rem', color: 'var(--text-primary)' }}>
                  {tiersInst.t4Pct ?? 0}%
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                  {tiersInst.T4 ? `${tiersInst.T4.toLocaleString()} obras` : 'Percentil 0–24%'}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── 11. GRUPO 4 & 5: Velocidad, Colaboración y Costos APC ────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        {/* Velocidad y Colaboración */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.75rem' }}>
            <TrendingUp size={17} style={{ color: 'var(--accent-cyan)' }} />
            <h3 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Velocidad de Citas y Colaboración</h3>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.6rem' }}>
            <div style={{ background: 'var(--bg-card)', padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Citas/año (avg)</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>{kpiVel.velocity_avg}</div>
            </div>
            <div style={{ background: 'var(--bg-card)', padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Citas últ. 3 años</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>{kpiVel.recent_cites_3yr.toLocaleString()}</div>
            </div>
            <div style={{ background: 'var(--bg-card)', padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>% Colab. Internacional</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--accent-purple)' }}>{kpiVel.pct_international}%</div>
            </div>
            <div style={{ background: 'var(--bg-card)', padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Países/paper (avg)</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>{kpiVel.avg_countries}</div>
            </div>
            <div style={{ background: 'var(--bg-card)', padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Autores/paper (avg)</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>{kpiVel.avg_author_count}</div>
            </div>
          </div>
        </div>

        {/* Acceso Abierto y Costos APC */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.75rem' }}>
            <DollarSign size={17} style={{ color: 'var(--accent-emerald)' }} />
            <h3 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Acceso Abierto y Costos Estimados (APC)</h3>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.6rem' }}>
            <div style={{ background: 'var(--bg-card)', padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>APC Total Estimado</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--accent-emerald)' }}>${kpiCosts.apc_paid_usd.toLocaleString()} USD</div>
            </div>
            <div style={{ background: 'var(--bg-card)', padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>% Papers con APC</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>{kpiCosts.pct_apc}%</div>
            </div>
            <div style={{ background: 'var(--bg-card)', padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Vida Media Citas</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>{kpiCosts.half_life_avg} años</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── 12. Glosario Metodológico Interactivo (Accordion) ───────────────── */}
      <div className="glass-card" style={{ marginBottom: '1.5rem', padding: '0.85rem 1.25rem' }}>
        <button
          onClick={() => setShowGlossary(!showGlossary)}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-primary)' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <HelpCircle size={18} style={{ color: 'var(--accent-cyan)' }} />
            <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>¿Qué significan estos indicadores metodológicos?</span>
          </div>
          {showGlossary ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </button>

        {showGlossary && (
          <div style={{ marginTop: '0.85rem', paddingTop: '0.85rem', borderTop: '1px solid var(--border-subtle)', fontSize: '0.85rem', lineHeight: '1.6', color: 'var(--text-secondary)' }}>
            <ul style={{ paddingLeft: '1.25rem', margin: 0 }}>
              <li><b>FWCI (Field-Weighted Citation Impact):</b> Relación entre las citas recibidas y el promedio esperado para la misma disciplina y año (Promedio Mundial = 1.0).</li>
              <li><b>Percentil Promedio:</b> Posición promedio mundial de los artículos respecto a sus citas (menor número indica mayor impacto; Top 10% son percentiles ≤ 10).</li>
              <li><b>% Top 10% / Top 1%:</b> Porcentaje de la producción científica ubicada en el 10% o 1% más citado a nivel internacional.</li>
              <li><b>% Open Access:</b> Proporción de artículos disponibles en acceso abierto (vías Gold, Green, Hybrid, Bronze).</li>
              <li><b>Citas/año (avg):</b> Velocidad promedio de citación anual desde la fecha de publicación del artículo.</li>
              <li><b>Citas últ. 3 años:</b> Impacto fresco acumulado en los últimos 36 meses.</li>
              <li><b>% Colaboración Internacional:</b> Porcentaje de artículos donde participa al menos una institución extranjera.</li>
              <li><b>Países/paper (avg):</b> Número promedio de países representados en las firmas de cada publicación.</li>
              <li><b>Autores/paper (avg):</b> Número promedio de coautores firmantes por artículo.</li>
              <li><b>APC Total:</b> Costo referencial acumulado en USD por cargos de procesamiento de artículos (Article Processing Charges).</li>
              <li><b>Vida Media Citas:</b> Años transcurridos hasta que los artículos acumulan el 50% de sus citas totales históricas.</li>
              <li><b>Gini temático:</b> Grado de concentración de la producción científica (0 = mono-temático, 1 = completamente disperso).</li>
            </ul>
          </div>
        )}
      </div>

      {/* ── 12b. Reporte Bibliométrico con Inteligencia Artificial ───────────── */}
      <AIReportViewer
        type="inst"
        targetName={selectedSubdependency || selectedDependency || selectedInstitution || "Entidad"}
        viewMode={viewMode}
        hasReport={metricsData?.has_ai_report}
      />

      {/* ── 13. Tabla Completa de Publicaciones Institucionales ─────────────── */}
      <div className="glass-card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <BookOpen size={20} style={{ color: 'var(--accent-blue)' }} />
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Publicaciones Científicas Institucionales</h3>
          </div>
          <span className="badge badge-cyan">
            {totalPapers.toLocaleString()} artículos {selectedYear !== 'Todos' ? `en ${selectedYear}` : 'totales'}
          </span>
        </div>

        {/* Controles de Filtros Dinámicos */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
          <div>
            <label className="form-label" style={{ fontSize: '0.75rem' }}>Filtrar por Año</label>
            <select
              className="form-select"
              value={selectedYear}
              onChange={(e) => { setSelectedYear(e.target.value); setPapersPage(0); }}
            >
              <option value="Todos">Todos los años</option>
              {availableYears.map((yr) => (
                <option key={yr} value={yr}>
                  {yr} {yr === currentYear ? '★ (Año en curso)' : ''}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="form-label" style={{ fontSize: '0.75rem' }}>Filtrar por ODS</label>
            <select
              className="form-select"
              value={selectedOds}
              onChange={(e) => { setSelectedOds(e.target.value); setPapersPage(0); }}
            >
              <option value="Todos">Todos los ODS</option>
              {availableOds.map((ods) => (
                <option key={ods} value={ods}>{ods}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="form-label" style={{ fontSize: '0.75rem' }}>Buscar por Título / Revista</label>
            <div style={{ position: 'relative' }}>
              <input
                type="text"
                className="form-input"
                placeholder="Escribe para buscar..."
                value={searchPaper}
                onChange={(e) => { setSearchPaper(e.target.value); setPapersPage(0); }}
                style={{ paddingLeft: '2rem' }}
              />
              <Search size={14} style={{ position: 'absolute', left: '0.7rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            </div>
          </div>
        </div>

        {/* Tabla */}
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                <th style={{ padding: '0.6rem 0.8rem', width: '60px' }}>Año</th>
                <th style={{ padding: '0.6rem 0.8rem' }}>Título</th>
                <th style={{ padding: '0.6rem 0.8rem' }}>Revista / Fuente</th>
                <th style={{ padding: '0.6rem 0.8rem', width: '70px', textAlign: 'right' }}>Citas</th>
                <th style={{ padding: '0.6rem 0.8rem' }}>ODS</th>
                <th style={{ padding: '0.6rem 0.8rem' }}>Tópico</th>
                <th style={{ padding: '0.6rem 0.8rem' }}>Autores</th>
                <th style={{ padding: '0.6rem 0.8rem', textAlign: 'right', width: '130px' }}>Enlaces</th>
              </tr>
            </thead>
            <tbody>
              {loadingPapers ? (
                <tr>
                  <td colSpan={8} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    Cargando publicaciones...
                  </td>
                </tr>
              ) : papersData.length > 0 ? (
                papersData.map((p, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '0.7rem 0.8rem', fontWeight: 600 }}>{p.year}</td>
                    <td style={{ padding: '0.7rem 0.8rem', fontWeight: 600, color: 'var(--text-primary)', maxWidth: '300px' }}>
                      {p.title}
                    </td>
                    <td style={{ padding: '0.7rem 0.8rem', color: 'var(--text-secondary)' }}>{p.source}</td>
                    <td style={{ padding: '0.7rem 0.8rem', textAlign: 'right', fontWeight: 700, color: 'var(--accent-purple)' }}>
                      {p.citations.toLocaleString()}
                    </td>
                    <td style={{ padding: '0.7rem 0.8rem' }}>
                      {p.ods && p.ods !== '—' ? (
                        <span className="badge badge-emerald" style={{ fontSize: '0.7rem' }}>{p.ods}</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>—</span>
                      )}
                    </td>
                    <td style={{ padding: '0.7rem 0.8rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      {p.topic}
                    </td>
                    <td style={{ padding: '0.7rem 0.8rem', fontSize: '0.8rem', color: 'var(--text-muted)', maxWidth: '200px' }}>
                      {p.authors}
                    </td>
                    <td style={{ padding: '0.7rem 0.8rem', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '0.35rem', justifyContent: 'flex-end' }}>
                        {p.doi_url && (
                          <a
                            href={p.doi_url}
                            target="_blank"
                            rel="noreferrer"
                            className="btn btn-secondary btn-sm"
                            style={{ padding: '0.2rem 0.45rem', fontSize: '0.7rem' }}
                            title="Ver en DOI"
                          >
                            DOI
                            <ExternalLink size={10} />
                          </a>
                        )}
                        {p.openalex_url && (
                          <a
                            href={p.openalex_url}
                            target="_blank"
                            rel="noreferrer"
                            className="btn btn-secondary btn-sm"
                            style={{ padding: '0.2rem 0.45rem', fontSize: '0.7rem' }}
                            title="Ver en OpenAlex"
                          >
                            OA
                            <ExternalLink size={10} />
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No se encontraron publicaciones con los filtros seleccionados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Paginación */}
        {totalPapers > PAGE_SIZE && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)', flexWrap: 'wrap', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Mostrando <b>{papersPage * PAGE_SIZE + 1}</b> a <b>{Math.min((papersPage + 1) * PAGE_SIZE, totalPapers)}</b> de <b>{totalPapers.toLocaleString()}</b> artículos
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <button
                className="btn btn-secondary btn-sm"
                disabled={papersPage === 0}
                onClick={() => setPapersPage((prev) => Math.max(0, prev - 1))}
              >
                Anterior
              </button>
              <span style={{ fontSize: '0.8rem', padding: '0 0.5rem', color: 'var(--text-muted)' }}>
                Página {papersPage + 1} de {Math.ceil(totalPapers / PAGE_SIZE)}
              </span>
              <button
                className="btn btn-secondary btn-sm"
                disabled={(papersPage + 1) * PAGE_SIZE >= totalPapers}
                onClick={() => setPapersPage((prev) => prev + 1)}
              >
                Siguiente
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default InstitutionalPanorama;
