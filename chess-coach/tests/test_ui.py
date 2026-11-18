"""Test de fumée de l'interface (mode hors-écran) : chaque page s'ouvre et réagit."""
import time

import chess
import pytest

pytest.importorskip("PySide6")


def _pump(app, n=10):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


def test_main_window(engine, tmp_path, monkeypatch):
    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication

    from coach.config import Settings
    from coach.db import Database
    from coach.service import analyse_and_store
    from coach.ui.context import AppContext
    from coach.ui.main_window import MainWindow
    from coach.ui.theme import STYLESHEET
    from tests.test_analysis import _load

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLESHEET)
    s = Settings(chesscom_username="MonPseudo", analysis_depth=10, analysis_time=0.1, engine_threads=1)
    monkeypatch.setattr(Settings, "save", lambda self: None)
    db = Database(tmp_path / "ui.db")
    gid = analyse_and_store(db, s, _load("sample_game.pgn"), played_at=1, user_rating=431)
    ctx = AppContext(db=db, settings=s)
    win = MainWindow(ctx)
    win.show()
    _pump(app)
    for key in ("dashboard", "games", "review", "training", "lessons", "screen", "settings"):
        win.go(key)
        _pump(app, 3)
    # Analyse : navigation et variantes
    win._open_game(gid)
    rv = win.review
    assert rv.ply > 0 and rv._current_move().is_error
    rv.go_first()
    assert rv.ply == 0
    rv.go_last()
    assert rv.board.board.is_checkmate()
    rv.next_error()
    rv.show_best_line()
    assert rv.var_base is not None
    rv.go_next()
    rv.exit_variation()
    assert rv.var_base is None
    # Exploration libre : jouer un coup sur l'échiquier
    rv.go_to(0)
    rv._on_user_move(chess.Move.from_uci("d2d4"))
    assert rv.var_moves == [chess.Move.from_uci("d2d4")]
    # Entraînement : une série démarre et un indice s'affiche
    win._train("")
    tr = win.training
    assert tr.exercises and tr.ex is not None
    tr.hint()
    tr.hint()
    tr.show_solution()
    tr.next_exercise()
    # Leçons
    win._lesson("fourchette")
    assert win.lessons.lesson.id == "fourchette"
    win.lessons._step(1)
    QThreadPool.globalInstance().waitForDone(5000)
    win.dashboard.refresh()
    win.close()
    _pump(app)
