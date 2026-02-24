"""
SQLite хранилище для истории чатов
"""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path


class ChatStorage:
    """Хранилище истории чатов в SQLite с скользящим окном"""

    def __init__(
        self,
        db_path: str = "./chat_history.db",
        max_messages_per_session: int = 20,
        session_ttl_hours: int = 24
    ):
        self.db_path = db_path
        self.max_messages = max_messages_per_session
        self.session_ttl_hours = session_ttl_hours
        self._init_db()

    def _init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Включить WAL mode для лучшей производительности
        cursor.execute("PRAGMA journal_mode=WAL;")

        # Таблица сессий
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT DEFAULT (datetime('now')),
                last_activity TEXT DEFAULT (datetime('now'))
            )
        """)

        # Таблица сообщений
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        """)

        # Индекс для быстрого поиска
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_msg_session
            ON messages(session_id, created_at)
        """)

        conn.commit()
        conn.close()

    def save_user_message(self, session_id: str, text: str):
        """Сохранить сообщение пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Создать сессию если не существует
        cursor.execute("""
            INSERT OR IGNORE INTO sessions (session_id) VALUES (?)
        """, (session_id,))

        # Обновить время последней активности
        cursor.execute("""
            UPDATE sessions SET last_activity = datetime('now') WHERE session_id = ?
        """, (session_id,))

        # Сохранить сообщение
        cursor.execute("""
            INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)
        """, (session_id, "user", text))

        conn.commit()
        conn.close()

        # Применить скользящее окно
        self._apply_sliding_window(session_id)

    def save_assistant_message(self, session_id: str, text: str):
        """Сохранить ответ ассистента (ТОЛЬКО текст, без base64 графиков)"""
        # Обрезать если слишком длинный
        if len(text) > 3000:
            text = text[:3000] + "\n\n[...обрезано...]"

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Обновить время последней активности
        cursor.execute("""
            UPDATE sessions SET last_activity = datetime('now') WHERE session_id = ?
        """, (session_id,))

        # Сохранить сообщение
        cursor.execute("""
            INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)
        """, (session_id, "assistant", text))

        conn.commit()
        conn.close()

        # Применить скользящее окно
        self._apply_sliding_window(session_id)

    def get_history(self, session_id: str) -> list:
        """
        Получить историю диалога для сессии.
        Возвращает список словарей с ключами 'role' и 'content'.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT role, content FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
        """, (session_id,))

        history = []
        for row in cursor.fetchall():
            history.append({"role": row[0], "content": row[1]})

        conn.close()
        return history

    def _apply_sliding_window(self, session_id: str):
        """Удалить лишние сообщения, оставив только последние N"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM messages
            WHERE session_id = ? AND id NOT IN (
                SELECT id FROM messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            )
        """, (session_id, session_id, self.max_messages))

        conn.commit()
        conn.close()

    def cleanup_expired(self):
        """Удалить сессии старше TTL"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_time = (datetime.now() - timedelta(hours=self.session_ttl_hours)).isoformat()

        # Удалить старые сообщения
        cursor.execute("""
            DELETE FROM messages WHERE session_id IN (
                SELECT session_id FROM sessions WHERE last_activity < ?
            )
        """, (cutoff_time,))

        # Удалить старые сессии
        cursor.execute("""
            DELETE FROM sessions WHERE last_activity < ?
        """, (cutoff_time,))

        deleted_sessions = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted_sessions > 0:
            print(f"🗑️  Удалено {deleted_sessions} устаревших сессий")

    def get_stats(self) -> dict:
        """Получить статистику по чатам"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Количество активных сессий
        cursor.execute("SELECT COUNT(*) FROM sessions")
        active_sessions = cursor.fetchone()[0]

        # Общее количество сообщений
        cursor.execute("SELECT COUNT(*) FROM messages")
        total_messages = cursor.fetchone()[0]

        # Размер базы данных
        db_size_mb = Path(self.db_path).stat().st_size / (1024 * 1024)

        conn.close()

        return {
            "active_sessions": active_sessions,
            "total_messages": total_messages,
            "db_size_mb": round(db_size_mb, 2),
        }
