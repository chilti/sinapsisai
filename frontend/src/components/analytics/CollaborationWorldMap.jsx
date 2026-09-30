import React, { useMemo } from 'react';
import Plot from 'react-plotly.js';
import { Globe } from 'lucide-react';

export default function CollaborationWorldMap({ countries = [], title = "Mapa Mundi de Países Colaboradores" }) {
  const plotData = useMemo(() => {
    if (!Array.isArray(countries) || countries.length === 0) {
      return null;
    }

    const locations = [];
    const z = [];
    const text = [];

    countries.forEach(c => {
      if (c.iso_a3 && c.papers > 0) {
        locations.push(c.iso_a3);
        z.push(c.papers);
        text.push(`<b>${c.name || c.iso_a3}</b><br>${c.papers.toLocaleString()} artículos conjuntos`);
      }
    });

    if (locations.length === 0) return null;

    return [{
      type: 'choropleth',
      locationmode: 'ISO-3',
      locations: locations,
      z: z,
      text: text,
      hoverinfo: 'text',
      colorscale: [
        [0, '#0f172a'],
        [0.05, '#0369a1'],
        [0.2, '#0284c7'],
        [0.5, '#00f0ff'],
        [1.0, '#38bdf8']
      ],
      autocolorscale: false,
      marker: {
        line: {
          color: 'rgba(255,255,255,0.18)',
          width: 0.6
        }
      },
      colorbar: {
        title: {
          text: 'Papers',
          font: { color: '#94a3b8', size: 11 }
        },
        tickfont: { color: '#94a3b8', size: 10 },
        len: 0.75,
        thickness: 12
      }
    }];
  }, [countries]);

  const totalPartners = countries.length;
  const totalPapersCollab = countries.reduce((acc, c) => acc + (c.papers || 0), 0);

  return (
    <div className="glass-card" style={{ padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Globe size={18} style={{ color: 'var(--accent-cyan)' }} />
            🗺️ {title}
          </h3>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
            Cartografía global de coautoría internacional ({totalPartners} naciones colaboradoras registradas).
          </p>
        </div>
        {totalPartners > 0 && (
          <span className="badge badge-cyan" style={{ fontSize: '0.78rem', padding: '0.35rem 0.75rem' }}>
            {totalPartners} países · {totalPapersCollab.toLocaleString()} colaboraciones
          </span>
        )}
      </div>

      {plotData ? (
        <Plot
          data={plotData}
          layout={{
            height: 380,
            margin: { t: 10, b: 10, l: 10, r: 10 },
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            geo: {
              showframe: false,
              showcoastlines: true,
              coastlinecolor: 'rgba(255,255,255,0.15)',
              bgcolor: 'transparent',
              showland: true,
              landcolor: 'rgba(255,255,255,0.03)',
              showocean: true,
              oceancolor: 'rgba(0,0,0,0.2)',
              projection: {
                type: 'natural earth'
              }
            }
          }}
          config={{ responsive: true, displayModeBar: false }}
          style={{ width: '100%' }}
        />
      ) : (
        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)', fontSize: '0.88rem' }}>
          Sin datos suficientes de colaboración geográfica para desplegar el mapa mundi.
        </div>
      )}
    </div>
  );
}
