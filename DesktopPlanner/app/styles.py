"""
styles.py
QSS-стили для тем Light / Dark. Тема System резолвится вызывающим кодом
через autostart.get_system_theme() в 'Light' или 'Dark' перед вызовом get_stylesheet().
"""

COLOR_HIGH = "#e74c3c"
COLOR_MEDIUM = "#f39c12"
COLOR_LOW = "#2ecc71"

DEADLINE_YELLOW = "#fff3b0"
DEADLINE_RED = "#ffb3b3"
DEADLINE_RED_DARK = "#5c2323"
DEADLINE_YELLOW_DARK = "#5c5323"

LIGHT = {
    "bg": "#f5f6fa",
    "bg_alt": "#ffffff",
    "fg": "#202124",
    "fg_muted": "#6b6f76",
    "border": "#dcdfe4",
    "accent": "#3d7eff",
    "accent_hover": "#2f68e0",
    "header_bg": "#eef0f5",
    "card_bg": "#ffffff",
    "card_hover": "#f0f4ff",
    "danger": "#e74c3c",
    "success": "#27ae60",
    "overdue_bg": "#ffe5e5",
    "deadline_yellow": DEADLINE_YELLOW,
    "deadline_red": DEADLINE_RED,
}

DARK = {
    "bg": "#1e1f22",
    "bg_alt": "#2b2d31",
    "fg": "#e3e5e8",
    "fg_muted": "#9aa0a6",
    "border": "#3a3d42",
    "accent": "#5c9bff",
    "accent_hover": "#4a89f5",
    "header_bg": "#26282c",
    "card_bg": "#2b2d31",
    "card_hover": "#33363b",
    "danger": "#ff6b6b",
    "success": "#4dd07f",
    "overdue_bg": "#3a2323",
    "deadline_yellow": DEADLINE_YELLOW_DARK,
    "deadline_red": DEADLINE_RED_DARK,
}


def get_palette(theme: str) -> dict:
    return DARK if theme == "Dark" else LIGHT


def get_stylesheet(theme: str) -> str:
    p = get_palette(theme)
    return f"""
    QWidget {{
        background-color: {p['bg']};
        color: {p['fg']};
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 13px;
    }}

    QWidget#TitleBar {{
        background-color: {p['header_bg']};
        border-bottom: 1px solid {p['border']};
    }}
    QLabel#TitleLabel {{
        font-weight: 600;
        font-size: 13px;
        color: {p['fg']};
    }}
    QPushButton#TitleBarButton {{
        background: transparent;
        border: none;
        border-radius: 4px;
        color: {p['fg']};
        font-size: 14px;
        min-width: 32px;
        min-height: 28px;
    }}
    QPushButton#TitleBarButton:hover {{
        background-color: {p['card_hover']};
    }}
    QPushButton#TitleBarCloseButton:hover {{
        background-color: {p['danger']};
        color: white;
    }}

    QTabWidget::pane {{
        border: 1px solid {p['border']};
        background-color: {p['bg']};
        border-radius: 6px;
    }}
    QTabBar::tab {{
        background-color: {p['header_bg']};
        color: {p['fg_muted']};
        padding: 8px 16px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background-color: {p['bg_alt']};
        color: {p['fg']};
        font-weight: 600;
    }}

    QPushButton {{
        background-color: {p['accent']};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 14px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {p['accent_hover']};
    }}
    QPushButton:disabled {{
        background-color: {p['border']};
        color: {p['fg_muted']};
    }}
    QPushButton#SecondaryButton {{
        background-color: transparent;
        color: {p['fg']};
        border: 1px solid {p['border']};
    }}
    QPushButton#SecondaryButton:hover {{
        background-color: {p['card_hover']};
    }}
    QPushButton#DangerButton {{
        background-color: {p['danger']};
    }}
    QPushButton#SuccessButton {{
        background-color: {p['success']};
    }}
    QPushButton#AddButton {{
        border-radius: 20px;
        font-size: 20px;
        font-weight: bold;
        min-width: 40px;
        min-height: 40px;
        max-width: 40px;
        max-height: 40px;
    }}

    QFrame#TaskCard {{
        background-color: {p['card_bg']};
        border: 1px solid {p['border']};
        border-radius: 8px;
    }}
    QFrame#TaskCard:hover {{
        background-color: {p['card_hover']};
    }}
    QFrame#TaskCardOverdue {{
        background-color: {p['overdue_bg']};
        border: 1px solid {p['danger']};
        border-radius: 8px;
    }}
    QFrame#TaskCardWarnYellow {{
        background-color: {p['deadline_yellow']};
        border: 1px solid {p['border']};
        border-radius: 8px;
    }}
    QFrame#TaskCardWarnRed {{
        background-color: {p['deadline_red']};
        border: 1px solid {p['danger']};
        border-radius: 8px;
    }}

    QLineEdit, QTextEdit, QPlainTextEdit, QDateEdit, QTimeEdit, QComboBox, QSpinBox {{
        background-color: {p['bg_alt']};
        border: 1px solid {p['border']};
        border-radius: 5px;
        padding: 4px 8px;
        color: {p['fg']};
    }}
    QComboBox::drop-down {{
        border: none;
    }}
    QCheckBox {{
        spacing: 8px;
    }}
    QScrollArea {{
        border: none;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
    }}
    QScrollBar::handle:vertical {{
        background: {p['border']};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p['fg_muted']};
    }}

    QLabel#PriorityHigh {{ color: {COLOR_HIGH}; font-weight: 600; }}
    QLabel#PriorityMedium {{ color: {COLOR_MEDIUM}; font-weight: 600; }}
    QLabel#PriorityLow {{ color: {COLOR_LOW}; font-weight: 600; }}

    QLabel#SectionHeader {{
        font-weight: 700;
        font-size: 14px;
        color: {p['fg']};
        padding: 4px 0;
    }}
    QLabel#OverdueHeader {{
        font-weight: 700;
        font-size: 14px;
        color: {p['danger']};
        padding: 4px 0;
    }}

    QWidget#CompactBar {{
        background-color: {p['header_bg']};
        border: 1px solid {p['border']};
        border-radius: 16px;
    }}

    QDialog {{
        background-color: {p['bg']};
    }}
    QGroupBox {{
        border: 1px solid {p['border']};
        border-radius: 6px;
        margin-top: 10px;
        padding-top: 12px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }}
    """
