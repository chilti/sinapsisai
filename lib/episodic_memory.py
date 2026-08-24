"""
episodic_memory.py - Sistema de Memoria Episódica Persistente y Trazabilidad Chain-of-Evidence (CoE)
Inspirado en el estándar CoE (ScientistOne, 2026) para almacenar experiencias de investigación,
trazabilidad de evidencia y optimizaciones entre sesiones con soporte multi-sistema (namespaces).
"""
import os
import sqlite3
import json
import time
from typing import Dict, Any, List, Optional
from pathlib import Path

DEFAULT_DB_PATH = Path("/mnt/expansion/desplegados/sos-mcp-services/data/episodic_memory.db")

class EpisodicMemory:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Sesiones y proyectos de investigación
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_sessions (
                session_id TEXT PRIMARY KEY,
                system_namespace TEXT NOT NULL,
                research_question TEXT NOT NULL,
                plan_dag TEXT,
                iterations_count INTEGER DEFAULT 1,
                critic_verdict TEXT,
                artifacts_emitted TEXT,
                final_answer TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """)

            # 2. Registro de Trazabilidad Chain-of-Evidence (CoE)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS chain_of_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                claim_type TEXT NOT NULL, -- 'numerical', 'citation', 'methodological', 'conclusion'
                claim_text TEXT NOT NULL,
                evidence_source TEXT NOT NULL, -- 'clickhouse', 'neo4j', 'qdrant', 'som', 'parquet'
                evidence_payload TEXT,
                verified INTEGER DEFAULT 1,
                created_at REAL NOT NULL,
                FOREIGN KEY (session_id) REFERENCES research_sessions(session_id)
            );
            """)

            # 3. Almacén de Experiencias y Aprendizajes acumulativos (Lifelong Learning)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS learned_experiences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                system_namespace TEXT NOT NULL,
                domain_topic TEXT NOT NULL,
                experience_type TEXT NOT NULL, -- 'optimal_som_params', 'query_pattern', 'louvain_res', 'failure_avoidance'
                item_key TEXT NOT NULL,
                item_value TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                created_at REAL NOT NULL
            );
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_ns ON research_sessions(system_namespace);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_coe_session ON chain_of_evidence(session_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_exp_topic ON learned_experiences(domain_topic, experience_type);")
            conn.commit()

    def start_session(self, session_id: str, research_question: str, system_namespace: str = "general"):
        """Inicia y registra una nueva sesión de investigación científica."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO research_sessions 
            (session_id, system_namespace, research_question, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """, (session_id, system_namespace, research_question, now, now))
            conn.commit()

    def record_evidence(
        self, 
        session_id: str, 
        claim_type: str, 
        claim_text: str, 
        evidence_source: str, 
        evidence_payload: Any, 
        verified: bool = True
    ):
        """Registra un eslabón de evidencia determinista (CoE) para una afirmación."""
        payload_str = json.dumps(evidence_payload, ensure_ascii=False) if not isinstance(evidence_payload, str) else evidence_payload
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO chain_of_evidence 
            (session_id, claim_type, claim_text, evidence_source, evidence_payload, verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (session_id, claim_type, claim_text, evidence_source, payload_str, 1 if verified else 0, now))
            conn.commit()

    def record_experience(
        self, 
        domain_topic: str, 
        experience_type: str, 
        key: str, 
        value: Any, 
        system_namespace: str = "general",
        confidence: float = 1.0
    ):
        """Almacena una experiencia o aprendizaje óptimo para reutilizar en consultas futuras."""
        val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO learned_experiences 
            (system_namespace, domain_topic, experience_type, item_key, item_value, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (system_namespace, domain_topic.lower().strip(), experience_type, key, val_str, confidence, now))
            conn.commit()

    def query_experiences(self, domain_topic: str, experience_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera experiencias previas relevantes para un tema o disciplina."""
        topic_clean = domain_topic.lower().strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if experience_type:
                cursor.execute("""
                SELECT * FROM learned_experiences 
                WHERE domain_topic LIKE ? AND experience_type = ?
                ORDER BY confidence DESC, created_at DESC LIMIT 10
                """, (f"%{topic_clean}%", experience_type))
            else:
                cursor.execute("""
                SELECT * FROM learned_experiences 
                WHERE domain_topic LIKE ?
                ORDER BY confidence DESC, created_at DESC LIMIT 10
                """, (f"%{topic_clean}%",))
            
            rows = cursor.fetchall()
            results = []
            for r in rows:
                try:
                    parsed_val = json.loads(r["item_value"])
                except Exception:
                    parsed_val = r["item_value"]
                results.append({
                    "id": r["id"],
                    "system_namespace": r["system_namespace"],
                    "domain_topic": r["domain_topic"],
                    "experience_type": r["experience_type"],
                    "key": r["item_key"],
                    "value": parsed_val,
                    "confidence": r["confidence"]
                })
            return results

    def close_session(
        self, 
        session_id: str, 
        plan_dag: Optional[Dict[str, Any]] = None, 
        iterations_count: int = 1, 
        critic_verdict: Optional[Dict[str, Any]] = None, 
        artifacts_emitted: Optional[List[Dict[str, Any]]] = None, 
        final_answer: str = ""
    ):
        """Cierra y consolida la investigación con su veredicto crítico y artefactos finales."""
        now = time.time()
        plan_str = json.dumps(plan_dag, ensure_ascii=False) if plan_dag else None
        critic_str = json.dumps(critic_verdict, ensure_ascii=False) if critic_verdict else None
        artifacts_str = json.dumps([a.get("artifact_id") for a in artifacts_emitted], ensure_ascii=False) if artifacts_emitted else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE research_sessions 
            SET plan_dag = ?, iterations_count = ?, critic_verdict = ?, artifacts_emitted = ?, final_answer = ?, updated_at = ?
            WHERE session_id = ?
            """, (plan_str, iterations_count, critic_str, artifacts_str, final_answer, now, session_id))
            conn.commit()

    def get_session_provenance(self, session_id: str) -> List[Dict[str, Any]]:
        """Retorna todos los eslabones de evidencia registrados para una sesión."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM chain_of_evidence WHERE session_id = ? ORDER BY created_at ASC", (session_id,))
            rows = cursor.fetchall()
            return [
                {
                    "claim_type": r["claim_type"],
                    "claim_text": r["claim_text"],
                    "evidence_source": r["evidence_source"],
                    "payload": json.loads(r["evidence_payload"]) if r["evidence_payload"] else None,
                    "verified": bool(r["verified"])
                }
                for r in rows
            ]

# Singleton global de memoria episódica
episodic_memory = EpisodicMemory()
