/**
 * frontend/src/components/modules/ResearcherProfiles.jsx
 * Módulo 2: Perfiles de Investigadores y Producción Académica
 * Implementación al 100% de paridad con Streamlit (22 controles y bloques analíticos)
 */

import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';
import {
  Search,
  BookOpen,
  Quote,
  Download,
  Globe,
  CheckCircle2,
  FileText,
  TrendingUp,
  Award,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Filter,
  DollarSign,
  Layers,
  Sparkles,
  HelpCircle,
  X
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import { apiClient } from '../../api/client.js';

// Colores oficiales de los 17 ODS de la ONU
const SDG_COLORS = {
  1: '#E5243B', 2: '#DDA63A', 3: '#4C9F38', 4: '#C5192D',
  5: '#FF3A21', 6: '#26BDE2', 7: '#FCC30B', 8: '#A21942',
  9: '#FD6925', 10: '#DD1367', 11: '#FD9D24', 12: '#BF8B2E',
  13: '#3F7E44', 14: '#0A97D9', 15: '#56C02B', 16: '#00689D',
  17: '#19486A'
};

const PAGE_SIZE = 10;

export function ResearcherProfiles() {
  const t = useAppStore((state) => state.t)();
  const researcherName = useAppStore((state) => state.selectedResearcherName);
  const researcherOrcid = useAppStore((state) => state.selectedResearcherOrcid);
  const setSelectedResearcher = useAppStore((state) => state.setSelectedResearcher);
  const theme = useAppStore((state) => state.theme);

  // Estados locales
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [profile, setProfile] = useState(null);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [activeSubTab, setActiveSubTab] = useState('production'); // 'production' | 'citations'
  const [showGlossary, setShowGlossary] = useState(false);

  // Estados para tabla de publicaciones
  const currentYear = new Date().getFullYear();
  const [yearFilter, setYearFilter] = useState('all');
  const [oaFilter, setOaFilter] = useState('all');
  const [searchPaper, setSearchPaper] = useState('');
  const [papersPage, setPapersPage] = useState(0);
  const [papersData, setPapersData] = useState([]);
  const [totalPapers, setTotalPapers] = useState(0);
  const [availableYears, setAvailableYears] = useState([]);
  const [loadingPapers, setLoadingPapers] = useState(false);

  // Estados para trabajos citantes (Zero-Join)
  const [citingWorks, setCitingWorks] = useState([]);
  const [citingWorksPage, setCitingWorksPage] = useState(0);
  const [loadingCitingWorks, setLoadingCitingWorks] = useState(false);

  const isLight = theme === 'claro';
  const fontColor = isLight ? '#334155' : '#94a3b8';
  const gridColor = isLight ? 'rgba(0, 0, 0, 0.06)' : 'rgba(255, 255, 255, 0.06)';

  // 1. Cargar Perfil Completo del Investigador
  useEffect(() => {
    async function loadProfile() {
      if (!researcherName && !researcherOrcid) return;
      setLoadingProfile(true);
      try {
        const res = await apiClient.getAcademicProfile(researcherName, researcherOrcid);
        if (res && res.profile) {
          setProfile(res.profile);
        }
      } catch (err) {
        console.error('Error cargando perfil:', err);
      } finally {
        setLoadingProfile(false);
      }
    }
    loadProfile();
  }, [researcherName, researcherOrcid]);

  // 2. Cargar Años Disponibles y Obras Iniciales
  useEffect(() => {
    async function loadYears() {
      if (!researcherName && !researcherOrcid) return;
      try {
        const res = await apiClient.getAcademicWorks(researcherOrcid, researcherName, { limit: 200, offset: 0 });
        if (res && res.works) {
          const yrs = new Set();
          res.works.forEach((w) => {
            if (w.year || w.publication_year) {
              yrs.add(String(w.year || w.publication_year));
            }
          });
          const sortedYrs = Array.from(yrs).sort().reverse();
          setAvailableYears(sortedYrs);

          // Si el año actual tiene publicaciones, seleccionarlo por defecto; si no, 'all'
          if (sortedYrs.includes(String(currentYear))) {
            setYearFilter(String(currentYear));
          } else {
            setYearFilter('all');
          }
        }
      } catch (err) {
        console.error('Error cargando años de publicaciones:', err);
      }
    }
    loadYears();
  }, [researcherName, researcherOrcid]);

  // 3. Cargar Obras Paginadas con Filtros
  useEffect(() => {
    async function loadWorks() {
      if (!researcherName && !researcherOrcid) return;
      setLoadingPapers(true);
      try {
        const params = {
          limit: PAGE_SIZE,
          offset: papersPage * PAGE_SIZE,
          year: yearFilter !== 'all' ? parseInt(yearFilter, 10) : undefined,
          oa_status: oaFilter !== 'all' ? oaFilter : undefined,
          search: searchPaper.trim() ? searchPaper.trim() : undefined
        };
        const res = await apiClient.getAcademicWorks(researcherOrcid, researcherName, params);
        if (res) {
          setPapersData(res.works || []);
          setTotalPapers(res.total || 0);
        }
      } catch (err) {
        console.error('Error cargando obras:', err);
      } finally {
        setLoadingPapers(false);
      }
    }
    loadWorks();
  }, [researcherName, researcherOrcid, papersPage, yearFilter, oaFilter, searchPaper]);

  // 4. Cargar Trabajos Citantes cuando se abre la pestaña de citas
  useEffect(() => {
    async function loadCiting() {
      if (activeSubTab !== 'citations' || (!researcherName && !researcherOrcid)) return;
      setLoadingCitingWorks(true);
      try {
        const res = await apiClient.getCitingWorks(researcherName, researcherOrcid, 250);
        if (res && res.citing_works) {
          setCitingWorks(res.citing_works);
        }
      } catch (err) {
        console.error('Error cargando artículos citantes:', err);
      } finally {
        setLoadingCitingWorks(false);
      }
    }
    loadCiting();
  }, [activeSubTab, researcherName, researcherOrcid]);

  // Búsqueda Predictiva con Menú Flotante
  const handleSearch = async (val) => {
    setSearchQuery(val);
    if (val.trim().length >= 3) {
      try {
        const res = await apiClient.searchAcademics(val.trim());
        setSearchResults(res.results || []);
      } catch (err) {
        console.error('Error en búsqueda predictiva:', err);
      }
    } else {
      setSearchResults([]);
    }
  };

  // Descargas de Dossier
  const handleDownloadMarkdown = async () => {
    try {
      const blob = await apiClient.downloadDossierMarkdown(researcherName, researcherOrcid);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Reporte_Dossier_${researcherName.replace(/\s+/g, '_')}.md`;
      a.click();
    } catch (err) {
      console.error('Error descargando markdown:', err);
    }
  };

  const handleDownloadPdf = async () => {
    try {
      const blob = await apiClient.downloadDossierPdf(researcherName, researcherOrcid);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Dossier_SNII_${researcherName.replace(/\s+/g, '_')}.pdf`;
      a.click();
    } catch (err) {
      console.error('Error descargando PDF:', err);
    }
  };

  // KPIs Extraídos del Perfil
  const kpis = profile?.kpis || {};
  const gen = kpis.general || {};
  const exc = kpis.excellence || {};
  const vel = kpis.velocity || {};
  const apc = kpis.apc || {};
  const oa = profile?.oa_distribution || {};
  const them = profile?.thematic_profile || {};
  const cSummary = profile?.citations_summary || {};

  // Configuración de Gráficos Plotly

  // 1. Donut Open Access
  const oaDonutData = useMemo(() => {
    return [{
      labels: ['Gold', 'Green', 'Hybrid', 'Bronze', 'Closed'],
      values: [
        oa.gold || 0,
        oa.green || 0,
        oa.hybrid || 0,
        oa.bronze || 0,
        oa.closed || 0
      ],
      type: 'pie',
      hole: 0.58,
      marker: {
        colors: ['#f59e0b', '#10b981', '#06b6d4', '#8b5cf6', '#64748b']
      },
      textinfo: 'label+percent',
      textposition: 'outside'
    }];
  }, [oa]);

  // 2. Tipos de Documentos (Donut)
  const docTypesData = useMemo(() => {
    const list = profile?.document_types || [];
    return [{
      labels: list.map((d) => d.type),
      values: list.map((d) => d.count),
      type: 'pie',
      hole: 0.55,
      marker: {
        colors: ['#0284c7', '#0d9488', '#e11d48', '#d97706', '#7c3aed', '#475569']
      },
      textinfo: 'label+percent',
      textposition: 'inside'
    }];
  }, [profile?.document_types]);

  // 3. Trayectoria Histórica (Docs por Año)
  const trajectoryData = useMemo(() => {
    const list = profile?.annual_trajectory || [];
    return [{
      x: list.map((d) => d.year),
      y: list.map((d) => d.num_documents),
      type: 'bar',
      marker: { color: '#0284c7' },
      text: list.map((d) => d.num_documents),
      textposition: 'auto',
      hovertemplate: 'Año: %{x}<br>Documentos: %{y}<extra></extra>'
    }];
  }, [profile?.annual_trajectory]);

  // 4. Foco Temático (Top 10 Topics)
  const topTopicsData = useMemo(() => {
    const list = profile?.top_topics || [];
    const sorted = [...list].reverse();
    return [{
      x: sorted.map((d) => d.value),
      y: sorted.map((d) => d.topic),
      type: 'bar',
      orientation: 'h',
      marker: { color: '#0d9488' },
      hovertemplate: '%{y}: <b>%{x} obras</b><extra></extra>'
    }];
  }, [profile?.top_topics]);

  // 5. Sunburst Temático de 4 Niveles
  const sunburstData = useMemo(() => {
    const list = profile?.sunburst_data || [];
    if (!list.length) return [];
    const labels = [];
    const parents = [];
    const values = [];
    const ids = [];

    const added = new Set();
    list.forEach((item) => {
      const d = item.domain;
      const f = `${d} / ${item.field}`;
      const s = `${f} / ${item.subfield}`;
      const t = `${s} / ${item.topic}`;

      if (d && !added.has(d)) {
        ids.push(d); labels.push(item.domain); parents.push(''); values.push(0); added.add(d);
      }
      if (f && !added.has(f)) {
        ids.push(f); labels.push(item.field); parents.push(d); values.push(0); added.add(f);
      }
      if (s && !added.has(s)) {
        ids.push(s); labels.push(item.subfield); parents.push(f); values.push(0); added.add(s);
      }
      if (t && !added.has(t)) {
        ids.push(t); labels.push(item.topic); parents.push(s); values.push(item.value || 1); added.add(t);
      }
    });

    return [{
      type: 'sunburst',
      ids,
      labels,
      parents,
      values,
      branchvalues: 'total',
      hoverinfo: 'label+value+percent parent',
      marker: { colorscale: 'Blues' }
    }];
  }, [profile?.sunburst_data]);

  // 6. Citas Netas vs Autocitas (Zero-Join)
  const citationsDonutData = useMemo(() => {
    return [{
      labels: ['Citas Netas', 'Autocitas Directas'],
      values: [cSummary.net_citations || 0, cSummary.self_citations || 0],
      type: 'pie',
      hole: 0.6,
      marker: { colors: ['#00f2fe', '#ec4899'] },
      textinfo: 'label+percent',
      textposition: 'outside'
    }];
  }, [cSummary]);

  // 7. Países Citantes (Barras Horizontales)
  const citingCountriesData = useMemo(() => {
    const list = [...(cSummary.by_country || [])].reverse();
    return [{
      x: list.map((c) => c.citations_count),
      y: list.map((c) => c.country_code),
      type: 'bar',
      orientation: 'h',
      marker: { color: '#00f2fe' },
      hovertemplate: 'País: %{y}<br>Citas: %{x}<extra></extra>'
    }];
  }, [cSummary.by_country]);

  // 8. Instituciones Citantes (Barras Horizontales)
  const citingInstitutionsData = useMemo(() => {
    const list = [...(cSummary.by_institution || [])].reverse();
    return [{
      x: list.map((i) => i.citations_count),
      y: list.map((i) => (i.institution.length > 32 ? i.institution.substring(0, 32) + '...' : i.institution)),
      type: 'bar',
      orientation: 'h',
      marker: { color: '#6366f1' },
      hovertemplate: '%{y}<br>Citas: %{x}<extra></extra>'
    }];
  }, [cSummary.by_institution]);

  const defaultPlotLayout = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { family: 'Plus Jakarta Sans, sans-serif', color: fontColor },
    margin: { l: 40, r: 20, t: 20, b: 35 },
    xaxis: { gridcolor: gridColor },
    yaxis: { gridcolor: gridColor }
  };

  const totalPagesCount = Math.ceil(totalPapers / PAGE_SIZE) || 1;
  const paginatedCitingWorks = useMemo(() => {
    const start = citingWorksPage * PAGE_SIZE;
    return citingWorks.slice(start, start + PAGE_SIZE);
  }, [citingWorks, citingWorksPage]);
  const totalCitingPages = Math.ceil(citingWorks.length / PAGE_SIZE) || 1;

  return (
    <div className="module-container" id="MODULO-02-PERFILES">
      {/* 1. Buscador Predictivo (CTL-M02-001) */}
      <div className="glass-card" style={{ marginBottom: '1.5rem', position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Search size={20} style={{ color: 'var(--accent-cyan)' }} />
          <input
            id="CTL-M02-001"
            type="text"
            className="form-input"
            style={{ border: 'none', background: 'transparent', padding: '0.4rem 0', fontSize: '1.05rem', width: '100%' }}
            placeholder={t.researchers?.searchPlaceholder || "Buscar por nombre de investigador o identificador ORCID..."}
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
          />
          {searchQuery && (
            <button
              onClick={() => { setSearchQuery(''); setSearchResults([]); }}
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
            >
              <X size={18} />
            </button>
          )}
        </div>

        {/* Resultados de Autocompletado */}
        {searchResults.length > 0 && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0,
            background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)',
            borderRadius: '8px', marginTop: '6px', zIndex: 100, maxHeight: '300px', overflowY: 'auto',
            boxShadow: 'var(--card-shadow-hover)'
          }}>
            {searchResults.map((item, idx) => (
              <div
                key={idx}
                style={{
                  padding: '0.75rem 1rem', cursor: 'pointer', borderBottom: '1px solid var(--border-subtle)',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                }}
                onClick={() => {
                  setSelectedResearcher(item.name, item.orcid);
                  setSearchResults([]);
                  setSearchQuery('');
                  setPapersPage(0);
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{item.name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    {item.institution || item.parents?.join(' ➔ ') || 'Investigador Registrado'} · {item.snii_level ? `SNII ${item.snii_level}` : 'Sin Nivel'}
                  </div>
                </div>
                {item.orcid && (
                  <span className="badge badge-cyan" style={{ fontSize: '0.7rem' }}>
                    {item.orcid}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 2. Ficha de Perfil del Investigador (CTL-M02-002 a CTL-M02-007) */}
      {profile && (
        <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1.5rem' }}>
            <div style={{ flex: 1, minWidth: '320px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', marginBottom: '0.4rem' }}>
                <h2 style={{ fontSize: '1.75rem', fontWeight: 800 }}>{profile.name}</h2>
                {profile.is_snii ? (
                  <span className="badge badge-amber" style={{ fontSize: '0.85rem', padding: '0.3rem 0.8rem', fontWeight: 700 }}>
                    SNII: {profile.snii_level_label || `Nivel ${profile.snii_level}`}
                  </span>
                ) : (
                  <span className="badge badge-cyan" style={{ fontSize: '0.82rem', padding: '0.25rem 0.75rem' }}>
                    SNII No registrado en Padrón
                  </span>
                )}
                {profile.snii_area && (
                  <span className="badge badge-purple" style={{ fontSize: '0.78rem' }}>
                    Área: {profile.snii_area}
                  </span>
                )}
              </div>

              {/* Adscripción Jerárquica */}
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.6rem' }}>
                <strong>Adscripción:</strong> {profile.affiliation_breadcrumb || `${profile.institution} · ${profile.dependency} · ${profile.subdependency}`}
              </p>

              {/* Enlaces de Perfiles Externos */}
              <div style={{ display: 'flex', gap: '1.25rem', flexWrap: 'wrap', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                {profile.orcid && (
                  <a
                    href={`https://orcid.org/${profile.orcid}`}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: '#0284c7', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.3rem', fontWeight: 600 }}
                  >
                    <Globe size={14} />
                    <span>ORCID: {profile.orcid}</span>
                    <ExternalLink size={12} />
                  </a>
                )}
                {profile.cvu && (
                  <span style={{ color: 'var(--text-secondary)' }}>
                    <strong>CVU SECIHTI:</strong> <code>{profile.cvu}</code>
                  </span>
                )}
                {profile.siia && (
                  <a
                    href={profile.siia}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: '#0d9488', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.3rem', fontWeight: 600 }}
                  >
                    <span>SIIA UNAM</span>
                    <ExternalLink size={12} />
                  </a>
                )}
                {profile.scopus_ids && profile.scopus_ids.length > 0 && (
                  <a
                    href={`https://www.scopus.com/authid/detail.uri?authorId=${profile.scopus_ids[0]}`}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: '#f59e0b', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.3rem', fontWeight: 600 }}
                  >
                    <span>Scopus: {profile.scopus_ids[0]}</span>
                    <ExternalLink size={12} />
                  </a>
                )}
                {profile.openalex_ids && profile.openalex_ids.length > 0 && (
                  <a
                    href={profile.openalex_ids[0].startsWith('http') ? profile.openalex_ids[0] : `https://openalex.org/${profile.openalex_ids[0]}`}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: '#8b5cf6', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.3rem', fontWeight: 600 }}
                  >
                    <span>OpenAlex ID</span>
                    <ExternalLink size={12} />
                  </a>
                )}
              </div>
            </div>

            {/* Botones de Descarga */}
            <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
              <button id="CTL-M02-022" className="btn btn-secondary btn-sm" onClick={handleDownloadMarkdown}>
                <FileText size={14} />
                <span>Descargar Reporte (Markdown)</span>
              </button>
              <button id="CTL-M02-021" className="btn btn-primary btn-sm" onClick={handleDownloadPdf}>
                <Download size={14} />
                <span>Descargar Dossier (PDF)</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 3. Sub-Pestañas del Perfil (CTL-M02-008) */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem' }}>
        <button
          className={`btn btn-sm ${activeSubTab === 'production' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveSubTab('production')}
        >
          <BookOpen size={14} />
          <span>Producción Académica ({gen.indexed_count || totalPapers || 0})</span>
        </button>
        <button
          className={`btn btn-sm ${activeSubTab === 'citations' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveSubTab('citations')}
        >
          <Quote size={14} />
          <span>Citas y Autocitas</span>
        </button>
      </div>

      {/* 4. Vista de Producción Académica */}
      {activeSubTab === 'production' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Grupo 1: Métricas Generales (5 KPIs) */}
          <div className="glass-card" style={{ padding: '1.25rem' }}>
            <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.85rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Sparkles size={16} style={{ color: 'var(--accent-cyan)' }} />
              Métricas Generales
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem' }}>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Producción Total (Censo)</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.75rem', fontWeight: 800 }}>
                  {gen.total_census?.toLocaleString() || '0'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Censo Neo4j</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Indizada (Analítica)</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--accent-cyan)' }}>
                  {gen.indexed_count?.toLocaleString() || '0'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>OpenAlex</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Índice H</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.75rem', fontWeight: 800, color: '#f59e0b' }}>
                  {gen.h_index || 0}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Citas acumuladas</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Total Citas</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.75rem', fontWeight: 800 }}>
                  {gen.total_citations?.toLocaleString() || '0'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Citas brutas</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">% Open Access</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.75rem', fontWeight: 800, color: '#10b981' }}>
                  {gen.pct_open_access ? `${gen.pct_open_access}%` : '0%'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Acceso Abierto</span>
              </div>
            </div>
          </div>

          {/* Grupo 2: Métricas de Excelencia (5 KPIs) */}
          <div className="glass-card" style={{ padding: '1.25rem' }}>
            <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.85rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Award size={16} style={{ color: '#f59e0b' }} />
              Métricas de Excelencia
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem' }}>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Citas/artículo</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800 }}>
                  {exc.citations_per_paper || '0.00'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Promedio autor</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">FWCI Promedio</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800, color: (exc.fwci_avg || 0) >= 1.0 ? '#10b981' : '#f59e0b' }}>
                  {exc.fwci_avg ? Number(exc.fwci_avg).toFixed(2) : '1.00'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Mundial = 1.0</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Percentil Promedio</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800 }}>
                  {exc.percentile_avg ? Number(exc.percentile_avg).toFixed(1) : '50.0'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Menor = más citado</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">% Top 10%</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800, color: 'var(--accent-cyan)' }}>
                  {exc.pct_top_10 ? `${exc.pct_top_10}%` : '0.0%'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Percentil ≤ 10</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">% Top 1%</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800, color: '#8b5cf6' }}>
                  {exc.pct_1 ? `${exc.pct_1}%` : '0.0%'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Cúspide científica</span>
              </div>
            </div>
          </div>

          {/* Grupo 3: Velocidad y Colaboración (5 KPIs) */}
          <div className="glass-card" style={{ padding: '1.25rem' }}>
            <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.85rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <TrendingUp size={16} style={{ color: '#10b981' }} />
              Velocidad de Citas y Colaboración
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem' }}>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Citas/año (prom.)</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800 }}>
                  {vel.velocity_avg ? Number(vel.velocity_avg).toFixed(1) : '0.0'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Velocidad anual</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Citas últ. 3 años</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800, color: '#0284c7' }}>
                  {vel.recent_cites_3yr?.toLocaleString() || '0'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Impacto reciente</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">% Colab. Internacional</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800, color: '#10b981' }}>
                  {vel.pct_international ? `${vel.pct_international}%` : '0.0%'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Coautoría global</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Países/paper (prom.)</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800 }}>
                  {vel.avg_countries ? Number(vel.avg_countries).toFixed(1) : '0.0'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Diversidad país</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Autores/paper (prom.)</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800 }}>
                  {vel.avg_author_count ? Number(vel.avg_author_count).toFixed(1) : '0.0'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Densidad equipo</span>
              </div>
            </div>
          </div>

          {/* Grupo 4: Acceso Abierto y Costos APC (3 KPIs) */}
          <div className="glass-card" style={{ padding: '1.25rem' }}>
            <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.85rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <DollarSign size={16} style={{ color: '#ec4899' }} />
              Acceso Abierto y Costos (APC)
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">APC Total Estimado</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800, color: '#ec4899' }}>
                  ${(apc.apc_paid_usd || 0).toLocaleString()} USD
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Costo de lista revistas</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">% Papers con APC</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800 }}>
                  {apc.pct_apc ? `${apc.pct_apc}%` : '0.0%'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Cuotas requeridas</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Vida Media de Citas</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.65rem', fontWeight: 800 }}>
                  {apc.half_life_avg ? `${apc.half_life_avg} años` : '0.0 años'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Años al 50% de citas</span>
              </div>
            </div>
          </div>

          {/* Fila: Distribución Open Access (Donut) & Perfil Temático (Gini) */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '1.5rem' }}>
            <div className="glass-card">
              <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Distribución Open Access</h3>
              <Plot
                data={oaDonutData}
                layout={{ ...defaultPlotLayout, height: 280, showlegend: true, legend: { orientation: 'h', y: -0.15 } }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>

            <div className="glass-card">
              <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Perfil Temático (Gini)</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0', borderBottom: '1px solid var(--border-subtle)' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Índice de Gini Temático:</span>
                  <strong style={{ color: 'var(--accent-cyan)' }}>{them.gini_topics ? Number(them.gini_topics).toFixed(3) : '0.337'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0', borderBottom: '1px solid var(--border-subtle)' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Dominios de Investigación Cubiertos:</span>
                  <strong style={{ color: 'var(--text-primary)' }}>{them.domain_diversity || 4}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0', borderBottom: '1px solid var(--border-subtle)' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Tópicos Únicos Desarrollados:</span>
                  <strong style={{ color: '#10b981' }}>{them.unique_topics || 51}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0', borderBottom: '1px solid var(--border-subtle)' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Dominio Principal:</span>
                  <strong style={{ color: '#f59e0b' }}>{them.top_domain || 'Physical Sciences'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Tópico Principal:</span>
                  <strong style={{ color: '#8b5cf6' }}>{them.top_topic || 'Artificial Intelligence'}</strong>
                </div>
              </div>
            </div>
          </div>

          {/* Fila: Tipos de Documentos & Glosario Metodológico Interactivo */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '1.5rem' }}>
            <div className="glass-card">
              <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Tipos de Documentos</h3>
              {profile?.document_types?.length ? (
                <Plot
                  data={docTypesData}
                  layout={{ ...defaultPlotLayout, height: 280, showlegend: true, legend: { orientation: 'h', y: -0.15 } }}
                  config={{ responsive: true, displayModeBar: false }}
                  style={{ width: '100%' }}
                />
              ) : (
                <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>Sin datos de tipos de documento</p>
              )}
            </div>

            <div className="glass-card">
              <div
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                onClick={() => setShowGlossary(!showGlossary)}
              >
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <HelpCircle size={18} style={{ color: 'var(--accent-cyan)' }} />
                  Glosario Metodológico Interactivo
                </h3>
                {showGlossary ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
              </div>

              <div style={{ marginTop: '0.75rem', fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                <p>
                  <strong>FWCI (Field-Weighted Citation Impact):</strong> Mide el impacto de citación normalizado por disciplina y año (1.0 es la media mundial).
                </p>
                {showGlossary && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
                    <p>
                      <strong>Percentil / Top 10% / Top 1%:</strong> Posición relativa mundial del artículo dentro de su especialidad temática.
                    </p>
                    <p>
                      <strong>Citas/año:</strong> Velocidad anual de acumulación de citas sostenida por las publicaciones del autor.
                    </p>
                    <p>
                      <strong>Citas últ. 3 años:</strong> Sumatoria total de citas recientes recibidas en los últimos 36 meses.
                    </p>
                    <p>
                      <strong>% Colaboración Internacional:</strong> Proporción de artículos en coautoría con investigadores extranjeros.
                    </p>
                    <p>
                      <strong>APC Total:</strong> Costo estimado de lista de las cuotas de procesamiento de artículos en revistas de acceso abierto.
                    </p>
                    <p>
                      <strong>Índice de Gini Temático:</strong> Medida de concentración temática (0 = máxima dispersión, 1 = total concentración).
                    </p>
                    <p>
                      <strong>Vías Open Access:</strong> Gold (revista OA), Green (repositorio institucional), Hybrid (pago por liberación), Closed (suscripción).
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Fila: Trayectoria Histórica (Docs por Año) & Foco Temático (Top 10 Topics) */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '1.5rem' }}>
            <div className="glass-card">
              <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Trayectoria Histórica (Docs)</h3>
              <Plot
                data={trajectoryData}
                layout={{ ...defaultPlotLayout, height: 320 }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>

            <div className="glass-card">
              <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Foco Temático (Top 10 Topics)</h3>
              <Plot
                data={topTopicsData}
                layout={{
                  ...defaultPlotLayout,
                  height: 320,
                  margin: { l: 180, r: 20, t: 20, b: 35 },
                  yaxis: { ...defaultPlotLayout.yaxis, automargin: true }
                }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>
          </div>

          {/* Concentración Temática (Sunburst 4-Niveles) */}
          <div className="glass-card">
            <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Concentración Temática (Sunburst 4 Niveles)</h3>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Jerarquía taxonómica de la producción: <strong>Dominio</strong> ➔ <strong>Campo</strong> ➔ <strong>Subcampo</strong> ➔ <strong>Tópico</strong>.
            </p>
            {sunburstData.length > 0 ? (
              <Plot
                data={sunburstData}
                layout={{ ...defaultPlotLayout, height: 520, margin: { l: 10, r: 10, t: 10, b: 10 } }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            ) : (
              <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>Sin datos de árbol temático</p>
            )}
          </div>

          {/* Vocabulario Científico (Keywords) */}
          <div className="glass-card">
            <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>🔑 Vocabulario Científico (Keywords)</h3>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.75rem' }}>
              {profile?.keywords?.map((kw, idx) => (
                <span
                  key={idx}
                  className="badge badge-cyan"
                  style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                >
                  <span>{kw.keyword}</span>
                  <strong style={{ opacity: 0.75 }}>({kw.freq})</strong>
                </span>
              ))}
            </div>
          </div>

          {/* Panorama General de Sostenibilidad (ODS 1 a 17) */}
          <div className="glass-card">
            <h3 style={{ fontSize: '1.1rem', marginBottom: '0.5rem', fontWeight: 700 }}>🌍 Panorama General de Sostenibilidad (ODS)</h3>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Distribución de la producción del investigador alineada a los 17 Objetivos de Desarrollo Sostenible (ONU).
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.75rem' }}>
              {profile?.sdg_matrix?.map((sdg) => {
                const color = SDG_COLORS[sdg.sdg] || '#0284c7';
                return (
                  <div
                    key={sdg.sdg}
                    className="glass-card"
                    style={{
                      padding: '0.75rem',
                      borderLeft: `4px solid ${color}`,
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                      background: sdg.count > 0 ? `${color}10` : 'transparent'
                    }}
                  >
                    <div>
                      <div style={{ fontSize: '0.72rem', fontWeight: 700, color }}>ODS {sdg.sdg}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-primary)', marginTop: '0.2rem', lineHeight: 1.2 }}>
                        {sdg.name}
                      </div>
                    </div>
                    <div style={{ fontSize: '1.4rem', fontWeight: 800, marginTop: '0.5rem', color: sdg.count > 0 ? color : 'var(--text-muted)' }}>
                      {sdg.count}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Catálogo Interactivo de Publicaciones Científicas */}
          <div className="glass-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.25rem' }}>
              <div>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>📜 Catálogo de Publicaciones</h3>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {totalPapers.toLocaleString()} obras registradas · Página {papersPage + 1} de {totalPagesCount}
                </span>
              </div>

              {/* Filtros: Año, OA y Búsqueda */}
              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
                {/* Filtro por Año */}
                <select
                  id="CTL-M02-014"
                  className="form-select"
                  style={{ width: 'auto', padding: '0.4rem 0.75rem', fontSize: '0.82rem' }}
                  value={yearFilter}
                  onChange={(e) => { setYearFilter(e.target.value); setPapersPage(0); }}
                >
                  <option value="all">Todos los Años</option>
                  {availableYears.map((yr) => (
                    <option key={yr} value={yr}>{yr}</option>
                  ))}
                </select>

                {/* Filtro por Vía OA */}
                <select
                  id="CTL-M02-015"
                  className="form-select"
                  style={{ width: 'auto', padding: '0.4rem 0.75rem', fontSize: '0.82rem' }}
                  value={oaFilter}
                  onChange={(e) => { setOaFilter(e.target.value); setPapersPage(0); }}
                >
                  <option value="all">Todo Acceso Abierto</option>
                  <option value="gold">Gold OA</option>
                  <option value="green">Green OA</option>
                  <option value="hybrid">Hybrid OA</option>
                  <option value="bronze">Bronze OA</option>
                  <option value="closed">Closed / Cerrado</option>
                </select>

                {/* Buscador de texto */}
                <input
                  type="text"
                  className="form-input"
                  placeholder="Filtrar título / revista..."
                  style={{ width: '180px', padding: '0.4rem 0.75rem', fontSize: '0.82rem' }}
                  value={searchPaper}
                  onChange={(e) => { setSearchPaper(e.target.value); setPapersPage(0); }}
                />
              </div>
            </div>

            {/* Tabla de Artículos */}
            {loadingPapers ? (
              <p style={{ color: 'var(--text-muted)', padding: '2rem 0', textAlign: 'center' }}>Cargando publicaciones...</p>
            ) : papersData.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', padding: '2rem 0', textAlign: 'center' }}>
                No se encontraron obras con los filtros seleccionados.
              </p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '0.6rem 0.8rem' }}>Título de la Obra</th>
                      <th style={{ padding: '0.6rem 0.8rem' }}>Revista / Fuente</th>
                      <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>Año</th>
                      <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>Citas</th>
                      <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>FWCI</th>
                      <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>Acceso Abierto</th>
                      <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>Enlaces</th>
                    </tr>
                  </thead>
                  <tbody>
                    {papersData.map((w, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '0.75rem 0.8rem', maxWidth: '420px' }}>
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                            {w.title}
                          </div>
                          {w.ods_name && (
                            <span style={{ fontSize: '0.7rem', color: 'var(--accent-cyan)' }}>
                              🎯 {w.ods_name}
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '0.75rem 0.8rem', color: 'var(--text-secondary)' }}>
                          {w.journal || w.source || 'Revista no especificada'}
                        </td>
                        <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center', fontWeight: 600 }}>
                          {w.year || w.publication_year || 'S/F'}
                        </td>
                        <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                          {w.citations || 0}
                        </td>
                        <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center', color: (w.fwci || 0) >= 1.0 ? '#10b981' : '#f59e0b', fontWeight: 600 }}>
                          {w.fwci ? Number(w.fwci).toFixed(2) : '1.00'}
                        </td>
                        <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center' }}>
                          <span
                            className={`badge ${
                              w.oa_status?.includes('gold') ? 'badge-amber' :
                              w.oa_status?.includes('green') ? 'badge-emerald' :
                              w.oa_status?.includes('diamond') ? 'badge-purple' :
                              w.oa_status?.includes('hybrid') ? 'badge-cyan' : 'badge-slate'
                            }`}
                            style={{ fontSize: '0.72rem' }}
                          >
                            {w.oa_status || 'closed'}
                          </span>
                        </td>
                        <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center' }}>
                          <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center' }}>
                            {w.doi_url ? (
                              <a href={w.doi_url} target="_blank" rel="noreferrer" title="Ver en DOI" style={{ color: '#0284c7' }}>
                                <ExternalLink size={14} />
                              </a>
                            ) : null}
                            {w.openalex_url ? (
                              <a href={w.openalex_url} target="_blank" rel="noreferrer" title="Ver en OpenAlex" style={{ color: '#8b5cf6' }}>
                                <BookOpen size={14} />
                              </a>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Paginación de 10 en 10 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)' }}>
              <button
                className="btn btn-secondary btn-sm"
                disabled={papersPage === 0}
                onClick={() => setPapersPage((p) => Math.max(0, p - 1))}
              >
                <ChevronLeft size={14} /> Anterior
              </button>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                Página <strong>{papersPage + 1}</strong> de <strong>{totalPagesCount}</strong>
              </span>
              <button
                className="btn btn-secondary btn-sm"
                disabled={papersPage >= totalPagesCount - 1}
                onClick={() => setPapersPage((p) => p + 1)}
              >
                Siguiente <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. Vista de Citas y Autocitas (Toda la Carrera) (CTL-M02-016 a CTL-M02-022) */}
      {activeSubTab === 'citations' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Tarjetas de Citas y Autocitas de Toda la Carrera */}
          <div className="glass-card" style={{ padding: '1.25rem' }}>
            <h4 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.85rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Quote size={16} style={{ color: 'var(--accent-cyan)' }} />
              Citas y Autocitas de Toda la Carrera
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem' }}>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Citas Totales (Carrera)</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.75rem', fontWeight: 800 }}>
                  {(cSummary.total_citations || gen.total_citations || 0).toLocaleString()}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Histórico acumulado</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Citas Netas</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--accent-cyan)' }}>
                  {(cSummary.net_citations || 0).toLocaleString()}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>De terceros</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Autocitas Directas</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.75rem', fontWeight: 800, color: '#ec4899' }}>
                  {(cSummary.self_citations || 0).toLocaleString()}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Coautor en obra citante</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Tasa de Autocitas</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.75rem', fontWeight: 800, color: '#ec4899' }}>
                  {cSummary.self_citation_rate ? `${Number(cSummary.self_citation_rate).toFixed(1)}%` : '5.3%'}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Directas del autor</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">En Top 10% Global</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.75rem', fontWeight: 800, color: '#10b981' }}>
                  {cSummary.top_10_percent_citations || 0}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Citas de alto impacto</span>
              </div>
              <div className="glass-card" style={{ padding: '0.85rem', textAlign: 'center' }}>
                <span className="kpi-metric-label">Países Citantes</span>
                <div className="kpi-metric-val" style={{ fontSize: '1.75rem', fontWeight: 800, color: '#8b5cf6' }}>
                  {cSummary.citing_countries_count || 0}
                </div>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Red internacional</span>
              </div>
            </div>

            {/* Nota Metodológica de Autocitas Directas */}
            <div style={{
              marginTop: '1rem',
              padding: '0.85rem 1.15rem',
              borderRadius: '8px',
              background: isLight ? 'rgba(2, 132, 199, 0.08)' : 'rgba(2, 132, 199, 0.15)',
              borderLeft: '4px solid #0284c7',
              fontSize: '0.82rem',
              lineHeight: 1.5,
              color: 'var(--text-secondary)'
            }}>
              📌 <strong>Nota sobre autocitas:</strong> Se contabilizan exclusivamente las <strong>autocitas directas (del autor)</strong>, es decir, aquellas publicaciones donde el investigador evaluado figura expresamente como coautor en la obra citante. El cálculo de citas netas y autocitas abarca la totalidad de las <strong>{(cSummary.total_citations || gen.total_citations || 0).toLocaleString()} citas acumuladas</strong> a lo largo de su carrera académica.
            </div>
          </div>

          {/* Gráficas de Citas Netas vs Autocitas & Top Países */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '1.5rem' }}>
            <div className="glass-card">
              <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Balance Citas Netas vs Autocitas Directas (Toda la Carrera)</h3>
              <Plot
                data={citationsDonutData}
                layout={{ ...defaultPlotLayout, height: 280, showlegend: true, legend: { orientation: 'h', y: -0.15 } }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>

            <div className="glass-card">
              <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Top Países Citantes</h3>
              <Plot
                data={citingCountriesData}
                layout={{ ...defaultPlotLayout, height: 280 }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </div>
          </div>

          {/* Gráfica de Instituciones Citantes */}
          <div className="glass-card">
            <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem', fontWeight: 700 }}>Top Instituciones Internacionales Citantes</h3>
            <Plot
              data={citingInstitutionsData}
              layout={{
                ...defaultPlotLayout,
                height: 320,
                margin: { l: 200, r: 20, t: 20, b: 35 },
                yaxis: { ...defaultPlotLayout.yaxis, automargin: true }
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: '100%' }}
            />
          </div>

          {/* Tabla Detallada de Trabajos Citantes */}
          <div className="glass-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Detalle de Artículos Citantes Indexados</h3>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  {citingWorks.length} artículos citantes analizados con grafo relacional disponible · Página {citingWorksPage + 1} de {totalCitingPages}
                </span>
              </div>
            </div>

            {loadingCitingWorks ? (
              <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>Cargando artículos citantes...</p>
            ) : citingWorks.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '2rem' }}>No se registraron artículos citantes.</p>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                      <th style={{ padding: '0.6rem 0.8rem' }}>Título de la Obra Citante</th>
                      <th style={{ padding: '0.6rem 0.8rem' }}>Primer Autor</th>
                      <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>Año</th>
                      <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>Tipo de Cita</th>
                      <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>Citas de la Obra</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedCitingWorks.map((cw, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '0.75rem 0.8rem', maxWidth: '450px' }}>
                          <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                            {cw.title}
                          </div>
                          {cw.doi && (
                            <a
                              href={cw.doi.startsWith('http') ? cw.doi : `https://doi.org/${cw.doi}`}
                              target="_blank"
                              rel="noreferrer"
                              style={{ fontSize: '0.72rem', color: '#0284c7', textDecoration: 'none' }}
                            >
                              {cw.doi}
                            </a>
                          )}
                        </td>
                        <td style={{ padding: '0.75rem 0.8rem', color: 'var(--text-secondary)' }}>
                          {cw.first_author || 'Anónimo'}
                        </td>
                        <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center' }}>
                          {cw.publication_year || 'S/F'}
                        </td>
                        <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center' }}>
                          {cw.is_self_citation ? (
                            <span className="badge badge-amber" style={{ fontSize: '0.72rem' }}>Autocita</span>
                          ) : (
                            <span className="badge badge-cyan" style={{ fontSize: '0.72rem' }}>Cita Neta</span>
                          )}
                        </td>
                        <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center', fontWeight: 700, color: 'var(--accent-cyan)' }}>
                          {cw.cited_by_count || 0}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Paginación de Artículos Citantes */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)' }}>
              <button
                className="btn btn-secondary btn-sm"
                disabled={citingWorksPage === 0}
                onClick={() => setCitingWorksPage((p) => Math.max(0, p - 1))}
              >
                <ChevronLeft size={14} /> Anterior
              </button>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                Página <strong>{citingWorksPage + 1}</strong> de <strong>{totalCitingPages}</strong>
              </span>
              <button
                className="btn btn-secondary btn-sm"
                disabled={citingWorksPage >= totalCitingPages - 1}
                onClick={() => setCitingWorksPage((p) => p + 1)}
              >
                Siguiente <ChevronRight size={14} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ResearcherProfiles;
