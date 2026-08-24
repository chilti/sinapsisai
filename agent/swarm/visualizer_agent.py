"""
visualizer_agent.py - Agente Especialista en Composición y Auto-Síntesis de Artefactos Interactivos
"""
import sys
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from agent.swarm.base_agent import BaseSpecialistAgent
from agent.artifact_manager import artifact_manager
from agent.episodic_memory import episodic_memory

try:
    from smolagents import tool
except ImportError:
    def tool(fn): return fn


# 1. Emit Existing Catalog Artifact (Top-level tool)
@tool
def emit_standard_artifact(artifact_id: str, title: str, data_json_str: str) -> str:
    """
    Renderiza un artefacto interactivo del catálogo existente (som-hexagonal-mesh, bibliometric-force-network, etc.).
    Args:
        artifact_id: ID del artefacto ('som-hexagonal-mesh', 'bibliometric-force-network', 'umap-density-contours', 'research-fronts-evolution', 'geopolitical-science-map', 'bibliometric-laws-curves', 'journal-benchmark-matrix', 'institutional-benchmarking-profile', 'graphrag-entity-subgraph', 'scientific-executive-report').
        title: Título descriptivo de la visualización.
        data_json_str: Estructura de datos en formato JSON requerida por el artefacto.
    """
    try:
        data = json.loads(data_json_str) if isinstance(data_json_str, str) else data_json_str
        html = artifact_manager.render_artifact(artifact_id, data, title=title)
        if html:
            return f"✅ Artefacto '{title}' ({artifact_id}) generado exitosamente."
        return f"❌ Error: Artefacto '{artifact_id}' no encontrado en el catálogo."
    except Exception as e:
        return f"❌ Error renderizando artefacto: {str(e)}"


# 2. SINTETIZAR NUEVO ARTEFACTO AL VUELO (Self-Synthesized Artifacts)
@tool
def synthesize_new_artifact(
    artifact_id: str,
    title: str,
    description: str,
    input_schema_json: str,
    template_html_code: str,
    data_json_str: str
) -> str:
    """
    Crea, persiste y renderiza un NUEVO artefacto interactivo al vuelo (HTML/D3/Plotly/Canvas) cuando ninguna plantilla existente cubre la necesidad.
    El nuevo artefacto queda guardado en .agents/artifacts/ para siempre y disponible para todos los sistemas.
    Args:
        artifact_id: Identificador kebab-case único (ej. 'citation-chord-diagram', '3d-spatial-scatter').
        title: Nombre legible del artefacto.
        description: Descripción metodológica y visual del nuevo gráfico.
        input_schema_json: Schema JSON de entrada esperado.
        template_html_code: Código HTML/JS autónomo completo que consuma 'window.__ARTIFACT_DATA__ = {{ DATA_JSON }}'.
        data_json_str: Datos JSON a inyectar y renderizar de inmediato.
    """
    try:
        artifacts_dir = Path("/mnt/expansion/desplegados/sos-mcp-services/.agents/artifacts")
        target_dir = artifacts_dir / artifact_id
        target_dir.mkdir(parents=True, exist_ok=True)

        md_content = f"""---
name: {artifact_id}
title: {title}
version: 1.0.0
content_type: text/html
description: {description}
input_schema:
{input_schema_json}
---

# Artefacto Auto-Sintetizado por el Enjambre Científico
Generado autónomamente por VisualizerAgent para cubrir nuevas necesidades de visualización.
"""
        (target_dir / "ARTIFACT.md").write_text(md_content, encoding="utf-8")
        (target_dir / "template.html").write_text(template_html_code, encoding="utf-8")
        artifact_manager.artifacts = artifact_manager._load_all_artifacts()

        data = json.loads(data_json_str) if isinstance(data_json_str, str) else data_json_str
        html = artifact_manager.render_artifact(artifact_id, data, title=title)
        
        if html:
            return f"🎉 ¡Nuevo artefacto '{title}' ({artifact_id}) auto-sintetizado, persistido y renderizado exitosamente!"
        return f"❌ Error al renderizar la nueva plantilla de '{artifact_id}'."
    except Exception as e:
        return f"❌ Error en auto-síntesis de artefacto: {str(e)}"


class InteractiveVisualizerAgent(BaseSpecialistAgent):
    """Agente especialista en renderizado y auto-síntesis de artefactos visuales interactivos."""
    def __init__(self, session_id: Optional[str] = None, emitted_collector: Optional[List[Dict[str, Any]]] = None, **kwargs):
        self.emitted_collector = emitted_collector if emitted_collector is not None else []
        self.session_id = session_id
        tools = [emit_standard_artifact, synthesize_new_artifact]
        role = ("Experto en visualización científica e interfaces interactivas D3.js, SVG, Canvas y Plotly. "
                "Emite artefactos del catálogo universal y posee la capacidad de AUTO-SINTETIZAR nuevos artefactos "
                "interactivos en tiempo de ejecución (`synthesize_new_artifact`) si se requiere un gráfico no contemplado.")
        super().__init__(name="InteractiveVisualizerAgent", role_description=role, tools=tools, **kwargs)
