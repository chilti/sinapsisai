"""
skill_manager.py - Dynamic Scientific Skill Registry & Injection Engine
Discovers, parses, and dynamically injects Antigravity/Claude-style skills from sos-mcp-services.
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

# Primary skill repositories
SKILL_DIRECTORIES = [
    Path("/mnt/expansion/desplegados/sos-mcp-services/.agents/skills"),
    Path(r"C:\Users\jlja\Documents\Proyectos\sos-mcp-services\.agents\skills"),
    Path(__file__).parent.parent / ".agents" / "skills"
]

class Skill:
    def __init__(self, name: str, description: str, path: Path, content: str):
        self.name = name
        self.description = description
        self.path = path
        self.content = content

    def __repr__(self):
        return f"<Skill name='{self.name}' desc='{self.description[:50]}...'>"

class SkillManager:
    def __init__(self, custom_dirs: Optional[List[Path]] = None):
        self.directories = custom_dirs or SKILL_DIRECTORIES
        self.skills: Dict[str, Skill] = {}
        self._load_skills()

    def _load_skills(self):
        """Scans directories and parses SKILL.md frontmatter."""
        self.skills.clear()
        for s_dir in self.directories:
            if not s_dir.exists():
                continue
            for skill_folder in s_dir.iterdir():
                if not skill_folder.is_dir():
                    continue
                skill_md = skill_folder / "SKILL.md"
                if not skill_md.exists():
                    continue
                try:
                    text = skill_md.read_text(encoding="utf-8")
                    name = skill_folder.name
                    desc = ""
                    
                    # Parse YAML frontmatter
                    if text.startswith("---"):
                        parts = text.split("---", 2)
                        if len(parts) >= 3:
                            fm = parts[1]
                            body = parts[2].strip()
                            for line in fm.splitlines():
                                if line.startswith("name:"):
                                    name = line.replace("name:", "").strip().strip('"\'')
                                elif line.startswith("description:"):
                                    desc = line.replace("description:", "").strip().strip('"\'')
                            text_body = body
                        else:
                            text_body = text
                    else:
                        text_body = text
                        
                    self.skills[name] = Skill(
                        name=name,
                        description=desc or name,
                        path=skill_md,
                        content=text_body
                    )
                except Exception as e:
                    print(f"Notice: Error loading skill from {skill_md}: {e}")

    def list_skills(self) -> List[Dict[str, str]]:
        """Returns catalogue of all loaded skills."""
        return [
            {"name": s.name, "description": s.description, "path": str(s.path)}
            for s in self.skills.values()
        ]

    def match_skills(self, query: str, top_k: int = 2) -> List[Skill]:
        """
        Matches relevant skills based on query terms and skill descriptions.
        """
        if not query or not self.skills:
            return []
            
        q_lower = query.lower()
        scored_skills = []
        
        for name, skill in self.skills.items():
            score = 0
            # Check name tokens
            for token in name.lower().replace('-', ' ').split():
                if token in q_lower:
                    score += 3
            # Check description tokens
            for token in skill.description.lower().split():
                if len(token) > 4 and token in q_lower:
                    score += 1
            # Keyword associations
            if "som" in q_lower and "som" in name: score += 5
            if ("red" in q_lower or "grafo" in q_lower or "louvain" in q_lower) and "network" in name: score += 5
            if ("ley" in q_lower or "lotka" in q_lower or "bradford" in q_lower) and "classical" in name: score += 5
            if ("revista" in q_lower or "editorial" in q_lower or "doaj" in q_lower) and "journal" in name: score += 5
            if ("frente" in q_lower or "topic" in q_lower or "linaje" in q_lower) and "fronts" in name: score += 5
            if ("openalex" in q_lower or "clickhouse" in q_lower) and "openalex" in name: score += 5
            if ("geopolit" in q_lower or "coautoria" in q_lower or "ods" in q_lower) and "geopolitical" in name: score += 5
            
            if score > 0:
                scored_skills.append((score, skill))
                
        scored_skills.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored_skills[:top_k]]

    def get_skill_instructions(self, skill_names_or_query: Any) -> str:
        """
        Returns assembled markdown instructions for active skills.
        """
        matched = []
        if isinstance(skill_names_or_query, str):
            matched = self.match_skills(skill_names_or_query)
        elif isinstance(skill_names_or_query, list):
            for sn in skill_names_or_query:
                if sn in self.skills:
                    matched.append(self.skills[sn])
                    
        if not matched:
            return ""
            
        instructions = ["\n## 🧠 METODOLOGÍAS Y SKILLS CIENTÍFICOS ACTIVADOS:"]
        for s in matched:
            instructions.append(f"\n### [Skill Activo: {s.name}]\n{s.description}\n\n{s.content[:3000]}\n")
            
        return "\n".join(instructions)

# Global default instance
skill_manager = SkillManager()
