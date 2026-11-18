"""État partagé de l'application (paramètres, base, moteur, IA)."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from ..config import Settings, find_stockfish
from ..db import Database
from ..engine import Engine
from ..training import import_bank


class AppContext(QObject):
    dataChanged = Signal()
    openGame = Signal(int)
    trainTheme = Signal(str)
    openLesson = Signal(str)
    navigate = Signal(str)

    def __init__(self, db: Database | None = None, settings: Settings | None = None):
        super().__init__()
        self.settings = settings or Settings.load()
        self.db = db or Database()
        import_bank(self.db)
        self._quick: Engine | None = None
        self._lock = threading.Lock()

    def stockfish_path(self) -> str | None:
        return find_stockfish(self.settings)

    def quick_engine(self) -> Engine | None:
        """Moteur partagé pour les petites évaluations (exercices, exploration)."""
        with self._lock:
            if self._quick is None:
                path = self.stockfish_path()
                if not path:
                    return None
                try:
                    self._quick = Engine(path, threads=1, hash_mb=64)
                except Exception:
                    return None
            return self._quick

    def reset_engine(self):
        with self._lock:
            if self._quick:
                self._quick.close()
            self._quick = None

    def ai_coach(self):
        if not self.settings.use_ai_coach or not self.settings.api_key():
            return None
        try:
            from ..llm import AICoach
            return AICoach(self.settings.api_key(), self.settings.current_elo, self.settings.target_elo)
        except Exception:
            return None

    def shutdown(self):
        self.reset_engine()
        self.db.close()
