import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict


class ChatStorage:
    def __init__(self, db_path: str = "./chat_history.db", max_messages_per_session: int = 20, session_ttl_hours: int = 24) -> None:
        self.db_path = db_path
        self.max_messages_per_session = max_messages_per_session
        self.session_ttl_hours = session_ttl_hours
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with closing(self._get_conn()) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT DEFAULT (datetime('now')),
                    last_activity TEXT DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id, created_at);")

    def _ensure_session(self, conn: sqlite3.Connection, session_id: str) -> None:
        conn.execute(
            """
            INSERT INTO sessions (session_id, created_at, last_activity)
            VALUES (?, datetime('now'), datetime('now'))
            ON CONFLICT(session_id) DO UPDATE SET last_activity = excluded.last_activity
            """,
            (session_id,),
        )

    def _delete_old_messages(self, conn: sqlite3.Connection, session_id: str) -> None:
        conn.execute(
            """
            DELETE FROM messages
            WHERE session_id = ? AND id NOT IN (
                SELECT id FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?
            )
            """,
            (session_id, session_id, self.max_messages_per_session),
        )

    def save_user_message(self, session_id: str, text: str) -> None:
        with closing(self._get_conn()) as conn:
            self._ensure_session(conn, session_id)
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
                (session_id, text),
            )
            self._delete_old_messages(conn, session_id)

    def save_assistant_message(self, session_id: str, text: str) -> None:
        content = text
        if len(content) > 3000:
            content = f"{content[:3000]}\n\n[...обрезано...]"

        with closing(self._get_conn()) as conn:
            self._ensure_session(conn, session_id)
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)",
                (session_id, content),
            )
            self._delete_old_messages(conn, session_id)

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        with closing(self._get_conn()) as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
            return [{"role": row["role"], "content": row["content"]} for row in rows]

    def cleanup_expired(self) -> None:
        cutoff = datetime.utcnow() - timedelta(hours=self.session_ttl_hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        with closing(self._get_conn()) as conn:
            conn.execute(
                """
                DELETE FROM messages WHERE session_id IN (
                    SELECT session_id FROM sessions WHERE datetime(last_activity) < datetime(?)
                )
                """,
                (cutoff_str,),
            )
            conn.execute("DELETE FROM sessions WHERE datetime(last_activity) < datetime(?)", (cutoff_str,))

    def get_stats(self) -> Dict[str, float]:
        with closing(self._get_conn()) as conn:
            active_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            total_messages = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

        db_size_mb = 0.0
        db_file = Path(self.db_path)
        if db_file.exists():
            db_size_mb = round(db_file.stat().st_size / (1024 * 1024), 3)

        return {
            "active_sessions": active_sessions,
            "total_messages": total_messages,
            "db_size_mb": db_size_mb,
        }
