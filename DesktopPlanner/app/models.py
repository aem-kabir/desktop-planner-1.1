"""
models.py
Датакласс Task и (де)сериализация в/из строки Google Таблицы.
Сопоставление колонок производится ПО ИМЕНИ заголовка, а не по позиции.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, time as dtime
from typing import Optional

from config import SHEET_HEADERS, DEFAULT_STATUS, DEFAULT_PRIORITY, STATUS_VALUES, PRIORITY_VALUES

DATE_FMT = "%Y-%m-%d"
TIME_FMT = "%H:%M"
DEFAULT_DEADLINE_TIME = "23:59"


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def new_uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class Task:
    id: str = field(default_factory=new_uuid)
    title: str = ""
    description: str = ""
    start_date: str = ""          # YYYY-MM-DD
    deadline_date: str = ""       # YYYY-MM-DD
    deadline_time: str = ""       # HH:MM, может быть пустым
    status: str = DEFAULT_STATUS
    priority: str = DEFAULT_PRIORITY
    assignee: str = ""
    updated_at: str = field(default_factory=now_iso)

    # --- Служебные (не пишутся в таблицу, используются локально) ---
    dirty: bool = False           # есть несинхронизированные локальные изменения
    deleted: bool = False         # помечена к удалению (мягкое удаление)

    # ------------------------------------------------------------------
    # Валидация / нормализация
    # ------------------------------------------------------------------
    def normalize(self):
        if self.status not in STATUS_VALUES:
            self.status = DEFAULT_STATUS
        if self.priority not in PRIORITY_VALUES:
            self.priority = DEFAULT_PRIORITY
        if not self.id:
            self.id = new_uuid()

    def effective_deadline_time(self) -> str:
        """Пустой DeadlineTime трактуется как 23:59."""
        return self.deadline_time.strip() if self.deadline_time and self.deadline_time.strip() else DEFAULT_DEADLINE_TIME

    def deadline_datetime(self) -> Optional[datetime]:
        if not self.deadline_date:
            return None
        try:
            d = datetime.strptime(self.deadline_date.strip(), DATE_FMT).date()
        except ValueError:
            return None
        t_str = self.effective_deadline_time()
        try:
            t = datetime.strptime(t_str, TIME_FMT).time()
        except ValueError:
            t = dtime(23, 59)
        return datetime.combine(d, t)

    def start_date_obj(self) -> Optional[date]:
        if not self.start_date:
            return None
        try:
            return datetime.strptime(self.start_date.strip(), DATE_FMT).date()
        except ValueError:
            return None

    def deadline_date_obj(self) -> Optional[date]:
        if not self.deadline_date:
            return None
        try:
            return datetime.strptime(self.deadline_date.strip(), DATE_FMT).date()
        except ValueError:
            return None

    def is_overdue(self, now: Optional[datetime] = None) -> bool:
        if self.status != "Active":
            return False
        dl = self.deadline_datetime()
        if dl is None:
            return False
        now = now or datetime.now()
        return dl < now

    def is_today(self, today: Optional[date] = None) -> bool:
        """Задача попадает в диапазон StartDate..DeadlineDate относительно today."""
        today = today or date.today()
        start = self.start_date_obj()
        end = self.deadline_date_obj()
        if start is None and end is None:
            return False
        if start is None:
            start = end
        if end is None:
            end = start
        if start > end:
            start, end = end, start
        return start <= today <= end

    def seconds_to_deadline(self, now: Optional[datetime] = None) -> Optional[float]:
        dl = self.deadline_datetime()
        if dl is None:
            return None
        now = now or datetime.now()
        return (dl - now).total_seconds()

    def touch(self):
        """Отметить как изменённую сейчас (обновляет UpdatedAt и dirty)."""
        self.updated_at = now_iso()
        self.dirty = True

    # ------------------------------------------------------------------
    # Сериализация в строку Google Таблицы (список значений по SHEET_HEADERS)
    # ------------------------------------------------------------------
    def to_row(self) -> list:
        mapping = {
            "ID": self.id,
            "Title": self.title,
            "Description": self.description,
            "StartDate": self.start_date,
            "DeadlineDate": self.deadline_date,
            "DeadlineTime": self.deadline_time,
            "Status": self.status,
            "Priority": self.priority,
            "Assignee": self.assignee,
            "UpdatedAt": self.updated_at,
        }
        return [mapping[h] for h in SHEET_HEADERS]

    @classmethod
    def from_record(cls, record: dict) -> "Task":
        """
        record — словарь {ЗаголовокКолонки: значение}, как возвращает
        gspread's get_all_records() (сопоставление ПО ИМЕНИ).
        Пустые Status/Priority трактуются как дефолт (защита от ручных правок).
        """
        task_id = str(record.get("ID", "")).strip() or new_uuid()
        status = str(record.get("Status", "")).strip() or DEFAULT_STATUS
        priority = str(record.get("Priority", "")).strip() or DEFAULT_PRIORITY
        if status not in STATUS_VALUES:
            status = DEFAULT_STATUS
        if priority not in PRIORITY_VALUES:
            priority = DEFAULT_PRIORITY
        updated_at = str(record.get("UpdatedAt", "")).strip() or now_iso()

        return cls(
            id=task_id,
            title=str(record.get("Title", "")).strip(),
            description=str(record.get("Description", "")),
            start_date=str(record.get("StartDate", "")).strip(),
            deadline_date=str(record.get("DeadlineDate", "")).strip(),
            deadline_time=str(record.get("DeadlineTime", "")).strip(),
            status=status,
            priority=priority,
            assignee=str(record.get("Assignee", "")).strip(),
            updated_at=updated_at,
            dirty=False,
            deleted=False,
        )

    # ------------------------------------------------------------------
    # Сериализация в/из словаря для SQLite
    # ------------------------------------------------------------------
    def to_db_dict(self) -> dict:
        d = asdict(self)
        d["dirty"] = int(self.dirty)
        d["deleted"] = int(self.deleted)
        return d

    @classmethod
    def from_db_row(cls, row: dict) -> "Task":
        return cls(
            id=row["id"],
            title=row["title"] or "",
            description=row["description"] or "",
            start_date=row["start_date"] or "",
            deadline_date=row["deadline_date"] or "",
            deadline_time=row["deadline_time"] or "",
            status=row["status"] or DEFAULT_STATUS,
            priority=row["priority"] or DEFAULT_PRIORITY,
            assignee=row["assignee"] or "",
            updated_at=row["updated_at"] or now_iso(),
            dirty=bool(row["dirty"]),
            deleted=bool(row["deleted"]),
        )
