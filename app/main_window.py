"""
main_window.py
Главное окно планера: frameless-окно со своей шапкой, вкладки
"Сегодня" / "Календарь" / "Отменённые", компактный режим,
прилипание к краям экрана, always-on-top, прозрачность.
"""
from datetime import date, datetime

from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QIcon, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget,
    QScrollArea, QCalendarWidget
)

from config import Settings, ICON_PATH
from db import Database
from models import Task
from task_card import TaskCard
from styles import get_stylesheet
from autostart import get_system_theme
from notifier import Notifier
from settings_dialog import SettingsDialog

SNAP_MARGIN = 20  # пикселей до края экрана, при котором окно "прилипает"


class TitleBar(QWidget):
    """Собственная шапка окна (frameless), даёт возможность перетаскивать
    окно и содержит кнопки свернуть в компактный режим / в трей / закрыть."""

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.setObjectName("TitleBar")
        self.setFixedHeight(36)
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 6, 0)

        self.title_label = QLabel("Планер задач")
        self.title_label.setObjectName("TitleLabel")
        layout.addWidget(self.title_label)
        layout.addStretch()

        self.compact_btn = QPushButton("—")
        self.compact_btn.setObjectName("TitleBarButton")
        self.compact_btn.setToolTip("Компактный режим")
        self.compact_btn.clicked.connect(self.parent_window.toggle_compact_mode)
        layout.addWidget(self.compact_btn)

        self.minimize_btn = QPushButton("🗕")
        self.minimize_btn.setObjectName("TitleBarButton")
        self.minimize_btn.setToolTip("Свернуть в трей")
        self.minimize_btn.clicked.connect(self.parent_window.hide_to_tray)
        layout.addWidget(self.minimize_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("TitleBarCloseButton")
        self.close_btn.setToolTip("Закрыть")
        self.close_btn.clicked.connect(self.parent_window.close)
        layout.addWidget(self.close_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.parent_window.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.parent_window.move_with_snap(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


class TaskListPanel(QScrollArea):
    """Прокручиваемый список TaskCard с секцией 'Просрочено' сверху (для
    вкладки Сегодня)."""

    def __init__(self, show_overdue_section: bool = False, empty_text: str = "Нет задач"):
        super().__init__()
        self.setWidgetResizable(True)
        self.show_overdue_section = show_overdue_section
        self.empty_text = empty_text
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setSpacing(8)
        self.setWidget(self.container)
        self.cards = []

    def clear(self):
        for card in self.cards:
            card.setParent(None)
            card.deleteLater()
        self.cards = []
        # Удаляем и оставшиеся заголовки/лейблы (например, пустое сообщение)
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def add_header(self, text: str, overdue: bool = False):
        label = QLabel(text)
        label.setObjectName("OverdueHeader" if overdue else "SectionHeader")
        self.layout.addWidget(label)

    def add_empty_message(self):
        label = QLabel(self.empty_text)
        label.setStyleSheet("color: gray; padding: 20px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(label)

    def add_card(self, card: TaskCard):
        self.layout.addWidget(card)
        self.cards.append(card)


class MainWindow(QWidget):
    def __init__(self, settings: Settings, db: Database, sync_thread, tray_icon, app):
        super().__init__()
        self.settings = settings
        self.db = db
        self.sync_thread = sync_thread
        self.tray_icon = tray_icon
        self.app = app
        self.notifier = Notifier(tray_icon=tray_icon, icon_path=str(ICON_PATH) if ICON_PATH.exists() else None)

        self._compact = False
        self._selected_calendar_date = date.today()

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self._build_ui()
        self.apply_settings()
        self.reload_tasks()

        # Таймер обновления визуала карточек (цветовая индикация по времени) и проверки уведомлений
        self.tick_timer = QTimer(self)
        self.tick_timer.timeout.connect(self._on_tick)
        self.tick_timer.start(15_000)  # каждые 15 секунд

        self.sync_thread.tasks_changed.connect(self.reload_tasks)
        self.sync_thread.sync_finished.connect(self._on_sync_finished)

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.title_bar = TitleBar(self)
        root.addWidget(self.title_bar)

        self.body_container = QWidget()
        body_layout = QVBoxLayout(self.body_container)
        body_layout.setContentsMargins(10, 10, 10, 10)

        top_row = QHBoxLayout()
        self.add_btn = QPushButton("+")
        self.add_btn.setObjectName("AddButton")
        self.add_btn.setToolTip("Новая задача")
        self.add_btn.clicked.connect(self.create_new_task)
        top_row.addWidget(self.add_btn)
        top_row.addStretch()

        self.sync_status_label = QLabel("")
        self.sync_status_label.setStyleSheet("color: gray; font-size: 11px;")
        top_row.addWidget(self.sync_status_label)

        self.sync_now_btn = QPushButton("Синхронизировать")
        self.sync_now_btn.setObjectName("SecondaryButton")
        self.sync_now_btn.clicked.connect(self.sync_now)
        top_row.addWidget(self.sync_now_btn)

        self.settings_btn = QPushButton("Настройки")
        self.settings_btn.setObjectName("SecondaryButton")
        self.settings_btn.clicked.connect(self.open_settings)
        top_row.addWidget(self.settings_btn)

        body_layout.addLayout(top_row)

        self.tabs = QTabWidget()
        self.today_panel = TaskListPanel(show_overdue_section=True, empty_text="На сегодня задач нет 🎉")
        self.calendar_tab = self._build_calendar_tab()
        self.canceled_panel = TaskListPanel(empty_text="Отменённых задач нет")

        self.tabs.addTab(self.today_panel, "Сегодня")
        self.tabs.addTab(self.calendar_tab, "Календарь")
        self.tabs.addTab(self.canceled_panel, "Отменённые")
        body_layout.addWidget(self.tabs)

        root.addWidget(self.body_container)

        # --- Компактная панель ---
        self.compact_bar = QWidget()
        self.compact_bar.setObjectName("CompactBar")
        self.compact_bar.setFixedHeight(40)
        compact_layout = QHBoxLayout(self.compact_bar)
        compact_layout.setContentsMargins(12, 4, 12, 4)
        self.compact_label = QLabel("🔥 0 | 🕒 0")
        self.compact_label.mousePressEvent = lambda e: self.toggle_compact_mode()
        compact_layout.addWidget(self.compact_label)
        compact_layout.addStretch()
        expand_btn = QPushButton("▢")
        expand_btn.setObjectName("TitleBarButton")
        expand_btn.setToolTip("Развернуть")
        expand_btn.clicked.connect(self.toggle_compact_mode)
        compact_layout.addWidget(expand_btn)
        root.addWidget(self.compact_bar)
        self.compact_bar.setVisible(False)

        self.resize(420, 560)

    def _build_calendar_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        self.calendar_widget = QCalendarWidget()
        self.calendar_widget.setGridVisible(True)
        self.calendar_widget.selectionChanged.connect(self._on_calendar_date_changed)
        layout.addWidget(self.calendar_widget)

        self.calendar_list_panel = TaskListPanel(empty_text="На эту дату задач нет")
        layout.addWidget(self.calendar_list_panel)
        return w

    # ------------------------------------------------------------------
    # Загрузка / отображение задач
    # ------------------------------------------------------------------
    def reload_tasks(self):
        all_tasks = self.db.get_all_tasks()
        self._render_today_tab(all_tasks)
        self._render_calendar_tab(all_tasks)
        self._render_canceled_tab(all_tasks)
        self._update_compact_and_tray(all_tasks)

    def _make_card(self, task: Task, panel: TaskListPanel):
        card = TaskCard(task)
        card.task_updated.connect(self._on_task_updated)
        card.task_deleted.connect(self._on_task_canceled_from_card)
        card.task_restored.connect(self._on_task_restored)
        panel.add_card(card)
        return card

    def _render_today_tab(self, all_tasks):
        self.today_panel.clear()
        today = date.today()
        overdue = [t for t in all_tasks if t.is_overdue()]
        todays = [t for t in all_tasks if t.status == "Active" and t.is_today(today) and not t.is_overdue()]

        overdue.sort(key=lambda t: t.deadline_datetime() or datetime.max)
        todays.sort(key=lambda t: t.deadline_datetime() or datetime.max)

        if overdue:
            self.today_panel.add_header(f"🔥 Просрочено ({len(overdue)})", overdue=True)
            for t in overdue:
                self._make_card(t, self.today_panel)

        if todays:
            self.today_panel.add_header(f"Сегодня ({len(todays)})")
            for t in todays:
                self._make_card(t, self.today_panel)

        if not overdue and not todays:
            self.today_panel.add_empty_message()

    def _render_calendar_tab(self, all_tasks):
        self.calendar_list_panel.clear()
        selected = self._selected_calendar_date
        matching = [
            t for t in all_tasks
            if t.status != "Canceled" and t.is_today(selected)
        ]
        matching.sort(key=lambda t: t.deadline_datetime() or datetime.max)
        if matching:
            for t in matching:
                self._make_card(t, self.calendar_list_panel)
        else:
            self.calendar_list_panel.add_empty_message()

    def _render_canceled_tab(self, all_tasks):
        self.canceled_panel.clear()
        canceled = [t for t in all_tasks if t.status == "Canceled"]
        canceled.sort(key=lambda t: t.updated_at, reverse=True)
        if canceled:
            for t in canceled:
                self._make_card(t, self.canceled_panel)
        else:
            self.canceled_panel.add_empty_message()

    def _on_calendar_date_changed(self):
        qd = self.calendar_widget.selectedDate()
        self._selected_calendar_date = date(qd.year(), qd.month(), qd.day())
        all_tasks = self.db.get_all_tasks()
        self._render_calendar_tab(all_tasks)

    def _update_compact_and_tray(self, all_tasks):
        overdue_count = sum(1 for t in all_tasks if t.is_overdue())
        today_count = sum(1 for t in all_tasks if t.status == "Active" and t.is_today() and not t.is_overdue())
        self.compact_label.setText(f"🔥 {overdue_count} | 🕒 {today_count}")
        self.tray_icon.update_counters(overdue_count, today_count)

    # ------------------------------------------------------------------
    # Обработчики действий с задачами
    # ------------------------------------------------------------------
    def create_new_task(self):
        task = Task(title="Новая задача", start_date=date.today().strftime("%Y-%m-%d"),
                    deadline_date=date.today().strftime("%Y-%m-%d"))
        task.touch()
        self.db.upsert_task_local(task)
        self.reload_tasks()

    def _on_task_updated(self, task: Task):
        self.db.upsert_task_local(task)
        self.reload_tasks()

    def _on_task_canceled_from_card(self, task_id: str):
        task = self.db.get_task(task_id)
        if task:
            task.status = "Canceled"
            task.touch()
            self.db.upsert_task_local(task)
        self.reload_tasks()

    def _on_task_restored(self, task_id: str):
        task = self.db.get_task(task_id)
        if task:
            task.status = "Active"
            task.touch()
            self.db.upsert_task_local(task)
        self.reload_tasks()

    # ------------------------------------------------------------------
    # Синхронизация
    # ------------------------------------------------------------------
    def sync_now(self):
        self.sync_status_label.setText("Синхронизация…")
        self.sync_thread.request_sync_now()

    def _on_sync_finished(self, ok, error, pushed, pulled):
        if ok:
            self.sync_status_label.setText(f"✅ Синхронизировано ({pushed}↑ {pulled}↓)")
        else:
            short_error = (error or "").splitlines()[0][:120] if error else "неизвестная ошибка"
            self.sync_status_label.setText(f"⚠ Ошибка синхронизации: {short_error}")

    # ------------------------------------------------------------------
    # Настройки / тема / прочее
    # ------------------------------------------------------------------
    def open_settings(self):
        dlg = SettingsDialog(self.settings, self.db, self)
        dlg.settings_saved.connect(self.apply_settings)
        dlg.exec()

    def apply_settings(self):
        theme = self.settings.get("personalization", "theme", default="System")
        resolved_theme = get_system_theme() if theme == "System" else theme
        self.setStyleSheet(get_stylesheet(resolved_theme))

        always_on_top = self.settings.get("personalization", "always_on_top", default=False)
        flags = self.windowFlags()
        if always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()

        opacity = self.settings.get("personalization", "opacity", default=100)
        self.setWindowOpacity(max(20, min(100, int(opacity))) / 100.0)

        geometry = self.settings.get("system", "window_geometry", default=None)
        if geometry and len(geometry) == 4:
            self.setGeometry(*geometry)

    # ------------------------------------------------------------------
    # Компактный режим
    # ------------------------------------------------------------------
    def toggle_compact_mode(self):
        self._compact = not self._compact
        self.body_container.setVisible(not self._compact)
        self.compact_bar.setVisible(self._compact)
        if self._compact:
            self.setFixedHeight(36 + 40)
            self.setMinimumWidth(220)
            self.setMaximumWidth(320)
        else:
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            self.setFixedHeight(16777215)
            self.setMinimumHeight(0)
            self.resize(420, 560)

    # ------------------------------------------------------------------
    # Перетаскивание окна с прилипанием к краям экрана
    # ------------------------------------------------------------------
    def move_with_snap(self, new_pos: QPoint):
        snap_enabled = self.settings.get("personalization", "snap_to_edges", default=True)
        if not snap_enabled:
            self.move(new_pos)
            return

        screen = QGuiApplication.screenAt(new_pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x, y = new_pos.x(), new_pos.y()
        w, h = self.width(), self.height()

        if abs(x - geo.left()) < SNAP_MARGIN:
            x = geo.left()
        if abs((x + w) - geo.right()) < SNAP_MARGIN:
            x = geo.right() - w
        if abs(y - geo.top()) < SNAP_MARGIN:
            y = geo.top()
        if abs((y + h) - geo.bottom()) < SNAP_MARGIN:
            y = geo.bottom() - h

        self.move(QPoint(x, y))

    # ------------------------------------------------------------------
    # Уведомления
    # ------------------------------------------------------------------
    def _on_tick(self):
        for panel in (self.today_panel, self.calendar_list_panel, self.canceled_panel):
            for card in panel.cards:
                card.refresh_visuals()
        self._check_notifications()

    def _check_notifications(self):
        if not self.settings.get("notifications", "enabled", default=True):
            return
        sound = self.settings.get("notifications", "sound", default=True)
        offsets = self.settings.get("notifications", "offsets_minutes", default=[120, 60, 15])
        tasks = self.db.get_all_tasks()
        now = datetime.now()
        for task in tasks:
            if task.status != "Active":
                continue
            seconds = task.seconds_to_deadline(now)
            if seconds is None or seconds < 0:
                continue
            minutes_left = seconds / 60.0
            for offset in offsets:
                # Срабатывает один раз, когда осталось <= offset минут (и ещё не отправляли)
                if minutes_left <= offset and not self.db.was_notified(task.id, offset):
                    self.notifier.notify(
                        "Дедлайн приближается",
                        f"«{task.title}» — осталось ~{offset} мин.",
                        sound=sound,
                    )
                    self.db.mark_notified(task.id, offset)

        all_tasks = self.db.get_all_tasks()
        self._update_compact_and_tray(all_tasks)

    # ------------------------------------------------------------------
    # Управление окном (трей, закрытие)
    # ------------------------------------------------------------------
    def hide_to_tray(self):
        self._save_geometry()
        self.hide()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide_to_tray()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _save_geometry(self):
        geo = self.geometry()
        self.settings.set("system", "window_geometry", [geo.x(), geo.y(), geo.width(), geo.height()])
        self.settings.save()

    def closeEvent(self, event):
        close_to_tray = self.settings.get("system", "close_to_tray", default=True)
        if close_to_tray:
            event.ignore()
            self.hide_to_tray()
        else:
            self._save_geometry()
            event.accept()
            self.app.quit()
