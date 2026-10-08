import React, { useState, useEffect, useRef } from 'react';
import {
  FileText, Download, Eye, EyeOff, Sparkles, AlertCircle, LogIn,
  Loader2, CheckCircle, RefreshCw, ExternalLink
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import apiClient, { getBaseApiUrl } from '../../api/client.js';

export default function AIReportViewer({
  type = "inst", // "inst" o "inv"
  targetName = "",
  entityName = "",
  institutionName = "",
  viewMode = "capacidad_instalada",
  hasReport = false
}) {
  const [showInScreen, setShowInScreen] = useState(false);
  const [reportExists, setReportExists] = useState(Boolean(hasReport));
  const [checkingStatus, setCheckingStatus] = useState(false);
  const [serverFilename, setServerFilename] = useState(null);

  // Estados de Tarea Asíncrona (Job en segundo plano)
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState('idle'); // 'idle' | 'pending' | 'processing' | 'completed' | 'error'
  const [jobProgress, setJobProgress] = useState({ step: 0, total_steps: 12, progress_msg: '' });
  const [jobError, setJobError] = useState(null);
  const [customReportUrl, setCustomReportUrl] = useState(null);
  const pollIntervalRef = useRef(null);

  const userSession = useAppStore((state) => state.userSession);
  const setActiveTab = useAppStore((state) => state.setActiveTab);
  const selectedLlmModel = useAppStore((state) => state.selectedLlmModel);
  const isAuthenticated = Boolean(userSession?.isAuthenticated);

  const base = typeof getBaseApiUrl === 'function' ? getBaseApiUrl() : '/api';
  const defaultReportUrl = `${base}/reports/ai-report?type=${type}&name=${encodeURIComponent(targetName)}&view_mode=${encodeURIComponent(viewMode)}`;

  // Consultar estado de existencia del reporte al cambiar de entidad o vista
  useEffect(() => {
    let isMounted = true;
    setJobId(null);
    setJobStatus('idle');
    setJobProgress({ step: 0, total_steps: 12, progress_msg: '' });
    setJobError(null);
    setCustomReportUrl(null);
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }

    if (!targetName || targetName === 'Entidad' || targetName === 'Investigador') {
      setReportExists(false);
      return;
    }

    const verifyExistence = async () => {
      setCheckingStatus(true);
      try {
        const res = await apiClient.checkAIReportStatus(type, targetName, viewMode);
        if (isMounted) {
          if (res && res.exists) {
            setReportExists(true);
            setServerFilename(res.filename);
          } else {
            setReportExists(false);
            setServerFilename(null);
          }
        }
      } catch (err) {
        if (isMounted) {
          setReportExists(Boolean(hasReport));
        }
      } finally {
        if (isMounted) setCheckingStatus(false);
      }
    };

    verifyExistence();

    return () => {
      isMounted = false;
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [targetName, type, viewMode, hasReport]);

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
            total_steps: res.total_steps || 12,
            progress_msg: res.progress_msg || ''
          });

          if (res.status === 'completed') {
            setJobStatus('completed');
            setCustomReportUrl(defaultReportUrl);
            setReportExists(true);
            setShowInScreen(true);
            try {
              const statusCheck = await apiClient.checkAIReportStatus(type, targetName, viewMode);
              if (statusCheck && statusCheck.filename) {
                setServerFilename(statusCheck.filename);
              }
            } catch (e) {}

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
  }, [jobId, jobStatus, type, targetName, viewMode, defaultReportUrl]);

  // Iniciar la generación en segundo plano
  const handleRequestReport = async () => {
    if (!isAuthenticated) {
      setActiveTab('mySpace');
      return;
    }
    setJobError(null);
    setJobStatus('pending');
    setShowInScreen(true);
    setJobProgress({ step: 0, total_steps: 12, progress_msg: 'Iniciando compilador cienciométrico con IA...' });

    try {
      const payload = {
        type,
        name: targetName,
        entity: entityName || targetName,
        institution: institutionName || targetName,
        view_mode: viewMode,
        save_to_disk: true,
        model: selectedLlmModel || 'gpt-oss-120b'
      };
      const res = await apiClient.requestAIReportJob(payload);
      if (res && res.job_id) {
        setJobId(res.job_id);
        setJobStatus('processing');
      } else {
        setJobStatus('error');
        setJobError('No se pudo registrar la tarea de compilación en el servidor.');
      }
    } catch (err) {
      setJobStatus('error');
      setJobError(err.response?.data?.detail || err.message || 'Error al iniciar la generación del reporte.');
    }
  };

  const effectiveReportUrl = customReportUrl || defaultReportUrl;
  const effectiveDownloadUrl = customReportUrl
    ? (customReportUrl.includes('?') ? `${customReportUrl}&download=true` : `${customReportUrl}?download=true`)
    : `${defaultReportUrl}&download=true`;

  const isGenerating = jobStatus === 'pending' || jobStatus === 'processing';
  const hasAvailableReport = reportExists || Boolean(customReportUrl);

  return (
    <div className="glass-card" style={{ padding: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '0.5rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '0.3rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
              <FileText size={18} style={{ color: 'var(--accent-cyan)' }} />
              📄 Reporte Bibliométrico con Inteligencia Artificial
            </h3>
            <span 
              className="badge" 
              style={{ 
                fontSize: '0.72rem', 
                padding: '0.15rem 0.55rem', 
                background: 'rgba(56, 189, 248, 0.12)', 
                border: '1px solid rgba(56, 189, 248, 0.3)', 
                color: 'var(--accent-cyan)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem'
              }}
              title="Modelo LLM configurado para la generación analítica (con respaldo automático si vLLM no está disponible)"
            >
              <Sparkles size={11} />
              Motor: <strong>{selectedLlmModel || 'gpt-oss-120b'}</strong>
              <span style={{ opacity: 0.75 }}>(auto-fallback local)</span>
            </span>
          </div>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, maxWidth: '820px' }}>
            Informe analítico cuantitativo y cualitativo interpretado mediante modelos de lenguaje (LLM). Integra diagnóstico global, velocidad de citación, madurez científica, impacto ponderado (FWCI) y posicionamiento temático de {targetName || "la entidad"}.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Botón Ver / Ocultar en Pantalla */}
          <button
            onClick={() => setShowInScreen(!showInScreen)}
            disabled={isGenerating}
            className={`btn ${showInScreen ? 'btn-outline' : 'btn-secondary'}`}
            style={{ fontSize: '0.82rem', padding: '0.45rem 0.95rem', display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontWeight: 600 }}
          >
            {showInScreen ? (
              <>
                <EyeOff size={15} /> Ocultar Reporte
              </>
            ) : (
              <>
                <Eye size={15} /> 👁️ Ver Reporte en Pantalla
              </>
            )}
          </button>

          {/* Botón de Generación / Regeneración */}
          {isAuthenticated ? (
            <button
              onClick={handleRequestReport}
              disabled={isGenerating}
              className="btn btn-primary"
              style={{
                fontSize: '0.82rem',
                padding: '0.45rem 0.95rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.4rem',
                fontWeight: 700,
                background: hasAvailableReport 
                  ? 'linear-gradient(135deg, #0ea5e9, #6366f1)' 
                  : 'linear-gradient(135deg, #06b6d4, #8b5cf6)',
                border: 'none',
                color: '#ffffff',
                boxShadow: '0 2px 8px rgba(139, 92, 246, 0.25)'
              }}
              title={hasAvailableReport ? "Regenerar reporte bibliométrico con IA" : "Compilar reporte bibliométrico con IA"}
            >
              {isGenerating ? (
                <>
                  <Loader2 size={15} className="spin-slow" />
                  <span>Compilando ({jobProgress.step}/11)...</span>
                </>
              ) : hasAvailableReport ? (
                <>
                  <RefreshCw size={14} />
                  <span>🔄 Regenerar con IA</span>
                </>
              ) : (
                <>
                  <Sparkles size={15} />
                  <span>✨ Generar Reporte con IA</span>
                </>
              )}
            </button>
          ) : !hasAvailableReport ? (
            <button
              onClick={() => setActiveTab('mySpace')}
              className="btn btn-secondary"
              title="Inicia sesión con tu ORCID para generar el informe analítico completo con IA"
              style={{ fontSize: '0.82rem', padding: '0.45rem 0.95rem', display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontWeight: 600 }}
            >
              <LogIn size={15} style={{ color: 'var(--accent-cyan)' }} />
              Iniciar sesión para generar
            </button>
          ) : null}

          {/* Botón Descargar Reporte (HTML) si el reporte está disponible */}
          {hasAvailableReport && (
            <a
              href={effectiveDownloadUrl}
              target="_blank"
              rel="noreferrer"
              className="btn btn-outline"
              style={{ fontSize: '0.82rem', padding: '0.45rem 0.95rem', display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontWeight: 700, textDecoration: 'none' }}
              title="Descargar archivo HTML independiente con gráficos y tablas interactivas"
            >
              <Download size={15} /> ⬇️ Descargar HTML
            </a>
          )}
        </div>
      </div>

      {showInScreen && (
        <div style={{ marginTop: '1rem', borderRadius: '12px', overflow: 'hidden', border: '1px solid var(--border-subtle)', background: '#ffffff' }}>
          {isGenerating ? (
            /* Vista de Progreso en Vivo */
            <div style={{ padding: '2.5rem 1.5rem', textAlign: 'center', background: 'rgba(15, 23, 42, 0.96)', color: '#ffffff' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
                <Sparkles size={24} style={{ color: 'var(--accent-cyan)' }} />
                <h4 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 700 }}>
                  Compilando Reporte Bibliométrico con Inteligencia Artificial
                </h4>
              </div>

              <div style={{ maxWidth: '580px', margin: '0 auto 1.25rem' }}>
                <div style={{ height: '8px', background: 'rgba(255, 255, 255, 0.15)', borderRadius: '4px', overflow: 'hidden', marginBottom: '0.5rem' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${Math.max(6, Math.min(100, Math.round((jobProgress.step / Math.max(jobProgress.total_steps, 11)) * 100)))}%`,
                      background: 'linear-gradient(90deg, var(--accent-cyan, #06b6d4), #8b5cf6)',
                      borderRadius: '4px',
                      transition: 'width 0.4s ease'
                    }}
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#94a3b8' }}>
                  <span>{jobProgress.progress_msg || 'Extrayendo datos cuantitativos y consultando modelo LLM...'}</span>
                  <span style={{ fontWeight: 600 }}>{jobProgress.step} / {jobProgress.total_steps || 11}</span>
                </div>
              </div>

              <p style={{ fontSize: '0.82rem', color: '#94a3b8', maxWidth: '620px', margin: '0 auto', lineHeight: 1.5 }}>
                El motor analiza los 11 módulos cienciométricos (resumen ejecutivo, trayectoria, velocidad de citación, madurez de Price, modelo de Bradford, cuartiles, impacto FWCI, colaboración, ODS y directrices estratégicas).
              </p>
            </div>
          ) : !hasAvailableReport ? (
            /* Vista cuando el reporte no está generado aún */
            <div style={{ padding: '2.5rem 1.5rem', textAlign: 'center', background: 'rgba(248, 250, 252, 0.98)', color: '#334155' }}>
              <AlertCircle size={38} style={{ color: '#f59e0b', marginBottom: '0.75rem' }} />
              <h4 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.4rem', color: '#0f172a' }}>
                El reporte analítico para esta selección aún no ha sido compilado
              </h4>
              <p style={{ fontSize: '0.85rem', color: '#64748b', maxWidth: '620px', margin: '0 auto 1.5rem', lineHeight: 1.5 }}>
                {isAuthenticated
                  ? 'Como usuario autenticado, puedes iniciar la compilación con Inteligencia Artificial ahora mismo. El reporte consolidará las 11 dimensiones bibliométricas y quedará disponible para consulta y descarga.'
                  : 'Para generar o solicitar la compilación analítica de este reporte con Inteligencia Artificial, inicia sesión con tu cuenta académica o identificador ORCID.'}
              </p>

              {jobError && (
                <div style={{ maxWidth: '520px', margin: '0 auto 1.25rem', padding: '0.6rem 0.9rem', borderRadius: '6px', background: '#fee2e2', border: '1px solid #f87171', color: '#b91c1c', fontSize: '0.82rem' }}>
                  {jobError}
                </div>
              )}

              {isAuthenticated ? (
                <button
                  onClick={handleRequestReport}
                  className="btn btn-primary"
                  style={{
                    fontSize: '0.88rem',
                    padding: '0.6rem 1.4rem',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    fontWeight: 700,
                    background: 'linear-gradient(135deg, #06b6d4, #8b5cf6)',
                    border: 'none',
                    color: '#ffffff'
                  }}
                >
                  <Sparkles size={16} /> ✨ Iniciar Generación con IA
                </button>
              ) : (
                <button
                  onClick={() => setActiveTab('mySpace')}
                  className="btn btn-primary"
                  style={{
                    fontSize: '0.88rem',
                    padding: '0.6rem 1.4rem',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    fontWeight: 700,
                    background: 'linear-gradient(135deg, #06b6d4, #8b5cf6)',
                    border: 'none',
                    color: '#ffffff'
                  }}
                >
                  <LogIn size={16} /> Iniciar sesión con ORCID
                </button>
              )}
            </div>
          ) : (
            /* Vista del iframe con el reporte compilado */
            <div>
              <div style={{
                padding: '0.6rem 1rem',
                background: '#f8fafc',
                borderBottom: '1px solid #e2e8f0',
                color: '#334155',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.82rem',
                flexWrap: 'wrap',
                gap: '0.5rem'
              }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontWeight: 600, color: '#047857' }}>
                  <CheckCircle size={15} style={{ color: '#059669' }} />
                  {jobStatus === 'completed'
                    ? 'Reporte generado exitosamente con Inteligencia Artificial'
                    : `Reporte compilado disponible (${serverFilename || 'HTML'})`}
                </span>

                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                  <a
                    href={effectiveReportUrl}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: '#0284c7', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.25rem', fontWeight: 600, fontSize: '0.78rem' }}
                  >
                    <ExternalLink size={12} /> Abrir en pestaña nueva
                  </a>

                  {isAuthenticated && (
                    <button
                      onClick={handleRequestReport}
                      disabled={isGenerating}
                      style={{ background: 'none', border: 'none', color: '#6366f1', cursor: 'pointer', fontSize: '0.78rem', textDecoration: 'underline', display: 'inline-flex', alignItems: 'center', gap: '0.25rem', fontWeight: 600 }}
                      title="Volver a ejecutar el análisis con el modelo de lenguaje"
                    >
                      <RefreshCw size={12} /> Regenerar con IA
                    </button>
                  )}
                </div>
              </div>

              <iframe
                src={effectiveReportUrl}
                title={`Reporte Bibliométrico IA - ${targetName}`}
                style={{
                  width: '100%',
                  height: '780px',
                  border: 'none',
                  display: 'block'
                }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
