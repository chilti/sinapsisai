/**
 * frontend/src/components/layout/Navbar.jsx
 * Barra de Navegación Principal de Info TlachIA (Control 1 a 1 de Módulo 7)
 */

import React, { useState, useEffect } from 'react';
import {
  Building2,
  Users,
  Compass,
  Network,
  UserCheck,
  ShieldCheck,
  Bot,
  Globe,
  LogIn,
  LogOut,
  Sparkles,
  ChevronDown,
  Sun,
  Moon,
  Info,
  Search,
  Menu,
  X
} from 'lucide-react';
import { useAppStore, isUserAdmin } from '../../store/useAppStore.js';
import { LANGUAGES } from '../../i18n/index.js';
import { GlobalSearchModal } from '../common/GlobalSearchModal.jsx';

export function Navbar() {
  const activeTab = useAppStore((state) => state.activeTab);
  const setActiveTab = useAppStore((state) => state.setActiveTab);
  const language = useAppStore((state) => state.language);
  const setLanguage = useAppStore((state) => state.setLanguage);
  const theme = useAppStore((state) => state.theme);
  const setTheme = useAppStore((state) => state.setTheme);
  const userSession = useAppStore((state) => state.userSession);
  const logout = useAppStore((state) => state.logout);
  const t = useAppStore((state) => state.t)();

  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const isMac = typeof navigator !== 'undefined' && /Mac|iPod|iPhone|iPad/.test(navigator.platform);

  useEffect(() => {
    const handleGlobalKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleGlobalKey);
    return () => window.removeEventListener('keydown', handleGlobalKey);
  }, []);

  const isAdmin = Boolean(
    userSession?.isAuthenticated && isUserAdmin(userSession)
  );

  const navItems = [
    { id: 'national', label: t.tabs?.national || 'Panorama Nacional', icon: Globe, controlId: 'CTL-M07-004B' },
    { id: 'panorama', label: t.tabs?.panorama || 'Panorama Institucional', icon: Building2, controlId: 'CTL-M07-005' },
    { id: 'researchers', label: t.tabs?.researchers || 'Investigadoras e Investigadores', icon: Users, controlId: 'CTL-M07-006' },
    { id: 'maps', label: t.tabs?.maps || 'Mapas de la Ciencia', icon: Compass, controlId: 'CTL-M07-007' },
    { id: 'networks', label: t.tabs?.networks || 'Redes SECIHTI', icon: Network, controlId: 'CTL-M07-007B' },
    { id: 'assistant', label: t.tabs?.assistant || 'Asistente IA', icon: Bot, isAi: true, controlId: 'CTL-M07-010' },
    { id: 'mySpace', label: t.tabs?.mySpace || 'Mi Espacio', icon: UserCheck, controlId: 'CTL-M07-008' },
    ...(isAdmin ? [{ id: 'governance', label: t.tabs?.governance || 'Administración', icon: ShieldCheck, controlId: 'CTL-M07-009' }] : []),
    { id: 'about', label: t.tabs?.about || 'Acerca de', icon: Info, controlId: 'CTL-M07-011' }
  ];

  const currentLangObj = LANGUAGES.find((l) => l.code === language) || LANGUAGES[0];

  return (
    <nav className="main-navbar" role="navigation" aria-label="Navegación Principal">
      {/* Fila 1: Marca, Buscador Global y Acciones */}
      <div className="navbar-top-row">
        <div className="navbar-container">
          {/* Brand */}
          <div className="navbar-brand" onClick={() => setActiveTab('national')}>
            <div className="brand-icon-wrapper">
              <Sparkles className="brand-sparkle-icon" size={18} />
            </div>
            <div className="brand-text-group">
              <span className="brand-main-title">{t.appName}</span>
              <span
                className="brand-sub-title"
                onClick={(e) => {
                  e.stopPropagation();
                  setActiveTab('about');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                style={{ cursor: 'pointer' }}
                title="Ir a Acerca de Info TlachIA SNII"
              >
                {t.appSubtitle}
              </span>
            </div>
          </div>

          {/* Buscador Global (Trigger Directo / Atajo Ctrl+K) */}
          <div className="navbar-search-wrapper">
            <button
              type="button"
              className="navbar-search-trigger"
              onClick={() => setSearchOpen(true)}
              title="Buscar investigadores, facultades, institutos u ORCID (Ctrl + K)"
              aria-label="Abrir buscador global"
            >
              <Search size={15} className="search-trigger-icon" />
              <span className="search-trigger-placeholder">Buscar investigadores, entidades u ORCID...</span>
              <span className="search-trigger-shortcut">
                <kbd>{isMac ? '⌘' : 'Ctrl'}</kbd> <kbd>K</kbd>
              </span>
            </button>
          </div>

          {/* Right Actions: Theme, Language & Auth */}
          <div className="navbar-actions">
            {/* Selector Unificado de Tema: Claro / Oscuro (CTL-M07-007) */}
            <button
              id="CTL-M07-007"
              data-testid="navbar_theme_toggle"
              type="button"
              className="theme-toggle-btn"
              onClick={() => setTheme(theme === 'claro' ? 'oscuro' : 'claro')}
              title={theme === 'claro' ? (t.theme?.dark ? `Cambiar a ${t.theme.dark}` : "Cambiar a modo oscuro") : (t.theme?.light ? `Cambiar a ${t.theme.light}` : "Cambiar a modo claro")}
              aria-label="Alternar tema claro y oscuro"
            >
              {theme === 'claro' ? (
                <>
                  <Sun size={14} className="theme-icon-sun" />
                  <span>{t.theme?.light || "Claro"}</span>
                </>
              ) : (
                <>
                  <Moon size={14} className="theme-icon-moon" />
                  <span>{t.theme?.dark || "Oscuro"}</span>
                </>
              )}
            </button>

            {/* Trilingual Selector (CTL-M07-006 / CTL-M07-011) */}
            <div className="lang-selector-wrapper">
              <button
                id="CTL-M07-006"
                data-testid="navbar_lang_selector"
                type="button"
                className="lang-selector-btn"
                onClick={() => setLangMenuOpen(!langMenuOpen)}
                title={t.common.language}
              >
                <span className="lang-flag">{currentLangObj.flag}</span>
                <span className="lang-code">{currentLangObj.code.toUpperCase()}</span>
                <ChevronDown size={14} className="lang-chevron" />
              </button>

              {langMenuOpen && (
                <div className="lang-dropdown-menu">
                  {LANGUAGES.map((lang) => (
                    <button
                      key={lang.code}
                      className={`lang-dropdown-item ${language === lang.code ? 'lang-item-active' : ''}`}
                      onClick={() => {
                        setLanguage(lang.code);
                        setLangMenuOpen(false);
                      }}
                    >
                      <span className="lang-flag">{lang.flag}</span>
                      <span className="lang-label">{lang.label}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* ORCID Login Button (CTL-M07-009 / CTL-M07-012) */}
            {userSession.isAuthenticated ? (
              <div className="user-profile-badge">
                <span className="user-name-label">{userSession.name || userSession.orcid}</span>
                <button
                  id="CTL-M07-009-logout"
                  className="user-logout-btn"
                  onClick={logout}
                  title={t.mySpace.logout}
                >
                  <LogOut size={14} />
                </button>
              </div>
            ) : (
              <button
                id="CTL-M07-009"
                data-testid="navbar_user_auth_button"
                className="btn btn-secondary btn-sm auth-btn"
                onClick={() => setActiveTab('mySpace')}
              >
                <LogIn size={14} />
                <span>ORCID</span>
              </button>
            )}
          </div>

          {/* Acciones Móviles (< 1024px): Buscar, Tema y Menú Hamburguesa */}
          <div className="navbar-mobile-actions">
            <button
              type="button"
              className="mobile-action-btn"
              onClick={() => setSearchOpen(true)}
              aria-label="Abrir buscador global"
              title="Buscar (Ctrl + K)"
            >
              <Search size={18} />
            </button>

            <button
              type="button"
              className="mobile-action-btn"
              onClick={() => {
                setTheme(theme === 'claro' ? 'oscuro' : 'claro');
              }}
              aria-label="Alternar tema claro y oscuro"
              title={theme === 'claro' ? 'Cambiar a modo oscuro' : 'Cambiar a modo claro'}
            >
              {theme === 'claro' ? <Sun size={17} style={{ color: '#f59e0b' }} /> : <Moon size={17} style={{ color: '#38bdf8' }} />}
            </button>

            <button
              type="button"
              className="mobile-action-btn mobile-hamburger-btn"
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Abrir menú de navegación"
              title="Menú"
            >
              <Menu size={20} />
            </button>
          </div>
        </div>
      </div>

      {/* Fila 2: Pestañas de Navegación Completas (Línea siguiente) */}
      <div className="navbar-nav-row">
        <div className="navbar-container navbar-tabs-container">
          <div className="navbar-tabs-group" role="tablist">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;

              return (
                <button
                  key={item.id}
                  id={item.controlId}
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => {
                    setActiveTab(item.id);
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                  className={`navbar-tab-btn ${isActive ? 'tab-btn-active' : ''} ${item.isAi ? 'tab-btn-ai' : ''}`}
                  title={item.label}
                >
                  <Icon size={16} className="tab-btn-icon" />
                  <span className="tab-btn-label">{item.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Modal / Spotlight de Búsqueda Global */}
      <GlobalSearchModal isOpen={searchOpen} onClose={() => setSearchOpen(false)} />

      {/* Cajón Lateral de Navegación Móvil (Mobile Drawer) */}
      {mobileMenuOpen && (
        <div
          className="mobile-drawer-backdrop"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        className={`mobile-drawer-panel ${mobileMenuOpen ? 'mobile-drawer-open' : ''}`}
        aria-label="Menú Móvil"
        aria-hidden={!mobileMenuOpen}
      >
        <div className="mobile-drawer-header">
          <div className="navbar-brand" onClick={() => { setActiveTab('national'); setMobileMenuOpen(false); }}>
            <div className="brand-icon-wrapper" style={{ width: 32, height: 32 }}>
              <Sparkles className="brand-sparkle-icon" size={16} />
            </div>
            <div className="brand-text-group">
              <span className="brand-main-title" style={{ fontSize: '1rem' }}>{t.appName}</span>
            </div>
          </div>
          <button
            type="button"
            className="mobile-drawer-close-btn"
            onClick={() => setMobileMenuOpen(false)}
            aria-label="Cerrar menú"
          >
            <X size={18} />
          </button>
        </div>

        {/* Estado de usuario / Login */}
        <div className="mobile-drawer-user">
          {userSession.isAuthenticated ? (
            <div className="mobile-user-card">
              <div className="mobile-user-info">
                <span className="mobile-user-name">{userSession.name || userSession.orcid}</span>
                <span className="mobile-user-role">{userSession.role || 'Investigador'}</span>
              </div>
              <button
                type="button"
                className="user-logout-btn"
                onClick={() => { logout(); setMobileMenuOpen(false); }}
                title={t.mySpace.logout}
              >
                <LogOut size={16} />
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ width: '100%', justifyContent: 'center' }}
              onClick={() => { setActiveTab('mySpace'); setMobileMenuOpen(false); }}
            >
              <LogIn size={15} />
              <span>Iniciar sesión con ORCID</span>
            </button>
          )}
        </div>

        {/* Lista de Navegación Completa */}
        <div className="mobile-drawer-body">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  setActiveTab(item.id);
                  setMobileMenuOpen(false);
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                className={`mobile-drawer-item ${isActive ? 'mobile-drawer-item-active' : ''}`}
              >
                <Icon size={18} className="mobile-drawer-icon" />
                <span className="mobile-drawer-label">{item.label}</span>
              </button>
            );
          })}
        </div>

        {/* Footer del Drawer: Idioma y Tema */}
        <div className="mobile-drawer-footer">
          <div>
            <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.4rem', fontWeight: 600 }}>
              {t.common.language}
            </span>
            <div style={{ display: 'flex', gap: '0.4rem' }}>
              {LANGUAGES.map((lang) => (
                <button
                  key={lang.code}
                  type="button"
                  onClick={() => setLanguage(lang.code)}
                  className={`btn btn-sm ${language === lang.code ? 'btn-primary' : 'btn-ghost'}`}
                  style={{ flex: 1, padding: '0.35rem 0.2rem', fontSize: '0.78rem', justifyContent: 'center' }}
                >
                  <span>{lang.flag} {lang.code.toUpperCase()}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.4rem', fontWeight: 600 }}>
              {t.theme?.title || "Tema"}
            </span>
            <button
              type="button"
              className="theme-toggle-btn"
              style={{ width: '100%', justifyContent: 'center' }}
              onClick={() => setTheme(theme === 'claro' ? 'oscuro' : 'claro')}
              title={theme === 'claro' ? 'Cambiar a modo oscuro' : 'Cambiar a modo claro'}
            >
              {theme === 'claro' ? (
                <>
                  <Sun size={14} className="theme-icon-sun" />
                  <span>{t.theme?.light || "Claro"}</span>
                </>
              ) : (
                <>
                  <Moon size={14} className="theme-icon-moon" />
                  <span>{t.theme?.dark || "Oscuro"}</span>
                </>
              )}
            </button>
          </div>
        </div>
      </aside>
    </nav>
  );
}

export default Navbar;
