"""Wi-Fi visualizations: channel overlap graph + RSSI history chart."""
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QColor, QPainter, QPen, QBrush, QPainterPath,
                            QLinearGradient, QFont)
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget

if TYPE_CHECKING:
    from .wifi import WifiNetwork

# distinct colours per network (cycle)
_PALETTE = [
    "#4c8dff", "#3ddc84", "#ffc24c", "#ff6b6b", "#cc7be8",
    "#7ecfec", "#f0963c", "#e6e9ef", "#ff8c8c", "#7fd1a8",
    "#c084fc", "#fb923c", "#34d399", "#60a5fa", "#f472b6",
]


def _net_color(index: int) -> str:
    return _PALETTE[index % len(_PALETTE)]


# 2.4 GHz channels 1-14 with their centre + ±2 overlap footprint
_24_CHANNELS = list(range(1, 14))
_5_CHANNELS   = [
    36, 40, 44, 48, 52, 56, 60, 64,
    100,104,108,112,116,120,124,128,132,136,140,144,
    149,153,157,161,165,
]
_6_CHANNELS = [1, 5, 9, 13, 17, 21, 25, 29, 33, 37, 41, 45, 49,
               53, 57, 61, 65, 69, 73, 77, 81, 85, 89, 93]


def _gaussian(x: float, center: float, sigma: float = 2.0) -> float:
    return math.exp(-0.5 * ((x - center) / sigma) ** 2)


class ChannelGraph(QWidget):
    """Bell-curve channel overlap view for Wi-Fi networks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._networks: list["WifiNetwork"] = []
        self._band = "2.4 GHz"
        self.setMinimumHeight(160)

    def set_networks(self, networks: list["WifiNetwork"], band: str = "2.4 GHz") -> None:
        self._networks = [n for n in networks if n.band == band or not n.band]
        self._band = band
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#1c1f28"))
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 48, 16, 12, 32

        nets = [n for n in self._networks
                if (self._band == "2.4 GHz" and n.channel <= 14)
                or (self._band == "5 GHz" and 32 <= n.channel <= 177)
                or (self._band == "6 GHz" and n.channel >= 1 and n.channel <= 93)]

        if self._band == "2.4 GHz":
            channels = _24_CHANNELS; sigma = 2.5
        elif self._band == "5 GHz":
            channels = _5_CHANNELS; sigma = 1.5
        else:
            channels = _6_CHANNELS; sigma = 1.5

        if not channels:
            p.setPen(QColor("#5a6075"))
            p.drawText(self.rect(), Qt.AlignCenter, "No data"); p.end(); return

        ch_min, ch_max = min(channels), max(channels)
        ch_range = ch_max - ch_min or 1
        graph_w = w - pad_l - pad_r
        graph_h = h - pad_t - pad_b

        def ch_to_x(ch: float) -> float:
            return pad_l + (ch - ch_min) / ch_range * graph_w

        # grid lines + channel labels
        p.setPen(QPen(QColor("#262a36")))
        f = QFont(); f.setPointSize(8); p.setFont(f)
        label_chs = channels[::2] if len(channels) > 10 else channels
        for ch in label_chs:
            x = ch_to_x(ch)
            p.drawLine(QPointF(x, pad_t), QPointF(x, h - pad_b))
            p.setPen(QPen(QColor("#5a6075")))
            p.drawText(QRectF(x - 12, h - pad_b + 2, 24, 16), Qt.AlignCenter, str(ch))
            p.setPen(QPen(QColor("#262a36")))

        # y-axis: RSSI scale -100 → -30 dBm
        rssi_min, rssi_max = -100, -20
        def rssi_to_y(rssi: float) -> float:
            frac = (rssi - rssi_min) / (rssi_max - rssi_min)
            return h - pad_b - frac * graph_h

        p.setPen(QPen(QColor("#5a6075")))
        for dbm in [-90, -70, -50, -30]:
            y = rssi_to_y(dbm)
            p.drawText(QRectF(0, y - 6, pad_l - 4, 12), Qt.AlignRight | Qt.AlignVCenter,
                       f"{dbm}")

        # draw each network as filled gaussian
        steps = 200
        for i, net in enumerate(nets):
            col = QColor(_net_color(i))
            col.setAlpha(160)
            peak_y = rssi_to_y(net.rssi) if net.rssi else rssi_to_y(-60)
            amplitude = h - pad_b - peak_y

            path = QPainterPath()
            path.moveTo(QPointF(ch_to_x(net.channel - 4), h - pad_b))
            x_range = [ch_min - 2 + j * (ch_range + 4) / steps for j in range(steps + 1)]
            for ch_f in x_range:
                g = _gaussian(ch_f, net.channel, sigma)
                y = (h - pad_b) - g * amplitude
                path.lineTo(QPointF(ch_to_x(ch_f), y))
            path.lineTo(QPointF(ch_to_x(ch_max + 2), h - pad_b))
            path.closeSubpath()

            # gradient fill
            grad = QLinearGradient(0, peak_y, 0, h - pad_b)
            c2 = QColor(col); c2.setAlpha(60)
            grad.setColorAt(0, col); grad.setColorAt(1, c2)
            p.setBrush(QBrush(grad))
            p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 220), 1.5))
            p.drawPath(path)

            # label at peak
            lx = ch_to_x(net.channel)
            ly = (h - pad_b) - amplitude - 14
            p.setPen(QPen(QColor("#ffffff")))
            f2 = QFont(); f2.setPointSize(8); f2.setBold(True); p.setFont(f2)
            label = (net.ssid or "(hidden)")[:14]
            p.drawText(QRectF(lx - 40, max(pad_t, ly), 80, 14), Qt.AlignCenter, label)

        # axis
        p.setPen(QPen(QColor("#3a4155")))
        p.drawLine(QPointF(pad_l, h - pad_b), QPointF(w - pad_r, h - pad_b))
        p.drawLine(QPointF(pad_l, pad_t), QPointF(pad_l, h - pad_b))

        # band label
        p.setPen(QPen(QColor("#8b93a7")))
        f3 = QFont(); f3.setPointSize(10); f3.setBold(True); p.setFont(f3)
        p.drawText(QRectF(pad_l + 4, pad_t, 100, 18), Qt.AlignLeft, self._band)
        p.end()


class RSSIHistoryChart(QWidget):
    """Time-series RSSI chart for a selected network."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[tuple[float, int]] = []  # (timestamp, rssi)
        self._ssid = ""
        self.setMinimumHeight(120)

    def set_data(self, data: list[tuple[float, int]], ssid: str = "") -> None:
        self._data = data[-200:]
        self._ssid = ssid
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#1c1f28"))
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 44, 12, 20, 28
        pts = self._data
        if len(pts) < 2:
            p.setPen(QColor("#5a6075"))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "No history yet — scan Wi-Fi to start recording")
            p.end(); return

        t0, t1 = pts[0][0], pts[-1][0]
        t_range = t1 - t0 or 1
        r_min = min(v for _, v in pts) - 5
        r_max = max(v for _, v in pts) + 5
        r_range = r_max - r_min or 1
        gw, gh = w - pad_l - pad_r, h - pad_t - pad_b

        def to_pt(ts, rssi):
            x = pad_l + (ts - t0) / t_range * gw
            y = h - pad_b - (rssi - r_min) / r_range * gh
            return QPointF(x, y)

        # gridlines
        p.setPen(QPen(QColor("#262a36")))
        for dbm in range(int(r_min), int(r_max) + 1, 10):
            y = h - pad_b - (dbm - r_min) / r_range * gh
            p.drawLine(QPointF(pad_l, y), QPointF(w - pad_r, y))
            p.setPen(QPen(QColor("#5a6075")))
            f = QFont(); f.setPointSize(8); p.setFont(f)
            p.drawText(QRectF(0, y - 6, pad_l - 4, 12),
                       Qt.AlignRight | Qt.AlignVCenter, f"{dbm}")
            p.setPen(QPen(QColor("#262a36")))

        # fill + line
        path = QPainterPath()
        path.moveTo(QPointF(to_pt(*pts[0]).x(), h - pad_b))
        for ts, rssi in pts:
            path.lineTo(to_pt(ts, rssi))
        path.lineTo(QPointF(to_pt(*pts[-1]).x(), h - pad_b))
        path.closeSubpath()
        grad = QLinearGradient(0, pad_t, 0, h - pad_b)
        grad.setColorAt(0, QColor(76, 141, 255, 120))
        grad.setColorAt(1, QColor(76, 141, 255, 10))
        p.setBrush(QBrush(grad)); p.setPen(Qt.NoPen); p.drawPath(path)

        pen = QPen(QColor("#4c8dff")); pen.setWidthF(1.5); p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        pp = QPainterPath()
        pp.moveTo(to_pt(*pts[0]))
        for ts, rssi in pts[1:]:
            pp.lineTo(to_pt(ts, rssi))
        p.drawPath(pp)

        # axes
        p.setPen(QPen(QColor("#3a4155")))
        p.drawLine(QPointF(pad_l, h - pad_b), QPointF(w - pad_r, h - pad_b))
        p.drawLine(QPointF(pad_l, pad_t), QPointF(pad_l, h - pad_b))

        # SSID label
        p.setPen(QPen(QColor("#8b93a7")))
        f2 = QFont(); f2.setPointSize(9); f2.setBold(True); p.setFont(f2)
        p.drawText(QRectF(pad_l + 4, 4, w, 14),
                   Qt.AlignLeft, f"Signal history: {self._ssid}")
        p.end()
