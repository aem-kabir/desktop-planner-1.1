"""
config.py
Константы приложения и работа с файлом настроек JSON.
Хранится в %LocalAppData%\\DesktopPlanner\\settings.json
"""
import json
import os
import sys
import copy
from pathlib import Path

APP_NAME = "DesktopPlanner"
APP_DISPLAY_NAME = "Планер задач"
ORG_NAME = "DesktopPlanner"

# ---------------------------------------------------------------------------
# Пути
# ---------------------------------------------------------------------------

def get_local_appdata_dir() -> Path:
    """
    Возвращает %LocalAppData%\\DesktopPlanner на Windows.
    На других ОС (для разработки/тестов) — аналог в домашней папке.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = os.path.expanduser("~\\AppData\\Local")
    else:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


APP_DATA_DIR = get_local_appdata_dir()
SETTINGS_PATH = APP_DATA_DIR / "settings.json"
DB_PATH = APP_DATA_DIR / "planner.db"
LOG_PATH = APP_DATA_DIR / "planner.log"

# Путь к каталогу приложения (для иконок и т.п.), учитывая PyInstaller onefile
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys._MEIPASS)  # noqa: SLF001
    EXE_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).resolve().parent
    EXE_DIR = APP_DIR

ASSETS_DIR = APP_DIR / "assets"
ICON_PATH = ASSETS_DIR / "icon.ico"
ICON_PNG_PATH = ASSETS_DIR / "icon.png"

# ---------------------------------------------------------------------------
# Дефолтные настройки
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "google_sheets": {
        "credentials_path": "",
        "spreadsheet_id": "",
        "sheet_name": "Tasks",
    },
    "personalization": {
        "theme": "System",          # Light / Dark / System
        "always_on_top": False,
        "opacity": 100,             # 20-100
        "snap_to_edges": True,
    },
    "system": {
        "autostart": False,
        "sync_interval_sec": 30,    # 15 - 300
        "close_to_tray": True,
        "window_geometry": None,    # [x, y, w, h]
    },
    "notifications": {
        "enabled": True,
        "sound": True,
        "offsets_minutes": [120, 60, 15],
    },
    "meta": {
        "settings_version": 1,
    },
}

STATUS_VALUES = ["Active", "Completed", "Canceled"]
PRIORITY_VALUES = ["High", "Medium", "Low"]
DEFAULT_STATUS = "Active"
DEFAULT_PRIORITY = "Medium"

SHEET_HEADERS = [
    "ID",
    "Title",
    "Description",
    "StartDate",
    "DeadlineDate",
    "DeadlineTime",
    "Status",
    "Priority",
    "Assignee",
    "UpdatedAt",
]


def _deep_merge(default: dict, override: dict) -> dict:
    """Рекурсивно дополняет default значениями из override, сохраняя
    структуру по умолчанию (защита от повреждённого/неполного файла)."""
    result = copy.deepcopy(default)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Settings:
    """Обёртка над JSON-настройками с автосохранением по требованию."""

    def __init__(self):
        self._data = self.load()

    @staticmethod
    def load() -> dict:
        if SETTINGS_PATH.exists():
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                return _deep_merge(DEFAULT_SETTINGS, raw)
            except (json.JSONDecodeError, OSError):
                # Повреждённый файл — используем дефолты, не роняем приложение
                return copy.deepcopy(DEFAULT_SETTINGS)
        return copy.deepcopy(DEFAULT_SETTINGS)

    def save(self):
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = SETTINGS_PATH.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(SETTINGS_PATH)

    def get(self, *keys, default=None):
        node = self._data
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    def set(self, *keys_and_value):
        """set('personalization', 'theme', 'Dark')"""
        *keys, value = keys_and_value
        node = self._data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value

    @property
    def data(self) -> dict:
        return self._data
