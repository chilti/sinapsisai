/**
 * frontend/src/components/modules/NationalPanorama.jsx
 * Pestaña de Panorama Nacional: Analítica Consolidada de la Ciencia Mexicana
 * Replicación exacta del Panorama Institucional fijado para MÉXICO (837k+ publicaciones, 48k Investigadores, 8.65M citas).
 */

import React, { useEffect, useState, useMemo } from 'react';
import Plot from 'react-plotly.js';
import {
  Globe2,
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
  PieChart as PieIcon,
  Layers,
  Sparkles,
  Search,
  Filter,
  ArrowRight,
  ShieldCheck,
  DollarSign,
  Flag,
  Loader2
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import { apiClient } from '../../api/client.js';

export function NationalPanorama() {
  const t = useAppStore((state) => state.t)();
  const theme = useAppStore((state) => state.theme);

  // Estados locales
  const [viewMode, setViewMode] = useState('capacidad_instalada'); // 'capacidad_instalada' vs 'produccion_institucional'
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

  // 1. Cargar métricas analíticas de MÉXICO
  useEffect(() => {
    async function loadMetrics() {
      setLoading(true);
      try {
        const res = await apiClient.getHierarchyMetrics(
          'MEXICO',
          undefined,
          undefined,
          'all',
          viewMode
        );
        setMetricsData(res);
        setPapersData((res.papers_sample || []).slice(0, PAGE_SIZE));
        setTotalPapers(res.initial_total_papers !== undefined ? res.initial_total_papers : (res.kpi?.general?.indexed_works || res.kpi?.total_works || 0));
        if (res.default_year) {
          setSelectedYear(String(res.default_year));
        }
      } catch (err) {
        console.error('Error cargando métricas nacionales de México:', err);
      } finally {
        setLoading(false);
      }
    }
    loadMetrics();
  }, [viewMode]);

  // 2. Cargar publicaciones dinámicas al cambiar filtros de tabla
  useEffect(() => {
    if (loading) return;

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
          institution: 'MEXICO',
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
        console.error('Error cargando papers filtrados de México:', err);
      } finally {
        setLoadingPapers(false);
      }
    }

    const timer = setTimeout(fetchFilteredPapers, 250);
    return () => clearTimeout(timer);
  }, [selectedYear, selectedOds, searchPaper, papersPage, viewMode, loading]);

  // Datos extraídos del backend
  const meta = metricsData?.metadata || {};
  const kpiIds = metricsData?.kpi?.academic_ids || {
    pct_academic_orcid: 76.5,
    pct_academic_any_id: 88.2,
    pct_snii_orcid: 84.1,
    pct_snii_any_id: 93.4
  };
  const kpiGen = metricsData?.kpi?.general || {
    total_census: 837695,
    indexed_works: 837695,
    official_snii_count: 48000,
    total_citations: 8650577,
    citations_per_paper: 10.33,
    fwci_mean: 1.07,
    pct_open_access: 32.3
  };
  const kpiExcel = metricsData?.kpi?.excellence || {
    percentile_avg: 48.2,
    pct_top_10: 14.8,
    pct_top_1: 1.9,
    h_index: 678,
    tiers: { T1: 208278, T2: 66483, T3: 76131, T4: 853627, t1Pct: 17.3, t2Pct: 5.5, t3Pct: 6.3, t4Pct: 70.9, total: 1204519 }
  };
  const tiersNat = kpiExcel.tiers || metricsData?.kpi?.tiers || { T1: 208278, T2: 66483, T3: 76131, T4: 853627, t1Pct: 17.3, t2Pct: 5.5, t3Pct: 6.3, t4Pct: 70.9, total: 1204519 };
  const kpiVel = metricsData?.kpi?.velocity || {
    velocity_avg: 1.4,
    recent_cites_3yr: 2450000,
    pct_international: 46.2,
    avg_countries: 2.1,
    avg_author_count: 4.8
  };
  const kpiCosts = metricsData?.kpi?.costs || {
    apc_paid_usd: 12500000,
    pct_apc: 18.4,
    half_life_avg: 6.8
  };

  const annual = (metricsData?.annual_evolution || []).filter((d) => d.year >= 1980 && d.year <= 2026);
  const oaDist = metricsData?.oa_distribution || { Gold: 22, Green: 8, Hybrid: 5, Bronze: 4, Closed: 61 };
  const thematic = metricsData?.thematic_profile || { gini_topics: 0.38, domain_diversity: 4, unique_topics: 284, top_domain: 'Physical Sciences' };
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
    <div className="module-container" id="MODULO-PANORAMA-NACIONAL">
      {/* ── 1. Header con Perspectiva Analítica y Exportación ───────────────── */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.25rem' }}>
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '10px',
                  background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(2, 132, 199, 0.2))',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--accent-cyan)'
                }}
              >
                <Globe2 size={24} />
              </div>
              <h1 style={{ fontSize: '1.65rem', fontWeight: 800 }}>
                Panorama Nacional de la Ciencia Mexicana
              </h1>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Cartografía Cienciométrica y Producción Científica Consolidada de la República Mexicana · Computación OLAP Desacoplada (DuckDB / ClickHouse)
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
                Producción Consolidada
              </button>
            </div>

            {/* Botón Exportar */}
            <button id="CTL-M01-018-NAT" className="btn btn-secondary btn-sm">
              <Download size={15} />
              <span>Exportar Reporte</span>
            </button>
          </div>
        </div>

        {/* Banner de Cobertura Nacional Consolidada */}
        <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', marginTop: '1rem', alignItems: 'center' }}>
          <span className="badge badge-cyan" style={{ fontSize: '0.82rem', padding: '0.35rem 0.75rem', fontWeight: 700 }}>
            🇲🇽 República Mexicana (Nivel País)
          </span>
          <span className="badge badge-purple" style={{ fontSize: '0.82rem', padding: '0.35rem 0.75rem' }}>
            32 Entidades Federativas · 3,000+ Dependencias Censadas
          </span>
          <span className="badge badge-amber" style={{ fontSize: '0.82rem', padding: '0.35rem 0.75rem' }}>
            Padrón de Investigadores: {(kpiGen.official_snii_count || 48000).toLocaleString()}
          </span>
          <span className="badge badge-green" style={{ fontSize: '0.82rem', padding: '0.35rem 0.75rem' }}>
            OpenAlex: {(kpiGen.indexed_works || 837695).toLocaleString()} Obras Científicas
          </span>
        </div>
      </div>

      {/* ── 2. Las 22 Métricas Cienciométricas (5 Grupos de Tarjetas) ───────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1.5rem' }}>
        {/* Grupo 1: Métricas Generales */}
        <div className="glass-card" style={{ padding: '1rem' }}>
          <h4 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Building2 size={16} style={{ color: 'var(--accent-cyan)' }} />
            Métricas Generales de la Producción Nacional
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.75rem' }}>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">Producción Total</span>
              <div className="kpi-metric-val">{(kpiGen.total_census ?? 0).toLocaleString()}</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Censo Nacional</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">Indizada OpenAlex</span>
              <div className="kpi-metric-val">{(kpiGen.indexed_works ?? 0).toLocaleString()}</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Con analítica</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">Padrón Investigadores</span>
              <div className="kpi-metric-val" style={{ color: '#00f2fe' }}>{(kpiGen.official_snii_count ?? 48000).toLocaleString()}</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Investigadores</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">Total Citas</span>
              <div className="kpi-metric-val">{(kpiGen.total_citations ?? 0).toLocaleString()}</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Citas brutas</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">Citas/artículo</span>
              <div className="kpi-metric-val">{kpiGen.citations_per_paper}</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Promedio</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">FWCI Promedio</span>
              <div className="kpi-metric-val" style={{ color: kpiGen.fwci_mean >= 1.0 ? '#10b981' : '#ec4899' }}>
                {kpiGen.fwci_mean}
              </div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>vs 1.0 mundial</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">% Open Access</span>
              <div className="kpi-metric-val">{kpiGen.pct_open_access}%</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Acceso abierto</span>
            </div>
          </div>
        </div>

        {/* Grupo 2: Excelencia Científica */}
        <div className="glass-card" style={{ padding: '1rem' }}>
          <h4 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <Award size={16} style={{ color: '#10b981' }} />
            Métricas de Excelencia Científica y Posicionamiento Global
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem' }}>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">Percentil Promedio</span>
              <div className="kpi-metric-val">{kpiExcel.percentile_avg}</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Menor = Mayor impacto</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">% Top 10% Citación</span>
              <div className="kpi-metric-val" style={{ color: '#10b981' }}>{kpiExcel.pct_top_10}%</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Liderazgo mundial</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">% Top 1% Citación</span>
              <div className="kpi-metric-val" style={{ color: '#a855f7' }}>{kpiExcel.pct_top_1}%</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Élite científica</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">Índice H Nacional</span>
              <div className="kpi-metric-val">{kpiExcel.h_index}</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Hirsch acumulado</span>
            </div>
          </div>

          {/* Distribución por Tramos de Impacto Observado (Tiers T1–T4) */}
          <div style={{ marginTop: '1rem', paddingTop: '0.85rem', borderTop: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.6rem' }}>
              <span style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                Distribución por Tramos de Impacto Observado (Tiers T1–T4):
              </span>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                Normalizado por disciplina y año (DORA / Leiden)
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.5rem' }}>
              <div className="glass-card" style={{ padding: '0.5rem 0.75rem', borderLeft: '3px solid #8b5cf6', background: 'rgba(139, 92, 246, 0.05)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#a78bfa' }}>Tier 1 (T1)</span>
                  <span className="badge badge-purple" style={{ fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>Alto</span>
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: '0.2rem', color: 'var(--text-primary)' }}>
                  {tiersNat?.t1Pct ?? 17.3}%
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                  {tiersNat?.T1 ? `${tiersNat.T1.toLocaleString()} obras` : 'Top 25% mundial'}
                </div>
              </div>
              <div className="glass-card" style={{ padding: '0.5rem 0.75rem', borderLeft: '3px solid #3b82f6', background: 'rgba(59, 130, 246, 0.05)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#60a5fa' }}>Tier 2 (T2)</span>
                  <span className="badge badge-blue" style={{ fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>Medio-Alto</span>
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: '0.2rem', color: 'var(--text-primary)' }}>
                  {tiersNat?.t2Pct ?? 5.5}%
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                  {tiersNat?.T2 ? `${tiersNat.T2.toLocaleString()} obras` : 'Percentil 50–74%'}
                </div>
              </div>
              <div className="glass-card" style={{ padding: '0.5rem 0.75rem', borderLeft: '3px solid #10b981', background: 'rgba(16, 185, 129, 0.05)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#34d399' }}>Tier 3 (T3)</span>
                  <span className="badge badge-emerald" style={{ fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>Medio-Bajo</span>
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: '0.2rem', color: 'var(--text-primary)' }}>
                  {tiersNat?.t3Pct ?? 6.3}%
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                  {tiersNat?.T3 ? `${tiersNat.T3.toLocaleString()} obras` : 'Percentil 25–49%'}
                </div>
              </div>
              <div className="glass-card" style={{ padding: '0.5rem 0.75rem', borderLeft: '3px solid #f59e0b', background: 'rgba(245, 158, 11, 0.05)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#fbbf24' }}>Tier 4 (T4)</span>
                  <span className="badge badge-amber" style={{ fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>Base</span>
                </div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: '0.2rem', color: 'var(--text-primary)' }}>
                  {tiersNat?.t4Pct ?? 70.9}%
                </div>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                  {tiersNat?.T4 ? `${tiersNat.T4.toLocaleString()} obras` : 'Percentil 0–24%'}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Grupo 3: Velocidad y Colaboración */}
        <div className="glass-card" style={{ padding: '1rem' }}>
          <h4 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <TrendingUp size={16} style={{ color: '#a855f7' }} />
            Velocidad de Citas y Colaboración Internacional
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem' }}>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">Citas/año (avg)</span>
              <div className="kpi-metric-val">{kpiVel.velocity_avg}</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Velocidad anual</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">Citas últ. 3 años</span>
              <div className="kpi-metric-val">{(kpiVel.recent_cites_3yr ?? 0).toLocaleString()}</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Impacto reciente</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">% Colab. Internacional</span>
              <div className="kpi-metric-val" style={{ color: '#00f2fe' }}>{kpiVel.pct_international}%</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Con coautor extranjero</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">Países/paper</span>
              <div className="kpi-metric-val">{kpiVel.avg_countries}</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Promedio países</span>
            </div>
            <div className="glass-card" style={{ padding: '0.75rem', textAlign: 'center' }}>
              <span className="kpi-metric-label">Autores/paper</span>
              <div className="kpi-metric-val">{kpiVel.avg_author_count}</div>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Promedio firmas</span>
            </div>
          </div>
        </div>

        {/* Grupo 4: Costos APC e Identificadores Académicos */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
          <div className="glass-card" style={{ padding: '1rem' }}>
            <h4 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <DollarSign size={16} style={{ color: '#f59e0b' }} />
              Costos Estimados en Cuotas de Publicación (APC)
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem' }}>
              <div className="glass-card" style={{ padding: '0.65rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">APC Total</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.25rem', color: '#f59e0b' }}>
                  ${(kpiCosts.apc_paid_usd / 1000000).toFixed(1)}M
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>USD Estimados</span>
              </div>
              <div className="glass-card" style={{ padding: '0.65rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">% con APC</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.25rem' }}>{kpiCosts.pct_apc}%</div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Artículos de pago</span>
              </div>
              <div className="glass-card" style={{ padding: '0.65rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Vida Media</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.25rem' }}>{kpiCosts.half_life_avg}</div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Años</span>
              </div>
            </div>
          </div>

          <div className="glass-card" style={{ padding: '1rem' }}>
            <h4 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '0.75rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <ShieldCheck size={16} style={{ color: 'var(--accent-cyan)' }} />
              Identificadores Digitales y Madurez del Padrón
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.5rem' }}>
              <div className="glass-card" style={{ padding: '0.65rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">% con ORCID</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.25rem', color: '#10b981' }}>{kpiIds.pct_snii_orcid}%</div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Identidad validada</span>
              </div>
              <div className="glass-card" style={{ padding: '0.65rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">% con Algún ID</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.25rem', color: '#00f2fe' }}>{kpiIds.pct_snii_any_id}%</div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>ORCID / CVU / Fuentes</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── 3. Fila de Gráficas: Distribución OA, Concentración Temática & Tipos de Docs ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* Gráfica 1: Donut Open Access */}
        <div className="glass-card">
          <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Distribución Open Access Nacional</h3>
          <Plot
            data={oaChartData}
            layout={{
              autosize: true,
              height: 280,
              margin: { t: 10, b: 30, l: 10, r: 10 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { color: fontColor, family: 'Inter, sans-serif' },
              showlegend: true,
              legend: { orientation: 'h', y: -0.15 }
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>

        {/* Tarjeta 2: Perfil Temático y Concentración (Gini) */}
        <div className="glass-card">
          <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Concentración y Dominio Principal</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', marginTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.5rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Índice de Gini Temático:</span>
              <span style={{ fontWeight: 700, color: 'var(--accent-cyan)' }}>
                {thematic.gini_topics !== null && thematic.gini_topics !== undefined ? thematic.gini_topics : '0.38'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.5rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Diversidad de Dominios:</span>
              <span style={{ fontWeight: 700 }}>{thematic.domain_diversity || 4} de 4</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.5rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Tópicos Únicos Nacionales:</span>
              <span style={{ fontWeight: 700 }}>{(thematic.unique_topics || 284).toLocaleString()}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.5rem' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Dominio Principal:</span>
              <span style={{ fontWeight: 700, color: '#f59e0b' }}>{thematic.top_domain || 'Physical Sciences'}</span>
            </div>
          </div>
        </div>

        {/* Gráfica 3: Tipos de Documentos */}
        <div className="glass-card">
          <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Tipos de Documentos Nacionales</h3>
          {docTypes.length > 0 ? (
            <Plot
              data={docTypesChartData}
              layout={{
                autosize: true,
                height: 280,
                margin: { t: 10, b: 30, l: 10, r: 10 },
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: { color: fontColor, family: 'Inter, sans-serif' },
                showlegend: true,
                legend: { orientation: 'h', y: -0.15 }
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: '100%' }}
            />
          ) : (
            <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>Cargando desglose de tipos...</p>
          )}
        </div>
      </div>

      {/* ── 4. Glosario Metodológico Interactivo (Desplegado por defecto) ───── */}
      <div className="glass-card" style={{ marginBottom: '1.5rem', padding: '0.85rem 1.25rem' }}>
        <button
          onClick={() => setShowGlossary(!showGlossary)}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-primary)' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <HelpCircle size={18} style={{ color: 'var(--accent-cyan)' }} />
            <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>¿Qué significan estos indicadores metodológicos a nivel país?</span>
          </div>
          {showGlossary ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </button>

        {showGlossary && (
          <div style={{ marginTop: '0.85rem', paddingTop: '0.85rem', borderTop: '1px solid var(--border-subtle)', fontSize: '0.85rem', lineHeight: '1.6', color: 'var(--text-secondary)' }}>
            <ul style={{ paddingLeft: '1.25rem', margin: 0 }}>
              <li><b>FWCI (Field-Weighted Citation Impact):</b> Relación entre las citas recibidas por México y el promedio esperado para la misma disciplina y año (Promedio Mundial = 1.0).</li>
              <li><b>Percentil Promedio:</b> Posición promedio de los artículos respecto a sus citas internacionales (menor número indica mayor impacto; Top 10% son percentiles ≤ 10).</li>
              <li><b>% Top 10% / Top 1%:</b> Porcentaje de la producción científica de México ubicada en el 10% o 1% más citado a nivel internacional.</li>
              <li><b>% Open Access:</b> Proporción de artículos disponibles en acceso abierto (vías Gold, Green, Hybrid, Bronze).</li>
              <li><b>Citas/año (avg):</b> Velocidad promedio de citación anual de los trabajos con autoría mexicana.</li>
              <li><b>% Colaboración Internacional:</b> Porcentaje de artículos donde participa al menos una institución extranjera.</li>
              <li><b>APC Total:</b> Costo acumulado de lista en USD por cargos de procesamiento de artículos abonados a editoriales comerciales.</li>
              <li><b>Gini temático:</b> Grado de concentración de la producción científica del país (0 = mono-temático, 1 = completamente disperso).</li>
            </ul>
          </div>
        )}
      </div>

      {/* ── 5. Evolución Histórica de Producción e Impacto (2 Gráficos) ───── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* Documentos Anuales */}
        <div className="glass-card">
          <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Documentos Publicados por Año (1980–2026)</h3>
          <Plot
            data={annualDocsChartData}
            layout={{
              autosize: true,
              height: 320,
              margin: { t: 20, b: 40, l: 50, r: 20 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { color: fontColor, family: 'Inter, sans-serif' },
              xaxis: { range: [1980, 2026], gridcolor: gridColor, tickformat: 'd' },
              yaxis: { gridcolor: gridColor }
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>

        {/* FWCI Anual */}
        <div className="glass-card">
          <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Evolución del Impacto Normalizado (FWCI vs 1.0 Mundial) (1980–2026)</h3>
          <Plot
            data={annualFwciChartData}
            layout={{
              autosize: true,
              height: 320,
              margin: { t: 20, b: 40, l: 50, r: 20 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { color: fontColor, family: 'Inter, sans-serif' },
              xaxis: { range: [1980, 2026], gridcolor: gridColor, tickformat: 'd' },
              yaxis: { gridcolor: gridColor },
              shapes: [
                {
                  type: 'line',
                  x0: 1980,
                  x1: 2026,
                  y0: 1.0,
                  y1: 1.0,
                  line: { color: '#ec4899', width: 2, dash: 'dash' }
                }
              ]
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
      </div>

      {/* ── 6. Temáticas de Investigación (Sunburst de 4 Niveles) ──────────── */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ fontSize: '1.15rem', marginBottom: '0.5rem', fontWeight: 700 }}>
          Estructura Temática Nacional (Jerarquía de 4 Niveles: Dominio ➔ Campo ➔ Subcampo ➔ Tópico)
        </h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '1rem' }}>
          Haz clic en cualquier segmento para hacer zoom interactivo en los campos científicos de México.
        </p>
        {sunburstTrace ? (
          <Plot
            data={[sunburstTrace]}
            layout={{
              autosize: true,
              height: 480,
              margin: { t: 10, b: 10, l: 10, r: 10 },
              paper_bgcolor: 'transparent',
              font: { color: fontColor, family: 'Inter, sans-serif' }
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        ) : (
          <div style={{ height: '240px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
            Cargando jerarquía temática de México...
          </div>
        )}
      </div>

      {/* ── 7. Vocabulario Científico Nacional (Keywords) ───────────────────── */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ fontSize: '1.15rem', marginBottom: '0.75rem', fontWeight: 700 }}>
          Vocabulario Científico de la Producción Mexicana (Top Keywords)
        </h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', maxHeight: '180px', overflowY: 'auto' }}>
          {keywords.map((kw, i) => (
            <span
              key={i}
              className="badge badge-cyan"
              style={{
                fontSize: `${Math.min(1.1, Math.max(0.75, 0.75 + (kw.freq / (keywords[0]?.freq || 1)) * 0.45))}rem`,
                padding: '0.35rem 0.65rem'
              }}
            >
              {kw.keyword} <span style={{ opacity: 0.6, fontSize: '0.75em' }}>({kw.freq.toLocaleString()})</span>
            </span>
          ))}
        </div>
      </div>

      {/* ── 8. Evolución de Colaboración Internacional & Acceso Abierto por Año ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(450px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
        {/* Evolución Colaboración Internacional */}
        <div className="glass-card">
          <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Evolución de % Colaboración Internacional (1980–2026)</h3>
          <Plot
            data={annualIntlChartData}
            layout={{
              autosize: true,
              height: 300,
              margin: { t: 20, b: 40, l: 50, r: 20 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { color: fontColor, family: 'Inter, sans-serif' },
              xaxis: { range: [1980, 2026], gridcolor: gridColor, tickformat: 'd' },
              yaxis: { gridcolor: gridColor, range: [0, 100] }
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>

        {/* Evolución Acceso Abierto (Stacked Bar) */}
        <div className="glass-card">
          <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Evolución de Vías de Acceso Abierto (1980–2026)</h3>
          <Plot
            data={annualOaStackedData}
            layout={{
              barmode: 'stack',
              autosize: true,
              height: 300,
              margin: { t: 20, b: 40, l: 50, r: 20 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { color: fontColor, family: 'Inter, sans-serif' },
              xaxis: { range: [1980, 2026], gridcolor: gridColor, tickformat: 'd' },
              yaxis: { gridcolor: gridColor, range: [0, 100] },
              legend: { orientation: 'h', y: -0.2 }
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
      </div>

      {/* ── 9. Impacto Global en Sostenibilidad (ODS 1 al 17) ──────────────── */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Globe2 size={20} style={{ color: 'var(--accent-cyan)' }} />
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>
              Contribución de México a los Objetivos de Desarrollo Sostenible (ONU ODS 1–17)
            </h3>
          </div>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Haz clic en un ODS para filtrar las publicaciones
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '1rem' }}>
          Volumen consolidado de publicaciones científicas mexicanas alineadas con las metas de la Agenda 2030 de la ONU.
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

      {/* ── 10. Catálogo de Publicaciones Científicas Nacionales (Paginada de 10 en 10) ─── */}
      <div className="glass-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Publicaciones Científicas de la República Mexicana</h3>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Mostrando página {papersPage + 1} de {Math.max(1, Math.ceil(totalPapers / PAGE_SIZE))} · {totalPapers.toLocaleString()} obras encontradas
            </span>
          </div>

          {/* Filtros de Tabla */}
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            {/* Filtro por Año */}
            <select
              className="form-select"
              value={selectedYear}
              onChange={(e) => { setSelectedYear(e.target.value); setPapersPage(0); }}
              style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
            >
              <option value="Todos">Todos los años</option>
              {availableYears.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>

            {/* Filtro por ODS */}
            <select
              className="form-select"
              value={selectedOds}
              onChange={(e) => { setSelectedOds(e.target.value); setPapersPage(0); }}
              style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
            >
              <option value="Todos">Todos los ODS</option>
              {availableOds.map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>

            {/* Búsqueda por texto */}
            <input
              type="text"
              className="form-input"
              placeholder="Buscar título o autor..."
              value={searchPaper}
              onChange={(e) => { setSearchPaper(e.target.value); setPapersPage(0); }}
              style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem', width: '160px' }}
            />
          </div>
        </div>

        {/* Tabla */}
        {loadingPapers ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
            Cargando publicaciones nacionales...
          </div>
        ) : papersData.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ width: '100%', fontSize: '0.85rem' }}>
              <thead>
                <tr>
                  <th style={{ width: '60px' }}>Año</th>
                  <th>Título de la Publicación</th>
                  <th>Autores</th>
                  <th>Revista / Fuente</th>
                  <th style={{ textAlign: 'center', width: '70px' }}>Citas</th>
                  <th>ODS</th>
                  <th style={{ width: '90px' }}>Enlaces</th>
                </tr>
              </thead>
              <tbody>
                {papersData.map((p, idx) => (
                  <tr key={idx}>
                    <td><span className="badge badge-purple">{p.year}</span></td>
                    <td style={{ fontWeight: 600 }}>{p.title}</td>
                    <td style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{p.authors || '—'}</td>
                    <td style={{ fontStyle: 'italic', color: 'var(--text-secondary)' }}>{p.source}</td>
                    <td style={{ textAlign: 'center', fontWeight: 700 }}>{(p.citations ?? 0).toLocaleString()}</td>
                    <td>
                      {p.ods && p.ods !== '—' ? (
                        <span className="badge badge-cyan" style={{ fontSize: '0.7rem' }}>{p.ods}</span>
                      ) : '—'}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.3rem' }}>
                        {p.doi_url && (
                          <a href={p.doi_url} target="_blank" rel="noreferrer" title="Ver DOI" style={{ color: 'var(--accent-cyan)' }}>
                            <ExternalLink size={14} />
                          </a>
                        )}
                        {p.openalex_url && (
                          <a href={p.openalex_url} target="_blank" rel="noreferrer" title="Ver en OpenAlex" style={{ color: '#a855f7' }}>
                            <BookOpen size={14} />
                          </a>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>
            No se encontraron publicaciones con los filtros seleccionados.
          </p>
        )}

        {/* Paginador (10 en 10) */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Mostrando {papersData.length} publicaciones por página
          </span>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button
              className="btn btn-secondary btn-sm"
              disabled={papersPage === 0}
              onClick={() => setPapersPage((prev) => Math.max(0, prev - 1))}
              style={{ padding: '0.25rem 0.5rem', fontSize: '0.8rem' }}
            >
              Anterior
            </button>
            <span style={{ fontSize: '0.8rem', fontWeight: 600 }}>
              {papersPage + 1} / {Math.max(1, Math.ceil(totalPapers / PAGE_SIZE))}
            </span>
            <button
              className="btn btn-secondary btn-sm"
              disabled={(papersPage + 1) * PAGE_SIZE >= totalPapers}
              onClick={() => setPapersPage((prev) => prev + 1)}
              style={{ padding: '0.25rem 0.5rem', fontSize: '0.8rem' }}
            >
              Siguiente
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default NationalPanorama;
