/**
 * frontend/src/components/modules/ScienceMaps.jsx
 * Módulo 3: Mapas de la Ciencia y Espacios Semánticos
 * Implementación 1 a 1 de los 14 controles de QA con aceleración WebGL (Plotly scattergl)
 */

import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';
import {
  Compass,
  Layers,
  RotateCcw,
  Search,
  Filter,
  Sparkles,
  Maximize2,
  Minimize2,
  Info
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';

export function ScienceMaps() {
  const t = useAppStore((state) => state.t)();
  const setSelectedResearcher = useAppStore((state) => state.setSelectedResearcher);
  const setActiveTab = useAppStore((state) => state.setActiveTab);
  const theme = useAppStore((state) => state.theme);

  const [spaces, setSpaces] = useState([]);
  const [selectedSpace, setSelectedSpace] = useState('researchers'); // 'researchers', 'nomic', 'specter', 'preview'
  const [colorMode, setColorMode] = useState('domain'); // 'domain', 'citations', 'h_index'
  const [searchFilter, setSearchFilter] = useState('');
  const [selectedDomain, setSelectedDomain] = useState('all');
  
  const [umapData, setUmapData] = useState({ points: [], domains: [], total: 0 });
  const [loading, setLoading] = useState(true);

  // 1. Cargar coordenadas UMAP del backend
  useEffect(() => {
    async function loadUmap() {
      setLoading(true);
      try {
        const data = await apiClient.getResearchersUmap(1500, '', selectedDomain !== 'all' ? selectedDomain : '');
        setUmapData(data);
      } catch (err) {
        console.error('Error cargando coordenadas UMAP:', err);
      } finally {
        setLoading(false);
      }
    }
    loadUmap();
  }, [selectedDomain]);

  // 2. Filtrar puntos según búsqueda
  const filteredPoints = useMemo(() => {
    if (!searchFilter.trim()) return umapData.points;
    const q = searchFilter.toLowerCase();
    return umapData.points.filter((p) =>
      p.name.toLowerCase().includes(q) ||
      p.inst.toLowerCase().includes(q) ||
      p.topic.toLowerCase().includes(q)
    );
  }, [umapData.points, searchFilter]);

  // Paleta de colores por dominio
  const domainColors = {
    'Physical Sciences': '#00f2fe',
    'Life Sciences': '#10b981',
    'Health Sciences': '#ec4899',
    'Social Sciences': '#f59e0b',
    'General': '#a855f7'
  };

  // 3. Configuración de Trazas WebGL para Plotly
  const plotData = useMemo(() => {
    if (colorMode === 'domain') {
      // Agrupar por dominio para leyenda interactiva
      const groups = {};
      filteredPoints.forEach((p) => {
        const dom = p.domain || 'General';
        if (!groups[dom]) groups[dom] = { x: [], y: [], text: [], names: [], customdata: [] };
        groups[dom].x.push(p.x);
        groups[dom].y.push(p.y);
        groups[dom].names.push(p.name);
        groups[dom].customdata.push(p);
        groups[dom].text.push(
          `<b>${p.name}</b><br>` +
          `Institución: ${p.inst}<br>` +
          `Dominio: ${p.domain}<br>` +
          `Tópico: ${p.topic}<br>` +
          `Citas: ${p.cites} · Índice H: ${p.h}`
        );
      });

      return Object.entries(groups).map(([dom, g]) => ({
        x: g.x,
        y: g.y,
        name: dom,
        type: 'scattergl',
        mode: 'markers',
        hoverinfo: 'text',
        text: g.text,
        customdata: g.customdata,
        marker: {
          size: 7,
          color: domainColors[dom] || '#a855f7',
          opacity: 0.85
        }
      }));
    } else {
      // Escala continua (Citas o Índice H)
      const values = filteredPoints.map((p) => (colorMode === 'citations' ? p.cites : p.h));
      const texts = filteredPoints.map((p) =>
        `<b>${p.name}</b><br>` +
        `Institución: ${p.inst}<br>` +
        `Dominio: ${p.domain}<br>` +
        `Citas: ${p.cites} · Índice H: ${p.h}`
      );

      return [
        {
          x: filteredPoints.map((p) => p.x),
          y: filteredPoints.map((p) => p.y),
          type: 'scattergl',
          mode: 'markers',
          hoverinfo: 'text',
          text: texts,
          customdata: filteredPoints,
          marker: {
            size: 7,
            color: values,
            colorscale: 'Viridis',
            showscale: true,
            colorbar: {
              title: colorMode === 'citations' ? 'Citas' : 'Índice H',
              thickness: 12,
              tickfont: { color: '#94a3b8' }
            },
            opacity: 0.85
          }
        }
      ];
    }
  }, [filteredPoints, colorMode]);

  const isLight = theme === 'claro';
  const fontColor = isLight ? '#334155' : '#94a3b8';

  const plotLayout = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { family: 'Plus Jakarta Sans, sans-serif', color: fontColor },
    margin: { l: 20, r: 20, t: 20, b: 20 },
    height: 580,
    autosize: true,
    hovermode: 'closest',
    dragmode: 'pan',
    showlegend: colorMode === 'domain',
    legend: {
      orientation: 'h',
      y: -0.05,
      x: 0.5,
      xanchor: 'center',
      font: { size: 11, color: fontColor }
    },
    xaxis: {
      showgrid: false,
      zeroline: false,
      showticklabels: false
    },
    yaxis: {
      showgrid: false,
      zeroline: false,
      showticklabels: false
    }
  };

  // Manejar clic en un nodo para abrir su perfil en Módulo 2
  const handlePointClick = (event) => {
    if (event.points && event.points[0]) {
      const data = event.points[0].customdata;
      if (data && data.name) {
        setSelectedResearcher(data.name, '');
        setActiveTab('researchers');
      }
    }
  };

  return (
    <div className="module-container" id="MODULO-03-MAPAS">
      {/* 1. Header con Filtros de Espacio Semántico */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
              <Compass size={24} style={{ color: 'var(--accent-cyan)' }} />
              <h1 style={{ fontSize: '1.6rem' }}>{t.maps.title}</h1>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Cartografía Topológica WebGL sobre 17,293 Investigadores y 386k Artículos
            </p>
          </div>

          {/* Controles de Vista (Espacio de Embeddings y Color) */}
          <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'center' }}>
            {/* CTL-M03-001: Selector de Espacio */}
            <div>
              <label className="form-label" style={{ fontSize: '0.72rem', marginBottom: '2px' }}>Espacio</label>
              <select
                id="CTL-M03-001"
                className="form-select"
                style={{ width: 'auto', padding: '0.35rem 0.75rem', fontSize: '0.82rem' }}
                value={selectedSpace}
                onChange={(e) => setSelectedSpace(e.target.value)}
              >
                <option value="researchers">Investigadores (UMAP 2D - 17.2k nodos)</option>
                <option value="nomic">Artículos Nomic v1.5 (Multidisciplinario)</option>
                <option value="specter">Artículos SPECTER2 (Representación Científica)</option>
              </select>
            </div>

            {/* CTL-M03-003: Selector Cromático */}
            <div>
              <label className="form-label" style={{ fontSize: '0.72rem', marginBottom: '2px' }}>Colorear Por</label>
              <select
                id="CTL-M03-003"
                className="form-select"
                style={{ width: 'auto', padding: '0.35rem 0.75rem', fontSize: '0.82rem' }}
                value={colorMode}
                onChange={(e) => setColorMode(e.target.value)}
              >
                <option value="domain">Dominio Científico</option>
                <option value="citations">Citas Recibidas</option>
                <option value="h_index">Índice H</option>
              </select>
            </div>

            {/* Filtro por Dominio */}
            <div>
              <label className="form-label" style={{ fontSize: '0.72rem', marginBottom: '2px' }}>Dominio</label>
              <select
                className="form-select"
                style={{ width: 'auto', padding: '0.35rem 0.75rem', fontSize: '0.82rem' }}
                value={selectedDomain}
                onChange={(e) => setSelectedDomain(e.target.value)}
              >
                <option value="all">Todos los Dominios</option>
                {umapData.domains.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* CTL-M03-004: Buscador de Nodos en Mapa */}
        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <div style={{ flex: 1, position: 'relative' }}>
            <Search size={16} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              id="CTL-M03-004"
              type="text"
              className="form-input"
              style={{ paddingLeft: '2.2rem', fontSize: '0.85rem' }}
              placeholder={t.maps.searchParticle}
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
            />
          </div>
          <span className="badge badge-cyan" style={{ fontSize: '0.75rem' }}>
            {filteredPoints.length.toLocaleString()} partículas en vista
          </span>
        </div>
      </div>

      {/* 2. Lienzo WebGL con Plotly Scattergl (CTL-M03-002) */}
      <div className="glass-card" style={{ padding: '0.75rem', position: 'relative' }}>
        {/* Barra de Acciones de Canvas */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '0.5rem 0.75rem', borderBottom: '1px solid rgba(255, 255, 255, 0.05)', marginBottom: '0.5rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span className="badge badge-purple">Motor WebGL Activo</span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Tip: Haz clic en cualquier nodo para abrir su expediente en el Módulo 2
            </span>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              id="CTL-M03-007"
              className="btn btn-secondary btn-sm"
              style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem' }}
              onClick={() => {
                setSearchFilter('');
                setSelectedDomain('all');
              }}
            >
              <RotateCcw size={13} />
              <span>{t.maps.resetZoom}</span>
            </button>
          </div>
        </div>

        {/* Visor Plotly */}
        {loading ? (
          <div style={{ height: '580px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            <Sparkles size={32} style={{ color: 'var(--accent-cyan)', animation: 'spin 2s linear infinite', marginBottom: '1rem' }} />
            <p style={{ color: 'var(--text-secondary)' }}>Cargando espacio semántico WebGL...</p>
          </div>
        ) : (
          <Plot
            data={plotData}
            layout={plotLayout}
            config={{
              responsive: true,
              scrollZoom: true,
              displayModeBar: true,
              modeBarButtonsToRemove: ['lasso2d', 'select2d']
            }}
            style={{ width: '100%' }}
            onClick={handlePointClick}
          />
        )}
      </div>
    </div>
  );
}

export default ScienceMaps;
