"""Slide-in device detail panel — v2 with ping graph, traceroute,
Bonjour, WoL, one-click actions, notes, vulnerability hints."""
from __future__ import annotations

import subprocess
import time

from PySide6.QtCore import Qt, QObject, QThread, Signal, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QScrollArea, QTextEdit, QSizePolicy, QApplication,
)

from . import scanner, detail, db as _db, vuln as _vuln, wol as _wol
from .ping_graph import PingGraph
from .widgets import StatusDot

MONO = "SF Mono, Menlo, monospace"
PANEL_WIDTH = 340


# ---- deep probe worker
class DeepWorker(QObject):
    progress = Signal(str)
    result   = Signal(object)

    def __init__(self, dev: scanner.Device):
        super().__init__()
        self._dev = dev
        self._cancelled = False

    def cancel(self): self._cancelled = True

    def run(self):
        def cb(msg):
            if not self._cancelled: self.progress.emit(msg)
        try:
            info = detail.probe(self._dev, progress_cb=cb)
            if not self._cancelled: self.result.emit(info)
        except Exception as e:
            if not self._cancelled:
                self.result.emit(detail.DeepInfo(ip=self._dev.ip, error=str(e)))


# ---- traceroute worker
class TraceWorker(QObject):
    hop    = Signal(object)   # traceroute.Hop
    done   = Signal()

    def __init__(self, ip: str):
        super().__init__()
        self._ip = ip
        self._cancelled = False

    def cancel(self): self._cancelled = True

    def run(self):
        from . import traceroute
        def on_hop(h):
            if not self._cancelled: self.hop.emit(h)
        traceroute.run(self._ip, max_hops=20, timeout_s=20, on_hop=on_hop)
        if not self._cancelled: self.done.emit()


# ---- helpers
def _section(title: str) -> QLabel:
    l = QLabel(title.upper())
    l.setObjectName("cardTitle")
    l.setContentsMargins(0, 12, 0, 4)
    return l


def _sep() -> QFrame:
    f = QFrame(); f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("background:#262a36; max-height:1px;")
    return f


def _kv(key: str, val: str, *, mono=False, color="#e6e9ef") -> QWidget:
    w = QWidget(); h = QHBoxLayout(w)
    h.setContentsMargins(0, 2, 0, 2); h.setSpacing(6)
    kl = QLabel(key); kl.setObjectName("statLabel")
    kl.setFixedWidth(110); kl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    vl = QLabel(val or "—"); vl.setWordWrap(True)
    vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    vl.setStyleSheet(f"color:{color};font-size:12px;"
                     + (f"font-family:{MONO};" if mono else ""))
    h.addWidget(kl); h.addWidget(vl, 1); return w


def _badge(text: str, color: str) -> QLabel:
    l = QLabel(f"  {text}  ")
    l.setStyleSheet(f"background:{color};color:#fff;border-radius:8px;"
                    f"font-size:10px;font-weight:700;padding:2px 0;")
    l.setAlignment(Qt.AlignCenter); l.setFixedHeight(20); return l


def _action_btn(icon: str, label: str, tip: str = "") -> QPushButton:
    b = QPushButton(f"{icon}  {label}")
    b.setFixedHeight(30)
    b.setStyleSheet(
        "QPushButton{background:#20242f;border:1px solid #2c3140;border-radius:6px;"
        "color:#cdd3e0;font-size:11px;padding:0 10px;text-align:left;}"
        "QPushButton:hover{background:#272c3a;color:#fff;}"
    )
    if tip: b.setToolTip(tip)
    return b


class _FlowWidget(QWidget):
    """Simple word-wrap container for chips."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[QWidget] = []

    def add(self, w):
        w.setParent(self); self._items.append(w)

    def clear_items(self):
        for w in self._items: w.deleteLater()
        self._items.clear()

    def _relayout(self):
        x = y = rh = 0
        for w in self._items:
            w.adjustSize()
            sw = w.sizeHint().width()
            if x and x + sw > self.width():
                x = 0; y += rh + 5; rh = 0
            w.move(x, y); w.show()
            rh = max(rh, w.sizeHint().height()); x += sw + 5
        self.setFixedHeight(y + rh + 4 if self._items else 0)

    def resizeEvent(self, e): super().resizeEvent(e); self._relayout()
    def showEvent(self, e): super().showEvent(e); QTimer.singleShot(0, self._relayout)


def _chip(text: str, color: str = "#1c2a3a", fg: str = "#7fd1a8") -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(f"background:{color};color:{fg};border-radius:5px;"
                    f"font-size:11px;font-family:{MONO};padding:3px 7px;")
    return l


# ---- main panel
class DeviceDetailPanel(QWidget):
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(0)
        self._dev: scanner.Device | None = None
        self._deep_thread: QThread | None = None
        self._deep_worker: DeepWorker | None = None
        self._trace_thread: QThread | None = None
        self._trace_worker: TraceWorker | None = None
        self._ping_graph = PingGraph()
        self._anim  = QPropertyAnimation(self, b"minimumWidth")
        self._anim2 = QPropertyAnimation(self, b"maximumWidth")
        for a in (self._anim, self._anim2):
            a.setDuration(220); a.setEasingCurve(QEasingCurve.OutCubic)
        self.setStyleSheet("DeviceDetailPanel{background:#181b23;border-left:1px solid #262a36;}")
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # header
        hdr = QWidget(); hdr.setFixedHeight(46)
        hdr.setStyleSheet("background:#1c1f28;border-bottom:1px solid #262a36;")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(14, 0, 10, 0)
        self._hdr_title = QLabel("Device Info")
        self._hdr_title.setStyleSheet("color:#fff;font-size:13px;font-weight:700;")
        self._fav_btn = QPushButton("☆")
        self._fav_btn.setFixedSize(28, 28)
        self._fav_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#8b93a7;border:none;font-size:16px;}"
            "QPushButton:hover{color:#ffc24c;}")
        self._fav_btn.clicked.connect(self._toggle_fav)
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#8b93a7;border:none;font-size:14px;}"
            "QPushButton:hover{color:#fff;}")
        close_btn.clicked.connect(self.hide_panel)
        hl.addWidget(self._hdr_title); hl.addStretch(1)
        hl.addWidget(self._fav_btn); hl.addWidget(close_btn)
        outer.addWidget(hdr)

        # scroll area
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background:transparent;")
        self._content = QWidget(); self._content.setStyleSheet("background:transparent;")
        self._cl = QVBoxLayout(self._content)
        self._cl.setContentsMargins(14, 10, 14, 18); self._cl.setSpacing(0)
        self._cl.addStretch(1)
        scroll.setWidget(self._content)
        outer.addWidget(scroll, 1)

        # probe status bar
        self._probe_bar = QWidget(); self._probe_bar.setFixedHeight(28)
        self._probe_bar.setStyleSheet("background:#1c1f28;border-top:1px solid #262a36;")
        pbl = QHBoxLayout(self._probe_bar); pbl.setContentsMargins(12, 0, 12, 0)
        self._probe_lbl = QLabel("Probing…"); self._probe_lbl.setObjectName("subtle")
        pbl.addWidget(self._probe_lbl); pbl.addStretch(1)
        self._probe_bar.hide()
        outer.addWidget(self._probe_bar)

    # ---- animation
    def show_panel(self):
        self.setMaximumWidth(PANEL_WIDTH)
        for a in (self._anim, self._anim2):
            a.stop(); a.setStartValue(self.width()); a.setEndValue(PANEL_WIDTH); a.start()

    def hide_panel(self):
        self._cancel_probes()
        self._ping_graph.stop()
        for a in (self._anim, self._anim2):
            a.stop(); a.setStartValue(self.width()); a.setEndValue(0); a.start()
        self._anim.finished.connect(lambda: self.setMaximumWidth(0))
        self.closed.emit()

    # ---- public entry
    def show_device(self, dev: scanner.Device):
        self._dev = dev
        self._cancel_probes()
        self._ping_graph.stop()
        self._clear()
        self._render_basic(dev)
        self.show_panel()
        self._ping_graph.start(dev.ip)
        self._start_deep(dev)

    def _clear(self):
        lay = self._cl
        while lay.count():
            it = lay.takeAt(0)
            if it.widget(): it.widget().deleteLater()

    # ---- basic render
    def _render_basic(self, dev: scanner.Device):
        lay = self._cl

        # IP + dot
        ir = QHBoxLayout()
        dot = StatusDot("#4c8dff" if dev.is_self else ("#ffc24c" if dev.is_gateway else "#3ddc84"))
        ip_lbl = QLabel(dev.ip)
        ip_lbl.setStyleSheet(f"color:#fff;font-size:19px;font-weight:700;font-family:{MONO};")
        ip_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ir.addWidget(dot, 0, Qt.AlignVCenter); ir.addSpacing(6); ir.addWidget(ip_lbl)
        ir.addStretch(1); lay.addLayout(ir)

        # badges
        br = QHBoxLayout(); br.setSpacing(5)
        if dev.is_self:    br.addWidget(_badge("YOU", "#4c8dff"))
        if dev.is_gateway: br.addWidget(_badge("GATEWAY", "#ffc24c"))
        if dev.is_new:     br.addWidget(_badge("NEW", "#3ddc84"))
        if dev.arp_conflict: br.addWidget(_badge("⚠ ARP CONFLICT", "#ff4444"))
        if dev.is_favourite: br.addWidget(_badge("★ FAVOURITE", "#ffc24c"))
        if dev.device_type and dev.device_type != "Unknown":
            br.addWidget(_badge(dev.device_type.upper()[:18], "#2a3550"))
        br.addStretch(1); lay.addLayout(br); lay.addSpacing(4)

        # OS row
        if dev.os_guess and dev.os_guess != "Unknown":
            or_ = QHBoxLayout(); or_.setSpacing(6)
            os_lbl = QLabel(f"{dev.os_icon}  {dev.os_guess}")
            os_lbl.setStyleSheet(f"color:#cdd3e0;font-size:12px;")
            conf = QLabel(f"({dev.os_confidence})")
            conf.setStyleSheet("color:#5a6075;font-size:10px;")
            or_.addWidget(os_lbl); or_.addWidget(conf); or_.addStretch(1)
            lay.addLayout(or_)

        lay.addSpacing(6); lay.addWidget(_sep())

        # ---- Actions
        lay.addWidget(_section("Actions"))
        act_grid = QHBoxLayout(); act_grid.setSpacing(6)
        self._btn_ssh  = _action_btn("🔒", "SSH",  f"ssh {dev.ip}")
        self._btn_http = _action_btn("🌐", "HTTP", f"http://{dev.ip}")
        self._btn_ping = _action_btn("📡", "Ping")
        act_grid.addWidget(self._btn_ssh); act_grid.addWidget(self._btn_http)
        act_grid.addWidget(self._btn_ping)
        lay.addLayout(act_grid)
        act2 = QHBoxLayout(); act2.setSpacing(6)
        self._btn_wol   = _action_btn("⚡", "Wake-on-LAN")
        self._btn_trace = _action_btn("🗺", "Traceroute")
        act2.addWidget(self._btn_wol); act2.addWidget(self._btn_trace)
        lay.addLayout(act2)

        self._btn_ssh.clicked.connect(lambda: self._open(f"ssh://{dev.ip}"))
        self._btn_http.clicked.connect(lambda: self._open(f"http://{dev.ip}"))
        self._btn_ping.clicked.connect(lambda: self._ping_graph.start(dev.ip))
        self._btn_wol.clicked.connect(self._do_wol)
        self._btn_wol.setEnabled(bool(dev.mac))
        self._btn_trace.clicked.connect(self._start_trace)

        lay.addWidget(_sep())

        # ---- Network info
        lay.addWidget(_section("Network"))
        lay.addWidget(_kv("Hostname", dev.hostname or "—"))
        lay.addWidget(_kv("Custom name", dev.custom_name or "—"))
        lay.addWidget(_kv("MAC Address", dev.mac or "—", mono=True))
        lay.addWidget(_kv("Vendor", dev.vendor or "—"))
        rtt = f"{dev.rtt_ms:.1f} ms" if dev.rtt_ms is not None else "—"
        lay.addWidget(_kv("Latency", rtt))
        if dev.first_seen:
            import datetime
            lay.addWidget(_kv("First seen", datetime.datetime.fromtimestamp(
                dev.first_seen).strftime("%d %b %Y %H:%M")))
        if dev.times_seen > 1:
            lay.addWidget(_kv("Times seen", str(dev.times_seen)))

        # ---- Ping graph (always visible)
        lay.addWidget(_sep())
        lay.addWidget(_section("Live Ping"))
        lay.addWidget(self._ping_graph)

        # ---- Open ports (fast scan)
        if dev.open_ports:
            lay.addWidget(_sep())
            lay.addWidget(_section(f"Open Ports ({len(dev.open_ports)})"))
            fw = _FlowWidget()
            for p in dev.open_ports:
                fw.add(_chip(f"{p}/{scanner.COMMON_PORTS.get(p,'?')}"))
            lay.addWidget(fw)

        # ---- Notes
        lay.addWidget(_sep())
        lay.addWidget(_section("Notes"))
        self._notes_edit = QTextEdit()
        self._notes_edit.setFixedHeight(60)
        self._notes_edit.setPlaceholderText("Add notes about this device…")
        self._notes_edit.setStyleSheet(
            "QTextEdit{background:#20242f;border:1px solid #2c3140;border-radius:6px;"
            "color:#e6e9ef;font-size:11px;padding:4px;}")
        self._notes_edit.setPlainText(dev.notes or "")
        self._notes_edit.textChanged.connect(self._save_notes)
        lay.addWidget(self._notes_edit)

        # placeholder for deep results
        self._deep_anchor = QWidget(); self._deep_anchor.setFixedHeight(0)
        lay.addWidget(self._deep_anchor)
        lay.addStretch(1)
        self._hdr_title.setText(dev.custom_name or dev.hostname or dev.ip)
        self._fav_btn.setText("★" if dev.is_favourite else "☆")
        self._fav_btn.setStyleSheet(
            f"QPushButton{{background:transparent;border:none;font-size:16px;"
            f"color:{'#ffc24c' if dev.is_favourite else '#8b93a7'};}}"
            "QPushButton:hover{color:#ffc24c;}")

    # ---- deep results
    def _render_deep(self, info: detail.DeepInfo):
        lay = self._cl
        # remove stretch + anchor
        for i in range(lay.count() - 1, -1, -1):
            item = lay.itemAt(i)
            if item and item.spacerItem(): lay.takeAt(i); break
        idx = lay.indexOf(self._deep_anchor)
        if idx >= 0: lay.takeAt(idx); self._deep_anchor.deleteLater()

        if info.error:
            lay.addWidget(_kv("Probe error", info.error, color="#ff8c8c"))
            lay.addStretch(1); return

        # ---- Deep Network
        lay.addWidget(_sep())
        lay.addWidget(_section("Deep Network"))
        if info.ping_rtt: lay.addWidget(_kv("RTT", f"{info.ping_rtt:.1f} ms"))
        if info.ttl:      lay.addWidget(_kv("TTL", str(info.ttl)))
        if info.hops is not None: lay.addWidget(_kv("Est. hops", str(info.hops)))
        if info.nbns_name: lay.addWidget(_kv("NetBIOS", info.nbns_name))
        if info.mdns_names: lay.addWidget(_kv("mDNS", ", ".join(info.mdns_names)))
        if info.http_title: lay.addWidget(_kv("HTTP title", info.http_title, color="#a9b2c7"))

        # ---- All ports
        if info.all_ports:
            lay.addWidget(_sep())
            lay.addWidget(_section(f"All Open Ports ({len(info.all_ports)})"))
            fw = _FlowWidget()
            from .detail import FULL_PORTS
            for p in info.all_ports:
                fw.add(_chip(f"{p}/{FULL_PORTS.get(p,'?')}"))
            lay.addWidget(fw)

        # ---- Banners
        if info.banners:
            lay.addWidget(_sep())
            lay.addWidget(_section("Service Banners"))
            for b in info.banners:
                if b.server or b.raw:
                    lay.addWidget(_kv(f"{b.port}/{b.service}",
                                      b.server or b.raw, mono=True, color="#7fd1a8"))

        # ---- Vulnerability hints
        hints = _vuln.scan(info.all_ports, [b.raw for b in info.banners],
                           info.http_title)
        if hints:
            lay.addWidget(_sep())
            lay.addWidget(_section(f"Security Hints ({len(hints)})"))
            for h in hints:
                col = _vuln.color_for(h.severity)
                row = QWidget(); rl = QVBoxLayout(row)
                rl.setContentsMargins(0, 3, 0, 3); rl.setSpacing(1)
                title_lbl = QLabel(f"[{h.severity.upper()}]  {h.title}")
                title_lbl.setStyleSheet(f"color:{col};font-size:11px;font-weight:700;")
                detail_lbl = QLabel(h.detail)
                detail_lbl.setWordWrap(True)
                detail_lbl.setStyleSheet("color:#8b93a7;font-size:10px;")
                rl.addWidget(title_lbl); rl.addWidget(detail_lbl)
                lay.addWidget(row)

        # ---- Traceroute placeholder
        lay.addWidget(_sep())
        lay.addWidget(_section("Traceroute"))
        self._trace_box = QWidget(); tb = QVBoxLayout(self._trace_box)
        tb.setContentsMargins(0, 0, 0, 0); tb.setSpacing(2)
        self._trace_status = QLabel("Click 'Traceroute' to run…")
        self._trace_status.setStyleSheet("color:#5a6075;font-size:11px;")
        tb.addWidget(self._trace_status)
        lay.addWidget(self._trace_box)

        lay.addStretch(1)

    # ---- traceroute render
    def _on_hop(self, hop):
        if not hasattr(self, "_trace_box"): return
        lbl = QLabel(hop.display)
        lbl.setStyleSheet(f"color:{'#3ddc84' if not hop.is_timeout else '#5a6075'};"
                          f"font-size:10px;font-family:{MONO};")
        self._trace_box.layout().addWidget(lbl)
        self._trace_status.hide()

    def _on_trace_done(self):
        if hasattr(self, "_trace_status"):
            self._trace_status.hide()

    # ---- workers
    def _start_deep(self, dev: scanner.Device):
        self._probe_bar.show(); self._probe_lbl.setText("Probing…")
        self._deep_thread = QThread()
        self._deep_worker = DeepWorker(dev)
        self._deep_worker.moveToThread(self._deep_thread)
        self._deep_thread.started.connect(self._deep_worker.run)
        self._deep_worker.progress.connect(lambda m: self._probe_lbl.setText(m))
        self._deep_worker.result.connect(self._on_deep_done)
        self._deep_thread.start()

    def _on_deep_done(self, info):
        self._probe_bar.hide()
        self._render_deep(info)
        if self._deep_thread: self._deep_thread.quit(); self._deep_thread.wait(2000)

    def _start_trace(self):
        if not self._dev: return
        if self._trace_thread and self._trace_thread.isRunning(): return
        if hasattr(self, "_trace_status"): self._trace_status.setText("Running…")
        self._trace_thread = QThread()
        self._trace_worker = TraceWorker(self._dev.ip)
        self._trace_worker.moveToThread(self._trace_thread)
        self._trace_thread.started.connect(self._trace_worker.run)
        self._trace_worker.hop.connect(self._on_hop)
        self._trace_worker.done.connect(self._on_trace_done)
        self._trace_thread.start()

    def _cancel_probes(self):
        for w in (self._deep_worker, self._trace_worker):
            if w: w.cancel()
        for t in (self._deep_thread, self._trace_thread):
            if t and t.isRunning(): t.quit(); t.wait(1000)
        self._deep_worker = self._deep_thread = None
        self._trace_worker = self._trace_thread = None
        self._probe_bar.hide()

    # ---- actions
    def _open(self, url: str):
        subprocess.Popen(["open", url])

    def _do_wol(self):
        if not self._dev or not self._dev.mac: return
        result = _wol.send_to(self._dev.mac)
        self._probe_lbl.setText(result); self._probe_bar.show()
        QTimer.singleShot(4000, self._probe_bar.hide)

    def _save_notes(self):
        if self._dev and self._dev.mac:
            notes = self._notes_edit.toPlainText()
            _db.set_notes(self._dev.mac, notes)
            if self._dev: self._dev.notes = notes

    def _toggle_fav(self):
        if not self._dev or not self._dev.mac: return
        self._dev.is_favourite = not self._dev.is_favourite
        _db.set_favourite(self._dev.mac, self._dev.is_favourite)
        self._fav_btn.setText("★" if self._dev.is_favourite else "☆")
        self._fav_btn.setStyleSheet(
            f"QPushButton{{background:transparent;border:none;font-size:16px;"
            f"color:{'#ffc24c' if self._dev.is_favourite else '#8b93a7'};}}"
            "QPushButton:hover{color:#ffc24c;}")
