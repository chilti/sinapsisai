/**
 * frontend/src/components/modules/MyResearcherSpace.jsx
 * Módulo 4: Mi Espacio de Investigador (Curación, Acreditación y Dossier)
 */

import React, { useState } from 'react';
import { UserCheck, Shield, FileText, CheckCircle, AlertCircle, LogIn, Send } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';

export function MyResearcherSpace() {
  const t = useAppStore((state) => state.t)();
  const userSession = useAppStore((state) => state.userSession);
  const selectedInstitution = useAppStore((state) => state.selectedInstitution);
  const selectedDependency = useAppStore((state) => state.selectedDependency);

  const [position, setPosition] = useState('');
  const [email, setEmail] = useState('');
  const [notes, setNotes] = useState('');
  const [statusMsg, setStatusMsg] = useState(null);

  // La institución/dependencia para la solicitud se fija en el nivel jerárquico más bajo
  const lowestUnit = selectedDependency || selectedInstitution;

  const handleRequestAccreditation = async (e) => {
    e.preventDefault();
    if (!lowestUnit) return;

    try {
      const payload = {
        user_orcid: userSession.orcid || '0000-0003-3659-6769',
        user_name: userSession.name || 'HUMBERTO CARRILLO CALVET',
        institution_name: lowestUnit,
        institutional_email: email,
        position: position,
        notes: notes
      };
      await apiClient.submitAccreditation(payload);
      setStatusMsg({ type: 'success', text: `Solicitud enviada exitosamente para ${lowestUnit}. En espera de revisión por el Super Administrador.` });
    } catch (err) {
      setStatusMsg({ type: 'error', text: err.response?.data?.detail || 'Error al enviar la solicitud.' });
    }
  };

  return (
    <div className="module-container" id="MODULO-04-MI-ESPACIO">
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.6rem', marginBottom: '0.25rem' }}>{t.mySpace.title}</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
          Gestión personalizada de trayectoria, validación de autorías y solicitudes de gobernanza.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '1.5rem' }}>
        {/* Formulario de Acreditación Jerárquica */}
        <div className="glass-card" id="CTL-M04-006">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
            <Shield size={20} style={{ color: 'var(--accent-cyan)' }} />
            <h3 style={{ fontSize: '1.15rem' }}>{t.mySpace.accreditationTitle}</h3>
          </div>

          <div style={{
            background: 'rgba(0, 242, 254, 0.06)', border: '1px solid rgba(0, 242, 254, 0.2)',
            borderRadius: '8px', padding: '0.85rem', marginBottom: '1rem', fontSize: '0.8rem', color: '#e2e8f0'
          }}>
            <p><strong>Directriz de Gobernanza Institucional:</strong></p>
            <p style={{ marginTop: '0.25rem' }}>{t.mySpace.accreditationNotice}</p>
            <div style={{ marginTop: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <span className="badge badge-cyan">Unidad Elegible:</span>
              <strong style={{ color: '#00f2fe' }}>{lowestUnit}</strong>
            </div>
          </div>

          <form onSubmit={handleRequestAccreditation}>
            <div style={{ marginBottom: '1rem' }}>
              <label className="form-label">Cargo Institucional</label>
              <input
                id="CTL-M04-008"
                type="text"
                className="form-input"
                required
                placeholder={t.mySpace.positionPlaceholder}
                value={position}
                onChange={(e) => setPosition(e.target.value)}
              />
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label className="form-label">Correo Institucional</label>
              <input
                id="CTL-M04-009"
                type="email"
                className="form-input"
                required
                placeholder={t.mySpace.emailPlaceholder}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div style={{ marginBottom: '1.25rem' }}>
              <label className="form-label">Notas Adicionales</label>
              <textarea
                id="CTL-M04-010"
                className="form-input"
                rows={3}
                placeholder="Indique justificación de la solicitud..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>

            <button id="CTL-M04-011" type="submit" className="btn btn-primary" style={{ width: '100%' }}>
              <Send size={15} />
              <span>{t.mySpace.requestAccreditationBtn}</span>
            </button>
          </form>

          {statusMsg && (
            <div style={{
              marginTop: '1rem', padding: '0.75rem', borderRadius: '6px', fontSize: '0.82rem',
              background: statusMsg.type === 'success' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
              border: `1px solid ${statusMsg.type === 'success' ? '#10b981' : '#f43f5e'}`,
              color: statusMsg.type === 'success' ? '#34d399' : '#fb7185'
            }}>
              {statusMsg.text}
            </div>
          )}
        </div>

        {/* Panel de Dossier y Curación */}
        <div className="glass-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
            <FileText size={20} style={{ color: 'var(--accent-purple)' }} />
            <h3 style={{ fontSize: '1.15rem' }}>{t.mySpace.curationTitle}</h3>
          </div>

          <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '1rem' }}>
            Auditoría de autorías asignadas automáticamente por algoritmos de desambiguación y validación cruzada.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <button id="CTL-M04-012" className="btn btn-secondary" style={{ justifyContent: 'flex-start' }}>
              <span>📄 Ver Lista de Obras Desvinculadas</span>
            </button>
            <button id="CTL-M04-016" className="btn btn-secondary" style={{ justifyContent: 'flex-start' }}>
              <span>📥 Cargar Archivo BibTeX (.bib)</span>
            </button>
            <button id="CTL-M04-023" className="btn btn-primary" style={{ justifyContent: 'flex-start', marginTop: '0.5rem' }}>
              <span>🏆 {t.mySpace.generateDossier}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default MyResearcherSpace;
