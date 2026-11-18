"""Petits composants réutilisables (cartes, graphiques simples)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QToolTip, QVBoxLayout, QWidget

from . import theme


def label(text: str, obj: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb


class Card(QFrame):
    def __init__(self, title: str | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(16, 14, 16, 14)
        self.lay.setSpacing(8)
        if title:
            self.lay.addWidget(label(title, "h2"))


class StatCard(Card):
    def __init__(self, caption: str, value: str = "—", sub: str = ""):
        super().__init__()
        self.value = label(value, "statValue")
        self.caption = label(caption, "statLabel")
        self.sub = label(sub, "muted", wrap=True)
        self.sub.setStyleSheet("font-size: 12px;")
        self.lay.addWidget(self.caption)
        self.lay.addWidget(self.value)
        self.lay.addWidget(self.sub)

    def set(self, value: str, sub: str = ""):
        self.value.setText(value)
        self.sub.setText(sub)


class MasteryRow(QWidget):
    STATUS_COLORS = {"maîtrisé": theme.GOOD, "en progrès": theme.WARN, "à travailler": theme.BAD, "à découvrir": theme.MUTED}

    def __init__(self, name: str, mastery: int, status: str, detail: str = ""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        n = label(name)
        n.setMinimumWidth(230)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(mastery)
        bar.setTextVisible(False)
        bar.setFixedHeight(10)
        col = self.STATUS_COLORS.get(status, theme.MUTED)
        bar.setStyleSheet(f"QProgressBar::chunk {{ background: {col}; border-radius: 5px; }}")
        icon = {"maîtrisé": "✔", "en progrès": "◐", "à travailler": "✖", "à découvrir": "○"}.get(status, "")
        st = label(f"{icon} {status}")
        st.setStyleSheet(f"color: {col}; font-size: 12px;")
        st.setMinimumWidth(110)
        lay.addWidget(n)
        lay.addWidget(bar, 1)
        lay.addWidget(st)
        if detail:
            self.setToolTip(detail)


class LineChart(QWidget):
    """Courbe simple (une seule série) avec ligne d'objectif optionnelle et info-bulle."""

    def __init__(self, title: str, color: str = theme.ACCENT2, y_suffix: str = "", parent=None):
        super().__init__(parent)
        self.title = title
        self.color = QColor(color)
        self.y_suffix = y_suffix
        self.points: list[float] = []
        self.labels: list[str] = []
        self.target: float | None = None
        self.target_label = ""
        self.y_range: tuple[float, float] | None = None
        self.setMinimumHeight(190)
        self.setMouseTracking(True)

    def set_data(self, points, labels=None, target=None, target_label="", y_range=None):
        self.points = list(points)
        self.labels = list(labels or [str(i + 1) for i in range(len(self.points))])
        self.target, self.target_label, self.y_range = target, target_label, y_range
        self.update()

    def _bounds(self):
        vals = self.points + ([self.target] if self.target is not None else [])
        if self.y_range:
            return self.y_range
        lo, hi = min(vals), max(vals)
        pad = max(5.0, (hi - lo) * 0.15)
        return lo - pad, hi + pad

    def _area(self):
        return QRectF(44, 30, self.width() - 60, self.height() - 52)

    def _pt(self, i, v, lo, hi, area):
        n = max(1, len(self.points) - 1)
        x = area.left() + area.width() * (i / n if len(self.points) > 1 else 0.5)
        y = area.bottom() - area.height() * (v - lo) / (hi - lo or 1)
        return QPointF(x, y)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont()
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(8, 4, self.width() - 16, 22), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        area = self._area()
        small = QFont()
        small.setPixelSize(11)
        p.setFont(small)
        if not self.points:
            p.setPen(QColor(theme.MUTED))
            p.drawText(area, Qt.AlignCenter, "Pas encore de données : analyse quelques parties.")
            p.end()
            return
        lo, hi = self._bounds()
        # grille discrète
        for k in range(4):
            v = lo + (hi - lo) * k / 3
            y = area.bottom() - area.height() * k / 3
            p.setPen(QPen(QColor(255, 255, 255, 22), 1))
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(0, y - 8, 40, 16), Qt.AlignRight | Qt.AlignVCenter, f"{v:.0f}")
        if self.target is not None and lo <= self.target <= hi:
            y = area.bottom() - area.height() * (self.target - lo) / (hi - lo)
            p.setPen(QPen(QColor(theme.MUTED), 1, Qt.DashLine))
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(area.right() - 160, y - 18, 160, 16), Qt.AlignRight, self.target_label)
        path = QPainterPath()
        for i, v in enumerate(self.points):
            pt = self._pt(i, v, lo, hi, area)
            path.moveTo(pt) if i == 0 else path.lineTo(pt)
        p.setPen(QPen(self.color, 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setBrush(self.color)
        p.setPen(QPen(QColor(theme.PANEL), 2))
        if len(self.points) <= 40:
            for i, v in enumerate(self.points):
                p.drawEllipse(self._pt(i, v, lo, hi, area), 4, 4)
        # dernière valeur en étiquette directe
        last = self._pt(len(self.points) - 1, self.points[-1], lo, hi, area)
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(last.x() - 60, last.y() - 22, 56, 16), Qt.AlignRight, f"{self.points[-1]:.0f}{self.y_suffix}")
        p.end()

    def mouseMoveEvent(self, e):
        if not self.points:
            return
        area = self._area()
        n = len(self.points)
        i = round((e.position().x() - area.left()) / max(1, area.width()) * (n - 1)) if n > 1 else 0
        i = max(0, min(n - 1, i))
        QToolTip.showText(e.globalPosition().toPoint(), f"{self.labels[i]} : {self.points[i]:.0f}{self.y_suffix}", self)


class HBarList(QWidget):
    """Liste de barres horizontales (une seule couleur), valeur en étiquette."""

    def __init__(self, color: str = theme.BAD):
        super().__init__()
        self.items: list[tuple[str, float]] = []
        self.color = QColor(color)
        self.setMinimumHeight(60)

    def set_items(self, items):
        self.items = list(items)
        self.setMinimumHeight(max(60, 30 * len(self.items) + 6))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f = QFont()
        f.setPixelSize(12)
        p.setFont(f)
        if not self.items:
            p.setPen(QColor(theme.MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "Aucune erreur enregistrée pour l'instant.")
            p.end()
            return
        mx = max(v for _, v in self.items) or 1
        lw = 230
        for i, (name, v) in enumerate(self.items):
            y = 4 + i * 30
            p.setPen(QColor(theme.TEXT))
            p.drawText(QRectF(0, y, lw - 8, 22), Qt.AlignLeft | Qt.AlignVCenter, name)
            w = (self.width() - lw - 50) * v / mx
            p.setPen(Qt.NoPen)
            p.setBrush(self.color)
            p.drawRoundedRect(QRectF(lw, y + 5, max(4, w), 12), 4, 4)
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(lw + w + 6, y, 44, 22), Qt.AlignLeft | Qt.AlignVCenter, f"{v:.0f}")
        p.end()
