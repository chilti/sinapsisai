import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any

class SessionMemoryManager:
    """
    Maneja la persistencia de las sesiones de chat de los usuarios
    usando SQLite local (puede ser migrado a Postgres en el futuro).
    """
    def __init__(self, db_path="sessions.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                session_id TEXT,
                role TEXT,
                content TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def add_message(self, session_id: str, role: str, content: str):
        """Añade un mensaje (user o assistant) al historial."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat_history (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content)
        )
        conn.commit()
        conn.close()

    def get_history(self, session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """Recupera los últimos 'limit' mensajes de una sesión."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Recuperamos primero los más recientes, limitados
        cursor.execute(
            "SELECT role, content FROM chat_history WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit)
        )
        rows = cursor.fetchall()
        conn.close()
        
        # Invertimos para que el orden cronológico sea el correcto (el más antiguo primero dentro del límite)
        messages = [{"role": row[0], "content": row[1]} for row in reversed(rows)]
        return messages

    def clear_session(self, session_id: str):
         """Elimina el historial de una sesión."""
         conn = sqlite3.connect(self.db_path)
         cursor = conn.cursor()
         cursor.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
         conn.commit()
         conn.close()
