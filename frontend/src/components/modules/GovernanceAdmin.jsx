/**
 * frontend/src/components/modules/GovernanceAdmin.jsx
 * Módulo 5: Administración y Gobernanza Institucional
 * Cumple con los 29 controles del inventario QA (CTL-M05-001 a CTL-M05-029)
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  ShieldCheck, Check, X, Users, Link2, Terminal, AlertTriangle,
  Play, StopCircle, RefreshCw, Trash2, Cpu, Globe, Database,
  Search, Plus, ShieldAlert, Award, Building, Activity
} from 'lucide-react';
import { useAppStore, isUserAdmin } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';

export function GovernanceAdmin() {
  const t = useAppStore((state) => state.t)();
  const selectedInstitution = useAppStore((state) => state.selectedInstitution);
  const userSession = useAppStore((state) => state.userSession);

  const isAdmin = Boolean(
    userSession?.isAuthenticated && isUserAdmin(userSession)
  );

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

  // 5. Configuración de Modelos LLM (Servidor C3 UNAM)
  const selectedLlmModel = useAppStore((state) => state.selectedLlmModel);
  const setSelectedLlmModel = useAppStore((state) => state.setSelectedLlmModel);
  const [testingModel, setTestingModel] = useState(false);
  const [modelTestResult, setModelTestResult] = useState(null);

  const handleTestModel = async (targetModel = null) => {
    const modelToTest = targetModel || selectedLlmModel || 'gpt-oss-120b';
    setTestingModel(true);
    setModelTestResult(null);
    try {
      const res = await apiClient.testModelConnection(modelToTest);
      setModelTestResult(res);
      if (res.status === 'success') {
        setActionMsg({
          type: 'success',
          text: `¡Conexión exitosa con ${res.resolved_model || modelToTest}! Latencia: ${res.latency_ms} ms. Respuesta de prueba: "${res.reply}"`
        });
      } else {
        setActionMsg({
          type: 'error',
          text: `Fallo al probar ${modelToTest}: ${res.error || 'Sin respuesta del servidor vLLM'}`
        });
      }
    } catch (err) {
      const errMsg = err?.response?.data?.detail || err.message;
      setModelTestResult({ status: 'error', error: errMsg });
      setActionMsg({
        type: 'error',
        text: `Error de red probando ${modelToTest}: ${errMsg}`
      });
    } finally {
      setTestingModel(false);
    }
  };

  const [runningTask, setRunningTask] = useState(null);
  const [taskLogs, setTaskLogs] = useState([
    'Sistema listo para operaciones de curación y sincronización masiva.'
  ]);

  const pollingIntervalRef = useRef(null);
  const logOffsetRef = useRef(0);

  // Limpiar temporizador al desmontar
  useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, []);

  // Consultar si ya existe una tarea en ejecución (o pipeline activo en terminal)
  const checkInitialStatus = async () => {
    try {
      const status = await apiClient.getPipelineStatus();
      if (status.status === 'system_running' || status.task_status === 'running') {
        setRunningTask({
          id: status.task_id || 'system_terminal',
          label: status.label || 'Pipeline en ejecución',
          progress: status.progress || 35
        });
        if (status.logs && status.logs.length > 0) {
          setTaskLogs(status.logs.slice().reverse());
          logOffsetRef.current = status.total_logs || status.logs.length;
        }
        startPolling(status.task_id, status.label || 'Pipeline');
      }
    } catch (e) {
      console.warn('No se pudo consultar el estado del pipeline:', e);
    }
  };

  // Carga inicial solo si es administrador
  useEffect(() => {
    if (!isAdmin) return;
    loadPendingRequests();
    loadActiveAdmins();
    loadAliases();
    checkInitialStatus();
  }, [isAdmin]);

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

  // Sondeo en tiempo real de logs y progreso (CTL-M05-013 a 029)
  const startPolling = (taskId, label) => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }

    pollingIntervalRef.current = setInterval(async () => {
      try {
        const res = await apiClient.getPipelineStatus(taskId, logOffsetRef.current);
        if (res.status === 'success' || res.status === 'system_running') {
          if (res.logs && res.logs.length > 0) {
            setTaskLogs((prev) => [
              ...res.logs.slice().reverse(),
              ...prev
            ]);
            logOffsetRef.current += res.logs.length;
          }

          setRunningTask((prev) => prev ? {
            ...prev,
            progress: res.progress !== undefined ? res.progress : prev.progress,
            label: res.label || prev.label
          } : null);

          if (res.task_status === 'completed' || res.task_status === 'failed' || res.task_status === 'cancelled') {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
            setRunningTask(null);
            const icon = res.task_status === 'completed' ? '✅' : '🛑';
            setTaskLogs((prev) => [
              `[${new Date().toLocaleTimeString()}] ${icon} Tarea '${label}' finalizada con estado: ${res.task_status}.`,
              ...prev
            ]);
          }
        }
      } catch (err) {
        console.error('Error sondeando bitácora de pipeline:', err);
      }
    }, 1500);
  };

  // Ejecutar tarea de pipeline (CTL-M05-019 a 029)
  const triggerTask = async (action, label) => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    logOffsetRef.current = 0;

    setRunningTask({ id: `pending_${action}`, label, progress: 5 });
    setTaskLogs((prev) => [
      `[${new Date().toLocaleTimeString()}] 🚀 Solicitando inicio de: ${label}...`,
      ...prev
    ]);

    try {
      const res = await apiClient.triggerPipeline({
        action,
        academic_filter: e2eAcademic,
        institution_filter: e2eInstitution,
        use_local_llm: useLocalLlm,
        sync_ch: syncClickhouse,
        sync_phase: syncPhase
      });

      const actualTaskId = res.task_id;
      setRunningTask({ id: actualTaskId, label, progress: 10 });
      setTaskLogs((prev) => [
        `[${new Date().toLocaleTimeString()}] 📡 Tarea confirmada en el servidor (ID: ${actualTaskId}).`,
        ...prev
      ]);

      startPolling(actualTaskId, label);
    } catch (err) {
      setRunningTask(null);
      const errMsg = err?.response?.data?.detail || err.message;
      setTaskLogs((prev) => [
        `[${new Date().toLocaleTimeString()}] ❌ Error ejecutando ${label}: ${errMsg}`,
        ...prev
      ]);
    }
  };

  // Cancelar tarea (CTL-M05-013)
  const handleStopTask = async () => {
    if (!runningTask) return;
    const taskToCancel = runningTask;
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    setRunningTask(null);

    try {
      await apiClient.cancelPipeline(taskToCancel.id);
      setTaskLogs((prev) => [
        `[${new Date().toLocaleTimeString()}] 🛑 Tarea '${taskToCancel.label}' cancelada por el usuario.`,
        ...prev
      ]);
    } catch (err) {
      const errMsg = err?.response?.data?.detail || err.message;
      setTaskLogs((prev) => [
        `[${new Date().toLocaleTimeString()}] ⚠️ Cancelación: ${errMsg}`,
        ...prev
      ]);
    }
  };

  // Sincronizar logs bajo demanda (CTL-M05-014)
  const handleRefreshLogs = async () => {
    try {
      const targetId = runningTask ? runningTask.id : null;
      const res = await apiClient.getPipelineStatus(targetId, logOffsetRef.current);
      if (res.logs && res.logs.length > 0) {
        setTaskLogs((prev) => [
          ...res.logs.slice().reverse(),
          ...prev
        ]);
        logOffsetRef.current += res.logs.length;
      }
      setTaskLogs((prev) => [
        `[${new Date().toLocaleTimeString()}] 🔄 Bitácora sincronizada.`,
        ...prev
      ]);
    } catch (e) {
      setTaskLogs((prev) => [
        `[${new Date().toLocaleTimeString()}] ⚠️ No se pudo sincronizar la bitácora.`,
        ...prev
      ]);
    }
  };

  // Limpiar historial de logs (CTL-M05-015)
  const handleClearLogs = () => {
    logOffsetRef.current = 0;
    setTaskLogs(['Bitácora reiniciada.']);
  };

  const filteredAliases = aliases.filter((a) => {
    if (!aliasSearch) return true;
    const q = aliasSearch.toLowerCase();
    return (a.canonical_entity || '').toLowerCase().includes(q) || (a.alias || '').toLowerCase().includes(q);
  });

  if (!isAdmin) {
    return (
      <div className="module-container" id="MODULO-05-ADMIN" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '50vh' }}>
        <div className="glass-card" style={{ maxWidth: '540px', width: '100%', textAlign: 'center', padding: '2.5rem 2rem' }}>
          <div style={{ display: 'inline-flex', padding: '1rem', borderRadius: '50%', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', marginBottom: '1.25rem' }}>
            <ShieldAlert size={40} />
          </div>
          <h2 style={{ fontSize: '1.35rem', fontWeight: 600, marginBottom: '0.5rem' }}>Acceso Restringido a Administración</h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: '1.5', margin: 0 }}>
            Este módulo de gobernanza y administración institucional está reservado exclusivamente para administradores acreditados.
          </p>
        </div>
      </div>
    );
  }

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

          <button
            id="CTL-M05-LLM-TAB"
            className={`btn btn-sm ${activeTab === 'llm_models' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab('llm_models')}
          >
            <Cpu size={14} />
            <span>Modelos LLM & C3</span>
            {selectedLlmModel === 'gpt-oss-120b' && (
              <span style={{ background: '#10b981', color: '#fff', fontSize: '0.65rem', padding: '0.1rem 0.4rem', borderRadius: '10px', marginLeft: '0.3rem' }}>
                120B
              </span>
            )}
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
                    <th>Investigadora/Investigador / Usuario</th>
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

              {/* Selector de Modelo LLM para Pipelines */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', background: 'rgba(255, 255, 255, 0.03)', padding: '0.65rem 0.85rem', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                <label className="form-label" style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.82rem' }}>
                  <Cpu size={13} style={{ color: 'var(--accent-cyan)' }} />
                  <span>Modelo de Lenguaje (LLM) para Pipelines</span>
                </label>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <select
                    className="form-select form-input-sm"
                    value={selectedLlmModel}
                    onChange={(e) => setSelectedLlmModel(e.target.value)}
                    style={{ flex: 1, fontSize: '0.82rem' }}
                  >
                    <option value="gpt-oss-120b">🚀 C3 UNAM GPT-OSS 120B (Cluster vLLM 120B)</option>
                    <option value="Kimi-K2.6">🧠 C3 UNAM Kimi K2.6</option>
                    <option value="openai/default">💻 LM Studio Local (gpt-oss-20b)</option>
                    <option value="gemini-3.5-flash-lite">✨ Google Gemini 3.5 Flash</option>
                  </select>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleTestModel(selectedLlmModel)}
                    disabled={testingModel}
                    title="Probar conexión con este modelo"
                    style={{ padding: '0.25rem 0.6rem' }}
                  >
                    {testingModel ? <RefreshCw size={12} className="spin" /> : <Play size={12} />}
                    <span style={{ fontSize: '0.78rem' }}>Probar</span>
                  </button>
                </div>
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
                  onClick={handleRefreshLogs}
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

      {/* 5. GESTIÓN DE MODELOS LLM & C3 UNAM */}
      {activeTab === 'llm_models' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Card Principal: Servidor vLLM C3 UNAM Activo */}
          <div className="glass-card" style={{
            background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(59, 130, 246, 0.08) 100%)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            padding: '1.5rem'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.5rem' }}>
                  <div style={{ padding: '0.4rem', borderRadius: '8px', background: 'rgba(16, 185, 129, 0.2)', color: '#34d399' }}>
                    <Cpu size={24} />
                  </div>
                  <div>
                    <h2 style={{ fontSize: '1.3rem', margin: 0, fontWeight: 700, color: 'var(--text-primary)' }}>
                      Servidor vLLM C3 UNAM — GPT-OSS 120B
                    </h2>
                    <span style={{ fontSize: '0.8rem', color: '#10b981', fontWeight: 600 }}>
                      ● Cluster de Inferencia de Alta Capacidad Disponible
                    </span>
                  </div>
                </div>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', margin: '0.5rem 0 0 0', maxWidth: '750px', lineHeight: 1.5 }}>
                  Modelo de lenguaje masivo de <b>120 Billones de parámetros</b> (OpenAI Open Weights) con soporte nativo para <b>131,072 tokens de contexto</b> y tokens de razonamiento profundo (Chain-of-Thought). Conexión cifrada a través de la VPN institucional de C3 UNAM.
                </p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', alignItems: 'flex-end' }}>
                <button
                  className="btn btn-primary"
                  onClick={() => handleTestModel('gpt-oss-120b')}
                  disabled={testingModel}
                  style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1.2rem', fontWeight: 600 }}
                >
                  {testingModel ? <RefreshCw size={16} className="spin" /> : <Play size={16} />}
                  <span>{testingModel ? 'Verificando...' : 'Probar Inferencia en Vivo'}</span>
                </button>
                {modelTestResult && (
                  <span style={{
                    fontSize: '0.78rem',
                    color: modelTestResult.status === 'success' ? '#34d399' : '#f87171',
                    background: modelTestResult.status === 'success' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                    padding: '0.2rem 0.5rem',
                    borderRadius: '4px'
                  }}>
                    {modelTestResult.status === 'success'
                      ? `🟢 Activo (${modelTestResult.latency_ms} ms)`
                      : `🔴 Error (${modelTestResult.error?.slice(0, 30)}...)`}
                  </span>
                )}
              </div>
            </div>

            {/* Metadatos Técnicos de Conexión */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '0.75rem',
              marginTop: '1.25rem',
              paddingTop: '1rem',
              borderTop: '1px solid rgba(255, 255, 255, 0.08)'
            }}>
              <div style={{ background: 'rgba(0,0,0,0.2)', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>URL Base (VPN C3)</span>
                <code style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)' }}>https://gptoss.c3.unam.mx/v1</code>
              </div>
              <div style={{ background: 'rgba(0,0,0,0.2)', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>IP / Proxy Interno</span>
                <code style={{ fontSize: '0.8rem', color: 'var(--text-primary)' }}>10.90.0.114 (ppp0)</code>
              </div>
              <div style={{ background: 'rgba(0,0,0,0.2)', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>Model ID en vLLM</span>
                <code style={{ fontSize: '0.8rem', color: '#10b981' }}>gpt-oss-120b</code>
              </div>
              <div style={{ background: 'rgba(0,0,0,0.2)', padding: '0.6rem 0.8rem', borderRadius: '6px' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>Ventana de Contexto</span>
                <code style={{ fontSize: '0.8rem', color: 'var(--text-primary)' }}>131,072 tokens</code>
              </div>
            </div>
          </div>

          {/* Selector de Modelos Disponibles */}
          <div className="glass-card">
            <h3 style={{ fontSize: '1.15rem', marginBottom: '0.5rem', color: 'var(--text-primary)' }}>
              Selección de Modelo de Lenguaje del Sistema
            </h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
              El modelo seleccionado será utilizado para el Asistente Científico, la generación de Reportes con IA y los procesos de curación institucional.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
              {/* Opción 1: GPT-OSS 120B C3 */}
              <div style={{
                background: selectedLlmModel === 'gpt-oss-120b' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(255, 255, 255, 0.03)',
                border: `2px solid ${selectedLlmModel === 'gpt-oss-120b' ? '#10b981' : 'var(--border-color)'}`,
                borderRadius: '10px',
                padding: '1.25rem',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                transition: 'all 0.2s ease'
              }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{
                      background: '#10b981', color: '#fff', fontSize: '0.7rem', fontWeight: 700,
                      padding: '0.15rem 0.5rem', borderRadius: '12px'
                    }}>
                      RECOMENDADO · 120B
                    </span>
                    {selectedLlmModel === 'gpt-oss-120b' && (
                      <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.8rem', fontWeight: 600 }}>
                        <Check size={14} /> Activo
                      </span>
                    )}
                  </div>
                  <h4 style={{ margin: '0.4rem 0', fontSize: '1.05rem', color: 'var(--text-primary)' }}>
                    C3 UNAM - GPT-OSS 120B
                  </h4>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', margin: 0, lineHeight: 1.45 }}>
                    Modelo de mayor capacidad y razonamiento analítico. Desplegado en el cluster vLLM del C3 UNAM. Ideal para análisis cienciométricos exhaustivos.
                  </p>
                </div>

                <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                  <button
                    className={`btn btn-sm ${selectedLlmModel === 'gpt-oss-120b' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ flex: 1, justifyContent: 'center' }}
                    onClick={() => {
                      setSelectedLlmModel('gpt-oss-120b');
                      setActionMsg({ type: 'success', text: 'Modelo activo cambiado a C3 UNAM GPT-OSS 120B.' });
                    }}
                  >
                    {selectedLlmModel === 'gpt-oss-120b' ? 'Modelo Activo' : 'Seleccionar'}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleTestModel('gpt-oss-120b')}
                    disabled={testingModel}
                    title="Probar este modelo"
                  >
                    <Play size={12} />
                  </button>
                </div>
              </div>

              {/* Opción 2: Kimi K2.6 C3 */}
              <div style={{
                background: selectedLlmModel === 'Kimi-K2.6' ? 'rgba(59, 130, 246, 0.12)' : 'rgba(255, 255, 255, 0.03)',
                border: `2px solid ${selectedLlmModel === 'Kimi-K2.6' ? '#3b82f6' : 'var(--border-color)'}`,
                borderRadius: '10px',
                padding: '1.25rem',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                transition: 'all 0.2s ease'
              }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{
                      background: 'rgba(59, 130, 246, 0.2)', color: '#60a5fa', fontSize: '0.7rem', fontWeight: 600,
                      padding: '0.15rem 0.5rem', borderRadius: '12px', border: '1px solid rgba(59, 130, 246, 0.4)'
                    }}>
                      C3 vLLM
                    </span>
                    {selectedLlmModel === 'Kimi-K2.6' && (
                      <span style={{ color: '#3b82f6', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.8rem', fontWeight: 600 }}>
                        <Check size={14} /> Activo
                      </span>
                    )}
                  </div>
                  <h4 style={{ margin: '0.4rem 0', fontSize: '1.05rem', color: 'var(--text-primary)' }}>
                    C3 UNAM - Kimi K2.6
                  </h4>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', margin: 0, lineHeight: 1.45 }}>
                    Servidor vLLM de Kimi en el C3 UNAM. Especializado en procesamiento largo de contexto en español.
                  </p>
                </div>

                <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                  <button
                    className={`btn btn-sm ${selectedLlmModel === 'Kimi-K2.6' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ flex: 1, justifyContent: 'center' }}
                    onClick={() => {
                      setSelectedLlmModel('Kimi-K2.6');
                      setActionMsg({ type: 'success', text: 'Modelo activo cambiado a C3 UNAM Kimi K2.6.' });
                    }}
                  >
                    {selectedLlmModel === 'Kimi-K2.6' ? 'Modelo Activo' : 'Seleccionar'}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleTestModel('Kimi-K2.6')}
                    disabled={testingModel}
                    title="Probar este modelo"
                  >
                    <Play size={12} />
                  </button>
                </div>
              </div>

              {/* Opción 3: LM Studio Local */}
              <div style={{
                background: selectedLlmModel === 'openai/default' ? 'rgba(168, 85, 247, 0.12)' : 'rgba(255, 255, 255, 0.03)',
                border: `2px solid ${selectedLlmModel === 'openai/default' ? '#a855f7' : 'var(--border-color)'}`,
                borderRadius: '10px',
                padding: '1.25rem',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                transition: 'all 0.2s ease'
              }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{
                      background: 'rgba(168, 85, 247, 0.2)', color: '#c084fc', fontSize: '0.7rem', fontWeight: 600,
                      padding: '0.15rem 0.5rem', borderRadius: '12px', border: '1px solid rgba(168, 85, 247, 0.4)'
                    }}>
                      LOCAL · 20B
                    </span>
                    {selectedLlmModel === 'openai/default' && (
                      <span style={{ color: '#a855f7', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.8rem', fontWeight: 600 }}>
                        <Check size={14} /> Activo
                      </span>
                    )}
                  </div>
                  <h4 style={{ margin: '0.4rem 0', fontSize: '1.05rem', color: 'var(--text-primary)' }}>
                    LM Studio Local (gpt-oss-20b)
                  </h4>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', margin: 0, lineHeight: 1.45 }}>
                    Instancia local en servidor (localhost:1234). Utiliza el modelo GPT-OSS 20B cargado en LM Studio CLI.
                  </p>
                </div>

                <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                  <button
                    className={`btn btn-sm ${selectedLlmModel === 'openai/default' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ flex: 1, justifyContent: 'center' }}
                    onClick={() => {
                      setSelectedLlmModel('openai/default');
                      setActionMsg({ type: 'success', text: 'Modelo activo cambiado a LM Studio Local.' });
                    }}
                  >
                    {selectedLlmModel === 'openai/default' ? 'Modelo Activo' : 'Seleccionar'}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleTestModel('openai/default')}
                    disabled={testingModel}
                    title="Probar este modelo"
                  >
                    <Play size={12} />
                  </button>
                </div>
              </div>

              {/* Opción 4: Google Gemini */}
              <div style={{
                background: selectedLlmModel === 'gemini-3.5-flash-lite' ? 'rgba(236, 72, 153, 0.12)' : 'rgba(255, 255, 255, 0.03)',
                border: `2px solid ${selectedLlmModel === 'gemini-3.5-flash-lite' ? '#ec4899' : 'var(--border-color)'}`,
                borderRadius: '10px',
                padding: '1.25rem',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                transition: 'all 0.2s ease'
              }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{
                      background: 'rgba(236, 72, 153, 0.2)', color: '#f472b6', fontSize: '0.7rem', fontWeight: 600,
                      padding: '0.15rem 0.5rem', borderRadius: '12px', border: '1px solid rgba(236, 72, 153, 0.4)'
                    }}>
                      GOOGLE CLOUD
                    </span>
                    {selectedLlmModel === 'gemini-3.5-flash-lite' && (
                      <span style={{ color: '#ec4899', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.8rem', fontWeight: 600 }}>
                        <Check size={14} /> Activo
                      </span>
                    )}
                  </div>
                  <h4 style={{ margin: '0.4rem 0', fontSize: '1.05rem', color: 'var(--text-primary)' }}>
                    Google Gemini 3.5 Flash
                  </h4>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', margin: 0, lineHeight: 1.45 }}>
                    Inferencia rápida y multimodal en la infraestructura de Google Cloud usando la API oficial de Gemini.
                  </p>
                </div>

                <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
                  <button
                    className={`btn btn-sm ${selectedLlmModel === 'gemini-3.5-flash-lite' ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ flex: 1, justifyContent: 'center' }}
                    onClick={() => {
                      setSelectedLlmModel('gemini-3.5-flash-lite');
                      setActionMsg({ type: 'success', text: 'Modelo activo cambiado a Google Gemini.' });
                    }}
                  >
                    {selectedLlmModel === 'gemini-3.5-flash-lite' ? 'Modelo Activo' : 'Seleccionar'}
                  </button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => handleTestModel('gemini-3.5-flash-lite')}
                    disabled={testingModel}
                    title="Probar este modelo"
                  >
                    <Play size={12} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default GovernanceAdmin;
