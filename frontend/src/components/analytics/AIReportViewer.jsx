import React, { useState, useEffect, useRef } from 'react';
import {
  FileText, Download, Eye, EyeOff, Sparkles, AlertCircle, LogIn,
  Loader2, CheckCircle, RefreshCw, ShieldAlert
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';

export default function AIReportViewer({
  type = "inst", // "inst" o "inv"
  targetName = "",
  viewMode = "capacidad_instalada",
  hasReport = true
}) {
  const [showInScreen, setShowInScreen] = useState(false);
  const [loadError, setLoadError] = useState(false);

  // Estados de Tarea Asíncrona (Job en segundo plano)
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState('idle'); // 'idle' | 'pending' | 'processing' | 'completed' | 'error'
  const [jobProgress, setJobProgress] = useState({ step: 0, total_steps: 11, progress_msg: '' });
  const [jobError, setJobError] = useState(null);
  const [customReportUrl, setCustomReportUrl] = useState(null);
  const pollIntervalRef = useRef(null);

  const userSession = useAppStore((state) => state.userSession);
  const setActiveTab = useAppStore((state) => state.setActiveTab);
  const isAuthenticated = Boolean(userSession?.isAuthenticated);
  const isAdmin = Boolean(
    userSession?.is_admin ||
    userSession?.role === 'super_admin' ||
    userSession?.role === 'admin_institucional' ||
    userSession?.role === 'admin'
  );

  // Limpiar y resetear al cambiar entidad o contexto
  useEffect(() => {
    setLoadError(false);
    setJobId(null);
    setJobStatus('idle');
    setJobProgress({ step: 0, total_steps: 11, progress_msg: '' });
    setJobError(null);
    setCustomReportUrl(null);
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, [targetName, type, viewMode]);

  // Polling del progreso de generación en segundo plano
  useEffect(() => {
    if (!jobId || (jobStatus !== 'pending' && jobStatus !== 'processing')) {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      return;
    }

    const checkStatus = async () => {
      try {
        const res = await apiClient.getAIReportJobStatus(jobId);
        if (res) {
          setJobProgress({
            step: res.step || 0,
            total_steps: res.total_steps || 11,
            progress_msg: res.progress_msg || ''
          });

          if (res.status === 'completed') {
            setJobStatus('completed');
            setCustomReportUrl(apiClient.getAIReportJobResultUrl(jobId));
            setLoadError(false);
            setShowInScreen(true);
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current);
              pollIntervalRef.current = null;
            }
          } else if (res.status === 'error') {
            setJobStatus('error');
            setJobError(res.error || 'Ocurrió un error durante la generación del reporte.');
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current);
              pollIntervalRef.current = null;
            }
          }
        }
      } catch (err) {
        console.error('Error consultando estado del reporte IA:', err);
      }
    };

    pollIntervalRef.current = setInterval(checkStatus, 3500);
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [jobId, jobStatus]);

  // Iniciar la generación en segundo plano
  const handleRequestReport = async () => {
    if (!isAuthenticated) {
      setActiveTab('mySpace');
      return;
    }
    setJobError(null);
    setJobStatus('pending');
    setShowInScreen(true);
    setJobProgress({ step: 0, total_steps: 11, progress_msg: 'Iniciando motor analítico cienciométrico...' });

    try {
      const payload = {
        type,
        name: targetName,
        entity: targetName,
        institution: targetName,
        view_mode: viewMode,
        save_to_disk: type === 'inst' // solo instituciones se guardan permanentemente en disco
      };
      const res = await apiClient.requestAIReportJob(payload);
      if (res && res.job_id) {
        setJobId(res.job_id);
        setJobStatus('processing');
      } else {
        setJobStatus('error');
        setJobError('No se pudo registrar la tarea de compilación.');
      }
    } catch (err) {
      setJobStatus('error');
      setJobError(err.response?.data?.detail || err.message || 'Error al iniciar la generación del reporte.');
    }
  };

  const defaultReportUrl = `/api/reports/ai-report?type=${type}&name=${encodeURIComponent(targetName)}&view_mode=${encodeURIComponent(viewMode)}`;
  const effectiveReportUrl = customReportUrl || defaultReportUrl;
  const effectiveDownloadUrl = customReportUrl
    ? `${customReportUrl}?download=true`
    : `${defaultReportUrl}&download=true`;

  const isGenerating = jobStatus === 'pending' || jobStatus === 'processing';

  return (
    <div className="glass-card" style={{ padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '0.5rem' }}>
        <div>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.3rem' }}>
            <FileText size={18} style={{ color: 'var(--accent-cyan)' }} />
            📄 Reporte Bibliométrico con Inteligencia Artificial
          </h3>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, maxWidth: '800px' }}>
            Informe analítico consolidado e interpretado por modelos de lenguaje (LLM), integrando el contexto disciplinar, la velocidad de citación y la madurez científica de la entidad.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {isAuthenticated ? (
            <button
              onClick={() => setShowInScreen(!showInScreen)}
              disabled={isGenerating}
              className={`btn ${showInScreen ? 'btn-outline' : 'btn-primary'}`}
              style={{ fontSize: '0.82rem', padding: '0.45rem 0.95rem', display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontWeight: 700 }}
            >
              {isGenerating ? (
                <>
                  <Loader2 size={15} className="spin-slow" />
                  <span>Compilando ({jobProgress.step}/11)...</span>
                </>
              ) : showInScreen ? (
                <>
                  <EyeOff size={15} /> Ocultar Reporte
                </>
              ) : (
                <>
                  <Eye size={15} /> 👁️ Ver Reporte en Pantalla
                </>
              )}
            </button>
          ) : (
            <button
              onClick={() => setActiveTab('mySpace')}
              className="btn btn-secondary"
              title="Inicia sesión con ORCID para visualizar el informe analítico completo"
              style={{ fontSize: '0.82rem', padding: '0.45rem 0.95rem', display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontWeight: 600 }}
            >
              <LogIn size={15} style={{ color: 'var(--accent-cyan)' }} />
              Iniciar sesión para ver reporte IA
            </button>
          )}

          {(!loadError || customReportUrl) && (
            <a
              href={effectiveDownloadUrl}
              target="_blank"
              rel="noreferrer"
              className="btn btn-outline"
              style={{ fontSize: '0.82rem', padding: '0.45rem 0.95rem', display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontWeight: 700, textDecoration: 'none' }}
            >
              <Download size={15} /> ⬇️ Descargar Reporte (HTML)
            </a>
          )}
        </div>
      </div>

      {showInScreen && isAuthenticated && (
        <div style={{ marginTop: '1rem', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border-subtle)', background: '#ffffff' }}>
          {isGenerating ? (
            /* Vista de Progreso en Vivo */
            <div style={{ padding: '2.5rem 1.5rem', textAlign: 'center', background: 'rgba(15, 23, 42, 0.95)', color: '#ffffff' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
                <Sparkles size={24} style={{ color: 'var(--accent-cyan)' }} />
                <h4 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 700 }}>
                  Generando Reporte Bibliométrico con Inteligencia Artificial
                </h4>
              </div>

              <div style={{ maxWidth: '560px', margin: '0 auto 1.25rem' }}>
                <div style={{ height: '8px', background: 'rgba(255, 255, 255, 0.15)', borderRadius: '4px', overflow: 'hidden', marginBottom: '0.5rem' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${Math.max(6, Math.min(100, Math.round((jobProgress.step / Math.max(jobProgress.total_steps, 11)) * 100)))}%`,
                      background: 'linear-gradient(90deg, var(--accent-cyan, #06b6d4), #3b82f6)',
                      borderRadius: '4px',
                      transition: 'width 0.4s ease'
                    }}
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#94a3b8' }}>
                  <span>{jobProgress.progress_msg || 'Analizando dimensiones cienciométricas...'}</span>
                  <span style={{ fontWeight: 600 }}>{jobProgress.step} / {jobProgress.total_steps || 11}</span>
                </div>
              </div>

              <p style={{ fontSize: '0.82rem', color: '#94a3b8', maxWidth: '600px', margin: '0 auto', lineHeight: 1.5 }}>
                {type === 'inv'
                  ? '✨ Generación bajo demanda para tu sesión activa: el informe se procesa de forma efímera en memoria (sin almacenar en disco). Puedes continuar explorando el sistema mientras el LLM compila las 11 secciones.'
                  : '⚡ Compilación institucional en curso: los resultados se guardarán permanentemente en el repositorio de reportes para consulta de la comunidad académica.'}
              </p>
            </div>
          ) : loadError && jobStatus !== 'completed' ? (
            /* Vista cuando el reporte no está pregenerado */
            <div style={{ padding: '2.5rem 1.5rem', textAlign: 'center', background: 'rgba(248, 250, 252, 0.98)', color: '#334155' }}>
              <AlertCircle size={36} style={{ color: '#f59e0b', marginBottom: '0.75rem' }} />
              <h4 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '0.4rem', color: '#0f172a' }}>
                El reporte analítico para esta selección aún no ha sido compilado
              </h4>
              <p style={{ fontSize: '0.85rem', color: '#64748b', maxWidth: '620px', margin: '0 auto 1.5rem', lineHeight: 1.5 }}>
                {type === 'inv'
                  ? 'Como usuario autenticado, puedes solicitar la compilación de este reporte con Inteligencia Artificial. Se generará en memoria para su consulta inmediata y descarga sin almacenarse en el servidor.'
                  : isAdmin
                    ? 'Como administrador del sistema, puedes iniciar la compilación y publicación de este reporte institucional. Se guardará de manera permanente en el servidor para consulta de todas las investigadoras e investigadores.'
                    : 'La generación y publicación de reportes para dependencias e instituciones está reservada a administradores del sistema.'}
              </p>

              {jobError && (
                <div style={{ maxWidth: '500px', margin: '0 auto 1.25rem', padding: '0.6rem 0.9rem', borderRadius: '6px', background: '#fee2e2', border: '1px solid #f87171', color: '#b91c1c', fontSize: '0.82rem' }}>
                  {jobError}
                </div>
              )}

              {/* Botón de acción según permisos */}
              {type === 'inv' ? (
                <button
                  onClick={handleRequestReport}
                  className="btn btn-primary"
                  style={{ fontSize: '0.88rem', padding: '0.6rem 1.3rem', display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700 }}
                >
                  <Sparkles size={16} /> ✨ Generar Reporte con IA (Bajo Demanda)
                </button>
              ) : isAdmin ? (
                <button
                  onClick={handleRequestReport}
                  className="btn btn-primary"
                  style={{ fontSize: '0.88rem', padding: '0.6rem 1.3rem', display: 'inline-flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700 }}
                >
                  <Sparkles size={16} /> ⚡ Compilar y Publicar Reporte Institucional (Admin)
                </button>
              ) : (
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', color: '#94a3b8', fontSize: '0.82rem', padding: '0.4rem 0.8rem', borderRadius: '6px', background: '#f1f5f9' }}>
                  <ShieldAlert size={15} /> Compilación reservada a administradores
                </div>
              )}
            </div>
          ) : (
            /* Vista del iframe con el reporte compilado */
            <div>
              {jobStatus === 'completed' && (
                <div style={{ padding: '0.6rem 1rem', background: '#ecfdf5', borderBottom: '1px solid #a7f3d0', color: '#065f46', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '0.82rem' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontWeight: 600 }}>
                    <CheckCircle size={15} style={{ color: '#059669' }} />
                    Reporte con IA generado exitosamente
                  </span>
                  <button
                    onClick={handleRequestReport}
                    style={{ background: 'none', border: 'none', color: '#059669', cursor: 'pointer', fontSize: '0.78rem', textDecoration: 'underline', display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
                  >
                    <RefreshCw size={12} /> Regenerar
                  </button>
                </div>
              )}
              <iframe
                src={effectiveReportUrl}
                title={`Reporte Bibliométrico IA - ${targetName}`}
                style={{
                  width: '100%',
                  height: '750px',
                  border: 'none',
                  display: 'block'
                }}
                onError={() => setLoadError(true)}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
