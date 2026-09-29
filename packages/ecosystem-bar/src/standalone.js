/**
 * packages/ecosystem-bar/src/standalone.js
 * Web Component autónomo <tlachia-suite-bar> para incrustación directa sin dependencias en HTML y Streamlit.
 */

import { ECOSYSTEM_APPS, SUITE_I18N } from './config.js';

class TlachiaSuiteBarElement extends HTMLElement {
  static get observedAttributes() {
    return ['current-app', 'lang', 'is-dev'];
  }

  connectedCallback() {
    this.render();
  }

  attributeChangedCallback() {
    this.render();
  }

  render() {
    const currentApp = this.getAttribute('current-app') || 'sinapsisai';
    const lang = this.getAttribute('lang') || 'es';
    const isDev = this.getAttribute('is-dev') === 'true' || 
      (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'));

    const i18n = SUITE_I18N[lang] || SUITE_I18N.es;

    const navItems = ECOSYSTEM_APPS.map((app) => {
      const isActive = app.id === currentApp;
      const targetUrl = isDev ? app.devUrl : app.prodUrl;
      const tagline = app.tagline[lang] || app.tagline.es;

      return `
        <a
          href="${isActive ? '#' : targetUrl}"
          class="tlachia-suite-item ${isActive ? 'tlachia-suite-item-active' : ''}"
          title="${app.name}: ${tagline}"
          target="${isActive ? '_self' : '_blank'}"
          rel="noopener noreferrer"
        >
          <span
            class="tlachia-suite-item-dot"
            style="background-color: ${app.badgeColor}; ${isActive ? `box-shadow: 0 0 8px ${app.badgeColor};` : ''}"
          ></span>
          <span class="tlachia-suite-item-name">${app.name}</span>
          <span class="tlachia-suite-tagline">· ${app.badge}</span>
          ${!isActive ? `
            <svg class="tlachia-suite-arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M7 17l9.2-9.2M17 17V8H8" />
            </svg>
          ` : ''}
        </a>
      `;
    }).join('');

    this.innerHTML = `
      <header class="tlachia-suite-container" role="banner" aria-label="${i18n.suiteTitle}">
        <div class="tlachia-suite-inner">
          <div class="tlachia-suite-brand" title="${i18n.suiteSubtitle}">
            <div class="tlachia-suite-logo-pulse">
              <span class="tlachia-suite-logo-pulse-circle"></span>
              <span class="tlachia-suite-logo-pulse-ring"></span>
            </div>
            <span class="tlachia-suite-brand-title">${i18n.suiteTitle}</span>
            <span class="tlachia-suite-badge-version">${i18n.version}</span>
          </div>

          <nav class="tlachia-suite-nav" aria-label="Ecosystem Apps">
            ${navItems}
          </nav>
        </div>
      </header>
    `;
  }
}

if (!customElements.get('tlachia-suite-bar')) {
  customElements.define('tlachia-suite-bar', TlachiaSuiteBarElement);
}

export { TlachiaSuiteBarElement };
