import React from 'react';
import { Flame, Rocket, ExternalLink, BookOpen } from 'lucide-react';

export default function FeaturedPublications({ featuredWorks = { most_cited: [], most_recent: [] } }) {
  const mostCited = featuredWorks?.most_cited || [];
  const mostRecent = featuredWorks?.most_recent || [];

  if (mostCited.length === 0 && mostRecent.length === 0) {
    return null;
  }

  return (
    <div className="glass-card" style={{ padding: '1.25rem' }}>
      <div style={{ marginBottom: '1rem' }}>
        <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
          <BookOpen size={18} style={{ color: 'var(--accent-cyan)' }} />
          🌟 Publicaciones Destacadas
        </h3>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
          Hitos de mayor impacto acumulado y aportaciones científicas más recientes de la investigadora o investigador.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.25rem' }}>
        {/* Columna: Artículos Más Citados */}
        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '1rem', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.45rem', color: '#f59e0b', marginBottom: '0.85rem' }}>
            <Flame size={16} /> 🔥 Artículos Más Citados
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            {mostCited.map((p, idx) => (
              <div
                key={idx}
                style={{
                  padding: '0.6rem 0.75rem',
                  borderRadius: '8px',
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(255,255,255,0.05)',
                  fontSize: '0.82rem',
                  lineHeight: 1.45
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem', marginBottom: '0.25rem' }}>
                  <span className="badge badge-amber" style={{ fontSize: '0.72rem', padding: '0.15rem 0.45rem', fontWeight: 800 }}>
                    {p.citations?.toLocaleString()} citas
                  </span>
                  {p.year && (
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      {p.year}
                    </span>
                  )}
                </div>
                {p.doi_url ? (
                  <a
                    href={p.doi_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: 'var(--text-primary)', fontWeight: 600, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
                  >
                    <span>{p.title}</span>
                    <ExternalLink size={12} style={{ opacity: 0.6, flexShrink: 0 }} />
                  </a>
                ) : (
                  <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{p.title}</span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Columna: Artículos Más Recientes */}
        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '1rem', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.45rem', color: 'var(--accent-cyan)', marginBottom: '0.85rem' }}>
            <Rocket size={16} /> 🚀 Artículos Más Recientes
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
            {mostRecent.map((p, idx) => (
              <div
                key={idx}
                style={{
                  padding: '0.6rem 0.75rem',
                  borderRadius: '8px',
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(255,255,255,0.05)',
                  fontSize: '0.82rem',
                  lineHeight: 1.45
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem', marginBottom: '0.25rem' }}>
                  <span className="badge badge-cyan" style={{ fontSize: '0.72rem', padding: '0.15rem 0.45rem', fontWeight: 800 }}>
                    {p.year || 'Reciente'}
                  </span>
                  {p.citations !== undefined && (
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      {p.citations} citas
                    </span>
                  )}
                </div>
                {p.doi_url ? (
                  <a
                    href={p.doi_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: 'var(--text-primary)', fontWeight: 600, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
                  >
                    <span>{p.title}</span>
                    <ExternalLink size={12} style={{ opacity: 0.6, flexShrink: 0 }} />
                  </a>
                ) : (
                  <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{p.title}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
