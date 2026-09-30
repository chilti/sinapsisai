import React, { useState, useMemo } from 'react';
import { Layers, ChevronDown, ChevronUp } from 'lucide-react';

const LEVEL_MAP = {
  'Dominio': 'domain',
  'Campo': 'field',
  'Subcampo': 'subfield',
  'Tópico': 'topic'
};

export default function ThematicEvolutionTable({ data = [], title = "Evolución Histórica de Perfiles de Conocimiento" }) {
  const [selectedLevel, setSelectedLevel] = useState('Dominio');
  const [showAllRows, setShowAllRows] = useState(false);

  // Procesar y pivotar datos
  const { years, rows, totalsByYear, grandTotal } = useMemo(() => {
    if (!Array.isArray(data) || data.length === 0) {
      return { years: [], rows: [], totalsByYear: {}, grandTotal: 0 };
    }

    const colKey = LEVEL_MAP[selectedLevel] || 'domain';
    const yearSet = new Set();
    const pivot = {}; // { themeName: { year: count } }

    data.forEach(item => {
      const theme = (item[colKey] || 'General').trim();
      const yr = parseInt(item.year, 10);
      const val = parseInt(item.value || 1, 10);

      if (theme && yr && yr >= 1970 && yr <= 2030) {
        yearSet.add(yr);
        if (!pivot[theme]) pivot[theme] = {};
        pivot[theme][yr] = (pivot[theme][yr] || 0) + val;
      }
    });

    const sortedYears = Array.from(yearSet).sort((a, b) => b - a); // Años descendentes
    const processedRows = Object.entries(pivot).map(([theme, countsByYear]) => {
      let total = 0;
      sortedYears.forEach(yr => {
        total += countsByYear[yr] || 0;
      });
      return {
        theme,
        countsByYear,
        total
      };
    });

    // Ordenar temas por volumen total descendente
    processedRows.sort((a, b) => b.total - a.total);

    // Totales por año
    const totalsByYear = {};
    let grandTotal = 0;
    sortedYears.forEach(yr => {
      const sumYr = processedRows.reduce((acc, r) => acc + (r.countsByYear[yr] || 0), 0);
      totalsByYear[yr] = sumYr;
      grandTotal += sumYr;
    });

    return { years: sortedYears, rows: processedRows, totalsByYear, grandTotal };
  }, [data, selectedLevel]);

  if (rows.length === 0) {
    return (
      <div className="glass-card" style={{ padding: '1.25rem' }}>
        <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <Layers size={18} style={{ color: 'var(--accent-cyan)' }} />
          📈 {title}
        </h3>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          Distribución anual del número de artículos por nivel temático de OpenAlex.
        </p>
        <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          Sin datos de evolución temática registrados para esta selección.
        </div>
      </div>
    );
  }

  const displayedRows = showAllRows ? rows : rows.slice(0, 15);

  return (
    <div className="glass-card" style={{ padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <Layers size={18} style={{ color: 'var(--accent-cyan)' }} />
            📈 {title}
          </h3>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
            Distribución anual de artículos por nivel taxonómico de OpenAlex (Total: {grandTotal.toLocaleString()} registros).
          </p>
        </div>

        {/* Selector de Nivel Temático */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', background: 'rgba(255,255,255,0.04)', padding: '0.25rem 0.4rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-secondary)', marginRight: '0.25rem' }}>Nivel:</span>
          {Object.keys(LEVEL_MAP).map(level => {
            const isSel = selectedLevel === level;
            return (
              <button
                key={level}
                onClick={() => setSelectedLevel(level)}
                style={{
                  padding: '0.3rem 0.65rem',
                  fontSize: '0.78rem',
                  fontWeight: isSel ? 700 : 500,
                  borderRadius: '6px',
                  border: 'none',
                  cursor: 'pointer',
                  background: isSel ? 'var(--accent-cyan)' : 'transparent',
                  color: isSel ? '#000000' : 'var(--text-secondary)',
                  transition: 'all 0.15s ease'
                }}
              >
                {level}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tabla con Scroll Horizontal */}
      <div style={{ overflowX: 'auto', maxHeight: '480px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', textAlign: 'right' }}>
          <thead>
            <tr style={{ background: 'rgba(255,255,255,0.05)', borderBottom: '2px solid var(--border-subtle)', position: 'sticky', top: 0, zIndex: 2 }}>
              <th style={{ textAlign: 'left', padding: '0.65rem 0.85rem', color: 'var(--text-primary)', fontWeight: 700, minWidth: '220px', background: 'var(--card-bg)' }}>
                {selectedLevel}
              </th>
              <th style={{ padding: '0.65rem 0.75rem', color: 'var(--accent-cyan)', fontWeight: 800, minWidth: '70px', background: 'var(--card-bg)' }}>
                Total
              </th>
              {years.map(yr => (
                <th key={yr} style={{ padding: '0.65rem 0.6rem', color: 'var(--text-secondary)', fontWeight: 600, minWidth: '55px', background: 'var(--card-bg)' }}>
                  {yr}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayedRows.map((r, idx) => (
              <tr
                key={r.theme}
                style={{
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                  background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)'
                }}
              >
                <td style={{ textAlign: 'left', padding: '0.55rem 0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {r.theme}
                </td>
                <td style={{ padding: '0.55rem 0.75rem', fontWeight: 800, color: 'var(--accent-cyan)' }}>
                  {r.total.toLocaleString()}
                </td>
                {years.map(yr => {
                  const val = r.countsByYear[yr] || 0;
                  return (
                    <td
                      key={yr}
                      style={{
                        padding: '0.55rem 0.6rem',
                        color: val > 0 ? 'var(--text-primary)' : 'var(--text-muted)',
                        opacity: val > 0 ? 1 : 0.4,
                        fontWeight: val > 0 ? 600 : 400
                      }}
                    >
                      {val > 0 ? val.toLocaleString() : '—'}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr style={{ background: 'rgba(0, 240, 255, 0.04)', borderTop: '2px solid var(--border-subtle)', fontWeight: 700, position: 'sticky', bottom: 0 }}>
              <td style={{ textAlign: 'left', padding: '0.65rem 0.85rem', color: 'var(--text-primary)' }}>
                Total General
              </td>
              <td style={{ padding: '0.65rem 0.75rem', color: 'var(--accent-cyan)', fontWeight: 800 }}>
                {grandTotal.toLocaleString()}
              </td>
              {years.map(yr => (
                <td key={yr} style={{ padding: '0.65rem 0.6rem', color: 'var(--text-primary)' }}>
                  {(totalsByYear[yr] || 0).toLocaleString()}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>

      {rows.length > 15 && (
        <div style={{ marginTop: '0.75rem', textAlign: 'center' }}>
          <button
            onClick={() => setShowAllRows(!showAllRows)}
            className="btn btn-outline"
            style={{ fontSize: '0.78rem', padding: '0.35rem 0.85rem', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}
          >
            {showAllRows ? (
              <>
                <ChevronUp size={14} /> Mostrar menos
              </>
            ) : (
              <>
                <ChevronDown size={14} /> Mostrar todos ({rows.length} {selectedLevel.toLowerCase()}s)
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
