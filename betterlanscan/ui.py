"""BetterLanScan main window (PySide6)."""
from __future__ import annotations

import csv
import time

from PySide6.QtCore import Qt, QObject, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QStatusBar,
    QFileDialog, QAbstractItemView, QSizePolicy,
)

from . import netinfo, scanner, wifi, __version__, __app_name__
from .style import QSS
from .widgets import SignalBars, StatusDot, SignalMeter, quality_color

MONO = "SF Mono, Menlo, monospace"


# ---------------------------------------------------------------- workers
class ScanWorker(QObject):
    device = Signal(object)
    progress = Signal(int, int)
    done = Signal(list)

    def __init__(self, hosts, self_ip, gateway_ip, do_ports):
        super().__init__()
        self.hosts = hosts
        self.self_ip = self_ip
        self.gateway_ip = gateway_ip
        self.do_ports = do_ports
        self.ctl = scanner.ScanController(
            on_device=lambda d: self.device.emit(d),
            on_progress=lambda a, b: self.progress.emit(a, b),
            on_done=lambda devs: self.done.emit(devs),
        )

    def run(self):
        self.ctl.start(
            self.hosts, self_ip=self.self_ip, gateway_ip=self.gateway_ip,
            do_ports=self.do_ports,
        )
        while self.ctl.running:
            time.sleep(0.1)

    def stop(self):
        self.ctl.stop()


class WifiWorker(QObject):
    result = Signal(object)

    def run(self):
        self.result.emit(wifi.get_status(active_scan=True))


# ---------------------------------------------------------------- helpers
def make_item(text, *, mono=False, color=None, align=Qt.AlignVCenter | Qt.AlignLeft,
              sort_value=None):
    it = QTableWidgetItem(str(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    it.setTextAlignment(align)
    if mono:
        it.setFont(QFont(MONO.split(",")[0].strip(), 11))
    if color:
        it.setForeground(QColor(color))
    if sort_value is not None:
        it.setData(Qt.UserRole, sort_value)
    return it


class SortItem(QTableWidgetItem):
    def __lt__(self, other):
        a = self.data(Qt.UserRole)
        b = other.data(Qt.UserRole)
        if a is not None and b is not None:
            return a < b
        return super().__lt__(other)


def sort_item(text, value, **kw):
    it = SortItem(str(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    it.setData(Qt.UserRole, value)
    it.setTextAlignment(kw.get("align", Qt.AlignVCenter | Qt.AlignLeft))
    if kw.get("mono"):
        it.setFont(QFont(MONO.split(",")[0].strip(), 11))
    if kw.get("color"):
        it.setForeground(QColor(kw["color"]))
    return it


# ---------------------------------------------------------------- LAN tab
LAN_COLS = ["", "IP Address", "Host name", "MAC Address", "Vendor",
            "Type", "Open ports", "Latency"]


class LanTab(QWidget):
    def __init__(self, info: netinfo.InterfaceInfo, status_cb):
        super().__init__()
        self.info = info
        self.status_cb = status_cb
        self.devices: dict[str, scanner.Device] = {}
        self.row_for_ip: dict[str, int] = {}
        self.thread: QThread | None = None
        self.worker: ScanWorker | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # ---- control bar
        bar = QHBoxLayout()
        bar.setSpacing(10)
        lbl = QLabel("Subnet")
        lbl.setObjectName("subtle")
        self.subnet_edit = QLineEdit(self.info.cidr or "192.168.1.0/24")
        self.subnet_edit.setFixedWidth(160)
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.clicked.connect(self.toggle_scan)
        self.ports_cb = QCheckBox("Port scan")
        self.ports_cb.setChecked(True)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter devices…")
        self.search.textChanged.connect(self.apply_filter)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.clicked.connect(self.export_csv)
        bar.addWidget(lbl)
        bar.addWidget(self.subnet_edit)
        bar.addWidget(self.scan_btn)
        bar.addWidget(self.ports_cb)
        bar.addStretch(1)
        bar.addWidget(self.search)
        bar.addWidget(self.export_btn)
        root.addLayout(bar)

        # ---- stat chips
        chips = QHBoxLayout()
        chips.setSpacing(12)
        self.chip_found = self._chip("DEVICES FOUND", "0")
        self.chip_scanned = self._chip("PROGRESS", "0 / 0")
        self.chip_gateway = self._chip("GATEWAY", self.info.gateway or "—")
        self.chip_subnet = self._chip("YOUR IP", self.info.ipv4 or "—")
        for c in (self.chip_found, self.chip_scanned, self.chip_gateway, self.chip_subnet):
            chips.addWidget(c)
        chips.addStretch(1)
        root.addLayout(chips)

        # ---- progress
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        # ---- table
        self.table = QTableWidget(0, len(LAN_COLS))
        self.table.setHorizontalHeaderLabels(LAN_COLS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 34)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        hh.setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(5, 140)
        self.table.setColumnWidth(7, 80)
        self.table.verticalHeader().setDefaultSectionSize(34)
        root.addWidget(self.table, 1)

    def _chip(self, title, value):
        f = QFrame()
        f.setObjectName("statChip")
        f.setFixedHeight(62)
        f.setMinimumWidth(150)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(2)
        t = QLabel(title); t.setObjectName("statLabel")
        v = QLabel(value); v.setObjectName("statValue")
        v.setProperty("role", "value")
        f._value = v
        lay.addWidget(t)
        lay.addWidget(v)
        return f

    # ---- scanning
    def toggle_scan(self):
        if self.thread and self.thread.isRunning():
            self.stop_scan()
        else:
            self.start_scan()

    def start_scan(self):
        try:
            hosts = netinfo.hosts_for_cidr(self.subnet_edit.text().strip())
        except Exception as e:
            self.status_cb(f"Invalid subnet: {e}")
            return
        self.devices.clear()
        self.row_for_ip.clear()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.chip_found._value.setText("0")
        self.progress.setValue(0)
        self.scan_btn.setText("Stop")
        self.scan_btn.setObjectName("danger")
        self.scan_btn.setStyleSheet("")  # re-evaluate objectName style
        self._restyle(self.scan_btn)
        self.status_cb(f"Scanning {self.subnet_edit.text().strip()} — {len(hosts)} hosts…")

        self.thread = QThread()
        self.worker = ScanWorker(
            hosts, self.info.ipv4, self.info.gateway, self.ports_cb.isChecked()
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.device.connect(self.on_device)
        self.worker.progress.connect(self.on_progress)
        self.worker.done.connect(self.on_done)
        self.thread.start()

    def stop_scan(self):
        if self.worker:
            self.worker.stop()
        self.status_cb("Stopping…")

    def _restyle(self, w):
        w.style().unpolish(w)
        w.style().polish(w)

    def on_progress(self, done, total):
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.chip_scanned._value.setText(f"{done} / {total}")

    def on_device(self, dev: scanner.Device):
        self.devices[dev.ip] = dev
        if dev.ip in self.row_for_ip:
            self._fill_row(self.row_for_ip[dev.ip], dev)
        else:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.row_for_ip[dev.ip] = row
            self._fill_row(row, dev)
        self.chip_found._value.setText(str(len(self.devices)))
        self.apply_filter(self.search.text())

    def _fill_row(self, row, dev: scanner.Device):
        # status dot
        color = "#4c8dff" if dev.is_self else ("#ffc24c" if dev.is_gateway else "#3ddc84")
        dot = StatusDot(color)
        wrap = QWidget(); wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0); wl.addWidget(dot, 0, Qt.AlignCenter)
        self.table.setCellWidget(row, 0, wrap)

        name = dev.ip + ("  (you)" if dev.is_self else "  (gateway)" if dev.is_gateway else "")
        self.table.setItem(row, 1, sort_item(name, dev.ip_sortkey, mono=True,
                                             color="#ffffff"))
        self.table.setItem(row, 2, make_item(dev.hostname or "—",
                                             color="#cdd3e0" if dev.hostname else "#5a6075"))
        self.table.setItem(row, 3, make_item(dev.mac or "—", mono=True,
                                             color="#cdd3e0" if dev.mac else "#5a6075"))
        self.table.setItem(row, 4, make_item(dev.vendor or "—",
                                             color="#cdd3e0" if dev.vendor and dev.vendor != "Unknown" else "#5a6075"))
        self.table.setItem(row, 5, make_item(dev.device_type or "—", color="#a9b2c7"))
        ports = ", ".join(
            f"{p}/{scanner.COMMON_PORTS.get(p, '?')}" for p in dev.open_ports[:6]
        )
        if len(dev.open_ports) > 6:
            ports += f"  +{len(dev.open_ports) - 6}"
        self.table.setItem(row, 6, make_item(ports or "—",
                                             color="#7fd1a8" if dev.open_ports else "#5a6075"))
        rtt = f"{dev.rtt_ms:.0f} ms" if dev.rtt_ms is not None else "—"
        self.table.setItem(row, 7, sort_item(rtt, dev.rtt_ms if dev.rtt_ms is not None else 9e9,
                                             mono=True, align=Qt.AlignVCenter | Qt.AlignRight,
                                             color="#a9b2c7"))

    def on_done(self, devices):
        self.scan_btn.setText("Scan")
        self.scan_btn.setObjectName("primary")
        self._restyle(self.scan_btn)
        self.table.setSortingEnabled(True)
        if self.thread:
            self.thread.quit()
            self.thread.wait(2000)
        up = len(self.devices)
        self.status_cb(f"Done — {up} device{'s' if up != 1 else ''} found on "
                       f"{self.subnet_edit.text().strip()}")

    def apply_filter(self, text):
        text = (text or "").lower().strip()
        for ip, row in self.row_for_ip.items():
            dev = self.devices.get(ip)
            if not dev:
                continue
            hay = " ".join([dev.ip, dev.hostname, dev.mac, dev.vendor,
                            dev.device_type]).lower()
            self.table.setRowHidden(row, bool(text) and text not in hay)

    def export_csv(self):
        if not self.devices:
            self.status_cb("Nothing to export — run a scan first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export devices", "lan-devices.csv", "CSV files (*.csv)")
        if not path:
            return
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["IP", "Hostname", "MAC", "Vendor", "Type",
                        "Open Ports", "Latency (ms)"])
            for dev in sorted(self.devices.values(), key=lambda d: d.ip_sortkey):
                w.writerow([dev.ip, dev.hostname, dev.mac, dev.vendor,
                            dev.device_type, " ".join(map(str, dev.open_ports)),
                            f"{dev.rtt_ms:.0f}" if dev.rtt_ms else ""])
        self.status_cb(f"Exported {len(self.devices)} devices → {path}")


# ---------------------------------------------------------------- WiFi tab
WIFI_COLS = ["Network (SSID)", "Signal", "RSSI", "Channel", "Band",
             "Width", "Security", "BSSID"]


class WifiTab(QWidget):
    def __init__(self, status_cb):
        super().__init__()
        self.status_cb = status_cb
        self.thread: QThread | None = None
        self.worker: WifiWorker | None = None
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.scan)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        bar = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Wi-Fi")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.clicked.connect(self.scan)
        self.auto_cb = QCheckBox("Auto-refresh (5s)")
        self.auto_cb.toggled.connect(self.toggle_auto)
        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName("subtle")
        bar.addWidget(self.scan_btn)
        bar.addWidget(self.auto_cb)
        bar.addStretch(1)
        bar.addWidget(self.count_lbl)
        root.addLayout(bar)

        # current connection card
        self.card = QFrame(); self.card.setObjectName("card")
        cl = QGridLayout(self.card)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setHorizontalSpacing(28)
        self.card_title = QLabel("CURRENT CONNECTION")
        self.card_title.setObjectName("cardTitle")
        self.cur_ssid = QLabel("—"); self.cur_ssid.setObjectName("cardBig")
        self.cur_bars = SignalBars(0)
        self._cur_fields = {}
        cl.addWidget(self.card_title, 0, 0, 1, 4)
        cl.addWidget(self.cur_ssid, 1, 0)
        cl.addWidget(self.cur_bars, 1, 1, Qt.AlignLeft)
        labels = ["Channel", "Band", "RSSI", "Tx Rate", "Security", "BSSID"]
        for i, name in enumerate(labels):
            t = QLabel(name); t.setObjectName("statLabel")
            v = QLabel("—"); v.setObjectName("subtle")
            v.setStyleSheet("color:#e6e9ef;font-weight:600;")
            self._cur_fields[name] = v
            cl.addWidget(t, 2, i)
            cl.addWidget(v, 3, i)
        root.addWidget(self.card)

        self.note = QLabel("")
        self.note.setObjectName("subtle")
        self.note.setWordWrap(True)
        root.addWidget(self.note)

        self.table = QTableWidget(0, len(WIFI_COLS))
        self.table.setHorizontalHeaderLabels(WIFI_COLS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 70)
        self.table.setColumnWidth(7, 150)
        self.table.verticalHeader().setDefaultSectionSize(34)
        root.addWidget(self.table, 1)

    def toggle_auto(self, on):
        if on:
            self.auto_timer.start(5000)
            self.scan()
        else:
            self.auto_timer.stop()

    def scan(self):
        if self.thread and self.thread.isRunning():
            return
        self.scan_btn.setEnabled(False)
        self.status_cb("Scanning Wi-Fi…")
        self.thread = QThread()
        self.worker = WifiWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.result.connect(self.on_result)
        self.thread.start()

    def on_result(self, st: wifi.WifiStatus):
        self.scan_btn.setEnabled(True)
        if self.thread:
            self.thread.quit(); self.thread.wait(2000)
        if not st.available:
            self.status_cb(st.error or "Wi-Fi unavailable")
            self.note.setText("⚠️  " + (st.error or "No Wi-Fi interface."))
            return

        self.cur_ssid.setText(st.current_ssid or "(not associated)")
        q = wifi.WifiNetwork(rssi=st.rssi).quality if st.rssi else 0
        self.cur_bars.set_quality(q)
        f = self._cur_fields
        f["Channel"].setText(str(st.channel) if st.channel else "—")
        f["Band"].setText(st.band or "—")
        f["RSSI"].setText(f"{st.rssi} dBm" if st.rssi else "—")
        f["Tx Rate"].setText(f"{st.tx_rate:.0f} Mbps" if st.tx_rate else "—")
        f["Security"].setText(st.security or "—")
        f["BSSID"].setText(st.current_bssid or "—")

        hidden_names = any(n.ssid in ("", "(hidden)") for n in st.networks)
        if hidden_names and st.networks:
            self.note.setText(
                "ℹ️  Network names/BSSIDs are blank because macOS requires "
                "Location Services permission for Wi-Fi scan results. "
                "Launch the built .app and grant Location access to see SSIDs. "
                "Signal, channel and security are accurate regardless.")
        else:
            self.note.setText("")

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for n in st.networks:
            self._add_row(n)
        self.table.setSortingEnabled(True)
        self.count_lbl.setText(f"{len(st.networks)} networks  ·  "
                               f"updated {time.strftime('%H:%M:%S')}")
        self.status_cb(f"Wi-Fi scan done — {len(st.networks)} networks")

    def _add_row(self, n: wifi.WifiNetwork):
        row = self.table.rowCount()
        self.table.insertRow(row)
        name = (n.ssid or "(hidden)") + ("  ●" if n.is_current else "")
        self.table.setItem(row, 0, make_item(
            name, color="#4c8dff" if n.is_current else "#ffffff"))
        meter = SignalMeter(n.quality, f"{n.quality}%")
        self.table.setCellWidget(row, 1, meter)
        self.table.setItem(row, 1, sort_item("", n.rssi))  # keep sortable
        self.table.setItem(row, 2, sort_item(f"{n.rssi} dBm", n.rssi, mono=True,
                                             color=quality_color(n.quality).name()))
        self.table.setItem(row, 3, sort_item(str(n.channel), n.channel, mono=True,
                                             align=Qt.AlignVCenter | Qt.AlignLeft))
        self.table.setItem(row, 4, make_item(n.band or "—"))
        self.table.setItem(row, 5, make_item(f"{n.width_mhz} MHz" if n.width_mhz else "—"))
        self.table.setItem(row, 6, make_item(n.security or "—",
                                             color="#ff8c8c" if n.security == "Open" else "#a9b2c7"))
        self.table.setItem(row, 7, make_item(n.bssid or "—", mono=True, color="#8b93a7"))


# ---------------------------------------------------------------- Info tab
class InfoTab(QWidget):
    def __init__(self, info: netinfo.InterfaceInfo):
        super().__init__()
        self.info = info
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)
        title = QLabel("Network Information")
        title.setObjectName("title")
        root.addWidget(title)

        card = QFrame(); card.setObjectName("card")
        g = QGridLayout(card)
        g.setContentsMargins(22, 20, 22, 20)
        g.setVerticalSpacing(14); g.setHorizontalSpacing(18)
        rows = [
            ("Interface", self.info.name),
            ("Your IPv4", self.info.ipv4),
            ("MAC address", self.info.mac),
            ("Subnet mask", self.info.netmask),
            ("Network (CIDR)", self.info.cidr),
            ("Scannable hosts", str(self.info.host_count)),
            ("Gateway / Router", self.info.gateway),
            ("Broadcast", self.info.broadcast),
            ("DNS servers", ", ".join(self.info.dns) or "—"),
        ]
        for i, (k, v) in enumerate(rows):
            kl = QLabel(k); kl.setObjectName("statLabel")
            vl = QLabel(v or "—")
            vl.setStyleSheet("color:#ffffff;font-size:14px;font-weight:600;")
            vl.setTextInteractionByMouse = True
            vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            g.addWidget(kl, i, 0, Qt.AlignRight)
            g.addWidget(vl, i, 1)
        g.setColumnStretch(1, 1)
        root.addWidget(card)
        root.addStretch(1)

        hint = QLabel(
            "BetterLanScan discovers devices with a concurrent ICMP sweep, "
            "resolves MAC addresses from the ARP cache, identifies vendors via "
            "the IEEE OUI registry, and fingerprints device types from open "
            "ports. Wi-Fi data comes from Apple CoreWLAN.")
        hint.setObjectName("subtle")
        hint.setWordWrap(True)
        root.addWidget(hint)


# ---------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.resize(1080, 720)
        self.setMinimumSize(880, 560)

        self.info = netinfo.get_interface_info()

        central = QWidget(); central.setObjectName("root")
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        header.setContentsMargins(20, 16, 20, 0)
        logo = QLabel("🛰  BetterLanScan")
        logo.setObjectName("title")
        sub = QLabel("Network & Wi-Fi scanner")
        sub.setObjectName("subtle")
        header.addWidget(logo)
        header.addSpacing(10)
        header.addWidget(sub)
        header.addStretch(1)
        lay.addLayout(header)

        self.tabs = QTabWidget()
        self.lan_tab = LanTab(self.info, self.set_status)
        self.wifi_tab = WifiTab(self.set_status)
        self.info_tab = InfoTab(self.info)
        self.tabs.addTab(self.lan_tab, "  LAN Devices  ")
        self.tabs.addTab(self.wifi_tab, "  Wi-Fi Networks  ")
        self.tabs.addTab(self.info_tab, "  Network Info  ")
        lay.addWidget(self.tabs)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.set_status(f"Ready · {self.info.cidr or 'no network'} · "
                        f"{self.info.host_count} hosts")

    def set_status(self, msg):
        self.statusBar().showMessage(msg)


def _fix_macos_menu_name(name: str) -> None:
    """Force the macOS menu bar to show 'name' instead of 'Python'.

    PyInstaller bootstraps via an internal Python loader; macOS reads the
    menu-bar label from NSRunningApplication.localizedName which in turn
    comes from CFBundleName in the *process* bundle — which can resolve to
    the embedded Python.framework before Qt sets its own name. We override it
    explicitly through the Foundation bundle dictionary.
    """
    try:
        from Foundation import NSBundle
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info is not None:
            info["CFBundleName"] = name
            info["CFBundleDisplayName"] = name
    except Exception:
        pass
    try:
        # Belt-and-suspenders: also rename the process itself.
        import ctypes, ctypes.util
        libc = ctypes.CDLL(ctypes.util.find_library("c"))
        # setprogname(3) — macOS-specific
        libc.setprogname(name.encode())
    except Exception:
        pass


def run():
    import sys
    _fix_macos_menu_name(__app_name__)
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationDisplayName(__app_name__)
    app.setStyleSheet(QSS)
    # Request Location auth so Wi-Fi scans can return SSIDs/BSSIDs.
    try:
        from . import location
        location.request_authorization()
    except Exception:
        pass
    win = MainWindow()
    win.show()

    # Debug: BLS_SHOT=/path renders the window to PNG then quits.
    import os
    shot = os.environ.get("BLS_SHOT")
    if shot:
        tab = int(os.environ.get("BLS_TAB", "0"))
        delay = int(os.environ.get("BLS_DELAY", "1200"))
        win.tabs.setCurrentIndex(tab)
        if tab == 1:
            win.wifi_tab.scan()
        elif tab == 0 and os.environ.get("BLS_RUNSCAN"):
            win.lan_tab.start_scan()
        QTimer.singleShot(delay, lambda: (win.grab().save(shot), app.quit()))

    sys.exit(app.exec())
