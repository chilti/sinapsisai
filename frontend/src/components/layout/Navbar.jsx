/**
 * frontend/src/components/layout/Navbar.jsx
 * Barra de Navegación Principal de SNII Info TlachIA (Control 1 a 1 de Módulo 7)
 */

import React, { useState } from 'react';
import {
  Building2,
  Users,
  Compass,
  UserCheck,
  ShieldCheck,
  Bot,
  Globe,
  LogIn,
  LogOut,
  Sparkles,
  ChevronDown
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import { LANGUAGES } from '../../i18n/index.js';

export function Navbar() {
  const activeTab = useAppStore((state) => state.activeTab);
  const setActiveTab = useAppStore((state) => state.setActiveTab);
  const language = useAppStore((state) => state.language);
  const setLanguage = useAppStore((state) => state.setLanguage);
  const userSession = useAppStore((state) => state.userSession);
  const logout = useAppStore((state) => state.logout);
  const t = useAppStore((state) => state.t)();

  const [langMenuOpen, setLangMenuOpen] = useState(false);

  const navItems = [
    { id: 'panorama', label: t.tabs.panorama, icon: Building2, controlId: 'CTL-M07-005' },
    { id: 'researchers', label: t.tabs.researchers, icon: Users, controlId: 'CTL-M07-006' },
    { id: 'maps', label: t.tabs.maps, icon: Compass, controlId: 'CTL-M07-007' },
    { id: 'mySpace', label: t.tabs.mySpace, icon: UserCheck, controlId: 'CTL-M07-008' },
    { id: 'governance', label: t.tabs.governance, icon: ShieldCheck, controlId: 'CTL-M07-009' },
    { id: 'assistant', label: t.tabs.assistant, icon: Bot, isAi: true, controlId: 'CTL-M07-010' }
  ];

  const currentLangObj = LANGUAGES.find((l) => l.code === language) || LANGUAGES[0];

  return (
    <nav className="main-navbar" role="navigation" aria-label="Navegación Principal">
      <div className="navbar-container">
        {/* Brand */}
        <div className="navbar-brand" onClick={() => setActiveTab('panorama')}>
          <div className="brand-icon-wrapper">
            <Sparkles className="brand-sparkle-icon" size={18} />
          </div>
          <div className="brand-text-group">
            <span className="brand-main-title">{t.appName}</span>
            <span className="brand-sub-title">{t.appSubtitle}</span>
          </div>
        </div>

        {/* 6 Tabs Navigation */}
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
                onClick={() => setActiveTab(item.id)}
                className={`navbar-tab-btn ${isActive ? 'tab-btn-active' : ''} ${item.isAi ? 'tab-btn-ai' : ''}`}
              >
                <Icon size={16} className="tab-btn-icon" />
                <span className="tab-btn-label">{item.label}</span>
                {item.isAi && <span className="tab-ai-badge">IA</span>}
              </button>
            );
          })}
        </div>

        {/* Right Actions: Language & Auth */}
        <div className="navbar-actions">
          {/* Trilingual Selector (CTL-M07-011) */}
          <div className="lang-selector-wrapper">
            <button
              id="CTL-M07-011"
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

          {/* ORCID Login Button (CTL-M07-012) */}
          {userSession.isAuthenticated ? (
            <div className="user-profile-badge">
              <span className="user-name-label">{userSession.name || userSession.orcid}</span>
              <button
                id="CTL-M07-012-logout"
                className="user-logout-btn"
                onClick={logout}
                title={t.mySpace.logout}
              >
                <LogOut size={14} />
              </button>
            </div>
          ) : (
            <button
              id="CTL-M07-012"
              className="btn btn-secondary btn-sm auth-btn"
              onClick={() => setActiveTab('mySpace')}
            >
              <LogIn size={14} />
              <span>ORCID</span>
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}

export default Navbar;
