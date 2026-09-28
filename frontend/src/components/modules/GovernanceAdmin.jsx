/**
 * frontend/src/components/modules/GovernanceAdmin.jsx
 * Módulo 5: Administración y Gobernanza Institucional
 */

import React, { useState } from 'react';
import { ShieldCheck, Check, X, Users, Link2, History } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';

export function GovernanceAdmin() {
  const t = useAppStore((state) => state.t)();
  const [activeSubTab, setActiveSubTab] = useState('requests');

  return (
    <div className="module-container" id="MODULO-05-ADMIN">
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.6rem', marginBottom: '0.25rem' }}>{t.governance.title}</h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
          Gestión de roles institucionales, aprobación de acreditaciones y mapeo de alias de instituciones.
        </p>

        {/* Sub-tabs */}
        <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1.25rem' }}>
          <button
            id="CTL-M05-001"
            className={`btn btn-sm ${activeSubTab === 'requests' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveSubTab('requests')}
          >
            <ShieldCheck size={14} />
            <span>{t.governance.pendingRequests}</span>
          </button>
          <button
            id="CTL-M05-002"
            className={`btn btn-sm ${activeSubTab === 'admins' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveSubTab('admins')}
          >
            <Users size={14} />
            <span>{t.governance.activeAdmins}</span>
          </button>
          <button
            id="CTL-M05-003"
            className={`btn btn-sm ${activeSubTab === 'aliases' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveSubTab('aliases')}
          >
            <Link2 size={14} />
            <span>{t.governance.institutionalAliases}</span>
          </button>
        </div>
      </div>

      <div className="glass-card">
        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', padding: '2rem 0' }}>
          {t.governance.noPending}
        </p>
      </div>
    </div>
  );
}

export default GovernanceAdmin;
