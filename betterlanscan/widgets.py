"""Small custom painted widgets: signal bars and status dots."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QBrush, QPen
from PySide6.QtWidgets import QWidget


def quality_color(q: int) -> QColor:
    if q >= 67:
        return QColor("#3ddc84")
    if q >= 34:
        return QColor("#ffc24c")
    return QColor("#ff6b6b")


class SignalBars(QWidget):
    """Four-bar Wi-Fi style signal indicator driven by a 0-100 quality."""

    def __init__(self, quality: int = 0, parent=None):
        super().__init__(parent)
        self._q = quality
        self.setFixedSize(46, 22)

    def set_quality(self, q: int):
        self._q = max(0, min(100, q))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bars = 4
        active = round(self._q / 100 * bars)
        col = quality_color(self._q)
        bw, gap = 8, 3
        for i in range(bars):
            h = 6 + i * 4
            x = i * (bw + gap)
            y = self.height() - h
            rect = QRectF(x, y, bw, h)
            if i < active:
                p.setBrush(QBrush(col))
                p.setPen(Qt.NoPen)
            else:
                p.setBrush(QBrush(QColor("#2c3140")))
                p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect, 2, 2)
        p.end()


class StatusDot(QWidget):
    def __init__(self, color: str = "#3ddc84", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(14, 14)

    def set_color(self, color: str):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(self._color))
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.drawEllipse(2, 2, 9, 9)
        p.end()


class SignalMeter(QWidget):
    """Horizontal quality meter bar with rounded fill (for table cells)."""

    def __init__(self, quality: int = 0, label: str = "", parent=None):
        super().__init__(parent)
        self._q = quality
        self._label = label
        self.setMinimumWidth(90)
        self.setFixedHeight(22)

    def set_value(self, quality: int, label: str = ""):
        self._q = max(0, min(100, quality))
        self._label = label
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        track = QRectF(2, h / 2 - 4, w - 4, 8)
        p.setBrush(QBrush(QColor("#2c3140")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(track, 4, 4)
        fill_w = (w - 4) * self._q / 100
        if fill_w > 0:
            p.setBrush(QBrush(quality_color(self._q)))
            p.drawRoundedRect(QRectF(2, h / 2 - 4, max(fill_w, 8), 8), 4, 4)
        if self._label:
            p.setPen(QPen(QColor("#cdd3e0")))
            f = p.font(); f.setPointSize(9); p.setFont(f)
            p.drawText(self.rect().adjusted(0, 0, -2, 0),
                       Qt.AlignRight | Qt.AlignVCenter, self._label)
        p.end()
