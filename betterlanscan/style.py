"""Dark theme stylesheet for the app."""

QSS = """
* { font-family: 'Helvetica Neue', 'SF Pro Text', Arial; }

QMainWindow, QWidget#root {
    background: #14161c;
    color: #e6e9ef;
}

QTabWidget::pane {
    border: none;
    background: #14161c;
}
QTabBar::tab {
    background: transparent;
    color: #8b93a7;
    padding: 9px 20px;
    margin-right: 4px;
    border: none;
    font-size: 13px;
    font-weight: 600;
}
QTabBar::tab:selected {
    color: #ffffff;
    border-bottom: 2px solid #4c8dff;
}
QTabBar::tab:hover { color: #cdd3e0; }

QLabel { color: #e6e9ef; }
QLabel#title { font-size: 17px; font-weight: 700; }
QLabel#subtle { color: #8b93a7; font-size: 12px; }
QLabel#statLabel { color: #8b93a7; font-size: 11px; font-weight: 600; }
QLabel#statValue { color: #ffffff; font-size: 20px; font-weight: 700; }
QLabel#cardTitle { color: #8b93a7; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#cardBig { color: #ffffff; font-size: 20px; font-weight: 700; }
QComboBox { background:#20242f; border:1px solid #2c3140; border-radius:8px; padding:6px 10px; color:#e6e9ef; }
QComboBox::drop-down { border:none; }
QComboBox QAbstractItemView { background:#1c1f28; border:1px solid #262a36; color:#e6e9ef; selection-background-color:#2a3550; }

QFrame#card {
    background: #1c1f28;
    border: 1px solid #262a36;
    border-radius: 12px;
}
QFrame#statChip {
    background: #1c1f28;
    border: 1px solid #262a36;
    border-radius: 10px;
}

QLineEdit {
    background: #20242f;
    border: 1px solid #2c3140;
    border-radius: 8px;
    padding: 7px 10px;
    color: #e6e9ef;
    selection-background-color: #4c8dff;
}
QLineEdit:focus { border: 1px solid #4c8dff; }

QPushButton {
    background: #20242f;
    border: 1px solid #2c3140;
    border-radius: 8px;
    padding: 7px 16px;
    color: #e6e9ef;
    font-weight: 600;
}
QPushButton:hover { background: #272c3a; }
QPushButton:pressed { background: #2e3344; }
QPushButton:disabled { color: #5a6075; }

QPushButton#primary {
    background: #4c8dff;
    border: 1px solid #4c8dff;
    color: #ffffff;
}
QPushButton#primary:hover { background: #5d99ff; }
QPushButton#primary:disabled { background: #2c3548; border-color: #2c3548; color: #6b7488; }

QPushButton#danger { background: #ff5d5d; border-color: #ff5d5d; color: #fff; }
QPushButton#danger:hover { background: #ff7070; }

QCheckBox { color: #cdd3e0; spacing: 6px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #3a4155; background: #20242f;
}
QCheckBox::indicator:checked { background: #4c8dff; border-color: #4c8dff; }

QProgressBar {
    background: #20242f;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk { background: #4c8dff; border-radius: 4px; }

QTableWidget {
    background: #1c1f28;
    alternate-background-color: #1f232e;
    border: 1px solid #262a36;
    border-radius: 10px;
    gridline-color: transparent;
    color: #e6e9ef;
    selection-background-color: #2a3550;
    selection-color: #ffffff;
}
QTableWidget::item { padding: 6px 8px; border: none; }
QHeaderView::section {
    background: #181b23;
    color: #8b93a7;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #262a36;
    font-weight: 700;
    font-size: 11px;
}
QTableCornerButton::section { background: #181b23; border: none; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #353b4d; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #434a5e; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #353b4d; border-radius: 5px; min-width: 30px; }

QStatusBar { background: #181b23; color: #8b93a7; }
QToolTip { background: #20242f; color: #e6e9ef; border: 1px solid #2c3140; padding: 6px; }
"""
