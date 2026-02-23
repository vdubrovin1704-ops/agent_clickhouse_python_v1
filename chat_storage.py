"""
SQLite хранилище для истории чатов.
Скользящее окно, автоочистка просроченных сессий.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path


class ChatStorage:
    """SQLite хранилище истории чатов."""

    def __init__(
        self,
        db_path: str = "./chat_history.db",
        max_messages_per_session: int = 20,
        session_ttl_hours: int = 24,
    ):
        self.db_path = db_path
        self.max_messages = max_messages_per_session
        self.session_ttl_hours = session_ttl_hours
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT DEFAULT (datetime('now')),
                    last_activity TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_msg_session
                ON messages(session_id, created_at)
            """)

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _ensure_session(self, conn, session_id: str):
        conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)",
            (session_id,),
        )
        conn.execute(
            "UPDATE sessions SET last_activity = datetime('now') WHERE session_id = ?",
            (session_id,),
        )

    def _trim_messages(self, conn, session_id: str):
        conn.execute(
            """
            DELETE FROM messages
            WHERE session_id = ? AND id NOT IN (
                SELECT id FROM messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            )
            """,
            (session_id, session_id, self.max_messages),
        )

    def save_user_message(self, session_id: str, text: str):
        with self._connect() as conn:
            self._ensure_session(conn, session_id)
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
                (session_id, text),
            )
            self._trim_messages(conn, session_id)

    def save_assistant_message(self, session_id: str, text: str):
        if len(text) > 3000:
            text = text[:3000] + "\n\n[...обрезано...]"
        with self._connect() as conn:
            self._ensure_session(conn, session_id)
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)",
                (session_id, text),
            )
            self._trim_messages(conn, session_id)

    def get_history(self, session_id: str) -> list:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows]

    def cleanup_expired(self):
        cutoff = (datetime.utcnow() - timedelta(hours=self.session_ttl_hours)).isoformat()
        with self._connect() as conn:
            expired = conn.execute(
                "SELECT session_id FROM sessions WHERE last_activity < ?",
                (cutoff,),
            ).fetchall()
            for (sid,) in expired:
                conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))

    def get_stats(self) -> dict:
        with self._connect() as conn:
            active = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        db_size = os.path.getsize(self.db_path) / (1024 * 1024) if os.path.exists(self.db_path) else 0
        return {
            "active_sessions": active,
            "total_messages": total,
            "db_size_mb": round(db_size, 2),
        }
