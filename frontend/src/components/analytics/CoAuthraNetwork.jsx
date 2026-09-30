import React, { useState } from 'react';
import { Share2, Eye, EyeOff, ExternalLink } from 'lucide-react';

export default function CoAuthraNetwork({
  academicName = "",
  authorId = "", // OpenAlex ID (ej: A5012345678) o ORCID
}) {
  // Embebido activo por defecto como en el dashboard original
  const [isOpen, setIsOpen] = useState(true);

  // Obtener la ruta base dinámica según el entorno (/sinapsisai_dev o /infotlachia)
  const getBasePath = () => {
    if (typeof window === 'undefined') return '';
    const p = window.location.pathname;
    if (p.includes('/sinapsisai_dev')) return '/sinapsisai_dev';
    if (p.includes('/infotlachia')) return '/infotlachia';
    if (p.includes('/sinapsisai')) return '/sinapsisai';
    return '';
  };

  // Limpiar el ID si viene con URL o en lista separada por comas
  const rawId = String(authorId || "").split(',')[0].trim();
  const cleanId = rawId.replace("https://openalex.org/", "").replace("https://orcid.org/", "").trim();
  const basePath = getBasePath();
  const iframeSrc = cleanId 
    ? `${basePath}/static/coauthra.html?author=${encodeURIComponent(cleanId)}` 
    : `${basePath}/static/coauthra.html`;

  return (
    <div className="glass-card" style={{ padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '0.85rem' }}>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
            <Share2 size={18} style={{ color: 'var(--accent-cyan)' }} />
            🕸️ Red de Colaboración Científica
          </h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, maxWidth: '850px' }}>
            Explora el mapa interactivo de coautorías y grafos académicos de <strong style={{ color: 'var(--text-primary)' }}>{academicName}</strong>.
            Esta visualización identifica comunidades científicas, proximidad temática y autores puente.
          </p>
        </div>

        <button
          onClick={() => setIsOpen(!isOpen)}
          className={`btn ${isOpen ? 'btn-outline' : 'btn-primary'}`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.45rem',
            padding: '0.45rem 1rem',
            fontSize: '0.82rem',
            fontWeight: 700
          }}
        >
          {isOpen ? (
            <>
              <EyeOff size={15} /> Ocultar Red de Colaboración
            </>
          ) : (
            <>
              <Eye size={15} /> 🕸️ Cargar Red de Colaboración
            </>
          )}
        </button>
      </div>

      {isOpen && (
        <div style={{ marginTop: '1rem', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border-subtle)', background: '#0b1120' }}>
          <iframe
            src={iframeSrc}
            title={`Red de Colaboración - ${academicName}`}
            style={{
              width: '100%',
              height: '750px',
              border: 'none',
              display: 'block'
            }}
          />
          <div style={{ padding: '0.65rem 1rem', background: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            <span>Visualización interactiva provista por <strong>CoAuthra</strong> (Joe Barnier, Licencia CC BY-NC-ND 4.0).</span>
            <a
              href={`https://coauthra.com/?author=${encodeURIComponent(cleanId)}`}
              target="_blank"
              rel="noreferrer"
              style={{ color: 'var(--accent-cyan)', display: 'inline-flex', alignItems: 'center', gap: '0.25rem', textDecoration: 'none' }}
            >
              Abrir en CoAuthra.com <ExternalLink size={12} />
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
