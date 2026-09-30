/**
 * frontend/src/components/modules/ScienceMaps.jsx
 * Módulo 3: Mapas de la Ciencia y Espacios Semánticos
 * Visualizador Topológico WebGL de Alta Escala con Deepscatter (10 Capas Semánticas)
 * + Explorador Integrado de Pares Académicos (UMAP 2D).
 */

import React, { useState, useEffect, useMemo, useRef } from 'react';
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
  ExternalLink,
  BookOpen,
  Users,
  Network,
  BarChart3,
  Globe,
  Info,
  ChevronDown,
  ChevronUp,
  Play,
  EyeOff,
  Radio
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import { apiClient } from '../../api/client.js';

// ── 10 Capas Semánticas y de Redes Deepscatter WebGL ──────────────────────────
const MAP_LAYERS = [
  {
    id: "articles_specter",
    name: "📄 Artículos (Semántica - SPECTER2)",
    category: "articulos",
    url: "https://dinamica1.fciencias.unam.mx/tiles/articles_specter_data.json",
    colorByCluster: true,
    emoji: "🔭",
    title: "Mapa de Artículos — Semántica SPECTER2",
    badge: "Recomendado",
    desc: "Cerca de un millón de artículos académicos proyectados en un plano 2D según embeddings SPECTER2 (Allen Institute for AI), pre-entrenados específicamente en literatura científica. La proximidad espacial enfatiza la similitud disciplinar y metodológica: artículos que comparten enfoque experimental o computacional quedan juntos aunque usen vocabulario diferente.",
    tech: "SPECTER2 768d → UMAP coseno → HDBSCAN + LLM etiquetas → WebGL Deepscatter",
    uses: [
      "Detectar grupos con metodologías compartidas entre disciplinas aparentemente distintas.",
      "Evaluar si proyectos financiados en áreas diversas comparten base técnica común.",
      "Identificar afinidades metodológicas entre cuerpos académicos de distintas IES.",
      "Comparar el perfil metodológico de la ciencia mexicana con otros países de la región."
    ]
  },
  {
    id: "articles_nomic",
    name: "📄 Artículos (Semántica - Nomic)",
    category: "articulos",
    url: "https://dinamica1.fciencias.unam.mx/tiles/articles_nomic_data.json",
    colorByCluster: false,
    emoji: "🔬",
    title: "Mapa de Artículos — Semántica Nomic v1.5",
    desc: "Proyección semántica global de artículos científicos mediante embeddings Nomic de 768 dimensiones. Los artículos de temáticas parecidas aparecen en el mismo 'continente' del mapa; cada región lleva una etiqueta temática generada automáticamente por IA (p. ej. Oncología Molecular, Educación Matemática).",
    tech: "Nomic 768d → UMAP coseno → HDBSCAN + LLM etiquetas → WebGL Deepscatter",
    uses: [
      "Identificar vacíos de conocimiento en la ciencia mexicana para orientar convocatorias.",
      "Descubrir intersecciones temáticas entre departamentos para investigación interdisciplinaria.",
      "Localizar investigadoras e investigadores activos en enfermedades o tecnologías estratégicas.",
      "Contextualizar la línea de investigación de un académico dentro del mapa nacional."
    ]
  },
  {
    id: "articles_qdrant",
    name: "📄 Artículos (Semántica - Qdrant)",
    category: "articulos",
    url: "https://dinamica1.fciencias.unam.mx/tiles/articles_data.json",
    colorByCluster: false,
    emoji: "📄",
    title: "Mapa de Artículos — Semántica (Qdrant / Legacy)",
    desc: "Visualización del corpus de artículos académicos de investigadoras e investigadores del país proyectados en 2D según su similitud semántica de contenido, usando embeddings almacenados en la base vectorial Qdrant (versión heredada). Los artículos con temáticas afines aparecen agrupados en regiones contiguas del mapa.",
    tech: "Embeddings locales → UMAP coseno → WebGL Deepscatter",
    uses: [
      "Exploración libre del corpus nacional de publicaciones.",
      "Identificar grupos temáticos emergentes sin búsqueda previa.",
      "Comparar la distribución geográfica del mapa con versiones más recientes."
    ]
  },
  {
    id: "people_specter",
    name: "🧑‍🤝‍🧑 Académicos (Semántica SPECTER2)",
    category: "investigadores",
    url: "https://dinamica1.fciencias.unam.mx/tiles/people_semantic_data.json",
    colorByCluster: false,
    emoji: "🎓",
    title: "Mapa de Investigadoras e Investigadores — Perfil Semántico (SPECTER2)",
    badge: "Afinidad Científica",
    desc: "Investigadoras e investigadores posicionados según el centroide semántico de toda su obra publicada, calculado con SPECTER2. A diferencia del mapa de red, aquí la posición refleja qué investiga el académico —no con quién colabora—. Dos académicos de instituciones distintas que publican sobre temas similares quedan cerca.",
    tech: "Perfil SPECTER2 por académico → UMAP coseno → WebGL Deepscatter",
    uses: [
      "Identificar investigadoras e investigadores con líneas afines para consolidar cuerpos académicos virtuales.",
      "Vincular necesidades tecnológicas de empresas con la investigadora o investigador más pertinente.",
      "Reclutar sinodales o directores de tesis por afinidad semántica real, no por departamento.",
      "Preseleccionar evaluadores de proyectos alineados genuinamente con el área convocada."
    ]
  },
  {
    id: "people_social",
    name: "🧑‍🤝‍🧑 Personas (Estructura Social)",
    category: "investigadores",
    url: "https://dinamica1.fciencias.unam.mx/tiles/people_data.json",
    colorByCluster: false,
    emoji: "🕸️",
    title: "Mapa de Investigadoras e Investigadores — Red Estructural (FastRP)",
    desc: "Investigadoras e investigadores posicionados según su lugar dentro de la red de coautoría y filiación institucional, calculado mediante FastRP sobre el grafo de Neo4j (nodos: Person, Institution, Paper; relaciones: AUTHOR_OF, AFFILIATED_TO). Quienes tienen colaboradores o instituciones comunes aparecen cerca. Revela la estructura social de la ciencia mexicana: comunidades, brokers y nodos aislados.",
    tech: "Neo4j GDS FastRP 128d → UMAP coseno → WebGL Deepscatter",
    uses: [
      "Identificar personas puente (brokers) entre comunidades científicas.",
      "Detectar académicos aislados estructuralmente para diseñar políticas de mentoría.",
      "Visualizar el peso relativo de universidades estatales dentro de la red nacional.",
      "Priorizar becas de movilidad para investigadoras e investigadores en la periferia de la red internacional."
    ]
  },
  {
    id: "people_topics_sdg",
    name: "🧑‍🤝‍🧑 Personas (Estructura + Temas + ODS)",
    category: "investigadores",
    url: "https://dinamica1.fciencias.unam.mx/tiles/people_topics_data.json",
    colorByCluster: false,
    emoji: "🌍",
    title: "Mapa de Investigadoras e Investigadores — Perfil Temático y ODS",
    badge: "Agenda 2030",
    desc: "Investigadoras e investigadores posicionados según su perfil temático y contribución a los Objetivos de Desarrollo Sostenible (ODS). El grafo de Neo4j incluye nodos Topic y SDG con relaciones HAS_TOPIC y CONTRIBUTES_TO. FastRP con este grafo ampliado produce embeddings que mezclan estructura de red con orientación temática.",
    tech: "Neo4j GDS FastRP (Person + Topic + SDG) → UMAP coseno → WebGL Deepscatter",
    uses: [
      "Identificar investigadoras e investigadores que contribuyen a cada ODS para reportes ante la ONU.",
      "Localizar expertos en ODS 13 (Clima), 3 (Salud) o 2 (Hambre Cero) para consejos técnicos.",
      "Alinear la investigación regional con cadenas de valor productivas locales.",
      "Establecer alianzas de investigación-acción con OSC en ODS sociales."
    ]
  },
  {
    id: "people_performance",
    name: "📊 Personas (Desempeño)",
    category: "investigadores",
    url: "https://dinamica1.fciencias.unam.mx/tiles/performance_data.json",
    colorByCluster: false,
    emoji: "📊",
    title: "Mapa de Desempeño Institucional Multidimensional",
    desc: "Investigadoras e investigadores agrupados según un vector de métricas bibliométricas de impacto: % Top 10, FWCI promedio, % Top 1% y Percentil Promedio de citación. Quienes presentan perfiles similares de impacto quedan cerca, independientemente de su disciplina o institución.",
    tech: "Vector 4D de métricas → UMAP euclidiano → WebGL Deepscatter",
    uses: [
      "Comparar el perfil de impacto de candidatos al SNII con una visión multidimensional.",
      "Detectar investigadoras e investigadores de alto impacto sin apoyos suficientes para retención de talento.",
      "Demostrar masa crítica de alto impacto en procesos de acreditación (CIEES, COPAES).",
      "Comparar el perfil de investigadoras e investigadores con el promedio nacional para atracción."
    ]
  },
  {
    id: "network_coauthorship",
    name: "🕸️ Red de Coautoría (WebGL - Comunidad/PageRank)",
    category: "redes",
    url: "https://dinamica1.fciencias.unam.mx/tiles/network_coauthorship_data.json",
    colorByCluster: true,
    emoji: "🕸️",
    title: "Red de Coautoría — Comunidades y PageRank",
    badge: "Grafo Complejo",
    desc: "Grafo interactivo de colaboración científica entre investigadoras e investigadores del país. Los nodos representan académicos y las aristas indican coautorías directas. El color identifica comunidades de colaboración (Louvain/Leiden) y el tamaño del nodo refleja su PageRank (influencia estructural en la red).",
    tech: "Neo4j → WebGL (sigma.js/force-directed) → comunidades Louvain",
    uses: [
      "Visualizar clústeres de colaboración y detectar comunidades científicas consolidadas.",
      "Identificar investigadoras e investigadores con alta influencia (PageRank alto) para articulación de redes.",
      "Detectar nodos puente entre comunidades disciplinarias o institucionales.",
      "Analizar la evolución de la colaboración nacional a lo largo del tiempo."
    ]
  },
  {
    id: "network_institutional",
    name: "🏛️ Red Institucional (WebGL - Louvain)",
    category: "redes",
    url: "https://dinamica1.fciencias.unam.mx/tiles/network_institutional_data.json",
    colorByCluster: true,
    emoji: "🏛️",
    title: "Red Institucional — Comunidades Louvain",
    desc: "Grafo de colaboración a nivel institucional: cada nodo es una institución y cada arista refleja coautorías agregadas entre sus investigadoras e investigadores. El algoritmo Louvain detecta comunidades de instituciones que colaboran frecuentemente entre sí.",
    tech: "Coautorías agregadas por institución → Louvain → WebGL Deepscatter",
    uses: [
      "Identificar clusters de IES con alta colaboración para proponer redes formales de investigación.",
      "Visualizar el posicionamiento de una universidad dentro del ecosistema científico nacional.",
      "Detectar instituciones periféricas con baja integración a redes más grandes.",
      "Diseñar políticas de fomento a la colaboración interinstitucional basadas en evidencia."
    ]
  },
  {
    id: "network_bipartite",
    name: "🌐 Red Bipartita Autor-Tema/ODS (WebGL)",
    category: "redes",
    url: "https://dinamica1.fciencias.unam.mx/tiles/network_bipartite_data.json",
    colorByCluster: true,
    emoji: "🌐",
    title: "Red Bipartita Autor–Tema/ODS",
    desc: "Red bipartita que conecta investigadoras e investigadores con los temas de OpenAlex y ODS a los que contribuyen sus publicaciones. Permite ver en un solo grafo quién trabaja en qué tema y cómo los temas y los ODS se relacionan a través de las personas que los comparten.",
    tech: "Relaciones HAS_TOPIC + CONTRIBUTES_TO de Neo4j → WebGL bipartito",
    uses: [
      "Identificar qué investigadoras e investigadores son centrales para un tema o ODS específico.",
      "Descubrir temas 'puente' que conectan ODS distintos a través de proyectos compartidos.",
      "Apoyar la construcción de equipos multidisciplinarios orientados a un ODS concreto.",
      "Generar reportes de alineación de la investigación nacional con la Agenda 2030."
    ]
  }
];

export function ScienceMaps() {
  const t = useAppStore((state) => state.t)();
  const setSelectedResearcher = useAppStore((state) => state.setSelectedResearcher);
  const setActiveTab = useAppStore((state) => state.setActiveTab);
  const theme = useAppStore((state) => state.theme);
  const isLight = theme === 'claro';

  // Estados del Módulo
  const [selectedLayerId, setSelectedLayerId] = useState('articles_specter');
  const [categoryFilter, setCategoryFilter] = useState('todos'); // 'todos', 'articulos', 'investigadores', 'redes'
  const [isMapLoaded, setIsMapLoaded] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showMethodology, setShowMethodology] = useState(true);
  const [iframeKey, setIframeKey] = useState(1);
  const containerRef = useRef(null);

  // Estados para el modo Explorador UMAP Local
  const [viewMode, setViewMode] = useState('deepscatter'); // 'deepscatter' vs 'umap_explorer'
  const [colorMode, setColorMode] = useState('domain');
  const [searchFilter, setSearchFilter] = useState('');
  const [selectedDomain, setSelectedDomain] = useState('all');
  const [umapData, setUmapData] = useState({ points: [], domains: [], total: 0 });
  const [loadingUmap, setLoadingUmap] = useState(false);

  // Capa activa
  const selectedLayer = useMemo(() => {
    return MAP_LAYERS.find((l) => l.id === selectedLayerId) || MAP_LAYERS[0];
  }, [selectedLayerId]);

  // URL del Iframe Deepscatter WebGL
  const iframeSrc = useMemo(() => {
    const colorByParam = selectedLayer.colorByCluster ? "&color_by=cluster" : "";
    return `https://dinamica1.fciencias.unam.mx/tiles/map_test.html?v=28&data=${selectedLayer.url}?v=28${colorByParam}`;
  }, [selectedLayer]);

  // Carga diferida de UMAP de investigadores si se activa el modo explorador
  useEffect(() => {
    if (viewMode !== 'umap_explorer') return;
    async function loadUmap() {
      setLoadingUmap(true);
      try {
        const data = await apiClient.getResearchersUmap(1500, '', selectedDomain !== 'all' ? selectedDomain : '');
        setUmapData(data);
      } catch (err) {
        console.error('Error cargando coordenadas UMAP:', err);
      } finally {
        setLoadingUmap(false);
      }
    }
    loadUmap();
  }, [viewMode, selectedDomain]);

  // Capas filtradas por categoría
  const filteredLayers = useMemo(() => {
    if (categoryFilter === 'todos') return MAP_LAYERS;
    return MAP_LAYERS.filter((l) => l.category === categoryFilter);
  }, [categoryFilter]);

  // Pantalla Completa
  const handleToggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  const handleReload = () => {
    setIframeKey((prev) => prev + 1);
  };

  // Filtrado de puntos UMAP
  const filteredUmapPoints = useMemo(() => {
    if (!searchFilter.trim()) return umapData.points;
    const q = searchFilter.toLowerCase();
    return umapData.points.filter((p) =>
      p.name.toLowerCase().includes(q) ||
      p.inst.toLowerCase().includes(q) ||
      p.topic.toLowerCase().includes(q)
    );
  }, [umapData.points, searchFilter]);

  const domainColors = {
    'Physical Sciences': '#00f2fe',
    'Life Sciences': '#10b981',
    'Health Sciences': '#ec4899',
    'Social Sciences': '#f59e0b',
    'General': '#a855f7'
  };

  // Traza de Plotly Scattergl para UMAP Local
  const plotData = useMemo(() => {
    if (colorMode === 'domain') {
      const groups = {};
      filteredUmapPoints.forEach((p) => {
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
        text: g.text,
        customdata: g.customdata,
        hoverinfo: 'text',
        marker: {
          size: 6,
          color: domainColors[dom] || '#00f2fe',
          opacity: 0.8
        }
      }));
    }

    return [{
      x: filteredUmapPoints.map((p) => p.x),
      y: filteredUmapPoints.map((p) => p.y),
      type: 'scattergl',
      mode: 'markers',
      customdata: filteredUmapPoints,
      hoverinfo: 'text',
      text: filteredUmapPoints.map((p) =>
        `<b>${p.name}</b><br>` +
        `Institución: ${p.inst}<br>` +
        `Citas: ${p.cites} · H: ${p.h}`
      ),
      marker: {
        size: 6,
        color: filteredUmapPoints.map((p) => colorMode === 'citations' ? p.cites : p.h),
        colorscale: 'Viridis',
        colorbar: {
          title: colorMode === 'citations' ? 'Citas' : 'Índice H'
        },
        opacity: 0.8
      }
    }];
  }, [filteredUmapPoints, colorMode]);

  const handlePointClick = (event) => {
    if (!event.points || !event.points[0]) return;
    const data = event.points[0].customdata;
    if (data && data.name) {
      setSelectedResearcher(data.name, '');
      setActiveTab('researchers');
    }
  };

  return (
    <div
      ref={containerRef}
      className="module-container"
      style={{
        padding: isFullscreen ? 0 : '0.5rem 1.5rem 2rem',
        height: isFullscreen ? '100vh' : 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem'
      }}
    >
      {/* ── 1. Barra de Navegación del Módulo y Modos de Visualización ─────── */}
      {!isFullscreen && (
        <div className="glass-card" style={{ padding: '1rem 1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{
                width: '42px', height: '42px', borderRadius: '10px',
                background: 'rgba(0, 242, 254, 0.12)', border: '1px solid rgba(0, 242, 254, 0.25)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-cyan)'
              }}>
                <Compass size={24} />
              </div>
              <div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 800, margin: 0, letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  Mapas de la Ciencia y Espacios Semánticos
                  <span className="badge badge-purple" style={{ fontSize: '0.72rem' }}>WebGL GPU 60 FPS</span>
                </h2>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: '2px 0 0 0' }}>
                  Cartografía topológica interactiva sobre millones de publicaciones y redes de investigadoras e investigadores del país.
                </p>
              </div>
            </div>

            {/* Alternador de Modo: Deepscatter WebGL vs Explorador UMAP */}
            <div style={{ display: 'flex', gap: '0.4rem', background: 'rgba(0,0,0,0.15)', padding: '0.25rem', borderRadius: '8px' }}>
              <button
                className={`btn btn-sm ${viewMode === 'deepscatter' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setViewMode('deepscatter')}
                style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem' }}
              >
                <Layers size={14} />
                <span>Deepscatter WebGL (10 Capas)</span>
              </button>
              <button
                className={`btn btn-sm ${viewMode === 'umap_explorer' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setViewMode('umap_explorer')}
                style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem' }}
              >
                <Users size={14} />
                <span>Explorador Pares UMAP</span>
              </button>
            </div>
          </div>

          {/* Selector de Categorías y Capas para Deepscatter */}
          {viewMode === 'deepscatter' && (
            <div>
              {/* Filtros de Categoría */}
              <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
                <button
                  className={`btn btn-xs ${categoryFilter === 'todos' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setCategoryFilter('todos')}
                >
                  <Globe size={13} /> Todas las Capas ({MAP_LAYERS.length})
                </button>
                <button
                  className={`btn btn-xs ${categoryFilter === 'articulos' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setCategoryFilter('articulos')}
                >
                  <BookOpen size={13} /> 📄 Artículos Semánticos
                </button>
                <button
                  className={`btn btn-xs ${categoryFilter === 'investigadores' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setCategoryFilter('investigadores')}
                >
                  <Users size={13} /> 🧑‍🤝‍🧑 Investigadoras e Investigadores & Desempeño
                </button>
                <button
                  className={`btn btn-xs ${categoryFilter === 'redes' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => setCategoryFilter('redes')}
                >
                  <Network size={13} /> 🕸️ Redes Complejas (Louvain)
                </button>
              </div>

              {/* Botonera / Pills de Selección de Capa */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
                gap: '0.5rem'
              }}>
                {filteredLayers.map((layer) => {
                  const isSelected = selectedLayerId === layer.id;
                  return (
                    <button
                      key={layer.id}
                      onClick={() => {
                        setSelectedLayerId(layer.id);
                        setIsMapLoaded(true);
                      }}
                      className={`btn btn-sm ${isSelected ? 'btn-primary' : 'btn-secondary'}`}
                      style={{
                        justifyContent: 'flex-start',
                        textAlign: 'left',
                        padding: '0.45rem 0.75rem',
                        fontSize: '0.8rem',
                        position: 'relative',
                        borderColor: isSelected ? 'var(--accent-cyan)' : 'var(--border-subtle)',
                        boxShadow: isSelected ? '0 0 12px rgba(0, 242, 254, 0.25)' : 'none'
                      }}
                    >
                      <span style={{ fontSize: '1rem', marginRight: '6px' }}>{layer.emoji}</span>
                      <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1 }}>
                        {layer.name.replace(/^[^\s]+\s/, '')}
                      </span>
                      {layer.badge && (
                        <span className="badge badge-amber" style={{ fontSize: '0.62rem', padding: '0.1rem 0.35rem', marginLeft: '4px' }}>
                          {layer.badge}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── 2. Ficha Metodológica de la Capa Activa (Deepscatter) ──────────── */}
      {viewMode === 'deepscatter' && !isFullscreen && (
        <div
          className="glass-card"
          style={{
            padding: '1rem 1.25rem',
            background: isLight ? 'linear-gradient(135deg, #f8fafc, #f1f5f9)' : 'linear-gradient(135deg, #0b1523, #13253b)',
            borderLeft: '4px solid var(--accent-cyan)'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                <span style={{ fontSize: '1.25rem' }}>{selectedLayer.emoji}</span>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, color: 'var(--accent-cyan)' }}>
                  {selectedLayer.title}
                </h3>
              </div>
              <p style={{ fontSize: '0.85rem', lineHeight: '1.55', color: 'var(--text-secondary)', margin: '0 0 0.5rem 0' }}>
                {selectedLayer.desc}
              </p>
            </div>

            <button
              onClick={() => setShowMethodology(!showMethodology)}
              className="btn btn-ghost btn-xs"
              style={{ flexShrink: 0 }}
              title={showMethodology ? "Ocultar detalles técnicos" : "Ver detalles técnicos"}
            >
              <Info size={14} />
              <span>{showMethodology ? "Menos info" : "Metodología y Casos"}</span>
              {showMethodology ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          </div>

          {showMethodology && (
            <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-subtle)', fontSize: '0.82rem' }}>
              <div style={{ marginBottom: '0.5rem' }}>
                <strong style={{ color: 'var(--accent-purple)' }}>⚙️ Pipeline Tecnológico: </strong>
                <code style={{ fontSize: '0.78rem', padding: '0.15rem 0.4rem', borderRadius: '4px', background: 'rgba(255,255,255,0.06)' }}>
                  {selectedLayer.tech}
                </code>
              </div>
              <div>
                <strong style={{ color: 'var(--accent-cyan)' }}>💡 Casos de Uso Principales:</strong>
                <ul style={{ margin: '0.35rem 0 0 0', paddingLeft: '1.25rem', lineHeight: '1.5', color: 'var(--text-secondary)' }}>
                  {selectedLayer.uses.map((u, i) => (
                    <li key={i}>{u}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── 3. Contenedor del Lienzo WebGL (Deepscatter) ────────────────────── */}
      {viewMode === 'deepscatter' && (
        <div
          className="glass-card"
          style={{
            padding: isFullscreen ? 0 : '0.5rem',
            position: 'relative',
            flex: 1,
            minHeight: isFullscreen ? '100vh' : '750px',
            display: 'flex',
            flexDirection: 'column'
          }}
        >
          {/* Barra de Controles del Lienzo */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '0.5rem 0.75rem',
            borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
            flexWrap: 'wrap',
            gap: '0.5rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className="badge badge-cyan" style={{ fontSize: '0.75rem' }}>
                {selectedLayer.name}
              </span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Navegación: Arrastra para desplazar · Rueda del mouse para zoom profundo
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <button
                className={`btn btn-sm ${isMapLoaded ? 'btn-secondary' : 'btn-primary'}`}
                onClick={() => setIsMapLoaded(!isMapLoaded)}
                style={{ fontSize: '0.75rem', padding: '0.3rem 0.65rem' }}
              >
                {isMapLoaded ? <EyeOff size={13} /> : <Play size={13} />}
                <span>{isMapLoaded ? "Ocultar Mapa" : "Cargar Mapa"}</span>
              </button>

              <button
                className="btn btn-secondary btn-sm"
                onClick={handleReload}
                style={{ fontSize: '0.75rem', padding: '0.3rem 0.65rem' }}
                title="Recargar lienzo WebGL"
              >
                <RotateCcw size={13} />
                <span>Recargar</span>
              </button>

              <button
                className="btn btn-secondary btn-sm"
                onClick={handleToggleFullscreen}
                style={{ fontSize: '0.75rem', padding: '0.3rem 0.65rem' }}
                title="Pantalla Completa"
              >
                {isFullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                <span>{isFullscreen ? "Salir" : "Pantalla Completa"}</span>
              </button>

              <a
                href={iframeSrc}
                target="_blank"
                rel="noreferrer"
                className="btn btn-ghost btn-sm"
                style={{ fontSize: '0.75rem', padding: '0.3rem 0.65rem' }}
                title="Abrir visor en pestaña nueva"
              >
                <ExternalLink size={13} />
                <span>Abrir directo</span>
              </a>
            </div>
          </div>

          {/* Iframe Deepscatter WebGL */}
          {isMapLoaded ? (
            <div style={{ flex: 1, position: 'relative', width: '100%', height: isFullscreen ? 'calc(100vh - 46px)' : '720px' }}>
              <iframe
                key={`${selectedLayer.id}-${iframeKey}`}
                src={iframeSrc}
                title={selectedLayer.title}
                style={{
                  width: '100%',
                  height: '100%',
                  border: 'none',
                  borderRadius: isFullscreen ? 0 : '8px',
                  display: 'block'
                }}
                loading="lazy"
                allow="accelerometer; camera; encrypted-media; gyroscope; picture-in-picture"
              />
            </div>
          ) : (
            <div style={{
              height: '480px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-muted)',
              gap: '1rem'
            }}>
              <Compass size={48} style={{ opacity: 0.3 }} />
              <p style={{ margin: 0 }}>El lienzo WebGL está en pausa para optimizar recursos de GPU.</p>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => setIsMapLoaded(true)}
              >
                <Play size={14} />
                <span>Cargar {selectedLayer.title}</span>
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── 4. Modo Secundario: Explorador de Pares Académicos (Plotly UMAP) ── */}
      {viewMode === 'umap_explorer' && (
        <div className="glass-card" style={{ padding: '1rem' }}>
          {/* Controles del Explorador UMAP */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
            <div style={{ flex: 1, minWidth: '240px', position: 'relative' }}>
              <Search size={16} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input
                type="text"
                className="form-input"
                style={{ paddingLeft: '2.2rem', fontSize: '0.85rem' }}
                placeholder="Buscar investigador, institución o tópico..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
              />
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <select
                className="form-select"
                style={{ fontSize: '0.82rem', padding: '0.35rem 0.65rem' }}
                value={colorMode}
                onChange={(e) => setColorMode(e.target.value)}
              >
                <option value="domain">Colorear por Dominio</option>
                <option value="citations">Colorear por Citas Totales</option>
                <option value="h_index">Colorear por Índice H</option>
              </select>

              <select
                className="form-select"
                style={{ fontSize: '0.82rem', padding: '0.35rem 0.65rem' }}
                value={selectedDomain}
                onChange={(e) => setSelectedDomain(e.target.value)}
              >
                <option value="all">Todos los Dominios</option>
                {umapData.domains.map((d) => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>

              <button
                className="btn btn-secondary btn-sm"
                onClick={() => { setSearchFilter(''); setSelectedDomain('all'); }}
                title="Restablecer filtros"
              >
                <RotateCcw size={13} />
              </button>
            </div>
          </div>

          <div style={{ marginBottom: '0.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="badge badge-cyan" style={{ fontSize: '0.75rem' }}>
              {filteredUmapPoints.length.toLocaleString()} pares académicos evaluados
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Tip: Haz clic sobre un nodo para abrir su perfil individual en el Módulo de Investigadores
            </span>
          </div>

          {loadingUmap ? (
            <div style={{ height: '560px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <Sparkles size={32} style={{ color: 'var(--accent-cyan)', animation: 'spin 2s linear infinite', marginBottom: '1rem' }} />
              <p style={{ color: 'var(--text-secondary)' }}>Cargando proyecciones UMAP de pares...</p>
            </div>
          ) : (
            <Plot
              data={plotData}
              layout={{
                autosize: true,
                height: 580,
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: { family: 'Plus Jakarta Sans, sans-serif', color: isLight ? '#334155' : '#94a3b8' },
                xaxis: {
                  zeroline: false,
                  showgrid: true,
                  gridcolor: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)',
                  showticklabels: false
                },
                yaxis: {
                  zeroline: false,
                  showgrid: true,
                  gridcolor: isLight ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.05)',
                  showticklabels: false
                },
                legend: { orientation: 'h', y: -0.08, x: 0 },
                margin: { l: 20, r: 20, t: 20, b: 50 },
                hovermode: 'closest'
              }}
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
      )}
    </div>
  );
}

export default ScienceMaps;
