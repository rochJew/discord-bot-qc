"""Échiquier interactif (QPainter + pièces SVG), barre d'évaluation et graphique."""
from __future__ import annotations

import math

import chess
import chess.svg
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QMenu, QSizePolicy, QWidget

LIGHT = QColor("#ebecd0")
DARK = QColor("#739552")
ARROW_COLORS = {
    "g": QColor(96, 190, 80, 200),
    "r": QColor(220, 70, 60, 200),
    "b": QColor(70, 140, 230, 200),
    "y": QColor(240, 190, 40, 210),
    "o": QColor(240, 130, 40, 200),
}
_RENDERERS: dict[str, QSvgRenderer] = {}


def piece_renderer(piece: chess.Piece) -> QSvgRenderer:
    key = piece.symbol()
    r = _RENDERERS.get(key)
    if r is None:
        svg = chess.svg.piece(piece)
        r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        _RENDERERS[key] = r
    return r


class ChessBoardWidget(QWidget):
    moveMade = Signal(object)        # chess.Move
    squareClicked = Signal(int)

    def __init__(self, parent=None, interactive: bool = False):
        super().__init__(parent)
        self.board = chess.Board()
        self.flipped = False
        self.interactive = interactive
        self.last_move: chess.Move | None = None
        self.arrows: list[tuple[int, int, str]] = []
        self.highlights: dict[int, QColor] = {}
        self.badge: tuple[int, str, QColor] | None = None   # (case, symbole, couleur)
        self.light, self.dark = LIGHT, DARK
        self.show_coords = True
        self._selected: int | None = None
        self._drag_from: int | None = None
        self._drag_pos: QPointF | None = None
        self._user_arrows: list[tuple[int, int, str]] = []
        self._rclick_from: int | None = None
        self.setMinimumSize(320, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------ API
    def set_board(self, board: chess.Board, last_move: chess.Move | None = None):
        self.board = board.copy()
        self.last_move = last_move if last_move is not None else (board.peek() if board.move_stack else None)
        self._selected = None
        self._user_arrows = []
        self.update()

    def set_fen(self, fen: str):
        self.set_board(chess.Board(fen), None)

    def set_arrows(self, arrows: list[tuple]):
        """arrows : [(case_depart, case_arrivee, couleur)] avec cases en int ou en nom ('e2')."""
        out = []
        for a, b, c in arrows:
            a = chess.parse_square(a) if isinstance(a, str) else a
            b = chess.parse_square(b) if isinstance(b, str) else b
            out.append((a, b, c))
        self.arrows = out
        self.update()

    def set_highlights(self, squares: dict):
        self.highlights = {(chess.parse_square(k) if isinstance(k, str) else k): QColor(v) for k, v in squares.items()}
        self.update()

    def set_badge(self, square: int | None, symbol: str = "", color: str = "#000"):
        self.badge = (square, symbol, QColor(color)) if square is not None else None
        self.update()

    def set_flipped(self, flipped: bool):
        self.flipped = flipped
        self.update()

    # ------------------------------------------------------------------ géométrie
    def _geom(self):
        size = min(self.width(), self.height())
        size -= size % 8
        x0 = (self.width() - size) / 2
        y0 = (self.height() - size) / 2
        return x0, y0, size / 8

    def square_rect(self, sq: int) -> QRectF:
        x0, y0, s = self._geom()
        f, r = chess.square_file(sq), chess.square_rank(sq)
        col, row = (7 - f, r) if self.flipped else (f, 7 - r)
        return QRectF(x0 + col * s, y0 + row * s, s, s)

    def square_at(self, pos: QPointF) -> int | None:
        x0, y0, s = self._geom()
        col = int((pos.x() - x0) // s)
        row = int((pos.y() - y0) // s)
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        return chess.square(7 - col, row) if self.flipped else chess.square(col, 7 - row)

    # ------------------------------------------------------------------ dessin
    def paintEvent(self, _):
        p = QPainter(self)
        self.paint_board(p)
        p.end()

    def paint_board(self, p: QPainter):
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        x0, y0, s = self._geom()
        coord_font = QFont()
        coord_font.setPixelSize(max(9, int(s * 0.18)))
        coord_font.setBold(True)
        for sq in chess.SQUARES:
            rect = self.square_rect(sq)
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
            p.fillRect(rect, self.light if light else self.dark)
            if self.last_move and sq in (self.last_move.from_square, self.last_move.to_square):
                p.fillRect(rect, QColor(255, 255, 51, 105))
            if sq in self.highlights:
                p.fillRect(rect, self.highlights[sq])
            if sq == self._selected:
                p.fillRect(rect, QColor(20, 85, 30, 110))
        if self.board.is_check():
            k = self.board.king(self.board.turn)
            if k is not None:
                rect = self.square_rect(k)
                p.setBrush(QColor(230, 40, 40, 150))
                p.setPen(Qt.NoPen)
                p.drawEllipse(rect.adjusted(s * 0.04, s * 0.04, -s * 0.04, -s * 0.04))
        if self.show_coords:
            p.setFont(coord_font)
            for i in range(8):
                # rangées à gauche, colonnes en bas
                sq_rank = chess.square(7 if self.flipped else 0, i)
                rect = self.square_rect(sq_rank)
                light = (chess.square_file(sq_rank) + i) % 2 == 1
                p.setPen(self.dark if light else self.light)
                p.drawText(rect.adjusted(3, 1, 0, 0), Qt.AlignLeft | Qt.AlignTop, str(i + 1))
                sq_file = chess.square(i, 7 if self.flipped else 0)
                rect = self.square_rect(sq_file)
                light = (i + chess.square_rank(sq_file)) % 2 == 1
                p.setPen(self.dark if light else self.light)
                p.drawText(rect.adjusted(0, 0, -3, -1), Qt.AlignRight | Qt.AlignBottom, "abcdefgh"[i])
        # Coups possibles de la pièce sélectionnée
        if self.interactive and self._selected is not None:
            p.setPen(Qt.NoPen)
            for mv in self.board.legal_moves:
                if mv.from_square == self._selected:
                    rect = self.square_rect(mv.to_square)
                    p.setBrush(QColor(0, 0, 0, 45))
                    if self.board.piece_at(mv.to_square):
                        p.setBrush(Qt.NoBrush)
                        p.setPen(QPen(QColor(0, 0, 0, 55), s * 0.08))
                        p.drawEllipse(rect.adjusted(s * 0.05, s * 0.05, -s * 0.05, -s * 0.05))
                        p.setPen(Qt.NoPen)
                    else:
                        p.drawEllipse(rect.center(), s * 0.16, s * 0.16)
        for sq, piece in self.board.piece_map().items():
            if sq == self._drag_from and self._drag_pos is not None:
                continue
            piece_renderer(piece).render(p, self.square_rect(sq))
        for a, b, c in self.arrows + self._user_arrows:
            self._draw_arrow(p, a, b, ARROW_COLORS.get(c, ARROW_COLORS["g"]), s)
        if self.badge and self.badge[0] is not None:
            sq, sym, col = self.badge
            rect = self.square_rect(sq)
            r = s * 0.19
            c = QPointF(rect.right() - r * 0.8, rect.top() + r * 0.8)
            p.setPen(QPen(QColor(255, 255, 255), 1.5))
            p.setBrush(col)
            p.drawEllipse(c, r, r)
            f = QFont()
            f.setPixelSize(int(r * 1.1))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignCenter, sym)
        if self._drag_from is not None and self._drag_pos is not None:
            piece = self.board.piece_at(self._drag_from)
            if piece:
                piece_renderer(piece).render(p, QRectF(self._drag_pos.x() - s / 2, self._drag_pos.y() - s / 2, s, s))

    def _draw_arrow(self, p: QPainter, a: int, b: int, color: QColor, s: float):
        ra, rb = self.square_rect(a), self.square_rect(b)
        start, end = ra.center(), rb.center()
        if a == b:
            p.setPen(QPen(color, s * 0.07))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(ra.adjusted(s * 0.06, s * 0.06, -s * 0.06, -s * 0.06))
            return
        dx, dy = end.x() - start.x(), end.y() - start.y()
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        # Cavalier : flèche en L
        fd, rd = abs(chess.square_file(a) - chess.square_file(b)), abs(chess.square_rank(a) - chess.square_rank(b))
        width = s * 0.16
        head = s * 0.42
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        if {fd, rd} == {1, 2}:
            if abs(dx) > abs(dy):
                corner = QPointF(end.x(), start.y())
            else:
                corner = QPointF(start.x(), end.y())
            path = QPainterPath()
            p.setPen(QPen(color, width, Qt.SolidLine, Qt.FlatCap, Qt.MiterJoin))
            p.setBrush(Qt.NoBrush)
            cx, cy = end.x() - corner.x(), end.y() - corner.y()
            cl = math.hypot(cx, cy)
            tip_base = QPointF(end.x() - cx / cl * head, end.y() - cy / cl * head)
            path.moveTo(start)
            path.lineTo(corner)
            path.lineTo(tip_base)
            p.drawPath(path)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            ux, uy = cx / cl, cy / cl
            base = tip_base
        else:
            start = QPointF(start.x() + ux * s * 0.2, start.y() + uy * s * 0.2)
            base = QPointF(end.x() - ux * head, end.y() - uy * head)
            px, py = -uy * width / 2, ux * width / 2
            p.drawPolygon(QPolygonF([QPointF(start.x() + px, start.y() + py), QPointF(base.x() + px, base.y() + py),
                                     QPointF(base.x() - px, base.y() - py), QPointF(start.x() - px, start.y() - py)]))
        px, py = -uy * head * 0.55, ux * head * 0.55
        p.drawPolygon(QPolygonF([end, QPointF(base.x() + px, base.y() + py), QPointF(base.x() - px, base.y() - py)]))

    # ------------------------------------------------------------------ souris
    def mousePressEvent(self, e):
        sq = self.square_at(e.position())
        if e.button() == Qt.RightButton:
            self._rclick_from = sq
            return
        if e.button() != Qt.LeftButton or sq is None:
            return
        self._user_arrows = []
        self.squareClicked.emit(sq)
        if not self.interactive:
            return
        piece = self.board.piece_at(sq)
        if self._selected is not None and self._selected != sq:
            if self._try_move(self._selected, sq):
                return
        if piece and piece.color == self.board.turn:
            self._selected = sq
            self._drag_from = sq
            self._drag_pos = e.position()
        else:
            self._selected = None
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag_from is not None and e.buttons() & Qt.LeftButton:
            self._drag_pos = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.RightButton:
            sq = self.square_at(e.position())
            if self._rclick_from is not None and sq is not None:
                arrow = (self._rclick_from, sq, "o")
                if arrow in self._user_arrows:
                    self._user_arrows.remove(arrow)
                else:
                    self._user_arrows.append(arrow)
                self.update()
            self._rclick_from = None
            return
        if self._drag_from is None:
            return
        sq = self.square_at(e.position())
        frm = self._drag_from
        self._drag_from = None
        self._drag_pos = None
        if sq is not None and sq != frm:
            if self._try_move(frm, sq):
                return
        self.update()

    def _try_move(self, frm: int, to: int) -> bool:
        piece = self.board.piece_at(frm)
        if piece is None:
            return False
        promo = None
        if piece.piece_type == chess.PAWN and chess.square_rank(to) in (0, 7):
            if chess.Move(frm, to, chess.QUEEN) in self.board.legal_moves:
                promo = self._ask_promotion()
                if promo is None:
                    return False
        mv = chess.Move(frm, to, promo)
        if mv in self.board.legal_moves:
            self._selected = None
            self.moveMade.emit(mv)
            self.update()
            return True
        return False

    def _ask_promotion(self):
        menu = QMenu(self)
        names = [("Dame", chess.QUEEN), ("Tour", chess.ROOK), ("Fou", chess.BISHOP), ("Cavalier", chess.KNIGHT)]
        acts = {menu.addAction(n): t for n, t in names}
        from PySide6.QtGui import QCursor
        chosen = menu.exec(QCursor.pos())
        return acts.get(chosen)

    # ------------------------------------------------------------------ rendu image
    def render_image(self, size: int = 640) -> QImage:
        img = QImage(size, size, QImage.Format_RGB32)
        img.fill(QColor("#262421"))
        old = self.size()
        self.resize(size, size)
        p = QPainter(img)
        self.paint_board(p)
        p.end()
        self.resize(old)
        return img

    def heightForWidth(self, w):
        return w

    def hasHeightForWidth(self):
        return True


class EvalBar(QWidget):
    """Barre verticale : la part blanche = avantage des Blancs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cp = 0
        self.mate: int | None = None
        self.flipped = False
        self.setFixedWidth(26)
        self.setMinimumHeight(200)

    def set_eval(self, cp: int, mate: int | None = None):
        self.cp, self.mate = cp, mate
        self.update()

    def paintEvent(self, _):
        from ..chessutil import win_percent
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h, w = self.height(), self.width()
        if self.mate is not None:
            frac = 1.0 if self.mate > 0 else 0.0 if self.mate < 0 else (1.0 if self.cp > 0 else 0.0)
        else:
            frac = win_percent(self.cp) / 100
        white_h = h * frac
        p.fillRect(0, 0, w, h, QColor("#403d39"))
        if self.flipped:
            p.fillRect(QRectF(0, 0, w, white_h), QColor("#f0f0f0"))
        else:
            p.fillRect(QRectF(0, h - white_h, w, white_h), QColor("#f0f0f0"))
        txt = (f"M{abs(self.mate)}" if self.mate is not None and self.mate != 0
               else f"{abs(self.cp) / 100:.1f}")
        f = QFont()
        f.setPixelSize(10)
        f.setBold(True)
        p.setFont(f)
        white_adv = (self.mate is not None and self.mate > 0) or (self.mate is None and self.cp >= 0)
        at_bottom = white_adv != self.flipped
        p.setPen(QColor("#222") if white_adv else QColor("#eee"))
        rect = QRectF(0, h - 20, w, 18) if at_bottom else QRectF(0, 2, w, 18)
        p.drawText(rect, Qt.AlignCenter, txt)
        p.end()


class EvalGraph(QWidget):
    """Graphique de l'évaluation au fil de la partie ; clic = aller au coup."""
    plyClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.values: list[float] = []      # chances de gain des Blancs (0-100) après chaque coup
        self.marks: dict[int, QColor] = {}
        self.current = -1
        self.setMinimumHeight(70)
        self.setMaximumHeight(110)

    def set_data(self, values: list[float], marks: dict[int, str]):
        self.values = values
        self.marks = {k: QColor(v) for k, v in marks.items()}
        self.update()

    def set_current(self, ply: int):
        self.current = ply
        self.update()

    def _x(self, i: int) -> float:
        n = max(1, len(self.values) - 1)
        return 4 + (self.width() - 8) * i / n

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#3a3835"))
        if not self.values:
            p.end()
            return
        poly = QPolygonF([QPointF(self._x(0), h)])
        for i, v in enumerate(self.values):
            poly.append(QPointF(self._x(i), h - h * v / 100))
        poly.append(QPointF(self._x(len(self.values) - 1), h))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e8e6e3"))
        p.drawPolygon(poly)
        p.setPen(QPen(QColor(120, 120, 120, 120), 1, Qt.DashLine))
        p.drawLine(0, h / 2, w, h / 2)
        for i, col in self.marks.items():
            if 0 <= i < len(self.values):
                p.setPen(QPen(QColor("#222"), 1))
                p.setBrush(col)
                p.drawEllipse(QPointF(self._x(i), h - h * self.values[i] / 100), 4, 4)
        if 0 <= self.current < len(self.values):
            p.setPen(QPen(QColor("#5aa9ff"), 2))
            x = self._x(self.current)
            p.drawLine(x, 0, x, h)
        p.end()

    def mousePressEvent(self, e):
        if not self.values:
            return
        n = len(self.values)
        i = round((e.position().x() - 4) / max(1, self.width() - 8) * (n - 1))
        self.plyClicked.emit(max(0, min(n - 1, i)))


def qimage_to_bgr(img: QImage):
    import numpy as np
    img = img.convertToFormat(QImage.Format_RGB32)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    arr = np.frombuffer(ptr, np.uint8, count=img.sizeInBytes()).reshape(h, img.bytesPerLine() // 4, 4)[:, :w, :3]
    return arr.copy()
