/**
 * frontend/src/components/common/GlobalSearchModal.jsx
 * Buscador Global Unificado con Grafo de Conocimiento Neo4j + Soporte ORCID (Spotlight / Command Palette)
 */

import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Search,
  X,
  Users,
  Building2,
  ExternalLink,
  Loader2,
  ChevronRight,
  Award,
  Sparkles,
  Command,
  ArrowRight
} from 'lucide-react';
import { useAppStore, canViewAllResearchers } from '../../store/useAppStore.js';
import { apiClient } from '../../api/client.js';

export function GlobalSearchModal({ isOpen, onClose }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filterType, setFilterType] = useState('all'); // 'all' | 'Academic' | 'Institution'
  const [selectedIndex, setSelectedIndex] = useState(0);

  const inputRef = useRef(null);
  const resultsContainerRef = useRef(null);
  const debounceTimerRef = useRef(null);

  const setActiveTab = useAppStore((state) => state.setActiveTab);
  const setSelectedResearcher = useAppStore((state) => state.setSelectedResearcher);
  const setSelectedInstitution = useAppStore((state) => state.setSelectedInstitution);
  const setSelectedDependency = useAppStore((state) => state.setSelectedDependency);
  const setSelectedSubdependency = useAppStore((state) => state.setSelectedSubdependency);
  const userSession = useAppStore((state) => state.userSession);
  const setNotification = useAppStore((state) => state.setNotification);

  // Auto-focus al abrir
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      }, 50);
      setSelectedIndex(0);
    } else {
      setQuery('');
      setResults([]);
      setFilterType('all');
    }
  }, [isOpen]);

  // Consulta reactiva con debounce de 220ms
  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed || trimmed.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    setLoading(true);
    debounceTimerRef.current = setTimeout(async () => {
      try {
        const data = await apiClient.searchGlobal(trimmed, 25);
        setResults(data.results || []);
        setSelectedIndex(0);
      } catch (err) {
        console.error('Error en búsqueda global:', err);
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 220);

    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [query]);

  // Filtrado de resultados según la píldora activa
  const filteredResults = useMemo(() => {
    if (filterType === 'all') return results;
    return results.filter((r) => r.type === filterType);
  }, [results, filterType]);

  // Navegación con teclado
  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (filteredResults.length === 0 ? 0 : (prev + 1) % filteredResults.length));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (filteredResults.length === 0 ? 0 : (prev - 1 + filteredResults.length) % filteredResults.length));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filteredResults[selectedIndex]) {
        handleSelect(filteredResults[selectedIndex]);
      }
    }
  };

  // Scroll automático para mantener el ítem seleccionado visible
  useEffect(() => {
    if (resultsContainerRef.current) {
      const activeEl = resultsContainerRef.current.querySelector(`[data-index="${selectedIndex}"]`);
      if (activeEl) {
        activeEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }, [selectedIndex]);

  // Selección y enrutamiento inteligente
  const handleSelect = (item) => {
    if (!item) return;

    if (item.type === 'Academic') {
      const canSeeAll = canViewAllResearchers(userSession);
      const isSelf = Boolean(
        userSession?.isAuthenticated && (
          (userSession.orcid && item.orcid && userSession.orcid === item.orcid) ||
          (userSession.name && item.name && userSession.name.trim().toLowerCase() === item.name.trim().toLowerCase())
        )
      );

      if (!canSeeAll && !isSelf) {
        setNotification({
          type: 'warning',
          message: 'El perfil es exclusivo para el usuario logeado y solo puede ver su perfil.'
        });
        onClose();
        return;
      }

      // 1. Sincronizar jerarquía si los padres están disponibles
      const parents = item.parents || [];
      if (parents.length > 0) {
        setSelectedInstitution(parents[0] || '');
        setSelectedDependency(parents[1] || '');
        setSelectedSubdependency(parents[2] || '');
      }

      // 2. Establecer investigador seleccionado
      setSelectedResearcher(item.name, item.orcid || '');

      // 3. Navegar al perfil de investigadores
      setActiveTab('researchers');
      onClose();
    } else {
      // Entidad Institucional
      const labels = item.labels || [];
      const parents = item.parents || [];

      if (labels.includes('Institution')) {
        setSelectedInstitution(item.name);
        setSelectedDependency('');
        setSelectedSubdependency('');
      } else if (labels.includes('Dependency')) {
        setSelectedInstitution(parents[0] || 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)');
        setSelectedDependency(item.name);
        setSelectedSubdependency('');
      } else if (labels.includes('Subdependency')) {
        setSelectedInstitution(parents[0] || 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)');
        setSelectedDependency(parents[1] || '');
        setSelectedSubdependency(item.name);
      } else {
        // Fallback genérico
        if (parents.length > 0) {
          setSelectedInstitution(parents[0]);
          setSelectedDependency(parents[1] || item.name);
          setSelectedSubdependency(parents[2] || '');
        } else {
          setSelectedInstitution(item.name);
        }
      }

      // Navegar a Panorama Institucional
      setActiveTab('panorama');
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="global-search-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="global-search-container"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Barra de entrada */}
        <div className="global-search-input-wrapper">
          <Search className="search-icon-left" size={20} />
          <input
            ref={inputRef}
            type="text"
            className="global-search-input"
            placeholder="Buscar investigadores, facultades, institutos u ORCID..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {loading && <Loader2 className="search-spinner" size={18} />}
          {query && !loading && (
            <button
              type="button"
              className="search-clear-btn"
              onClick={() => {
                setQuery('');
                inputRef.current?.focus();
              }}
              title="Limpiar búsqueda"
            >
              <X size={16} />
            </button>
          )}
          <span className="search-esc-badge" onClick={onClose}>ESC</span>
        </div>

        {/* Píldoras de Filtro Rápido */}
        {results.length > 0 && (
          <div className="global-search-filters">
            <button
              className={`search-filter-pill ${filterType === 'all' ? 'active' : ''}`}
              onClick={() => { setFilterType('all'); setSelectedIndex(0); }}
            >
              Todos ({results.length})
            </button>
            <button
              className={`search-filter-pill ${filterType === 'Academic' ? 'active' : ''}`}
              onClick={() => { setFilterType('Academic'); setSelectedIndex(0); }}
            >
              <Users size={13} /> Investigadores ({results.filter(r => r.type === 'Academic').length})
            </button>
            <button
              className={`search-filter-pill ${filterType === 'Institution' ? 'active' : ''}`}
              onClick={() => { setFilterType('Institution'); setSelectedIndex(0); }}
            >
              <Building2 size={13} /> Instituciones / Dependencias ({results.filter(r => r.type === 'Institution').length})
            </button>
          </div>
        )}

        {/* Contenedor de Resultados */}
        <div className="global-search-results-list" ref={resultsContainerRef}>
          {/* Estado inicial / sugerencias */}
          {!query && (
            <div className="search-empty-state">
              <div className="empty-state-icon">
                <Sparkles size={28} />
              </div>
              <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.98rem', fontWeight: 600 }}>
                Búsqueda Global en el Grafo Nacional de Conocimiento
              </h4>
              <p style={{ margin: '0 0 1rem', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                Escribe al menos 2 letras o ingresa un identificador ORCID para explorar:
              </p>
              <div className="search-hints-grid">
                <div className="search-hint-card" onClick={() => setQuery('Pardo Cemo')}>
                  <Users size={15} style={{ color: '#0284c7' }} />
                  <span>Ej. "Pardo Cemo, Annie"</span>
                </div>
                <div className="search-hint-card" onClick={() => setQuery('0000-0003-2168-9073')}>
                  <Command size={15} style={{ color: '#10b981' }} />
                  <span>Ej. "0000-0003-2168-9073" (ORCID)</span>
                </div>
                <div className="search-hint-card" onClick={() => setQuery('Facultad de Ciencias')}>
                  <Building2 size={15} style={{ color: '#8b5cf6' }} />
                  <span>Ej. "Facultad de Ciencias"</span>
                </div>
                <div className="search-hint-card" onClick={() => setQuery('Biotecnologia')}>
                  <Sparkles size={15} style={{ color: '#f59e0b' }} />
                  <span>Ej. "Instituto de Biotecnología"</span>
                </div>
              </div>
            </div>
          )}

          {/* Estado de sin resultados */}
          {query.trim().length >= 2 && !loading && filteredResults.length === 0 && (
            <div className="search-empty-state">
              <p style={{ margin: '0.5rem 0', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                No se encontraron coincidencias en el grafo para "<strong>{query}</strong>".
              </p>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-dim)' }}>
                Prueba buscando únicamente por el apellido principal o verifica la ortografía.
              </p>
            </div>
          )}

          {/* Listado de ítems encontrados */}
          {filteredResults.map((item, idx) => {
            const isSelected = idx === selectedIndex;
            const isAcademic = item.type === 'Academic';
            const parents = item.parents || [];

            return (
              <div
                key={`${item.type}_${item.id || item.name}_${idx}`}
                data-index={idx}
                className={`search-result-item ${isSelected ? 'selected' : ''}`}
                onClick={() => handleSelect(item)}
                onMouseEnter={() => setSelectedIndex(idx)}
              >
                {/* Icono de tipo */}
                <div className={`result-type-icon ${isAcademic ? 'icon-academic' : 'icon-institution'}`}>
                  {isAcademic ? <Users size={18} /> : <Building2 size={18} />}
                </div>

                {/* Contenido principal */}
                <div className="result-info">
                  <div className="result-title-row">
                    <span className="result-name">{item.name}</span>

                    {/* Badges para Investigador */}
                    {isAcademic && item.snii_level && (
                      <span className="snii-badge-pill" title={`Nivel SNII: ${item.snii_level}`}>
                        <Award size={11} /> SNII {item.snii_level === 'C' ? 'Candidato' : item.snii_level === 'E' ? 'Emérito' : item.snii_level}
                      </span>
                    )}

                    {isAcademic && item.orcid && (
                      <span className="orcid-badge-pill" title={`ORCID: ${item.orcid}`}>
                        <span className="orcid-dot" /> {item.orcid}
                      </span>
                    )}

                    {/* Badges para Institución / Dependencia */}
                    {!isAcademic && item.labels && (
                      <span className="entity-type-badge">
                        {item.labels.includes('Subdependency')
                          ? 'Subdependencia'
                          : item.labels.includes('Dependency')
                            ? 'Dependencia'
                            : 'Institución'}
                      </span>
                    )}
                  </div>

                  {/* Ruta de Adscripción Jerárquica */}
                  {parents.length > 0 && (
                    <div className="result-breadcrumbs">
                      {parents.map((p, pIdx) => (
                        <React.Fragment key={pIdx}>
                          {pIdx > 0 && <ChevronRight size={11} className="breadcrumb-arrow" />}
                          <span className="breadcrumb-step">{p}</span>
                        </React.Fragment>
                      ))}
                    </div>
                  )}
                </div>

                {/* Acción al extremo derecho */}
                <div className="result-action-hint">
                  {isSelected ? (
                    <span className="action-hint-active">
                      Abrir <ArrowRight size={13} />
                    </span>
                  ) : (
                    <span className="action-hint-subtle">
                      {isAcademic ? 'Ver Perfil' : 'Ver Panorama'}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Pie de ayuda del modal */}
        <div className="global-search-footer">
          <div className="footer-keys">
            <span><kbd>↑</kbd> <kbd>↓</kbd> Navegar</span>
            <span><kbd>↵ Enter</kbd> Seleccionar</span>
            <span><kbd>Esc</kbd> Cerrar</span>
          </div>
          <div className="footer-source">
            Grafo Nacional de Conocimiento (Neo4j) · Info TlachIA
          </div>
        </div>
      </div>
    </div>
  );
}

export default GlobalSearchModal;
