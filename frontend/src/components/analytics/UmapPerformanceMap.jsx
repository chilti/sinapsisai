import React, { useState, useEffect, useMemo } from 'react';
import Plot from 'react-plotly.js';
import { Target, Sparkles, Filter } from 'lucide-react';

const METRIC_OPTIONS = [
  { label: 'Impacto (FWCI)', key: 'fwci_avg', defaultScale: 2.0 },
  { label: 'Documentos', key: 'num_documents', defaultScale: 50 },
  { label: 'Excelencia (% Top 10)', key: 'pct_top_10', defaultScale: 25.0 },
  { label: 'Citas Totales', key: 'citations', defaultScale: 500 }
];

export default function UmapPerformanceMap({
  academicName = "",
  entityName = "",
  institutionName = "UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)",
  viewMode = "capacidad_instalada"
}) {
  const [data, setData] = useState({ entity: { points: [] }, institution: { points: [] } });
  const [loading, setLoading] = useState(true);
  const [sizeMetric, setSizeMetric] = useState('fwci_avg');

  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    const params = new URLSearchParams({
      name: academicName,
      institution: institutionName,
      view_mode: viewMode
    });
    if (entityName) params.append('entity', entityName);

    fetch(`/api/academics/umap?${params.toString()}`)
      .then(res => res.json())
      .then(json => {
        if (isMounted && json.status === 'success') {
          setData(json);
        }
      })
      .catch(err => console.error("Error fetching UMAP:", err))
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => { isMounted = false; };
  }, [academicName, entityName, institutionName, viewMode]);

  const createPlotTraces = (points = [], contextTitle = "") => {
    if (!points || points.length === 0) return null;

    const metricConfig = METRIC_OPTIONS.find(m => m.key === sizeMetric) || METRIC_OPTIONS[0];

    const peers = points.filter(p => !p.is_selected);
    const selected = points.find(p => p.is_selected);

    // Calcular escala de burbuja
    const values = points.map(p => p[sizeMetric] || 0.1);
    const maxVal = Math.max(...values, 1.0);

    const getMarkerSize = (val) => {
      const norm = Math.min(Math.max((val || 0.1) / maxVal, 0.05), 1.0);
      return 6 + Math.sqrt(norm) * 18;
    };

    const traces = [];

    // Traza de Pares Académicos
    if (peers.length > 0) {
      traces.push({
        x: peers.map(p => p.x),
        y: peers.map(p => p.y),
        mode: 'markers',
        type: 'scatter',
        name: 'Pares Académicos',
        text: peers.map(p => 
          `<b>${p.name}</b><br>` +
          `Docs: ${p.num_documents} · FWCI: ${p.fwci_avg}<br>` +
          `Top 10%: ${p.pct_top_10}% · Citas: ${p.citations.toLocaleString()}`
        ),
        hoverinfo: 'text',
        marker: {
          size: peers.map(p => getMarkerSize(p[sizeMetric])),
          color: peers.map(p => p.fwci_avg || 1.0),
          colorscale: 'Blues',
          showscale: false,
          opacity: 0.7,
          line: { color: 'rgba(255,255,255,0.2)', width: 0.5 }
        }
      });
    }

    // Traza del Investigador Destacado
    if (selected) {
      traces.push({
        x: [selected.x],
        y: [selected.y],
        mode: 'markers+text',
        type: 'scatter',
        name: academicName,
        text: [academicName],
        textposition: 'top center',
        textfont: { color: '#00f0ff', size: 12, weight: 800 },
        hoverinfo: 'text',
        hovertext: [
          `⭐ <b>${selected.name} (Evaluado)</b><br>` +
          `Docs: ${selected.num_documents} · FWCI: ${selected.fwci_avg}<br>` +
          `Top 10%: ${selected.pct_top_10}% · Citas: ${selected.citations.toLocaleString()}`
        ],
        marker: {
          size: Math.max(getMarkerSize(selected[sizeMetric]) * 1.5, 18),
          color: '#00f0ff',
          symbol: 'diamond',
          line: { color: '#ffffff', width: 2 }
        }
      });
    }

    return traces;
  };

  const defaultLayout = {
    height: 380,
    margin: { t: 30, b: 35, l: 35, r: 20 },
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    showlegend: false,
    xaxis: { showgrid: true, gridcolor: 'rgba(255,255,255,0.06)', zeroline: false },
    yaxis: { showgrid: true, gridcolor: 'rgba(255,255,255,0.06)', zeroline: false }
  };

  return (
    <div className="glass-card" style={{ padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.25rem' }}>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.3rem' }}>
            <Target size={18} style={{ color: 'var(--accent-cyan)' }} />
            🎯 Mapas de Desempeño (UMAP)
          </h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, maxWidth: '850px' }}>
            Cálculo multidimensional comparando %Top 10, FWCI, % Top 1% y Percentil Promedio frente a sus pares académicos.
            Proyección del investigador en su dependencia de adscripción y en el contexto de la institución completa.
          </p>
        </div>

        {/* Selector de Tamaño de Burbuja */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(255,255,255,0.03)', padding: '0.35rem 0.65rem', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
          <Filter size={14} style={{ color: 'var(--accent-cyan)' }} />
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Tamaño de burbuja:</span>
          <select
            className="form-select"
            value={sizeMetric}
            onChange={(e) => setSizeMetric(e.target.value)}
            style={{ width: 'auto', padding: '0.25rem 0.6rem', fontSize: '0.78rem' }}
          >
            {METRIC_OPTIONS.map(m => (
              <option key={m.key} value={m.key}>{m.label}</option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
          <Sparkles size={24} className="animate-spin" style={{ color: 'var(--accent-cyan)', marginBottom: '0.5rem' }} />
          <p>Cargando mapas UMAP multidimensionales...</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.5rem' }}>
          {/* 1. Contexto de la Entidad o Dependencia */}
          <div className="glass-card" style={{ padding: '1rem', background: 'rgba(255,255,255,0.02)' }}>
            <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--accent-cyan)', marginBottom: '0.25rem' }}>
              🏢 Contexto de la Entidad: {data?.entity?.name || entityName || 'Dependencia'}
            </h4>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {data?.entity?.count || 0} pares académicos evaluados en la facultad
            </span>
            {createPlotTraces(data?.entity?.points) ? (
              <Plot
                data={createPlotTraces(data?.entity?.points)}
                layout={{ ...defaultLayout }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            ) : (
              <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                Sin proyección UMAP calculada para la entidad.
              </div>
            )}
          </div>

          {/* 2. Contexto de la Institución Completa */}
          <div className="glass-card" style={{ padding: '1rem', background: 'rgba(255,255,255,0.02)' }}>
            <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#f59e0b', marginBottom: '0.25rem' }}>
              🏛️ Contexto Institucional: {data?.institution?.name || institutionName}
            </h4>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {data?.institution?.count || 0} investigadoras e investigadores en el universo institucional
            </span>
            {createPlotTraces(data?.institution?.points) ? (
              <Plot
                data={createPlotTraces(data?.institution?.points)}
                layout={{ ...defaultLayout }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            ) : (
              <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                Sin proyección UMAP calculada para la institución.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
