/**
 * frontend/src/components/modules/AIAssistant.jsx
 * Módulo 6: Asistente Científico IA (RAG Híbrido, Swarm y Streaming SSE)
 * Cumple con los 11 controles del inventario QA (CTL-M06-001 a CTL-M06-011)
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Bot, Send, Sparkles, Trash2, Cpu, Copy, Check, RotateCcw,
  Download, Layers, Terminal, ChevronDown, ChevronUp, Database,
  Brain, FileText, CheckCircle2
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import apiClient from '../../api/client.js';

export function AIAssistant() {
  const t = useAppStore((state) => state.t)();
  
  // 1. Selector de Modelo LLM (CTL-M06-001)
  const [selectedModel, setSelectedModel] = useState('lmstudio'); // 'lmstudio' | 'openai'

  // 2. Modo del Asistente (CTL-M06-002)
  const [assistantMode, setAssistantMode] = useState('direct'); // 'direct' | 'agent'

  // 3. Habilidades Activas (CTL-M06-003)
  const [skills, setSkills] = useState({
    clickhouse: true,
    neo4j: true,
    snii: true,
    embeddings: true
  });

  // Mensajes de la conversación
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '¡Hola! Soy el Asistente de Inteligencia Científica de SNII Info TlachIA. Puedo responder preguntas sobre la producción académica de investigadores, indicadores de impacto, redes de coautoría o cartografía temática.',
      thoughts: 'Inicialización de memoria conversacional y registro de herramientas cienciométricas (ClickHouse, Neo4j, SNII).'
    }
  ]);

  // 4. Input de chat (CTL-M06-004)
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

  const toggleSkill = (key) => {
    setSkills((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // 5. Enviar Mensaje (CTL-M06-005) y 7. Streaming (CTL-M06-007)
  const handleSend = async (textToSend) => {
    const q = textToSend || input;
    if (!q.trim() || loading) return;

    setLastQuery(q);
    const userMsg = { role: 'user', content: q };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    const activeSkillsList = Object.keys(skills).filter((k) => skills[k]).join(', ');
    const simThoughts = `Modo: ${assistantMode.toUpperCase()} | Modelo: ${selectedModel.toUpperCase()} | Habilidades: [${activeSkillsList}]\n` +
      `Consultando Padrón SNII 2026 y motor Zero-Join para la petición: "${q.slice(0, 60)}..."`;

    setMessages((prev) => [
      ...prev,
      { role: 'assistant', content: '', thoughts: simThoughts }
    ]);

    try {
      const response = await fetch('/api/assistant/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q,
          model_type: selectedModel,
          ui_context: `mode:${assistantMode};skills:${activeSkillsList}`,
          stream: true
        })
      });

      if (!response.body) throw new Error('No stream body');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let aiText = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });

        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.replace('data: ', '').trim();
            if (dataStr === '[DONE]') break;
            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.chunk || parsed.token) {
                aiText += (parsed.chunk || parsed.token);
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && last.role === 'assistant') {
                    last.content = aiText;
                  }
                  return updated;
                });
              }
            } catch (e) {
              aiText += dataStr;
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.role === 'assistant') {
                  last.content = aiText;
                }
                return updated;
              });
            }
          }
        }
      }
    } catch (err) {
      console.error('Error streaming assistant:', err);
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last && last.role === 'assistant') {
          last.content = 'Disculpa, ha ocurrido un error al conectar con el motor LLM. Asegúrate de que el servidor LM Studio local esté activo o verifica tu conexión.';
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
    setMessages([
      {
        role: 'assistant',
        content: '¡Conversación reiniciada! ¿En qué puedo asistirte hoy sobre producción científica?',
        thoughts: 'Memoria de contexto restablecida.'
      }
    ]);
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
      {/* Header del Módulo con Controles de Modelo y Modo */}
      <div className="glass-card" style={{ marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div className="brand-icon-wrapper" style={{ background: 'linear-gradient(135deg, rgba(121, 40, 202, 0.2) 0%, rgba(255, 0, 128, 0.2) 100%)', borderColor: 'rgba(255, 0, 128, 0.3)' }}>
              <Bot size={20} style={{ color: '#ff0080' }} />
            </div>
            <div>
              <h1 style={{ fontSize: '1.5rem', margin: 0 }}>{t.assistant.title}</h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.82rem', marginTop: '0.2rem' }}>
                RAG Híbrido sobre Grafo de Conocimiento Neo4j, Padrón SNII 2026 y OLAP ClickHouse
              </p>
            </div>
          </div>

          {/* Selector de Modelo (CTL-M06-001) y Acciones Rápidas */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Cpu size={15} style={{ color: 'var(--text-muted)' }} />
              <select
                id="CTL-M06-001"
                className="form-select form-input-sm"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                style={{ width: 'auto' }}
              >
                <option value="lmstudio">LM Studio Local (DeepSeek-R1 / Qwen2.5)</option>
                <option value="openai">OpenAI GPT-4o Mini</option>
              </select>
            </div>

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
            </button>
          </div>
        </div>

        {/* Modo de Inferencia (CTL-M06-002) y Habilidades (CTL-M06-003) */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginTop: '1rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-color)' }}>
          {/* Segmented Radio Modo (CTL-M06-002) */}
          <div id="CTL-M06-002" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{t.assistant.mode_selection}:</span>
            <div style={{ display: 'flex', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '6px', padding: '2px' }}>
              <button
                className={`btn btn-sm ${assistantMode === 'direct' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ padding: '0.25rem 0.65rem', fontSize: '0.78rem', borderRadius: '4px' }}
                onClick={() => setAssistantMode('direct')}
              >
                {t.assistant.modes.direct}
              </button>
              <button
                className={`btn btn-sm ${assistantMode === 'agent' ? 'btn-primary' : 'btn-secondary'}`}
                style={{ padding: '0.25rem 0.65rem', fontSize: '0.78rem', borderRadius: '4px' }}
                onClick={() => setAssistantMode('agent')}
              >
                {t.assistant.modes.agent}
              </button>
            </div>
          </div>

          {/* Chips Habilidades Activas (CTL-M06-003) */}
          <div id="CTL-M06-003" style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{t.assistant.skills_filter}:</span>
            {[
              { id: 'clickhouse', label: 'ClickHouse' },
              { id: 'neo4j', label: 'Neo4j' },
              { id: 'snii', label: 'Padrón SNII' },
              { id: 'embeddings', label: 'Embeddings' }
            ].map((sk) => {
              const active = skills[sk.id];
              return (
                <button
                  key={sk.id}
                  className={`badge ${active ? 'badge-cyan' : 'badge-purple'}`}
                  style={{ cursor: 'pointer', opacity: active ? 1 : 0.45, border: 'none', padding: '0.25rem 0.5rem' }}
                  onClick={() => toggleSkill(sk.id)}
                >
                  {sk.label}
                </button>
              );
            })}
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
                <div
                  style={{
                    padding: '0.85rem 1.15rem',
                    borderRadius: '10px',
                    background: isUser ? 'rgba(0, 242, 254, 0.12)' : 'rgba(255, 255, 255, 0.04)',
                    border: `1px solid ${isUser ? 'rgba(0, 242, 254, 0.3)' : 'rgba(255, 255, 255, 0.08)'}`,
                    color: '#f8fafc',
                    fontSize: '0.9rem',
                    lineHeight: 1.6,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word'
                  }}
                >
                  {m.content}
                </div>

                {/* Acordeón de Razonamiento y Herramientas (CTL-M06-008) */}
                {!isUser && m.thoughts && (
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    <button
                      id="CTL-M06-008"
                      className="btn btn-secondary btn-sm"
                      style={{ fontSize: '0.72rem', padding: '0.15rem 0.5rem', background: 'transparent', border: '1px solid rgba(255, 255, 255, 0.1)' }}
                      onClick={() => setShowThoughts((prev) => ({ ...prev, [idx]: !prev[idx] }))}
                    >
                      <Brain size={12} style={{ color: 'var(--accent-purple)' }} />
                      <span>{t.assistant.thinking_process}</span>
                      {showThoughts[idx] ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    </button>

                    {showThoughts[idx] && (
                      <div style={{ marginTop: '0.35rem', padding: '0.5rem 0.75rem', background: 'rgba(0, 0, 0, 0.4)', borderRadius: '6px', border: '1px dashed rgba(255, 255, 255, 0.15)', fontFamily: 'monospace', fontSize: '0.75rem', color: '#94a3b8' }}>
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
