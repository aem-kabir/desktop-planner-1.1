"""
tray.py
Системный трей: иконка + контекстное меню
(Показать/Скрыть, Синхронизировать сейчас, Настройки, Выход).
"""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu

from config import APP_DISPLAY_NAME


class TrayIcon(QSystemTrayIcon):
    show_hide_requested = pyqtSignal()
    sync_now_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, icon: QIcon, parent=None):
        super().__init__(icon, parent)
        self.setToolTip(APP_DISPLAY_NAME)
        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self):
        menu = QMenu()
        self.toggle_action = menu.addAction("Показать/Скрыть планер")
        self.toggle_action.triggered.connect(self.show_hide_requested.emit)

        sync_action = menu.addAction("Синхронизировать сейчас")
        sync_action.triggered.connect(self.sync_now_requested.emit)

        settings_action = menu.addAction("Настройки")
        settings_action.triggered.connect(self.settings_requested.emit)

        menu.addSeparator()

        quit_action = menu.addAction("Выход")
        quit_action.triggered.connect(self.quit_requested.emit)

        self.setContextMenu(menu)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_hide_requested.emit()

    def update_counters(self, overdue_count: int, today_count: int):
        self.setToolTip(f"{APP_DISPLAY_NAME}\n🔥 Просрочено: {overdue_count} | 🕒 Сегодня: {today_count}")
