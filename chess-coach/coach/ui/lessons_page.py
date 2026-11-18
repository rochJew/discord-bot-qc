"""Page « Leçons » : le programme de 400 à 1000 Elo."""
from __future__ import annotations

import chess
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from ..lessons import recommended_lessons
from ..motifs import THEMES
from ..progress import weakest_themes
from . import theme
from .board import ChessBoardWidget
from .widgets import label


class LessonsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("page")
        self.ctx = ctx
        self.lesson = None
        self.step_idx = 0
        self.move_idx = 0
        self._build()
        self.refresh()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(18)
        side = QVBoxLayout()
        side.addWidget(label("Leçons", "h1"))
        side.addWidget(label("Le programme pour passer de 400 à 1000. Les leçons liées à tes erreurs sont en haut.", "muted", wrap=True))
        self.list = QListWidget()
        self.list.setMinimumWidth(300)
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(self._select)
        side.addWidget(self.list, 1)
        root.addLayout(side, 2)

        main = QVBoxLayout()
        self.title = label("", "h1", wrap=True)
        self.meta = label("", "muted")
        main.addWidget(self.title)
        main.addWidget(self.meta)
        body = QHBoxLayout()
        bcol = QVBoxLayout()
        self.board = ChessBoardWidget()
        bcol.addWidget(self.board, 1)
        mv_row = QHBoxLayout()
        self.btn_mprev = QPushButton("◀ coup")
        self.btn_mprev.clicked.connect(lambda: self._move(-1))
        self.btn_mnext = QPushButton("coup ▶")
        self.btn_mnext.clicked.connect(lambda: self._move(1))
        self.moves_lbl = label("", "muted")
        mv_row.addWidget(self.btn_mprev)
        mv_row.addWidget(self.btn_mnext)
        mv_row.addWidget(self.moves_lbl, 1)
        bcol.addLayout(mv_row)
        body.addLayout(bcol, 3)
        tcol = QVBoxLayout()
        self.text = QTextBrowser()
        tcol.addWidget(self.text, 1)
        nav = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Précédent")
        self.btn_prev.clicked.connect(lambda: self._step(-1))
        self.step_lbl = label("", "muted")
        self.btn_next = QPushButton("Suivant ▶")
        self.btn_next.setObjectName("primary")
        self.btn_next.clicked.connect(lambda: self._step(1))
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.step_lbl, 1, Qt.AlignCenter)
        nav.addWidget(self.btn_next)
        tcol.addLayout(nav)
        self.btn_train = QPushButton("🎯 M'entraîner sur ce thème")
        self.btn_train.clicked.connect(lambda: self.lesson and self.ctx.trainTheme.emit(self.lesson.theme))
        tcol.addWidget(self.btn_train)
        body.addLayout(tcol, 2)
        main.addLayout(body, 1)
        root.addLayout(main, 6)

    def refresh(self):
        done = self.ctx.db.lessons_done()
        order = recommended_lessons(weakest_themes(self.ctx.db, 3), set())
        weak = set(weakest_themes(self.ctx.db, 3))
        self.ordered = order
        cur = self.lesson.id if self.lesson else None
        self.list.blockSignals(True)
        self.list.clear()
        for l in order:
            mark = "✔ " if l.id in done else ("⭐ " if l.theme in weak else "")
            it = QListWidgetItem(f"{mark}{l.title}\n{l.level} Elo · {THEMES.get(l.theme, l.theme)}")
            self.list.addItem(it)
        self.list.blockSignals(False)
        idx = next((i for i, l in enumerate(order) if l.id == cur), 0)
        self.list.setCurrentRow(idx)
        self._select(idx)

    def open_lesson(self, lid: str):
        for i, l in enumerate(self.ordered):
            if l.id == lid:
                self.list.setCurrentRow(i)

    def _select(self, row: int):
        if row < 0 or row >= len(self.ordered):
            return
        self.lesson = self.ordered[row]
        self.step_idx = 0
        self.title.setText(self.lesson.title)
        self.meta.setText(f"Niveau {self.lesson.level} Elo · {self.lesson.summary}")
        self._show()

    def _step(self, d: int):
        if not self.lesson:
            return
        n = len(self.lesson.steps)
        if self.step_idx + d >= n:
            self.ctx.db.mark_lesson(self.lesson.id)
            self._show(final=True)
            return
        self.step_idx = max(0, self.step_idx + d)
        self._show()

    def _show(self, final: bool = False):
        l = self.lesson
        st = l.steps[min(self.step_idx, len(l.steps) - 1)]
        self.move_idx = len(st.moves)
        self._render_board()
        n = len(l.steps)
        self.step_lbl.setText(f"Étape {self.step_idx + 1}/{n}")
        self.btn_prev.setEnabled(self.step_idx > 0)
        self.btn_next.setText("Terminer ✔" if self.step_idx == n - 1 else "Suivant ▶")
        html = f"<p style='font-size:16px; line-height:150%'>{st.text}</p>"
        if final or self.step_idx == n - 1:
            html += "<hr><p><b>À retenir</b></p><ul>" + "".join(f"<li>{k}</li>" for k in l.key_points) + "</ul>"
        if final:
            html += (f"<p style='color:{theme.GOOD}'><b>Leçon terminée !</b> Passe à la pratique avec le bouton "
                     "« M'entraîner sur ce thème ».</p>")
            self.refresh_marks()
        self.text.setHtml(html)

    def refresh_marks(self):
        done = self.ctx.db.lessons_done()
        weak = set(weakest_themes(self.ctx.db, 3))
        for i, l in enumerate(self.ordered):
            mark = "✔ " if l.id in done else ("⭐ " if l.theme in weak else "")
            self.list.item(i).setText(f"{mark}{l.title}\n{l.level} Elo · {THEMES.get(l.theme, l.theme)}")

    def _move(self, d: int):
        st = self.lesson.steps[self.step_idx]
        self.move_idx = max(0, min(len(st.moves), self.move_idx + d))
        self._render_board()

    def _render_board(self):
        st = self.lesson.steps[self.step_idx]
        b = chess.Board(st.fen)
        sans = []
        last = None
        for i, san in enumerate(st.moves):
            mv = b.parse_san(san) if i < self.move_idx else None
            if mv is None:
                break
            sans.append(san)
            last = mv
            b.push(mv)
        self.board.set_board(b, last_move=last)
        if last is None:
            self.board.last_move = None
        self.board.set_flipped(chess.Board(st.fen).turn == chess.BLACK and not st.moves)
        full = self.move_idx == len(st.moves)
        self.board.set_arrows(st.arrows if full else [])
        self.board.set_highlights({s: "#66f0c15c" for s in st.highlights} if full else {})
        has_moves = bool(st.moves)
        self.btn_mprev.setVisible(has_moves)
        self.btn_mnext.setVisible(has_moves)
        from ..chessutil import san_fr
        self.moves_lbl.setText(" ".join(san_fr(s) for s in st.moves[:self.move_idx]) if has_moves else "")

