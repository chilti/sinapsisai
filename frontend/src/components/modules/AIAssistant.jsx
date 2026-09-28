/**
 * frontend/src/components/modules/AIAssistant.jsx
 * Módulo 6: Asistente IA de Inteligencia Científica
 */

import React, { useState } from 'react';
import { Bot, Send, Sparkles, Trash2, Cpu } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';

export function AIAssistant() {
  const t = useAppStore((state) => state.t)();
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '¡Hola! Soy el Asistente de Inteligencia Científica de SNII Info TlachIA. Puedo responder preguntas sobre la producción académica de investigadores, indicadores de impacto, redes de coautoría o cartografía temática.'
    }
  ]);
  const [input, setInput] = useState('');
  const [selectedModel, setSelectedModel] = useState('lmstudio');
  const [loading, setLoading] = useState(false);

  const handleSend = async (textToSend) => {
    const q = textToSend || input;
    if (!q.trim()) return;

    const userMsg = { role: 'user', content: q };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const response = await fetch('/api/assistant/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, model_type: selectedModel, stream: true })
      });

      if (!response.body) throw new Error('No streaming body');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let aiResponseText = '';

      setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        
        // Procesar SSE data:
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const dataStr = line.replace('data: ', '').trim();
            if (dataStr === '[DONE]') break;
            try {
              const parsed = JSON.parse(dataStr);
              if (parsed.chunk) {
                aiResponseText += parsed.chunk;
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = { role: 'assistant', content: aiResponseText };
                  return updated;
                });
              }
            } catch (e) {
              aiResponseText += dataStr;
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: 'assistant', content: aiResponseText };
                return updated;
              });
            }
          }
        }
      }
    } catch (err) {
      console.error('Error con Asistente IA:', err);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Disculpa, ha ocurrido un error al conectar con el motor LLM. Asegúrate de que el servidor LM Studio local esté activo.' }
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="module-container" id="MODULO-06-ASISTENTE">
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div className="brand-icon-wrapper" style={{ background: 'linear-gradient(135deg, rgba(121, 40, 202, 0.2) 0%, rgba(255, 0, 128, 0.2) 100%)', borderColor: 'rgba(255, 0, 128, 0.3)' }}>
              <Bot size={20} style={{ color: '#ff0080' }} />
            </div>
            <div>
              <h1 style={{ fontSize: '1.6rem', marginBottom: '0.2rem' }}>{t.assistant.title}</h1>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                RAG Híbrido sobre Grafo de Conocimiento Neo4j, Padrón SNII y Embeddings
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <Cpu size={16} style={{ color: 'var(--text-muted)' }} />
            <select
              id="CTL-M06-001"
              className="form-select"
              style={{ width: 'auto' }}
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
            >
              <option value="lmstudio">LM Studio Local (DeepSeek-R1 / Qwen2.5)</option>
              <option value="openai">OpenAI GPT-4o Mini</option>
            </select>
            <button
              id="CTL-M06-007"
              className="btn btn-secondary btn-sm"
              onClick={() => setMessages([])}
              title={t.assistant.clearHistory}
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Caja de Conversación */}
      <div className="glass-card" style={{ minHeight: '450px', display: 'flex', flexDirection: 'column' }}>
        <div style={{ flex: 1, overflowY: 'auto', marginBottom: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {messages.map((m, idx) => (
            <div
              key={idx}
              style={{
                alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '80%',
                padding: '0.85rem 1.15rem',
                borderRadius: '10px',
                background: m.role === 'user' ? 'rgba(0, 242, 254, 0.12)' : 'rgba(255, 255, 255, 0.04)',
                border: `1px solid ${m.role === 'user' ? 'rgba(0, 242, 254, 0.3)' : 'rgba(255, 255, 255, 0.08)'}`,
                color: '#f8fafc',
                fontSize: '0.9rem',
                lineHeight: 1.6
              }}
            >
              {m.content}
            </div>
          ))}
          {loading && (
            <div style={{ color: 'var(--accent-cyan)', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Sparkles size={14} />
              <span>{t.assistant.streaming}</span>
            </div>
          )}
        </div>

        {/* Sugerencias Rápidas */}
        {messages.length <= 1 && (
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

        {/* Input Bar */}
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <input
            id="CTL-M06-004"
            type="text"
            className="form-input"
            placeholder={t.assistant.inputPlaceholder}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          />
          <button
            id="CTL-M06-005"
            className="btn btn-primary"
            onClick={() => handleSend()}
            disabled={loading}
          >
            <Send size={15} />
            <span>{t.assistant.send}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default AIAssistant;
