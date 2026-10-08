/**
 * frontend/src/components/modules/AIAssistant.jsx
 * Módulo 6: Asistente Científico IA (RAG Híbrido, Swarm y Streaming SSE)
 * Cumple con los 11 controles del inventario QA (CTL-M06-001 a CTL-M06-011)
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Bot, Send, Sparkles, Trash2, Cpu, Copy, Check, RotateCcw,
  Download, Layers, Terminal, ChevronDown, ChevronUp, Database,
  Brain, FileText, CheckCircle2, Shield
} from 'lucide-react';
import { useAppStore, isUserAdmin } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';
import MarkdownRenderer from '../common/MarkdownRenderer.jsx';

// Reutilizar el mismo detector de base URL que usa apiClient/axios
const getApiBase = () => {
  if (typeof window !== 'undefined') {
    const path = window.location.pathname;
    if (path.includes('/sinapsisai_dev')) return '/sinapsisai_dev/api';
    if (path.includes('/sinapsisai')) return '/sinapsisai/api';
    if (path.includes('/infotlachia')) return '/infotlachia/api';
  }
  return '/api';
};

export function AIAssistant() {
  const t = useAppStore((state) => state.t)();
  const userSession = useAppStore((state) => state.userSession);
  
  // Detección robusta de administrador (isUserAdmin, orcid de admin, o flag local)
  const isAdmin = Boolean(
    isUserAdmin(userSession) ||
    userSession?.orcid === '0000-0003-3659-6769' ||
    (typeof window !== 'undefined' && (
      localStorage.getItem('tlachia_is_admin') === 'true' ||
      isUserAdmin(JSON.parse(localStorage.getItem('tlachia_user') || '{}'))
    ))
  );

  // Modo del Asistente - Solo administradores tienen acceso al Agente Autónomo Híbrido
  const [assistantMode, setAssistantMode] = useState('direct'); // 'direct' | 'agent'

  useEffect(() => {
    if (!isAdmin && assistantMode === 'agent') {
      setAssistantMode('direct');
    }
  }, [isAdmin, assistantMode]);

  // Mensajes de la conversación persistentes en el store global (no se pierden al cambiar de pestaña)
  const messages = useAppStore((state) => state.assistantMessages);
  const setMessages = useAppStore((state) => state.setAssistantMessages);
  const resetAssistantMessages = useAppStore((state) => state.resetAssistantMessages);
  const selectedLlmModel = useAppStore((state) => state.selectedLlmModel);
  const setSelectedLlmModel = useAppStore((state) => state.setSelectedLlmModel);

  // Input de chat (CTL-M06-004)
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastQuery, setLastQuery] = useState('');
  const [copiedIdx, setCopiedIdx] = useState(null);
  const [showThoughts, setShowThoughts] = useState({});

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // Enviar Mensaje (CTL-M06-005) y Streaming SSE (CTL-M06-007)
  const handleSend = async (textToSend) => {
    const q = textToSend || input;
    if (!q.trim() || loading) return;

    setLastQuery(q);
    const userMsg = { role: 'user', content: q };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    const activeModel = isAdmin ? (selectedLlmModel || 'gpt-oss-120b') : 'default';
    let liveThoughts = `Modo: ${assistantMode === 'agent' ? 'AGENTE AUTÓNOMO HÍBRIDO' : 'CHAT CIENCIOMÉTRICO'}\n` +
      (isAdmin ? `Modelo: ${activeModel === 'gpt-oss-120b' ? 'C3 UNAM GPT-OSS 120B' : activeModel}\n` : '') +
      `Iniciando análisis cienciométrico para la petición: "${q.slice(0, 60)}..."\n`;

    const nextAssistantIdx = messages.length + 1;
    setShowThoughts((prev) => ({ ...prev, [nextAssistantIdx]: true }));

    setMessages((prev) => [
      ...prev,
      { role: 'assistant', content: '', thoughts: liveThoughts }
    ]);

    try {
      const response = await fetch(`${getApiBase()}/assistant/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q,
          model: activeModel,
          model_type: activeModel,
          ui_context: `mode:${assistantMode}`,
          stream: true
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      if (!response.body) throw new Error('No stream body');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let aiText = '';
      let isDone = false;
      let buffer = '';

      while (!isDone) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        // Preservar la última línea si está incompleta para el siguiente chunk
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('data: ')) {
            const dataStr = trimmed.slice(6).trim();
            if (dataStr === '[DONE]') {
              isDone = true;
              break;
            }
            try {
              const parsed = JSON.parse(dataStr);

              // 1. Evento de inicio de herramienta
              if (parsed.type === 'tool_start') {
                const toolName = parsed.tool || parsed.name || 'Herramienta';
                let inputDesc = '';
                if (parsed.input) {
                  if (typeof parsed.input === 'object') {
                    if (parsed.input.cypher_query) {
                      inputDesc = `\n🕸️ Consulta Cypher (Neo4j Grafo de Conocimiento):\n${parsed.input.cypher_query}`;
                    } else if (parsed.input.sql_query) {
                      inputDesc = `\n📊 Consulta SQL (ClickHouse / DuckDB):\n${parsed.input.sql_query}`;
                    } else if (parsed.input.query) {
                      inputDesc = `\n🔍 Búsqueda: "${parsed.input.query}"`;
                    } else {
                      inputDesc = `\nParámetros:\n${JSON.stringify(parsed.input, null, 2)}`;
                    }
                  } else {
                    inputDesc = `\nEntrada: ${parsed.input}`;
                  }
                }
                liveThoughts += `\n⚙️ [Ejecutando herramienta: ${toolName}]${inputDesc}\n`;

                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
                    updated[lastIdx] = { ...updated[lastIdx], thoughts: liveThoughts };
                  }
                  return updated;
                });
              } 
              // 2. Evento de fin de herramienta con resultados
              else if (parsed.type === 'tool_end') {
                const toolName = parsed.tool || parsed.name || 'Herramienta';
                const outVal = parsed.output || parsed.result || '';
                liveThoughts += `✅ [Resultado de ${toolName}]: ${String(outVal).slice(0, 500)}${String(outVal).length > 500 ? '...' : ''}\n`;

                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
                    updated[lastIdx] = { ...updated[lastIdx], thoughts: liveThoughts };
                  }
                  return updated;
                });
              }

              // 3. Tokens de la respuesta generada
              const tokenText = parsed.token || parsed.chunk || '';
              if (tokenText && parsed.type !== 'tool_start' && parsed.type !== 'tool_end') {
                aiText += tokenText;
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
                    updated[lastIdx] = { ...updated[lastIdx], content: aiText, thoughts: liveThoughts };
                  }
                  return updated;
                });
              }
              if (parsed.error) {
                throw new Error(parsed.error);
              }
            } catch (e) {
              // Si no es JSON válido (ej. texto puro no serializado que no sea fragmento roto)
              if (dataStr && !dataStr.startsWith('{') && dataStr !== '[DONE]') {
                aiText += dataStr;
                setMessages((prev) => {
                  const updated = [...prev];
                  const lastIdx = updated.length - 1;
                  if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
                    updated[lastIdx] = { ...updated[lastIdx], content: aiText };
                  }
                  return updated;
                });
              }
            }
          }
        }
      }
    } catch (err) {
      console.error('Error streaming assistant:', err);
      setMessages((prev) => {
        const updated = [...prev];
        const lastIdx = updated.length - 1;
        if (lastIdx >= 0 && updated[lastIdx].role === 'assistant') {
          updated[lastIdx] = {
            ...updated[lastIdx],
            content: `⚠️ Error al conectar con el Asistente de Inteligencia Científica: ${err.message}. Verifica que el servidor LLM esté activo.`
          };
        }
        return updated;
      });
    } finally {
      setLoading(false);
    }
  };


  // 6. Limpiar Conversación (CTL-M06-006)
  const handleClear = async () => {
    try {
      await apiClient.clearChatSession();
    } catch (e) {
      // Ignorar error de red si ocurre
    }
    resetAssistantMessages();
    setInput('');
  };

  // 9. Copiar al Portapapeles (CTL-M06-009)
  const handleCopy = (content, idx) => {
    navigator.clipboard.writeText(content);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2500);
  };

  // 10. Regenerar Respuesta (CTL-M06-010)
  const handleRetry = () => {
    if (lastQuery) {
      handleSend(lastQuery);
    }
  };

  // 11. Exportar Conversación en Markdown (CTL-M06-011)
  const handleExportChat = () => {
    const markdownContent = messages.map((m) => {
      const header = m.role === 'user' ? '### 👤 Usuario' : '### 🤖 Asistente Científico TlachIA';
      const thoughtsBlock = m.thoughts ? `\n> *Razonamiento*: ${m.thoughts}\n` : '';
      return `${header}\n${thoughtsBlock}\n${m.content}\n\n---`;
    }).join('\n\n');

    const blob = new Blob([markdownContent], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Conversacion_TlachIA_${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <div className="module-container" id="MODULO-06-ASISTENTE">
      {/* Header del Módulo con Controles de Modo y Acciones */}
      <div className="glass-card" style={{ marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div className="brand-icon-wrapper" style={{ background: 'linear-gradient(135deg, rgba(121, 40, 202, 0.2) 0%, rgba(255, 0, 128, 0.2) 100%)', borderColor: 'rgba(255, 0, 128, 0.3)' }}>
              <Bot size={20} style={{ color: '#ff0080' }} />
            </div>
            <div>
              <h1 style={{ fontSize: '1.5rem', margin: 0 }}>{t.assistant.title}</h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', marginTop: '0.2rem' }}>
                RAG Híbrido sobre Grafo de Conocimiento Neo4j, Padrón de Investigadoras e Investigadores 2026 y OLAP ClickHouse
              </p>
            </div>
          </div>

          {/* Modo de Inferencia (Visible para Administradores) y Acciones Rápidas */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            {isAdmin ? (
              <div id="CTL-M06-002" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginRight: '0.5rem' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{t.assistant.mode_selection}:</span>
                <div style={{
                  display: 'flex',
                  background: 'rgba(255, 255, 255, 0.05)',
                  borderRadius: '8px',
                  padding: '3px',
                  border: '1px solid rgba(255, 255, 255, 0.12)',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)'
                }}>
                  <button
                    type="button"
                    className={`btn btn-sm ${assistantMode === 'direct' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{
                      padding: '0.3rem 0.75rem',
                      fontSize: '0.78rem',
                      borderRadius: '6px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      fontWeight: assistantMode === 'direct' ? 600 : 400
                    }}
                    onClick={() => setAssistantMode('direct')}
                  >
                    <Bot size={13} />
                    <span>{t.assistant.modes.direct}</span>
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm ${assistantMode === 'agent' ? 'btn-primary' : 'btn-ghost'}`}
                    style={{
                      padding: '0.3rem 0.75rem',
                      fontSize: '0.78rem',
                      borderRadius: '6px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                      fontWeight: assistantMode === 'agent' ? 600 : 400,
                      background: assistantMode === 'agent' ? 'linear-gradient(135deg, #7928ca 0%, #ff0080 100%)' : undefined,
                      boxShadow: assistantMode === 'agent' ? '0 0 12px rgba(255, 0, 128, 0.35)' : undefined
                    }}
                    onClick={() => setAssistantMode('agent')}
                  >
                    <Sparkles size={13} style={{ color: assistantMode === 'agent' ? '#fff' : '#ff0080' }} />
                    <span>{t.assistant.modes.agent}</span>
                  </button>
                </div>

                {/* Selector de Modelo Exclusivo para Administradores */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  background: 'rgba(0, 242, 254, 0.08)',
                  padding: '3px 8px',
                  borderRadius: '8px',
                  border: '1px solid rgba(0, 242, 254, 0.25)',
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.2)'
                }}>
                  <Cpu size={14} style={{ color: 'var(--accent-cyan)' }} />
                  <select
                    className="form-select form-input-sm"
                    style={{
                      fontSize: '0.78rem',
                      padding: '0.15rem 0.4rem',
                      height: '28px',
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--text-primary)',
                      fontWeight: 600,
                      cursor: 'pointer',
                      outline: 'none'
                    }}
                    value={selectedLlmModel}
                    onChange={(e) => setSelectedLlmModel(e.target.value)}
                    title="Modelo de Lenguaje LLM (Configuración Exclusiva para Administradores)"
                  >
                    <option value="gpt-oss-120b" style={{ background: '#111827', color: '#fff' }}>🚀 C3 GPT-OSS 120B</option>
                    <option value="Kimi-K2.6" style={{ background: '#111827', color: '#fff' }}>🧠 C3 Kimi K2.6</option>
                    <option value="openai/default" style={{ background: '#111827', color: '#fff' }}>💻 LM Studio Local</option>
                    <option value="gemini-3.5-flash-lite" style={{ background: '#111827', color: '#fff' }}>✨ Google Gemini</option>
                  </select>
                </div>
              </div>
            ) : (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '0.35rem 0.75rem',
                  borderRadius: '6px',
                  background: 'rgba(255, 255, 255, 0.04)',
                  border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
                  fontSize: '0.78rem',
                  color: 'var(--text-muted)'
                }}
                title="El Agente Autónomo Híbrido está reservado para perfiles con privilegios de Administrador. Puedes autenticarte en Mi Espacio."
              >
                <Shield size={13} style={{ color: '#f59e0b' }} />
                <span>Modo: {t.assistant.modes.direct}</span>
              </div>
            )}

            {/* Exportar Conversación (CTL-M06-011) */}
            <button
              id="CTL-M06-011"
              className="btn btn-secondary btn-sm"
              onClick={handleExportChat}
              title={t.assistant.btn_export_chat}
            >
              <Download size={13} />
              <span>Exportar .md</span>
            </button>

            {/* Limpiar Conversación (CTL-M06-006) */}
            <button
              id="CTL-M06-006"
              className="btn btn-secondary btn-sm"
              onClick={handleClear}
              title={t.assistant.btn_clear}
            >
              <Trash2 size={13} />
              <span>{t.assistant.btn_clear}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Contenedor Principal del Chat (CTL-M06-007) */}
      <div className="glass-card" id="CTL-M06-007" style={{ minHeight: '480px', display: 'flex', flexDirection: 'column' }}>
        {/* Lista de Mensajes */}
        <div style={{ flex: 1, overflowY: 'auto', marginBottom: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem', paddingRight: '0.25rem' }}>
          {messages.map((m, idx) => {
            const isUser = m.role === 'user';
            return (
              <div
                key={idx}
                style={{
                  alignSelf: isUser ? 'flex-end' : 'flex-start',
                  maxWidth: '85%',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.35rem'
                }}
              >
                {/* Contenido del Mensaje: Solo si es usuario o si hay texto generado */}
                {(isUser || (m.content && m.content.trim().length > 0)) && (
                  <div
                    style={{
                      padding: '0.85rem 1.15rem',
                      borderRadius: '10px',
                      background: isUser ? 'rgba(0, 242, 254, 0.12)' : 'var(--bg-card)',
                      border: `1px solid ${isUser ? 'rgba(0, 242, 254, 0.3)' : 'var(--border-subtle)'}`,
                      color: 'var(--text-primary)',
                      fontSize: '0.9rem',
                      lineHeight: 1.6,
                      wordBreak: 'break-word',
                      boxShadow: isUser ? 'none' : '0 2px 8px rgba(0, 0, 0, 0.04)'
                    }}
                  >
                    {isUser ? (
                      <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
                    ) : (
                      <MarkdownRenderer content={m.content} />
                    )}
                  </div>
                )}

                {/* Acordeón de Razonamiento y Herramientas (CTL-M06-008) */}
                {!isUser && m.thoughts && (
                  <div style={{ fontSize: '0.78rem' }}>
                    <button
                      id="CTL-M06-008"
                      className="assistant-thoughts-btn"
                      onClick={() => setShowThoughts((prev) => ({ ...prev, [idx]: !prev[idx] }))}
                    >
                      <Brain size={13} style={{ color: 'var(--accent-purple)' }} />
                      <span>{t.assistant.thinking_process}</span>
                      {showThoughts[idx] ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    </button>

                    {showThoughts[idx] && (
                      <div className="assistant-thoughts-box">
                        {m.thoughts}
                      </div>
                    )}
                  </div>
                )}

                {/* Acciones de Mensaje (Copiar CTL-M06-009, Regenerar CTL-M06-010) */}
                {!isUser && m.content && (
                  <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.2rem' }}>
                    {/* Botón Copiar (CTL-M06-009) */}
                    <button
                      id="CTL-M06-009"
                      className="btn btn-secondary btn-sm"
                      style={{ fontSize: '0.72rem', padding: '0.15rem 0.5rem', background: 'transparent' }}
                      onClick={() => handleCopy(m.content, idx)}
                    >
                      {copiedIdx === idx ? <Check size={11} style={{ color: '#34d399' }} /> : <Copy size={11} />}
                      <span>{copiedIdx === idx ? t.assistant.copied_alert : t.assistant.btn_copy}</span>
                    </button>

                    {/* Botón Regenerar (CTL-M06-010) */}
                    {idx === messages.length - 1 && (
                      <button
                        id="CTL-M06-010"
                        className="btn btn-secondary btn-sm"
                        style={{ fontSize: '0.72rem', padding: '0.15rem 0.5rem', background: 'transparent' }}
                        onClick={handleRetry}
                        disabled={loading}
                      >
                        <RotateCcw size={11} />
                        <span>{t.assistant.btn_regenerate}</span>
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {loading && (
            <div style={{ color: 'var(--accent-cyan)', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 0' }}>
              <Sparkles size={14} className="spin" />
              <span>{t.assistant.streaming}</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Sugerencias Rápidas de Prompt */}
        {messages.length <= 2 && (
          <div style={{ marginBottom: '1rem' }}>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.4rem' }}>
              {t.assistant.suggestionsTitle}:
            </span>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {t.assistant.suggestions.map((s, idx) => (
                <button
                  key={idx}
                  className="btn btn-secondary btn-sm"
                  style={{ fontSize: '0.75rem', padding: '0.35rem 0.65rem' }}
                  onClick={() => handleSend(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Barra de Entrada (Input CTL-M06-004 y Botón Enviar CTL-M06-005) */}
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <input
            id="CTL-M06-004"
            type="text"
            className="form-input"
            placeholder={t.assistant.inputPlaceholder}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            disabled={loading}
          />

          <button
            id="CTL-M06-005"
            className="btn btn-primary"
            onClick={() => handleSend()}
            disabled={loading || !input.trim()}
          >
            <Send size={15} />
            <span>{t.assistant.btn_send}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default AIAssistant;
