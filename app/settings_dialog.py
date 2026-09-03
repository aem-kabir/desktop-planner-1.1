"""
settings_dialog.py
Окно настроек: Google Sheets, Персонализация, Система, Уведомления.
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QCheckBox, QSlider, QSpinBox,
    QFileDialog, QMessageBox, QTabWidget, QWidget, QListWidget,
    QListWidgetItem, QInputDialog
)

from config import Settings
from autostart import set_autostart, is_autostart_enabled
from sync import SyncEngine, extract_spreadsheet_id
from db import Database


class SettingsDialog(QDialog):
    settings_saved = pyqtSignal()

    def __init__(self, settings: Settings, db: Database, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.db = db
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(480)
        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------
    def _build_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_sheets_tab(), "Google Sheets")
        self.tabs.addTab(self._build_personalization_tab(), "Персонализация")
        self.tabs.addTab(self._build_system_tab(), "Система")
        self.tabs.addTab(self._build_notifications_tab(), "Уведомления")

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()
        self.save_btn = QPushButton("Сохранить")
        self.save_btn.clicked.connect(self._on_save)
        self.close_btn = QPushButton("Закрыть")
        self.close_btn.setObjectName("SecondaryButton")
        self.close_btn.clicked.connect(self.close)
        buttons_row.addWidget(self.close_btn)
        buttons_row.addWidget(self.save_btn)
        layout.addLayout(buttons_row)

    # --- Вкладка Google Sheets ------------------------------------------------
    def _build_sheets_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        cred_row = QHBoxLayout()
        self.credentials_edit = QLineEdit()
        self.credentials_edit.setPlaceholderText("Путь к credentials.json")
        browse_btn = QPushButton("Обзор…")
        browse_btn.setObjectName("SecondaryButton")
        browse_btn.clicked.connect(self._browse_credentials)
        cred_row.addWidget(self.credentials_edit)
        cred_row.addWidget(browse_btn)
        form.addRow("credentials.json:", cred_row)

        help_label = QLabel(
            "credentials.json — это файл-ключ сервисного аккаунта Google.\n"
            "Он позволяет приложению входить в Google Sheets автоматически,\n"
            "без открытия браузера и ручного логина. Как его получить — см.\n"
            "инструкцию SETUP_GOOGLE_SHEETS.md, приложенную к проекту."
        )
        help_label.setStyleSheet("color: gray; font-size: 11px;")
        help_label.setWordWrap(True)
        form.addRow(help_label)

        self.spreadsheet_id_edit = QLineEdit()
        self.spreadsheet_id_edit.setPlaceholderText("ID таблицы или полная ссылка на неё")
        form.addRow("Spreadsheet ID / ссылка:", self.spreadsheet_id_edit)

        self.sheet_name_edit = QLineEdit()
        self.sheet_name_edit.setPlaceholderText("Tasks")
        form.addRow("Название листа:", self.sheet_name_edit)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton("Проверить подключение")
        self.test_btn.clicked.connect(self._test_connection)
        self.test_result_label = QLabel("")
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_result_label, stretch=1)
        form.addRow(test_row)

        return w

    def _browse_credentials(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите credentials.json", "", "JSON файлы (*.json)"
        )
        if path:
            self.credentials_edit.setText(path)

    def _test_connection(self):
        self._apply_sheets_values_to_settings_temp()
        engine = SyncEngine(self.db, self.settings)
        self.test_btn.setEnabled(False)
        self.test_result_label.setText("Проверка…")
        try:
            result = engine.test_connection()
        finally:
            self.test_btn.setEnabled(True)
        if result.ok:
            self.test_result_label.setText("✅ Подключение успешно")
            self.test_result_label.setStyleSheet("color: green;")
        else:
            self.test_result_label.setText(f"❌ Ошибка: {result.error[:200]}")
            self.test_result_label.setStyleSheet("color: red;")

    def _apply_sheets_values_to_settings_temp(self):
        """Применяет значения формы во временный объект настроек, чтобы
        SyncEngine мог использовать их для тестового подключения без
        обязательного нажатия 'Сохранить'."""
        self.settings.set("google_sheets", "credentials_path", self.credentials_edit.text().strip())
        self.settings.set(
            "google_sheets", "spreadsheet_id",
            extract_spreadsheet_id(self.spreadsheet_id_edit.text().strip())
        )
        self.settings.set(
            "google_sheets", "sheet_name",
            self.sheet_name_edit.text().strip() or "Tasks"
        )

    # --- Вкладка Персонализация -------------------------------------------
    def _build_personalization_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "System"])
        form.addRow("Тема:", self.theme_combo)

        self.always_on_top_check = QCheckBox("Поверх всех окон")
        form.addRow(self.always_on_top_check)

        opacity_row = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_value_label = QLabel("100%")
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_value_label.setText(f"{v}%")
        )
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_value_label)
        form.addRow("Прозрачность окна:", opacity_row)

        self.snap_check = QCheckBox("Прилипание к краям экрана")
        form.addRow(self.snap_check)

        return w

    # --- Вкладка Система ---------------------------------------------------
    def _build_system_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self.autostart_check = QCheckBox("Запускать при старте Windows")
        form.addRow(self.autostart_check)

        self.sync_interval_spin = QSpinBox()
        self.sync_interval_spin.setRange(15, 300)
        self.sync_interval_spin.setSuffix(" сек")
        form.addRow("Интервал синхронизации:", self.sync_interval_spin)

        self.close_to_tray_check = QCheckBox("Сворачивать в трей при нажатии [X]")
        form.addRow(self.close_to_tray_check)

        reset_pos_btn = QPushButton("Сбросить позицию окна")
        reset_pos_btn.setObjectName("SecondaryButton")
        reset_pos_btn.clicked.connect(self._reset_window_position)
        form.addRow(reset_pos_btn)

        return w

    def _reset_window_position(self):
        self.settings.set("system", "window_geometry", None)
        QMessageBox.information(self, "Готово", "Позиция окна будет сброшена после перезапуска.")

    # --- Вкладка Уведомления -------------------------------------------------
    def _build_notifications_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        self.notif_enabled_check = QCheckBox("Включить уведомления")
        layout.addWidget(self.notif_enabled_check)

        self.notif_sound_check = QCheckBox("Звук")
        layout.addWidget(self.notif_sound_check)

        layout.addWidget(QLabel("Тайминги (за сколько минут до дедлайна напоминать):"))
        self.offsets_list = QListWidget()
        layout.addWidget(self.offsets_list)

        offset_buttons = QHBoxLayout()
        add_offset_btn = QPushButton("Добавить")
        add_offset_btn.setObjectName("SecondaryButton")
        add_offset_btn.clicked.connect(self._add_offset)
        remove_offset_btn = QPushButton("Удалить выбранный")
        remove_offset_btn.setObjectName("SecondaryButton")
        remove_offset_btn.clicked.connect(self._remove_offset)
        offset_buttons.addWidget(add_offset_btn)
        offset_buttons.addWidget(remove_offset_btn)
        layout.addLayout(offset_buttons)

        return w

    def _add_offset(self):
        value, ok = QInputDialog.getInt(
            self, "Новый тайминг", "За сколько минут до дедлайна напоминать:", 30, 1, 10080
        )
        if ok:
            item = QListWidgetItem(f"{value} мин")
            item.setData(Qt.ItemDataRole.UserRole, value)
            self.offsets_list.addItem(item)

    def _remove_offset(self):
        for item in self.offsets_list.selectedItems():
            self.offsets_list.takeItem(self.offsets_list.row(item))

    # ------------------------------------------------------------------
    def _load_values(self):
        gs = self.settings.get("google_sheets", default={})
        self.credentials_edit.setText(gs.get("credentials_path", ""))
        self.spreadsheet_id_edit.setText(gs.get("spreadsheet_id", ""))
        self.sheet_name_edit.setText(gs.get("sheet_name", "Tasks"))

        p = self.settings.get("personalization", default={})
        self.theme_combo.setCurrentText(p.get("theme", "System"))
        self.always_on_top_check.setChecked(p.get("always_on_top", False))
        self.opacity_slider.setValue(int(p.get("opacity", 100)))
        self.snap_check.setChecked(p.get("snap_to_edges", True))

        s = self.settings.get("system", default={})
        self.autostart_check.setChecked(is_autostart_enabled())
        self.sync_interval_spin.setValue(int(s.get("sync_interval_sec", 30)))
        self.close_to_tray_check.setChecked(s.get("close_to_tray", True))

        n = self.settings.get("notifications", default={})
        self.notif_enabled_check.setChecked(n.get("enabled", True))
        self.notif_sound_check.setChecked(n.get("sound", True))
        self.offsets_list.clear()
        for minutes in n.get("offsets_minutes", [120, 60, 15]):
            item = QListWidgetItem(f"{minutes} мин")
            item.setData(Qt.ItemDataRole.UserRole, minutes)
            self.offsets_list.addItem(item)

    def _on_save(self):
        self.settings.set("google_sheets", "credentials_path", self.credentials_edit.text().strip())
        self.settings.set(
            "google_sheets", "spreadsheet_id",
            extract_spreadsheet_id(self.spreadsheet_id_edit.text().strip())
        )
        self.settings.set("google_sheets", "sheet_name", self.sheet_name_edit.text().strip() or "Tasks")

        self.settings.set("personalization", "theme", self.theme_combo.currentText())
        self.settings.set("personalization", "always_on_top", self.always_on_top_check.isChecked())
        self.settings.set("personalization", "opacity", self.opacity_slider.value())
        self.settings.set("personalization", "snap_to_edges", self.snap_check.isChecked())

        self.settings.set("system", "sync_interval_sec", self.sync_interval_spin.value())
        self.settings.set("system", "close_to_tray", self.close_to_tray_check.isChecked())

        autostart_wanted = self.autostart_check.isChecked()
        ok = set_autostart(autostart_wanted)
        self.settings.set("system", "autostart", autostart_wanted if ok else is_autostart_enabled())
        if not ok:
            QMessageBox.warning(self, "Автозагрузка", "Не удалось изменить настройку автозагрузки в реестре.")

        self.settings.set("notifications", "enabled", self.notif_enabled_check.isChecked())
        self.settings.set("notifications", "sound", self.notif_sound_check.isChecked())
        offsets = []
        for i in range(self.offsets_list.count()):
            offsets.append(self.offsets_list.item(i).data(Qt.ItemDataRole.UserRole))
        self.settings.set("notifications", "offsets_minutes", sorted(set(offsets), reverse=True))

        self.settings.save()
        self.settings_saved.emit()
        QMessageBox.information(self, "Настройки", "Настройки сохранены.")
