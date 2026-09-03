"""
sync.py
SyncWorker выполняется в отдельном QThread и никогда не блокирует UI.

Логика конфликтов:
- Побеждает запись с более свежим UpdatedAt.
- Локальные несинхронизированные правки (задачи, у которых есть записи в outbox)
  НЕ перезатираются входящими данными из таблицы, пока они не выгружены
  (сначала всегда пытаемся отправить исходящие изменения, потом читаем входящие;
  если задача всё ещё в outbox после попытки отправки - входящие данные для неё
  по-прежнему не должны затирать более новую локальную версию: сравниваем
  UpdatedAt и применяем только если удалённая версия строго новее).
"""
import traceback
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal, QObject

from config import Settings
from models import Task, now_iso
from db import Database

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:  # библиотека может быть недоступна до первой настройки
    GSPREAD_AVAILABLE = False

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def extract_spreadsheet_id(text: str) -> str:
    """Принимает либо чистый ID, либо полную ссылку вида
    https://docs.google.com/spreadsheets/d/<ID>/edit#gid=0 и извлекает ID."""
    text = (text or "").strip()
    if "/d/" in text:
        try:
            after = text.split("/d/", 1)[1]
            return after.split("/")[0].split("?")[0]
        except IndexError:
            return text
    return text


def parse_iso(ts: str):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


class SyncResult:
    def __init__(self):
        self.ok = False
        self.error = ""
        self.pushed = 0
        self.pulled = 0
        self.conflicts_kept_local = 0


class SyncEngine:
    """Логика синхронизации, изолированная от Qt-специфики, чтобы её можно
    было тестировать отдельно и переиспользовать (например, при "Проверить подключение")."""

    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self._client = None
        self._sheet = None

    # ------------------------------------------------------------------
    def _connect(self):
        if not GSPREAD_AVAILABLE:
            raise RuntimeError(
                "Библиотеки gspread/google-auth не установлены. "
                "Выполните: pip install -r requirements.txt"
            )
        creds_path = self.settings.get("google_sheets", "credentials_path", default="")
        spreadsheet_id_raw = self.settings.get("google_sheets", "spreadsheet_id", default="")
        sheet_name = self.settings.get("google_sheets", "sheet_name", default="Tasks")

        if not creds_path:
            raise RuntimeError("Не указан путь к credentials.json в настройках.")
        if not spreadsheet_id_raw:
            raise RuntimeError("Не указан Spreadsheet ID (или ссылка) в настройках.")

        spreadsheet_id = extract_spreadsheet_id(spreadsheet_id_raw)

        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(spreadsheet_id)
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=200, cols=20)
            from config import SHEET_HEADERS
            worksheet.append_row(SHEET_HEADERS)

        self._client = client
        self._sheet = worksheet
        return worksheet

    def test_connection(self) -> SyncResult:
        result = SyncResult()
        try:
            sheet = self._connect()
            _ = sheet.row_values(1)  # читаем заголовки, чтобы убедиться в доступе
            result.ok = True
        except Exception as e:  # noqa: BLE001
            result.error = str(e)
        return result

    # ------------------------------------------------------------------
    def run_sync(self) -> SyncResult:
        result = SyncResult()
        try:
            sheet = self._connect()
        except Exception as e:  # noqa: BLE001
            result.error = str(e)
            return result

        try:
            # 1. Сначала выгружаем исходящие изменения (outbox), чтобы наши
            #    последние правки как можно скорее попали в таблицу.
            result.pushed = self._push_outbox(sheet)

            # 2. Затем читаем всю таблицу и мёржим с локальной базой.
            pulled, conflicts = self._pull_and_merge(sheet)
            result.pulled = pulled
            result.conflicts_kept_local = conflicts

            result.ok = True
            self.db.set_meta("last_sync_at", now_iso())
        except Exception as e:  # noqa: BLE001
            result.error = f"{e}\n{traceback.format_exc(limit=3)}"
        return result

    # ------------------------------------------------------------------
    def _push_outbox(self, sheet) -> int:
        entries = self.db.get_outbox_entries()
        if not entries:
            return 0

        # Кэшируем текущее состояние листа один раз (по ID), чтобы не делать
        # запрос к API на каждую запись outbox.
        existing_records = sheet.get_all_records()
        id_to_row_index = {}
        for idx, rec in enumerate(existing_records, start=2):  # строка 1 — заголовки
            rid = str(rec.get("ID", "")).strip()
            if rid:
                id_to_row_index[rid] = idx

        pushed = 0
        for entry in entries:
            task_id = entry["task_id"]
            op = entry["op"]
            try:
                if op == "delete":
                    row_idx = id_to_row_index.get(task_id)
                    if row_idx:
                        sheet.delete_rows(row_idx)
                        # Сдвигаем индексы строк ниже удалённой
                        id_to_row_index = {
                            rid: (ri - 1 if ri > row_idx else ri)
                            for rid, ri in id_to_row_index.items()
                            if ri != row_idx
                        }
                    self.db.delete_task_local(task_id, hard=True)
                    self.db.clear_notifications_for(task_id)
                else:  # upsert
                    # Не используем JSON-снимок из outbox: всегда берём
                    # актуальное состояние задачи из локальной БД, т.к. оно
                    # могло измениться повторно после постановки в очередь.
                    current = self.db.get_task(task_id)
                    if current is None:
                        # Задачу уже удалили локально после постановки в очередь
                        self.db.remove_outbox_entry(entry["id"])
                        continue
                    row_values = current.to_row()
                    row_idx = id_to_row_index.get(task_id)
                    if row_idx:
                        sheet.update(f"A{row_idx}", [row_values])
                    else:
                        sheet.append_row(row_values)
                        id_to_row_index[task_id] = len(id_to_row_index) + 2
                pushed += 1
                self.db.remove_outbox_entry(entry["id"])
            except Exception as e:  # noqa: BLE001
                self.db.mark_outbox_error(entry["id"], str(e))
                # Не прерываем цикл — пробуем отправить остальные записи
                continue
        return pushed

    def _pull_and_merge(self, sheet):
        records = sheet.get_all_records()
        remote_tasks = {}
        for rec in records:
            task = Task.from_record(rec)
            remote_tasks[task.id] = task

        pending_ids = self.db.pending_task_ids()  # ещё не отправленные локальные правки
        local_tasks = {t.id: t for t in self.db.get_all_tasks(include_deleted=True)}

        pulled = 0
        conflicts_kept_local = 0

        for rid, remote_task in remote_tasks.items():
            local_task = local_tasks.get(rid)

            if local_task is None:
                # Новая задача, появившаяся в таблице (например, добавлена вручную)
                self.db.apply_remote_task(remote_task)
                pulled += 1
                continue

            if rid in pending_ids:
                # Есть несинхронизированные локальные изменения — не затираем их
                # входящими данными, если только удалённая версия не строго новее
                # (например, кто-то другой успел синхронизировать более свежую правку).
                remote_dt = parse_iso(remote_task.updated_at)
                local_dt = parse_iso(local_task.updated_at)
                if remote_dt and local_dt and remote_dt > local_dt:
                    self.db.apply_remote_task(remote_task)
                    self.db.clear_outbox_for_task(rid)  # локальные правки устарели
                    pulled += 1
                else:
                    conflicts_kept_local += 1
                continue

            # Нет локальных несинхронизированных правок — обычное сравнение
            # по UpdatedAt: побеждает более свежая запись.
            remote_dt = parse_iso(remote_task.updated_at)
            local_dt = parse_iso(local_task.updated_at)
            if remote_dt and local_dt:
                if remote_dt > local_dt:
                    self.db.apply_remote_task(remote_task)
                    pulled += 1
                # если локальная новее или равна — ничего не делаем
            elif remote_dt and not local_dt:
                self.db.apply_remote_task(remote_task)
                pulled += 1

        return pulled, conflicts_kept_local


class SyncWorker(QObject):
    """Живёт в отдельном QThread. Управляется через сигналы, чтобы UI-поток
    никогда не ждал сетевых операций."""

    sync_started = pyqtSignal()
    sync_finished = pyqtSignal(bool, str, int, int)  # ok, error, pushed, pulled
    tasks_changed = pyqtSignal()  # сигнал для UI: перечитать задачи из локальной БД

    def __init__(self, db: Database, settings: Settings):
        super().__init__()
        self.db = db
        self.settings = settings
        self.engine = SyncEngine(db, settings)
        self._busy = False

    def run_once(self):
        if self._busy:
            return
        self._busy = True
        self.sync_started.emit()
        result = self.engine.run_sync()
        self._busy = False
        self.sync_finished.emit(result.ok, result.error, result.pushed, result.pulled)
        if result.ok and (result.pushed or result.pulled):
            self.tasks_changed.emit()

    def test_connection(self):
        return self.engine.test_connection()


class SyncThread(QThread):
    """Тонкая обёртка QThread, периодически вызывающая SyncWorker.run_once()
    по таймеру, реализованному через QThread.msleep в цикле, плюс поддержка
    ручного триггера 'Синхронизировать сейчас' через флаг force_sync."""

    sync_started = pyqtSignal()
    sync_finished = pyqtSignal(bool, str, int, int)
    tasks_changed = pyqtSignal()

    def __init__(self, db: Database, settings: Settings, parent=None):
        super().__init__(parent)
        self.db = db
        self.settings = settings
        self.worker = SyncWorker(db, settings)
        self.worker.sync_started.connect(self.sync_started.emit)
        self.worker.sync_finished.connect(self.sync_finished.emit)
        self.worker.tasks_changed.connect(self.tasks_changed.emit)
        self._running = True
        self._force = False
        self._elapsed_ms = 0

    def request_sync_now(self):
        self._force = True

    def stop(self):
        self._running = False

    def run(self):
        tick_ms = 500
        while self._running:
            self.msleep(tick_ms)
            self._elapsed_ms += tick_ms
            interval_sec = int(self.settings.get("system", "sync_interval_sec", default=30))
            interval_ms = max(15, interval_sec) * 1000
            if self._force or self._elapsed_ms >= interval_ms:
                self._force = False
                self._elapsed_ms = 0
                self.worker.run_once()
