import React, { useState, useMemo, useRef } from 'react';
import { Sparkles, Search, SlidersHorizontal, Hash } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';

// Paleta para Modo Claro: Tonos profundos, saturados y de alto contraste editorial
const COLOR_TIERS_LIGHT = [
  { threshold: 0.85, color: '#0369a1', bgHover: 'rgba(3, 105, 161, 0.12)', glow: 'rgba(3, 105, 161, 0.3)', weight: 800 },
  { threshold: 0.65, color: '#0284c7', bgHover: 'rgba(2, 132, 199, 0.10)', glow: 'rgba(2, 132, 199, 0.25)', weight: 700 },
  { threshold: 0.45, color: '#4f46e5', bgHover: 'rgba(79, 70, 229, 0.09)', glow: 'rgba(79, 70, 229, 0.25)', weight: 600 },
  { threshold: 0.25, color: '#7c3aed', bgHover: 'rgba(124, 58, 237, 0.08)', glow: 'rgba(124, 58, 237, 0.2)', weight: 600 },
  { threshold: 0.10, color: '#be185d', bgHover: 'rgba(190, 24, 93, 0.08)', glow: 'rgba(190, 24, 93, 0.18)', weight: 500 },
  { threshold: 0.0, color: '#64748b', bgHover: 'rgba(100, 116, 139, 0.08)', glow: 'rgba(100, 116, 139, 0.15)', weight: 500 }
];

// Paleta para Modo Oscuro: Neones luminosos sobre fondo noche
const COLOR_TIERS_DARK = [
  { threshold: 0.85, color: '#00f0ff', bgHover: 'rgba(0, 240, 255, 0.14)', glow: 'rgba(0, 240, 255, 0.65)', weight: 800 },
  { threshold: 0.65, color: '#38bdf8', bgHover: 'rgba(56, 189, 248, 0.12)', glow: 'rgba(56, 189, 248, 0.55)', weight: 700 },
  { threshold: 0.45, color: '#818cf8', bgHover: 'rgba(129, 140, 248, 0.10)', glow: 'rgba(129, 140, 248, 0.45)', weight: 600 },
  { threshold: 0.25, color: '#c084fc', bgHover: 'rgba(192, 132, 252, 0.10)', glow: 'rgba(192, 132, 252, 0.40)', weight: 600 },
  { threshold: 0.10, color: '#f472b6', bgHover: 'rgba(244, 114, 182, 0.08)', glow: 'rgba(244, 114, 182, 0.35)', weight: 500 },
  { threshold: 0.0, color: '#94a3b8', bgHover: 'rgba(148, 163, 184, 0.08)', glow: 'rgba(148, 163, 184, 0.20)', weight: 500 }
];

export default function WordCloudInteractive({
  keywords = [],
  title = "Vocabulario Científico (Keywords)",
  subtitle = "Nube de términos y conceptos clave extraídos de la producción científica."
}) {
  const theme = useAppStore((state) => state.theme);
  const isDark = theme === 'oscuro';
  const colorTiers = isDark ? COLOR_TIERS_DARK : COLOR_TIERS_LIGHT;

  const [hoveredWord, setHoveredWord] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [searchTerm, setSearchTerm] = useState('');
  const [limitCount, setLimitCount] = useState(100);
  const containerRef = useRef(null);

  // Procesar y ordenar keywords
  const { processedWords, maxFreq, totalOccurrences } = useMemo(() => {
    if (!Array.isArray(keywords) || keywords.length === 0) {
      return { processedWords: [], maxFreq: 1, totalOccurrences: 0 };
    }

    const validKeywords = keywords
      .filter(k => k && k.keyword && typeof k.freq === 'number')
      .map(k => ({
        keyword: String(k.keyword).trim(),
        freq: k.freq
      }));

    const max = Math.max(...validKeywords.map(k => k.freq), 1);
    const sum = validKeywords.reduce((acc, k) => acc + k.freq, 0);

    return {
      processedWords: validKeywords,
      maxFreq: max,
      totalOccurrences: sum
    };
  }, [keywords]);

  // Filtrado por buscador y límite de palabras
  const visibleWords = useMemo(() => {
    let list = processedWords;
    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      list = list.filter(w => w.keyword.toLowerCase().includes(q));
    }
    return list.slice(0, limitCount);
  }, [processedWords, searchTerm, limitCount]);

  const handleMouseMove = (e, word) => {
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      setTooltipPos({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
      });
    }
    setHoveredWord(word);
  };

  const handleMouseLeave = () => {
    setHoveredWord(null);
  };

  if (processedWords.length === 0) {
    return (
      <div className="glass-card" style={{ padding: '1.25rem' }}>
        <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
          <Sparkles size={18} style={{ color: 'var(--accent-cyan)' }} />
          🔑 {title}
        </h3>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>{subtitle}</p>
        <div style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-muted)', fontSize: '0.88rem' }}>
          Sin datos de palabras clave registradas para esta selección.
        </div>
      </div>
    );
  }

  // Estilo del lienzo de palabras según tema
  const canvasStyle = isDark
    ? {
        position: 'relative',
        padding: '1.5rem 1rem',
        borderRadius: '12px',
        background: 'radial-gradient(ellipse at center, rgba(15, 23, 42, 0.90) 0%, rgba(7, 10, 19, 0.96) 100%)',
        border: '1px solid rgba(56, 189, 248, 0.18)',
        boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 8px 30px rgba(0, 0, 0, 0.4)',
        minHeight: '260px',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.55rem 0.85rem',
        overflow: 'hidden'
      }
    : {
        position: 'relative',
        padding: '1.5rem 1rem',
        borderRadius: '12px',
        background: 'linear-gradient(180deg, #ffffff 0%, #f8fafc 100%)',
        border: '1px solid #e2e8f0',
        boxShadow: 'inset 0 1px 2px rgba(0, 0, 0, 0.02), 0 2px 10px rgba(0, 0, 0, 0.03)',
        minHeight: '260px',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '0.55rem 0.85rem',
        overflow: 'hidden'
      };

  return (
    <div className="glass-card" style={{ padding: '1.25rem' }} ref={containerRef}>
      {/* Encabezado y Controles */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.25rem' }}>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <Sparkles size={18} style={{ color: 'var(--accent-cyan)' }} />
            🔑 {title}
          </h3>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
            {subtitle} ({processedWords.length} términos identificados, {totalOccurrences.toLocaleString()} menciones).
          </p>
        </div>

        {/* Barra de Filtros: Buscador + Selector de Palabras */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          {/* Buscador de términos */}
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <Search size={14} style={{ position: 'absolute', left: '10px', color: 'var(--text-muted)', pointerEvents: 'none' }} />
            <input
              type="text"
              placeholder="Buscar concepto..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="form-input"
              style={{
                paddingLeft: '30px',
                paddingRight: '12px',
                paddingTop: '0.35rem',
                paddingBottom: '0.35rem',
                fontSize: '0.8rem',
                width: '180px',
                borderRadius: '8px'
              }}
            />
          </div>

          {/* Selector de número de palabras */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', background: isDark ? 'rgba(255,255,255,0.03)' : '#f1f5f9', padding: '0.25rem 0.4rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
            <SlidersHorizontal size={13} style={{ color: 'var(--accent-cyan)', marginLeft: '4px' }} />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Mostrar:</span>
            {[50, 100, 150].map((num) => (
              <button
                key={num}
                onClick={() => setLimitCount(num)}
                style={{
                  padding: '0.2rem 0.55rem',
                  fontSize: '0.75rem',
                  fontWeight: limitCount === num ? 700 : 500,
                  borderRadius: '5px',
                  border: 'none',
                  cursor: 'pointer',
                  background: limitCount === num ? 'var(--accent-cyan)' : 'transparent',
                  color: limitCount === num ? '#ffffff' : 'var(--text-secondary)',
                  transition: 'all 0.15s ease'
                }}
              >
                {num}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Contenedor de la Nube de Palabras Interactiva */}
      <div style={canvasStyle}>
        {visibleWords.map((word, idx) => {
          const ratio = word.freq / maxFreq;
          // Escalamiento suave de tamaño tipográfico entre 0.82rem y 2.15rem
          const fontSize = 0.82 + Math.sqrt(ratio) * 1.35;
          const tier = colorTiers.find(t => ratio >= t.threshold) || colorTiers[colorTiers.length - 1];

          const isHovered = hoveredWord?.keyword === word.keyword;
          const isFaded = hoveredWord !== null && !isHovered;

          return (
            <span
              key={`${word.keyword}-${idx}`}
              onMouseMove={(e) => handleMouseMove(e, word)}
              onMouseLeave={handleMouseLeave}
              style={{
                fontSize: `${fontSize.toFixed(2)}rem`,
                fontWeight: tier.weight,
                color: tier.color,
                cursor: 'pointer',
                userSelect: 'none',
                padding: '0.25rem 0.55rem',
                borderRadius: '8px',
                display: 'inline-block',
                lineHeight: 1.18,
                transition: 'all 0.18s cubic-bezier(0.2, 0.8, 0.2, 1)',
                opacity: isFaded ? (isDark ? 0.2 : 0.28) : 1,
                transform: isHovered ? 'scale(1.18)' : 'scale(1)',
                zIndex: isHovered ? 10 : 1,
                filter: isHovered
                  ? (isDark
                      ? `drop-shadow(0 0 12px ${tier.glow}) drop-shadow(0 0 20px ${tier.glow})`
                      : 'drop-shadow(0 4px 8px rgba(0, 0, 0, 0.12))')
                  : 'none',
                background: isHovered ? tier.bgHover : 'transparent',
                borderBottom: isHovered ? `2px solid ${tier.color}` : '2px solid transparent'
              }}
            >
              {word.keyword}
            </span>
          );
        })}

        {/* Tooltip Dinámico Flotante */}
        {hoveredWord && (
          <div
            style={{
              position: 'absolute',
              top: `${tooltipPos.y + 18}px`,
              left: `${Math.min(tooltipPos.x, containerRef.current?.offsetWidth ? containerRef.current.offsetWidth - 220 : tooltipPos.x)}px`,
              pointerEvents: 'none',
              background: isDark ? 'rgba(10, 17, 34, 0.95)' : 'rgba(255, 255, 255, 0.98)',
              backdropFilter: 'blur(12px)',
              border: isDark ? '1px solid var(--accent-cyan)' : '1px solid #0284c7',
              boxShadow: isDark ? '0 8px 24px rgba(0, 240, 255, 0.35)' : '0 10px 25px -3px rgba(2, 132, 199, 0.25), 0 4px 10px rgba(0, 0, 0, 0.06)',
              borderRadius: '10px',
              padding: '0.65rem 0.9rem',
              zIndex: 100,
              minWidth: '190px',
              color: isDark ? '#ffffff' : '#0f172a',
              animation: 'fadeIn 0.15s ease-out'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.35rem' }}>
              <Hash size={14} style={{ color: 'var(--accent-cyan)' }} />
              <strong style={{ fontSize: '0.88rem', color: isDark ? '#ffffff' : '#0f172a', letterSpacing: '-0.01em' }}>
                {hoveredWord.keyword}
              </strong>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', color: isDark ? '#94a3b8' : '#64748b', marginBottom: '0.4rem' }}>
              <span>Frecuencia:</span>
              <strong style={{ color: 'var(--accent-cyan)', fontSize: '0.85rem' }}>
                {hoveredWord.freq.toLocaleString()} apariciones
              </strong>
            </div>

            {/* Barra de Intensidad Relativa */}
            <div style={{ width: '100%', height: '5px', background: isDark ? 'rgba(255,255,255,0.1)' : '#e2e8f0', borderRadius: '3px', overflow: 'hidden' }}>
              <div
                style={{
                  width: `${Math.min(100, Math.round((hoveredWord.freq / maxFreq) * 100))}%`,
                  height: '100%',
                  background: 'linear-gradient(90deg, #0284c7, #818cf8)',
                  borderRadius: '3px'
                }}
              />
            </div>
            <div style={{ textAlign: 'right', fontSize: '0.68rem', color: isDark ? '#94a3b8' : '#64748b', marginTop: '0.2rem' }}>
              {((hoveredWord.freq / maxFreq) * 100).toFixed(1)}% del pico temático
            </div>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.75rem', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
        <span>Pasa el cursor sobre cualquier concepto para consultar su frecuencia y peso de co-ocurrencia científica.</span>
        <span>Mostrando {visibleWords.length} de {processedWords.length} términos</span>
      </div>
    </div>
  );
}
