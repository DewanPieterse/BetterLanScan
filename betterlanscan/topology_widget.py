"""Force-directed network topology map drawn with QPainter."""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import (QColor, QPainter, QPen, QBrush, QPainterPath,
                            QRadialGradient, QFont)
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from .scanner import Device

_TYPE_COLORS = {
    "Router / Gateway":     "#ffc24c",
    "Computer (Windows)":   "#4c8dff",
    "Computer / Server":    "#4c8dff",
    "Apple device":         "#e6e9ef",
    "iPhone / iPad":        "#e6e9ef",
    "Printer":              "#ff8c8c",
    "Network device":       "#a9b2c7",
    "IoT / Embedded":       "#7fd1a8",
    "Media Server (Plex)":  "#cc7be8",
    "Amazon Echo / Fire":   "#f0963c",
    "Google / Chromecast":  "#f0963c",
    "Smart TV":             "#7ecfec",
    "Web device":           "#8b93a7",
    "Unknown":              "#5a6075",
}

_SELF_COLOR = "#4c8dff"


class _Node:
    def __init__(self, dev: "Device", x: float, y: float):
        self.dev = dev
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.r = 18.0 if dev.is_gateway else (16.0 if dev.is_self else 13.0)


class TopologyWidget(QWidget):
    device_selected = Signal(object)   # Device

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: list[_Node] = []
        self._selected: _Node | None = None
        self._drag: _Node | None = None
        self._drag_offset = QPointF()
        self._pan = QPointF(0, 0)
        self._scale = 1.0
        self._last_pan = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self.setMinimumSize(300, 200)
        self.setMouseTracking(True)

    def set_devices(self, devices: list["Device"]) -> None:
        cx, cy = self.width() / 2, self.height() / 2
        existing = {n.dev.ip: n for n in self._nodes}
        new_nodes: list[_Node] = []
        for dev in devices:
            if dev.ip in existing:
                n = existing[dev.ip]; n.dev = dev; new_nodes.append(n)
            else:
                angle = random.uniform(0, 2 * math.pi)
                dist  = random.uniform(60, 200)
                n = _Node(dev, cx + math.cos(angle) * dist,
                               cy + math.sin(angle) * dist)
                if dev.is_gateway:
                    n.x, n.y = cx, cy
                new_nodes.append(n)
        self._nodes = new_nodes
        if not self._timer.isActive():
            self._timer.start(30)
        self.update()

    # ---- layout step (simple spring model)
    def _step(self):
        nodes = self._nodes
        if len(nodes) < 2:
            self.update(); return
        cx, cy = self.width() / 2, self.height() / 2
        REPEL = 4000.0; ATTRACT = 0.006; DAMP = 0.88; ANCHOR = 0.002

        for a in nodes:
            fx = fy = 0.0
            for b in nodes:
                if b is a: continue
                dx, dy = a.x - b.x, a.y - b.y
                d2 = dx * dx + dy * dy or 0.01
                f = REPEL / d2
                fx += f * dx / (d2 ** 0.5 + 0.01)
                fy += f * dy / (d2 ** 0.5 + 0.01)
            # attraction to gateway (or centre)
            gw = next((n for n in nodes if n.dev.is_gateway), None)
            if gw and a is not gw:
                dx, dy = gw.x - a.x, gw.y - a.y
                d = (dx * dx + dy * dy) ** 0.5 or 1
                fx += ATTRACT * d * dx / d
                fy += ATTRACT * d * dy / d
            else:
                fx += ANCHOR * (cx - a.x)
                fy += ANCHOR * (cy - a.y)
            # anchor gateway to centre
            if a.dev.is_gateway:
                a.x = cx; a.y = cy; a.vx = 0.0; a.vy = 0.0; continue
            if a is self._drag: continue
            a.vx = (a.vx + fx) * DAMP
            a.vy = (a.vy + fy) * DAMP
            a.x += a.vx
            a.y += a.vy
        self.update()

    # ---- painting
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#14161c"))

        if not self._nodes:
            p.setPen(QColor("#5a6075"))
            p.drawText(self.rect(), Qt.AlignCenter, "Run a scan to see the network map")
            p.end(); return

        gw = next((n for n in self._nodes if n.dev.is_gateway), None)

        # edges gateway ↔ devices
        pen = QPen(QColor("#1e2535")); pen.setWidthF(1.0); p.setPen(pen)
        if gw:
            for n in self._nodes:
                if n is gw: continue
                p.drawLine(QPointF(gw.x, gw.y), QPointF(n.x, n.y))

        # nodes
        font = QFont(); font.setPointSize(9)
        p.setFont(font)
        for n in self._nodes:
            col = QColor(_SELF_COLOR if n.dev.is_self
                         else _TYPE_COLORS.get(n.dev.device_type, "#5a6075"))
            is_sel = n is self._selected

            # glow
            if is_sel:
                grd = QRadialGradient(n.x, n.y, n.r * 2.5)
                grd.setColorAt(0, QColor(col.red(), col.green(), col.blue(), 80))
                grd.setColorAt(1, QColor(0, 0, 0, 0))
                p.setBrush(QBrush(grd)); p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(n.x, n.y), n.r * 2.5, n.r * 2.5)

            # arp conflict ring
            if n.dev.arp_conflict:
                p.setPen(QPen(QColor("#ff4444"), 2)); p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(n.x, n.y), n.r + 3, n.r + 3)

            # main circle
            p.setBrush(QBrush(col))
            p.setPen(QPen(QColor("#14161c"), 2) if not is_sel
                     else QPen(QColor("#ffffff"), 2))
            p.drawEllipse(QPointF(n.x, n.y), n.r, n.r)

            # OS icon / fav
            p.setPen(QPen(QColor("#14161c")))
            icon = n.dev.os_icon or ("⭐" if n.dev.is_favourite else "")
            if icon:
                f2 = QFont(); f2.setPointSize(9); p.setFont(f2)
                ir = QRectF(n.x - n.r, n.y - n.r, n.r * 2, n.r * 2)
                p.drawText(ir, Qt.AlignCenter, icon)

            # label
            label = n.dev.custom_name or n.dev.hostname or n.dev.ip
            if len(label) > 18: label = label[:16] + "…"
            p.setPen(QPen(QColor("#cdd3e0")))
            f3 = QFont(); f3.setPointSize(8); p.setFont(f3)
            p.drawText(QRectF(n.x - 60, n.y + n.r + 2, 120, 16),
                       Qt.AlignCenter, label)
        p.end()

    # ---- interaction
    def _node_at(self, pos: QPointF) -> _Node | None:
        for n in self._nodes:
            if (n.x - pos.x()) ** 2 + (n.y - pos.y()) ** 2 <= (n.r + 4) ** 2:
                return n
        return None

    def mousePressEvent(self, e):
        n = self._node_at(e.position())
        if n:
            self._drag = n
            self._drag_offset = e.position() - QPointF(n.x, n.y)
            if n is not self._selected:
                self._selected = n
                self.device_selected.emit(n.dev)
        else:
            self._selected = None
            self._last_pan = e.position()
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag:
            p = e.position() - self._drag_offset
            self._drag.x = p.x(); self._drag.y = p.y()
            self._drag.vx = 0.0; self._drag.vy = 0.0
            self.update()
        elif self._last_pan is not None:
            pass

    def mouseReleaseEvent(self, _):
        self._drag = None; self._last_pan = None

    def wheelEvent(self, e):
        pass   # zoom reserved for future
