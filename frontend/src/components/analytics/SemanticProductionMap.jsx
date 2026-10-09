import React, { useState, useRef, useEffect } from 'react';
import { Compass, Eye, EyeOff, Sparkles, ExternalLink } from 'lucide-react';

export default function SemanticProductionMap({
  targetName = "Entidad",
  type = "institution", // "institution" o "author"
  dois = [],
  oaIds = [],
  totalWorks = 0
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const iframeRef = useRef(null);

  // Limpieza de siglas institucionales para URL y detección de ámbito nacional
  const isMexico = targetName && (targetName.toUpperCase() === 'MÉXICO' || targetName.toUpperCase() === 'MEXICO');
  const cleanTargetName = type === 'institution' ? targetName.replace(/\s*\([^)]*\)/g, '').trim() : targetName;
  const encodedTarget = encodeURIComponent(cleanTargetName);
  const paramKey = type === "author" ? "highlight_author" : "highlight_inst";
  const iframeSrc = `https://dinamica1.fciencias.unam.mx/tiles/map_test.html?v=28&data=https://dinamica1.fciencias.unam.mx/tiles/articles_specter_data.json?v=28&color_by=cluster&${paramKey}=${encodedTarget}`;

  // Comunicación bidireccional con el iframe WebGL vía postMessage
  const handleIframeLoad = () => {
    setIsLoading(false);
    if (iframeRef.current && iframeRef.current.contentWindow) {
      try {
        iframeRef.current.contentWindow.postMessage({
          type: 'HIGHLIGHT_DOIS',
          dois: Array.isArray(dois) ? dois : [],
          oa_ids: Array.isArray(oaIds) ? oaIds : []
        }, '*');
      } catch (e) {
        console.warn('postMessage to WebGL map blocked or error:', e);
      }
    }
  };

  return (
    <div className="glass-card" style={{ padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '0.85rem' }}>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
            <Compass size={18} style={{ color: 'var(--accent-cyan)' }} />
            🗺️ Mapa Semántico de Producción (WebGL)
          </h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, maxWidth: '850px' }}>
            Exploración espacial de la producción científica en alta dimensión (Specter / UMAP).
            {totalWorks > 0 ? (
              isMexico ? (
                <> Los <strong style={{ color: 'var(--accent-cyan)' }}>{totalWorks.toLocaleString()} artículos</strong> de la ciencia mexicana están proyectados y coloreados por cluster temático.</>
              ) : (
                <> Los <strong style={{ color: 'var(--accent-cyan)' }}>{totalWorks.toLocaleString()} artículos</strong> de {targetName} están coloreados; el resto de la base nacional aparece en gris tenue.</>
              )
            ) : (
              <> Los artículos de la entidad están coloreados dentro del cosmos de la ciencia nacional.</>
            )}
          </p>
        </div>

        <button
          onClick={() => {
            if (!isOpen) setIsLoading(true);
            setIsOpen(!isOpen);
          }}
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
              <EyeOff size={15} /> Ocultar Mapa WebGL
            </>
          ) : (
            <>
              <Eye size={15} /> Cargar Mapa Interactivo (WebGL)
            </>
          )}
        </button>
      </div>

      {isOpen && (
        <div style={{ marginTop: '1rem', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border-subtle)', background: '#0a0f1d', position: 'relative' }}>
          {isLoading && (
            <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: 'rgba(10, 15, 29, 0.85)', zIndex: 10, color: 'var(--text-primary)' }}>
              <Sparkles size={28} className="animate-spin" style={{ color: 'var(--accent-cyan)', marginBottom: '0.75rem' }} />
              <span style={{ fontSize: '0.9rem', fontWeight: 600 }}>Cargando atlas semántico WebGL de la producción...</span>
            </div>
          )}
          <iframe
            ref={iframeRef}
            src={iframeSrc}
            title={`Mapa Semántico de Producción - ${targetName}`}
            style={{
              width: '100%',
              height: '620px',
              border: 'none',
              display: 'block'
            }}
            onLoad={handleIframeLoad}
          />
          <div style={{ padding: '0.5rem 1rem', background: 'rgba(0,0,0,0.6)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            <span>Motor de proyección tridimensional Specter / WebGL dinámico. Usa el ratón o trackpad para zoom y rotación espacial.</span>
            <a
              href={iframeSrc}
              target="_blank"
              rel="noreferrer"
              style={{ color: 'var(--accent-cyan)', display: 'inline-flex', alignItems: 'center', gap: '0.25rem', textDecoration: 'none' }}
            >
              Abrir pantalla completa <ExternalLink size={12} />
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
