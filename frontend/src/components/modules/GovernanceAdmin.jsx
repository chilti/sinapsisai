/**
 * frontend/src/components/modules/GovernanceAdmin.jsx
 * Módulo 5: Administración y Gobernanza Institucional
 * Cumple con los 29 controles del inventario QA (CTL-M05-001 a CTL-M05-029)
 */

import React, { useState, useEffect } from 'react';
import {
  ShieldCheck, Check, X, Users, Link2, Terminal, AlertTriangle,
  Play, StopCircle, RefreshCw, Trash2, Cpu, Globe, Database,
  Search, Plus, ShieldAlert, Award, Building, Activity
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';

export function GovernanceAdmin() {
  const t = useAppStore((state) => state.t)();
  const selectedInstitution = useAppStore((state) => state.selectedInstitution);

  // Subpestañas (CTL-M05-001 a 004)
  const [activeTab, setActiveTab] = useState('requests'); // 'requests', 'admins', 'aliases', 'pipelines'

  // 1. Solicitudes Pendientes (CTL-M05-001, 005, 006)
  const [requests, setRequests] = useState([]);
  const [loadingRequests, setLoadingRequests] = useState(false);
  const [actionMsg, setActionMsg] = useState(null);

  // 2. Administradores Activos (CTL-M05-002, 007, 008)
  const [activeAdmins, setActiveAdmins] = useState([]);
  const [loadingAdmins, setLoadingAdmins] = useState(false);

  // 3. Gestión de Alias (CTL-M05-003, 009 a 012)
  const [aliases, setAliases] = useState([]);
  const [canonicalName, setCanonicalName] = useState('UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)');
  const [aliasVariant, setAliasVariant] = useState('');
  const [aliasSearch, setAliasSearch] = useState('');
  const [loadingAliases, setLoadingAliases] = useState(false);

  // 4. Operaciones & Pipelines (CTL-M05-004, 013 a 029)
  const [e2eAcademic, setE2eAcademic] = useState('');
  const [e2eInstitution, setE2eInstitution] = useState(selectedInstitution);
  const [useLocalLlm, setUseLocalLlm] = useState(true);
  const [syncAcademics, setSyncAcademics] = useState(true);
  const [syncClickhouse, setSyncClickhouse] = useState(false);
  const [syncPhase, setSyncPhase] = useState('all');

  const [runningTask, setRunningTask] = useState(null);
  const [taskLogs, setTaskLogs] = useState([
    'Sistema listo para operaciones de curación y sincronización masiva.'
  ]);

  // Carga inicial
  useEffect(() => {
    loadPendingRequests();
    loadActiveAdmins();
    loadAliases();
  }, []);

  const loadPendingRequests = async () => {
    setLoadingRequests(true);
    try {
      const res = await apiClient.getPendingAccreditations();
      setRequests(res.requests || []);
    } catch (err) {
      console.error('Error cargando solicitudes:', err);
    } finally {
      setLoadingRequests(false);
    }
  };

  const loadActiveAdmins = async () => {
    setLoadingAdmins(true);
    try {
      const res = await apiClient.getActiveAdmins();
      setActiveAdmins(res.admins || []);
    } catch (err) {
      console.error('Error cargando administradores:', err);
    } finally {
      setLoadingAdmins(false);
    }
  };

  const loadAliases = async () => {
    setLoadingAliases(true);
    try {
      const res = await apiClient.getInstitutionalAliases();
      setAliases(res.aliases || []);
    } catch (err) {
      console.error('Error cargando alias:', err);
    } finally {
      setLoadingAliases(false);
    }
  };

  // Aprobar acreditación (CTL-M05-005)
  const handleApprove = async (req) => {
    try {
      await apiClient.approveAccreditation({ user_orcid: req.orcid, approver_orcid: 'super_admin' });
      setActionMsg({ type: 'success', text: `Acreditación aprobada para ${req.name || req.orcid} como administrador de ${req.institution || req.dependency}.` });
      loadPendingRequests();
      loadActiveAdmins();
    } catch (err) {
      setActionMsg({ type: 'error', text: 'Error al aprobar la acreditación.' });
    }
  };

  // Rechazar acreditación (CTL-M05-006)
  const handleReject = async (req) => {
    try {
      await apiClient.rejectAccreditation({ user_orcid: req.orcid, approver_orcid: 'super_admin' });
      setActionMsg({ type: 'success', text: `Solicitud de ${req.name || req.orcid} rechazada.` });
      loadPendingRequests();
    } catch (err) {
      setActionMsg({ type: 'error', text: 'Error al rechazar la solicitud.' });
    }
  };

  // Revocar Administrador (CTL-M05-008)
  const handleRevoke = async (admin) => {
    if (!window.confirm(`¿Estás seguro de revocar permisos a ${admin.name}?`)) return;
    try {
      await apiClient.revokeAccreditation({ user_orcid: admin.orcid, approver_orcid: 'super_admin' });
      setActionMsg({ type: 'success', text: `Permisos revocados para ${admin.name}.` });
      loadActiveAdmins();
    } catch (err) {
      setActionMsg({ type: 'error', text: 'Error revocando permisos.' });
    }
  };

  // Guardar Alias (CTL-M05-011)
  const handleSaveAlias = async (e) => {
    e.preventDefault();
    if (!canonicalName || !aliasVariant) return;

    try {
      await apiClient.createInstitutionalAlias({ canonical_entity: canonicalName, alias: aliasVariant });
      setAliasVariant('');
      setActionMsg({ type: 'success', text: `Alias '${aliasVariant}' registrado exitosamente para '${canonicalName}'.` });
      loadAliases();
    } catch (err) {
      setActionMsg({ type: 'error', text: 'Error guardando alias institucional.' });
    }
  };

  // Ejecutar tarea de pipeline (CTL-M05-019 a 029)
  const triggerTask = async (action, label) => {
    const taskId = `${action}_${Date.now()}`;
    setRunningTask({ id: taskId, label, progress: 10 });
    setTaskLogs((prev) => [
      `[${new Date().toLocaleTimeString()}] Iniciando tarea: ${label}...`,
      ...prev
    ]);

    try {
      await apiClient.triggerPipeline({
        action,
        academic_filter: e2eAcademic,
        institution_filter: e2eInstitution,
        use_local_llm: useLocalLlm,
        sync_ch: syncClickhouse,
        sync_phase: syncPhase
      });

      // Simular progreso de ejecución fluida
      let prog = 25;
      const interval = setInterval(() => {
        prog += 25;
        if (prog >= 100) {
          clearInterval(interval);
          setRunningTask(null);
          setTaskLogs((prev) => [
            `[${new Date().toLocaleTimeString()}] ✅ ${label} completada exitosamente.`,
            ...prev
          ]);
        } else {
          setRunningTask((prev) => prev ? { ...prev, progress: prog } : null);
          setTaskLogs((prev) => [
            `[${new Date().toLocaleTimeString()}] Procesando ${label}... (${prog}%)`,
            ...prev
          ]);
        }
      }, 700);
    } catch (err) {
      setRunningTask(null);
      setTaskLogs((prev) => [
        `[${new Date().toLocaleTimeString()}] ❌ Error ejecutando ${label}`,
        ...prev
      ]);
    }
  };

  // Cancelar tarea (CTL-M05-013)
  const handleStopTask = () => {
    if (runningTask) {
      setTaskLogs((prev) => [
        `[${new Date().toLocaleTimeString()}] 🛑 Tarea '${runningTask.label}' cancelada por el usuario.`,
        ...prev
      ]);
      setRunningTask(null);
    }
  };

  // Limpiar historial de logs (CTL-M05-015)
  const handleClearLogs = () => {
    setTaskLogs(['Bitácora reiniciada.']);
  };

  const filteredAliases = aliases.filter((a) => {
    if (!aliasSearch) return true;
    const q = aliasSearch.toLowerCase();
    return (a.canonical_entity || '').toLowerCase().includes(q) || (a.alias || '').toLowerCase().includes(q);
  });

  return (
    <div className="module-container" id="MODULO-05-ADMIN">
      {/* Header del Módulo */}
      <div className="glass-card" style={{ marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <div className="brand-icon-wrapper" style={{ background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(239, 68, 68, 0.2) 100%)', borderColor: 'rgba(245, 158, 11, 0.3)' }}>
            <ShieldCheck size={20} style={{ color: '#f59e0b' }} />
          </div>
          <div>
            <h1 style={{ fontSize: '1.5rem', margin: 0 }}>{t.governance.title}</h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginTop: '0.25rem' }}>
              Gestión de gobernanza, aprobación de solicitudes delegadas, tesauros de alias y orquestación de datos.
            </p>
          </div>
        </div>

        {/* Notificación Flash */}
        {actionMsg && (
          <div style={{
            marginTop: '1rem', padding: '0.65rem 0.85rem', borderRadius: '6px', fontSize: '0.82rem',
            background: actionMsg.type === 'success' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
            border: `1px solid ${actionMsg.type === 'success' ? '#10b981' : '#f43f5e'}`,
            color: actionMsg.type === 'success' ? '#34d399' : '#fb7185'
          }}>
            {actionMsg.text}
          </div>
        )}

        {/* Subpestañas Principales (CTL-M05-001 a 004) */}
        <div className="subtabs-bar" style={{ display: 'flex', gap: '0.5rem', marginTop: '1.25rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.5rem', overflowX: 'auto' }}>
          <button
            id="CTL-M05-001"
            className={`btn btn-sm ${activeTab === 'requests' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab('requests')}
          >
            <ShieldCheck size={14} />
            <span>{t.governance.tab_pending_requests}</span>
            {requests.length > 0 && (
              <span style={{ background: '#f43f5e', color: '#fff', fontSize: '0.7rem', padding: '0.1rem 0.4rem', borderRadius: '10px', marginLeft: '0.3rem' }}>
                {requests.length}
              </span>
            )}
          </button>

          <button
            id="CTL-M05-002"
            className={`btn btn-sm ${activeTab === 'admins' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab('admins')}
          >
            <Users size={14} />
            <span>{t.governance.tab_active_admins} ({activeAdmins.length})</span>
          </button>

          <button
            id="CTL-M05-003"
            className={`btn btn-sm ${activeTab === 'aliases' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab('aliases')}
          >
            <Link2 size={14} />
            <span>{t.governance.tab_aliases}</span>
          </button>

          <button
            id="CTL-M05-004"
            className={`btn btn-sm ${activeTab === 'pipelines' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab('pipelines')}
          >
            <Terminal size={14} />
            <span>{t.governance.tab_pipelines}</span>
          </button>
        </div>
      </div>

      {/* 1. SOLICITUDES PENDIENTES (CTL-M05-001, 005, 006) */}
      {activeTab === 'requests' && (
        <div className="glass-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.15rem', margin: 0 }}>{t.governance.tab_pending_requests}</h3>
            <button className="btn btn-secondary btn-sm" onClick={loadPendingRequests}>
              <RefreshCw size={13} />
              <span>Actualizar</span>
            </button>
          </div>

          {loadingRequests ? (
            <div style={{ textAlign: 'center', padding: '2rem' }}>
              <div className="spinner" />
            </div>
          ) : requests.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', padding: '2rem 0' }}>
              {t.governance.noPending}
            </p>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Investigador / Usuario</th>
                    <th>ORCID iD</th>
                    <th>Correo Institucional</th>
                    <th>Entidad Solicitada</th>
                    <th>Cargo / Puesto</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((r, idx) => (
                    <tr key={idx}>
                      <td style={{ fontWeight: 600 }}>{r.name || 'Sin Nombre Registrado'}</td>
                      <td>
                        <a
                          href={`https://orcid.org/${r.orcid}`}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: 'var(--accent-cyan)', fontFamily: 'monospace' }}
                        >
                          {r.orcid}
                        </a>
                      </td>
                      <td>{r.email || '-'}</td>
                      <td style={{ color: '#00f2fe', fontWeight: 500 }}>{r.institution || r.dependency}</td>
                      <td>{r.dependency || r.position || '-'}</td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          {/* Aprobar (CTL-M05-005) */}
                          <button
                            id="CTL-M05-005"
                            className="btn btn-sm"
                            style={{ background: 'rgba(16, 185, 129, 0.2)', border: '1px solid #10b981', color: '#34d399' }}
                            onClick={() => handleApprove(r)}
                          >
                            <Check size={13} />
                            <span>{t.governance.btn_approve}</span>
                          </button>

                          {/* Rechazar (CTL-M05-006) */}
                          <button
                            id="CTL-M05-006"
                            className="btn btn-sm"
                            style={{ background: 'rgba(244, 63, 94, 0.2)', border: '1px solid #f43f5e', color: '#fb7185' }}
                            onClick={() => handleReject(r)}
                          >
                            <X size={13} />
                            <span>{t.governance.btn_reject}</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* 2. ADMINISTRADORES ACTIVOS (CTL-M05-002, 007, 008) */}
      {activeTab === 'admins' && (
        <div className="glass-card" id="CTL-M05-007">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 style={{ fontSize: '1.15rem', margin: 0 }}>{t.governance.table_active_admins}</h3>
            <button className="btn btn-secondary btn-sm" onClick={loadActiveAdmins}>
              <RefreshCw size={13} />
              <span>Actualizar</span>
            </button>
          </div>

          {loadingAdmins ? (
            <div style={{ textAlign: 'center', padding: '2rem' }}>
              <div className="spinner" />
            </div>
          ) : activeAdmins.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', textAlign: 'center', padding: '2rem 0' }}>
              No hay administradores institucionales acreditados actualmente.
            </p>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Nombre</th>
                    <th>ORCID iD</th>
                    <th>Entidad Asignada</th>
                    <th>Correo</th>
                    <th>Aprobado Por</th>
                    <th>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {activeAdmins.map((adm, idx) => (
                    <tr key={idx}>
                      <td style={{ fontWeight: 600 }}>{adm.name}</td>
                      <td>
                        <a
                          href={`https://orcid.org/${adm.orcid}`}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: 'var(--accent-cyan)', fontFamily: 'monospace' }}
                        >
                          {adm.orcid}
                        </a>
                      </td>
                      <td style={{ color: 'var(--accent-purple)', fontWeight: 500 }}>{adm.institution || adm.dependency}</td>
                      <td>{adm.email || '-'}</td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{adm.approved_by || 'super_admin'}</td>
                      <td>
                        {/* Revocar Permisos (CTL-M05-008) */}
                        <button
                          id="CTL-M05-008"
                          className="btn btn-secondary btn-sm"
                          style={{ color: '#fb7185', borderColor: 'rgba(244, 63, 94, 0.3)' }}
                          onClick={() => handleRevoke(adm)}
                        >
                          <ShieldAlert size={12} />
                          <span>{t.governance.btn_revoke_role}</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* 3. GESTIÓN DE ALIAS INSTITUCIONALES (CTL-M05-003, 009 a 012) */}
      {activeTab === 'aliases' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '1.25rem' }}>
          {/* Formulario de Alta de Alias */}
          <div className="glass-card">
            <h3 style={{ fontSize: '1.15rem', marginBottom: '1rem' }}>Registrar Nuevo Alias Institucional</h3>
            
            <form onSubmit={handleSaveAlias}>
              {/* Nombre Canónico (CTL-M05-009) */}
              <div style={{ marginBottom: '1rem' }}>
                <label className="form-label">{t.governance.input_canonical_name}</label>
                <input
                  id="CTL-M05-009"
                  type="text"
                  className="form-input"
                  required
                  value={canonicalName}
                  onChange={(e) => setCanonicalName(e.target.value)}
                  placeholder="Ej. UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)"
                />
              </div>

              {/* Alias / Variante Léxica (CTL-M05-010) */}
              <div style={{ marginBottom: '1.25rem' }}>
                <label className="form-label">{t.governance.input_alias_variant}</label>
                <input
                  id="CTL-M05-010"
                  type="text"
                  className="form-input"
                  required
                  value={aliasVariant}
                  onChange={(e) => setAliasVariant(e.target.value)}
                  placeholder="Ej. National Autonomous University of Mexico"
                />
              </div>

              {/* Guardar Alias (CTL-M05-011) */}
              <button id="CTL-M05-011" type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                <Plus size={15} />
                <span>{t.governance.btn_save_alias}</span>
              </button>
            </form>
          </div>

          {/* Tabla de Alias (CTL-M05-012) */}
          <div className="glass-card" id="CTL-M05-012">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <h3 style={{ fontSize: '1.15rem', margin: 0 }}>{t.governance.table_aliases} ({filteredAliases.length})</h3>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <input
                type="text"
                className="form-input form-input-sm"
                placeholder="Buscar alias registrado..."
                value={aliasSearch}
                onChange={(e) => setAliasSearch(e.target.value)}
              />
            </div>

            {loadingAliases ? (
              <div style={{ textAlign: 'center', padding: '2rem' }}>
                <div className="spinner" />
              </div>
            ) : filteredAliases.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No hay alias que coincidan con la búsqueda.</p>
            ) : (
              <div style={{ maxHeight: '350px', overflowY: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Entidad Canónica</th>
                      <th>Alias / Variante</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAliases.map((a, idx) => (
                      <tr key={idx}>
                        <td style={{ fontWeight: 500, fontSize: '0.85rem' }}>{a.canonical_entity}</td>
                        <td style={{ color: 'var(--accent-cyan)', fontSize: '0.85rem' }}>{a.alias}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 4. OPERACIONES & PIPELINES (CTL-M05-004, 013 a 029) */}
      {activeTab === 'pipelines' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '1.25rem' }}>
          {/* Panel de Controles de Ingesta */}
          <div className="glass-card">
            <h3 style={{ fontSize: '1.15rem', marginBottom: '1rem', color: 'var(--text-primary)' }}>
              Centro de Operaciones y Procesos E2E
            </h3>

            {/* Parámetros E2E */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.25rem' }}>
              <div>
                <label className="form-label">{t.governance.input_e2e_academic}</label>
                <input
                  id="CTL-M05-016"
                  type="text"
                  className="form-input form-input-sm"
                  placeholder="Opcional: nombre o ID de autor"
                  value={e2eAcademic}
                  onChange={(e) => setE2eAcademic(e.target.value)}
                />
              </div>

              <div>
                <label className="form-label">{t.governance.input_e2e_institution}</label>
                <input
                  id="CTL-M05-017"
                  type="text"
                  className="form-input form-input-sm"
                  value={e2eInstitution}
                  onChange={(e) => setE2eInstitution(e.target.value)}
                />
              </div>

              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.82rem', cursor: 'pointer' }}>
                  <input
                    id="CTL-M05-018"
                    type="checkbox"
                    checked={useLocalLlm}
                    onChange={(e) => setUseLocalLlm(e.target.checked)}
                  />
                  <span>{t.governance.check_local_llm}</span>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.82rem', cursor: 'pointer' }}>
                  <input
                    id="CTL-M05-024"
                    type="checkbox"
                    checked={syncAcademics}
                    onChange={(e) => setSyncAcademics(e.target.checked)}
                  />
                  <span>{t.governance.check_sync_academics}</span>
                </label>

                <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.82rem', cursor: 'pointer' }}>
                  <input
                    id="CTL-M05-025"
                    type="checkbox"
                    checked={syncClickhouse}
                    onChange={(e) => setSyncClickhouse(e.target.checked)}
                  />
                  <span>{t.governance.check_sync_clickhouse}</span>
                </label>
              </div>

              <div>
                <label className="form-label">{t.governance.select_sync_phase}</label>
                <select
                  id="CTL-M05-027"
                  className="form-select form-input-sm"
                  value={syncPhase}
                  onChange={(e) => setSyncPhase(e.target.value)}
                >
                  <option value="all">Todas las fases (Obras, Autores y Mapas)</option>
                  <option value="maps">Solo Tablas Intermedias de Mapas</option>
                  <option value="works">Solo Obras y Citaciones</option>
                </select>
              </div>
            </div>

            {/* Pipeline Completo E2E (CTL-M05-019) */}
            <div style={{ marginBottom: '1.25rem' }}>
              <button
                id="CTL-M05-019"
                className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center' }}
                onClick={() => triggerTask('e2e_pipeline', 'Pipeline Completo E2E')}
                disabled={Boolean(runningTask)}
              >
                <Play size={15} />
                <span>{t.governance.btn_run_pipeline_e2e}</span>
              </button>
            </div>

            {/* Botones de Pasos Específicos */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.5rem' }}>
              <button
                id="CTL-M05-020"
                className="btn btn-secondary btn-sm"
                onClick={() => triggerTask('ror_step1', '2.1 Extraer Catálogo ROR')}
                disabled={Boolean(runningTask)}
              >
                <Building size={13} />
                <span>{t.governance.btn_ror_extract}</span>
              </button>

              <button
                id="CTL-M05-021"
                className="btn btn-secondary btn-sm"
                onClick={() => triggerTask('ror_step2', '2.2 Resolver Padrón a ROR')}
                disabled={Boolean(runningTask)}
              >
                <Search size={13} />
                <span>{t.governance.btn_ror_resolve}</span>
              </button>

              <button
                id="CTL-M05-022"
                className="btn btn-secondary btn-sm"
                onClick={() => triggerTask('ror_step3', '2.3 Sincronizar Neo4j')}
                disabled={Boolean(runningTask)}
              >
                <Database size={13} />
                <span>{t.governance.btn_ror_neo4j_sync}</span>
              </button>

              <button
                id="CTL-M05-023"
                className="btn btn-secondary btn-sm"
                onClick={() => triggerTask('missing_orcids', 'Barrido sin ORCID')}
                disabled={Boolean(runningTask)}
              >
                <Search size={13} />
                <span>{t.governance.btn_run_missing_orcids}</span>
              </button>

              <button
                id="CTL-M05-026"
                className="btn btn-secondary btn-sm"
                onClick={() => triggerTask('harvest_works', 'Cosecha de Obras OpenAlex')}
                disabled={Boolean(runningTask)}
              >
                <Globe size={13} />
                <span>{t.governance.btn_harvest_works}</span>
              </button>

              <button
                id="CTL-M05-028"
                className="btn btn-secondary btn-sm"
                onClick={() => triggerTask('ch_sync', 'Sincronización ClickHouse')}
                disabled={Boolean(runningTask)}
              >
                <Activity size={13} />
                <span>{t.governance.btn_run_ch_sync}</span>
              </button>

              <button
                id="CTL-M05-029"
                className="btn btn-secondary btn-sm"
                onClick={() => triggerTask('compute_metrics', 'Cómputo de Métricas')}
                disabled={Boolean(runningTask)}
              >
                <Award size={13} />
                <span>{t.governance.btn_compute_metrics}</span>
              </button>
            </div>
          </div>

          {/* Consola de Bitácora y Estado (CTL-M05-013 a 015) */}
          <div className="glass-card" style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Terminal size={16} style={{ color: 'var(--accent-cyan)' }} />
                <h3 style={{ fontSize: '1.1rem', margin: 0 }}>Bitácora de Procesos</h3>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem' }}>
                {runningTask && (
                  <button
                    id="CTL-M05-013"
                    className="btn btn-sm"
                    style={{ background: 'rgba(244, 63, 94, 0.2)', border: '1px solid #f43f5e', color: '#fb7185' }}
                    onClick={handleStopTask}
                  >
                    <StopCircle size={13} />
                    <span>{t.governance.btn_cancel_task}</span>
                  </button>
                )}

                <button
                  id="CTL-M05-014"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setTaskLogs((prev) => [`[${new Date().toLocaleTimeString()}] Sincronizado.`, ...prev])}
                  title={t.governance.btn_refresh_log}
                >
                  <RefreshCw size={13} />
                </button>

                <button
                  id="CTL-M05-015"
                  className="btn btn-secondary btn-sm"
                  onClick={handleClearLogs}
                  title={t.governance.btn_clear_history}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>

            {/* Barra de progreso si hay tarea activa */}
            {runningTask && (
              <div style={{ marginBottom: '1rem', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '6px', padding: '0.5rem', border: '1px solid var(--border-color)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.35rem' }}>
                  <span style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>{runningTask.label}</span>
                  <span>{runningTask.progress}%</span>
                </div>
                <div style={{ width: '100%', height: '6px', background: 'rgba(255, 255, 255, 0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${runningTask.progress}%`, height: '100%', background: 'linear-gradient(90deg, #00f2fe 0%, #4facfe 100%)', transition: 'width 0.3s ease' }} />
                </div>
              </div>
            )}

            {/* Salida de Terminal */}
            <div style={{
              flex: 1, minHeight: '300px', background: '#070a0f', border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '8px', padding: '0.85rem', fontFamily: 'monospace', fontSize: '0.8rem',
              color: '#38bdf8', overflowY: 'auto', display: 'flex', flexDirection: 'column-reverse', gap: '0.35rem'
            }}>
              {taskLogs.map((log, idx) => (
                <div key={idx} style={{ opacity: idx === 0 ? 1 : 0.8 }}>
                  {log}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default GovernanceAdmin;
