/**
 * frontend/src/components/modules/HomeGalaxy.jsx
 * Pestaña de Inicio: Galaxia del Conocimiento Científico (Animación WebGL Interactiva)
 * Paridad exacta con la pestaña "🌌 Inicio" del dashboard original de Streamlit.
 */

import React, { useState, useRef } from 'react';
import { Sparkles, Maximize2, Minimize2, RotateCcw, ExternalLink, Compass } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';

export function HomeGalaxy() {
  const [isLoading, setIsLoading] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [iframeKey, setIframeKey] = useState(1);
  const containerRef = useRef(null);
  const theme = useAppStore((state) => state.theme);
  const isLight = theme === 'claro';

  const iframeUrl = "https://dinamica1.fciencias.unam.mx/tiles/map.html?v=26&demo=true&data=https://dinamica1.fciencias.unam.mx/tiles/articles_data.json?v=26";

  const handleToggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  const handleReload = () => {
    setIsLoading(true);
    setIframeKey((prev) => prev + 1);
  };

  return (
    <div
      ref={containerRef}
      className="module-container"
      style={{
        padding: isFullscreen ? 0 : '0.5rem 1.5rem 1.5rem',
        height: isFullscreen ? '100vh' : 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.75rem'
      }}
    >
      {/* Barra Superior con Controles y Badges */}
      {!isFullscreen && (
        <div
          className="glass-card"
          style={{
            padding: '0.65rem 1.25rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '0.75rem'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, rgba(0, 242, 254, 0.2), rgba(79, 70, 229, 0.2))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--accent-cyan)'
              }}
            >
              <Compass size={18} />
            </div>
            <div>
              <h2 style={{ fontSize: '1.15rem', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                Mapa de la Ciencia Mexicana
                <span className="badge badge-purple" style={{ fontSize: '0.7rem' }}>WebGL 3D/2D</span>
              </h2>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Cartografía topológica interactiva de artículos, clústeres temáticos y trayectorias nacionales
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              onClick={handleReload}
              className="btn btn-secondary btn-sm"
              title="Reiniciar animación"
              style={{ padding: '0.35rem 0.65rem', fontSize: '0.8rem' }}
            >
              <RotateCcw size={14} />
              <span>Reiniciar</span>
            </button>
            <button
              onClick={handleToggleFullscreen}
              className="btn btn-secondary btn-sm"
              title={isFullscreen ? "Salir de pantalla completa" : "Pantalla completa"}
              style={{ padding: '0.35rem 0.65rem', fontSize: '0.8rem' }}
            >
              {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              <span>{isFullscreen ? "Reducir" : "Pantalla Completa"}</span>
            </button>
            <a
              href={iframeUrl}
              target="_blank"
              rel="noreferrer"
              className="btn btn-primary btn-sm"
              style={{ padding: '0.35rem 0.75rem', fontSize: '0.8rem', textDecoration: 'none' }}
              title="Abrir en pestaña independiente"
            >
              <ExternalLink size={14} />
              <span>Visor Externo</span>
            </a>
          </div>
        </div>
      )}

      {/* Contenedor Iframe del Mapa de la Ciencia Mexicana */}
      <div
        className="glass-card"
        style={{
          position: 'relative',
          width: '100%',
          height: isFullscreen ? '100vh' : 'calc(100vh - 170px)',
          minHeight: '520px',
          overflow: 'hidden',
          padding: 0,
          borderRadius: isFullscreen ? 0 : '12px',
          border: isFullscreen ? 'none' : '1px solid var(--border-subtle)',
          background: isLight ? '#f4f4f5' : '#07090e'
        }}
      >
        {/* Spinner elegante mientras carga */}
        {isLoading && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              background: isLight ? 'rgba(244, 244, 245, 0.92)' : 'rgba(7, 9, 14, 0.92)',
              zIndex: 10,
              gap: '0.85rem'
            }}
          >
            <div
              style={{
                width: '40px',
                height: '40px',
                border: '3px solid rgba(0, 242, 254, 0.2)',
                borderTopColor: 'var(--accent-cyan)',
                borderRadius: '50%',
                animation: 'spin 0.8s linear infinite'
              }}
            />
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <Sparkles size={16} style={{ color: 'var(--accent-cyan)' }} />
                Cargando mapa de la ciencia Mexicana...
              </div>
              <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Renderizando mapa topológico de artículos y clústeres en WebGL
              </span>
            </div>
          </div>
        )}

        <iframe
          key={iframeKey}
          id="galaxy-map-iframe"
          title="Mapa de la Ciencia Mexicana"
          src={iframeUrl}
          onLoad={() => setIsLoading(false)}
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
            display: 'block'
          }}
          scrolling="no"
          allow="fullscreen"
        />
      </div>
    </div>
  );
}

export default HomeGalaxy;
