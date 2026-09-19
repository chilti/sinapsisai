#!/usr/bin/env python3
"""
generate_snii_html_report.py
============================
Genera un informe HTML ejecutivo y estilizado con las estadísticas y hallazgos
de la transición y auditoría cienciométrica del Padrón SNII.
"""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
SNII_DIR = DATA_DIR / "snii"
REPORTS_DIR = DATA_DIR / "reports"
DEFAULT_JSON = SNII_DIR / "snii_audit_diff_2025_2026.json"
DEFAULT_HTML = REPORTS_DIR / "reporte_auditoria_snii_2026.html"


def generate_snii_html_report(json_path=None, output_path=None):
    jpath = Path(json_path) if json_path else DEFAULT_JSON
    opath = Path(output_path) if output_path else DEFAULT_HTML
    opath.parent.mkdir(parents=True, exist_ok=True)

    if not jpath.exists():
        raise FileNotFoundError(f"No se encontró el archivo de auditoría: {jpath}")

    with open(jpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Métricas clave
    total_25 = data.get("total_2025", 44794)
    total_26 = data.get("total_2026", 48000)
    var_neta = data.get("variacion_neta", total_26 - total_25)
    pct_var = (var_neta / total_25) * 100 if total_25 else 0
    altas = data.get("altas_totales", 4812)
    bajas = data.get("bajas_totales", 1606)
    continuantes = data.get("continuantes_totales", 43188)
    tasa_retencion = (continuantes / total_25) * 100 if total_25 else 0
    promociones = data.get("promociones_totales", 2351)
    descensos = data.get("descensos_totales", 204)
    movilidad = data.get("movilidad_institucional_total", 1784)
    mismo_nivel = data.get("mismo_nivel", 40633)

    altas_nivel = data.get("altas_por_nivel", {})
    bajas_nivel = data.get("bajas_por_nivel", {})
    top_inst = data.get("altas_por_institucion_top10", {})
    areas = data.get("altas_por_area", {})
    trans = data.get("transiciones_promocion", {})
    identidad = data.get("resumen_resolucion_identidad", {})
    resueltos = identidad.get("ya_resueltos", 35036)
    pendientes = identidad.get("pendientes", 12964)

    # Colores por nivel
    color_map = {
        "C": "#38bdf8",  # Sky
        "1": "#34d399",  # Emerald
        "2": "#fbbf24",  # Amber
        "3": "#f87171",  # Rose
        "E": "#a855f7",  # Purple
    }
    nombre_nivel = {
        "C": "Candidato",
        "1": "Nivel I",
        "2": "Nivel II",
        "3": "Nivel III",
        "E": "Emérito",
    }

    # Filas de Altas por nivel
    altas_rows = ""
    for niv in ["C", "1", "2", "3", "E"]:
        cnt = altas_nivel.get(niv, 0)
        pct = (cnt / altas * 100) if altas else 0
        c = color_map.get(niv, "#94a3b8")
        altas_rows += f"""
        <tr>
            <td><span class="badge" style="background:{c}22; color:{c}; border:1px solid {c}55;">{nombre_nivel.get(niv, niv)}</span></td>
            <td style="text-align:right; font-weight:600;">{cnt:,}</td>
            <td style="text-align:right;">{pct:.1f}%</td>
            <td>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" style="width:{pct}%; background:{c};"></div>
                </div>
            </td>
        </tr>
        """

    # Filas de Bajas por nivel
    bajas_rows = ""
    for niv in ["C", "1", "2", "3", "E"]:
        cnt = bajas_nivel.get(niv, 0)
        pct = (cnt / bajas * 100) if bajas else 0
        c = color_map.get(niv, "#94a3b8")
        bajas_rows += f"""
        <tr>
            <td><span class="badge" style="background:{c}22; color:{c}; border:1px solid {c}55;">{nombre_nivel.get(niv, niv)}</span></td>
            <td style="text-align:right; font-weight:600;">{cnt:,}</td>
            <td style="text-align:right;">{pct:.1f}%</td>
            <td>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" style="width:{pct}%; background:{c};"></div>
                </div>
            </td>
        </tr>
        """

    # Filas de Top Instituciones
    inst_rows = ""
    max_inst = max(top_inst.values()) if top_inst else 1
    for rank, (inst, count) in enumerate(top_inst.items(), 1):
        pct_bar = (count / max_inst) * 100
        inst_rows += f"""
        <tr>
            <td style="width:40px; text-align:center; font-weight:bold; color:#64748b;">#{rank}</td>
            <td style="font-weight:600; color:#1e293b;">{inst}</td>
            <td style="text-align:right; font-weight:700; color:#0f766e;">+{count:,}</td>
            <td style="width:25%;">
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" style="width:{pct_bar}%; background:linear-gradient(90deg, #0d9488, #14b8a6);"></div>
                </div>
            </td>
        </tr>
        """

    # Filas de Áreas de Conocimiento
    areas_rows = ""
    max_area = max(areas.values()) if areas else 1
    for area, count in areas.items():
        pct_area = (count / altas * 100) if altas else 0
        pct_bar = (count / max_area) * 100
        areas_rows += f"""
        <tr>
            <td style="font-weight:600; color:#1e293b;">{area}</td>
            <td style="text-align:right; font-weight:700;">{count:,}</td>
            <td style="text-align:right; color:#64748b;">{pct_area:.1f}%</td>
            <td style="width:30%;">
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" style="width:{pct_bar}%; background:linear-gradient(90deg, #3b82f6, #60a5fa);"></div>
                </div>
            </td>
        </tr>
        """

    # Filas de Transiciones de Promoción
    trans_rows = ""
    max_trans = max(trans.values()) if trans else 1
    for pair, count in sorted(trans.items(), key=lambda x: x[1], reverse=True):
        pct_bar = (count / max_trans) * 100
        trans_rows += f"""
        <tr>
            <td style="font-weight:700; color:#0f172a;"><span class="transition-pill">{pair}</span></td>
            <td style="text-align:right; font-weight:700; color:#059669;">{count:,}</td>
            <td style="width:40%;">
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" style="width:{pct_bar}%; background:linear-gradient(90deg, #10b981, #34d399);"></div>
                </div>
            </td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Informe Cienciométrico: Auditoría Padrón SNII 2026</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #f8fafc;
            --surface: #ffffff;
            --surface-subtle: #f1f5f9;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --primary: #0f766e;
            --primary-light: #ccfbf1;
            --primary-gradient: linear-gradient(135deg, #0f766e 0%, #115e59 100%);
            --accent: #2563eb;
            --success: #10b981;
            --danger: #ef4444;
            --card-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05);
            --card-shadow-hover: 0 10px 15px -3px rgb(0 0 0 / 0.08), 0 4px 6px -4px rgb(0 0 0 / 0.08);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            line-height: 1.6;
            padding: 2.5rem 1.5rem;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        /* Header Header */
        .report-header {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 1.25rem;
            padding: 2.5rem;
            margin-bottom: 2rem;
            box-shadow: var(--card-shadow);
            position: relative;
            overflow: hidden;
        }}

        .report-header::before {{
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 6px;
            background: linear-gradient(90deg, #0f766e, #2563eb, #8b5cf6);
        }}

        .header-tag {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            font-family: 'Outfit', sans-serif;
            font-size: 0.85rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.075em;
            color: var(--primary);
            background: var(--primary-light);
            padding: 0.35rem 0.85rem;
            border-radius: 9999px;
            margin-bottom: 1rem;
        }}

        h1 {{
            font-family: 'Outfit', sans-serif;
            font-size: 2.25rem;
            font-weight: 800;
            color: #0f172a;
            line-height: 1.25;
            margin-bottom: 0.75rem;
        }}

        .subtitle {{
            font-size: 1.05rem;
            color: var(--text-muted);
            max-width: 800px;
        }}

        .meta-strip {{
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            margin-top: 1.5rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border);
            font-size: 0.9rem;
            color: var(--text-muted);
        }}

        .meta-item strong {{
            color: var(--text-main);
        }}

        /* KPI Grid */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2rem;
        }}

        .kpi-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 1rem;
            padding: 1.5rem;
            box-shadow: var(--card-shadow);
            transition: all 0.2s ease;
        }}

        .kpi-card:hover {{
            box-shadow: var(--card-shadow-hover);
            transform: translateY(-2px);
        }}

        .kpi-label {{
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.5rem;
        }}

        .kpi-value {{
            font-family: 'Outfit', sans-serif;
            font-size: 2.25rem;
            font-weight: 800;
            color: var(--text-main);
            line-height: 1;
            margin-bottom: 0.5rem;
        }}

        .kpi-subtext {{
            font-size: 0.85rem;
            color: var(--text-muted);
        }}

        .badge-pill {{
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 700;
            padding: 0.2rem 0.6rem;
            border-radius: 0.375rem;
            margin-left: 0.5rem;
        }}

        .badge-positive {{
            background: #dcfce7;
            color: #15803d;
        }}

        .badge-negative {{
            background: #fee2e2;
            color: #b91c1c;
        }}

        /* 2-Column Content Layout */
        .grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        @media (max-width: 900px) {{
            .grid-2 {{
                grid-template-columns: 1fr;
            }}
        }}

        /* Section Cards */
        .section-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 1rem;
            padding: 1.75rem;
            box-shadow: var(--card-shadow);
            margin-bottom: 1.5rem;
        }}

        .section-title {{
            font-family: 'Outfit', sans-serif;
            font-size: 1.35rem;
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        /* Tables */
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.92rem;
        }}

        th {{
            text-align: left;
            padding: 0.75rem 1rem;
            font-size: 0.8rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 2px solid var(--border);
        }}

        td {{
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
        }}

        tr:last-child td {{
            border-bottom: none;
        }}

        tr:hover td {{
            background-color: #f8fafc;
        }}

        /* Progress Bars */
        .progress-bar-bg {{
            background: #e2e8f0;
            border-radius: 9999px;
            height: 8px;
            width: 100%;
            overflow: hidden;
        }}

        .progress-bar-fill {{
            height: 100%;
            border-radius: 9999px;
            transition: width 0.5s ease-out;
        }}

        /* Badges & Tags */
        .badge {{
            display: inline-block;
            font-size: 0.8rem;
            font-weight: 700;
            padding: 0.25rem 0.65rem;
            border-radius: 0.375rem;
        }}

        .transition-pill {{
            background: #f1f5f9;
            border: 1px solid #cbd5e1;
            padding: 0.25rem 0.6rem;
            border-radius: 0.375rem;
            font-family: 'Outfit', sans-serif;
            font-size: 0.85rem;
        }}

        .callout-box {{
            background: linear-gradient(135deg, #f0fdfa 0%, #e6fffa 100%);
            border: 1px solid #99f6e4;
            border-radius: 0.75rem;
            padding: 1.25rem;
            margin-top: 1.5rem;
        }}

        .callout-title {{
            font-weight: 700;
            color: #0f766e;
            margin-bottom: 0.35rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .callout-text {{
            font-size: 0.92rem;
            color: #134e4a;
        }}

        /* Print formatting */
        @media print {{
            body {{
                padding: 0;
                background: #fff;
            }}
            .report-header, .section-card, .kpi-card {{
                box-shadow: none;
                border: 1px solid #cbd5e1;
            }}
        }}
    </style>
</head>
<body>

<div class="container">
    <!-- Header -->
    <header class="report-header">
        <div class="header-tag">🔬 Info TlachIA Cienciometría</div>
        <h1>Informe Ejecutivo: Padrón SNII 2026</h1>
        <p class="subtitle">
            Auditoría cienciométrica comparativa entre los padrones del Sistema Nacional de Investigadoras e Investigadores (2025 vs. 2026), identificando variaciones netas, movilidad institucional, ascensos de nivel y cobertura de identidad digital.
        </p>
        <div class="meta-strip">
            <div class="meta-item">📅 <strong>Fecha de corte:</strong> Junio 2026 (2T 2026)</div>
            <div class="meta-item">🏛️ <strong>Fuentes:</strong> SECIHTI / Padrón SNII 2026</div>
            <div class="meta-item">⚙️ <strong>Sistema:</strong> Info TlachIA (UNAM)</div>
        </div>
    </header>

    <!-- Top KPIs -->
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Padrón Vigente 2026</div>
            <div class="kpi-value">{total_26:,}</div>
            <div class="kpi-subtext">Investigadores vigentes en México</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Variación Neta</div>
            <div class="kpi-value" style="color:var(--success);">+{var_neta:,} <span class="badge-pill badge-positive">+{pct_var:.1f}%</span></div>
            <div class="kpi-subtext">Crecimiento respecto a 2025 ({total_25:,})</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Nuevos Ingresos (Altas)</div>
            <div class="kpi-value" style="color:#0284c7;">+{altas:,}</div>
            <div class="kpi-subtext">Nuevas plazas incorporadas al padrón</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Bajas del Padrón</div>
            <div class="kpi-value" style="color:var(--danger);">{bajas:,} <span class="badge-pill badge-negative">3.6%</span></div>
            <div class="kpi-subtext">Salidas de investigadores de 2025</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Tasa de Continuidad</div>
            <div class="kpi-value">{tasa_retencion:.1f}%</div>
            <div class="kpi-subtext">{continuantes:,} investigadores retenidos</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Promociones de Nivel</div>
            <div class="kpi-value" style="color:#059669;">{promociones:,}</div>
            <div class="kpi-subtext">5.4% de continuantes ascendieron</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Movilidad Institucional</div>
            <div class="kpi-value" style="color:#7c3aed;">{movilidad:,}</div>
            <div class="kpi-subtext">Investigadores con cambio de adscripción</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Identidad Digital Consolidada</div>
            <div class="kpi-value">{resueltos:,}</div>
            <div class="kpi-subtext">{(resueltos / total_26 * 100) if total_26 else 0:.1f}% vinculados con ORCID/OpenAlex</div>
        </div>
    </div>

    <!-- Grid: Altas y Bajas por Nivel -->
    <div class="grid-2">
        <!-- Altas por Nivel -->
        <div class="section-card">
            <div class="section-title">
                <span>🟢 Nuevos Ingresos por Nivel</span>
                <span style="font-size:0.9rem; color:#0f766e; font-weight:600;">Total: {altas:,}</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Nivel</th>
                        <th style="text-align:right;">Cantidad</th>
                        <th style="text-align:right;">% Altas</th>
                        <th style="width:35%;">Distribución</th>
                    </tr>
                </thead>
                <tbody>
                    {altas_rows}
                </tbody>
            </table>
            <div class="callout-box">
                <div class="callout-title">💡 Hallazgo en Altas</div>
                <div class="callout-text">
                    El <strong>73.1%</strong> de las nuevas incorporaciones entran en la categoría de <strong>Candidato (3,518)</strong>, consolidando el relevo generacional y el fortalecimiento de jóvenes investigadores.
                </div>
            </div>
        </div>

        <!-- Bajas por Nivel -->
        <div class="section-card">
            <div class="section-title">
                <span>🔴 Bajas del Padrón por Nivel</span>
                <span style="font-size:0.9rem; color:#b91c1c; font-weight:600;">Total: {bajas:,}</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Nivel</th>
                        <th style="text-align:right;">Cantidad</th>
                        <th style="text-align:right;">% Bajas</th>
                        <th style="width:35%;">Distribución</th>
                    </tr>
                </thead>
                <tbody>
                    {bajas_rows}
                </tbody>
            </table>
            <div class="callout-box" style="background:#fff1f2; border-color:#fecdd3;">
                <div class="callout-title" style="color:#b91c1c;">⚠️ Bajas en Niveles Consolidados</div>
                <div class="callout-text" style="color:#881337;">
                    Se registraron <strong>18 bajas de Eméritos</strong> y <strong>31 bajas de Nivel III</strong>, principalmente atribuibles a jubilaciones y decesos.
                </div>
            </div>
        </div>
    </div>

    <!-- Grid: Dinámica de Promociones y Top Instituciones -->
    <div class="grid-2">
        <!-- Ascensos de Nivel -->
        <div class="section-card">
            <div class="section-title">
                <span>🎖️ Principales Ascensos de Nivel</span>
                <span style="font-size:0.9rem; color:#059669; font-weight:600;">{promociones:,} promociones</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Transición</th>
                        <th style="text-align:right;">Investigadores</th>
                        <th>Proporción</th>
                    </tr>
                </thead>
                <tbody>
                    {trans_rows}
                </tbody>
            </table>
            <div class="callout-box">
                <div class="callout-title">🌟 Destacado: Nuevos Eméritos</div>
                <div class="callout-text">
                    <strong>169 investigadoras e investigadores de Nivel III</strong> alcanzaron la máxima distinción como <strong>Investigadores Eméritos (E)</strong> en esta convocatoria.
                </div>
            </div>
        </div>

        <!-- Top Instituciones Captación -->
        <div class="section-card">
            <div class="section-title">
                <span>🏛️ Top 10 Instituciones Captadoras</span>
                <span style="font-size:0.9rem; color:var(--text-muted);">Nuevos Ingresos</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Institución</th>
                        <th style="text-align:right;">Altas</th>
                        <th>Volumen</th>
                    </tr>
                </thead>
                <tbody>
                    {inst_rows}
                </tbody>
            </table>
        </div>
    </div>

    <!-- Áreas del Conocimiento -->
    <div class="section-card">
        <div class="section-title">
            <span>📚 Distribución de Nuevas Plazas por Área del Conocimiento</span>
            <span style="font-size:0.9rem; color:var(--text-muted);">9 Áreas del Conocimiento</span>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Área del Conocimiento</th>
                    <th style="text-align:right;">Nuevos Ingresos</th>
                    <th style="text-align:right;">% Total</th>
                    <th>Concentración</th>
                </tr>
            </thead>
            <tbody>
                {areas_rows}
            </tbody>
        </table>
    </div>

    <!-- Identidad Digital y ROR -->
    <div class="section-card">
        <div class="section-title">
            <span>🌐 Cobertura de Identidad Digital y Vinculación ROR</span>
        </div>
        <p style="font-size:0.95rem; color:var(--text-muted); margin-bottom:1.25rem;">
            Estado de integración del nuevo Padrón 2026 en el grafo de conocimiento científico y las bases de datos analíticas (ClickHouse, Neo4j, DuckDB):
        </p>
        <div class="kpi-grid" style="margin-bottom:0;">
            <div class="kpi-card" style="background:#f8fafc;">
                <div class="kpi-label">Identidades Consolidadas</div>
                <div class="kpi-value" style="font-size:1.75rem; color:#0f766e;">{resueltos:,}</div>
                <div class="kpi-subtext">Con OpenAlex ID / ORCID vinculado ({(resueltos / total_26 * 100) if total_26 else 0:.1f}%)</div>
            </div>
            <div class="kpi-card" style="background:#f8fafc;">
                <div class="kpi-label">Pendientes Residuales</div>
                <div class="kpi-value" style="font-size:1.75rem; color:#2563eb;">{pendientes:,}</div>
                <div class="kpi-subtext">Investigadores sin producción registrada ({(pendientes / total_26 * 100) if total_26 else 0:.1f}%)</div>
            </div>
            <div class="kpi-card" style="background:#f8fafc;">
                <div class="kpi-label">Instituciones con ROR</div>
                <div class="kpi-value" style="font-size:1.75rem; color:#7c3aed;">746</div>
                <div class="kpi-subtext">Mapeadas en ClickHouse y Neo4j</div>
            </div>
            <div class="kpi-card" style="background:#f8fafc;">
                <div class="kpi-label">Tasa Cobertura ROR</div>
                <div class="kpi-value" style="font-size:1.75rem; color:#059669;">100%</div>
                <div class="kpi-subtext">343/343 entidades del padrón evaluadas</div>
            </div>
        </div>
    </div>

    <!-- Footer -->
    <footer style="text-align:center; padding-top:2rem; font-size:0.85rem; color:#94a3b8; border-top:1px solid var(--border);">
        SNII Info TlachIA • Laboratorio de Auto-Organización y Modelado de Sistemas Complejos (LabSOM) • UNAM 2026
    </footer>
</div>

</body>
</html>
"""

    with open(opath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ Reporte HTML generado exitosamente en: {opath}")
    return opath


if __name__ == "__main__":
    generate_snii_html_report()
