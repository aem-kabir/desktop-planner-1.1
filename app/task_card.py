"""
task_card.py
Карточка задачи в виде accordion: свёрнутый заголовок + раскрываемое тело
с описанием и элементами редактирования (дата/время/приоритет/ответственный)
и кнопками Выполнено / Отменить / Отложить.
"""
from datetime import datetime, timedelta

from PyQt6.QtCore import pyqtSignal, QDate, QTime
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QDateEdit, QTimeEdit, QComboBox, QSizePolicy, QMenu
)

from config import PRIORITY_VALUES
from models import Task

PRIORITY_LABELS = {"High": "Высокий", "Medium": "Средний", "Low": "Низкий"}
PRIORITY_OBJECT_NAMES = {"High": "PriorityHigh", "Medium": "PriorityMedium", "Low": "PriorityLow"}


class TaskCard(QFrame):
    """Одна карточка задачи. Испускает сигналы при изменениях, чтобы
    main_window сохранял их в БД и ставил в outbox."""

    task_updated = pyqtSignal(Task)
    task_deleted = pyqtSignal(str)         # task_id — для мягкого удаления/архивации
    task_restored = pyqtSignal(str)        # task_id — восстановление из "Отменённых"

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task
        self.setObjectName("TaskCard")
        self._expanded = False
        self._build_ui()
        self.refresh_visuals()

    # ------------------------------------------------------------------
    def _build_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(6)

        # --- Заголовок (всегда виден) ---
        header = QHBoxLayout()
        self.expand_btn = QPushButton("▶")
        self.expand_btn.setObjectName("SecondaryButton")
        self.expand_btn.setFixedWidth(28)
        self.expand_btn.clicked.connect(self.toggle_expanded)
        header.addWidget(self.expand_btn)

        self.title_label = QLabel(self.task.title or "(без названия)")
        self.title_label.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        header.addWidget(self.title_label, stretch=1)

        self.priority_label = QLabel(PRIORITY_LABELS.get(self.task.priority, self.task.priority))
        self.priority_label.setObjectName(PRIORITY_OBJECT_NAMES.get(self.task.priority, "PriorityMedium"))
        header.addWidget(self.priority_label)

        self.deadline_label = QLabel(self._format_deadline())
        self.deadline_label.setStyleSheet("color: gray;")
        header.addWidget(self.deadline_label)

        outer.addLayout(header)

        # --- Тело (раскрывается) ---
        self.body = QWidget()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(28, 4, 4, 4)

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Описание задачи…")
        self.description_edit.setPlainText(self.task.description)
        self.description_edit.setMaximumHeight(80)
        self.description_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        body_layout.addWidget(self.description_edit)

        # Название (редактируемое)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Название:"))
        self.title_edit = QLineEdit(self.task.title)
        title_row.addWidget(self.title_edit, stretch=1)
        body_layout.addLayout(title_row)

        # Даты
        dates_row = QHBoxLayout()
        dates_row.addWidget(QLabel("Начало:"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDate(self._to_qdate(self.task.start_date_obj()) or QDate.currentDate())
        dates_row.addWidget(self.start_date_edit)

        dates_row.addWidget(QLabel("Дедлайн:"))
        self.deadline_date_edit = QDateEdit()
        self.deadline_date_edit.setCalendarPopup(True)
        self.deadline_date_edit.setDate(self._to_qdate(self.task.deadline_date_obj()) or QDate.currentDate())
        dates_row.addWidget(self.deadline_date_edit)

        self.deadline_time_edit = QTimeEdit()
        self.deadline_time_edit.setDisplayFormat("HH:mm")
        eff_time = self.task.effective_deadline_time()
        try:
            h, m = map(int, eff_time.split(":"))
            self.deadline_time_edit.setTime(QTime(h, m))
        except ValueError:
            self.deadline_time_edit.setTime(QTime(23, 59))
        dates_row.addWidget(self.deadline_time_edit)
        body_layout.addLayout(dates_row)

        # Приоритет и ответственный
        meta_row = QHBoxLayout()
        meta_row.addWidget(QLabel("Приоритет:"))
        self.priority_combo = QComboBox()
        self.priority_combo.addItems([PRIORITY_LABELS[p] for p in PRIORITY_VALUES])
        self.priority_combo.setCurrentIndex(PRIORITY_VALUES.index(self.task.priority))
        meta_row.addWidget(self.priority_combo)

        meta_row.addWidget(QLabel("Ответственный:"))
        self.assignee_edit = QLineEdit(self.task.assignee)
        meta_row.addWidget(self.assignee_edit, stretch=1)
        body_layout.addLayout(meta_row)

        # Кнопки действий
        actions_row = QHBoxLayout()
        self.save_btn = QPushButton("Сохранить")
        self.save_btn.clicked.connect(self._on_save_clicked)
        actions_row.addWidget(self.save_btn)

        self.done_btn = QPushButton("Выполнено")
        self.done_btn.setObjectName("SuccessButton")
        self.done_btn.clicked.connect(self._on_done_clicked)
        actions_row.addWidget(self.done_btn)

        self.cancel_btn = QPushButton("Отменить")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        actions_row.addWidget(self.cancel_btn)

        self.snooze_btn = QPushButton("Отложить ▾")
        self.snooze_btn.setObjectName("SecondaryButton")
        self.snooze_btn.clicked.connect(self._show_snooze_menu)
        actions_row.addWidget(self.snooze_btn)

        self.restore_btn = QPushButton("Восстановить")
        self.restore_btn.setObjectName("SecondaryButton")
        self.restore_btn.clicked.connect(lambda: self.task_restored.emit(self.task.id))
        self.restore_btn.setVisible(self.task.status == "Canceled")
        actions_row.addWidget(self.restore_btn)

        body_layout.addLayout(actions_row)

        outer.addWidget(self.body)
        self.body.setVisible(False)

    # ------------------------------------------------------------------
    def _to_qdate(self, d):
        if d is None:
            return None
        return QDate(d.year, d.month, d.day)

    def _format_deadline(self) -> str:
        dl = self.task.deadline_datetime()
        if dl is None:
            return ""
        return dl.strftime("%d.%m.%Y %H:%M")

    def toggle_expanded(self):
        self._expanded = not self._expanded
        self.body.setVisible(self._expanded)
        self.expand_btn.setText("▼" if self._expanded else "▶")

    # ------------------------------------------------------------------
    def refresh_visuals(self):
        """Обновляет цветовую индикацию по времени до дедлайна и просрочке."""
        self.title_label.setText(self.task.title or "(без названия)")
        self.priority_label.setText(PRIORITY_LABELS.get(self.task.priority, self.task.priority))
        self.priority_label.setObjectName(PRIORITY_OBJECT_NAMES.get(self.task.priority, "PriorityMedium"))
        self.deadline_label.setText(self._format_deadline())
        self.restore_btn.setVisible(self.task.status == "Canceled")
        self.done_btn.setVisible(self.task.status == "Active")
        self.cancel_btn.setVisible(self.task.status == "Active")
        self.snooze_btn.setVisible(self.task.status == "Active")

        seconds = self.task.seconds_to_deadline()
        self.setObjectName("TaskCard")
        if self.task.is_overdue():
            self.setObjectName("TaskCardOverdue")
        elif seconds is not None and self.task.status == "Active":
            if seconds < 3600:
                self.setObjectName("TaskCardWarnRed")
            elif seconds < 4 * 3600:
                self.setObjectName("TaskCardWarnYellow")
            else:
                self.setObjectName("TaskCard")
        # Форсируем переприменение стиля для смены objectName
        self.style().unpolish(self)
        self.style().polish(self)

    # ------------------------------------------------------------------
    def _collect_form_into_task(self):
        self.task.title = self.title_edit.text().strip()
        self.task.description = self.description_edit.toPlainText()
        qd = self.start_date_edit.date()
        self.task.start_date = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        qd2 = self.deadline_date_edit.date()
        self.task.deadline_date = f"{qd2.year():04d}-{qd2.month():02d}-{qd2.day():02d}"
        qt = self.deadline_time_edit.time()
        self.task.deadline_time = f"{qt.hour():02d}:{qt.minute():02d}"
        self.task.priority = PRIORITY_VALUES[self.priority_combo.currentIndex()]
        self.task.assignee = self.assignee_edit.text().strip()

    def _on_save_clicked(self):
        self._collect_form_into_task()
        self.task.touch()
        self.task_updated.emit(self.task)
        self.refresh_visuals()

    def _on_done_clicked(self):
        self._collect_form_into_task()
        self.task.status = "Completed"
        self.task.touch()
        self.task_updated.emit(self.task)
        self.refresh_visuals()

    def _on_cancel_clicked(self):
        self._collect_form_into_task()
        self.task.status = "Canceled"
        self.task.touch()
        self.task_updated.emit(self.task)
        self.refresh_visuals()

    def _show_snooze_menu(self):
        menu = QMenu(self)
        act_3h = menu.addAction("+3 часа")
        act_tomorrow = menu.addAction("На завтра")
        menu.addAction("На следующие выходные")
        chosen = menu.exec(self.snooze_btn.mapToGlobal(self.snooze_btn.rect().bottomLeft()))
        if chosen is None:
            return
        self._collect_form_into_task()
        now = datetime.now()
        if chosen == act_3h:
            new_dt = now + timedelta(hours=3)
        elif chosen == act_tomorrow:
            tomorrow = now.date() + timedelta(days=1)
            new_dt = datetime.combine(tomorrow, now.time())
        else:  # следующие выходные (ближайшая суббота)
            days_ahead = (5 - now.weekday()) % 7  # 5 = суббота (Mon=0)
            days_ahead = days_ahead or 7
            sat = now.date() + timedelta(days=days_ahead)
            new_dt = datetime.combine(sat, now.time())

        self.task.deadline_date = new_dt.strftime("%Y-%m-%d")
        self.task.deadline_time = new_dt.strftime("%H:%M")
        self.task.touch()
        self.task_updated.emit(self.task)
        # Обновим поля формы, чтобы они отражали новое значение
        self.deadline_date_edit.setDate(QDate(new_dt.year, new_dt.month, new_dt.day))
        self.deadline_time_edit.setTime(QTime(new_dt.hour, new_dt.minute))
        self.refresh_visuals()
