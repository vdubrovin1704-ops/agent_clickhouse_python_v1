"""
SQLite хранилище для истории чатов.
Скользящее окно — хранит только последние N сообщений на сессию.
Автоочистка просроченных сессий.
"""

import sqlite3
from datetime import datetime, timedelta, timezone


class ChatStorage:
    """SQLite хранилище истории чатов"""

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

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT DEFAULT (datetime('now')),
                    last_activity TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_msg_session
                    ON messages(session_id, created_at);
            """)

    def _ensure_session(self, session_id: str):
        """Создать сессию если не существует, обновить last_activity."""
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)",
                (session_id,),
            )
            conn.execute(
                "UPDATE sessions SET last_activity = datetime('now') WHERE session_id = ?",
                (session_id,),
            )

    def _trim_session(self, session_id: str):
        """Скользящее окно: удалить сообщения сверх лимита."""
        with self._get_conn() as conn:
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
        """Сохранить сообщение пользователя."""
        self._ensure_session(session_id)
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
                (session_id, text),
            )
        self._trim_session(session_id)

    def save_assistant_message(self, session_id: str, text: str):
        """
        Сохранить ответ ассистента.
        Сохраняется ТОЛЬКО текст — без base64 графиков.
        Длинные ответы обрезаются для экономии места в SQLite.
        """
        self._ensure_session(session_id)
        if len(text) > 3000:
            text = text[:3000] + "\n\n[...обрезано...]"
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)",
                (session_id, text),
            )
        self._trim_session(session_id)

    def get_history(self, session_id: str) -> list:
        """
        Получить историю сессии в формате:
        [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages "
                "WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [{"role": row[0], "content": row[1]} for row in rows]

    def cleanup_expired(self):
        """Удалить сессии (и их сообщения) старше TTL."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=self.session_ttl_hours)).isoformat()
        with self._get_conn() as conn:
            expired = conn.execute(
                "SELECT session_id FROM sessions WHERE last_activity < ?",
                (cutoff,),
            ).fetchall()
            for (sid,) in expired:
                conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))

    def get_stats(self) -> dict:
        """Статистика: активные сессии, всего сообщений, размер БД."""
        import os
        with self._get_conn() as conn:
            active = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            total_msg = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        db_size = os.path.getsize(self.db_path) / (1024 * 1024) if os.path.exists(self.db_path) else 0
        return {
            "active_sessions": active,
            "total_messages": total_msg,
            "db_size_mb": round(db_size, 3),
        }
