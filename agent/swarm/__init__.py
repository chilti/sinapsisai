"""
agent.swarm - Módulo del Enjambre Científico Autónomo Universal
"""
from agent.swarm.base_agent import BaseSpecialistAgent
from agent.swarm.data_scientist_agent import DataScientistAgent
from agent.swarm.topological_agent import TopologicalAgent
from agent.swarm.critic_agent import ScientometricCriticAgent
from agent.swarm.visualizer_agent import InteractiveVisualizerAgent
from agent.swarm.supervisor_agent import ScientificSwarm

__all__ = [
    "ScientificSwarm",
    "BaseSpecialistAgent",
    "DataScientistAgent",
    "TopologicalAgent",
    "ScientometricCriticAgent",
    "InteractiveVisualizerAgent"
]
