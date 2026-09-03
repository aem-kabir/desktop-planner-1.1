"""
db.py
SQLite как локальный offline-кэш (источник истины для UI) + очередь outbox
для несинхронизированных изменений. Поддерживает простую автомиграцию схемы:
при появлении новых полей в модели Task в будущем, недостающие столбцы
добавляются автоматически через ALTER TABLE ... ADD COLUMN.
"""
import sqlite3
import threading
import json
from contextlib import contextmanager
from typing import List, Optional

from config import DB_PATH
from models import Task, now_iso

# Описание столбцов таблицы tasks: имя -> SQL-тип с дефолтом.
# Если в будущем в Task добавится новое поле — добавьте его сюда,
# и _migrate() создаст столбец в уже существующих базах автоматически.
TASKS_SCHEMA = {
    "id": "TEXT PRIMARY KEY",
    "title": "TEXT DEFAULT ''",
    "description": "TEXT DEFAULT ''",
    "start_date": "TEXT DEFAULT ''",
    "deadline_date": "TEXT DEFAULT ''",
    "deadline_time": "TEXT DEFAULT ''",
    "status": "TEXT DEFAULT 'Active'",
    "priority": "TEXT DEFAULT 'Medium'",
    "assignee": "TEXT DEFAULT ''",
    "updated_at": "TEXT DEFAULT ''",
    "dirty": "INTEGER DEFAULT 0",
    "deleted": "INTEGER DEFAULT 0",
}

OUTBOX_SCHEMA = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "task_id": "TEXT NOT NULL",
    "op": "TEXT NOT NULL",          # upsert | delete
    "payload": "TEXT",              # JSON-снимок задачи на момент постановки в очередь
    "created_at": "TEXT NOT NULL",
    "attempts": "INTEGER DEFAULT 0",
    "last_error": "TEXT DEFAULT ''",
}

NOTIF_SCHEMA = {
    "task_id": "TEXT NOT NULL",
    "offset_minutes": "INTEGER NOT NULL",
    "sent_at": "TEXT NOT NULL",
}


class Database:
    """Потокобезопасная обёртка над SQLite (свой connection на поток)."""

    def __init__(self, path=DB_PATH):
        self.path = str(path)
        self._local = threading.local()
        self._lock = threading.RLock()
        self._init_schema()

    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _cursor(self):
        with self._lock:
            conn = self._connect()
            cur = conn.cursor()
            try:
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()

    # ------------------------------------------------------------------
    def _init_schema(self):
        with self._cursor() as cur:
            cur.execute(
                f"""CREATE TABLE IF NOT EXISTS tasks (
                    {', '.join(f'{c} {t}' for c, t in TASKS_SCHEMA.items())}
                )"""
            )
            cur.execute(
                f"""CREATE TABLE IF NOT EXISTS outbox (
                    {', '.join(f'{c} {t}' for c, t in OUTBOX_SCHEMA.items())}
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS sent_notifications (
                    task_id TEXT NOT NULL,
                    offset_minutes INTEGER NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (task_id, offset_minutes)
                )"""
            )
            cur.execute(
                """CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )"""
            )
        self._migrate()

    def _migrate(self):
        """Добавляет недостающие столбцы в существующую БД (авто-миграция)."""
        with self._cursor() as cur:
            cur.execute("PRAGMA table_info(tasks)")
            existing = {row["name"] for row in cur.fetchall()}
            for col, col_type in TASKS_SCHEMA.items():
                if col not in existing:
                    # ALTER TABLE ADD COLUMN не поддерживает PRIMARY KEY - убираем
                    safe_type = col_type.replace("PRIMARY KEY", "").strip()
                    cur.execute(f"ALTER TABLE tasks ADD COLUMN {col} {safe_type}")

    # ------------------------------------------------------------------
    # CRUD задач (локальный кэш)
    # ------------------------------------------------------------------
    def get_all_tasks(self, include_deleted: bool = False) -> List[Task]:
        with self._cursor() as cur:
            if include_deleted:
                cur.execute("SELECT * FROM tasks")
            else:
                cur.execute("SELECT * FROM tasks WHERE deleted = 0")
            return [Task.from_db_row(dict(row)) for row in cur.fetchall()]

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cur.fetchone()
            return Task.from_db_row(dict(row)) if row else None

    def upsert_task_local(self, task: Task):
        """Сохраняет задачу локально и кладёт изменение в outbox (для будущей синхронизации)."""
        task.normalize()
        with self._cursor() as cur:
            cols = list(TASKS_SCHEMA.keys())
            values = [task.to_db_dict()[c] for c in cols]
            placeholders = ", ".join(["?"] * len(cols))
            updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "id")
            cur.execute(
                f"""INSERT INTO tasks ({', '.join(cols)}) VALUES ({placeholders})
                    ON CONFLICT(id) DO UPDATE SET {updates}""",
                values,
            )
            cur.execute(
                "INSERT INTO outbox (task_id, op, payload, created_at) VALUES (?, ?, ?, ?)",
                (task.id, "upsert", json.dumps(task.to_db_dict(), ensure_ascii=False), now_iso()),
            )

    def apply_remote_task(self, task: Task):
        """
        Применяет задачу, пришедшую из Google Sheets, БЕЗ постановки в outbox
        (это не локальное изменение). Используется движком синхронизации.
        Если задача есть в outbox (несинхронизированные локальные правки),
        решение "кто побеждает" принимает sync.py ДО вызова этого метода.
        """
        task.dirty = False
        with self._cursor() as cur:
            cols = list(TASKS_SCHEMA.keys())
            values = [task.to_db_dict()[c] for c in cols]
            placeholders = ", ".join(["?"] * len(cols))
            updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "id")
            cur.execute(
                f"""INSERT INTO tasks ({', '.join(cols)}) VALUES ({placeholders})
                    ON CONFLICT(id) DO UPDATE SET {updates}""",
                values,
            )

    def delete_task_local(self, task_id: str, hard: bool = False):
        with self._cursor() as cur:
            if hard:
                cur.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            else:
                cur.execute(
                    "UPDATE tasks SET deleted = 1, updated_at = ? WHERE id = ?",
                    (now_iso(), task_id),
                )
            cur.execute(
                "INSERT INTO outbox (task_id, op, payload, created_at) VALUES (?, ?, ?, ?)",
                (task_id, "delete", "{}", now_iso()),
            )

    # ------------------------------------------------------------------
    # Outbox
    # ------------------------------------------------------------------
    def get_outbox_entries(self) -> List[sqlite3.Row]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM outbox ORDER BY id ASC")
            return cur.fetchall()

    def has_pending_outbox_for(self, task_id: str) -> bool:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM outbox WHERE task_id = ?", (task_id,))
            return cur.fetchone()["c"] > 0

    def pending_task_ids(self) -> set:
        with self._cursor() as cur:
            cur.execute("SELECT DISTINCT task_id FROM outbox")
            return {row["task_id"] for row in cur.fetchall()}

    def remove_outbox_entry(self, entry_id: int):
        with self._cursor() as cur:
            cur.execute("DELETE FROM outbox WHERE id = ?", (entry_id,))

    def clear_outbox_for_task(self, task_id: str):
        with self._cursor() as cur:
            cur.execute("DELETE FROM outbox WHERE task_id = ?", (task_id,))

    def mark_outbox_error(self, entry_id: int, error: str):
        with self._cursor() as cur:
            cur.execute(
                "UPDATE outbox SET attempts = attempts + 1, last_error = ? WHERE id = ?",
                (error, entry_id),
            )

    # ------------------------------------------------------------------
    # Уведомления (защита от повторной отправки)
    # ------------------------------------------------------------------
    def was_notified(self, task_id: str, offset_minutes: int) -> bool:
        with self._cursor() as cur:
            cur.execute(
                "SELECT 1 FROM sent_notifications WHERE task_id = ? AND offset_minutes = ?",
                (task_id, offset_minutes),
            )
            return cur.fetchone() is not None

    def mark_notified(self, task_id: str, offset_minutes: int):
        with self._cursor() as cur:
            cur.execute(
                """INSERT OR REPLACE INTO sent_notifications (task_id, offset_minutes, sent_at)
                   VALUES (?, ?, ?)""",
                (task_id, offset_minutes, now_iso()),
            )

    def clear_notifications_for(self, task_id: str):
        with self._cursor() as cur:
            cur.execute("DELETE FROM sent_notifications WHERE task_id = ?", (task_id,))

    # ------------------------------------------------------------------
    # Meta (например, время последней синхронизации)
    # ------------------------------------------------------------------
    def get_meta(self, key: str, default=None):
        with self._cursor() as cur:
            cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else default

    def set_meta(self, key: str, value: str):
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
