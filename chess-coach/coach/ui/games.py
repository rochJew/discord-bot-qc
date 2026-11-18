"""Page « Mes parties » : import Chess.com, PGN collé, liste des parties analysées."""
from __future__ import annotations

import datetime as dt
import html

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from .. import chesscom
from ..service import analyse_and_store
from . import theme
from .widgets import label
from .workers import run_task

TIME_FR = {"rapid": "Rapide", "blitz": "Blitz", "bullet": "Bullet", "daily": "Quotidienne"}
RES_FR = {"win": "Victoire", "loss": "Défaite", "draw": "Nulle"}
RES_COL = {"win": theme.GOOD, "loss": theme.BAD, "draw": theme.MUTED}


def _date(ts) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M") if ts else ""


class GamesPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("page")
        self.ctx = ctx
        self.online: list[chesscom.OnlineGame] = []
        self.queue: list[dict] = []
        self.busy = False
        self.cancel_flag = False
        self._build()
        self.refresh_local()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)
        root.addWidget(label("Mes parties", "h1"))
        root.addWidget(label("Importe tes parties Chess.com (aucun mot de passe nécessaire : l'API publique suffit) "
                             "ou colle un PGN. Chaque partie est analysée par Stockfish, puis tes erreurs deviennent "
                             "des exercices personnalisés.", "muted", wrap=True))
        # Barre de progression
        prog = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.hide()
        self.status = label("", "muted")
        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.hide()
        self.btn_cancel.clicked.connect(self._cancel)
        prog.addWidget(self.status)
        prog.addWidget(self.progress, 1)
        prog.addWidget(self.btn_cancel)
        root.addLayout(prog)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        # --- Chess.com
        cc = QWidget()
        cv = QVBoxLayout(cc)
        cv.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        self.user = QLineEdit(self.ctx.settings.chesscom_username)
        self.user.setPlaceholderText("Ton pseudo Chess.com")
        self.user.setMaximumWidth(260)
        btn_fetch = QPushButton("Récupérer mes dernières parties")
        btn_fetch.setObjectName("primary")
        btn_fetch.clicked.connect(self.fetch)
        row.addWidget(self.user)
        row.addWidget(btn_fetch)
        row.addStretch()
        self.btn_analyse_sel = QPushButton("Analyser la sélection")
        self.btn_analyse_sel.clicked.connect(self.analyse_selected)
        self.btn_analyse_new = QPushButton("Analyser les 5 dernières non analysées")
        self.btn_analyse_new.clicked.connect(lambda: self.analyse_new(5))
        row.addWidget(self.btn_analyse_sel)
        row.addWidget(self.btn_analyse_new)
        cv.addLayout(row)
        self.online_table = self._table(["Date", "Cadence", "Couleur", "Adversaire", "Résultat", "Ton Elo", "Statut"])
        self.online_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.online_table.doubleClicked.connect(lambda *_: self.analyse_selected())
        cv.addWidget(self.online_table, 1)
        tabs.addTab(cc, "Chess.com")

        # --- PGN
        pg = QWidget()
        pv = QVBoxLayout(pg)
        pv.setContentsMargins(0, 10, 0, 0)
        self.pgn_edit = QPlainTextEdit()
        self.pgn_edit.setPlaceholderText("Colle ici le PGN d'une partie (Chess.com : Partager → PGN → Copier)…")
        pv.addWidget(self.pgn_edit, 1)
        prow = QHBoxLayout()
        self.color_box = QComboBox()
        self.color_box.addItems(["Ma couleur : détecter avec mon pseudo", "J'avais les Blancs", "J'avais les Noirs"])
        btn_file = QPushButton("Ouvrir un fichier PGN…")
        btn_file.clicked.connect(self.open_pgn_file)
        btn_pgn = QPushButton("Analyser ce PGN")
        btn_pgn.setObjectName("primary")
        btn_pgn.clicked.connect(self.analyse_pgn)
        prow.addWidget(self.color_box)
        prow.addWidget(btn_file)
        prow.addStretch()
        prow.addWidget(btn_pgn)
        pv.addLayout(prow)
        tabs.addTab(pg, "Coller un PGN")

        # --- Parties analysées
        an = QWidget()
        av = QVBoxLayout(an)
        av.setContentsMargins(0, 10, 0, 0)
        arow = QHBoxLayout()
        arow.addWidget(label("Double-clique sur une partie pour la revoir avec le coach.", "muted"))
        arow.addStretch()
        btn_del = QPushButton("Supprimer")
        btn_del.clicked.connect(self.delete_selected)
        arow.addWidget(btn_del)
        av.addLayout(arow)
        self.local_table = self._table(["Date", "Blancs", "Noirs", "Résultat", "Précision", "Gaffes", "Erreurs", "Imprécisions"])
        self.local_table.doubleClicked.connect(self.open_selected)
        av.addWidget(self.local_table, 1)
        tabs.addTab(an, "Parties analysées")
        self.tabs = tabs

    def _table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().hide()
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setAlternatingRowColors(True)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return t

    # ------------------------------------------------------------------ Chess.com
    def fetch(self):
        name = self.user.text().strip()
        if not name:
            QMessageBox.information(self, "Pseudo manquant", "Indique ton pseudo Chess.com.")
            return
        if name != self.ctx.settings.chesscom_username:
            self.ctx.settings.chesscom_username = name
            self.ctx.settings.save()
        self.status.setText("Récupération des parties sur Chess.com…")
        run_task(chesscom.recent_games, name, 40, on_done=self._fetched, on_error=self._error)

    def _fetched(self, games):
        self.online = games
        self.status.setText(f"{len(games)} parties trouvées.")
        name = self.ctx.settings.chesscom_username
        self.online_table.setRowCount(len(games))
        ratings = [g.user_rating(name) for g in games if g.user_rating(name)]
        if ratings and ratings[0]:
            self.ctx.settings.current_elo = ratings[0]
            self.ctx.settings.save()
        for r, g in enumerate(games):
            color = g.user_color(name)
            res = g.user_result(name)
            done = self.ctx.db.game_exists(g.url)
            vals = [_date(g.end_time), TIME_FR.get(g.time_class, g.time_class), "Blancs" if color == "white" else "Noirs",
                    f"{g.opponent(name)} ({g.black_rating if color == 'white' else g.white_rating})",
                    RES_FR.get(res, res), str(g.user_rating(name) or ""), "✓ analysée" if done else "—"]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 4:
                    it.setForeground(QColor(RES_COL.get(res, theme.TEXT)))
                if c == 6 and done:
                    it.setForeground(QColor(theme.GOOD))
                self.online_table.setItem(r, c, it)

    def _game_job(self, g: chesscom.OnlineGame) -> dict:
        name = self.ctx.settings.chesscom_username
        return dict(pgn=g.pgn, url=g.url, source="chess.com", user_color=g.user_color(name),
                    user_rating=g.user_rating(name),
                    opp_rating=g.black_rating if g.user_color(name) == "white" else g.white_rating,
                    time_class=g.time_class, played_at=g.end_time, user_result=g.user_result(name))

    def analyse_selected(self):
        rows = sorted({i.row() for i in self.online_table.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "Aucune partie", "Sélectionne une ou plusieurs parties dans la liste.")
            return
        for r in rows:
            self.queue.append(self._game_job(self.online[r]))
        self._next()

    def analyse_new(self, n: int):
        if not self.online:
            self.fetch()
            return
        todo = [g for g in self.online if not self.ctx.db.game_exists(g.url)][:n]
        if not todo:
            self.status.setText("Toutes les parties récentes sont déjà analysées.")
            return
        for g in todo:
            self.queue.append(self._game_job(g))
        self._next()

    # ------------------------------------------------------------------ PGN
    def open_pgn_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir un PGN", "", "PGN (*.pgn);;Tous les fichiers (*)")
        if path:
            with open(path, encoding="utf-8", errors="replace") as f:
                self.pgn_edit.setPlainText(f.read())

    def analyse_pgn(self):
        text = self.pgn_edit.toPlainText().strip()
        if not text:
            return
        color = {0: None, 1: "white", 2: "black"}[self.color_box.currentIndex()]
        from ..analysis import parse_pgn
        try:
            parse_pgn(text)
        except ValueError as exc:
            QMessageBox.warning(self, "PGN invalide", str(exc))
            return
        self.queue.append(dict(pgn=text, source="pgn", user_color=color))
        self._next()

    def enqueue_pgn(self, pgn: str, user_color: str | None, source: str = "écran"):
        self.queue.append(dict(pgn=pgn, source=source, user_color=user_color))
        self._next()

    # ------------------------------------------------------------------ file d'analyse
    def _next(self):
        if self.busy or not self.queue:
            return
        job = self.queue.pop(0)
        self.busy = True
        self.cancel_flag = False
        self.progress.setValue(0)
        self.progress.show()
        self.btn_cancel.show()
        left = len(self.queue)
        self.status.setText("Analyse en cours…" + (f" ({left} en attente)" if left else ""))
        run_task(analyse_and_store, self.ctx.db, self.ctx.settings, should_stop=lambda: self.cancel_flag,
                 on_done=self._analysed, on_error=self._error,
                 on_progress=lambda a, b: (self.progress.setMaximum(b), self.progress.setValue(a)), **job)

    def _cancel(self):
        self.cancel_flag = True
        self.queue.clear()

    def _analysed(self, gid):
        self.busy = False
        self.refresh_local()
        if self.online:
            self._fetched(self.online)
        self.ctx.dataChanged.emit()
        if self.queue:
            self._next()
        else:
            self.progress.hide()
            self.btn_cancel.hide()
            self.status.setText("Analyse terminée ✓ — tes erreurs ont été ajoutées à tes exercices.")
            self.ctx.openGame.emit(gid)

    def _error(self, msg):
        self.busy = False
        self.progress.hide()
        self.btn_cancel.hide()
        self.status.setText("")
        if "annulée" not in msg:
            QMessageBox.warning(self, "Oups", html.unescape(msg))
        self.queue.clear() if "Stockfish" in msg else self._next()

    # ------------------------------------------------------------------ parties analysées
    def refresh_local(self):
        rows = self.ctx.db.games()
        self.local_ids = [r["id"] for r in rows]
        self.local_table.setRowCount(len(rows))
        for i, g in enumerate(rows):
            vals = [_date(g["played_at"]), g["white"], g["black"],
                    RES_FR.get(g["user_result"], g["result"]), f"{g['accuracy']:.0f}%",
                    str(g["blunders"]), str(g["mistakes"] + g["misses"]), str(g["inaccuracies"])]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 3:
                    it.setForeground(QColor(RES_COL.get(g["user_result"], theme.TEXT)))
                self.local_table.setItem(i, c, it)

    def open_selected(self):
        r = self.local_table.currentRow()
        if 0 <= r < len(self.local_ids):
            self.ctx.openGame.emit(self.local_ids[r])

    def delete_selected(self):
        r = self.local_table.currentRow()
        if 0 <= r < len(self.local_ids):
            if QMessageBox.question(self, "Supprimer", "Supprimer cette partie et ses statistiques ?") == QMessageBox.Yes:
                self.ctx.db.delete_game(self.local_ids[r])
                self.refresh_local()
                self.ctx.dataChanged.emit()

    def show_analysed(self):
        self.tabs.setCurrentIndex(2)

