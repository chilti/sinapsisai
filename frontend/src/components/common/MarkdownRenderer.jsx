/**
 * frontend/src/components/common/MarkdownRenderer.jsx
 * Renderizador de Markdown GFM con soporte para tablas, listas, código y sanitización segura
 */

import React, { useMemo } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import './MarkdownRenderer.css';

// Configuración de marked para soporte completo de GitHub Flavored Markdown
marked.setOptions({
  gfm: true,
  breaks: true,
  pedantic: false
});

export function MarkdownRenderer({ content, className = '' }) {
  const html = useMemo(() => {
    if (!content) return '';
    try {
      // Limpiar posibles artefactos de streaming malformados (ej. JSON parciales como {"token": ...})
      const cleaned = content.replace(/\{"token":\s*"[^"]*",?\s*"chunk"?[^}]*\}/g, '');
      const rawHtml = marked.parse(cleaned);
      return DOMPurify.sanitize(rawHtml, {
        ADD_ATTR: ['target', 'rel'],
        FORBID_TAGS: ['style', 'script', 'iframe']
      });
    } catch (e) {
      console.error('Error procesando Markdown:', e);
      return content;
    }
  }, [content]);

  return (
    <div
      className={`markdown-body ${className}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export default MarkdownRenderer;
