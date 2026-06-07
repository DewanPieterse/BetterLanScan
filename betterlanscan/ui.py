"""BetterLanScan main window — v2."""
from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
import time
import datetime
import subprocess

from PySide6.QtCore import Qt, QObject, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QStatusBar,
    QFileDialog, QAbstractItemView, QComboBox, QSplitter, QScrollArea,
    QDialog, QDialogButtonBox, QSpinBox, QTextEdit, QSizePolicy,
)

from . import netinfo, scanner, wifi, db as _db, __version__, __app_name__
from .style import QSS
from .widgets import SignalBars, StatusDot, SignalMeter, quality_color
from .detail_panel import DeviceDetailPanel
from .topology_widget import TopologyWidget
from .wifi_graphs import ChannelGraph, RSSIHistoryChart

MONO = "SF Mono, Menlo, monospace"


# ---------------------------------------------------------------- helpers
def _fix_macos_menu_name(name: str) -> None:
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
        import ctypes, ctypes.util
        libc = ctypes.CDLL(ctypes.util.find_library("c"))
        libc.setprogname(name.encode())
    except Exception:
        pass


def make_item(text, *, mono=False, color=None,
              align=Qt.AlignVCenter | Qt.AlignLeft):
    it = QTableWidgetItem(str(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    it.setTextAlignment(align)
    if mono: it.setFont(QFont(MONO.split(",")[0].strip(), 11))
    if color: it.setForeground(QColor(color))
    return it


class SortItem(QTableWidgetItem):
    def __lt__(self, other):
        a, b = self.data(Qt.UserRole), other.data(Qt.UserRole)
        if a is not None and b is not None: return a < b
        return super().__lt__(other)


def sort_item(text, value, **kw):
    it = SortItem(str(text))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    it.setData(Qt.UserRole, value)
    it.setTextAlignment(kw.get("align", Qt.AlignVCenter | Qt.AlignLeft))
    if kw.get("mono"): it.setFont(QFont(MONO.split(",")[0].strip(), 11))
    if kw.get("color"): it.setForeground(QColor(kw["color"]))
    return it


# ---------------------------------------------------------------- workers
class ScanWorker(QObject):
    device  = Signal(object)
    progress = Signal(int, int)
    done    = Signal(list)
    new_dev = Signal(object)

    def __init__(self, hosts, self_ip, gateway_ip, do_ports, extra_ports):
        super().__init__()
        self.hosts = hosts; self.self_ip = self_ip; self.gateway_ip = gateway_ip
        self.do_ports = do_ports; self.extra_ports = extra_ports
        self.ctl = scanner.ScanController(
            on_device=lambda d: self.device.emit(d),
            on_progress=lambda a, b: self.progress.emit(a, b),
            on_done=lambda devs: self.done.emit(devs),
            on_new_device=lambda d: self.new_dev.emit(d),
        )

    def run(self):
        self.ctl.start(self.hosts, self_ip=self.self_ip,
                       gateway_ip=self.gateway_ip, do_ports=self.do_ports,
                       extra_ports=self.extra_ports)
        while self.ctl.running: time.sleep(0.1)

    def stop(self): self.ctl.stop()


class WifiWorker(QObject):
    result = Signal(object)
    def run(self): self.result.emit(wifi.get_status(active_scan=True))


class SpeedWorker(QObject):
    progress = Signal(str, object)
    result   = Signal(object)
    def run(self):
        from . import speedtest
        r = speedtest.run(lambda s, v: self.progress.emit(s, v))
        self.result.emit(r)


class TraceWorker(QObject):
    result = Signal(str)

    def __init__(self, target: str):
        super().__init__()
        self._target = target

    def run(self):
        from . import traceroute
        hops = traceroute.run(self._target, max_hops=20, timeout_s=25)
        self.result.emit("\n".join(h.display for h in hops))


# ---------------------------------------------------------------- LAN tab
LAN_COLS = ["", "★", "IP Address", "Name / Host", "OS", "MAC Address",
            "Vendor", "Type", "Open ports", "Latency"]


class LanTab(QWidget):
    def __init__(self, info: netinfo.InterfaceInfo, status_cb):
        super().__init__()
        self.info = info
        self.status_cb = status_cb
        self.devices: dict[str, scanner.Device] = {}
        self.row_for_ip: dict[str, int] = {}
        self.thread: QThread | None = None
        self.worker: ScanWorker | None = None
        self._filter_mode = "all"
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 0, 14); root.setSpacing(10)

        # ---- toolbar
        bar = QHBoxLayout(); bar.setSpacing(8)
        bar.setContentsMargins(0, 0, 20, 0)

        lbl = QLabel("Subnet"); lbl.setObjectName("subtle")
        self.subnet_edit = QLineEdit(self.info.cidr or "192.168.1.0/24")
        self.subnet_edit.setFixedWidth(155)
        self.subnet_edit.setToolTip("CIDR subnet to scan (e.g. 192.168.1.0/24). "
                                    "Separate multiple with comma.")

        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.clicked.connect(self.toggle_scan)

        self.ports_cb = QCheckBox("Port scan")
        self.ports_cb.setChecked(True)

        self.extra_ports_edit = QLineEdit()
        self.extra_ports_edit.setPlaceholderText("Extra ports (e.g. 8888,9000)")
        self.extra_ports_edit.setFixedWidth(180)
        self.extra_ports_edit.setToolTip("Comma-separated additional ports beyond the default set")

        filter_lbl = QLabel("Show:"); filter_lbl.setObjectName("subtle")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All devices", "⭐ Favourites", "🆕 New devices",
                                     "⚠ ARP conflicts"])
        self.filter_combo.currentIndexChanged.connect(self._on_filter_mode_changed)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter…")
        self.search.setFixedWidth(140)
        self.search.textChanged.connect(self.apply_filter)

        self.export_btn = QPushButton("Export ▾")
        self.export_btn.clicked.connect(self._show_export_menu)

        bar.addWidget(lbl); bar.addWidget(self.subnet_edit)
        bar.addWidget(self.scan_btn); bar.addWidget(self.ports_cb)
        bar.addWidget(self.extra_ports_edit); bar.addStretch(1)
        bar.addWidget(filter_lbl); bar.addWidget(self.filter_combo)
        bar.addWidget(self.search); bar.addWidget(self.export_btn)
        root.addLayout(bar)

        # ---- stat chips
        chips = QHBoxLayout(); chips.setSpacing(10)
        chips.setContentsMargins(0, 0, 20, 0)
        self.chip_found   = self._chip("DEVICES FOUND", "0")
        self.chip_scanned = self._chip("PROGRESS", "0 / 0")
        self.chip_gateway = self._chip("GATEWAY", self.info.gateway or "—")
        self.chip_subnet  = self._chip("YOUR IP", self.info.ipv4 or "—")
        self.chip_new     = self._chip("NEW DEVICES", "0")
        for c in (self.chip_found, self.chip_scanned, self.chip_gateway,
                  self.chip_subnet, self.chip_new):
            chips.addWidget(c)
        chips.addStretch(1); root.addLayout(chips)

        # ---- progress bar
        self.progress = QProgressBar()
        self.progress.setTextVisible(False); self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        # ---- table + detail panel
        split = QHBoxLayout(); split.setContentsMargins(0,0,0,0); split.setSpacing(0)
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
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 30); self.table.setColumnWidth(1, 26)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.setColumnWidth(2, 120); self.table.setColumnWidth(4, 28)
        self.table.setColumnWidth(5, 140); self.table.setColumnWidth(7, 120)
        self.table.setColumnWidth(8, 140); self.table.setColumnWidth(9, 70)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self.table.doubleClicked.connect(self._on_double_click)
        split.addWidget(self.table, 1)

        self.detail_panel = DeviceDetailPanel()
        self.detail_panel.closed.connect(self._on_panel_closed)
        split.addWidget(self.detail_panel)
        root.addLayout(split, 1)

    def _chip(self, title, value):
        f = QFrame(); f.setObjectName("statChip"); f.setFixedHeight(58)
        f.setMinimumWidth(130)
        lay = QVBoxLayout(f); lay.setContentsMargins(12, 6, 12, 6); lay.setSpacing(1)
        t = QLabel(title); t.setObjectName("statLabel")
        v = QLabel(value); v.setObjectName("statValue")
        f._value = v; lay.addWidget(t); lay.addWidget(v); return f

    # ---- scanning
    def toggle_scan(self):
        if self.thread and self.thread.isRunning():
            self.worker.stop(); return
        self.start_scan()

    def start_scan(self):
        subnets = [s.strip() for s in self.subnet_edit.text().split(",") if s.strip()]
        hosts: list[str] = []
        for cidr in subnets:
            try: hosts += netinfo.hosts_for_cidr(cidr)
            except Exception as e: self.status_cb(f"Bad subnet {cidr}: {e}"); return

        extra_ports: list[int] = []
        for part in self.extra_ports_edit.text().split(","):
            part = part.strip()
            if part.isdigit(): extra_ports.append(int(part))

        self.devices.clear(); self.row_for_ip.clear()
        self.table.setSortingEnabled(False); self.table.setRowCount(0)
        self.chip_found._value.setText("0"); self.chip_new._value.setText("0")
        self.progress.setValue(0)
        self.scan_btn.setText("Stop"); self.scan_btn.setObjectName("danger")
        self._restyle(self.scan_btn)
        self.status_cb(f"Scanning {', '.join(subnets)} — {len(hosts)} hosts…")

        self.thread = QThread()
        self.worker = ScanWorker(hosts, self.info.ipv4, self.info.gateway,
                                 self.ports_cb.isChecked(), extra_ports)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.device.connect(self.on_device)
        self.worker.progress.connect(self.on_progress)
        self.worker.done.connect(self.on_done)
        self.worker.new_dev.connect(lambda d: self.chip_new._value.setText(
            str(int(self.chip_new._value.text() or "0") + 1)))
        self.thread.start()

    def _restyle(self, w):
        w.style().unpolish(w); w.style().polish(w)

    def on_progress(self, done, total):
        self.progress.setRange(0, total); self.progress.setValue(done)
        self.chip_scanned._value.setText(f"{done} / {total}")

    def on_device(self, dev: scanner.Device):
        self.devices[dev.ip] = dev
        if dev.ip in self.row_for_ip:
            self._fill_row(self.row_for_ip[dev.ip], dev)
        else:
            row = self.table.rowCount(); self.table.insertRow(row)
            self.row_for_ip[dev.ip] = row; self._fill_row(row, dev)
        self.chip_found._value.setText(str(len(self.devices)))
        self.apply_filter(self.search.text())
        # push to topology
        self._push_topology()

    def _fill_row(self, row, dev: scanner.Device):
        # status dot
        col = "#4c8dff" if dev.is_self else ("#ffc24c" if dev.is_gateway else "#3ddc84")
        if dev.arp_conflict: col = "#ff4444"
        dot = StatusDot(col)
        wrap = QWidget(); wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0,0,0,0); wl.addWidget(dot, 0, Qt.AlignCenter)
        self.table.setCellWidget(row, 0, wrap)

        # fav star
        fav = "★" if dev.is_favourite else ""
        fi = make_item(fav, color="#ffc24c" if fav else "#5a6075",
                       align=Qt.AlignCenter)
        self.table.setItem(row, 1, fi)

        # IP
        ip_text = dev.ip + ("  (you)" if dev.is_self else " (gw)" if dev.is_gateway else "")
        self.table.setItem(row, 2, sort_item(ip_text, dev.ip_sortkey, mono=True,
                                             color="#ffffff"))

        # Name / host
        name = dev.custom_name or dev.hostname or "—"
        new_badge = "  🆕" if dev.is_new else ""
        self.table.setItem(row, 3, make_item(name + new_badge,
                                             color="#cdd3e0" if name != "—" else "#5a6075"))

        # OS icon
        self.table.setItem(row, 4, make_item(dev.os_icon or "❓",
                                             align=Qt.AlignCenter))

        # MAC
        self.table.setItem(row, 5, make_item(dev.mac or "—", mono=True,
                                             color="#cdd3e0" if dev.mac else "#5a6075"))

        # Vendor
        self.table.setItem(row, 6, make_item(dev.vendor or "—",
                                             color="#cdd3e0" if dev.vendor and dev.vendor != "Unknown" else "#5a6075"))

        # Type
        self.table.setItem(row, 7, make_item(dev.device_type or "—", color="#a9b2c7"))

        # Ports
        ports = ", ".join(f"{p}/{scanner.COMMON_PORTS.get(p,'?')}" for p in dev.open_ports[:5])
        if len(dev.open_ports) > 5: ports += f" +{len(dev.open_ports)-5}"
        self.table.setItem(row, 8, make_item(ports or "—",
                                             color="#7fd1a8" if dev.open_ports else "#5a6075"))

        # Latency
        rtt = f"{dev.rtt_ms:.0f} ms" if dev.rtt_ms is not None else "—"
        self.table.setItem(row, 9, sort_item(rtt, dev.rtt_ms if dev.rtt_ms is not None else 9e9,
                                             mono=True, align=Qt.AlignRight | Qt.AlignVCenter,
                                             color="#a9b2c7"))

    def on_done(self, devices):
        self.scan_btn.setText("Scan"); self.scan_btn.setObjectName("primary")
        self._restyle(self.scan_btn)
        self.table.setSortingEnabled(True)
        if self.thread: self.thread.quit(); self.thread.wait(2000)
        self.status_cb(f"Done — {len(self.devices)} devices on "
                       f"{self.subnet_edit.text().strip()}")
        self._push_topology()

    def _push_topology(self):
        # push devices to topology widget (accessed via parent tabs)
        try:
            win = self.window()
            if hasattr(win, "topo_tab"):
                win.topo_tab.topo.set_devices(list(self.devices.values()))
        except Exception:
            pass

    # ---- selection
    def _on_row_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows: return
        ip_text = (self.table.item(rows[0].row(), 2) or QTableWidgetItem()).text()
        ip = ip_text.split()[0]
        dev = self.devices.get(ip)
        if dev: self.detail_panel.show_device(dev)

    def _on_panel_closed(self): self.table.clearSelection()

    def _on_double_click(self, idx):
        ip_text = (self.table.item(idx.row(), 2) or QTableWidgetItem()).text()
        ip = ip_text.split()[0]
        dev = self.devices.get(ip)
        if dev: self.detail_panel.show_device(dev)

    # ---- filter
    def _on_filter_mode_changed(self, idx):
        modes = ["all", "fav", "new", "arp"]
        self._filter_mode = modes[idx]
        self.apply_filter(self.search.text())

    def apply_filter(self, text):
        text = (text or "").lower().strip()
        for ip, row in self.row_for_ip.items():
            dev = self.devices.get(ip)
            if not dev: continue
            mode_ok = (
                self._filter_mode == "all" or
                (self._filter_mode == "fav" and dev.is_favourite) or
                (self._filter_mode == "new" and dev.is_new) or
                (self._filter_mode == "arp" and dev.arp_conflict)
            )
            hay = " ".join([dev.ip, dev.hostname, dev.mac, dev.vendor,
                            dev.device_type, dev.custom_name, dev.os_guess]).lower()
            text_ok = not text or text in hay
            self.table.setRowHidden(row, not (mode_ok and text_ok))

    # ---- export
    def _show_export_menu(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.addAction("Export CSV",  lambda: self._export("csv"))
        menu.addAction("Export JSON", lambda: self._export("json"))
        menu.addAction("Export XML",  lambda: self._export("xml"))
        menu.exec(self.export_btn.mapToGlobal(self.export_btn.rect().bottomLeft()))

    def _export(self, fmt: str):
        if not self.devices:
            self.status_cb("Nothing to export — run a scan first."); return
        exts = {"csv": "CSV files (*.csv)", "json": "JSON files (*.json)",
                "xml": "XML files (*.xml)"}
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export devices", f"lan-devices.{fmt}", exts[fmt])
        if not path: return
        devs = sorted(self.devices.values(), key=lambda d: d.ip_sortkey)
        if fmt == "csv":
            with open(path, "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["IP","Hostname","Custom Name","MAC","Vendor","OS","Type",
                            "Open Ports","Latency ms","Favourite","Notes"])
                for d in devs:
                    w.writerow([d.ip, d.hostname, d.custom_name, d.mac, d.vendor,
                                d.os_guess, d.device_type,
                                " ".join(map(str, d.open_ports)),
                                f"{d.rtt_ms:.0f}" if d.rtt_ms else "",
                                int(d.is_favourite), d.notes])
        elif fmt == "json":
            data = []
            for d in devs:
                data.append({"ip": d.ip, "hostname": d.hostname,
                             "custom_name": d.custom_name, "mac": d.mac,
                             "vendor": d.vendor, "os": d.os_guess,
                             "device_type": d.device_type,
                             "open_ports": d.open_ports,
                             "latency_ms": d.rtt_ms,
                             "favourite": d.is_favourite, "notes": d.notes})
            with open(path, "w") as fh:
                json.dump(data, fh, indent=2)
        elif fmt == "xml":
            root = ET.Element("devices")
            for d in devs:
                el = ET.SubElement(root, "device")
                for k, v in [("ip", d.ip), ("hostname", d.hostname),
                              ("mac", d.mac), ("vendor", d.vendor),
                              ("os", d.os_guess), ("type", d.device_type),
                              ("latency_ms", str(d.rtt_ms or "")),
                              ("favourite", str(int(d.is_favourite))),
                              ("notes", d.notes)]:
                    ET.SubElement(el, k).text = v
                ports = ET.SubElement(el, "open_ports")
                for p in d.open_ports:
                    ET.SubElement(ports, "port").text = str(p)
            ET.ElementTree(root).write(path, encoding="unicode", xml_declaration=True)
        self.status_cb(f"Exported {len(devs)} devices → {path}")


# ---------------------------------------------------------------- Wi-Fi tab
WIFI_COLS = ["Network (SSID)", "Signal", "RSSI", "Channel", "Band",
             "Width", "Security", "BSSID"]


class WifiTab(QWidget):
    def __init__(self, status_cb):
        super().__init__()
        self.status_cb = status_cb
        self.thread: QThread | None = None
        self.worker = None
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.scan)
        self._networks: list = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(20,14,20,14); root.setSpacing(10)

        bar = QHBoxLayout(); bar.setSpacing(8)
        self.scan_btn = QPushButton("Scan Wi-Fi")
        self.scan_btn.setObjectName("primary"); self.scan_btn.clicked.connect(self.scan)
        self.auto_cb = QCheckBox("Auto-refresh (5s)"); self.auto_cb.toggled.connect(self.toggle_auto)
        self.count_lbl = QLabel(""); self.count_lbl.setObjectName("subtle")
        bar.addWidget(self.scan_btn); bar.addWidget(self.auto_cb)
        bar.addStretch(1); bar.addWidget(self.count_lbl)
        root.addLayout(bar)

        # current connection card
        self.card = QFrame(); self.card.setObjectName("card")
        cl = QGridLayout(self.card); cl.setContentsMargins(16,12,16,12)
        cl.setHorizontalSpacing(24)
        self.card_title = QLabel("CURRENT CONNECTION"); self.card_title.setObjectName("cardTitle")
        self.cur_ssid = QLabel("—"); self.cur_ssid.setObjectName("cardBig")
        self.cur_bars = SignalBars(0)
        self._cur_fields = {}
        cl.addWidget(self.card_title, 0, 0, 1, 6)
        cl.addWidget(self.cur_ssid, 1, 0); cl.addWidget(self.cur_bars, 1, 1, Qt.AlignLeft)
        for i, name in enumerate(["Channel","Band","RSSI","Tx Rate","Security","BSSID"]):
            t = QLabel(name); t.setObjectName("statLabel")
            v = QLabel("—"); v.setStyleSheet("color:#e6e9ef;font-weight:600;")
            self._cur_fields[name] = v
            cl.addWidget(t, 2, i); cl.addWidget(v, 3, i)
        root.addWidget(self.card)

        # sub-tabs: list / 2.4 GHz graph / 5 GHz graph / History
        self.sub_tabs = QTabWidget()
        self.sub_tabs.setStyleSheet(
            "QTabBar::tab{padding:6px 14px;font-size:12px;}"
            "QTabBar::tab:selected{border-bottom:2px solid #4c8dff;}")

        # list view
        list_w = QWidget(); list_lay = QVBoxLayout(list_w)
        list_lay.setContentsMargins(0,8,0,0); list_lay.setSpacing(6)
        self.note = QLabel(""); self.note.setObjectName("subtle"); self.note.setWordWrap(True)
        list_lay.addWidget(self.note)
        self.table = QTableWidget(0, len(WIFI_COLS))
        self.table.setHorizontalHeaderLabels(WIFI_COLS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setShowGrid(False); self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch); hh.setSectionResizeMode(6, QHeaderView.Stretch)
        self.table.setColumnWidth(1,100); self.table.setColumnWidth(2,80)
        self.table.setColumnWidth(3,80); self.table.setColumnWidth(4,80)
        self.table.setColumnWidth(5,70); self.table.setColumnWidth(7,150)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.itemSelectionChanged.connect(self._on_net_selected)
        list_lay.addWidget(self.table, 1)

        # channel graphs
        self._ch24 = ChannelGraph()
        self._ch5  = ChannelGraph()

        # history chart
        hist_w = QWidget(); hist_lay = QVBoxLayout(hist_w)
        hist_lay.setContentsMargins(0,8,0,0); hist_lay.setSpacing(6)
        self._hist_lbl = QLabel("Select a network in the List tab to see RSSI history.")
        self._hist_lbl.setObjectName("subtle")
        self._rssi_chart = RSSIHistoryChart()
        hist_lay.addWidget(self._hist_lbl)
        hist_lay.addWidget(self._rssi_chart, 1)

        self.sub_tabs.addTab(list_w, " List ")
        self.sub_tabs.addTab(self._ch24, " 2.4 GHz Channel ")
        self.sub_tabs.addTab(self._ch5,  " 5 GHz Channel ")
        self.sub_tabs.addTab(hist_w,     " RSSI History ")
        root.addWidget(self.sub_tabs, 1)

    def toggle_auto(self, on):
        if on: self.auto_timer.start(5000); self.scan()
        else:  self.auto_timer.stop()

    def scan(self):
        if self.thread and self.thread.isRunning(): return
        self.scan_btn.setEnabled(False); self.status_cb("Scanning Wi-Fi…")
        self.thread = QThread(); self.worker = WifiWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.result.connect(self.on_result)
        self.thread.start()

    def on_result(self, st):
        self.scan_btn.setEnabled(True)
        if self.thread: self.thread.quit(); self.thread.wait(2000)
        if not st.available:
            self.status_cb(st.error or "Wi-Fi unavailable"); return

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

        self._networks = st.networks
        hidden = any(n.ssid in ("", "(hidden)") for n in st.networks)
        if hidden and st.networks:
            self.note.setText(
                'ℹ️  SSIDs hidden — BetterLanScan needs Location Services to see network names.  '
                '<a href="x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices"'
                ' style="color:#4c8dff;">Open Location Settings</a>'
            )
            self.note.setOpenExternalLinks(True)
        else:
            self.note.setText("")

        # persist Wi-Fi history
        for n in st.networks:
            _db.log_wifi(n.bssid, n.ssid, n.rssi, n.channel, n.band, n.security)

        self.table.setSortingEnabled(False); self.table.setRowCount(0)
        for n in st.networks:
            self._add_row(n)
        self.table.setSortingEnabled(True)
        self.count_lbl.setText(f"{len(st.networks)} networks  ·  updated {time.strftime('%H:%M:%S')}")
        self.status_cb(f"Wi-Fi scan done — {len(st.networks)} networks")

        self._ch24.set_networks(st.networks, "2.4 GHz")
        self._ch5.set_networks(st.networks, "5 GHz")

    def _add_row(self, n):
        row = self.table.rowCount(); self.table.insertRow(row)
        name = (n.ssid or "(hidden)") + ("  ●" if n.is_current else "")
        self.table.setItem(row, 0, make_item(name, color="#4c8dff" if n.is_current else "#ffffff"))
        meter = SignalMeter(n.quality, f"{n.quality}%")
        self.table.setCellWidget(row, 1, meter)
        self.table.setItem(row, 1, sort_item("", n.rssi))
        self.table.setItem(row, 2, sort_item(f"{n.rssi} dBm", n.rssi, mono=True,
                                             color=quality_color(n.quality).name()))
        self.table.setItem(row, 3, sort_item(str(n.channel), n.channel, mono=True))
        self.table.setItem(row, 4, make_item(n.band or "—"))
        self.table.setItem(row, 5, make_item(f"{n.width_mhz} MHz" if n.width_mhz else "—"))
        self.table.setItem(row, 6, make_item(n.security or "—",
                                             color="#ff8c8c" if n.security == "Open" else "#a9b2c7"))
        self.table.setItem(row, 7, make_item(n.bssid or "—", mono=True, color="#8b93a7"))

    def _on_net_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows: return
        bssid_item = self.table.item(rows[0].row(), 7)
        if not bssid_item: return
        bssid = bssid_item.text().strip()
        ssid_item = self.table.item(rows[0].row(), 0)
        ssid = ssid_item.text().strip() if ssid_item else bssid
        history = _db.wifi_rssi_history(bssid, limit=200)
        self._rssi_chart.set_data(history, ssid)
        self.sub_tabs.setCurrentIndex(3)


# ---------------------------------------------------------------- Topology tab
class TopologyTab(QWidget):
    def __init__(self, status_cb):
        super().__init__()
        self.status_cb = status_cb
        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0)
        hdr = QHBoxLayout(); hdr.setContentsMargins(20,12,20,8)
        t = QLabel("Network Topology"); t.setObjectName("title")
        hint = QLabel("Drag nodes · click to inspect · run a LAN scan to populate")
        hint.setObjectName("subtle")
        hdr.addWidget(t); hdr.addSpacing(12); hdr.addWidget(hint); hdr.addStretch(1)
        root.addLayout(hdr)
        self.topo = TopologyWidget()
        self.topo.device_selected.connect(self._on_select)
        root.addWidget(self.topo, 1)

    def _on_select(self, dev):
        self.status_cb(f"Selected: {dev.display_name}  {dev.ip}  {dev.os_icon} {dev.os_guess}")


# ---------------------------------------------------------------- Tools tab
class ToolsTab(QWidget):
    def __init__(self, info: netinfo.InterfaceInfo, status_cb):
        super().__init__()
        self.info = info; self.status_cb = status_cb
        self._speed_thread: QThread | None = None
        self._speed_worker: SpeedWorker | None = None
        self._trace_thread: QThread | None = None
        self._trace_worker: TraceWorker | None = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self); root.setContentsMargins(20,14,20,14); root.setSpacing(16)
        title = QLabel("Network Tools"); title.setObjectName("title")
        root.addWidget(title)

        cols = QHBoxLayout(); cols.setSpacing(16); cols.setAlignment(Qt.AlignTop)

        # ---- Speed test card
        speed_card = self._card("⚡  Internet Speed Test")
        sl = speed_card.layout()
        self._dl_lbl  = QLabel("—"); self._dl_lbl.setObjectName("cardBig")
        self._ul_lbl  = QLabel("—"); self._ul_lbl.setObjectName("cardBig")
        self._lat_lbl = QLabel("—")
        self._lat_lbl.setStyleSheet("color:#a9b2c7;font-size:13px;font-weight:600;")
        sl.addWidget(QLabel("Download")); sl.addWidget(self._dl_lbl)
        sl.addWidget(QLabel("Upload"));   sl.addWidget(self._ul_lbl)
        sl.addWidget(QLabel("Latency"));  sl.addWidget(self._lat_lbl)
        self._speed_prog = QProgressBar(); self._speed_prog.setRange(0,0)
        self._speed_prog.setTextVisible(False); self._speed_prog.setFixedHeight(4)
        self._speed_prog.hide(); sl.addWidget(self._speed_prog)
        self._speed_btn = QPushButton("Run Speed Test"); self._speed_btn.setObjectName("primary")
        self._speed_btn.clicked.connect(self._run_speed)
        sl.addWidget(self._speed_btn)
        cols.addWidget(speed_card, 1)

        # ---- DNS lookup card
        dns_card = self._card("🔍  DNS Lookup")
        dl = dns_card.layout()
        self._dns_edit = QLineEdit(); self._dns_edit.setPlaceholderText("hostname or IP…")
        self._dns_btn = QPushButton("Lookup"); self._dns_btn.setObjectName("primary")
        self._dns_btn.clicked.connect(self._run_dns)
        self._dns_edit.returnPressed.connect(self._run_dns)
        self._dns_result = QTextEdit(); self._dns_result.setReadOnly(True)
        self._dns_result.setFixedHeight(80)
        self._dns_result.setStyleSheet(
            "background:#20242f;border:1px solid #2c3140;border-radius:6px;color:#7fd1a8;font-size:11px;")
        dl.addWidget(self._dns_edit); dl.addWidget(self._dns_btn); dl.addWidget(self._dns_result)
        cols.addWidget(dns_card, 1)

        root.addLayout(cols)

        # ---- Ping / Traceroute card (full width)
        pt_card = self._card("📡  Ping & Traceroute")
        ptl = pt_card.layout()
        pr = QHBoxLayout(); pr.setSpacing(8)
        self._pt_edit = QLineEdit(); self._pt_edit.setPlaceholderText("IP or hostname…")
        self._pt_edit.setText(self.info.gateway or "")
        self._ping_btn  = QPushButton("Ping once");      self._ping_btn.clicked.connect(self._run_ping)
        self._trace_btn = QPushButton("Traceroute");     self._trace_btn.clicked.connect(self._run_trace)
        self._ping_btn.setObjectName("primary"); self._trace_btn.setObjectName("primary")
        pr.addWidget(self._pt_edit,1); pr.addWidget(self._ping_btn); pr.addWidget(self._trace_btn)
        ptl.addLayout(pr)
        self._pt_result = QTextEdit(); self._pt_result.setReadOnly(True); self._pt_result.setFixedHeight(140)
        self._pt_result.setStyleSheet(
            "background:#20242f;border:1px solid #2c3140;border-radius:6px;"
            "color:#cdd3e0;font-size:11px;font-family:'SF Mono',Menlo,monospace;")
        ptl.addWidget(self._pt_result)
        root.addWidget(pt_card)

        # ---- Scan history
        hist_card = self._card("🕑  Scan History")
        hl = hist_card.layout()
        self._hist_table = QTableWidget(0, 3)
        self._hist_table.setHorizontalHeaderLabels(["Time","Subnet","Devices"])
        self._hist_table.setShowGrid(False); self._hist_table.setAlternatingRowColors(True)
        self._hist_table.verticalHeader().setVisible(False)
        self._hist_table.setFixedHeight(120)
        self._hist_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        hl.addWidget(self._hist_table)
        self._refresh_history()
        root.addWidget(hist_card)
        root.addStretch(1)

    def _card(self, title: str) -> QFrame:
        f = QFrame(); f.setObjectName("card")
        lay = QVBoxLayout(f); lay.setContentsMargins(16,12,16,14); lay.setSpacing(8)
        t = QLabel(title); t.setObjectName("cardTitle"); t.setContentsMargins(0,0,0,4)
        lay.addWidget(t); return f

    def _run_speed(self):
        if self._speed_thread and self._speed_thread.isRunning(): return
        self._dl_lbl.setText("…"); self._ul_lbl.setText("…"); self._lat_lbl.setText("…")
        self._speed_prog.show(); self._speed_btn.setEnabled(False)
        self._speed_thread = QThread(); self._speed_worker = SpeedWorker()
        self._speed_worker.moveToThread(self._speed_thread)
        self._speed_thread.started.connect(self._speed_worker.run)
        self._speed_worker.progress.connect(self._on_speed_progress)
        self._speed_worker.result.connect(self._on_speed_done)
        self._speed_thread.start()

    def _on_speed_progress(self, stage, val):
        if stage == "download" and val:
            self._dl_lbl.setText(f"{val/1e6:.1f} MB…")

    def _on_speed_done(self, r):
        self._speed_prog.hide(); self._speed_btn.setEnabled(True)
        if self._speed_thread: self._speed_thread.quit(); self._speed_thread.wait(2000)
        self._speed_worker = None
        self._dl_lbl.setText(f"{r.download_mbps:.1f} Mbps" if r.download_mbps else "—")
        self._ul_lbl.setText(f"{r.upload_mbps:.1f} Mbps"  if r.upload_mbps else "—")
        self._lat_lbl.setText(f"{r.latency_ms:.0f} ms" if r.latency_ms else "—")
        self.status_cb(f"Speed test: ↓{r.download_mbps:.0f}  ↑{r.upload_mbps:.0f} Mbps" if r.download_mbps else "Speed test failed")

    def _run_dns(self):
        import socket
        target = self._dns_edit.text().strip()
        if not target: return
        try:
            try:
                ip = socket.gethostbyname(target)
                host = socket.gethostbyaddr(ip)[0]
                info = socket.getaddrinfo(target, None)
                lines = [f"Forward:  {target} → {ip}",
                         f"Reverse:  {ip} → {host}"]
                ipv6 = [ai[4][0] for ai in info if ai[0].name == "AF_INET6"]
                if ipv6: lines.append(f"IPv6:     {', '.join(set(ipv6))}")
                self._dns_result.setPlainText("\n".join(lines))
            except socket.herror:
                self._dns_result.setPlainText(f"No reverse DNS for {target}")
        except Exception as e:
            self._dns_result.setPlainText(f"Error: {e}")

    def _run_ping(self):
        target = self._pt_edit.text().strip()
        if not target: return
        try:
            out = subprocess.run(["ping","-c","5","-W","1000",target],
                                 capture_output=True, text=True, timeout=10).stdout
            self._pt_result.setPlainText(out)
        except Exception as e:
            self._pt_result.setPlainText(str(e))

    def _run_trace(self):
        if self._trace_thread and self._trace_thread.isRunning():
            return
        target = self._pt_edit.text().strip()
        if not target:
            return
        self._pt_result.setPlainText("Running traceroute…")
        self._trace_thread = QThread()
        self._trace_worker = TraceWorker(target)
        self._trace_worker.moveToThread(self._trace_thread)
        self._trace_thread.started.connect(self._trace_worker.run)
        self._trace_worker.result.connect(self._pt_result.setPlainText)
        self._trace_worker.result.connect(self._trace_thread.quit)
        self._trace_thread.start()

    def _refresh_history(self):
        rows = _db.scan_history(limit=20)
        self._hist_table.setRowCount(0)
        for r in rows:
            row = self._hist_table.rowCount(); self._hist_table.insertRow(row)
            ts = datetime.datetime.fromtimestamp(r["timestamp"]).strftime("%d %b %H:%M")
            self._hist_table.setItem(row, 0, make_item(ts))
            self._hist_table.setItem(row, 1, make_item(r["subnet"] or "—"))
            self._hist_table.setItem(row, 2, make_item(str(r["device_count"] or "—"),
                                                        align=Qt.AlignCenter))


# ---------------------------------------------------------------- Network info tab
class InfoTab(QWidget):
    def __init__(self, info: netinfo.InterfaceInfo):
        super().__init__()
        root = QVBoxLayout(self); root.setContentsMargins(20,14,20,14); root.setSpacing(14)
        title = QLabel("Network Information"); title.setObjectName("title")
        root.addWidget(title)
        card = QFrame(); card.setObjectName("card")
        g = QGridLayout(card); g.setContentsMargins(20,16,20,16)
        g.setVerticalSpacing(12); g.setHorizontalSpacing(16)
        rows = [("Interface", info.name), ("Your IPv4", info.ipv4),
                ("MAC address", info.mac), ("Subnet mask", info.netmask),
                ("Network (CIDR)", info.cidr), ("Scannable hosts", str(info.host_count)),
                ("Gateway / Router", info.gateway), ("Broadcast", info.broadcast),
                ("DNS servers", ", ".join(info.dns) or "—")]
        for i, (k, v) in enumerate(rows):
            kl = QLabel(k); kl.setObjectName("statLabel")
            vl = QLabel(v or "—")
            vl.setStyleSheet("color:#ffffff;font-size:14px;font-weight:600;")
            vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            g.addWidget(kl, i, 0, Qt.AlignRight); g.addWidget(vl, i, 1)
        g.setColumnStretch(1, 1); root.addWidget(card); root.addStretch(1)
        hint = QLabel("BetterLanScan discovers devices with concurrent ICMP, resolves MACs "
                      "via ARP, identifies vendors (IEEE OUI), fingerprints OS from TTL + ports, "
                      "and finds services via Bonjour/mDNS. Wi-Fi uses Apple CoreWLAN.")
        hint.setObjectName("subtle"); hint.setWordWrap(True); root.addWidget(hint)


# ---------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.resize(1160, 740); self.setMinimumSize(900, 580)
        _db.init()
        self.info = netinfo.get_interface_info()
        central = QWidget(); central.setObjectName("root")
        lay = QVBoxLayout(central); lay.setContentsMargins(0,0,0,0)

        hdr = QHBoxLayout(); hdr.setContentsMargins(20,14,20,0)
        logo = QLabel("🛰  BetterLanScan"); logo.setObjectName("title")
        sub = QLabel("Network & Wi-Fi scanner"); sub.setObjectName("subtle")
        hdr.addWidget(logo); hdr.addSpacing(10); hdr.addWidget(sub); hdr.addStretch(1)
        lay.addLayout(hdr)

        self.tabs = QTabWidget()
        self.lan_tab   = LanTab(self.info, self.set_status)
        self.wifi_tab  = WifiTab(self.set_status)
        self.topo_tab  = TopologyTab(self.set_status)
        self.tools_tab = ToolsTab(self.info, self.set_status)
        self.info_tab  = InfoTab(self.info)
        self.tabs.addTab(self.lan_tab,   "  LAN Devices  ")
        self.tabs.addTab(self.wifi_tab,  "  Wi-Fi Networks  ")
        self.tabs.addTab(self.topo_tab,  "  Topology  ")
        self.tabs.addTab(self.tools_tab, "  Tools  ")
        self.tabs.addTab(self.info_tab,  "  Network Info  ")
        lay.addWidget(self.tabs)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.set_status(f"Ready · {self.info.cidr or 'no network'} · {self.info.host_count} hosts")

    def set_status(self, msg): self.statusBar().showMessage(msg)


def run():
    import sys
    _fix_macos_menu_name(__app_name__)
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationDisplayName(__app_name__)
    app.setStyleSheet(QSS)
    try:
        from . import location
        location.request_authorization()
    except Exception:
        pass
    win = MainWindow(); win.show()

    import os
    shot = os.environ.get("BLS_SHOT")
    if shot:
        tab = int(os.environ.get("BLS_TAB", "0"))
        delay = int(os.environ.get("BLS_DELAY", "1500"))
        win.tabs.setCurrentIndex(tab)
        if tab == 1: win.wifi_tab.scan()
        elif tab == 0 and os.environ.get("BLS_RUNSCAN"): win.lan_tab.start_scan()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(delay, lambda: (win.grab().save(shot), app.quit()))

    sys.exit(app.exec())
