/**
 * packages/ecosystem-bar/src/TlachiaSuiteBar.jsx
 * Componente React Oficial para la Franja del Ecosistema Científico TlachIA
 */

import React from 'react';
import { ECOSYSTEM_APPS, SUITE_I18N } from './config.js';
import './tlachia-suite-bar.css';

export function TlachiaSuiteBar({
  currentApp = 'sinapsisai',
  lang = 'es',
  isDev = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'),
  onNavigate
}) {
  const i18n = SUITE_I18N[lang] || SUITE_I18N.es;

  const handleAppClick = (app, e) => {
    if (app.id === currentApp) {
      e.preventDefault();
      return;
    }
    if (onNavigate) {
      const intercepted = onNavigate(app);
      if (intercepted) {
        e.preventDefault();
      }
    }
  };

  return (
    <header className="tlachia-suite-container" role="banner" aria-label={i18n.suiteTitle}>
      <div className="tlachia-suite-inner">
        {/* Brand / Logo */}
        <div id="suite_brand_link" className="tlachia-suite-brand" title={i18n.suiteSubtitle}>
          <div className="tlachia-suite-logo-pulse">
            <span className="tlachia-suite-logo-pulse-circle"></span>
            <span className="tlachia-suite-logo-pulse-ring"></span>
          </div>
          <span className="tlachia-suite-brand-title">{i18n.suiteTitle}</span>
          <span className="tlachia-suite-badge-version">{i18n.version}</span>
        </div>

        {/* Apps Navigation */}
        <nav className="tlachia-suite-nav" aria-label="Ecosystem Apps">
          {ECOSYSTEM_APPS.map((app) => {
            const isActive = app.id === currentApp;
            const targetUrl = isDev ? app.devUrl : app.prodUrl;
            const tagline = app.tagline[lang] || app.tagline.es;
            const controlId = app.id === 'sinapsisai' 
              ? 'suite_tab_infotlachia' 
              : app.id === 'revistaslatam' 
              ? 'suite_tab_revistaslatam' 
              : app.id === 'knomap' 
              ? 'suite_tab_knomap' 
              : 'suite_tab_metrics';

            return (
              <a
                key={app.id}
                id={controlId}
                href={isActive ? '#' : targetUrl}
                onClick={(e) => handleAppClick(app, e)}
                className={`tlachia-suite-item ${isActive ? 'tlachia-suite-item-active' : ''}`}
                title={`${app.name}: ${tagline}`}
                target={isActive ? '_self' : '_blank'}
                rel="noopener noreferrer"
              >
                <span
                  className="tlachia-suite-item-dot"
                  style={{
                    backgroundColor: app.badgeColor,
                    boxShadow: isActive ? `0 0 8px ${app.badgeColor}` : 'none'
                  }}
                />
                <span className="tlachia-suite-item-name">{app.name}</span>
                <span className="tlachia-suite-tagline">· {app.badge}</span>
                {!isActive && (
                  <svg
                    className="tlachia-suite-arrow-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M7 17l9.2-9.2M17 17V8H8" />
                  </svg>
                )}
              </a>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

export default TlachiaSuiteBar;
