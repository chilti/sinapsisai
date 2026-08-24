"""
topological_agent.py - Agente Especialista en Modelado Topológico SOM, Redes y UMAP (knoMap)
"""
import sys
import os
import math
import json
from typing import Dict, Any, List, Optional
import numpy as np

from agent.swarm.base_agent import BaseSpecialistAgent
from agent.episodic_memory import episodic_memory

try:
    from smolagents import tool
except ImportError:
    def tool(fn): return fn


# 1. SOM Mesh Dimension Calculator via SVD
@tool
def calculate_som_optimal_grid(n_samples: int, ratio_principal_components: float = 1.5) -> str:
    """
    Calcula el tamaño óptimo de filas y columnas para una malla hexagonal SOM según la regla espectral SVD:
    Total nodos = 5 * sqrt(N), proporción = lambda_1 / lambda_2.
    Args:
        n_samples: Número de muestras o entidades a mapear.
        ratio_principal_components: Razón entre el primer y segundo valor propio de PCA/SVD (default: 1.5).
    """
    total_nodes = max(9, int(5.0 * math.sqrt(n_samples)))
    ratio = max(1.0, float(ratio_principal_components))
    cols = max(3, int(math.sqrt(total_nodes * ratio)))
    rows = max(3, int(total_nodes / cols))
    res = {
        "n_samples": n_samples,
        "recommended_rows": rows,
        "recommended_cols": cols,
        "total_nodes": rows * cols,
        "topology": "hexagonal"
    }
    return json.dumps(res, ensure_ascii=False)


# 2. Louvain Modularity and Communities Calculator
@tool
def compute_network_modularity_louvain(adjacency_matrix_json: str) -> str:
    """
    Calcula la partición de comunidades y la modularidad Q de Newman-Girvan sobre una red bibliométrica.
    Args:
        adjacency_matrix_json: JSON con 'nodes' (id, label) y 'links' (source, target, weight).
    """
    import networkx as nx
    try:
        data = json.loads(adjacency_matrix_json)
        G = nx.Graph()
        for n in data.get("nodes", []):
            G.add_node(n["id"], label=n.get("label", n["id"]))
        for l in data.get("links", []):
            G.add_edge(l["source"], l["target"], weight=float(l.get("weight", l.get("strength", 1.0))))
        
        communities = list(nx.community.louvain_communities(G, seed=42))
        modularity = nx.community.modularity(G, communities)
        
        result = {
            "num_nodes": G.number_of_nodes(),
            "num_edges": G.number_of_edges(),
            "num_communities": len(communities),
            "modularity_q": round(float(modularity), 4),
            "communities": [{f"cluster_{i+1}": list(c)} for i, c in enumerate(communities)]
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return f"Error en cálculo Louvain: {str(e)}"


class TopologicalAgent(BaseSpecialistAgent):
    """Agente especialista en redes neuronales auto-organizadas (SOM), reducción UMAP y grafos complejos."""
    def __init__(self, session_id: Optional[str] = None, **kwargs):
        self.session_id = session_id
        tools = [calculate_som_optimal_grid, compute_network_modularity_louvain]
        role = ("Experto en topología no lineal, redes neuronales SOM de Kohonen (mallas hexagonales, U-Matrix, "
                "errores QE y TE), proyección de variedades semánticas con UMAP (dimensión intrínseca MLE) "
                "y detección de comunidades complejas con modularidad Louvain. "
                "Ejecuta Parallel Explore-Exploit (PEE) para encontrar la mejor representación de datos.")
        super().__init__(name="TopologicalAgent", role_description=role, tools=tools, **kwargs)
