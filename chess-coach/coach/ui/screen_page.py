"""Page « Capture d'écran » : enregistrer une partie jouée à l'écran pour l'analyser ensuite."""
from __future__ import annotations

import chess
from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from ..chessutil import san_fr
from ..config import app_dir
from . import theme
from .board import ChessBoardWidget
from .widgets import Card, label


def bgr_to_qimage(img) -> QImage:
    import numpy as np
    rgb = np.ascontiguousarray(img[:, :, ::-1])
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class RegionDialog(QDialog):
    """Affiche la capture d'écran réduite ; l'utilisateur trace un carré autour de l'échiquier."""

    def __init__(self, img, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sélectionne l'échiquier")
        self.full = bgr_to_qimage(img)
        self.scale = min(1.0, 1100 / self.full.width(), 680 / self.full.height())
        self.pix = QPixmap.fromImage(self.full).scaled(int(self.full.width() * self.scale), int(self.full.height() * self.scale),
                                                       Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.view = QLabel()
        self.view.setPixmap(self.pix)
        self.view.setFixedSize(self.pix.size())
        self.view.mousePressEvent = self._press
        self.view.mouseMoveEvent = self._move
        self.start = self.end = None
        lay = QVBoxLayout(self)
        lay.addWidget(label("Clique-glisse du coin haut-gauche au coin bas-droit de l'échiquier (sans les coordonnées extérieures).", wrap=True))
        lay.addWidget(self.view)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _press(self, e):
        self.start = e.position().toPoint()
        self.end = self.start
        self._draw()

    def _move(self, e):
        self.end = e.position().toPoint()
        self._draw()

    def _draw(self):
        pm = QPixmap(self.pix)
        if self.start and self.end:
            p = QPainter(pm)
            p.setPen(QPen(QColor(theme.ACCENT), 3))
            side = max(abs(self.end.x() - self.start.x()), abs(self.end.y() - self.start.y()))
            p.drawRect(QRect(self.start, QPoint(self.start.x() + side, self.start.y() + side)))
            p.end()
        self.view.setPixmap(pm)

    def rect(self):
        if not self.start or not self.end:
            return None
        side = max(abs(self.end.x() - self.start.x()), abs(self.end.y() - self.start.y()))
        if side < 40:
            return None
        return (int(self.start.x() / self.scale), int(self.start.y() / self.scale), int(side / self.scale))


class ScreenPage(QWidget):
    def __init__(self, ctx, games_page):
        super().__init__()
        self.setObjectName("page")
        self.ctx = ctx
        self.games_page = games_page
        self.rect = None          # (x_abs, y_abs, size)
        self.recognizer = None
        self.tracker = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._build()
        self._load_saved()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(18)
        left = QVBoxLayout()
        left.addWidget(label("Capture d'écran", "h1"))
        left.addWidget(label(
            "Enregistre une partie directement depuis l'écran (Chess.com, Lichess…), même si tu n'as pas le PGN. "
            "L'application lit l'échiquier et reconstitue les coups. Par respect du fair-play, AUCUNE aide n'est "
            "affichée pendant la partie : l'analyse se fait seulement quand tu cliques sur « Terminer et analyser ».",
            "muted", wrap=True))
        steps = Card("Mode d'emploi")
        self.lbl_step1 = label("1. Ouvre une partie qui commence (position de départ visible à l'écran).", wrap=True)
        self.lbl_step2 = label("2. Clique sur « Détecter l'échiquier » (ou sélectionne-le à la main).", wrap=True)
        self.lbl_step3 = label("3. Clique sur « Calibrer » pendant que la position de départ est affichée.", wrap=True)
        self.lbl_step4 = label("4. « Démarrer l'enregistrement », joue ta partie, puis « Terminer et analyser ».", wrap=True)
        for w in (self.lbl_step1, self.lbl_step2, self.lbl_step3, self.lbl_step4):
            steps.lay.addWidget(w)
        left.addWidget(steps)
        row1 = QHBoxLayout()
        b = QPushButton("🔍 Détecter l'échiquier")
        b.clicked.connect(self.detect)
        row1.addWidget(b)
        b = QPushButton("✂ Sélectionner à la main")
        b.clicked.connect(self.select_manual)
        row1.addWidget(b)
        self.btn_cal = QPushButton("🎯 Calibrer")
        self.btn_cal.clicked.connect(self.calibrate)
        row1.addWidget(self.btn_cal)
        left.addLayout(row1)
        row2 = QHBoxLayout()
        self.btn_start = QPushButton("⏺ Démarrer l'enregistrement")
        self.btn_start.setObjectName("primary")
        self.btn_start.clicked.connect(self.start)
        self.btn_stop = QPushButton("⏹ Terminer et analyser")
        self.btn_stop.clicked.connect(self.stop_and_analyse)
        self.btn_undo = QPushButton("↶ Annuler le dernier coup")
        self.btn_undo.clicked.connect(self.undo)
        row2.addWidget(self.btn_start)
        row2.addWidget(self.btn_stop)
        row2.addWidget(self.btn_undo)
        left.addLayout(row2)
        self.status = label("", wrap=True)
        self.status.setStyleSheet(f"background:{theme.PANEL}; border-radius:10px; padding:10px;")
        left.addWidget(self.status)
        self.preview = QLabel()
        self.preview.setMinimumHeight(200)
        self.preview.setAlignment(Qt.AlignCenter)
        left.addWidget(self.preview, 1)
        root.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(label("Partie reconstituée", "h2"))
        self.board = ChessBoardWidget()
        right.addWidget(self.board, 2)
        self.moves = QListWidget()
        right.addWidget(self.moves, 1)
        root.addLayout(right, 2)
        self._update_buttons()

    def _update_buttons(self):
        rec = self.timer.isActive()
        self.btn_cal.setEnabled(self.rect is not None and not rec)
        self.btn_start.setEnabled(bool(self.rect and self.recognizer and self.recognizer.calibrated) and not rec)
        self.btn_stop.setEnabled(rec or bool(self.tracker and self.tracker.board.move_stack))
        self.btn_undo.setEnabled(bool(self.tracker and self.tracker.board.move_stack))

    # ------------------------------------------------------------------ persistance
    def _paths(self):
        return app_dir() / "vision_templates.json", app_dir() / "vision_region.txt"

    def _load_saved(self):
        try:
            from ..vision import PieceRecognizer
        except Exception:
            self.status.setText("Module de vision indisponible (opencv-python manquant).")
            return
        tpl, reg = self._paths()
        if reg.exists():
            try:
                self.rect = tuple(int(v) for v in reg.read_text().split(","))
            except ValueError:
                self.rect = None
        rec = PieceRecognizer()
        if tpl.exists() and rec.load(tpl):
            self.recognizer = rec
            self.status.setText("Calibration précédente chargée. Vérifie que l'échiquier est au même endroit, sinon refais la détection.")
        self._update_buttons()

    # ------------------------------------------------------------------ étapes
    def _grab(self):
        from ..vision import grab_full
        win = self.window()
        win.showMinimized()
        QTimer.singleShot(0, lambda: None)
        import time
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        time.sleep(0.6)
        try:
            img, ox, oy = grab_full()
        finally:
            win.showNormal()
            win.raise_()
            win.activateWindow()
        return img, ox, oy

    def detect(self):
        from ..vision import find_board
        try:
            img, ox, oy = self._grab()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Capture impossible", str(exc))
            return
        r = find_board(img)
        if r is None:
            self.status.setText("Je n'ai pas trouvé d'échiquier. Utilise « Sélectionner à la main » "
                                "(les thèmes d'échiquier unis, comme le vert par défaut de Chess.com, marchent le mieux).")
            return
        self._set_rect((r.x + ox, r.y + oy, r.size), img[r.y:r.y + r.size, r.x:r.x + r.size])

    def select_manual(self):
        try:
            img, ox, oy = self._grab()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Capture impossible", str(exc))
            return
        dlg = RegionDialog(img, self)
        if dlg.exec() and dlg.rect():
            x, y, s = dlg.rect()
            self._set_rect((x + ox, y + oy, s), img[y:y + s, x:x + s])

    def _set_rect(self, rect, crop):
        self.rect = rect
        self._paths()[1].write_text(",".join(str(v) for v in rect))
        self._show_preview(crop)
        self.status.setText(f"Échiquier trouvé ({rect[2]}×{rect[2]} pixels). Étape suivante : « Calibrer » avec la position de départ affichée.")
        self._update_buttons()

    def _show_preview(self, crop):
        q = bgr_to_qimage(crop)
        self.preview.setPixmap(QPixmap.fromImage(q).scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _capture_board(self):
        from ..vision import grab_screen
        x, y, s = self.rect
        return grab_screen((x, y, s, s))

    def calibrate(self):
        from ..vision import PieceRecognizer
        try:
            img = self._capture_board()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Capture impossible", str(exc))
            return
        self._show_preview(img)
        rec = PieceRecognizer()
        err = rec.calibrate(img)
        if err:
            self.status.setText("⚠ " + err)
            return
        self.recognizer = rec
        rec.save(self._paths()[0])
        side = "Blancs" if rec.white_bottom else "Noirs"
        self.status.setText(f"Calibration réussie ✓ Tu joues les {side} (pièces du bas). Clique sur « Démarrer l'enregistrement ».")
        self._update_buttons()

    def start(self):
        from ..vision import GameTracker
        self.tracker = GameTracker(chess.Board())
        self.moves.clear()
        self.board.set_board(chess.Board())
        self.board.set_flipped(not self.recognizer.white_bottom)
        self.timer.start(350)
        self.status.setText("⏺ Enregistrement en cours… Joue ta partie normalement. Aucune aide ne sera affichée.")
        self._update_buttons()

    def _tick(self):
        try:
            img = self._capture_board()
            obs = self.recognizer.read(img)
        except Exception as exc:  # noqa: BLE001
            self.status.setText(f"Lecture impossible : {exc}")
            return
        if self.tracker.is_new_game(obs):
            self.status.setText("Une nouvelle partie semble commencer : clique sur « Terminer et analyser » pour la précédente.")
            return
        before = self.tracker.board.copy()
        new = self.tracker.feed(obs)
        b = before
        for mv in new:
            n = b.fullmove_number
            txt = f"{n}. {san_fr(b.san(mv))}" if b.turn == chess.WHITE else f"{n}… {san_fr(b.san(mv))}"
            self.moves.addItem(txt)
            b.push(mv)
        if new:
            self.moves.scrollToBottom()
            self.board.set_board(self.tracker.board)
            self._update_buttons()
        if self.tracker.board.is_game_over():
            self.timer.stop()
            self.status.setText("Partie terminée ✓ Clique sur « Terminer et analyser ».")
            self._update_buttons()

    def undo(self):
        if self.tracker and self.tracker.board.move_stack:
            self.tracker.board.pop()
            if self.moves.count():
                self.moves.takeItem(self.moves.count() - 1)
            self.board.set_board(self.tracker.board)
            self._update_buttons()

    def stop_and_analyse(self):
        self.timer.stop()
        if not self.tracker or not self.tracker.board.move_stack:
            self._update_buttons()
            return
        user_white = self.recognizer.white_bottom
        me = self.ctx.settings.chesscom_username or "Moi"
        pgn = self.tracker.pgn(white=me if user_white else "Adversaire", black="Adversaire" if user_white else me)
        self.status.setText("Partie envoyée à l'analyse (voir « Mes parties »).")
        self.games_page.enqueue_pgn(pgn, "white" if user_white else "black", source="écran")
        self.tracker = None
        self._update_buttons()
        self.ctx.navigate.emit("games")
