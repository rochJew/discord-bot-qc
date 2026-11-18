"""Fenêtre principale : barre latérale + pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .. import __version__
from .context import AppContext
from .dashboard import DashboardPage
from .games import GamesPage
from .lessons_page import LessonsPage
from .review import ReviewPage
from .screen_page import ScreenPage
from .settings_page import SettingsPage
from .training_page import TrainingPage
from .widgets import label


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("Chess Coach — de 430 à 1000 Elo")
        self.resize(1360, 860)
        central = QWidget()
        self.setCentralWidget(central)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(228)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 12)
        sv.setSpacing(2)
        sv.addWidget(label("♞ Chess Coach", "appTitle"))
        sv.addWidget(label("Ton coach d'échecs perso", "appSub"))
        self.stack = QStackedWidget()
        self.pages = {}
        self.dashboard = DashboardPage(ctx)
        self.games = GamesPage(ctx)
        self.review = ReviewPage(ctx)
        self.training = TrainingPage(ctx)
        self.lessons = LessonsPage(ctx)
        self.screen = ScreenPage(ctx, self.games)
        self.settings = SettingsPage(ctx)
        entries = [
            ("dashboard", "🏠  Tableau de bord", self.dashboard),
            ("games", "♟  Mes parties", self.games),
            ("review", "🔍  Analyse", self.review),
            ("training", "🎯  Entraînement", self.training),
            ("lessons", "📘  Leçons", self.lessons),
            ("screen", "🖥  Capture d'écran", self.screen),
            ("settings", "⚙  Paramètres", self.settings),
        ]
        self.group = QButtonGroup(self)
        self.buttons = {}
        for key, text, page in entries:
            b = QPushButton(text)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.group.addButton(b)
            self.buttons[key] = b
            self.pages[key] = page
            self.stack.addWidget(page)
            if key == "lessons":
                sv.addSpacing(6)
            sv.addWidget(b)
        sv.addStretch()
        sv.addWidget(label(f"v{__version__} · analyse Stockfish", "appSub"))
        lay.addWidget(side)
        lay.addWidget(self.stack, 1)

        ctx.dataChanged.connect(self._data_changed)
        ctx.openGame.connect(self._open_game)
        ctx.trainTheme.connect(self._train)
        ctx.openLesson.connect(self._lesson)
        ctx.navigate.connect(self.go)
        self.go("dashboard")
        self.setWindowIcon(QIcon())

    def go(self, key: str):
        self.stack.setCurrentWidget(self.pages[key])
        self.buttons[key].setChecked(True)
        if key == "dashboard":
            self.dashboard.refresh()
        if key == "games":
            self.games.refresh_local()

    def _data_changed(self):
        self.dashboard.refresh()
        self.lessons.refresh_marks()

    def _open_game(self, gid: int):
        self.review.load_game(gid)
        self.go("review")
        self.review.next_error()

    def _train(self, theme_key: str):
        self.go("training")
        self.training.start_session(theme_key or None)

    def _lesson(self, lid: str):
        self.go("lessons")
        self.lessons.open_lesson(lid)

    def closeEvent(self, e):
        self.ctx.shutdown()
        super().closeEvent(e)
