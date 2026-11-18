"""Thème sombre de l'application."""

BG = "#1e1f22"
PANEL = "#2b2d31"
PANEL2 = "#313338"
BORDER = "#3c3f45"
TEXT = "#e6e6e6"
MUTED = "#a3a6ad"
ACCENT = "#81b64c"      # vert « échiquier »
ACCENT2 = "#5aa9ff"
GOOD = "#5dbb63"
WARN = "#f0c15c"
BAD = "#e0533d"

STYLESHEET = f"""
* {{ font-family: "Segoe UI", "Inter", "DejaVu Sans", sans-serif; font-size: 14px; color: {TEXT}; }}
QMainWindow, QWidget#page, QStackedWidget {{ background: {BG}; }}
QWidget#sidebar {{ background: #17181b; border-right: 1px solid {BORDER}; }}
QPushButton#nav {{ text-align: left; padding: 11px 18px; border: none; border-radius: 8px; color: {MUTED};
                   font-size: 15px; margin: 2px 10px; }}
QPushButton#nav:hover {{ background: {PANEL}; color: {TEXT}; }}
QPushButton#nav:checked {{ background: {PANEL2}; color: {TEXT}; font-weight: 600; border-left: 3px solid {ACCENT}; }}
QLabel#appTitle {{ font-size: 19px; font-weight: 700; padding: 18px 18px 4px 18px; }}
QLabel#appSub {{ color: {MUTED}; padding: 0 18px 14px 18px; font-size: 12px; }}
QLabel#h1 {{ font-size: 24px; font-weight: 700; }}
QLabel#h2 {{ font-size: 17px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#statValue {{ font-size: 28px; font-weight: 700; }}
QLabel#statLabel {{ color: {MUTED}; font-size: 12px; }}
QPushButton {{ background: {PANEL2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 14px; }}
QPushButton:hover {{ background: #3a3d44; }}
QPushButton:disabled {{ color: #6b6e75; }}
QPushButton#primary {{ background: {ACCENT}; border: none; color: #10210a; font-weight: 700; }}
QPushButton#primary:hover {{ background: #95c95f; }}
QPushButton#primary:disabled {{ background: #4a5a3c; color: #2a2f25; }}
QPushButton#icon {{ padding: 6px 10px; font-size: 16px; min-width: 34px; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{ background: {PANEL2}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 6px 8px; selection-background-color: {ACCENT2}; }}
QComboBox QAbstractItemView {{ background: {PANEL2}; }}
QTextBrowser {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; padding: 10px; }}
QTableWidget, QListWidget, QTreeWidget {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px;
    gridline-color: {BORDER}; alternate-background-color: #2f3136; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: #3d4a5c; }}
QListWidget::item {{ padding: 8px; border-radius: 6px; }}
QHeaderView::section {{ background: {PANEL2}; border: none; padding: 6px; color: {MUTED}; }}
QProgressBar {{ background: {PANEL2}; border: none; border-radius: 6px; height: 12px; text-align: center; font-size: 11px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 8px 14px; color: {MUTED}; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #4a4d55; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QToolTip {{ background: {PANEL2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; }}
QSplitter::handle {{ background: {BG}; }}
"""
