def load_styles() -> str:
    return """
/* === GLOBAL === */
* {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: #FFFFFF;
    outline: none;
}

QMainWindow, QDialog {
    background-color: #0F0F0F;
}

QWidget {
    background-color: #1A1A1A;
}

/* === SPLITTERS === */
QSplitter::handle {
    background-color: #2A2A2A;
    width: 2px;
    height: 2px;
}
QSplitter::handle:hover {
    background-color: #6C3BE4;
}

/* === SCROLLBARS === */
QScrollBar:vertical {
    background: #1A1A1A;
    width: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #444444;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #666666; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal {
    background: #1A1A1A;
    height: 8px;
    border-radius: 4px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #444444;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover { background: #666666; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; border: none; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

/* === TABLE === */
QTableWidget {
    background-color: #1A1A1A;
    alternate-background-color: #1F1F1F;
    gridline-color: #2D2D2D;
    selection-background-color: #3D2B6B;
    selection-color: #FFFFFF;
    border: 1px solid #2D2D2D;
    border-radius: 4px;
}
QTableWidget::item {
    padding: 4px 8px;
    border: none;
}
QTableWidget::item:hover { background-color: #2E2E2E; }
QTableWidget::item:selected { background-color: #3D2B6B; }
QHeaderView::section {
    background-color: #242424;
    color: #888888;
    border: none;
    border-bottom: 1px solid #333333;
    border-right: 1px solid #333333;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: 600;
}
QHeaderView::section:hover { background-color: #2E2E2E; color: #CCCCCC; }
QHeaderView { background-color: #242424; }

/* === BUTTONS === */
QPushButton {
    background-color: #2D2D2D;
    border: 1px solid #3D3D3D;
    border-radius: 5px;
    padding: 6px 14px;
    color: #FFFFFF;
    font-weight: 500;
    min-height: 28px;
}
QPushButton:hover { background-color: #383838; border-color: #555555; }
QPushButton:pressed { background-color: #242424; }
QPushButton:disabled { background-color: #1F1F1F; color: #555555; border-color: #2A2A2A; }

QPushButton[role="primary"] {
    background-color: #6C3BE4;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: 700;
    font-size: 13px;
}
QPushButton[role="primary"]:hover { background-color: #7B4CF0; }
QPushButton[role="primary"]:pressed { background-color: #5530C0; }

QPushButton[role="danger"] {
    background-color: #C0392B;
    border: none;
    border-radius: 5px;
}
QPushButton[role="danger"]:hover { background-color: #E74C3C; }

QPushButton[role="success"] {
    background-color: #1E8449;
    border: none;
    border-radius: 5px;
}
QPushButton[role="success"]:hover { background-color: #27AE60; }

QPushButton[role="ghost"] {
    background-color: transparent;
    border: 1px solid #444444;
    border-radius: 5px;
    color: #AAAAAA;
}
QPushButton[role="ghost"]:hover { border-color: #6C3BE4; color: #FFFFFF; background-color: #2A2A2A; }

/* === INPUTS === */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #242424;
    border: 1px solid #383838;
    border-radius: 5px;
    padding: 6px 10px;
    color: #FFFFFF;
    selection-background-color: #6C3BE4;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #6C3BE4;
    background-color: #2A2424;
}
QLineEdit:disabled, QTextEdit:disabled { color: #555555; background-color: #1F1F1F; }

/* === COMBOBOX === */
QComboBox {
    background-color: #242424;
    border: 1px solid #383838;
    border-radius: 5px;
    padding: 5px 10px;
    color: #FFFFFF;
    min-height: 28px;
}
QComboBox:hover { border-color: #555555; }
QComboBox:focus { border-color: #6C3BE4; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background-color: #2A2A2A;
    border: 1px solid #444444;
    border-radius: 4px;
    selection-background-color: #6C3BE4;
    outline: none;
    padding: 4px;
}
QComboBox QAbstractItemView::item { padding: 5px 8px; border-radius: 3px; }

/* === SLIDERS === */
QSlider::groove:horizontal {
    height: 4px;
    background: #333333;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #6C3BE4;
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover { background: #7B4CF0; }
QSlider::sub-page:horizontal { background: #6C3BE4; border-radius: 2px; }
QSlider::groove:vertical {
    width: 4px;
    background: #333333;
    border-radius: 2px;
}
QSlider::handle:vertical {
    background: #6C3BE4;
    border: none;
    width: 14px;
    height: 14px;
    margin: 0 -5px;
    border-radius: 7px;
}
QSlider::sub-page:vertical { background: #6C3BE4; border-radius: 2px; }

/* === TABS === */
QTabWidget::pane {
    background-color: #1A1A1A;
    border: 1px solid #2D2D2D;
    border-radius: 0 5px 5px 5px;
}
QTabBar::tab {
    background-color: #242424;
    color: #888888;
    padding: 7px 16px;
    border: 1px solid #2D2D2D;
    border-bottom: none;
    border-radius: 5px 5px 0 0;
    margin-right: 2px;
    font-size: 12px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background-color: #1A1A1A;
    color: #FFFFFF;
    border-bottom: 2px solid #6C3BE4;
}
QTabBar::tab:hover:!selected { background-color: #2E2E2E; color: #CCCCCC; }

/* === PROGRESS BAR === */
QProgressBar {
    background-color: #242424;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
    max-height: 6px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6C3BE4, stop:1 #9B59B6);
    border-radius: 4px;
}

/* === GROUP BOXES === */
QGroupBox {
    border: 1px solid #2D2D2D;
    border-radius: 6px;
    margin-top: 14px;
    padding: 8px;
    font-size: 11px;
    font-weight: 600;
    color: #888888;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 10px;
    background-color: #1A1A1A;
}

/* === MENU === */
QMenuBar {
    background-color: #0F0F0F;
    border-bottom: 1px solid #2D2D2D;
    padding: 2px;
}
QMenuBar::item { padding: 4px 10px; border-radius: 3px; }
QMenuBar::item:selected { background-color: #2E2E2E; }
QMenu {
    background-color: #1E1E1E;
    border: 1px solid #3D3D3D;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item { padding: 6px 28px 6px 12px; border-radius: 3px; }
QMenu::item:selected { background-color: #3D2B6B; }
QMenu::separator { height: 1px; background: #2D2D2D; margin: 4px 0; }

/* === TOOLBAR === */
QToolBar {
    background-color: #141414;
    border-bottom: 1px solid #2D2D2D;
    spacing: 4px;
    padding: 4px 8px;
}
QToolBar::separator { width: 1px; background: #2D2D2D; margin: 4px 4px; }
QToolButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 5px 10px;
    color: #CCCCCC;
    font-size: 12px;
}
QToolButton:hover { background-color: #2E2E2E; border-color: #3D3D3D; }
QToolButton:pressed { background-color: #242424; }
QToolButton:checked { background-color: #3D2B6B; color: #FFFFFF; border-color: #6C3BE4; }

/* === CHECKBOXES === */
QCheckBox { color: #CCCCCC; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    background-color: #242424;
    border: 1px solid #444444;
    border-radius: 3px;
}
QCheckBox::indicator:checked {
    background-color: #6C3BE4;
    border-color: #6C3BE4;
}
QCheckBox::indicator:hover { border-color: #6C3BE4; }

/* === RADIO BUTTONS === */
QRadioButton { color: #CCCCCC; spacing: 8px; }
QRadioButton::indicator {
    width: 16px; height: 16px;
    background-color: #242424;
    border: 1px solid #444444;
    border-radius: 8px;
}
QRadioButton::indicator:checked {
    background-color: #6C3BE4;
    border-color: #6C3BE4;
}

/* === SPIN BOX === */
QSpinBox, QDoubleSpinBox {
    background-color: #242424;
    border: 1px solid #383838;
    border-radius: 5px;
    padding: 5px 8px;
    color: #FFFFFF;
    min-height: 28px;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #6C3BE4; }
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background-color: #333333;
    border: none;
    width: 18px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #444444;
}

/* === STATUS BAR === */
QStatusBar {
    background-color: #0F0F0F;
    border-top: 1px solid #2D2D2D;
    color: #888888;
    font-size: 11px;
    padding: 2px 8px;
}

/* === LABELS === */
QLabel { background-color: transparent; color: #FFFFFF; }
QLabel[role="muted"] { color: #888888; font-size: 11px; }
QLabel[role="title"] { font-size: 15px; font-weight: 700; color: #FFFFFF; }
QLabel[role="accent"] { color: #6C3BE4; font-weight: 600; }
QLabel[role="success"] { color: #2ECC71; }
QLabel[role="warning"] { color: #F39C12; }
QLabel[role="danger"] { color: #E74C3C; }

/* === FRAME === */
QFrame[frameShape="4"], QFrame[frameShape="5"] {
    color: #2D2D2D;
}

/* === PROCESS LOG === */
QTextEdit#process_log {
    background-color: #0A0A0A;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    border: none;
    border-top: 1px solid #2D2D2D;
    padding: 6px;
    color: #CCCCCC;
}

/* === TIMELINE AREA === */
QWidget#timeline_widget {
    background-color: #141414;
    border-top: 2px solid #2D2D2D;
}

/* === PREVIEW AREA === */
QLabel#video_preview {
    background-color: #000000;
    border: 1px solid #2D2D2D;
    border-radius: 4px;
}

/* === CHAT AREA === */
QTextEdit#chat_history {
    background-color: #141414;
    border: 1px solid #2D2D2D;
    border-radius: 6px;
    padding: 8px;
    font-size: 13px;
}

/* === SEPARATOR === */
QWidget#panel_separator {
    background-color: #2D2D2D;
    max-width: 1px;
    max-height: 1px;
}
"""
