"""Slide-in device detail panel for the LAN tab."""
from __future__ import annotations

import time

from PySide6.QtCore import (Qt, QObject, QThread, Signal, QPropertyAnimation,
                             QEasingCurve, QSize, QTimer)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QLinearGradient
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QScrollArea, QSizePolicy, QProgressBar, QApplication,
)

from . import scanner, detail
from .widgets import StatusDot, SignalMeter

MONO = "SF Mono, Menlo, monospace"


# ---------------------------------------------------------------- deep probe worker
class DeepWorker(QObject):
    progress = Signal(str)
    result   = Signal(object)   # detail.DeepInfo

    def __init__(self, dev: scanner.Device):
        super().__init__()
        self._dev = dev
        self._cancelled = False

    def cancel(self): self._cancelled = True

    def run(self):
        def cb(msg):
            if not self._cancelled:
                self.progress.emit(msg)
        try:
            info = detail.probe(self._dev, progress_cb=cb)
            if not self._cancelled:
                self.result.emit(info)
        except Exception as e:
            if not self._cancelled:
                self.result.emit(detail.DeepInfo(ip=self._dev.ip, error=str(e)))


# ---------------------------------------------------------------- small helpers
def _section(title: str) -> QLabel:
    lbl = QLabel(title.upper())
    lbl.setObjectName("cardTitle")
    lbl.setContentsMargins(0, 10, 0, 4)
    return lbl


def _row(key: str, value: str, *, mono: bool = False,
         value_color: str = "#e6e9ef") -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 2, 0, 2)
    h.setSpacing(8)
    kl = QLabel(key)
    kl.setObjectName("statLabel")
    kl.setFixedWidth(120)
    kl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    vl = QLabel(value or "—")
    vl.setWordWrap(True)
    vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    vl.setStyleSheet(
        f"color:{value_color}; font-size:12px;"
        + (f"font-family:{MONO};" if mono else "")
    )
    h.addWidget(kl)
    h.addWidget(vl, 1)
    return w


def _badge(text: str, color: str) -> QLabel:
    lbl = QLabel(f"  {text}  ")
    lbl.setStyleSheet(
        f"background:{color}; color:#fff; border-radius:8px;"
        f" font-size:10px; font-weight:700; padding:2px 0;"
    )
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setFixedHeight(20)
    return lbl


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("color:#262a36; background:#262a36; max-height:1px;")
    return line


def _port_chip(port: int, service: str) -> QLabel:
    lbl = QLabel(f"{port}/{service}")
    lbl.setStyleSheet(
        "background:#1c2a3a; color:#7fd1a8; border-radius:6px;"
        f"font-size:11px; font-family:{MONO}; padding:3px 8px;"
    )
    return lbl


# ---------------------------------------------------------------- port chips flow layout helper
class FlowWidget(QWidget):
    """Wraps children in a flow (word-wrap) layout."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[QWidget] = []

    def add(self, w: QWidget):
        w.setParent(self)
        self._items.append(w)

    def clear_items(self):
        for w in self._items:
            w.deleteLater()
        self._items.clear()

    def _relayout(self):
        x, y, row_h = 0, 0, 0
        for w in self._items:
            w.adjustSize()
            if x > 0 and x + w.sizeHint().width() > self.width():
                x = 0; y += row_h + 6; row_h = 0
            w.move(x, y)
            w.show()
            row_h = max(row_h, w.sizeHint().height())
            x += w.sizeHint().width() + 6
        self.setFixedHeight(y + row_h + 4 if self._items else 0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._relayout()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._relayout)


# ---------------------------------------------------------------- main panel
PANEL_WIDTH = 320


class DeviceDetailPanel(QWidget):
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(0)           # hidden initially
        self._dev: scanner.Device | None = None
        self._thread: QThread | None = None
        self._worker: DeepWorker | None = None
        self._anim = QPropertyAnimation(self, b"minimumWidth")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim2 = QPropertyAnimation(self, b"maximumWidth")
        self._anim2.setDuration(220)
        self._anim2.setEasingCurve(QEasingCurve.OutCubic)
        self.setStyleSheet("""
            DeviceDetailPanel {
                background: #181b23;
                border-left: 1px solid #262a36;
            }
        """)
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # header bar
        hdr = QWidget(); hdr.setFixedHeight(46)
        hdr.setStyleSheet("background:#1c1f28; border-bottom:1px solid #262a36;")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(16, 0, 12, 0)
        self._hdr_title = QLabel("Device Info")
        self._hdr_title.setStyleSheet("color:#ffffff; font-size:13px; font-weight:700;")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#8b93a7;border:none;font-size:14px;}"
            "QPushButton:hover{color:#ffffff;}"
        )
        close_btn.clicked.connect(self.hide_panel)
        hl.addWidget(self._hdr_title)
        hl.addStretch(1)
        hl.addWidget(close_btn)
        outer.addWidget(hdr)

        # scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background:transparent;")
        self._content = QWidget()
        self._content.setStyleSheet("background:transparent;")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(16, 12, 16, 20)
        self._content_layout.setSpacing(0)
        self._content_layout.addStretch(1)
        scroll.setWidget(self._content)
        outer.addWidget(scroll, 1)

        # probe status bar at bottom
        self._probe_bar = QWidget()
        self._probe_bar.setFixedHeight(32)
        self._probe_bar.setStyleSheet("background:#1c1f28; border-top:1px solid #262a36;")
        pbl = QHBoxLayout(self._probe_bar)
        pbl.setContentsMargins(12, 0, 12, 0)
        self._probe_lbl = QLabel("Probing…")
        self._probe_lbl.setObjectName("subtle")
        self._probe_progress = QProgressBar()
        self._probe_progress.setRange(0, 0)   # indeterminate
        self._probe_progress.setFixedHeight(4)
        self._probe_progress.setTextVisible(False)
        pbl.addWidget(self._probe_lbl)
        pbl.addStretch(1)
        self._probe_bar.hide()
        pb_outer = QVBoxLayout()
        pb_outer.setContentsMargins(0, 0, 0, 0)
        pb_outer.addWidget(self._probe_progress)
        pbl.addLayout(pb_outer)
        outer.addWidget(self._probe_bar)

    # ---- show / hide animation
    def show_panel(self):
        self.setMaximumWidth(PANEL_WIDTH)
        for a in (self._anim, self._anim2):
            a.stop()
            a.setStartValue(self.width())
            a.setEndValue(PANEL_WIDTH)
            a.start()

    def hide_panel(self):
        self._cancel_probe()
        for a in (self._anim, self._anim2):
            a.stop()
            a.setStartValue(self.width())
            a.setEndValue(0)
            a.start()
        self._anim.finished.connect(lambda: self.setMaximumWidth(0))
        self.closed.emit()

    # ---- populate
    def show_device(self, dev: scanner.Device):
        self._dev = dev
        self._cancel_probe()
        self._clear_content()
        self._render_basic(dev)
        self.show_panel()
        self._start_probe(dev)

    def _clear_content(self):
        layout = self._content_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_basic(self, dev: scanner.Device):
        lay = self._content_layout

        # ── Identity
        ip_row = QHBoxLayout()
        dot_color = "#4c8dff" if dev.is_self else ("#ffc24c" if dev.is_gateway else "#3ddc84")
        dot = StatusDot(dot_color)
        ip_lbl = QLabel(dev.ip)
        ip_lbl.setStyleSheet(f"color:#ffffff; font-size:20px; font-weight:700; font-family:{MONO};")
        ip_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ip_row.addWidget(dot, 0, Qt.AlignVCenter)
        ip_row.addSpacing(6)
        ip_row.addWidget(ip_lbl)
        ip_row.addStretch(1)
        lay.addLayout(ip_row)

        # badges
        badge_row = QHBoxLayout()
        badge_row.setSpacing(6)
        if dev.is_self:    badge_row.addWidget(_badge("THIS DEVICE", "#4c8dff"))
        if dev.is_gateway: badge_row.addWidget(_badge("GATEWAY", "#ffc24c"))
        if dev.device_type and dev.device_type != "Unknown":
            badge_row.addWidget(_badge(dev.device_type.upper(), "#3a4155"))
        badge_row.addStretch(1)
        lay.addLayout(badge_row)
        lay.addSpacing(10)
        lay.addWidget(_separator())

        # ── Network
        lay.addWidget(_section("Network"))
        lay.addWidget(_row("Hostname", dev.hostname or "—"))
        lay.addWidget(_row("MAC Address", dev.mac or "—", mono=True))
        lay.addWidget(_row("Vendor", dev.vendor or "—",
                           value_color="#cdd3e0" if dev.vendor and dev.vendor != "Unknown" else "#5a6075"))
        rtt = f"{dev.rtt_ms:.1f} ms" if dev.rtt_ms is not None else "—"
        lay.addWidget(_row("Latency", rtt))
        lay.addWidget(_separator())

        # ── Open ports (from fast scan)
        if dev.open_ports:
            lay.addWidget(_section(f"Open Ports ({len(dev.open_ports)})"))
            flow = FlowWidget()
            for p in dev.open_ports:
                flow.add(_port_chip(p, scanner.COMMON_PORTS.get(p, "?")))
            lay.addWidget(flow)
            lay.addWidget(_separator())

        # placeholder for deep-probe results
        self._deep_anchor = QWidget()
        self._deep_anchor.setFixedHeight(0)
        lay.addWidget(self._deep_anchor)
        lay.addStretch(1)

        # header
        self._hdr_title.setText(dev.hostname or dev.ip)

    def _render_deep(self, info: detail.DeepInfo):
        """Insert deep-probe results just above the stretch spacer."""
        lay = self._content_layout
        # remove old stretch
        for i in range(lay.count() - 1, -1, -1):
            item = lay.itemAt(i)
            if item and item.spacerItem():
                lay.takeAt(i)
                break

        # remove placeholder
        idx = lay.indexOf(self._deep_anchor)
        if idx >= 0:
            lay.takeAt(idx)
            self._deep_anchor.deleteLater()

        if info.error:
            lay.addWidget(_row("Probe error", info.error, value_color="#ff8c8c"))
            lay.addStretch(1)
            return

        # ── Deep Network
        lay.addWidget(_section("Deep Network"))
        if info.ping_rtt is not None:
            lay.addWidget(_row("RTT", f"{info.ping_rtt:.1f} ms"))
        if info.ttl is not None:
            lay.addWidget(_row("TTL", str(info.ttl)))
        if info.hops is not None:
            lay.addWidget(_row("Est. hops", str(info.hops)))
        if info.nbns_name:
            lay.addWidget(_row("NetBIOS name", info.nbns_name, value_color="#cdd3e0"))
        if info.mdns_names:
            lay.addWidget(_row("mDNS", ", ".join(info.mdns_names), value_color="#cdd3e0"))
        if info.http_title:
            lay.addWidget(_row("HTTP title", info.http_title, value_color="#a9b2c7"))
        lay.addWidget(_separator())

        # ── Full port list
        if info.all_ports:
            lay.addWidget(_section(f"All Open Ports ({len(info.all_ports)})"))
            flow = FlowWidget()
            for p in info.all_ports:
                flow.add(_port_chip(p, detail.FULL_PORTS.get(p, "?")))
            lay.addWidget(flow)
            lay.addWidget(_separator())

        # ── Banners
        if info.banners:
            lay.addWidget(_section("Service Banners"))
            for b in info.banners:
                if b.server or b.raw:
                    lay.addWidget(_row(
                        f"{b.port}/{b.service}",
                        b.server or b.raw,
                        mono=True,
                        value_color="#7fd1a8",
                    ))
            lay.addWidget(_separator())

        lay.addStretch(1)

    # ---- deep probe plumbing
    def _start_probe(self, dev: scanner.Device):
        self._probe_bar.show()
        self._probe_lbl.setText("Probing…")
        self._thread = QThread()
        self._worker = DeepWorker(dev)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_probe_progress)
        self._worker.result.connect(self._on_probe_done)
        self._thread.start()

    def _on_probe_progress(self, msg: str):
        self._probe_lbl.setText(msg)

    def _on_probe_done(self, info: detail.DeepInfo):
        self._probe_bar.hide()
        self._render_deep(info)
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)

    def _cancel_probe(self):
        if self._worker:
            self._worker.cancel()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)
        self._worker = None
        self._thread = None
        self._probe_bar.hide()
