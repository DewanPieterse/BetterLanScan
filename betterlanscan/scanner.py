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

# Common ports probed for the optional service scan + device-type hinting.
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
    rtt_ms: float | None = None
    is_up: bool = False
    is_self: bool = False
    is_gateway: bool = False
    open_ports: list[int] = field(default_factory=list)
    device_type: str = ""
    last_seen: float = field(default_factory=time.time)

    @property
    def ip_sortkey(self) -> int:
        try:
            return int(ipaddress.IPv4Address(self.ip))
        except Exception:
            return 0


def _ping(ip: str, timeout_ms: int = 600) -> tuple[bool, float | None]:
    """Single ICMP probe. Returns (up, rtt_ms)."""
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


_ARP_RE = re.compile(
    r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F:]+)"
)


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
        # normalise single-digit octets (a:b:c -> 0a:0b:0c)
        parts = mac.split(":")
        if len(parts) == 6:
            table[ip] = ":".join(p.zfill(2) for p in parts)
    return table


def scan_ports(ip: str, ports: list[int] | None = None,
               timeout: float = 0.4) -> list[int]:
    ports = ports or list(COMMON_PORTS)
    open_ports: list[int] = []

    def probe(p: int) -> int | None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            try:
                if s.connect_ex((ip, p)) == 0:
                    return p
            except Exception:
                return None
        return None

    with cf.ThreadPoolExecutor(max_workers=min(len(ports), 40)) as ex:
        for r in ex.map(probe, ports):
            if r is not None:
                open_ports.append(r)
    return sorted(open_ports)


def guess_device_type(dev: Device) -> str:
    v = (dev.vendor or "").lower()
    ports = set(dev.open_ports)
    host = (dev.hostname or "").lower()
    if dev.is_gateway:
        return "Router / Gateway"
    if 9100 in ports or 515 in ports or 631 in ports:
        return "Printer"
    if 32400 in ports:
        return "Media Server"
    if 62078 in ports or "iphone" in host or "ipad" in host:
        return "iPhone / iPad"
    if any(k in v for k in ("apple",)):
        return "Apple device"
    if any(k in v for k in ("raspberry", "espressif", "texas instruments")):
        return "IoT / Embedded"
    if any(k in v for k in ("samsung", "lg", "sony", "hisense")) and 8080 in ports:
        return "Smart TV"
    if any(k in v for k in ("tp-link", "netgear", "d-link", "asus", "ubiquiti",
                            "aruba", "cisco", "avm")):
        return "Network device"
    if any(k in v for k in ("amazon", "google")):
        return "Smart speaker / Cast"
    if 445 in ports or 139 in ports or 3389 in ports:
        return "Computer (Windows)"
    if 22 in ports:
        return "Computer / Server"
    if 80 in ports or 443 in ports:
        return "Web device"
    return "Unknown"


class ScanController:
    """Drives a concurrent sweep. Callbacks fire from worker threads."""

    def __init__(self, on_device=None, on_progress=None, on_done=None):
        self.on_device = on_device or (lambda d: None)
        self.on_progress = on_progress or (lambda done, total: None)
        self.on_done = on_done or (lambda devices: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, hosts: list[str], *, self_ip: str = "", gateway_ip: str = "",
              do_ports: bool = True, max_workers: int = 128,
              ping_timeout_ms: int = 600) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(hosts, self_ip, gateway_ip, do_ports, max_workers, ping_timeout_ms),
            daemon=True,
        )
        self._thread.start()

    def _run(self, hosts, self_ip, gateway_ip, do_ports, max_workers, ping_timeout_ms):
        total = len(hosts)
        done = 0
        found: list[Device] = []
        lock = threading.Lock()

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
                dev.open_ports = scan_ports(ip)
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

        # enrich with ARP MACs + vendor + device type (ARP populated by pings)
        arp = read_arp_table()
        for dev in found:
            dev.mac = arp.get(dev.ip, dev.mac)
            if dev.mac:
                dev.vendor = oui.lookup(dev.mac)
            dev.device_type = guess_device_type(dev)
            self.on_device(dev)  # emit again with enriched data

        found.sort(key=lambda d: d.ip_sortkey)
        self.on_done(found)


if __name__ == "__main__":
    from . import netinfo
    info = netinfo.get_interface_info()
    hosts = netinfo.hosts_for_cidr(info.cidr)
    print(f"Scanning {info.cidr} ({len(hosts)} hosts)…")
    results: list[Device] = []
    ctl = ScanController(
        on_progress=lambda d, t: print(f"\r{d}/{t}", end="", flush=True),
        on_done=lambda devs: results.extend(devs),
    )
    ctl.start(hosts, self_ip=info.ipv4, gateway_ip=info.gateway, do_ports=True)
    while ctl.running:
        time.sleep(0.2)
    print("\n")
    for d in results:
        print(f"{d.ip:<16}{d.mac:<19}{d.vendor:<16}{d.device_type:<18}{d.hostname}")
