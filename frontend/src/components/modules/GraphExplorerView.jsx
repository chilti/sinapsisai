/**
 * frontend/src/components/modules/GraphExplorerView.jsx
 * Módulo de Redes de Conocimiento y Capacidades Científicas (SECIHTI Ejes 1 y 2)
 * Renderizado interactivo WebGL 2D/3D con Reagraph + Resiliencia SVG 2D para entornos sin GPU.
 */

import React, { useState, useEffect, useRef, useMemo, Component } from 'react';
import { GraphCanvas, darkTheme, lightTheme } from 'reagraph';
import {
  Network,
  Sparkles,
  Layers,
  Maximize2,
  Minimize2,
  Search,
  X,
  ExternalLink,
  Info,
  ShieldCheck,
  AlertCircle,
  RefreshCw,
  Zap,
  Table as TableIcon
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import { apiClient } from '../../api/client.js';
import './GraphExplorerView.css';

// Detección de soporte nativo WebGL
function checkWebGLSupport() {
  if (typeof window === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    return Boolean(gl && gl instanceof WebGLRenderingContext);
  } catch (e) {
    return false;
  }
}

// ErrorBoundary local para aislar fallos de WebGL/Three.js y ofrecer fallback automático
class WebGLBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    console.warn('Fallo en contexto WebGL de Reagraph:', error, info);
  }
  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

// Visualizador 2D SVG Alternativo (Zero-WebGL)
function SvgGraphFallback({ nodes, edges, onNodeClick, onEdgeClick, selectedNode, theme }) {
  const isDark = theme === 'oscuro' || theme === 'navy';
  const width = 900;
  const height = 550;
  const centerX = width / 2;
  const centerY = height / 2;

  // Distribuir nodos en círculos concéntricos según orden
  const positionedNodes = useMemo(() => {
    if (!nodes || nodes.length === 0) return [];
    const count = nodes.length;
    return nodes.map((node, i) => {
      // Distribución en espiral de Fermat para espaciado armónico
      const angle = i * 2.399963; // Ángulo áureo
      const radius = Math.min(centerX - 60, Math.sqrt(i + 1) * 38);
      const x = centerX + radius * Math.cos(angle);
      const y = centerY + radius * Math.sin(angle);
      return { ...node, x, y };
    });
  }, [nodes, centerX, centerY]);

  const nodeMap = useMemo(() => {
    const map = new Map();
    positionedNodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [positionedNodes]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', overflow: 'hidden' }}>
      <div style={{
        position: 'absolute',
        top: 10,
        left: 10,
        background: 'rgba(245, 158, 11, 0.15)',
        border: '1px solid rgba(245, 158, 11, 0.4)',
        borderRadius: 8,
        padding: '0.4rem 0.8rem',
        fontSize: '0.78rem',
        color: '#f59e0b',
        zIndex: 10,
        display: 'flex',
        alignItems: 'center',
        gap: '0.4rem'
      }}>
        <Info size={14} />
        <span>Modo Resiliente 2D SVG Activo (Aceleración WebGL no disponible en este entorno)</span>
      </div>

      <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} style={{ background: 'transparent' }}>
        {/* Aristas finas coloreadas según intensidad de colaboración */}
        <g strokeWidth="1.2">
          {edges.slice(0, 200).map((edge) => {
            const s = nodeMap.get(edge.source);
            const t = nodeMap.get(edge.target);
            if (!s || !t) return null;
            return (
              <line
                key={edge.id}
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke={edge.fill || (isDark ? 'rgba(148, 163, 184, 0.4)' : 'rgba(100, 116, 139, 0.4)')}
                strokeDasharray={edge.dashed ? '4,4' : undefined}
                style={{ cursor: 'pointer' }}
                onClick={() => onEdgeClick && onEdgeClick(edge)}
              />
            );
          })}
        </g>

        {/* Nodos */}
        <g>
          {positionedNodes.map((n) => {
            const isSelected = selectedNode?.id === n.id;
            const r = isSelected ? 12 : 8;
            return (
              <g
                key={n.id}
                transform={`translate(${n.x}, ${n.y})`}
                style={{ cursor: 'pointer' }}
                onClick={() => onNodeClick && onNodeClick(n)}
              >
                <circle
                  r={r}
                  fill={n.fill || '#6366f1'}
                  stroke={isSelected ? '#ffffff' : 'rgba(255,255,255,0.4)'}
                  strokeWidth={isSelected ? 3 : 1.5}
                />
                <text
                  x={12}
                  y={4}
                  fontSize="10"
                  fill={isDark ? '#e2e8f0' : '#1e293b'}
                  style={{ pointerEvents: 'none', userSelect: 'none' }}
                >
                  {n.label}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

const SNII_AREAS = [
  { id: '', label: 'Todas las Áreas (Mapa Nacional)' },
  { id: 'I. FISICO-MATEMATICAS Y CIENCIAS DE LA TIERRA', label: 'I. Fís-Mat y Tierra' },
  { id: 'II. BIOLOGIA Y QUIMICA', label: 'II. Biología y Química' },
  { id: 'III. MEDICINA Y CIENCIAS DE LA SALUD', label: 'III. Medicina y Salud' },
  { id: 'IV. CIENCIAS DE LA CONDUCTA Y LA EDUCACION', label: 'IV. Conducta y Educación' },
  { id: 'V. HUMANIDADES', label: 'V. Humanidades' },
  { id: 'VI. CIENCIAS SOCIALES', label: 'VI. Ciencias Sociales' },
  { id: 'VII. CIENCIAS DE AGRICULTURA, AGROPECUARIAS, FORESTALES Y DE ECOSISTEMAS', label: 'VII. Agro y Ecosistemas' },
  { id: 'VIII. INGENIERIAS Y DESARROLLO TECNOLOGICO', label: 'VIII. Ingenierías y Tec.' },
  { id: 'IX. INTERDISCIPLINARIA', label: 'IX. Interdisciplinaria' }
];

export function GraphExplorerView() {
  const theme = useAppStore((state) => state.theme);
  const setActiveTab = useAppStore((state) => state.setActiveTab);
  const setSelectedResearcher = useAppStore((state) => state.setSelectedResearcher);
  const setSelectedInstitution = useAppStore((state) => state.setSelectedInstitution);

  const [hasWebGL, setHasWebGL] = useState(true);

  useEffect(() => {
    setHasWebGL(checkWebGLSupport());
  }, []);

  // Estados de Configuración de Vista
  const [mode, setMode] = useState('presets'); // 'presets' | 'custom'
  const [presets, setPresets] = useState([]);
  const [activePresetId, setActivePresetId] = useState('cpis_collab');

  // Parámetros de Consulta
  const [nodeLimit, setNodeLimit] = useState(80);
  const [threshold, setThreshold] = useState(5);
  const [areaFilter, setAreaFilter] = useState('');
  const [is3D, setIs3D] = useState(false);
  const [layoutType, setLayoutType] = useState('forceDirected2d');
  const [labelType, setLabelType] = useState('auto');

  // Datos del Grafo
  const [graphData, setGraphData] = useState({ nodes: [], edges: [], stats: {} });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Estados de Interacción
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedNodeDetails, setSelectedNodeDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [selectedEdge, setSelectedEdge] = useState(null);

  // Modo Libre (Custom Query)
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [selectedEntities, setSelectedEntities] = useState([]);

  // Control de Física WebGL Dinámica (Convergencia rápida y congelamiento a 60 FPS)
  const [isPhysicsActive, setIsPhysicsActive] = useState(true);
  const physicsTimerRef = useRef(null);

  const triggerPhysicsSettle = (durationMs = 2200) => {
    setIsPhysicsActive(true);
    if (physicsTimerRef.current) clearTimeout(physicsTimerRef.current);
    physicsTimerRef.current = setTimeout(() => {
      setIsPhysicsActive(false);
    }, durationMs);
  };

  const glConfig = useMemo(() => ({
    powerPreference: 'high-performance',
    antialias: false,
    preserveDrawingBuffer: false,
    stencil: false,
    depth: true
  }), []);

  const graphRef = useRef(null);

  // 1. Cargar catálogo de presets al montar
  useEffect(() => {
    apiClient.getGraphPresets()
      .then((data) => {
        setPresets(data);
        if (data.length > 0 && !activePresetId) {
          setActivePresetId(data[0].id);
        }
      })
      .catch((err) => {
        console.error('Error cargando presets de grafo:', err);
      });
  }, []);

  // 2. Cargar datos del preset activo
  const loadPresetData = (presetId, limitVal, threshVal, areaVal = null) => {
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    setSelectedNodeDetails(null);
    setSelectedEdge(null);

    apiClient.getGraphPreset(presetId, limitVal, threshVal, areaVal)
      .then((res) => {
        setGraphData({
          nodes: res.nodes || [],
          edges: res.edges || [],
          stats: res.stats || {}
        });
        setLoading(false);
        triggerPhysicsSettle(2200);
      })
      .catch((err) => {
        console.error('Error obteniendo subgrafo del preset:', err);
        setError('No se pudo cargar la red de conocimiento para este escenario.');
        setLoading(false);
      });
  };

  useEffect(() => {
    if (mode === 'presets' && activePresetId) {
      const activePresetObj = presets.find((p) => p.id === activePresetId);
      const isLandscape = activePresetId === 'snii_topic_landscape';
      const defaultThresh = activePresetObj?.controls?.default_threshold || (isLandscape ? 10 : 1);
      const defaultLim = activePresetObj?.default_limit || (isLandscape ? 5000 : 80);

      setThreshold(defaultThresh);
      setNodeLimit(defaultLim);
      setAreaFilter('');

      if (isLandscape && !is3D) {
        setLayoutType('forceatlas2');
      } else if (!isLandscape && !is3D) {
        setLayoutType('forceDirected2d');
      }

      loadPresetData(activePresetId, defaultLim, defaultThresh, null);
    }
  }, [mode, activePresetId]);

  const handleToggle3D = (enable3d) => {
    setIs3D(enable3d);
    if (enable3d) {
      setLayoutType('forceDirected3d');
    } else {
      setLayoutType('forceDirected2d');
    }
  };

  // Búsqueda de entidades con autocompletado en Modo Libre
  useEffect(() => {
    if (!searchTerm || searchTerm.trim().length < 2) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(() => {
      apiClient.searchGraphEntities(searchTerm.trim(), 12)
        .then((res) => setSearchResults(res || []))
        .catch(() => setSearchResults([]));
    }, 280);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  const handleExecuteCustomSubgraph = () => {
    if (selectedEntities.length === 0) return;
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    setSelectedNodeDetails(null);
    setSelectedEdge(null);

    const query = {
      entity_ids: selectedEntities.map((e) => e.id),
      min_weight: threshold,
      limit: nodeLimit
    };

    apiClient.generateSubgraph(query)
      .then((res) => {
        setGraphData({
          nodes: res.nodes || [],
          edges: res.edges || [],
          stats: res.stats || {}
        });
        setLoading(false);
        triggerPhysicsSettle(2200);
      })
      .catch((err) => {
        console.error('Error generando subgrafo personalizado:', err);
        setError('Error al generar la red con las entidades seleccionadas.');
        setLoading(false);
      });
  };

  const handleNodeClick = (node) => {
    setSelectedNode(node);
    setSelectedEdge(null);

    // Detección directa instantánea para tópicos y áreas del SNII
    if (node.data?.type === 'topic') {
      const breakdown = (node.data.areas_breakdown || []);
      const breakdownText = breakdown.map(b => `${b.area.split('.')[0]}: ${b.researchers} inv.`).join(' · ');

      setSelectedNodeDetails({
        type: 'topic',
        id: node.id,
        title: node.data.full_name || node.label,
        subtitle: `Tópico OpenAlex · ${node.data.total_researchers || node.subLabel} inv. SNII`,
        properties: {
          'Tópico': node.data.full_name || node.label,
          'Total Investigadores SNII': `${node.data.total_researchers || 0} investigadoras e investigadores`,
          'Área Principal Dominante': node.data.primary_area || 'Multidisciplinaria',
          'Presencia por Áreas': breakdownText || 'Información de distribución consolidada'
        }
      });
      return;
    }

    if (node.data?.type === 'snii_area') {
      setSelectedNodeDetails({
        type: 'snii_area',
        id: node.id,
        title: node.data.full_name || node.label,
        subtitle: 'Gran Área del Conocimiento del SNII',
        properties: {
          'Área Científica': node.data.full_name || node.label,
          'Investigadores Vinculados': `${node.data.total_researchers?.toLocaleString() || 0} vínculos temáticos`,
          'Descripción': node.data.description || 'Nodo central de la constelación temática nacional'
        }
      });
      return;
    }

    setLoadingDetails(true);
    apiClient.getNodeDetails(node.id)
      .then((details) => {
        setSelectedNodeDetails(details);
        setLoadingDetails(false);
      })
      .catch(() => {
        setSelectedNodeDetails({
          type: 'generic',
          id: node.id,
          title: node.label,
          subtitle: node.subLabel || 'Entidad',
          properties: node.data || {}
        });
        setLoadingDetails(false);
      });
  };

  const handleEdgeClick = (edge) => {
    setSelectedEdge(edge);
    setSelectedNode(null);
    setSelectedNodeDetails(null);
  };

  const handleNavigateEntity = (details) => {
    if (!details) return;
    if (details.type === 'person') {
      const orcid = details.properties?.['ORCID'];
      const name = details.title;
      if (setSelectedResearcher) {
        setSelectedResearcher(name, orcid !== 'No registrado' ? orcid : null);
      }
      setActiveTab('researchers');
    } else if (details.type === 'institution' || details.type === 'cpi') {
      const instName = details.title;
      if (setSelectedInstitution) {
        setSelectedInstitution(instName);
      }
      setActiveTab('panorama');
    }
  };

  const reagraphTheme = useMemo(() => {
    const isDark = theme === 'oscuro' || theme === 'navy';
    const base = isDark ? darkTheme : lightTheme;
    const isLandscape = activePresetId === 'snii_topic_landscape';
    return {
      ...base,
      canvas: {
        ...base.canvas,
        background: 'transparent'
      },
      node: {
        ...base.node,
        inactiveOpacity: 0.2
      },
      edge: {
        ...base.edge,
        inactiveOpacity: isLandscape ? 0.05 : 0.12,
        activeOpacity: 0.95,
        opacity: isLandscape ? 0.22 : 0.35,
        size: 1
      }
    };
  }, [theme, activePresetId]);

  const nodeLegendItems = useMemo(() => {
    if (activePresetId === 'cpis_collab') {
      return [
        { label: 'Centro Público de Inv. (CPI SECIHTI)', color: '#f59e0b' },
        { label: 'Universidad / Instituto Externo', color: '#38bdf8' }
      ];
    } else if (activePresetId === 'regional_flows') {
      return [
        { label: 'Polo Científico Regional', color: '#a855f7' },
        { label: 'Entidad Federativa', color: '#c084fc' }
      ];
    } else if (activePresetId === 'sdg_capacities') {
      return [
        { label: 'CPI SECIHTI', color: '#f59e0b' },
        { label: 'Objetivo de Desarrollo Sostenible (ODS)', color: '#10b981' }
      ];
    } else if (activePresetId === 'snii_topic_landscape') {
      return [
        { label: 'Área Científica del SNII (Nodo Central)', color: '#6366f1' },
        { label: 'Tópico OpenAlex (Satélite)', color: '#2563eb' }
      ];
    } else if (activePresetId === 'evaluator_distance') {
      return [
        { label: 'Investigador Evaluado', color: '#3b82f6' },
        { label: 'Evaluador Idóneo (Sin conflicto, Dist. ≥ 2)', color: '#10b981' },
        { label: 'Conflicto Directo (Coautor directo)', color: '#ef4444' }
      ];
    }
    return [
      { label: 'CPI SECIHTI', color: '#f59e0b' },
      { label: 'Universidad / Institución', color: '#38bdf8' },
      { label: 'Investigadora o Investigador', color: '#818cf8' },
      { label: 'Objetivo Sostenible (ODS)', color: '#10b981' }
    ];
  }, [activePresetId]);

  const gradientScale = useMemo(() => {
    const range = graphData.stats?.edge_range || {};
    const minVal = range.min ?? threshold ?? 1;
    const maxVal = range.max ?? 100;

    if (activePresetId === 'snii_topic_landscape') {
      return {
        title: 'Investigadores SNII vinculados al Tópico',
        gradient: 'linear-gradient(to right, #94a3b8 0%, #38bdf8 33%, #6366f1 66%, #f59e0b 100%)',
        minLabel: `${minVal} inv.`,
        midLabel: `${Math.round((minVal + maxVal) / 2)} inv.`,
        maxLabel: `${maxVal} inv.`
      };
    } else if (activePresetId === 'sdg_capacities') {
      return {
        title: 'Aporte al ODS (Artículos Indexados)',
        gradient: 'linear-gradient(to right, #94a3b8 0%, #38bdf8 33%, #10b981 66%, #059669 100%)',
        minLabel: `${minVal} arts.`,
        midLabel: `${Math.round((minVal + maxVal) / 2)} arts.`,
        maxLabel: `${maxVal} arts.`
      };
    } else if (activePresetId === 'evaluator_distance') {
      return null;
    }
    return {
      title: 'Intensidad de Colaboración (Publicaciones)',
      gradient: 'linear-gradient(to right, #94a3b8 0%, #38bdf8 25%, #818cf8 50%, #d946ef 75%, #f59e0b 100%)',
      minLabel: `${minVal} pub.`,
      midLabel: `${Math.round(Math.sqrt(minVal * maxVal))} pub.`,
      maxLabel: `${maxVal} pub.`
    };
  }, [activePresetId, graphData.stats, threshold]);

  return (
    <div className="graph-explorer-root">
      {/* 1. Encabezado y Selector de Modo */}
      <header className="graph-header">
        <div className="graph-title-row">
          <div className="graph-title-group">
            <div className="graph-title-icon-box">
              <Network size={24} />
            </div>
            <div className="graph-title-text">
              <h1>
                Redes de Conocimiento y Capacidades
                <span className="secihti-badge">SECIHTI Ejes 1 y 2</span>
              </h1>
              <p className="graph-subtitle">
                Cartografía interactiva del grafo de conocimiento Neo4j para articular el Sistema Nacional de CTI, descentralización interestatal y evaluación por pares.
              </p>
            </div>
          </div>

          <div className="mode-toggle-group">
            <button
              className={`mode-toggle-btn ${mode === 'presets' ? 'active' : ''}`}
              onClick={() => setMode('presets')}
            >
              <Sparkles size={16} />
              Demos Estratégicos
            </button>
            <button
              className={`mode-toggle-btn ${mode === 'custom' ? 'active' : ''}`}
              onClick={() => setMode('custom')}
            >
              <Layers size={16} />
              Explorador Libre
            </button>
          </div>
        </div>

        {/* 2. Grid de Presets SECIHTI */}
        {mode === 'presets' && (
          <div className="presets-grid">
            {presets.map((preset) => {
              const isActive = activePresetId === preset.id;
              return (
                <div
                  key={preset.id}
                  className={`preset-card ${isActive ? 'active' : ''}`}
                  onClick={() => setActivePresetId(preset.id)}
                >
                  <span className="preset-axis">{preset.axis}</span>
                  <h3 className="preset-title">{preset.title}</h3>
                  <p className="preset-desc">{preset.description}</p>
                </div>
              );
            })}
          </div>
        )}

        {/* 3. Panel de Búsqueda para Modo Libre */}
        {mode === 'custom' && (
          <div className="custom-query-panel">
            <div className="search-input-wrapper">
              <Search className="search-icon-inside" size={18} />
              <input
                type="text"
                className="entity-search-input"
                placeholder="Buscar investigadores SNII, instituciones o temas para tejer la red..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />

              {searchResults.length > 0 && (
                <div className="autocomplete-dropdown">
                  {searchResults.map((item) => (
                    <div
                      key={item.id}
                      className="autocomplete-item"
                      onClick={() => {
                        if (!selectedEntities.find((e) => e.id === item.id)) {
                          setSelectedEntities([...selectedEntities, item]);
                        }
                        setSearchTerm('');
                        setSearchResults([]);
                      }}
                    >
                      <span className="autocomplete-item-name">{item.label}</span>
                      <span className="autocomplete-badge">{item.badge}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {selectedEntities.length > 0 && (
              <div className="selected-entities-row">
                <span className="toolbar-label">Entidades focales:</span>
                {selectedEntities.map((ent) => (
                  <span key={ent.id} className="entity-chip">
                    {ent.name}
                    <button
                      className="entity-chip-remove"
                      onClick={() => setSelectedEntities(selectedEntities.filter((e) => e.id !== ent.id))}
                    >
                      <X size={14} />
                    </button>
                  </span>
                ))}
                <button
                  className="toolbar-button active"
                  style={{ marginLeft: 'auto' }}
                  onClick={handleExecuteCustomSubgraph}
                >
                  <Network size={15} />
                  Generar Red en Grafo
                </button>
              </div>
            )}
          </div>
        )}
      </header>

      {/* 4. Barra de Herramientas del Canvas */}
      <div className="canvas-toolbar">
        <div className="toolbar-group">
          {hasWebGL && (
            <>
              <button
                className={`toolbar-button ${!is3D ? 'active' : ''}`}
                onClick={() => handleToggle3D(false)}
                title="Proyección plana 2D"
              >
                2D
              </button>
              <button
                className={`toolbar-button ${is3D ? 'active' : ''}`}
                onClick={() => handleToggle3D(true)}
                title="Visualización espacial 3D inmersiva"
              >
                3D WebGL
              </button>
            </>
          )}

          {/* Selector de Layout */}
          {hasWebGL && (
            <>
              <span className="toolbar-label">Distribución:</span>
              <select
                className="toolbar-select"
                value={layoutType}
                onChange={(e) => setLayoutType(e.target.value)}
              >
                {!is3D && (
                  <>
                    <option value="forceDirected2d">Fuerzas Físicas (Force-Directed 2D)</option>
                    <option value="forceatlas2">ForceAtlas2 (Gephi - Anti-traslape)</option>
                    <option value="radialOut2d">Radial Concéntrico</option>
                    <option value="concentric2d">Concéntrico por Centralidad</option>
                    <option value="hierarchicalTd">Jerárquico (Árbol Vertical)</option>
                    <option value="circular2d">Circular Anular</option>
                  </>
                )}
                {is3D && (
                  <>
                    <option value="forceDirected3d">Fuerzas Espaciales 3D</option>
                    <option value="radialOut3d">Radial 3D</option>
                    <option value="concentric3d">Concéntrico 3D</option>
                  </>
                )}
              </select>

              <span className="toolbar-label">Etiquetas:</span>
              <select
                className="toolbar-select"
                value={labelType}
                onChange={(e) => setLabelType(e.target.value)}
              >
                <option value="auto">Automático (Zoom)</option>
                <option value="all">Mostrar Todas</option>
                <option value="nodes">Solo Nodos</option>
              </select>
            </>
          )}
        </div>

        <div className="toolbar-group">
          {/* Selector de Área SNII exclusivo para el Paisaje Temático */}
          {activePresetId === 'snii_topic_landscape' && mode === 'presets' && (
            <>
              <span className="toolbar-label">Área SNII:</span>
              <select
                className="toolbar-select"
                style={{ maxWidth: '170px' }}
                value={areaFilter}
                onChange={(e) => {
                  const val = e.target.value;
                  setAreaFilter(val);
                  loadPresetData(activePresetId, nodeLimit, threshold, val || null);
                }}
              >
                {SNII_AREAS.map((a) => (
                  <option key={a.id} value={a.id}>{a.label}</option>
                ))}
              </select>
            </>
          )}

          {/* Límite de Nodos / Tópicos */}
          <span className="toolbar-label">
            {activePresetId === 'snii_topic_landscape' ? 'Límite Tópicos:' : 'Límite Nodos:'}
          </span>
          <select
            className="toolbar-select"
            value={nodeLimit}
            onChange={(e) => {
              const val = Number(e.target.value);
              setNodeLimit(val);
              if (mode === 'presets') {
                loadPresetData(activePresetId, val, threshold, areaFilter || null);
              }
            }}
          >
            {activePresetId === 'snii_topic_landscape' ? (
              <>
                <option value={500}>500 temas (Enfoque rápido)</option>
                <option value={1000}>1,000 temas</option>
                <option value={2500}>2,500 temas</option>
                <option value={5000}>5,000 temas (Recomendado)</option>
                <option value={15000}>Sin límite (Todos los temas)</option>
              </>
            ) : (
              <>
                <option value={30}>30 nodos (Rápido)</option>
                <option value={50}>50 nodos</option>
                <option value={80}>80 nodos (Equilibrado)</option>
                <option value={150}>150 nodos</option>
                <option value={250}>250 nodos (Detallado)</option>
              </>
            )}
          </select>

          {/* Umbral de Colaboraciones / Investigadores */}
          <span className="toolbar-label">
            {activePresetId === 'snii_topic_landscape' ? 'Mín. Investigadores:' : 'Umbral Enlaces:'}
          </span>
          <select
            className="toolbar-select"
            value={threshold}
            onChange={(e) => {
              const val = Number(e.target.value);
              setThreshold(val);
              if (mode === 'presets') {
                loadPresetData(activePresetId, nodeLimit, val, areaFilter || null);
              }
            }}
          >
            {activePresetId === 'snii_topic_landscape' ? (
              <>
                <option value={1}>≥ 1 inv. (Todas las 18k ligas)</option>
                <option value={3}>≥ 3 inv. (Detallado · ~10.6k ligas)</option>
                <option value={5}>≥ 5 inv. (Amplio · ~7.9k ligas)</option>
                <option value={10}>≥ 10 inv. (Recomendado · ~5.0k ligas)</option>
                <option value={20}>≥ 20 inv. (Troncal · ~2.9k ligas)</option>
                <option value={40}>≥ 40 inv. (Focal · ~1.2k ligas)</option>
              </>
            ) : (
              <>
                <option value={1}>≥ 1 publicación</option>
                <option value={5}>≥ 5 publicaciones</option>
                <option value={15}>≥ 15 publicaciones</option>
                <option value={30}>≥ 30 publicaciones</option>
                <option value={50}>≥ 50 publicaciones</option>
              </>
            )}
          </select>

          {/* Botón Refrescar */}
          <button
            className="toolbar-button"
            title="Recargar consulta de grafo"
            onClick={() => {
              if (mode === 'presets') {
                loadPresetData(activePresetId, nodeLimit, threshold, areaFilter || null);
              } else {
                handleExecuteCustomSubgraph();
              }
            }}
          >
            <RefreshCw size={15} />
          </button>

          {/* Botón de Estabilización de Física WebGL (Convergencia a 60 FPS) */}
          <button
            className={`toolbar-button ${isPhysicsActive ? 'active' : ''}`}
            title={isPhysicsActive ? 'Física activa (reordenando nodos...)' : 'Física estabilizada a 60 FPS fijos. Haz clic para reordenar.'}
            onClick={() => {
              if (isPhysicsActive) {
                setIsPhysicsActive(false);
              } else {
                triggerPhysicsSettle(2200);
              }
            }}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
          >
            <Zap size={14} style={{ color: isPhysicsActive ? '#10b981' : 'inherit' }} />
            <span style={{ fontSize: '0.72rem' }}>{isPhysicsActive ? 'Física...' : '60 FPS'}</span>
          </button>

          {/* Contador de Nodos y Aristas */}
          <div className="stats-counter" title="Conteo de nodos y aristas activas en el subgrafo">
            {activePresetId === 'snii_topic_landscape' && graphData.stats?.topic_nodes !== undefined ? (
              `${graphData.stats.area_nodes || 9} áreas · ${graphData.stats.topic_nodes.toLocaleString()} tópicos · ${graphData.edges.length.toLocaleString()} enlaces`
            ) : (
              `${graphData.nodes.length} nodos · ${graphData.edges.length} enlaces`
            )}
          </div>

          {/* Pantalla Completa */}
          <button
            className="toolbar-button"
            title={isFullscreen ? 'Salir de pantalla completa' : 'Pantalla completa'}
            onClick={() => setIsFullscreen(!isFullscreen)}
          >
            {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
        </div>
      </div>

      {/* 5. Área del Canvas WebGL / Fallback SVG */}
      <div className={`graph-canvas-container ${isFullscreen ? 'fullscreen' : ''}`}>
        {loading && (
          <div className="graph-loading-overlay">
            <div className="loading-spinner" />
            <span>Consultando topología en Grafo Neo4j...</span>
          </div>
        )}

        {error && !loading && (
          <div className="graph-loading-overlay">
            <AlertCircle size={32} color="#ef4444" />
            <span>{error}</span>
          </div>
        )}

        {/* Canvas de Reagraph envuelto en WebGLBoundary con aceleración por hardware */}
        {graphData.nodes.length > 0 && (
          <WebGLBoundary
            fallback={
              <SvgGraphFallback
                nodes={graphData.nodes}
                edges={graphData.edges}
                onNodeClick={handleNodeClick}
                onEdgeClick={handleEdgeClick}
                selectedNode={selectedNode}
                theme={theme}
              />
            }
          >
            {hasWebGL ? (
              <GraphCanvas
                ref={graphRef}
                nodes={graphData.nodes}
                edges={graphData.edges}
                theme={reagraphTheme}
                layoutType={layoutType}
                labelType={activePresetId === 'snii_topic_landscape' ? 'auto' : labelType}
                cameraMode={is3D ? 'rotate' : 'pan'}
                animated={isPhysicsActive}
                edgeInterpolation="linear"
                glOptions={glConfig}
                onNodeClick={handleNodeClick}
                onEdgeClick={handleEdgeClick}
                onCanvasClick={() => {
                  setSelectedNode(null);
                  setSelectedNodeDetails(null);
                  setSelectedEdge(null);
                }}
              />
            ) : (
              <SvgGraphFallback
                nodes={graphData.nodes}
                edges={graphData.edges}
                onNodeClick={handleNodeClick}
                onEdgeClick={handleEdgeClick}
                selectedNode={selectedNode}
                theme={theme}
              />
            )}
          </WebGLBoundary>
        )}

        {/* Leyenda Flotante */}
        <div className="graph-legend-floating">
          <span className="legend-title">Topología y Clases</span>
          {nodeLegendItems.map((item, idx) => (
            <div key={idx} className="legend-item">
              <span className="legend-dot" style={{ backgroundColor: item.color }} />
              <span>{item.label}</span>
            </div>
          ))}

          {/* Barra Cromática Continua con Degradado */}
          {gradientScale && (
            <div className="gradient-bar-wrapper">
              <span className="gradient-bar-title">{gradientScale.title}</span>
              <div
                className="gradient-color-bar"
                style={{ background: gradientScale.gradient }}
              />
              <div className="gradient-bar-labels">
                <span>{gradientScale.minLabel}</span>
                <span>{gradientScale.midLabel}</span>
                <span>{gradientScale.maxLabel}</span>
              </div>
            </div>
          )}

          {activePresetId === 'evaluator_distance' && (
            <div className="gradient-bar-wrapper">
              <span className="gradient-bar-title">Dictaminación de Pares</span>
              <div className="legend-item" style={{ marginTop: '0.2rem' }}>
                <span style={{ width: 14, height: 2.5, backgroundColor: '#10b981', borderTop: '1px dashed #fff', flexShrink: 0 }} />
                <span>Sin Conflicto (Par Recomendado)</span>
              </div>
              <div className="legend-item">
                <span style={{ width: 14, height: 2.5, backgroundColor: '#ef4444', flexShrink: 0 }} />
                <span>Conflicto Directo (Coautor)</span>
              </div>
            </div>
          )}
        </div>

        {/* 6. Drawer Lateral de Inspección de Nodo */}
        {selectedNode && (
          <aside className="graph-inspector-drawer">
            <div className="drawer-header">
              <div className="drawer-title-box">
                <h3>{selectedNodeDetails?.title || selectedNode.label}</h3>
                <span className="drawer-subtitle">
                  {selectedNodeDetails?.subtitle || selectedNode.subLabel || 'Entidad'}
                </span>
              </div>
              <button
                className="drawer-close-btn"
                onClick={() => {
                  setSelectedNode(null);
                  setSelectedNodeDetails(null);
                }}
              >
                <X size={16} />
              </button>
            </div>

            {loadingDetails ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: '#94a3b8' }}>
                Cargando métricas...
              </div>
            ) : (
              <>
                <div className="drawer-props-list">
                  {selectedNodeDetails?.properties &&
                    Object.entries(selectedNodeDetails.properties).map(([k, v]) => (
                      <div key={k} className="drawer-prop-row">
                        <span className="drawer-prop-key">{k}</span>
                        <span className="drawer-prop-val">{String(v)}</span>
                      </div>
                    ))}
                </div>

                {(selectedNodeDetails?.type === 'person' ||
                  selectedNodeDetails?.type === 'institution' ||
                  selectedNodeDetails?.type === 'cpi') && (
                  <div className="drawer-actions">
                    <button
                      className="drawer-action-btn"
                      onClick={() => handleNavigateEntity(selectedNodeDetails)}
                    >
                      <ExternalLink size={14} />
                      {selectedNodeDetails?.type === 'person'
                        ? 'Ver Perfil del Investigador'
                        : 'Ver en Panorama Institucional'}
                    </button>
                  </div>
                )}
              </>
            )}
          </aside>
        )}

        {/* 7. Drawer Lateral de Inspección de Arista */}
        {selectedEdge && (
          <aside className="graph-inspector-drawer">
            <div className="drawer-header">
              <div className="drawer-title-box">
                <h3>Vínculo de Colaboración</h3>
                <span className="drawer-subtitle">{selectedEdge.label || 'Enlace Científico'}</span>
              </div>
              <button
                className="drawer-close-btn"
                onClick={() => setSelectedEdge(null)}
              >
                <X size={16} />
              </button>
            </div>

            <div className="drawer-props-list">
              <div className="drawer-prop-row">
                <span className="drawer-prop-key">Origen</span>
                <span className="drawer-prop-val">{selectedEdge.source}</span>
              </div>
              <div className="drawer-prop-row">
                <span className="drawer-prop-key">Destino</span>
                <span className="drawer-prop-val">{selectedEdge.target}</span>
              </div>
              {selectedEdge.data?.weight && (
                <div className="drawer-prop-row">
                  <span className="drawer-prop-key">Fuerza de Enlace</span>
                  <span className="drawer-prop-val">{selectedEdge.data.weight} publicaciones conjuntas</span>
                </div>
              )}
              {selectedEdge.data?.description && (
                <div className="drawer-prop-row">
                  <span className="drawer-prop-key">Detalle</span>
                  <span className="drawer-prop-val">{selectedEdge.data.description}</span>
                </div>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

export default GraphExplorerView;
