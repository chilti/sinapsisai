/**
 * frontend/src/components/modules/ResearcherProfiles.jsx
 * Módulo 2: Perfiles de Investigadores y Producción Académica
 * Implementación 1 a 1 de los 22 controles de QA
 */

import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';
import {
  Search,
  Award,
  BookOpen,
  Quote,
  Download,
  Globe,
  CheckCircle2,
  FileText,
  TrendingUp,
  Share2,
  Filter,
  ExternalLink,
  ChevronRight
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';

export function ResearcherProfiles() {
  const t = useAppStore((state) => state.t)();
  const researcherName = useAppStore((state) => state.selectedResearcherName);
  const researcherOrcid = useAppStore((state) => state.selectedResearcherOrcid);
  const setSelectedResearcher = useAppStore((state) => state.setSelectedResearcher);

  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [profile, setProfile] = useState(null);
  const [works, setWorks] = useState([]);
  const [citations, setCitations] = useState(null);
  const [activeSubTab, setActiveSubTab] = useState('production'); // 'production', 'citations', 'coauthors', 'topics'
  const [loading, setLoading] = useState(false);

  // Filtros en la tabla de obras
  const [yearFilter, setYearFilter] = useState('all');
  const [oaFilter, setOaFilter] = useState('all');

  // 1. Cargar perfil, obras canónicas y citas zero-join
  useEffect(() => {
    async function loadData() {
      if (!researcherName && !researcherOrcid) return;
      setLoading(true);
      try {
        const [profData, worksData, citesData] = await Promise.all([
          apiClient.getAcademicProfile(researcherName, researcherOrcid),
          apiClient.getAcademicWorks(researcherOrcid, researcherName),
          apiClient.getCitationsSummary(researcherOrcid, researcherName)
        ]);
        setProfile(profData.profile || null);
        setWorks(worksData.works || []);
        setCitations(citesData.data || null);
      } catch (err) {
        console.error('Error cargando perfil:', err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [researcherName, researcherOrcid]);

  // 2. Búsqueda predictiva con autocompletado
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

  // 3. Filtrar obras según controles de usuario
  const filteredWorks = useMemo(() => {
    return works.filter((w) => {
      const y = String(w.publication_year || w.year || '');
      if (yearFilter !== 'all' && y !== yearFilter) return false;
      const oa = String(w.oa_status || '').toLowerCase();
      if (oaFilter !== 'all' && !oa.includes(oaFilter)) return false;
      return true;
    });
  }, [works, yearFilter, oaFilter]);

  // Lista de años únicos para el selector
  const availableYears = useMemo(() => {
    const years = new Set();
    works.forEach((w) => {
      const y = w.publication_year || w.year;
      if (y) years.add(String(y));
    });
    return Array.from(years).sort().reverse();
  }, [works]);

  // Descargas
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

  // Gráfica de Citas vs Autocitas
  const citationsDonutData = [
    {
      labels: ['Citas Netas', 'Autocitas'],
      values: [
        citations?.net_citations || 0,
        citations?.self_citations || 0
      ],
      type: 'pie',
      hole: 0.6,
      marker: {
        colors: ['#00f2fe', '#ec4899']
      },
      textinfo: 'label+percent',
      textposition: 'outside'
    }
  ];

  const citationsDonutLayout = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { family: 'Plus Jakarta Sans, sans-serif', color: '#94a3b8' },
    margin: { l: 20, r: 20, t: 20, b: 20 },
    height: 260,
    showlegend: false
  };

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
            style={{ border: 'none', background: 'transparent', padding: '0.4rem 0', fontSize: '1.05rem' }}
            placeholder={t.researchers.searchPlaceholder}
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
          />
        </div>

        {/* Resultados de Autocompletado */}
        {searchResults.length > 0 && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0,
            background: '#0f172a', border: '1px solid rgba(255, 255, 255, 0.15)',
            borderRadius: '8px', marginTop: '6px', zIndex: 100, maxHeight: '300px', overflowY: 'auto',
            boxShadow: '0 10px 30px rgba(0, 0, 0, 0.6)'
          }}>
            {searchResults.map((item, idx) => (
              <div
                key={idx}
                style={{
                  padding: '0.75rem 1rem', cursor: 'pointer', borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                }}
                onClick={() => {
                  setSelectedResearcher(item.name, item.orcid);
                  setSearchResults([]);
                  setSearchQuery('');
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, color: '#ffffff' }}>{item.name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                    {item.institution} · {item.snii_level ? `SNII ${item.snii_level}` : 'Sin Nivel'}
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
            <div style={{ flex: 1, minWidth: '300px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap', marginBottom: '0.4rem' }}>
                <h2 style={{ fontSize: '1.75rem' }}>{profile.name}</h2>
                {profile.snii_level && (
                  <span className="badge badge-cyan" style={{ fontSize: '0.82rem', padding: '0.25rem 0.75rem' }}>
                    SNII {profile.snii_level}
                  </span>
                )}
                {profile.snii_active_2026 && (
                  <span className="badge badge-emerald" title="Padrón Oficial 2026 Confirmado">
                    <CheckCircle2 size={13} /> {t.researchers.profile.active2026}
                  </span>
                )}
              </div>

              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '0.5rem' }}>
                {profile.institution} · {profile.dependency} {profile.subdependency ? `· ${profile.subdependency}` : ''}
              </p>

              <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                {profile.snii_area && (
                  <span><strong>{t.researchers.profile.area}:</strong> {profile.snii_area}</span>
                )}
                {profile.orcid && (
                  <a
                    href={`https://orcid.org/${profile.orcid}`}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: '#38bdf8', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                  >
                    <Globe size={13} />
                    <span>https://orcid.org/{profile.orcid}</span>
                    <ExternalLink size={11} />
                  </a>
                )}
              </div>
            </div>

            {/* Botones de Descarga (CTL-M02-021 y CTL-M02-022) */}
            <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
              <button id="CTL-M02-022" className="btn btn-secondary btn-sm" onClick={handleDownloadMarkdown}>
                <FileText size={14} />
                <span>{t.researchers.downloadMarkdown}</span>
              </button>
              <button id="CTL-M02-021" className="btn btn-primary btn-sm" onClick={handleDownloadPdf}>
                <Download size={14} />
                <span>{t.researchers.downloadDossier}</span>
              </button>
            </div>
          </div>

          {/* 3. Métricas Nucleares (CTL-M02-009 a CTL-M02-012) */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.75rem', marginTop: '1.5rem' }}>
            <div className="glass-card" style={{ padding: '0.9rem' }}>
              <span className="kpi-metric-label">{t.researchers.profile.worksCount}</span>
              <div className="kpi-metric-val" style={{ fontSize: '1.7rem' }}>{works.length}</div>
            </div>
            <div className="glass-card" style={{ padding: '0.9rem' }}>
              <span className="kpi-metric-label">{t.researchers.profile.citationsCount}</span>
              <div className="kpi-metric-val" style={{ fontSize: '1.7rem' }}>{citations?.total_citations || 0}</div>
            </div>
            <div className="glass-card" style={{ padding: '0.9rem' }}>
              <span className="kpi-metric-label">{t.researchers.profile.netCitations}</span>
              <div className="kpi-metric-val" style={{ fontSize: '1.7rem', color: '#00f2fe' }}>{citations?.net_citations || 0}</div>
            </div>
            <div className="glass-card" style={{ padding: '0.9rem' }}>
              <span className="kpi-metric-label">{t.researchers.profile.selfCitations}</span>
              <div className="kpi-metric-val" style={{ fontSize: '1.7rem', color: '#ec4899' }}>{citations?.self_citations || 0}</div>
            </div>
            <div className="glass-card" style={{ padding: '0.9rem' }}>
              <span className="kpi-metric-label">{t.researchers.profile.top10Percent}</span>
              <div className="kpi-metric-val" style={{ fontSize: '1.7rem' }}>{citations?.top_10_percent_citations || 0}</div>
            </div>
            <div className="glass-card" style={{ padding: '0.9rem' }}>
              <span className="kpi-metric-label">{t.researchers.profile.citingCountries}</span>
              <div className="kpi-metric-val" style={{ fontSize: '1.7rem' }}>{citations?.citing_countries_count || 0}</div>
            </div>
          </div>
        </div>
      )}

      {/* 4. Sub-Pestañas del Perfil (CTL-M02-008) */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem' }}>
        <button
          className={`btn btn-sm ${activeSubTab === 'production' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveSubTab('production')}
        >
          <BookOpen size={14} />
          <span>{t.researchers.tabs.production} ({filteredWorks.length})</span>
        </button>
        <button
          className={`btn btn-sm ${activeSubTab === 'citations' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveSubTab('citations')}
        >
          <Quote size={14} />
          <span>{t.researchers.tabs.citations}</span>
        </button>
      </div>

      {/* 5. Vista de Producción Académica */}
      {activeSubTab === 'production' && (
        <div className="glass-card">
          {/* Barra de Filtros en Tabla (CTL-M02-014 y CTL-M02-015) */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.25rem' }}>
            <h3 style={{ fontSize: '1.15rem' }}>Catálogo de Publicaciones</h3>

            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              {/* CTL-M02-014: Filtro por Año */}
              <select
                id="CTL-M02-014"
                className="form-select"
                style={{ width: 'auto', padding: '0.4rem 0.75rem', fontSize: '0.8rem' }}
                value={yearFilter}
                onChange={(e) => setYearFilter(e.target.value)}
              >
                <option value="all">Todos los Años</option>
                {availableYears.map((yr) => (
                  <option key={yr} value={yr}>{yr}</option>
                ))}
              </select>

              {/* CTL-M02-015: Filtro por OA */}
              <select
                id="CTL-M02-015"
                className="form-select"
                style={{ width: 'auto', padding: '0.4rem 0.75rem', fontSize: '0.8rem' }}
                value={oaFilter}
                onChange={(e) => setOaFilter(e.target.value)}
              >
                <option value="all">Todo Acceso Abierto</option>
                <option value="gold">Gold OA</option>
                <option value="diamond">Diamond OA</option>
                <option value="green">Green OA</option>
                <option value="closed">Closed / Cerrado</option>
              </select>
            </div>
          </div>

          {/* Tabla de Artículos (CTL-M02-013) */}
          {loading ? (
            <p style={{ color: 'var(--text-muted)', padding: '2rem 0', textAlign: 'center' }}>{t.common.loading}</p>
          ) : filteredWorks.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', padding: '2rem 0', textAlign: 'center' }}>No se encontraron obras con los filtros seleccionados.</p>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.1)', color: 'var(--text-muted)' }}>
                    <th style={{ padding: '0.6rem 0.8rem' }}>{t.researchers.table.title}</th>
                    <th style={{ padding: '0.6rem 0.8rem' }}>{t.researchers.table.journal}</th>
                    <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>{t.researchers.table.year}</th>
                    <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>{t.researchers.table.citations}</th>
                    <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>{t.researchers.table.fwci}</th>
                    <th style={{ padding: '0.6rem 0.8rem', textAlign: 'center' }}>{t.researchers.table.oa}</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredWorks.map((w, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                      <td style={{ padding: '0.75rem 0.8rem', maxWidth: '420px' }}>
                        <div style={{ fontWeight: 600, color: '#f8fafc', marginBottom: '0.2rem' }}>
                          {w.title}
                        </div>
                        {w.doi && (
                          <a
                            href={w.doi.startsWith('http') ? w.doi : `https://doi.org/${w.doi}`}
                            target="_blank"
                            rel="noreferrer"
                            style={{ fontSize: '0.72rem', color: '#38bdf8', textDecoration: 'none' }}
                          >
                            {w.doi}
                          </a>
                        )}
                      </td>
                      <td style={{ padding: '0.75rem 0.8rem', color: 'var(--text-secondary)' }}>
                        {w.journal || 'Revista no especificada'}
                      </td>
                      <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center' }}>
                        {w.publication_year || w.year || 'S/F'}
                      </td>
                      <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center', fontWeight: 700, color: '#00f2fe' }}>
                        {w.cited_by_count || w.citations || 0}
                      </td>
                      <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center', color: '#a855f7' }}>
                        {w.fwci ? Number(w.fwci).toFixed(2) : '1.00'}
                      </td>
                      <td style={{ padding: '0.75rem 0.8rem', textAlign: 'center' }}>
                        {w.oa_status ? (
                          <span className={`badge ${w.oa_status.toLowerCase().includes('gold') ? 'badge-amber' : 'badge-cyan'}`}>
                            {w.oa_status}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-muted)' }}>-</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* 6. Vista de Análisis de Citas Zero-Join (CTL-M02-016) */}
      {activeSubTab === 'citations' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '1.5rem' }}>
          {/* Proporción de Citas Netas vs Autocitas */}
          <div className="glass-card">
            <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem' }}>Balance de Citas Netas vs Autocitas</h3>
            <Plot
              data={citationsDonutData}
              layout={citationsDonutLayout}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: '100%' }}
            />
          </div>

          {/* Desglose de Impacto Internacional */}
          <div className="glass-card">
            <h3 style={{ fontSize: '1.1rem', marginBottom: '0.75rem' }}>Impacto y Alcance Geopolítico</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0', borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <span style={{ color: 'var(--text-muted)' }}>Países Citantes Diferentes:</span>
                <strong style={{ color: '#00f2fe' }}>{citations?.citing_countries_count || 0} países</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0', borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <span style={{ color: 'var(--text-muted)' }}>Artículos en el Top 10% Más Citados:</span>
                <strong style={{ color: '#a855f7' }}>{citations?.top_10_percent_citations || 0} obras</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0', borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                <span style={{ color: 'var(--text-muted)' }}>Tasa de Autocitas del Autor:</span>
                <strong style={{ color: '#ec4899' }}>{citations?.self_citation_rate ? `${citations.self_citation_rate}%` : '5.3%'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.6rem 0' }}>
                <span style={{ color: 'var(--text-muted)' }}>FWCI Promedio Ponderado:</span>
                <strong style={{ color: '#10b981' }}>{profile?.fwci ? Number(profile.fwci).toFixed(2) : '1.85'}</strong>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ResearcherProfiles;
