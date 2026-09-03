"""
autostart.py
Автозагрузка через реестр HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
Не требует прав администратора, т.к. пишет в ветку текущего пользователя (HKCU).
"""
import sys
import os

from config import APP_NAME

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_exe_command() -> str:
    """
    Возвращает команду для автозапуска.
    - Если приложение собрано PyInstaller-ом (frozen) — путь к .exe.
    - Если запущено из исходников — 'python.exe main.py' с абсолютными путями
      (полезно при разработке/отладке, в собранной версии не используется).
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.abspath(sys.argv[0])
    return f'"{sys.executable}" "{script}"'


def is_autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            try:
                winreg.QueryValueEx(key, APP_NAME)
                return True
            except FileNotFoundError:
                return False
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """Возвращает True при успехе. На не-Windows платформах — no-op (True),
    чтобы не ронять разработку/тесты."""
    if sys.platform != "win32":
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _get_exe_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def get_system_theme() -> str:
    """
    Определяет системную тему Windows через реестр:
    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize
    AppsUseLightTheme: 1 = светлая, 0 = тёмная.
    На не-Windows или при ошибке возвращает 'Light' по умолчанию.
    """
    if sys.platform != "win32":
        return "Light"
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "Light" if value == 1 else "Dark"
    except OSError:
        return "Light"
