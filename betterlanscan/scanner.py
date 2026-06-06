"""LAN device discovery: concurrent ping sweep + ARP + reverse DNS + ports."""
from __future__ import annotations

import concurrent.futures as cf
import ipaddress
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field

from . import oui

COMMON_PORTS: dict[int, str] = {
    21: "FTP", 22: "SSH", 23: "Telnet", 53: "DNS", 80: "HTTP",
    139: "SMB", 443: "HTTPS", 445: "SMB", 515: "Printer", 548: "AFP",
    631: "IPP", 1883: "MQTT", 3000: "HTTP-alt", 3389: "RDP", 5000: "UPnP",
    5060: "SIP", 5353: "mDNS", 62078: "iPhone-sync", 8080: "HTTP-alt",
    8443: "HTTPS-alt", 9100: "Printer", 32400: "Plex",
}


@dataclass
class Device:
    ip: str
    mac: str = ""
    vendor: str = ""
    hostname: str = ""
    custom_name: str = ""       # user-assigned label (from DB)
    rtt_ms: float | None = None
    is_up: bool = False
    is_self: bool = False
    is_gateway: bool = False
    open_ports: list[int] = field(default_factory=list)
    device_type: str = ""
    os_guess: str = ""          # e.g. "macOS", "Windows"
    os_icon: str = ""           # emoji
    os_confidence: str = ""     # "certain" / "likely" / "guess"
    is_favourite: bool = False
    is_new: bool = False        # True if not seen in DB before
    arp_conflict: bool = False  # same MAC seen on different IP
    notes: str = ""
    first_seen: float = 0.0
    times_seen: int = 1
    last_seen: float = field(default_factory=time.time)
    bonjour_services: list[str] = field(default_factory=list)
    ipv6: list[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.custom_name or self.hostname or self.ip

    @property
    def ip_sortkey(self) -> int:
        try:
            return int(ipaddress.IPv4Address(self.ip))
        except Exception:
            return 0


def _ping(ip: str, timeout_ms: int = 600) -> tuple[bool, float | None]:
    try:
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout_ms), "-n", ip],
            capture_output=True, text=True, timeout=(timeout_ms / 1000) + 1.5,
        )
    except Exception:
        return False, None
    if proc.returncode != 0:
        return False, None
    m = re.search(r"time[=<]([\d.]+)", proc.stdout)
    return True, (float(m.group(1)) if m else None)


def _reverse_dns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


_ARP_RE = re.compile(r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F:]+)")


def read_arp_table() -> dict[str, str]:
    """Map IP -> MAC from the system ARP cache."""
    table: dict[str, str] = {}
    try:
        out = subprocess.run(
            ["arp", "-a", "-n"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return table
    for line in out.splitlines():
        m = _ARP_RE.search(line)
        if not m:
            continue
        ip, mac = m.group(1), m.group(2).lower()
        if mac in ("(incomplete)", "ff:ff:ff:ff:ff:ff"):
            continue
        parts = mac.split(":")
        if len(parts) == 6:
            table[ip] = ":".join(p.zfill(2) for p in parts)
    return table


def detect_arp_conflicts(devices: list[Device]) -> set[str]:
    """Return set of MACs that appear on more than one IP."""
    mac_to_ips: dict[str, list[str]] = {}
    for d in devices:
        if d.mac:
            mac_to_ips.setdefault(d.mac, []).append(d.ip)
    return {mac for mac, ips in mac_to_ips.items() if len(ips) > 1}


def scan_ports(ip: str, ports: list[int] | None = None,
               timeout: float = 0.4) -> list[int]:
    ports = ports or list(COMMON_PORTS)

    def probe(p: int) -> int | None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return p if s.connect_ex((ip, p)) == 0 else None

    with cf.ThreadPoolExecutor(max_workers=min(len(ports), 40)) as ex:
        return sorted(r for r in ex.map(probe, ports) if r is not None)


def guess_device_type(dev: Device) -> str:
    v = (dev.vendor or "").lower()
    ports = set(dev.open_ports)
    host = (dev.hostname or "").lower()
    if dev.is_gateway:
        return "Router / Gateway"
    if 9100 in ports or 515 in ports or 631 in ports:
        return "Printer"
    if 32400 in ports:
        return "Media Server (Plex)"
    if 62078 in ports or "iphone" in host or "ipad" in host:
        return "iPhone / iPad"
    if any(k in v for k in ("apple",)):
        return "Apple device"
    if any(k in v for k in ("raspberry", "espressif", "texas instruments")):
        return "IoT / Embedded"
    if any(k in v for k in ("samsung", "lg", "sony", "hisense")) and (8080 in ports or 55001 in ports):
        return "Smart TV"
    if any(k in v for k in ("tp-link", "netgear", "d-link", "asus", "ubiquiti",
                            "aruba", "cisco", "avm", "mikrotik")):
        return "Network device"
    if any(k in v for k in ("amazon",)):
        return "Amazon Echo / Fire"
    if any(k in v for k in ("google",)):
        return "Google / Chromecast"
    if 445 in ports or 139 in ports or 3389 in ports:
        return "Computer (Windows)"
    if 22 in ports:
        return "Computer / Server"
    if 80 in ports or 443 in ports:
        return "Web device"
    return "Unknown"


class ScanController:
    """Concurrent sweep with DB integration, OS guessing, ARP conflict detection."""

    def __init__(self, on_device=None, on_progress=None, on_done=None,
                 on_new_device=None):
        self.on_device = on_device or (lambda d: None)
        self.on_progress = on_progress or (lambda done, total: None)
        self.on_done = on_done or (lambda devices: None)
        self.on_new_device = on_new_device or (lambda d: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, hosts: list[str], *, self_ip: str = "", gateway_ip: str = "",
              do_ports: bool = True, max_workers: int = 128,
              ping_timeout_ms: int = 600,
              extra_ports: list[int] | None = None) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(hosts, self_ip, gateway_ip, do_ports, max_workers,
                  ping_timeout_ms, extra_ports),
            daemon=True,
        )
        self._thread.start()

    def _run(self, hosts, self_ip, gateway_ip, do_ports, max_workers,
             ping_timeout_ms, extra_ports):
        from . import db, os_detect, notify
        db.init()
        known = db.known_macs()
        total = len(hosts)
        done = 0
        found: list[Device] = []
        lock = threading.Lock()

        ports_to_scan = list(COMMON_PORTS)
        if extra_ports:
            ports_to_scan = sorted(set(ports_to_scan) | set(extra_ports))

        def work(ip: str) -> Device | None:
            if self._stop.is_set():
                return None
            up, rtt = _ping(ip, ping_timeout_ms)
            is_self = ip == self_ip
            if not up and not is_self:
                return None
            dev = Device(ip=ip, is_up=True, rtt_ms=rtt, is_self=is_self,
                         is_gateway=(ip == gateway_ip))
            dev.hostname = _reverse_dns(ip)
            if do_ports and not self._stop.is_set():
                dev.open_ports = scan_ports(ip, ports_to_scan)
            return dev

        with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(work, ip): ip for ip in hosts}
            for fut in cf.as_completed(futures):
                done += 1
                self.on_progress(done, total)
                if self._stop.is_set():
                    continue
                dev = fut.result()
                if dev is not None:
                    with lock:
                        found.append(dev)
                    self.on_device(dev)

        # Enrich: ARP → MAC → vendor → OS → device type → DB
        arp = read_arp_table()
        for dev in found:
            dev.mac = arp.get(dev.ip, dev.mac)
            if dev.mac:
                dev.vendor = oui.lookup(dev.mac)
                # Load persisted info
                row = db.get_device(dev.mac)
                if row:
                    dev.custom_name = row["custom_name"] or ""
                    dev.notes       = row["notes"] or ""
                    dev.is_favourite= bool(row["is_favourite"])
                    dev.first_seen  = row["first_seen"] or 0
                    dev.times_seen  = (row["times_seen"] or 1) + 1
                    dev.is_new      = False
                else:
                    dev.is_new = True

            dev.device_type = guess_device_type(dev)

            # OS guess
            og = os_detect.guess(None, dev.open_ports, [], dev.vendor, dev.hostname)
            dev.os_guess = og.name
            dev.os_icon  = og.icon
            dev.os_confidence = og.confidence

            # Persist
            if dev.mac:
                db.upsert_device(dev.mac, dev.ip, dev.hostname,
                                 dev.vendor, dev.device_type, dev.os_guess)
                db.log_ping(dev.ip, dev.rtt_ms)
                if dev.is_new:
                    self.on_new_device(dev)
                    try:
                        notify.new_device(dev.ip, dev.mac, dev.vendor, dev.hostname)
                    except Exception:
                        pass

            self.on_device(dev)

        # ARP conflict detection
        conflict_macs = detect_arp_conflicts(found)
        for dev in found:
            if dev.mac in conflict_macs:
                dev.arp_conflict = True
                self.on_device(dev)
                try:
                    from . import notify as _n
                    others = [d.ip for d in found if d.mac == dev.mac and d.ip != dev.ip]
                    _n.arp_conflict(dev.ip, dev.mac, others[0] if others else "?")
                except Exception:
                    pass

        from . import db as _db
        _db.log_scan(f"{len(hosts)} hosts", len(found))

        found.sort(key=lambda d: d.ip_sortkey)
        self.on_done(found)
