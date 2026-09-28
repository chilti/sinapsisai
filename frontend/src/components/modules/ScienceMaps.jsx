/**
 * frontend/src/components/modules/ScienceMaps.jsx
 * Módulo 3: Mapas de la Ciencia y Espacios Semánticos
 */

import React, { useState, useEffect } from 'react';
import { Compass, Layers, RotateCcw, Filter, Sparkles } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';

export function ScienceMaps() {
  const t = useAppStore((state) => state.t)();
  const [spaces, setSpaces] = useState([]);
  const [selectedSpace, setSelectedSpace] = useState('preview');
  const [clusters, setClusters] = useState([]);

  useEffect(() => {
    async function loadSpaces() {
      try {
        const data = await apiClient.getMapSpaces();
        setSpaces(data.spaces || []);
      } catch (err) {
        console.error('Error cargando espacios:', err);
      }
    }
    loadSpaces();
  }, []);

  useEffect(() => {
    async function loadClusters() {
      try {
        const data = await apiClient.getMapClusters(selectedSpace);
        setClusters(data.clusters || []);
      } catch (err) {
        console.error('Error cargando clusters:', err);
      }
    }
    loadClusters();
  }, [selectedSpace]);

  return (
    <div className="module-container" id="MODULO-03-MAPAS">
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <h1 style={{ fontSize: '1.6rem', marginBottom: '0.25rem' }}>{t.maps.title}</h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Proyección Semántica Multidimensional (Nomic Embed v1.5 / SPECTER2 / UMAP)
            </p>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <label className="form-label" style={{ margin: 0 }}>{t.maps.spaceSelect}:</label>
            <select
              id="CTL-M03-001"
              className="form-select"
              style={{ width: 'auto' }}
              value={selectedSpace}
              onChange={(e) => setSelectedSpace(e.target.value)}
            >
              <option value="preview">{t.maps.previewModel}</option>
              <option value="nomic">{t.maps.nomicModel}</option>
              <option value="specter">{t.maps.specterModel}</option>
            </select>
          </div>
        </div>
      </div>

      {/* Visor Cartográfico Canvas / WebGL Placeholder */}
      <div className="glass-card" style={{ height: '520px', display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem', zIndex: 10 }}>
          <span className="badge badge-cyan">WebGL Space: {selectedSpace.toUpperCase()}</span>
          <button id="CTL-M03-008" className="btn btn-secondary btn-sm" style={{ padding: '0.3rem 0.6rem' }}>
            <RotateCcw size={13} />
            <span>{t.maps.resetZoom}</span>
          </button>
        </div>

        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          background: 'radial-gradient(circle, rgba(15, 23, 42, 0.9) 0%, rgba(7, 9, 14, 0.98) 100%)',
          borderRadius: '8px', border: '1px dashed rgba(255, 255, 255, 0.1)', padding: '2rem', textAlign: 'center'
        }}>
          <Compass size={48} style={{ color: 'var(--accent-cyan)', marginBottom: '1rem', opacity: 0.8 }} />
          <h3 style={{ fontSize: '1.2rem', marginBottom: '0.5rem' }}>
            Lienzo Cartográfico de la Ciencia Activo
          </h3>
          <p style={{ color: 'var(--text-secondary)', maxWidth: '500px', fontSize: '0.85rem' }}>
            Espacio de partículas semánticas listo. La vista interactiva WebGL 2D/3D se montará con aceleración por hardware en la Fase 3.
          </p>
        </div>
      </div>
    </div>
  );
}

export default ScienceMaps;
