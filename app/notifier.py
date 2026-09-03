"""
notifier.py
Windows Toast уведомления через win11toast, с fallback на QSystemTrayIcon.showMessage,
если win11toast недоступен (например, старая Windows или библиотека не установлена).

Дедупликация ("без повторного дублирования одного и того же уведомления")
обеспечивается на уровне вызывающего кода (main_window.py), который сверяется
с таблицей sent_notifications в БД перед вызовом notify().
"""
import sys
import logging

logger = logging.getLogger(__name__)

try:
    from win11toast import toast as _win11_toast
    WIN11TOAST_AVAILABLE = True
except ImportError:
    WIN11TOAST_AVAILABLE = False


class Notifier:
    def __init__(self, tray_icon=None, icon_path: str = None):
        """
        tray_icon: QSystemTrayIcon — используется как fallback.
        icon_path: путь к .ico/.png для тела toast-уведомления (опционально).
        """
        self.tray_icon = tray_icon
        self.icon_path = icon_path
        self.sound_enabled = True

    def notify(self, title: str, message: str, sound: bool = True):
        self.sound_enabled = sound
        if sys.platform == "win32" and WIN11TOAST_AVAILABLE:
            try:
                kwargs = {}
                if self.icon_path:
                    kwargs["icon"] = self.icon_path
                if not sound:
                    kwargs["audio"] = {"silent": "true"}
                _win11_toast(title, message, **kwargs)
                return
            except Exception as e:  # noqa: BLE001
                logger.warning("win11toast failed, falling back to tray: %s", e)

        # Fallback: системный трей
        if self.tray_icon is not None:
            try:
                from PyQt6.QtWidgets import QSystemTrayIcon
                self.tray_icon.showMessage(
                    title, message, QSystemTrayIcon.MessageIcon.Information, 8000
                )
            except Exception as e:  # noqa: BLE001
                logger.error("Tray notification failed: %s", e)
        else:
            logger.info("Notification (no backend available): %s - %s", title, message)
