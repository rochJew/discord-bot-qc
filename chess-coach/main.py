"""Point d'entrée : lance l'application Chess Coach."""
import sys


def main():
    from PySide6.QtWidgets import QApplication

    from coach.ui.context import AppContext
    from coach.ui.main_window import MainWindow
    from coach.ui.theme import STYLESHEET

    app = QApplication(sys.argv)
    app.setApplicationName("Chess Coach")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    ctx = AppContext()
    win = MainWindow(ctx)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
