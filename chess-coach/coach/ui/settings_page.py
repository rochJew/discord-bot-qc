"""Page « Paramètres »."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit,
                               QMessageBox, QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from ..config import app_dir, find_stockfish
from . import theme
from .widgets import Card, label
from .workers import run_task


class SettingsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.setObjectName("page")
        self.ctx = ctx
        s = ctx.settings
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)
        root.addWidget(label("Paramètres", "h1"))

        c1 = Card("Mon profil")
        f1 = QFormLayout()
        self.user = QLineEdit(s.chesscom_username)
        self.user.setPlaceholderText("ex : MonPseudo")
        self.elo = QSpinBox()
        self.elo.setRange(100, 3000)
        self.elo.setValue(s.current_elo)
        self.target = QSpinBox()
        self.target.setRange(200, 3000)
        self.target.setValue(s.target_elo)
        f1.addRow("Pseudo Chess.com", self.user)
        f1.addRow("Mon Elo actuel", self.elo)
        f1.addRow("Objectif", self.target)
        c1.lay.addLayout(f1)
        root.addWidget(c1)

        c2 = Card("Moteur d'analyse (Stockfish)")
        row = QHBoxLayout()
        self.sf = QLineEdit(s.stockfish_path)
        self.sf.setPlaceholderText("Détection automatique")
        b_browse = QPushButton("Parcourir…")
        b_browse.clicked.connect(self.browse)
        b_dl = QPushButton("⬇ Télécharger Stockfish")
        b_dl.clicked.connect(self.download)
        row.addWidget(self.sf, 1)
        row.addWidget(b_browse)
        row.addWidget(b_dl)
        c2.lay.addLayout(row)
        self.sf_status = label("", "muted", wrap=True)
        c2.lay.addWidget(self.sf_status)
        self.dl_bar = QProgressBar()
        self.dl_bar.hide()
        c2.lay.addWidget(self.dl_bar)
        f2 = QFormLayout()
        self.depth = QSpinBox()
        self.depth.setRange(8, 30)
        self.depth.setValue(s.analysis_depth)
        self.time = QDoubleSpinBox()
        self.time.setRange(0.1, 10)
        self.time.setSingleStep(0.1)
        self.time.setValue(s.analysis_time)
        self.threads = QSpinBox()
        self.threads.setRange(1, 32)
        self.threads.setValue(s.engine_threads)
        f2.addRow("Profondeur d'analyse", self.depth)
        f2.addRow("Temps max par position (s)", self.time)
        f2.addRow("Threads", self.threads)
        c2.lay.addLayout(f2)
        root.addWidget(c2)

        c3 = Card("Coach IA (explications détaillées et questions libres)")
        c3.lay.addWidget(label("Optionnel : sans clé, le coach intégré explique déjà chaque erreur. Avec une clé API "
                               "Anthropic (console.anthropic.com), tu obtiens des explications rédigées par Claude "
                               "et tu peux poser tes propres questions. La clé reste sur ton PC.", "muted", wrap=True))
        row3 = QHBoxLayout()
        self.key = QLineEdit(s.anthropic_api_key)
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("sk-ant-… (ou variable d'environnement ANTHROPIC_API_KEY)")
        b_test = QPushButton("Tester")
        b_test.clicked.connect(self.test_ai)
        row3.addWidget(self.key, 1)
        row3.addWidget(b_test)
        c3.lay.addLayout(row3)
        self.use_ai = QCheckBox("Activer le coach IA")
        self.use_ai.setChecked(s.use_ai_coach)
        c3.lay.addWidget(self.use_ai)
        self.ai_status = label("", "muted", wrap=True)
        c3.lay.addWidget(self.ai_status)
        root.addWidget(c3)

        bottom = QHBoxLayout()
        bottom.addWidget(label(f"Données : {app_dir()}", "muted"))
        bottom.addStretch()
        save = QPushButton("Enregistrer")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        bottom.addWidget(save)
        root.addLayout(bottom)
        root.addStretch()
        self._check_sf()

    def _check_sf(self):
        p = find_stockfish(self.ctx.settings)
        if p:
            self.sf_status.setText(f"✔ Stockfish trouvé : {p}")
            self.sf_status.setStyleSheet(f"color: {theme.GOOD};")
        else:
            self.sf_status.setText("✖ Stockfish introuvable : clique sur « Télécharger Stockfish » (≈ 40 Mo) ou indique son emplacement.")
            self.sf_status.setStyleSheet(f"color: {theme.BAD};")

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choisir l'exécutable Stockfish", "", "Exécutables (*.exe);;Tous (*)")
        if path:
            self.sf.setText(path)
            self.save()

    def download(self):
        from ..stockfish_dl import download_stockfish
        self.dl_bar.show()
        self.sf_status.setText("Téléchargement en cours…")

        def done(path):
            self.dl_bar.hide()
            self.sf.setText(path)
            self.save()

        def err(msg):
            self.dl_bar.hide()
            self.sf_status.setText("✖ " + msg + " — tu peux aussi le télécharger sur stockfishchess.org et l'indiquer avec « Parcourir ».")
            self.sf_status.setStyleSheet(f"color: {theme.BAD};")

        run_task(download_stockfish, on_done=done, on_error=err,
                 on_progress=lambda a, b: (self.dl_bar.setMaximum(b), self.dl_bar.setValue(a)))

    def test_ai(self):
        self.save(silent=True)
        coach = self.ctx.ai_coach()
        if coach is None:
            self.ai_status.setText("Renseigne une clé et coche « Activer le coach IA ».")
            return
        self.ai_status.setText("Test en cours…")
        run_task(coach._call, [{"role": "user", "content": "Dis bonjour en une phrase à ton élève."}], 200,
                 on_done=lambda t: self.ai_status.setText("✔ " + t),
                 on_error=lambda m: self.ai_status.setText("✖ " + m))

    def save(self, silent: bool = False):
        s = self.ctx.settings
        s.chesscom_username = self.user.text().strip()
        s.current_elo = self.elo.value()
        s.target_elo = self.target.value()
        s.stockfish_path = self.sf.text().strip()
        s.analysis_depth = self.depth.value()
        s.analysis_time = self.time.value()
        s.engine_threads = self.threads.value()
        s.anthropic_api_key = self.key.text().strip()
        s.use_ai_coach = self.use_ai.isChecked()
        s.save()
        self.ctx.reset_engine()
        self._check_sf()
        self.ctx.dataChanged.emit()
        if not silent:
            QMessageBox.information(self, "Paramètres", "Paramètres enregistrés.")
