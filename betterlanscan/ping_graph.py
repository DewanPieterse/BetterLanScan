"""Live RTT sparkline + continuous pinger widget."""
from __future__ import annotations

import collections
import socket
import subprocess
import re
import threading
import time

from PySide6.QtCore import Qt, QTimer, QObject, Signal, QThread, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPainterPath, QLinearGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

MAX_POINTS = 60   # 60 seconds of history


class PingWorker(QObject):
    result = Signal(float)   # rtt_ms, or -1 for timeout
    stopped = Signal()

    def __init__(self, ip: str, interval_s: float = 1.0):
        super().__init__()
        self._ip = ip
        self._interval = interval_s
        self._running = True

    def stop(self): self._running = False

    def run(self):
        while self._running:
            t0 = time.perf_counter()
            try:
                proc = subprocess.run(
                    ["ping", "-c", "1", "-W", "1000", "-n", self._ip],
                    capture_output=True, text=True, timeout=2.5,
                )
                m = re.search(r"time[=<]([\d.]+)", proc.stdout)
                rtt = float(m.group(1)) if m else -1.0
            except Exception:
                rtt = -1.0
            self.result.emit(rtt)
            elapsed = time.perf_counter() - t0
            time.sleep(max(0, self._interval - elapsed))
        self.stopped.emit()


class PingGraph(QWidget):
    """Sparkline RTT chart with live continuous pinger."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: collections.deque[float] = collections.deque(maxlen=MAX_POINTS)
        self._ip = ""
        self._thread: QThread | None = None
        self._worker: PingWorker | None = None
        self.setMinimumHeight(80)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QHBoxLayout()
        self._lbl_ip = QLabel("")
        self._lbl_ip.setStyleSheet("color:#8b93a7; font-size:11px;")
        self._lbl_cur = QLabel("—")
        self._lbl_cur.setStyleSheet("color:#ffffff; font-size:11px; font-weight:600;")
        self._lbl_avg = QLabel("")
        self._lbl_avg.setStyleSheet("color:#8b93a7; font-size:10px;")
        top.addWidget(self._lbl_ip)
        top.addStretch(1)
        top.addWidget(self._lbl_avg)
        top.addSpacing(8)
        top.addWidget(self._lbl_cur)
        lay.addLayout(top)
        self._canvas = _GraphCanvas(self._data)
        lay.addWidget(self._canvas, 1)

    def start(self, ip: str):
        self.stop()
        self._ip = ip
        self._data.clear()
        self._lbl_ip.setText(f"Ping  {ip}")
        self._lbl_cur.setText("…")
        self._lbl_avg.setText("")
        self._thread = QThread()
        self._worker = PingWorker(ip)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.result.connect(self._on_result)
        self._thread.start()

    def stop(self):
        if self._worker: self._worker.stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit(); self._thread.wait(2000)
        self._worker = None; self._thread = None

    def _on_result(self, rtt: float):
        self._data.append(rtt)
        if rtt < 0:
            self._lbl_cur.setText("timeout")
            self._lbl_cur.setStyleSheet("color:#ff6b6b; font-size:11px; font-weight:600;")
        else:
            self._lbl_cur.setText(f"{rtt:.1f} ms")
            self._lbl_cur.setStyleSheet("color:#3ddc84; font-size:11px; font-weight:600;")
        valid = [v for v in self._data if v >= 0]
        if valid:
            avg = sum(valid) / len(valid)
            self._lbl_avg.setText(f"avg {avg:.1f}  min {min(valid):.1f}  max {max(valid):.1f} ms")
        self._canvas.update()

    def closeEvent(self, e):
        self.stop()
        super().closeEvent(e)


class _GraphCanvas(QWidget):
    def __init__(self, data: collections.deque, parent=None):
        super().__init__(parent)
        self._data = data
        self.setMinimumHeight(56)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#181b23"))

        pts = list(self._data)
        if len(pts) < 2:
            p.setPen(QPen(QColor("#2c3140")))
            p.drawLine(0, h // 2, w, h // 2)
            p.end(); return

        valid = [v for v in pts if v >= 0]
        if not valid: p.end(); return

        mn, mx = 0.0, max(valid) * 1.2 or 10.0
        n = len(pts)
        x_step = w / (MAX_POINTS - 1)

        def pt(i, v):
            x = i * x_step
            y = h - 4 - (v - mn) / (mx - mn) * (h - 8) if v >= 0 else h - 2
            return QPointF(x, max(4.0, min(float(h - 2), y)))

        # gradient fill under curve
        path = QPainterPath()
        first_valid = next((i for i, v in enumerate(pts) if v >= 0), None)
        if first_valid is None: p.end(); return
        fp = pt(first_valid, pts[first_valid])
        path.moveTo(QPointF(fp.x(), h))
        path.lineTo(fp)
        for i in range(first_valid + 1, n):
            if pts[i] >= 0:
                path.lineTo(pt(i, pts[i]))
        last_i = next((i for i in range(n - 1, -1, -1) if pts[i] >= 0), first_valid)
        lp = pt(last_i, pts[last_i])
        path.lineTo(QPointF(lp.x(), h))
        path.closeSubpath()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor(61, 220, 132, 80))
        grad.setColorAt(1, QColor(61, 220, 132, 0))
        p.setBrush(QBrush(grad)); p.setPen(Qt.NoPen)
        p.drawPath(path)

        # line
        pen = QPen(QColor("#3ddc84")); pen.setWidthF(1.5)
        p.setPen(pen)
        prev = None
        for i, v in enumerate(pts):
            if v < 0: prev = None; continue
            cur = pt(i, v)
            if prev: p.drawLine(prev, cur)
            prev = cur

        # timeout ticks
        p.setPen(QPen(QColor("#ff6b6b")))
        for i, v in enumerate(pts):
            if v < 0:
                x = i * x_step
                p.drawLine(QPointF(x, h - 6), QPointF(x, h - 2))
        p.end()
