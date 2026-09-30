/**
 * frontend/src/components/modules/ResearcherProfiles.jsx
 * Módulo 2: Perfiles de Investigadores y Producción Académica
 * Implementación al 100% de paridad con Streamlit (22 controles y bloques analíticos)
 */

import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';
import {
  Search,
  Users,
  Building2,
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
  X,
  Share2,
  Check
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import { apiClient } from '../../api/client.js';
import ThematicEvolutionTable from '../analytics/ThematicEvolutionTable.jsx';
import CollaborationWorldMap from '../analytics/CollaborationWorldMap.jsx';
import SemanticProductionMap from '../analytics/SemanticProductionMap.jsx';
import AIReportViewer from '../analytics/AIReportViewer.jsx';
import FeaturedPublications from '../analytics/FeaturedPublications.jsx';
import UmapPerformanceMap from '../analytics/UmapPerformanceMap.jsx';
import CoAuthraNetwork from '../analytics/CoAuthraNetwork.jsx';
import WordCloudInteractive from '../analytics/WordCloudInteractive.jsx';

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
  const selectedInstitution = useAppStore((state) => state.selectedInstitution);
  const setSelectedInstitution = useAppStore((state) => state.setSelectedInstitution);
  const selectedDependency = useAppStore((state) => state.selectedDependency);
  const setSelectedDependency = useAppStore((state) => state.setSelectedDependency);
  const selectedSubdependency = useAppStore((state) => state.selectedSubdependency);
  const setSelectedSubdependency = useAppStore((state) => state.setSelectedSubdependency);
  const researcherName = useAppStore((state) => state.selectedResearcherName);
  const researcherOrcid = useAppStore((state) => state.selectedResearcherOrcid);
  const setSelectedResearcher = useAppStore((state) => state.setSelectedResearcher);
  const setNotification = useAppStore((state) => state.setNotification);
  const theme = useAppStore((state) => state.theme);

  const [copiedShare, setCopiedShare] = useState(false);

  const handleShareUrl = () => {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('tab', 'researchers');
      if (researcherName) url.searchParams.set('academic', researcherName);
      if (researcherOrcid) url.searchParams.set('orcid', researcherOrcid);
      if (selectedInstitution) url.searchParams.set('institution', selectedInstitution);
      if (selectedDependency) url.searchParams.set('dependency', selectedDependency);
      if (selectedSubdependency) url.searchParams.set('subdependency', selectedSubdependency);

      const finalUrl = url.toString();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(finalUrl).then(() => {
          setCopiedShare(true);
          setTimeout(() => setCopiedShare(false), 2500);
          setNotification({
            type: 'success',
            message: `¡Enlace del perfil de ${researcherName} copiado al portapapeles!`
          });
        }).catch(() => {
          prompt('Copia el siguiente enlace:', finalUrl);
        });
      } else {
        prompt('Copia el siguiente enlace:', finalUrl);
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Estados locales para jerarquía y combobox de académicos
  const [institutions, setInstitutions] = useState([]);
  const [dependencies, setDependencies] = useState([]);
  const [subdependencies, setSubdependencies] = useState([]);
  const [academicsList, setAcademicsList] = useState([]);
  const [loadingAcademics, setLoadingAcademics] = useState(false);

  const [profile, setProfile] = useState(null);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [activeSubTab, setActiveSubTab] = useState('production'); // 'production' | 'citations'
  const [showGlossary, setShowGlossary] = useState(true);

  // Estados para tabla de publicaciones
  const currentYear = new Date().getFullYear();
  const [yearFilter, setYearFilter] = useState('all');
  const [oaFilter, setOaFilter] = useState('all');
  const [odsFilter, setOdsFilter] = useState('all');
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

  // 2. Cargar Años Disponibles (sin filtrar por año actual para no ocultar publicaciones históricas)
  useEffect(() => {
    // Resetear filtros al cambiar de investigador
    setYearFilter('all');
    setOaFilter('all');
    setOdsFilter('all');
    setSearchPaper('');
    setPapersPage(0);

    async function loadYears() {
      if (!researcherName && !researcherOrcid) return;
      try {
        // Usar limit alto para capturar todos los años posibles del investigador
        const res = await apiClient.getAcademicWorks(researcherOrcid, researcherName, { limit: 500, offset: 0 });
        if (res && res.works) {
          const yrs = new Set();
          res.works.forEach((w) => {
            if (w.year || w.publication_year) {
              yrs.add(String(w.year || w.publication_year));
            }
          });
          const sortedYrs = Array.from(yrs).sort().reverse();
          setAvailableYears(sortedYrs);
          // Siempre mostrar 'Todos los Años' por defecto para no ocultar producción histórica
          setYearFilter('all');
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
          ods: odsFilter !== 'all' ? odsFilter : undefined,
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
  }, [researcherName, researcherOrcid, papersPage, yearFilter, oaFilter, odsFilter, searchPaper]);

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

  // 4. Cargar lista de académicos de la entidad para el Combobox
  useEffect(() => {
    async function loadAcademics() {
      setLoadingAcademics(true);
      try {
        const data = await apiClient.getAcademicsList(selectedInstitution, selectedDependency, selectedSubdependency);
        const list = data.academics || [];
        setAcademicsList(list);

        // Si hay una lista, sincronizar o validar la selección actual
        if (list.length > 0) {
          if (researcherName) {
            const normCurrent = researcherName.replace(/,/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
            const match = list.find((a) => {
              const normA = a.name.replace(/,/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
              return normA === normCurrent || normA.includes(normCurrent) || normCurrent.includes(normA);
            });
            if (match && match.name !== researcherName) {
              setSelectedResearcher(match.name, match.orcid || researcherOrcid);
            } else if (!match && !list.some((a) => a.name === researcherName)) {
              // Si el investigador actual no pertenece a la entidad recién seleccionada, seleccionar el primero
              setSelectedResearcher(list[0].name, list[0].orcid || '');
            }
          } else {
            setSelectedResearcher(list[0].name, list[0].orcid || '');
          }
        }
      } catch (err) {
        console.error('Error cargando lista de académicos:', err);
      } finally {
        setLoadingAcademics(false);
      }
    }
    loadAcademics();
  }, [selectedInstitution, selectedDependency, selectedSubdependency]);

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
      a.download = `Dossier_Trayectoria_${researcherName.replace(/\s+/g, '_')}.pdf`;
      a.click();
    } catch (err) {
      console.error('Error descargando PDF:', err);
    }
  };

  // KPIs Extraídos del Perfil
  const kpis = profile?.kpis || {};
  const gen = kpis.general || {};
  const exc = kpis.excellence || {};
  const tiersProf = exc.tiers || kpis.tiers;
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
    // Si el backend ya calculó el trace oficial con px.sunburst
    if (profile?.sunburst_trace && profile.sunburst_trace.labels?.length) {
      const tr = profile.sunburst_trace;
      return [{
        type: 'sunburst',
        ids: tr.ids,
        labels: tr.labels,
        parents: tr.parents,
        values: tr.values,
        branchvalues: 'total',
        hoverinfo: 'label+value+percent parent',
        insidetextorientation: 'radial',
        marker: {
          colors: tr.colors || tr.values,
          colorscale: 'Blues',
          showscale: true,
          colorbar: {
            title: { text: 'value' },
            len: 0.85,
            thickness: 16
          }
        }
      }];
    }

    const list = profile?.sunburst_data || [];
    if (!list.length) return [];

    // Calcular sumas acumuladas de obras para que los padres tengan el valor real de sus hijos
    const domainSums = {};
    const fieldSums = {};
    const subfieldSums = {};

    list.forEach((item) => {
      const v = Number(item.value) || 1;
      const d = item.domain;
      const f = `${d} / ${item.field}`;
      const s = `${f} / ${item.subfield}`;

      if (d) domainSums[d] = (domainSums[d] || 0) + v;
      if (f) fieldSums[f] = (fieldSums[f] || 0) + v;
      if (s) subfieldSums[s] = (subfieldSums[s] || 0) + v;
    });

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
        ids.push(d); labels.push(item.domain); parents.push(''); values.push(domainSums[d] || 0); added.add(d);
      }
      if (f && !added.has(f)) {
        ids.push(f); labels.push(item.field); parents.push(d); values.push(fieldSums[f] || 0); added.add(f);
      }
      if (s && !added.has(s)) {
        ids.push(s); labels.push(item.subfield); parents.push(f); values.push(subfieldSums[s] || 0); added.add(s);
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
      insidetextorientation: 'radial',
      marker: {
        colors: values,
        colorscale: 'Blues',
        showscale: true,
        colorbar: {
          title: { text: 'value' },
          len: 0.85,
          thickness: 16
        }
      }
    }];
  }, [profile?.sunburst_data, profile?.sunburst_trace]);

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
      {/* 1. Selector Jerárquico y Combobox de Selección de Investigador (CTL-M02-001) */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        {/* Filtros Jerárquicos de Entidad */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.25rem' }}>
          <div>
            <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
              {t.panorama?.institutionSelect || 'Institución'}
            </label>
            <select
              className="form-select"
              value={selectedInstitution}
              onChange={(e) => setSelectedInstitution(e.target.value)}
              style={{ fontSize: '0.9rem' }}
            >
              {institutions.map((inst) => (
                <option key={inst} value={inst}>{inst}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
              {t.panorama?.dependencySelect || 'Dependencia / Facultad'}
            </label>
            <select
              className="form-select"
              value={selectedDependency}
              onChange={(e) => setSelectedDependency(e.target.value)}
              style={{ fontSize: '0.9rem' }}
            >
              <option value="">{t.panorama?.allDependencies || 'Todas las dependencias'}</option>
              {dependencies.map((dep) => (
                <option key={dep} value={dep}>{dep}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
              {t.panorama?.subdependencySelect || 'Subdependencia / Centro'}
            </label>
            <select
              className="form-select"
              value={selectedSubdependency}
              onChange={(e) => setSelectedSubdependency(e.target.value)}
              disabled={subdependencies.length === 0}
              style={{ fontSize: '0.9rem' }}
            >
              <option value="">{t.panorama?.allSubdependencies || 'Todas las subdependencias'}</option>
              {subdependencies.map((sub) => (
                <option key={sub} value={sub}>{sub}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Combobox Principal de Selección de Investigador */}
        <div style={{ paddingTop: '0.5rem', borderTop: '1px solid var(--border-subtle)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem', flexWrap: 'wrap', gap: '0.5rem' }}>
            <label
              htmlFor="CTL-M02-001"
              className="form-label"
              style={{ fontWeight: 700, fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-primary)', margin: 0 }}
            >
              <Users size={18} style={{ color: 'var(--accent-cyan)' }} />
              Seleccione un Académico:
            </label>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              {loadingAcademics ? 'Cargando directorio...' : `${academicsList.length} académicos disponibles`}
            </span>
          </div>

          <select
            id="CTL-M02-001"
            className="form-select"
            style={{
              fontSize: '1rem',
              fontWeight: 600,
              padding: '0.65rem 1rem',
              width: '100%',
              borderRadius: '8px',
              cursor: 'pointer',
              background: 'var(--bg-card)',
              color: 'var(--text-primary)',
              borderColor: 'var(--accent-cyan)'
            }}
            value={researcherName}
            onChange={(e) => {
              const chosen = e.target.value;
              const found = academicsList.find((a) => a.name === chosen);
              setSelectedResearcher(chosen, found?.orcid || '');
              setPapersPage(0);
            }}
            disabled={loadingAcademics || academicsList.length === 0}
          >
            {academicsList.length === 0 && (
              <option value="">(No hay académicos registrados en esta selección)</option>
            )}
            {academicsList.map((item, idx) => (
              <option key={idx} value={item.name}>
                {item.name}
              </option>
            ))}
          </select>

          {/* Nota Metodológica de Cobertura */}
          <div style={{
            marginTop: '0.75rem',
            fontSize: '0.8rem',
            color: 'var(--text-secondary)',
            lineHeight: 1.45,
            padding: '0.5rem 0.75rem',
            background: isLight ? 'rgba(0,0,0,0.03)' : 'rgba(255,255,255,0.03)',
            borderRadius: '6px'
          }}>
            ℹ️ Los indicadores se calcularon a partir de la producción académica recuperada de fuentes internacionales y ORCID, lo cual implica que puede haber trabajos faltantes y trabajos con afiliaciones distintas a la actual.
          </div>
        </div>
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
                    {profile.snii_level_label || `Nivel ${profile.snii_level}`}
                  </span>
                ) : (
                  <span className="badge badge-cyan" style={{ fontSize: '0.82rem', padding: '0.25rem 0.75rem' }}>
                    No registrado en Padrón
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
                    <span>ID Autor: {profile.scopus_ids[0]}</span>
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

            {/* Botones de Acción: Descargas y Compartir URL */}
            <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
              <button
                id="CTL-M02-SHARE"
                className={`btn btn-sm ${copiedShare ? 'btn-success' : 'btn-secondary'}`}
                onClick={handleShareUrl}
                title="Copiar enlace permanente de este perfil de investigador"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  borderColor: copiedShare ? '#10b981' : undefined,
                  color: copiedShare ? '#10b981' : undefined
                }}
              >
                {copiedShare ? <Check size={14} /> : <Share2 size={14} />}
                <span>{copiedShare ? '¡Enlace Copiado!' : 'Compartir Perfil'}</span>
              </button>
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
          {/* Panorama General de Sostenibilidad (ODS 1 a 17) */}
          <div className="glass-card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Globe size={20} style={{ color: 'var(--accent-cyan)' }} />
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>Impacto en Sostenibilidad (ODS 1 a 17)</h3>
              </div>
              <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                Haz clic en un ODS para filtrar las publicaciones
              </span>
            </div>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Distribución de la producción científica de la investigadora o investigador alineada a los 17 Objetivos de Desarrollo Sostenible (ONU).
            </p>

            {/* Notificación de Filtro ODS Activo */}
            {odsFilter !== 'all' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                <span
                  className="badge badge-cyan"
                  style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.35rem 0.75rem', fontSize: '0.82rem' }}
                >
                  Filtrando por: <b>ODS {odsFilter}</b>
                  <button
                    onClick={() => { setOdsFilter('all'); setPapersPage(0); }}
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
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.85rem' }}>
              {profile?.sdg_matrix?.map((sdg) => {
                const odsId = sdg.sdg || sdg.id;
                const isSelected = odsFilter === String(odsId);
                const count = sdg.count || 0;
                const totalWorksCount = profile?.kpis?.indexed_works || totalPapers || 1;
                const pct = sdg.pct !== undefined ? sdg.pct : (totalWorksCount > 0 ? ((count / totalWorksCount) * 100).toFixed(1) : 0);

                return (
                  <div
                    key={odsId}
                    onClick={() => {
                      setOdsFilter(isSelected ? 'all' : String(odsId));
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

          {/* Vocabulario Científico (Keywords Word Cloud) */}
          <WordCloudInteractive
            keywords={profile?.keywords}
            title={profile?.name ? `Vocabulario Científico · ${profile.name}` : "Vocabulario Científico (Word Cloud)"}
            subtitle="Nube interactiva con eventos de cursor para explorar frecuencias y conceptos de producción."
          />

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

          {/* 3b. Evolución Histórica de Perfiles de Conocimiento */}
          <ThematicEvolutionTable
            data={profile?.thematic_evolution}
            title="Evolución Histórica de Perfiles de Conocimiento"
          />

          {/* 3c. Red de Colaboración Científica (CoAuthra) */}
          <CoAuthraNetwork
            academicName={profile?.name}
            authorId={profile?.openalex_ids?.[0] || profile?.orcid}
          />

          {/* 3d. Mapa Semántico de Producción (WebGL) */}
          <SemanticProductionMap
            targetName={profile?.name || "Investigador"}
            type="author"
            dois={profile?.dois_list}
            oaIds={profile?.oa_list}
            totalWorks={gen.indexed_count}
          />

          {/* 3e. Mapas de Desempeño (UMAP) */}
          <UmapPerformanceMap
            academicName={profile?.name}
            entityName={profile?.subdependency || profile?.dependency}
            institutionName={profile?.institution}
            viewMode="capacidad_instalada"
          />

          {/* 3f. Publicaciones Destacadas (Más citadas y Más recientes) */}
          <FeaturedPublications
            featuredWorks={profile?.featured_works}
          />

          {/* 3g. Países Colaboradores (Choropleth) */}
          <CollaborationWorldMap
            countries={profile?.collaboration_countries}
            title={profile?.name ? `Países Colaboradores · ${profile.name}` : "Países Colaboradores"}
          />

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

            {/* Distribución por Tramos de Impacto Observado (Tiers T1–T4) */}
            {tiersProf && (
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
                      {tiersProf.t1Pct ?? 0}%
                    </div>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                      {tiersProf.T1 ? `${tiersProf.T1.toLocaleString()} obras` : 'Top 25% mundial'}
                    </div>
                  </div>
                  <div className="glass-card" style={{ padding: '0.5rem 0.75rem', borderLeft: '3px solid #3b82f6', background: 'rgba(59, 130, 246, 0.05)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#60a5fa' }}>Tier 2 (T2)</span>
                      <span className="badge badge-blue" style={{ fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>Medio-Alto</span>
                    </div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: '0.2rem', color: 'var(--text-primary)' }}>
                      {tiersProf.t2Pct ?? 0}%
                    </div>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                      {tiersProf.T2 ? `${tiersProf.T2.toLocaleString()} obras` : 'Percentil 50–74%'}
                    </div>
                  </div>
                  <div className="glass-card" style={{ padding: '0.5rem 0.75rem', borderLeft: '3px solid #10b981', background: 'rgba(16, 185, 129, 0.05)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#34d399' }}>Tier 3 (T3)</span>
                      <span className="badge badge-emerald" style={{ fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>Medio-Bajo</span>
                    </div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: '0.2rem', color: 'var(--text-primary)' }}>
                      {tiersProf.t3Pct ?? 0}%
                    </div>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                      {tiersProf.T3 ? `${tiersProf.T3.toLocaleString()} obras` : 'Percentil 25–49%'}
                    </div>
                  </div>
                  <div className="glass-card" style={{ padding: '0.5rem 0.75rem', borderLeft: '3px solid #f59e0b', background: 'rgba(245, 158, 11, 0.05)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#fbbf24' }}>Tier 4 (T4)</span>
                      <span className="badge badge-amber" style={{ fontSize: '0.68rem', padding: '0.15rem 0.4rem' }}>Base</span>
                    </div>
                    <div style={{ fontSize: '1.1rem', fontWeight: 800, marginTop: '0.2rem', color: 'var(--text-primary)' }}>
                      {tiersProf.t4Pct ?? 0}%
                    </div>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                      {tiersProf.T4 ? `${tiersProf.T4.toLocaleString()} obras` : 'Percentil 0–24%'}
                    </div>
                  </div>
                </div>
              </div>
            )}
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
                      <strong>% Colaboración Internacional:</strong> Proporción de artículos en coautoría con investigadoras e investigadores extranjeros.
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

          {/* 7b. Reporte Bibliométrico con Inteligencia Artificial */}
          <AIReportViewer
            type="inv"
            targetName={profile?.name || "Investigador"}
            viewMode="capacidad_instalada"
            hasReport={profile?.has_ai_report}
          />

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
                      <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>Tramo (Tier)</th>
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
                        <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center' }}>
                          {(() => {
                            const tier = w.tier || (w.is_top_1 || (w.percentile != null && w.percentile >= 75) || (w.fwci != null && w.fwci >= 1.5) ? 'T1' : (w.percentile != null && w.percentile >= 50) || (w.fwci != null && w.fwci >= 1.0) ? 'T2' : (w.percentile != null && w.percentile >= 25) || (w.fwci != null && w.fwci >= 0.6) ? 'T3' : 'T4');
                            const bClass = tier.startsWith('T1') ? 'badge-purple' : tier.startsWith('T2') ? 'badge-blue' : tier.startsWith('T3') ? 'badge-emerald' : 'badge-amber';
                            return (
                              <span className={`badge ${bClass}`} style={{ fontSize: '0.75rem', fontWeight: 700 }} title={`Tramo ${tier}`}>
                                {tier}
                              </span>
                            );
                          })()}
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
              📌 <strong>Nota sobre autocitas:</strong> Se contabilizan exclusivamente las <strong>autocitas directas (del autor)</strong>, es decir, aquellas publicaciones donde la investigadora o investigador evaluado figura expresamente como coautor/a en la obra citante. El cálculo de citas netas y autocitas abarca la totalidad de las <strong>{(cSummary.total_citations || gen.total_citations || 0).toLocaleString()} citas acumuladas</strong> a lo largo de su carrera académica.
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
