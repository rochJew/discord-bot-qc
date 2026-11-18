"""Page « Entraînement » : exercices personnalisés avec indices progressifs."""
from __future__ import annotations

import chess
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..motifs import THEMES
from ..progress import weakest_themes
from ..training import THEME_HINTS, check_move, select_exercises, solution_explanation
from . import theme
from .board import ChessBoardWidget
from .widgets import Card, label
from .workers import run_task


class TrainingPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("page")
        self.ctx = ctx
        self.exercises = []
        self.idx = -1
        self.step = 0
        self.cur_board: chess.Board | None = None
        self.failed = False
        self.hints = 0
        self.score = 0
        self.done_count = 0
        self.checking = False
        self._recorded = False
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(18)
        left = QVBoxLayout()
        self.title = label("Entraînement", "h1", wrap=True)
        left.addWidget(self.title)
        self.prompt = label("Choisis un programme à droite puis clique sur « Commencer ».", "h2", wrap=True)
        left.addWidget(self.prompt)
        self.board = ChessBoardWidget(interactive=False)
        self.board.moveMade.connect(self.on_move)
        left.addWidget(self.board, 1)
        self.feedback = label("", wrap=True)
        self.feedback.setMinimumHeight(48)
        self.feedback.setStyleSheet(f"background:{theme.PANEL}; border-radius:10px; padding:10px; font-size:15px;")
        left.addWidget(self.feedback)
        row = QHBoxLayout()
        self.btn_hint = QPushButton("💡 Indice")
        self.btn_hint.clicked.connect(self.hint)
        self.btn_sol = QPushButton("Voir la solution")
        self.btn_sol.clicked.connect(self.show_solution)
        self.btn_retry = QPushButton("↺ Réessayer")
        self.btn_retry.clicked.connect(self.retry)
        self.btn_next = QPushButton("Exercice suivant ▶")
        self.btn_next.setObjectName("primary")
        self.btn_next.clicked.connect(self.next_exercise)
        for b in (self.btn_hint, self.btn_sol, self.btn_retry, self.btn_next):
            row.addWidget(b)
        left.addLayout(row)
        root.addLayout(left, 3)

        right = QVBoxLayout()
        card = Card("Programme")
        self.theme_box = QComboBox()
        self.theme_box.addItem("🎯 Personnalisé : mes points faibles", None)
        for k, v in THEMES.items():
            self.theme_box.addItem(v, k)
        card.lay.addWidget(self.theme_box)
        self.focus_lbl = label("", "muted", wrap=True)
        card.lay.addWidget(self.focus_lbl)
        start = QPushButton("Commencer une série de 10 exercices")
        start.setObjectName("primary")
        start.clicked.connect(lambda: self.start_session())
        card.lay.addWidget(start)
        right.addWidget(card)
        self.session_lbl = label("", "h2")
        right.addWidget(self.session_lbl)
        self.queue_list = QListWidget()
        self.queue_list.setMaximumHeight(220)
        self.queue_list.setWordWrap(True)
        right.addWidget(self.queue_list)
        self.explain = QTextBrowser()
        right.addWidget(self.explain, 1)
        root.addLayout(right, 2)
        self._buttons(False)

    def _buttons(self, active: bool, solved: bool = False):
        self.btn_hint.setEnabled(active and not solved)
        self.btn_sol.setEnabled(active and not solved)
        self.btn_retry.setEnabled(active and not solved)
        self.btn_next.setEnabled(bool(self.exercises))

    def showEvent(self, e):
        super().showEvent(e)
        weak = weakest_themes(self.ctx.db, 3)
        self.focus_lbl.setText("Tes priorités du moment : " + ", ".join(THEMES.get(t, t) for t in weak) + ".")

    # ------------------------------------------------------------------ séance
    def start_session(self, theme_key: str | None = "__box__"):
        if theme_key == "__box__":
            theme_key = self.theme_box.currentData()
        else:
            i = self.theme_box.findData(theme_key)
            if i >= 0:
                self.theme_box.setCurrentIndex(i)
        self.exercises = select_exercises(self.ctx.db, 10, theme_key)
        self.idx = -1
        self.score = 0
        self.done_count = 0
        if not self.exercises:
            self.prompt.setText("Pas encore d'exercice pour ce thème. Analyse des parties pour en générer !")
            return
        self.queue_list.clear()
        for ex in self.exercises:
            it = QListWidgetItem(("📌 " if ex.source == "partie" else "🧩 ") + ex.title)
            self.queue_list.addItem(it)
        self.next_exercise()

    def next_exercise(self):
        if not self.exercises:
            self.start_session()
            return
        if self.idx >= 0 and self.ex and not self._recorded:
            self._record(False)
        self.idx += 1
        if self.idx >= len(self.exercises):
            self._end_session()
            return
        ex = self.ex
        self.step = 0
        self.failed = False
        self.hints = 0
        self._recorded = False
        self.cur_board = ex.board
        self.board.interactive = True
        self.board.set_flipped(self.cur_board.turn == chess.BLACK)
        self.board.set_board(self.cur_board, last_move=None)
        self.board.last_move = None
        self.board.set_arrows([])
        self.board.set_highlights({})
        self.board.set_badge(None)
        self.title.setText(ex.title)
        side = "Blancs" if self.cur_board.turn == chess.WHITE else "Noirs"
        if ex.theme == "mat":
            task = f"Les {side} jouent et font mat."
        elif ex.kind == "quiz":
            task = f"Les {side} jouent : quel coup respecte les principes ?"
        elif ex.source == "partie":
            task = f"Les {side} jouent. Dans ta partie, tu t'es trompé ici : trouve le meilleur coup !"
        else:
            task = f"Les {side} jouent et gagnent quelque chose. À toi !"
        self.prompt.setText(task)
        self.feedback.setText("Prends ton temps : échecs, captures, menaces.")
        self.feedback.setStyleSheet(f"background:{theme.PANEL}; border-radius:10px; padding:10px; font-size:15px;")
        self.explain.setHtml(f"<p style='color:{theme.MUTED}'>Thème : {THEMES.get(ex.theme, ex.theme)}</p>")
        self.queue_list.setCurrentRow(self.idx)
        self.session_lbl.setText(f"Exercice {self.idx + 1}/{len(self.exercises)} · réussis : {self.score}")
        self._buttons(True)

    @property
    def ex(self):
        return self.exercises[self.idx] if 0 <= self.idx < len(self.exercises) else None

    def _end_session(self):
        n = len(self.exercises)
        self.board.interactive = False
        self.title.setText("Série terminée !")
        pct = self.score / n * 100 if n else 0
        msg = ("Excellent ! Ces notions commencent à être solides." if pct >= 80 else
               "Pas mal ! Refais une série demain : les exercices ratés reviendront." if pct >= 50 else
               "C'est en se trompant qu'on apprend : relis la leçon associée puis refais une série.")
        self.prompt.setText(f"Score : {self.score}/{n}. {msg}")
        self.feedback.setText("Clique sur « Commencer » pour une nouvelle série.")
        self.exercises = []
        self._buttons(False)
        self.ctx.dataChanged.emit()

    # ------------------------------------------------------------------ coups
    def on_move(self, mv: chess.Move):
        ex = self.ex
        if not ex or self.checking:
            return
        self.checking = True
        board = self.cur_board.copy()
        tmp = board.copy()
        tmp.push(mv)
        self.board.set_board(tmp, last_move=mv)
        self.board.interactive = False
        eng = self.ctx.quick_engine()
        step = self.step
        self.feedback.setText("Vérification…")
        run_task(check_move, ex, board, mv, step, eng, on_done=lambda r: self._checked(r, mv),
                 on_error=lambda m: self._checked(None, mv))

    def _checked(self, res, mv):
        self.checking = False
        ex = self.ex
        if res is None or not ex:
            self.board.interactive = True
            return
        if res.status == "wrong":
            self.failed = True
            self.feedback.setText("✗ " + res.message)
            self.feedback.setStyleSheet(f"background:#3b2523; border-radius:10px; padding:10px; font-size:15px; color:{theme.TEXT};")
            self.board.set_highlights({mv.to_square: QColor(224, 83, 61, 90)})
            QTimer.singleShot(1300, self.retry)
            return
        self.cur_board.push(mv)
        if res.status == "correct" and res.reply is not None:
            self.feedback.setText("✓ " + res.message)
            self.feedback.setStyleSheet("background:#24351f; border-radius:10px; padding:10px; font-size:15px;")
            self.step += 2

            def play_reply():
                self.cur_board.push(res.reply)
                self.board.set_board(self.cur_board, last_move=res.reply)
                self.board.interactive = True
            QTimer.singleShot(600, play_reply)
            return
        # Résolu
        self.feedback.setText("✓ Bravo ! " + ("(avec de l'aide, il reviendra bientôt pour t'entraîner)" if (self.failed or self.hints >= 2) else ""))
        self.feedback.setStyleSheet("background:#24351f; border-radius:10px; padding:10px; font-size:15px;")
        self._record(not self.failed and self.hints < 2)
        self.explain.setHtml(solution_explanation(ex))
        self._buttons(True, solved=True)

    def retry(self):
        if not self.ex:
            return
        self.board.set_board(self.cur_board, last_move=self.cur_board.peek() if self.step else None)
        if not self.step:
            self.board.last_move = None
        self.board.set_highlights({})
        self.board.interactive = True
        self.feedback.setText("Essaie encore. Pose-toi la question : qu'est-ce qui n'est pas protégé ?")
        self.feedback.setStyleSheet(f"background:{theme.PANEL}; border-radius:10px; padding:10px; font-size:15px;")

    def hint(self):
        ex = self.ex
        if not ex:
            return
        self.hints += 1
        sol = chess.Move.from_uci(ex.solution[self.step])
        if self.hints == 1:
            self.feedback.setText("💡 " + (ex.hint or THEME_HINTS.get(ex.theme, "Échecs, captures, menaces !")))
        elif self.hints == 2:
            p = self.cur_board.piece_at(sol.from_square)
            from ..chessutil import PIECE_FR
            self.feedback.setText(f"💡 Joue avec ton {PIECE_FR[p.piece_type] if p else 'pièce'} en surbrillance.")
            self.board.set_highlights({sol.from_square: QColor(240, 193, 92, 120)})
        else:
            self.show_solution()

    def show_solution(self):
        ex = self.ex
        if not ex:
            return
        self.failed = True
        sol = chess.Move.from_uci(ex.solution[self.step])
        self.board.set_board(self.cur_board, last_move=None)
        self.board.set_arrows([(sol.from_square, sol.to_square, "g")])
        self.feedback.setText("Voici la solution. Joue-la sur l'échiquier pour bien la retenir.")
        self.explain.setHtml(solution_explanation(ex))
        self.board.interactive = True

    def _record(self, success: bool):
        ex = self.ex
        if not ex or getattr(self, "_recorded", False):
            return
        self._recorded = True
        self.ctx.db.record_attempt(ex.id, ex.theme, success, self.hints)
        self.done_count += 1
        if success:
            self.score += 1
            it = self.queue_list.item(self.idx)
            if it:
                it.setText("✔ " + it.text()[2:])
        else:
            it = self.queue_list.item(self.idx)
            if it:
                it.setText("✖ " + it.text()[2:])
        self.session_lbl.setText(f"Exercice {self.idx + 1}/{len(self.exercises)} · réussis : {self.score}")
