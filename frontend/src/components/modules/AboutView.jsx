/**
 * frontend/src/components/modules/AboutView.jsx
 * Módulo Institucional: Acerca de Info TlachIA, Equipo de Trabajo, Cobertura SNII-ROR y Auditoría
 */

import React, { useState, useEffect } from 'react';
import {
  Info,
  ShieldCheck,
  Users,
  Building2,
  GraduationCap,
  FileText,
  Download,
  ExternalLink,
  Database,
  Layers,
  Sparkles,
  GitBranch,
  Network,
  X,
  Maximize2,
  CheckCircle2,
  TrendingUp,
  Cpu,
  Eye,
  BookOpen,
  Clock,
  Calendar
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore.js';
import { apiClient } from '../../api/client.js';

export function AboutView() {
  const theme = useAppStore((state) => state.theme);
  const isLight = theme === 'claro';

  const [stats, setStats] = useState({
    snii_total: 82334,
    snii_with_orcid: 33677,
    snii_with_oa: 34323,
    institutions_total: 2263,
    institutions_with_ror: 204,
    ror_high_confidence: 204,
    ror_coverage_pct: 9.0
  });
  const [systemInfo, setSystemInfo] = useState(null);
  const [showModalReport, setShowModalReport] = useState(false);

  useEffect(() => {
    async function loadStats() {
      try {
        const res = await apiClient.getSniiRorStats();
        if (res && res.snii_total) {
          setStats(res);
        }
      } catch (err) {
        console.warn('Usando estadísticas pre-calculadas de SNII/ROR:', err);
      }
    }
    async function loadSystemInfo() {
      try {
        const info = await apiClient.getSystemInfo();
        if (info) {
          setSystemInfo(info);
        }
      } catch (err) {
        console.warn('No se pudieron obtener metadatos de /api/info:', err);
      }
    }
    loadStats();
    loadSystemInfo();
  }, []);

  const reportUrl = apiClient.getSniiAuditReportUrl(false);
  const downloadUrl = apiClient.getSniiAuditReportUrl(true);

  return (
    <div className="module-container" style={{ padding: '0.75rem 1.5rem 3rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1400px', margin: '0 auto' }}>

      {/* ── 1. Encabezado de la Plataforma ─────────────────────────────────── */}
      <div className="glass-card" style={{ padding: '1.75rem 2rem', position: 'relative', overflow: 'hidden' }}>
        <div style={{
          position: 'absolute', top: '-20px', right: '-20px', width: '220px', height: '220px',
          background: 'radial-gradient(circle, rgba(0, 242, 254, 0.12) 0%, transparent 70%)',
          pointerEvents: 'none', borderRadius: '50%'
        }} />

        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.25rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', flexWrap: 'wrap' }}>
              <span className="badge badge-cyan" style={{ fontSize: '0.75rem' }}>v2.0 Arquitectura Ecosistémica</span>
              <span className="badge badge-amber" style={{ fontSize: '0.75rem', background: 'rgba(245, 158, 11, 0.12)', color: '#f59e0b', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
                Proyecto Piloto Demostrativo
              </span>
              <span className="badge badge-purple" style={{ fontSize: '0.75rem' }}>Ciencia Abierta UNAM</span>
            </div>
            <h1 style={{ fontSize: '1.85rem', fontWeight: 800, margin: '0 0 0.4rem 0', letterSpacing: '-0.02em', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <Sparkles style={{ color: 'var(--accent-cyan)' }} size={26} />
              Acerca de Info TlachIA SNII
            </h1>
            <p style={{ fontSize: '0.95rem', color: 'var(--text-secondary)', margin: 0, maxWidth: '950px', lineHeight: 1.6 }}>
              Plataforma de Inteligencia Científica, Evaluación Cienciométrica y Mapeo Topológico del Sistema Nacional de Investigadoras e Investigadores (SNII). Un desarrollo colaborativo de la <b>Facultad de Ciencias</b> y el <b>Centro de Ciencias de la Complejidad (C3)</b> de la Universidad Nacional Autónoma de México (UNAM).
            </p>
          </div>

          <a
            href="https://github.com/chilti/sinapsisai"
            target="_blank"
            rel="noreferrer"
            className="btn btn-secondary btn-sm"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', padding: '0.5rem 0.9rem' }}
          >
            <GitBranch size={15} />
            <span>github.com/chilti/sinapsisai</span>
            <ExternalLink size={13} style={{ opacity: 0.6 }} />
          </a>
        </div>

        {/* Nota Institucional del Piloto Demostrativo y Metodología */}
        <div style={{
          padding: '1.15rem 1.35rem',
          borderRadius: '10px',
          background: isLight ? 'rgba(245, 158, 11, 0.05)' : 'rgba(245, 158, 11, 0.07)',
          borderLeft: '4px solid #f59e0b',
          border: '1px solid rgba(245, 158, 11, 0.25)',
          borderLeftWidth: '4px',
          maxWidth: '100%',
          fontSize: '0.88rem',
          lineHeight: '1.65',
          color: 'var(--text-secondary)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700, color: isLight ? '#b45309' : '#fbbf24', marginBottom: '0.45rem', fontSize: '0.92rem' }}>
            <Info size={17} />
            <span>Proyecto Piloto Demostrativo en Proceso Continuo de Alimentación</span>
          </div>
          <p style={{ margin: '0 0 0.55rem 0' }}>
            Esta versión de <b>Info TlachIA SNII</b> opera como un <b>proyecto piloto demostrativo</b> cuyos repositorios y bases de conocimiento se encuentran en constante proceso de alimentación, enriquecimiento y verificación.
          </p>
          <p style={{ margin: 0 }}>
            Para la conformación de este corpus, la plataforma articula los metadatos globales de literatura científica de <b>OpenAlex</b> con los registros oficiales del <b>Padrón del SNII</b>. Sobre esta base, se emplean algoritmos cienciométricos avanzados y <b>modelos de lenguaje (LLMs)</b> para la búsqueda, resolución y homologación de identificadores persistentes unívocos: <b>ORCID</b> (<em>Open Researcher and Contributor ID</em>) para la desambiguación autoral de investigadoras e investigadores, y <b>ROR</b> (<em>Research Organization Registry</em>) para la estandarización institucional de dependencias y centros de investigación.
          </p>
        </div>
      </div>

      {/* ── 1.5. Estado de los Datos, Última Actualización y Snapshot ──────── */}
      <div
        className="glass-card"
        style={{
          padding: '1.5rem',
          border: '1px solid rgba(0, 242, 254, 0.3)',
          background: isLight
            ? 'linear-gradient(135deg, rgba(0, 242, 254, 0.05) 0%, rgba(16, 185, 129, 0.04) 100%)'
            : 'linear-gradient(135deg, rgba(0, 242, 254, 0.08) 0%, rgba(16, 185, 129, 0.05) 100%)',
          boxShadow: '0 8px 32px rgba(0, 242, 254, 0.08)'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
            <div style={{
              width: '42px', height: '42px', borderRadius: '10px',
              background: 'linear-gradient(135deg, #00f2fe 0%, #0284c7 100%)',
              color: '#0f172a', display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 14px rgba(0, 242, 254, 0.35)', fontWeight: 800
            }}>
              <Database size={22} />
            </div>
            <div>
              <h2 style={{ fontSize: '1.2rem', fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                Estado de los Datos y Última Actualización
              </h2>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.2rem 0 0 0' }}>
                Trazabilidad del pipeline de métricas, snapshot oficial de OpenAlex y cobertura nacional
              </p>
            </div>
          </div>

          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: '0.5rem',
            padding: '0.45rem 0.95rem', borderRadius: '20px',
            background: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.35)',
            fontSize: '0.8rem', fontWeight: 700, color: '#10b981'
          }}>
            <span style={{
              width: '8px', height: '8px', borderRadius: '50%',
              backgroundColor: '#10b981', boxShadow: '0 0 8px #10b981'
            }} />
            <span>Pipeline Sincronizado</span>
          </div>
        </div>

        {/* Grid de 4 tarjetas de métricas del estado */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem' }}>
          {/* Última Actualización */}
          <div style={{
            padding: '1rem 1.15rem', borderRadius: '10px',
            background: isLight ? 'rgba(0,0,0,0.02)' : 'rgba(255,255,255,0.02)',
            border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: '0.3rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              <Clock size={14} style={{ color: 'var(--accent-cyan)' }} />
              <span>Última Actualización</span>
            </div>
            <div style={{ fontSize: '0.95rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              {systemInfo?.last_updated
                ? new Date(systemInfo.last_updated).toLocaleDateString('es-MX', {
                    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
                  })
                : '7 de octubre de 2026, 11:20'}
            </div>
          </div>

          {/* Snapshot de OpenAlex */}
          <div style={{
            padding: '1rem 1.15rem', borderRadius: '10px',
            background: isLight ? 'rgba(0,0,0,0.02)' : 'rgba(255,255,255,0.02)',
            border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: '0.3rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              <Calendar size={14} style={{ color: '#10b981' }} />
              <span>Snapshot de OpenAlex</span>
            </div>
            <div style={{ fontSize: '0.95rem', fontWeight: 800, color: '#10b981' }}>
              {systemInfo?.openalex_release || (systemInfo?.snapshot_date ? `OpenAlex Snapshot ${systemInfo.snapshot_date}` : 'OpenAlex Snapshot 2026-09-23')}
            </div>
          </div>

          {/* Obras Analizadas */}
          <div style={{
            padding: '1rem 1.15rem', borderRadius: '10px',
            background: isLight ? 'rgba(0,0,0,0.02)' : 'rgba(255,255,255,0.02)',
            border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: '0.3rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              <Layers size={14} style={{ color: '#f59e0b' }} />
              <span>Obras Indizadas</span>
            </div>
            <div style={{ fontSize: '0.95rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              {(systemInfo?.total_works || 1652927).toLocaleString()} artículos analizados
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              {(systemInfo?.total_author_links || 2241792).toLocaleString()} vínculos de autoría
            </span>
          </div>

          {/* Motor Analítico */}
          <div style={{
            padding: '1rem 1.15rem', borderRadius: '10px',
            background: isLight ? 'rgba(0,0,0,0.02)' : 'rgba(255,255,255,0.02)',
            border: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: '0.3rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              <Cpu size={14} style={{ color: 'var(--accent-purple)' }} />
              <span>Motor Analítico y Grafo</span>
            </div>
            <div style={{ fontSize: '0.95rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              {systemInfo?.database_engine || 'ClickHouse + Neo4j + Qdrant'}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              Versión {systemInfo?.pipeline_version || '2.0.0'}
            </span>
          </div>
        </div>
      </div>

      {/* ── 2. Raíces e Identidad: El Significado de Tlachia (Náhuatl) ──────── */}
      <div
        className="glass-card"
        style={{
          padding: '1.5rem',
          background: isLight
            ? 'linear-gradient(135deg, rgba(245, 158, 11, 0.05), rgba(0, 242, 254, 0.05))'
            : 'linear-gradient(135deg, rgba(245, 158, 11, 0.08), rgba(0, 242, 254, 0.08))',
          borderLeft: '4px solid #f59e0b'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
          <div style={{
            width: '36px', height: '36px', borderRadius: '8px',
            background: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <Eye size={20} />
          </div>
          <div>
            <h3 style={{ fontSize: '1.15rem', fontWeight: 800, margin: 0, color: isLight ? '#b45309' : '#fbbf24' }}>
              Raíces e Identidad: El Significado de <em>Tlachia</em> en la Lengua Náhuatl
            </h3>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: 0 }}>
              Etimología prehispánica y su convergencia con la Inteligencia Artificial (Tlach-IA)
            </p>
          </div>
        </div>

        <p style={{ fontSize: '0.9rem', lineHeight: '1.65', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          El nombre de la plataforma tiene su origen en el verbo náhuatl clásico <b><em>tlachia</em></b> (pronunciado <em>[tɬaˈt͡ʃi.a]</em>), cuyos significados fundamentales son <b>«mirar», «observar», «contemplar con atención», «abrir los ojos»</b> y <b>«cobrar la vista»</b> (despertar del sueño hacia la lucidez y el discernimiento).
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '0.85rem', marginBottom: '1rem' }}>
          <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ fontWeight: 700, fontSize: '0.88rem', color: '#f59e0b', marginBottom: '0.25rem' }}>
              👁️ <em>Tlachia</em> (Verbo raíz)
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Mirar con intención, observar detenidamente el entorno, vigilar, abrir los ojos y percibir con claridad lo que antes permanecía oculto o disperso.
            </div>
          </div>

          <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--accent-cyan)', marginBottom: '0.25rem' }}>
              🔭 <em>Tlachialoyan</em> (Lugar de observación)
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Mirador, atalaya o puesto elevado desde el cual se contempla el horizonte en su totalidad, análogo a un observatorio científico contemporáneo.
            </div>
          </div>

          <div style={{ padding: '0.85rem 1rem', borderRadius: '10px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--accent-purple)', marginBottom: '0.25rem' }}>
              💡 <em>Tlachieliztli</em> (La mirada lúcida)
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              La facultad de la vista, la observación sistemática y el acto consciente de generar conocimiento a través del examen riguroso de la realidad.
            </div>
          </div>
        </div>

        <div style={{
          padding: '0.85rem 1.15rem', borderRadius: '8px',
          background: isLight ? 'rgba(0,0,0,0.02)' : 'rgba(0,0,0,0.2)',
          borderLeft: '3px solid var(--accent-cyan)',
          fontSize: '0.84rem', lineHeight: '1.6', color: 'var(--text-secondary)'
        }}>
          <strong style={{ color: 'var(--accent-cyan)' }}>Convergencia con la Inteligencia Artificial (Tlach-IA): </strong>
          En el ecosistema académico de la UNAM, <b>TlachIA</b> une esta herencia del «mirar atento» con la <b>Inteligencia Artificial (IA)</b>. No se trata simplemente de compilar datos pasivos, sino de ofrecer una <b>atalaya u observatorio analítico</b> para que las comunidades científicas puedan <em>abrir los ojos</em> sobre su propia trayectoria, descubrir patrones emergentes, iluminar sus redes humanas de colaboración y potenciar el impacto social de la investigación en México e Iberoamérica.
        </div>
      </div>

      {/* ── 3. Aviso de Privacidad y Fuentes de Datos Públicas ─────────────── */}
      <div
        className="glass-card"
        style={{
          padding: '1.25rem 1.5rem',
          borderLeft: '4px solid #10b981',
          background: isLight ? 'rgba(16, 185, 129, 0.04)' : 'rgba(16, 185, 129, 0.08)'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.5rem' }}>
          <ShieldCheck size={20} style={{ color: '#10b981' }} />
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, color: isLight ? '#065f46' : '#34d399' }}>
            Aviso de Privacidad, Ética y Fuentes de Datos de Acceso Abierto
          </h3>
        </div>
        <p style={{ fontSize: '0.88rem', lineHeight: '1.6', color: 'var(--text-secondary)', margin: '0 0 0.5rem 0' }}>
          La información bibliométrica y de producción científica procesada en <b>Info TlachIA</b> procede exclusivamente de fuentes de datos públicas y repositorios de acceso libre: <b>OpenAlex</b>, <b>Scopus</b> (uso de scopus id), <b>ORCID</b>, padrones públicos del <b>SNII (CONAHCYT)</b>, <b>SIIA (UNAM)</b>, <b>Research Organization Registry (ROR)</b> y catálogos globales de metadatos.
        </p>
        <p style={{ fontSize: '0.84rem', lineHeight: '1.55', color: 'var(--text-muted)', margin: 0 }}>
          <b>Privacidad y Datos Personales:</b> Este sistema no almacena ni procesa datos personales sensibles. La plataforma se limita al análisis de metadatos públicos de producción y filiación científica, con estricto apego a los principios de Ciencia Abierta, trazabilidad metodológica y transparencia en la investigación nacional.
        </p>
      </div>

      {/* ── 3. Equipo de Trabajo & Créditos Institucionales ────────────────── */}
      <div className="glass-card" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1.25rem' }}>
          <Users size={22} style={{ color: 'var(--accent-purple)' }} />
          <div>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, margin: 0 }}>Equipo de Trabajo & Colaboradores</h2>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>Investigadoras e Investigadores responsables y estudiantes de la UNAM</p>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))', gap: '1.5rem' }}>

          {/* Columna: Investigadores Principales */}
          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '1.25rem', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '1rem', color: 'var(--accent-cyan)' }}>
              <Building2 size={17} />
              <h3 style={{ fontSize: '0.95rem', fontWeight: 700, margin: 0, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Facultad de Ciencias & Centro de Ciencias de la Complejidad (C3)
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              <div style={{ padding: '0.5rem 0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>Dr. Humberto Andrés Carrillo Calvet</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Facultad de Ciencias y Centro de Ciencias de la Complejidad (UNAM)</div>
              </div>

              <div style={{ padding: '0.5rem 0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>Dr. José Luis Jiménez Andrade</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Facultad de Ciencias y Centro de Ciencias de la Complejidad (UNAM)</div>
              </div>

              <div style={{ padding: '0.5rem 0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>Dra. María Victoria Guzmán Sánchez</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Facultad de Ciencias (UNAM)</div>
              </div>

              <div style={{ padding: '0.5rem 0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>Dr. Ricardo Arencibia Jorge</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Centro de Ciencias de la Complejidad (UNAM)</div>
              </div>

              <div style={{ padding: '0.5rem 0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>M. en C. Romel Calero Ramos</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Centro de Ciencias de la Complejidad (UNAM) • Infraestructura y Administración ClickHouse</div>
              </div>

              <div style={{ padding: '0.5rem 0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.02)' }}>
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>M. en C. Lorena Delgado Quiroz</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Centro de Ciencias de la Complejidad (UNAM)</div>
              </div>
            </div>
          </div>

          {/* Columna: Estudiantes de la Facultad de Ciencias */}
          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '1.25rem', borderRadius: '12px', border: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '1rem', color: '#f59e0b' }}>
              <GraduationCap size={18} />
              <h3 style={{ fontSize: '0.95rem', fontWeight: 700, margin: 0, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Estudiantes de la Facultad de Ciencias (UNAM)
              </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.02)', borderLeft: '3px solid #f59e0b' }}>
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                  Ana Valeria Deloya Andrade
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  Ingeniería de Prompts para describir, contextualizar y analizar gráficas cienciométricas automatizadas.
                </div>
              </div>

              <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.02)', borderLeft: '3px solid var(--accent-cyan)' }}>
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                  Rodrigo Aldair Ortega Venegas
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  Modelado y visualización del impacto científico alineado a los 17 Objetivos de Desarrollo Sostenible (ODS) de la ONU.
                </div>
              </div>

              <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(255,255,255,0.02)', borderLeft: '3px solid var(--accent-purple)' }}>
                <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                  Leonardo Vázquez Rodríguez
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  Visualización de trayectorias científicas, dinámica temporal de citación y movilidad académica.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── 4. Cobertura de Datos: SNII y Vinculación ROR ───────────────────── */}
      <div className="glass-card" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1rem' }}>
          <TrendingUp size={22} style={{ color: 'var(--accent-cyan)' }} />
          <div>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, margin: 0 }}>Cobertura de Datos: Padrón SNII & ROR</h2>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
              Estadísticas sobre el mapeo de investigadoras e investigadores del país y su resolución de filiación vía Research Organization Registry
            </p>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '1rem' }}>
          <div style={{ padding: '1rem', borderRadius: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Investigadoras e Investigadores SNII</span>
            <div style={{ fontSize: '1.55rem', fontWeight: 800, color: 'var(--accent-cyan)', marginTop: '0.2rem' }}>
              {(stats.snii_total || 82334).toLocaleString()}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Padrón histórico</span>
          </div>

          <div style={{ padding: '1rem', borderRadius: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Con ORCID Verificado</span>
            <div style={{ fontSize: '1.55rem', fontWeight: 800, color: '#10b981', marginTop: '0.2rem' }}>
              {(stats.snii_with_orcid || 33677).toLocaleString()}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Identificador persistente unívoco</span>
          </div>

          <div style={{ padding: '1rem', borderRadius: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Con OpenAlex ID</span>
            <div style={{ fontSize: '1.55rem', fontWeight: 800, color: 'var(--accent-purple)', marginTop: '0.2rem' }}>
              {(stats.snii_with_oa || 34323).toLocaleString()}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Obras indizadas globalmente</span>
          </div>

          <div style={{ padding: '1rem', borderRadius: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Entidades y Dependencias</span>
            <div style={{ fontSize: '1.55rem', fontWeight: 800, color: '#f59e0b', marginTop: '0.2rem' }}>
              {(stats.institutions_total || 2263).toLocaleString()}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Unidades institucionales mapeadas</span>
          </div>

          <div style={{ padding: '1rem', borderRadius: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>ROR Confianza ≥ 70%</span>
            <div style={{ fontSize: '1.55rem', fontWeight: 800, color: '#00f2fe', marginTop: '0.2rem' }}>
              {(stats.ror_high_confidence || 204).toLocaleString()}
            </div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Resolución institucional alta</span>
          </div>
        </div>
      </div>

      {/* ── 5. Informe Ejecutivo: Auditoría Cienciométrica Padrón SNII 2026 ── */}
      <div className="glass-card" style={{ padding: '1.5rem', background: 'linear-gradient(135deg, rgba(0, 242, 254, 0.05), rgba(168, 85, 247, 0.05))' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ maxWidth: '850px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
              <FileText size={20} style={{ color: 'var(--accent-cyan)' }} />
              <h3 style={{ fontSize: '1.1rem', fontWeight: 800, margin: 0 }}>
                📑 Informe Ejecutivo del Padrón SNII 2026
              </h3>
            </div>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.55, margin: 0 }}>
              Análisis comparativo de la transición 2025 ➔ 2026: <b>4,812 nuevos ingresos</b>, <b>1,606 bajas</b>, <b>2,351 promociones de nivel</b> (incluyendo 169 nuevas Investigadoras e Investigadores Eméritos), movilidad entre instituciones y desglose analítico en las 9 áreas del conocimiento.
            </p>
          </div>

          <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
            <button
              onClick={() => setShowModalReport(true)}
              className="btn btn-primary btn-sm"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.85rem' }}
            >
              <Maximize2 size={14} />
              <span>Ver Informe Completo</span>
            </button>
            <a
              href={downloadUrl}
              download="reporte_auditoria_snii_2026.html"
              className="btn btn-secondary btn-sm"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.85rem' }}
            >
              <Download size={14} />
              <span>Descargar HTML</span>
            </a>
          </div>
        </div>
      </div>

      {/* ── 6. Arquitectura Tecnológica & Metamodelo de Grafo Neo4j ─────────── */}
      <div className="glass-card" style={{ padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1rem' }}>
          <Cpu size={22} style={{ color: 'var(--accent-purple)' }} />
          <div>
            <h2 style={{ fontSize: '1.2rem', fontWeight: 800, margin: 0 }}>Arquitectura Tecnológica & Metamodelo</h2>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
              Infraestructura híbrida de alta escala para analítica cienciométrica en tiempo real
            </p>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
          <div style={{ padding: '1rem', borderRadius: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.4rem', color: '#f59e0b' }}>
              <Database size={16} />
              <strong style={{ fontSize: '0.88rem' }}>ClickHouse Analytics</strong>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: '0 0 0.5rem 0' }}>
              Motor analítico columnar con agregaciones en milisegundos sobre 569 millones de obras y 337 millones de autores a nivel global.
            </p>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '0.45rem', lineHeight: 1.45 }}>
              <span style={{ color: '#f59e0b', fontWeight: 600 }}>Agradecimiento especial:</span> Agradecemos al <b>M. en C. Romel Calero Ramos</b> (Centro de Ciencias de la Complejidad, UNAM), quien instaló, configuró y mantiene activamente la infraestructura de este servicio de alto rendimiento.
            </div>
          </div>

          <div style={{ padding: '1rem', borderRadius: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.4rem', color: '#10b981' }}>
              <Network size={16} />
              <strong style={{ fontSize: '0.88rem' }}>Neo4j Knowledge Graph</strong>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
              Grafo relacional de coautorías, filiaciones y algoritmos de grafos (FastRP, Louvain, PageRank) sobre el ecosistema científico nacional.
            </p>
          </div>

          <div style={{ padding: '1rem', borderRadius: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.4rem', color: 'var(--accent-cyan)' }}>
              <Layers size={16} />
              <strong style={{ fontSize: '0.88rem' }}>Deepscatter WebGL GPU</strong>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
              Renderizado acelerado por GPU de 10 capas semánticas con capacidad de manejar millones de partículas a 60 FPS en el navegador.
            </p>
          </div>
        </div>

        {/* Metamodelo Relacional Conceptual */}
        <div style={{ background: isLight ? 'rgba(0,0,0,0.02)' : 'rgba(0,0,0,0.25)', padding: '1.25rem', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
          <h4 style={{ fontSize: '0.92rem', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--accent-cyan)' }}>
            Esquema del Grafo Científico (Entidades Principales)
          </h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', fontSize: '0.8rem' }}>
            <span className="badge" style={{ background: 'rgba(0, 242, 254, 0.1)', color: 'var(--accent-cyan)' }}>Person (Investigadora / Investigador SNII)</span>
            <span style={{ color: 'var(--text-muted)' }}>➔ AUTHOR_OF ➔</span>
            <span className="badge" style={{ background: 'rgba(168, 85, 247, 0.1)', color: 'var(--accent-purple)' }}>Paper (Artículo OpenAlex)</span>
            <span style={{ color: 'var(--text-muted)' }}>➔ HAS_TOPIC ➔</span>
            <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: '#10b981' }}>Topic (Jerarquía 4 Niveles)</span>
            <span style={{ color: 'var(--text-muted)' }}>➔ CONTRIBUTES_TO ➔</span>
            <span className="badge" style={{ background: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b' }}>SDG (Objetivos ONU 1-17)</span>
          </div>
        </div>
      </div>

      {/* ── Modal Flotante de Pantalla Completa: Informe SNII 2026 ─────────── */}
      {showModalReport && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.85)',
            backdropFilter: 'blur(8px)',
            zIndex: 99999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1.5rem'
          }}
        >
          <div
            className="glass-card"
            style={{
              width: '95vw',
              maxWidth: '1280px',
              height: '90vh',
              display: 'flex',
              flexDirection: 'column',
              padding: 0,
              overflow: 'hidden',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.8)',
              border: '1px solid var(--accent-cyan)'
            }}
          >
            {/* Modal Header */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '0.85rem 1.25rem',
              borderBottom: '1px solid var(--border-subtle)',
              background: 'rgba(0,0,0,0.3)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <FileText size={18} style={{ color: 'var(--accent-cyan)' }} />
                <h3 style={{ fontSize: '1rem', fontWeight: 700, margin: 0 }}>
                  Informe Ejecutivo del Padrón SNII 2026
                </h3>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <a
                  href={downloadUrl}
                  download="reporte_auditoria_snii_2026.html"
                  className="btn btn-secondary btn-xs"
                >
                  <Download size={13} />
                  <span>Descargar HTML</span>
                </a>
                <button
                  onClick={() => setShowModalReport(false)}
                  className="btn btn-ghost btn-xs"
                  style={{ padding: '0.3rem', borderRadius: '50%' }}
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            {/* Modal Body: Iframe */}
            <div style={{ flex: 1, position: 'relative', width: '100%', height: '100%', background: '#fff' }}>
              <iframe
                src={reportUrl}
                title="Auditoría SNII 2026"
                style={{ width: '100%', height: '100%', border: 'none' }}
              />
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default AboutView;
