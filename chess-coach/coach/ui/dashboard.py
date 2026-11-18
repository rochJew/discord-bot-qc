"""Page « Tableau de bord » : progression vers 1000 Elo."""
from __future__ import annotations

import datetime as dt

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ..config import find_stockfish
from ..lessons import recommended_lessons
from ..motifs import THEMES
from ..progress import compute_progress, elo_goal_text, weakest_themes
from . import theme
from .widgets import Card, HBarList, LineChart, MasteryRow, StatCard, label


class DashboardPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("page")
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("page")
        scroll.setWidget(body)
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(24, 20, 24, 24)
        self.lay.setSpacing(16)

        head = QHBoxLayout()
        tcol = QVBoxLayout()
        self.hello = label("Tableau de bord", "h1")
        self.sub = label("", "muted", wrap=True)
        tcol.addWidget(self.hello)
        tcol.addWidget(self.sub)
        head.addLayout(tcol, 1)
        self.lay.addLayout(head)

        self.setup_card = Card("Pour commencer")
        self.setup_txt = label("", wrap=True)
        self.setup_card.lay.addWidget(self.setup_txt)
        srow = QHBoxLayout()
        b = QPushButton("Ouvrir les paramètres")
        b.clicked.connect(lambda: self.ctx.navigate.emit("settings"))
        srow.addWidget(b)
        b = QPushButton("Importer mes parties")
        b.setObjectName("primary")
        b.clicked.connect(lambda: self.ctx.navigate.emit("games"))
        srow.addWidget(b)
        srow.addStretch()
        self.setup_card.lay.addLayout(srow)
        self.lay.addWidget(self.setup_card)

        stats = QHBoxLayout()
        self.s_games = StatCard("Parties analysées")
        self.s_acc = StatCard("Précision (10 dernières)")
        self.s_blund = StatCard("Gaffes par partie")
        self.s_elo = StatCard("Elo Chess.com")
        self.s_est = StatCard("Niveau de jeu estimé")
        self.s_ex = StatCard("Exercices réussis")
        for c in (self.s_games, self.s_acc, self.s_blund, self.s_elo, self.s_est, self.s_ex):
            stats.addWidget(c)
        self.lay.addLayout(stats)

        goal = Card("Objectif 1000 Elo")
        grow = QHBoxLayout()
        self.goal_bar = QProgressBar()
        self.goal_bar.setFixedHeight(16)
        self.goal_lbl = label("", "h2")
        grow.addWidget(self.goal_bar, 1)
        grow.addWidget(self.goal_lbl)
        goal.lay.addLayout(grow)
        self.goal_txt = label("", "muted", wrap=True)
        goal.lay.addWidget(self.goal_txt)
        self.lay.addWidget(goal)

        today = Card("Ta séance du jour")
        self.today_txt = label("", wrap=True)
        today.lay.addWidget(self.today_txt)
        trow = QHBoxLayout()
        self.btn_train = QPushButton("🎯 10 exercices sur mes points faibles")
        self.btn_train.setObjectName("primary")
        self.btn_train.clicked.connect(lambda: self.ctx.trainTheme.emit(""))
        self.btn_lesson = QPushButton("📘 Leçon conseillée")
        self.btn_lesson.clicked.connect(self._open_lesson)
        self.btn_last = QPushButton("♟ Revoir ma dernière partie")
        self.btn_last.clicked.connect(self._open_last)
        for b in (self.btn_train, self.btn_lesson, self.btn_last):
            trow.addWidget(b)
        trow.addStretch()
        today.lay.addLayout(trow)
        self.lay.addWidget(today)

        charts = QHBoxLayout()
        c_acc = Card()
        self.acc_chart = LineChart("Précision par partie (%)", theme.ACCENT2, "%")
        c_acc.lay.addWidget(self.acc_chart)
        c_elo = Card()
        self.elo_chart = LineChart("Elo Chess.com", theme.ACCENT)
        c_elo.lay.addWidget(self.elo_chart)
        charts.addWidget(c_acc)
        charts.addWidget(c_elo)
        self.lay.addLayout(charts)

        grid = QGridLayout()
        grid.setSpacing(16)
        c_err = Card("Mes erreurs les plus fréquentes")
        self.err_bars = HBarList(theme.BAD)
        c_err.lay.addWidget(self.err_bars)
        c_sw = Card("Points forts et points faibles")
        self.sw_txt = label("", wrap=True)
        c_sw.lay.addWidget(self.sw_txt)
        grid.addWidget(c_err, 0, 0)
        grid.addWidget(c_sw, 0, 1)
        self.lay.addLayout(grid)

        c_m = Card("Les notions : ce que je maîtrise, ce que je dois travailler")
        self.mastery_box = QVBoxLayout()
        c_m.lay.addLayout(self.mastery_box)
        self.lay.addWidget(c_m)
        self.lay.addStretch()
        self._lesson_id = None
        self._last_gid = None
        self.refresh()

    def refresh(self):
        s = self.ctx.settings
        p = compute_progress(self.ctx.db)
        name = s.chesscom_username or "champion"
        self.hello.setText(f"Salut {name} 👋")
        self.sub.setText("Ton objectif : passer de 430 à 1000 Elo en apprenant à réfléchir comme un joueur d'échecs. "
                         "Joue → analyse → comprends → entraîne-toi.")
        missing = []
        if not find_stockfish(s):
            missing.append("• Installe le moteur d'analyse Stockfish (Paramètres → Télécharger Stockfish).")
        if not s.chesscom_username:
            missing.append("• Indique ton pseudo Chess.com pour importer tes parties.")
        if p.games == 0:
            missing.append("• Analyse tes premières parties : le coach apprendra tes erreurs habituelles.")
        self.setup_card.setVisible(bool(missing))
        self.setup_txt.setText("\n".join(missing))

        rating = p.chesscom_rating or s.current_elo
        self.s_games.set(str(p.games))
        self.s_acc.set(f"{p.recent_accuracy:.0f}%" if p.games else "—", "moyenne globale : " + (f"{p.avg_accuracy:.0f}%" if p.games else "—"))
        self.s_blund.set(f"{p.blunders_per_game:.1f}" if p.games else "—", "objectif 1000 Elo : moins de 1")
        self.s_elo.set(str(rating), "dernière partie importée" if p.chesscom_rating else "saisi dans les paramètres")
        self.s_est.set(f"~{p.estimated_elo}" if p.games else "—", "d'après ta précision récente (estimation)")
        self.s_ex.set(f"{p.exercises_success:.0f}%" if p.exercises_done else "—", f"{p.exercises_done} tentatives")

        start, target = 430 if rating >= 430 else rating, s.target_elo
        self.goal_bar.setRange(0, 100)
        self.goal_bar.setValue(int(max(0, min(100, (rating - start) / max(1, target - start) * 100))))
        self.goal_lbl.setText(f"{rating} → {target}")
        self.goal_txt.setText(elo_goal_text(rating, target))

        hist = p.history[-40:]
        labels = [dt.datetime.fromtimestamp(h["date"]).strftime("%d/%m") if h["date"] else "" for h in hist]
        self.acc_chart.set_data([h["accuracy"] for h in hist], labels, target=70, target_label="niveau ~1000 Elo", y_range=(0, 100))
        rated = [(lbl, h["rating"]) for lbl, h in zip(labels, hist) if h["rating"]]
        self.elo_chart.set_data([r for _, r in rated], [lbl for lbl, _ in rated], target=target, target_label=f"objectif {target}")

        self.err_bars.set_items(p.top_errors)
        ws = p.weaknesses
        st = p.strengths
        txt = ""
        if ws:
            txt += "<b style='color:%s'>À travailler en priorité</b><br>" % theme.BAD + "<br>".join(
                f"• {t.label} ({t.mastery}%)" for t in ws)
        if st:
            txt += "<br><br><b style='color:%s'>Points forts</b><br>" % theme.GOOD + "<br>".join(
                f"• {t.label} ({t.mastery}%)" for t in st)
        if not txt:
            txt = "Analyse quelques parties et fais des exercices : le coach identifiera tes forces et faiblesses."
        self.sw_txt.setText(txt)

        while self.mastery_box.count():
            it = self.mastery_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for t in sorted(p.themes, key=lambda t: (t.status == "à découvrir", t.mastery)):
            detail = f"{t.errors_per_game:.2f} erreur(s) pondérée(s) par partie · {t.attempts} exercices"
            if t.success_rate is not None:
                detail += f" · {t.success_rate * 100:.0f}% réussis"
            self.mastery_box.addWidget(MasteryRow(t.label, t.mastery, t.status, detail))

        weak = weakest_themes(self.ctx.db, 3)
        lessons = recommended_lessons(weak, self.ctx.db.lessons_done())
        self._lesson_id = lessons[0].id if lessons else None
        self.btn_lesson.setText(f"📘 Leçon : {lessons[0].title}" if lessons else "📘 Leçons")
        games = self.ctx.db.games(1)
        self._last_gid = games[0]["id"] if games else None
        self.btn_last.setEnabled(self._last_gid is not None)
        self.today_txt.setText(
            "1) Joue 1 à 3 parties en 10 minutes sur Chess.com.  2) Importe-les et lis les explications du coach "
            "sur tes erreurs.  3) Fais une série d'exercices ciblés.  Focus du moment : "
            + ", ".join(THEMES.get(t, t) for t in weak) + ".")

    def _open_lesson(self):
        if self._lesson_id:
            self.ctx.openLesson.emit(self._lesson_id)

    def _open_last(self):
        if self._last_gid:
            self.ctx.openGame.emit(self._last_gid)
