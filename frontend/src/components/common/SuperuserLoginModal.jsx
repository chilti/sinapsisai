/**
 * frontend/src/components/common/SuperuserLoginModal.jsx
 * Modal de autenticación para Superusuarios y Evaluadores Especiales.
 * Permite desbloquear la vista de Investigadoras e Investigadores para personas autorizadas.
 */

import React, { useState, useEffect, useRef } from 'react';
import { ShieldCheck, Lock, User, KeyRound, X, Loader2, Sparkles, AlertCircle } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';

export function SuperuserLoginModal({ isOpen, onClose }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  const setUserSession = useAppStore((state) => state.setUserSession);
  const setActiveTab = useAppStore((state) => state.setActiveTab);
  const setNotification = useAppStore((state) => state.setNotification);

  const userInputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setErrorMsg(null);
      setUsername('');
      setPassword('');
      setTimeout(() => {
        userInputRef.current?.focus();
      }, 60);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (isOpen && e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setErrorMsg('Por favor introduce usuario y contraseña.');
      return;
    }

    setLoading(true);
    setErrorMsg(null);

    try {
      const res = await apiClient.superuserLogin(username.trim(), password);
      if (res && res.status === 'success' && res.user) {
        setUserSession(res.user);
        setNotification({
          type: 'success',
          message: '🎉 Acceso Especial verificado. Directorio de investigadores desbloqueado.'
        });
        setActiveTab('researchers');
        onClose();
      } else {
        setErrorMsg('Respuesta de autenticación no válida.');
      }
    } catch (err) {
      console.error('Error en login de superusuario:', err);
      const detail = err.response?.data?.detail || 'Usuario o contraseña no válidos.';
      setErrorMsg(detail);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="global-search-backdrop"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      style={{ zIndex: 10000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
    >
      <div
        className="glass-card"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%',
          maxWidth: '440px',
          padding: '2rem 1.75rem',
          borderRadius: '16px',
          boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.4), 0 0 35px rgba(16, 185, 129, 0.15)',
          border: '1px solid var(--border-color)',
          background: 'var(--bg-surface)',
          position: 'relative'
        }}
      >
        {/* Botón cerrar */}
        <button
          type="button"
          onClick={onClose}
          style={{
            position: 'absolute',
            top: '1rem',
            right: '1rem',
            background: 'transparent',
            border: 'none',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
            padding: '0.35rem',
            borderRadius: '6px'
          }}
          title="Cerrar (Esc)"
        >
          <X size={18} />
        </button>

        {/* Encabezado */}
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          <div
            style={{
              width: '52px',
              height: '52px',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(6, 182, 212, 0.2))',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#10b981',
              marginBottom: '0.85rem',
              border: '1px solid rgba(16, 185, 129, 0.35)'
            }}
          >
            <ShieldCheck size={28} />
          </div>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 0.4rem 0', color: 'var(--text-primary)' }}>
            Acceso Especial / Evaluadores
          </h3>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.45 }}>
            Ingresa las credenciales autorizadas para desbloquear el directorio nacional de investigadores.
          </p>
        </div>

        {/* Mensaje de error */}
        {errorMsg && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.6rem',
              padding: '0.65rem 0.85rem',
              background: 'rgba(239, 68, 68, 0.12)',
              border: '1px solid rgba(239, 68, 68, 0.35)',
              borderRadius: '8px',
              color: '#ef4444',
              fontSize: '0.82rem',
              marginBottom: '1rem'
            }}
          >
            <AlertCircle size={16} style={{ flexShrink: 0 }} />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Formulario */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '1rem' }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.78rem',
                fontWeight: 600,
                color: 'var(--text-secondary)',
                marginBottom: '0.4rem',
                textTransform: 'uppercase',
                letterSpacing: '0.04em'
              }}
            >
              Usuario / ID Especial
            </label>
            <div style={{ position: 'relative' }}>
              <User
                size={16}
                style={{
                  position: 'absolute',
                  left: '0.75rem',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-secondary)'
                }}
              />
              <input
                ref={userInputRef}
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="ej. especial"
                autoComplete="username"
                style={{
                  width: '100%',
                  padding: '0.65rem 0.75rem 0.65rem 2.25rem',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  background: 'var(--bg-card)',
                  color: 'var(--text-primary)',
                  fontSize: '0.9rem',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
            </div>
          </div>

          <div style={{ marginBottom: '1.4rem' }}>
            <label
              style={{
                display: 'block',
                fontSize: '0.78rem',
                fontWeight: 600,
                color: 'var(--text-secondary)',
                marginBottom: '0.4rem',
                textTransform: 'uppercase',
                letterSpacing: '0.04em'
              }}
            >
              Contraseña de Acceso
            </label>
            <div style={{ position: 'relative' }}>
              <Lock
                size={16}
                style={{
                  position: 'absolute',
                  left: '0.75rem',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-secondary)'
                }}
              />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                autoComplete="current-password"
                style={{
                  width: '100%',
                  padding: '0.65rem 0.75rem 0.65rem 2.25rem',
                  borderRadius: '8px',
                  border: '1px solid var(--border-color)',
                  background: 'var(--bg-card)',
                  color: 'var(--text-primary)',
                  fontSize: '0.9rem',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={onClose}
              disabled={loading}
              style={{ padding: '0.6rem 1rem' }}
            >
              Cancelar
            </button>
            <button
              type="submit"
              className="btn btn-primary btn-sm"
              disabled={loading}
              style={{
                padding: '0.6rem 1.25rem',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.5rem',
                background: 'linear-gradient(135deg, #10b981, #059669)',
                borderColor: '#10b981'
              }}
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="search-spinner" />
                  <span>Verificando...</span>
                </>
              ) : (
                <>
                  <KeyRound size={15} />
                  <span>Ingresar</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default SuperuserLoginModal;
