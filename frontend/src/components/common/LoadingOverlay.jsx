/**
 * frontend/src/components/common/LoadingOverlay.jsx
 * Componente de carga Glassmorphic con animación WebGL (Sparkles + Resplandor Cian)
 * Soporta modo Overlay translúcido sobre contenido existente y modo standalone.
 */

import React from 'react';
import { Sparkles } from 'lucide-react';

export function LoadingOverlay({
  loading = false,
  message = 'Cargando datos...',
  subtitle = '',
  minHeight = '360px',
  children = null
}) {
  const content = (
    <div className="webgl-loading-card">
      <div className="webgl-loading-sparkles-wrap">
        <div className="webgl-loading-glow" />
        <Sparkles size={32} className="animate-spin" style={{ color: 'var(--accent-cyan)' }} />
      </div>
      <div className="webgl-loading-message">{message}</div>
      {subtitle && <div className="webgl-loading-subtitle" title={subtitle}>{subtitle}</div>}
    </div>
  );

  if (!children) {
    if (!loading) return null;
    return (
      <div className="webgl-loading-standalone" style={{ minHeight }}>
        {content}
      </div>
    );
  }

  return (
    <div className="webgl-loading-container" style={{ minHeight: loading ? minHeight : undefined }}>
      <div className={loading ? 'webgl-loading-content-blurred' : 'webgl-loading-content-active'}>
        {children}
      </div>

      {loading && (
        <div className="webgl-loading-backdrop" aria-busy="true" aria-live="polite">
          {content}
        </div>
      )}
    </div>
  );
}

export default LoadingOverlay;
