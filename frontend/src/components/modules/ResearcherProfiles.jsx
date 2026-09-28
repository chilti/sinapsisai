/**
 * frontend/src/components/modules/ResearcherProfiles.jsx
 * Módulo 2: Perfiles de Investigadores y Producción Académica
 */

import React, { useState, useEffect } from 'react';
import { Search, Award, BookOpen, Quote, Download, Globe, CheckCircle2 } from 'lucide-react';
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
  const [loading, setLoading] = useState(false);

  // Cargar perfil y obras del investigador activo
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

  // Manejo de búsqueda predictiva
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

  const handleDownloadMarkdown = async () => {
    try {
      const blob = await apiClient.downloadDossierMarkdown(researcherName, researcherOrcid);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Reporte_${researcherName.replace(/\s+/g, '_')}.md`;
      a.click();
    } catch (err) {
      console.error('Error descargando markdown:', err);
    }
  };

  return (
    <div className="module-container" id="MODULO-02-PERFILES">
      {/* Buscador Predictivo (CTL-M02-001) */}
      <div className="glass-card" style={{ marginBottom: '1.5rem', position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Search size={18} style={{ color: 'var(--text-muted)' }} />
          <input
            id="CTL-M02-001"
            type="text"
            className="form-input"
            style={{ border: 'none', background: 'transparent', padding: '0.4rem 0', fontSize: '1rem' }}
            placeholder={t.researchers.searchPlaceholder}
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
          />
        </div>

        {searchResults.length > 0 && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0,
            background: '#0f172a', border: '1px solid rgba(255, 255, 255, 0.12)',
            borderRadius: '8px', marginTop: '6px', zIndex: 50, maxHeight: '280px', overflowY: 'auto'
          }}>
            {searchResults.map((item, idx) => (
              <div
                key={idx}
                style={{ padding: '0.65rem 1rem', cursor: 'pointer', borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}
                onClick={() => {
                  setSelectedResearcher(item.name, item.orcid);
                  setSearchResults([]);
                  setSearchQuery('');
                }}
              >
                <div style={{ fontWeight: 600, color: '#ffffff' }}>{item.name}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  {item.institution} · {item.snii_level ? `SNII ${item.snii_level}` : 'Sin Nivel'}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tarjeta de Perfil SNII */}
      {profile && (
        <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                <h2 style={{ fontSize: '1.5rem' }}>{profile.name}</h2>
                {profile.snii_level && (
                  <span className="badge badge-cyan">SNII {profile.snii_level}</span>
                )}
                {profile.snii_active_2026 && (
                  <span className="badge badge-emerald" title="Padrón 2026 confirmado">
                    <CheckCircle2 size={12} /> 2026
                  </span>
                )}
              </div>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                {profile.institution} · {profile.dependency} · Área {profile.snii_area || 'Sin Área'}
              </p>
              {profile.orcid && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.4rem', fontSize: '0.78rem', color: '#38bdf8' }}>
                  <Globe size={13} />
                  <span>https://orcid.org/{profile.orcid}</span>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button id="CTL-M02-022" className="btn btn-secondary btn-sm" onClick={handleDownloadMarkdown}>
                <Download size={14} />
                <span>Markdown</span>
              </button>
            </div>
          </div>

          {/* KPIs del Investigador */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', marginTop: '1.25rem' }}>
            <div className="glass-card" style={{ padding: '0.85rem' }}>
              <span className="kpi-metric-label">{t.researchers.profile.worksCount}</span>
              <div className="kpi-metric-val" style={{ fontSize: '1.6rem' }}>{works.length}</div>
            </div>
            <div className="glass-card" style={{ padding: '0.85rem' }}>
              <span className="kpi-metric-label">{t.researchers.profile.citationsCount}</span>
              <div className="kpi-metric-val" style={{ fontSize: '1.6rem' }}>{citations?.total_citations || 0}</div>
            </div>
            <div className="glass-card" style={{ padding: '0.85rem' }}>
              <span className="kpi-metric-label">{t.researchers.profile.netCitations}</span>
              <div className="kpi-metric-val" style={{ fontSize: '1.6rem' }}>{citations?.net_citations || 0}</div>
            </div>
            <div className="glass-card" style={{ padding: '0.85rem' }}>
              <span className="kpi-metric-label">{t.researchers.profile.selfCitations}</span>
              <div className="kpi-metric-val" style={{ fontSize: '1.6rem' }}>{citations?.self_citations || 0}</div>
            </div>
            <div className="glass-card" style={{ padding: '0.85rem' }}>
              <span className="kpi-metric-label">{t.researchers.profile.citingCountries}</span>
              <div className="kpi-metric-val" style={{ fontSize: '1.6rem' }}>{citations?.citing_countries_count || 0}</div>
            </div>
          </div>
        </div>
      )}

      {/* Lista de Publicaciones */}
      <div className="glass-card">
        <h3 style={{ fontSize: '1.15rem', marginBottom: '1rem' }}>
          {t.researchers.tabs.production} ({works.length})
        </h3>
        {loading ? (
          <p style={{ color: 'var(--text-muted)' }}>{t.common.loading}</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {works.slice(0, 15).map((w, idx) => (
              <div key={idx} style={{
                padding: '0.85rem 1rem', background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid rgba(255, 255, 255, 0.05)', borderRadius: '8px'
              }}>
                <div style={{ fontWeight: 600, color: '#f8fafc', marginBottom: '0.2rem' }}>
                  {w.title}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                  <span>📅 {w.publication_year || w.year || 'S/F'}</span>
                  <span>📖 {w.journal || 'Revista no especificada'}</span>
                  <span>⚡ Citas: {w.cited_by_count || w.citations || 0}</span>
                  {w.oa_status && <span className="badge badge-cyan">{w.oa_status}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default ResearcherProfiles;
