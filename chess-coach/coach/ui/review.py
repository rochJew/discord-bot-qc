"""Page « Analyse » : revoir une partie coup par coup avec le coach."""
from __future__ import annotations

import html

import chess
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLineEdit, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget, QHeaderView,
                               QAbstractItemView)

from ..analysis import CLASS_COLOR, CLASS_FR, CLASS_SYMBOL, ERROR_CLASSES, GameAnalysis, MoveAnalysis
from ..chessutil import san_fr, win_percent
from ..explain import explanation_text, game_summary
from ..llm import markdown_to_html
from . import theme
from .board import ChessBoardWidget, EvalBar, EvalGraph
from .widgets import label
from .workers import run_task


def _white_win(cp: int, mate: int | None) -> float:
    if mate is not None:
        return 100.0 if mate > 0 else 0.0 if mate < 0 else (100.0 if cp > 0 else 0.0)
    return win_percent(cp)


def opponent_move_html(m: MoveAnalysis) -> str:
    num = f"{m.move_number}{'.' if m.color == 'white' else '...'}"
    title = f"<h3>{num}{san_fr(m.san)} — coup de ton adversaire ({CLASS_FR[m.classification].lower()})</h3>"
    if m.classification in ("mistake", "blunder", "miss"):
        body = (f"<p><b>Ton adversaire vient de se tromper !</b> Ses chances passent de {m.win_before:.0f}% à "
                f"{m.win_after:.0f}%. C'est le moment de te demander : « Qu'est-ce que ce coup a laissé ? Une pièce "
                f"sans protection ? Un échec ? ». Regarde le coup suivant pour voir si tu en as profité.</p>")
        if m.reply_pv_san:
            body += f"<p><b>Comment le punir :</b> {san_fr(m.reply_pv_san[0])} était le meilleur coup pour toi.</p>"
    elif m.classification == "inaccuracy":
        body = "<p>Petite imprécision de ton adversaire : rien de grave, mais il t'a laissé un peu plus de liberté.</p>"
    else:
        body = "<p>Bon coup de ton adversaire. Demande-toi toujours : « Qu'est-ce qu'il menace maintenant ? »</p>"
        if m.reply_pv_san:
            body += f"<p>La meilleure réponse pour toi était {san_fr(m.reply_pv_san[0])}.</p>"
    return title + body


class ReviewPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("page")
        self.ctx = ctx
        self.gid: int | None = None
        self.ga: GameAnalysis | None = None
        self.boards: list[chess.Board] = []
        self.ply = 0
        self.var_base: chess.Board | None = None
        self.var_moves: list[chess.Move] = []
        self.var_idx = 0
        self.var_label = ""
        self.chat_history: list[dict] = []
        self._build()

    # ------------------------------------------------------------------ interface
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        split = QSplitter(Qt.Horizontal)
        root.addWidget(split)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)
        self.header = label("Choisis une partie dans « Mes parties » pour l'analyser.", "h2", wrap=True)
        lv.addWidget(self.header)
        brow = QHBoxLayout()
        self.evalbar = EvalBar()
        self.board = ChessBoardWidget(interactive=True)
        self.board.moveMade.connect(self._on_user_move)
        brow.addWidget(self.evalbar)
        brow.addWidget(self.board, 1)
        lv.addLayout(brow, 1)
        self.var_banner = label("", "muted", wrap=True)
        self.var_banner.setStyleSheet(f"background:{theme.PANEL2}; border-radius:8px; padding:6px 10px; color:{theme.ACCENT2};")
        self.var_banner.hide()
        lv.addWidget(self.var_banner)
        nav = QHBoxLayout()
        self.btn_first = self._icon("⏮", "Début (Début)", self.go_first)
        self.btn_prev = self._icon("◀", "Coup précédent (←)", self.go_prev)
        self.btn_next = self._icon("▶", "Coup suivant (→)", self.go_next)
        self.btn_last = self._icon("⏭", "Fin (Fin)", self.go_last)
        self.btn_flip = self._icon("⇅", "Retourner l'échiquier", self.flip)
        for b in (self.btn_first, self.btn_prev, self.btn_next, self.btn_last, self.btn_flip):
            nav.addWidget(b)
        nav.addSpacing(10)
        self.btn_next_err = QPushButton("Erreur suivante ⚑")
        self.btn_next_err.clicked.connect(self.next_error)
        nav.addWidget(self.btn_next_err)
        nav.addStretch()
        self.chk_compare = QCheckBox("Comparer avec le meilleur coup")
        self.chk_compare.setChecked(True)
        self.chk_compare.setToolTip("Sur tes erreurs, affiche la position AVANT ton coup : flèche rouge = ton coup, verte = le meilleur.")
        self.chk_compare.toggled.connect(lambda *_: self.refresh())
        nav.addWidget(self.chk_compare)
        lv.addLayout(nav)
        var = QHBoxLayout()
        self.btn_best_line = QPushButton("▶ Rejouer la meilleure suite")
        self.btn_best_line.clicked.connect(self.show_best_line)
        self.btn_punish = QPushButton("▶ Voir comment l'adversaire en profite")
        self.btn_punish.clicked.connect(self.show_reply_line)
        self.btn_exit_var = QPushButton("✕ Revenir à la partie")
        self.btn_exit_var.clicked.connect(self.exit_variation)
        self.btn_exit_var.hide()
        var.addWidget(self.btn_best_line)
        var.addWidget(self.btn_punish)
        var.addWidget(self.btn_exit_var)
        var.addStretch()
        lv.addLayout(var)
        self.graph = EvalGraph()
        self.graph.plyClicked.connect(lambda i: self.go_to(i + 1))
        lv.addWidget(self.graph)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        self.stats = label("", "muted", wrap=True)
        rv.addWidget(self.stats)
        self.tabs = QTabWidget()
        # Onglet coach
        coach = QWidget()
        cv = QVBoxLayout(coach)
        cv.setContentsMargins(0, 8, 0, 0)
        self.coach_view = QTextBrowser()
        self.coach_view.setOpenExternalLinks(True)
        cv.addWidget(self.coach_view, 1)
        ai_row = QHBoxLayout()
        self.btn_ai = QPushButton("🤖 Explication détaillée du coach IA")
        self.btn_ai.setObjectName("primary")
        self.btn_ai.clicked.connect(self.ai_explain)
        ai_row.addWidget(self.btn_ai)
        ai_row.addStretch()
        cv.addLayout(ai_row)
        q_row = QHBoxLayout()
        self.question = QLineEdit()
        self.question.setPlaceholderText("Pose une question au coach sur cette position (ex : pourquoi pas Cxe5 ?)")
        self.question.returnPressed.connect(self.ask)
        btn_q = QPushButton("Demander")
        btn_q.clicked.connect(self.ask)
        q_row.addWidget(self.question, 1)
        q_row.addWidget(btn_q)
        cv.addLayout(q_row)
        self.tabs.addTab(coach, "Coach")
        # Onglet coups
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["N°", "Blancs", "Noirs"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.cellClicked.connect(self._cell_clicked)
        self.tabs.addTab(self.table, "Coups")
        # Onglet bilan
        bil = QWidget()
        bv = QVBoxLayout(bil)
        bv.setContentsMargins(0, 8, 0, 0)
        self.summary_view = QTextBrowser()
        bv.addWidget(self.summary_view, 1)
        self.btn_review = QPushButton("🤖 Bilan de partie par le coach IA")
        self.btn_review.clicked.connect(self.ai_review)
        bv.addWidget(self.btn_review)
        self.tabs.addTab(bil, "Bilan")
        rv.addWidget(self.tabs, 1)
        split.addWidget(right)
        split.setSizes([620, 520])

        for key, fn in ((Qt.Key_Left, self.go_prev), (Qt.Key_Right, self.go_next), (Qt.Key_Home, self.go_first),
                        (Qt.Key_End, self.go_last)):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
        self._set_enabled(False)

    def _icon(self, txt, tip, fn):
        b = QPushButton(txt)
        b.setObjectName("icon")
        b.setToolTip(tip)
        b.clicked.connect(fn)
        return b

    def _set_enabled(self, on: bool):
        for w in (self.btn_first, self.btn_prev, self.btn_next, self.btn_last, self.btn_next_err, self.btn_best_line,
                  self.btn_punish, self.btn_ai, self.btn_review, self.question):
            w.setEnabled(on)

    # ------------------------------------------------------------------ chargement
    def load_game(self, gid: int, ply: int | None = None):
        ga = self.ctx.db.load_analysis(gid)
        if not ga:
            return
        self.gid, self.ga = gid, ga
        b = chess.Board(ga.moves[0].fen_before) if ga.moves else chess.Board()
        self.boards = [b.copy()]
        for m in ga.moves:
            b.push(chess.Move.from_uci(m.uci))
            self.boards.append(b.copy())
        self.board.set_flipped(ga.user_color == "black")
        self.evalbar.flipped = ga.user_color == "black"
        g = self.ctx.db.game(gid)
        def _r(color):
            if not g or not ga.user_color:
                return ""
            v = g["user_rating"] if ga.user_color == color else g["opp_rating"]
            return f" ({v})" if v else ""
        wr, br = _r("white"), _r("black")
        self.header.setText(f"{ga.white}{wr}  vs  {ga.black}{br}   —   {ga.result}")
        c = ga.counts()
        you = "toi" if ga.user_color else "les Blancs"
        self.stats.setText(
            f"Précision ({you}) : <b>{ga.accuracy():.0f}%</b> · adversaire : {ga.accuracy('black' if ga.user_color == 'white' else 'white'):.0f}%"
            f"  ·  <span style='color:{CLASS_COLOR['blunder']}'>?? {c['blunder']} gaffes</span> · "
            f"<span style='color:{CLASS_COLOR['mistake']}'>? {c['mistake']} erreurs</span> · "
            f"<span style='color:{CLASS_COLOR['miss']}'>✗ {c['miss']} occasions manquées</span> · "
            f"<span style='color:{CLASS_COLOR['inaccuracy']}'>?! {c['inaccuracy']} imprécisions</span>")
        self._fill_table()
        vals = [_white_win(m.eval_after, m.mate_after) for m in ga.moves]
        marks = {i: CLASS_COLOR[m.classification] for i, m in enumerate(ga.moves)
                 if m.is_user and m.classification in ERROR_CLASSES}
        self.graph.set_data(vals, marks)
        summ = game_summary(ga)
        review = g["ai_review"] if g else None
        self.summary_view.setHtml(
            f"<h3>Bilan de la partie</h3><p>{html.escape(summ['text'])}</p>"
            + (f"<hr><h3>Bilan du coach IA</h3>{markdown_to_html(review)}" if review else ""))
        self.chat_history = []
        self._set_enabled(True)
        self.exit_variation(refresh=False)
        self.go_to(ply if ply is not None else 0)

    def _fill_table(self):
        ga = self.ga
        rows = (len(ga.moves) + 1 + (1 if ga.moves and ga.moves[0].color == "black" else 0)) // 2
        self.table.setRowCount(rows)
        first_num = ga.moves[0].move_number if ga.moves else 1
        for r in range(rows):
            it = QTableWidgetItem(str(first_num + r))
            it.setForeground(QColor(theme.MUTED))
            self.table.setItem(r, 0, it)
        for i, m in enumerate(ga.moves):
            row = m.move_number - first_num
            col = 1 if m.color == "white" else 2
            sym = CLASS_SYMBOL[m.classification] if m.classification not in ("best", "excellent", "good") else ""
            it = QTableWidgetItem(f"{san_fr(m.san)} {sym}")
            it.setData(Qt.UserRole, i + 1)
            if m.classification in ERROR_CLASSES or m.classification == "best" and m.is_user:
                it.setForeground(QColor(CLASS_COLOR[m.classification]))
            if m.is_user and m.classification in ERROR_CLASSES:
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            it.setToolTip(f"{CLASS_FR[m.classification]} — meilleur : {san_fr(m.best_san)}")
            self.table.setItem(row, col, it)

    def _cell_clicked(self, r, c):
        it = self.table.item(r, c)
        if it and it.data(Qt.UserRole):
            self.exit_variation(refresh=False)
            self.go_to(int(it.data(Qt.UserRole)))
            self.tabs.setCurrentIndex(0)

    # ------------------------------------------------------------------ navigation
    def go_to(self, ply: int):
        if not self.ga:
            return
        self.ply = max(0, min(len(self.ga.moves), ply))
        self.refresh()

    def go_first(self):
        if self.var_base is not None:
            self.var_idx = 0
            self.refresh()
        else:
            self.go_to(0)

    def go_last(self):
        if self.var_base is not None:
            self.var_idx = len(self.var_moves)
            self.refresh()
        elif self.ga:
            self.go_to(len(self.ga.moves))

    def go_prev(self):
        if self.var_base is not None:
            if self.var_idx > 0:
                self.var_idx -= 1
                self.refresh()
            else:
                self.exit_variation()
        else:
            self.go_to(self.ply - 1)

    def go_next(self):
        if self.var_base is not None:
            if self.var_idx < len(self.var_moves):
                self.var_idx += 1
                self.refresh()
        else:
            self.go_to(self.ply + 1)

    def next_error(self):
        if not self.ga:
            return
        for i in range(self.ply, len(self.ga.moves)):
            m = self.ga.moves[i]
            if m.is_user and m.classification in ERROR_CLASSES and i + 1 > self.ply:
                self.exit_variation(refresh=False)
                self.go_to(i + 1)
                return
        for i, m in enumerate(self.ga.moves):  # recommence au début
            if m.is_user and m.classification in ERROR_CLASSES:
                self.exit_variation(refresh=False)
                self.go_to(i + 1)
                return

    def flip(self):
        self.board.set_flipped(not self.board.flipped)
        self.evalbar.flipped = self.board.flipped
        self.evalbar.update()

    # ------------------------------------------------------------------ variantes
    def _start_variation(self, base: chess.Board, moves: list[chess.Move], label_txt: str, idx: int = 1):
        self.var_base, self.var_moves, self.var_idx, self.var_label = base.copy(), moves, idx, label_txt
        self.btn_exit_var.show()
        self.refresh()

    def show_best_line(self):
        m = self._current_move()
        if not m:
            return
        base = chess.Board(m.fen_before)
        moves = self._san_list(base, m.best_pv_san)
        self._start_variation(base, moves, f"Meilleure suite : {' '.join(san_fr(s) for s in m.best_pv_san[:8])}")

    def show_reply_line(self):
        m = self._current_move()
        if not m:
            return
        base = chess.Board(m.fen_after)
        moves = self._san_list(base, m.reply_pv_san)
        self._start_variation(base, moves, f"Après {san_fr(m.san)}, la meilleure suite adverse : "
                                           f"{' '.join(san_fr(s) for s in m.reply_pv_san[:8])}")

    @staticmethod
    def _san_list(board: chess.Board, sans: list[str]) -> list[chess.Move]:
        b = board.copy()
        out = []
        for s in sans:
            try:
                mv = b.parse_san(s)
            except ValueError:
                break
            out.append(mv)
            b.push(mv)
        return out

    def exit_variation(self, refresh: bool = True):
        self.var_base = None
        self.var_moves = []
        self.var_idx = 0
        self.btn_exit_var.hide()
        self.var_banner.hide()
        if refresh:
            self.refresh()

    def _on_user_move(self, mv: chess.Move):
        """Exploration libre : on joue un coup sur l'échiquier."""
        if not self.ga:
            return
        if self.var_base is not None:
            self.var_moves = self.var_moves[:self.var_idx] + [mv]
            self.var_idx = len(self.var_moves)
            self.var_label = "Exploration libre"
            self.refresh()
        else:
            base = self.board.board.copy()
            self._start_variation(base, [mv], "Exploration libre (le moteur te montre sa meilleure réponse en bleu)")

    def _current_move(self) -> MoveAnalysis | None:
        if not self.ga or self.ply == 0:
            return None
        return self.ga.moves[self.ply - 1]

    # ------------------------------------------------------------------ affichage
    def refresh(self):
        if not self.ga:
            return
        if self.var_base is not None:
            self._refresh_variation()
            return
        m = self._current_move()
        self.graph.set_current(self.ply - 1)
        self._select_table(self.ply)
        self.board.set_highlights({})
        if m is None:
            self.board.set_board(self.boards[0])
            self.board.set_arrows([])
            self.board.set_badge(None)
            first = self.ga.moves[0] if self.ga.moves else None
            self.evalbar.set_eval(first.eval_before if first else 0, first.mate_before if first else None)
            self.coach_view.setHtml(
                "<h3>Début de la partie</h3><p>Utilise les flèches ◀ ▶ (ou les touches du clavier) pour avancer, "
                "ou clique sur <b>Erreur suivante ⚑</b> pour aller directement aux moments importants.</p>"
                f"<p>{html.escape(game_summary(self.ga)['text'])}</p>")
            self.btn_best_line.setEnabled(False)
            self.btn_punish.setEnabled(False)
            self.btn_ai.setEnabled(False)
            return
        self.btn_best_line.setEnabled(bool(m.best_pv_san))
        self.btn_punish.setEnabled(bool(m.reply_pv_san))
        self.btn_ai.setEnabled(m.is_user and m.classification in ERROR_CLASSES)
        played = chess.Move.from_uci(m.uci)
        best = chess.Move.from_uci(m.best_uci) if m.best_uci else None
        compare = self.chk_compare.isChecked() and m.is_error and best and best != played
        color = CLASS_COLOR[m.classification]
        if compare:
            self.board.set_board(self.boards[self.ply - 1], last_move=None)
            self.board.last_move = None
            self.board.set_arrows([(played.from_square, played.to_square, "r"), (best.from_square, best.to_square, "g")])
            self.board.set_badge(played.to_square, CLASS_SYMBOL[m.classification], color)
            self.evalbar.set_eval(m.eval_before, m.mate_before)
        else:
            self.board.set_board(self.boards[self.ply], last_move=played)
            arrows = []
            if m.is_error and m.reply_pv_san:
                rep = self._san_list(self.boards[self.ply], m.reply_pv_san[:1])
                if rep:
                    arrows.append((rep[0].from_square, rep[0].to_square, "b"))
            self.board.set_arrows(arrows)
            sym = CLASS_SYMBOL[m.classification]
            self.board.set_badge(played.to_square, sym, color)
            self.evalbar.set_eval(m.eval_after, m.mate_after)
        # Surlignage des cases des motifs (pièce en prise, fourchette…)
        hl = {}
        if m.is_user and m.is_error:
            for mo in m.motifs:
                for s in mo.get("squares", [])[1:] if mo["theme"] in ("fourchette", "clouage", "enfilade") else mo.get("squares", []):
                    hl[s] = QColor(224, 83, 61, 70)
        self.board.set_highlights(hl)
        if m.is_user:
            txt = explanation_text(m)
            ai = self.ctx.db.ai_explanation(self.gid, m.ply)
            if ai:
                txt += "<hr><h3>🤖 Le coach IA t'explique</h3>" + markdown_to_html(ai)
            legend = ("<p style='color:#a3a6ad;font-size:12px'>Flèche rouge : ton coup · flèche verte : le meilleur coup · "
                      "flèche bleue : la réponse adverse.</p>") if m.is_error else ""
            self.coach_view.setHtml(txt + legend)
        else:
            self.coach_view.setHtml(opponent_move_html(m))

    def _refresh_variation(self):
        b = self.var_base.copy()
        for mv in self.var_moves[:self.var_idx]:
            b.push(mv)
        self.board.set_board(b, last_move=self.var_moves[self.var_idx - 1] if self.var_idx else None)
        self.board.set_badge(None)
        self.board.set_highlights({})
        self.board.set_arrows([])
        sans = []
        bb = self.var_base.copy()
        for i, mv in enumerate(self.var_moves):
            s = san_fr(bb.san(mv))
            sans.append(f"<b>[{s}]</b>" if i == self.var_idx - 1 else s)
            bb.push(mv)
        self.var_banner.setText(f"{self.var_label}<br>{' '.join(sans)}   ({self.var_idx}/{len(self.var_moves)})")
        self.var_banner.show()
        self._eval_async(b)

    def _eval_async(self, b: chess.Board):
        eng = self.ctx.quick_engine()
        if eng is None:
            return
        fen = b.fen()

        def work():
            lines = eng.analyse(chess.Board(fen), depth=14, time=0.4)
            return fen, lines[0]

        def done(res):
            f, line = res
            if self.var_base is None or self.board.board.fen() != f:
                return
            turn = chess.Board(f).turn
            cp = line.score_cp if turn == chess.WHITE else -line.score_cp
            mate = None if line.mate is None else (line.mate if turn == chess.WHITE else -line.mate)
            self.evalbar.set_eval(cp, mate)
            if line.best:
                self.board.set_arrows([(line.best.from_square, line.best.to_square, "b")])

        run_task(work, on_done=done)

    def _select_table(self, ply: int):
        self.table.clearSelection()
        if ply == 0 or not self.ga:
            return
        m = self.ga.moves[ply - 1]
        first = self.ga.moves[0].move_number
        self.table.setCurrentCell(m.move_number - first, 1 if m.color == "white" else 2)

    # ------------------------------------------------------------------ IA
    def ai_explain(self):
        m = self._current_move()
        coach = self.ctx.ai_coach()
        if not m:
            return
        if coach is None:
            self.coach_view.append("<p style='color:#f0c15c'>Le coach IA n'est pas configuré : ajoute ta clé API Anthropic "
                                   "dans Paramètres. Les explications ci-dessus fonctionnent sans IA.</p>")
            return
        self.btn_ai.setEnabled(False)
        self.btn_ai.setText("🤖 Le coach réfléchit…")
        gid, ply = self.gid, m.ply

        def done(text):
            self.ctx.db.set_ai_explanation(gid, ply, text)
            self.btn_ai.setText("🤖 Explication détaillée du coach IA")
            self.btn_ai.setEnabled(True)
            if self.gid == gid and self.ply - 1 == ply:
                self.refresh()
                self.coach_view.verticalScrollBar().setValue(self.coach_view.verticalScrollBar().maximum())

        def err(msg):
            self.btn_ai.setText("🤖 Explication détaillée du coach IA")
            self.btn_ai.setEnabled(True)
            self.coach_view.append(f"<p style='color:{theme.BAD}'>{html.escape(msg)}</p>")

        run_task(coach.explain_move, m, on_done=done, on_error=err)

    def ask(self):
        q = self.question.text().strip()
        if not q or not self.ga:
            return
        coach = self.ctx.ai_coach()
        if coach is None:
            self.coach_view.append("<p style='color:#f0c15c'>Pour poser des questions, ajoute ta clé API Anthropic dans Paramètres.</p>")
            return
        self.question.clear()
        b = self.board.board
        m = self._current_move()
        ctx = [f"Position actuelle (FEN) : {b.fen()}", f"Trait aux {'Blancs' if b.turn else 'Noirs'}",
               f"Le joueur a les {'Blancs' if self.ga.user_color == 'white' else 'Noirs'}"]
        if m and self.var_base is None:
            ctx += [f"Dernier coup : {san_fr(m.san)} ({CLASS_FR[m.classification]})", f"Meilleur coup était : {san_fr(m.best_san)}",
                    f"Meilleure suite : {' '.join(san_fr(s) for s in m.best_pv_san[:6])}",
                    f"Réponse adverse attendue : {' '.join(san_fr(s) for s in m.reply_pv_san[:6])}"]
        self.chat_history.append({"role": "user", "content": q})
        self.coach_view.append(f"<p><b>Toi :</b> {html.escape(q)}</p><p style='color:{theme.MUTED}'>Le coach réfléchit…</p>")

        def done(text):
            self.chat_history.append({"role": "assistant", "content": text})
            self.coach_view.append("<p><b>🤖 Coach :</b></p>" + markdown_to_html(text))

        def err(msg):
            self.chat_history.pop()
            self.coach_view.append(f"<p style='color:{theme.BAD}'>{html.escape(msg)}</p>")

        eng = self.ctx.quick_engine()
        history = list(self.chat_history)
        fen = b.fen()

        def work():
            facts = list(ctx)
            if eng:
                try:
                    bb = chess.Board(fen)
                    lines = eng.analyse(bb, depth=14, time=0.5, multipv=3)
                    facts.append("Meilleurs coups selon Stockfish dans la position actuelle : " + ", ".join(
                        f"{san_fr(bb.san(ln.best))} ({'mat en %d' % abs(ln.mate) if ln.mate else f'{ln.score_cp / 100:+.1f}'})"
                        for ln in lines if ln.best))
                except Exception:  # noqa: BLE001
                    pass
            return coach.chat(history, "\n".join(facts))

        run_task(work, on_done=done, on_error=err)

    def ai_review(self):
        coach = self.ctx.ai_coach()
        if not self.ga:
            return
        if coach is None:
            self.summary_view.append("<p style='color:#f0c15c'>Ajoute ta clé API Anthropic dans Paramètres pour le bilan IA.</p>")
            return
        self.btn_review.setEnabled(False)
        gid = self.gid
        summ = game_summary(self.ga)["text"]

        def done(text):
            self.ctx.db.set_ai_review(gid, text)
            self.btn_review.setEnabled(True)
            if self.gid == gid:
                self.summary_view.append("<hr><h3>Bilan du coach IA</h3>" + markdown_to_html(text))

        def err(msg):
            self.btn_review.setEnabled(True)
            self.summary_view.append(f"<p style='color:{theme.BAD}'>{html.escape(msg)}</p>")

        run_task(coach.game_review, summ, self.ga.key_moments(), on_done=done, on_error=err)
