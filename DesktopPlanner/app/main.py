"""
main.py
Точка входа приложения. Настраивает single-instance lock, БД, синхронизацию,
системный трей и главное окно.
"""
import sys
import logging

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from config import Settings, LOG_PATH, ICON_PATH, APP_NAME
from db import Database
from sync import SyncThread
from tray import TrayIcon
from single_instance import SingleInstanceGuard
from main_window import MainWindow


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Запуск %s", APP_NAME)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)

    # --- Single instance lock ---
    guard = SingleInstanceGuard()
    if not guard.try_acquire():
        logger.info("Экземпляр уже запущен — передаём сигнал показа и выходим.")
        sys.exit(0)

    # --- Иконка приложения ---
    if ICON_PATH.exists():
        icon = QIcon(str(ICON_PATH))
    else:
        icon = app.style().standardIcon(app.style().StandardPixmap.SP_ComputerIcon)

    settings = Settings()
    db = Database()

    sync_thread = SyncThread(db, settings)

    tray_icon = TrayIcon(icon)
    tray_icon.show()

    window = MainWindow(settings, db, sync_thread, tray_icon, app)

    guard.show_requested.connect(window.toggle_visibility)
    tray_icon.show_hide_requested.connect(window.toggle_visibility)
    tray_icon.sync_now_requested.connect(window.sync_now)
    tray_icon.settings_requested.connect(window.open_settings)

    def do_quit():
        window._save_geometry()
        sync_thread.stop()
        sync_thread.wait(2000)
        db.close()
        app.quit()

    tray_icon.quit_requested.connect(do_quit)

    sync_thread.start()
    window.show()

    exit_code = app.exec()
    sync_thread.stop()
    sync_thread.wait(2000)
    db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
