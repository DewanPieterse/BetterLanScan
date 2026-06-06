"""Deep per-device probe run on-demand when a row is selected."""
from __future__ import annotations

import concurrent.futures as cf
import re
import socket
import subprocess
import time
from dataclasses import dataclass, field

from . import scanner


# Extended port list — everything in the fast scan plus extra services.
FULL_PORTS: dict[int, str] = {
    **scanner.COMMON_PORTS,
    20: "FTP-data", 25: "SMTP", 110: "POP3", 143: "IMAP",
    161: "SNMP", 179: "BGP", 389: "LDAP", 587: "SMTP-TLS",
    993: "IMAPS", 995: "POP3S", 1194: "OpenVPN", 1433: "MSSQL",
    1883: "MQTT", 2049: "NFS", 2181: "Zookeeper", 3306: "MySQL",
    3478: "STUN", 4000: "HTTP-alt", 4443: "HTTPS-alt",
    5432: "PostgreSQL", 5900: "VNC", 6379: "Redis", 6881: "BitTorrent",
    7000: "Cassandra", 8000: "HTTP-alt", 8008: "HTTP-alt",
    8081: "HTTP-alt", 8888: "HTTP-alt", 9000: "HTTP-alt",
    9090: "Prometheus", 9200: "Elasticsearch", 27017: "MongoDB",
    51820: "WireGuard",
}


@dataclass
class Banner:
    port: int
    service: str
    raw: str = ""     # first line of response
    server: str = ""  # parsed server header / version string


@dataclass
class DeepInfo:
    ip: str
    ping_rtt: float | None = None
    ttl: int | None = None
    hops: int | None = None          # estimated from TTL
    all_ports: list[int] = field(default_factory=list)
    banners: list[Banner] = field(default_factory=list)
    mdns_names: list[str] = field(default_factory=list)
    nbns_name: str = ""              # NetBIOS name
    http_title: str = ""
    error: str = ""


def _ping_detail(ip: str) -> tuple[float | None, int | None]:
    """Returns (rtt_ms, ttl) from a single verbose ping."""
    try:
        out = subprocess.run(
            ["ping", "-c", "1", "-W", "1000", ip],
            capture_output=True, text=True, timeout=3,
        ).stdout
        rtt = None; ttl = None
        m = re.search(r"time[=<]([\d.]+)", out)
        if m: rtt = float(m.group(1))
        m = re.search(r"ttl=(\d+)", out, re.I)
        if m: ttl = int(m.group(1))
        return rtt, ttl
    except Exception:
        return None, None


def _estimate_hops(ttl: int | None) -> int | None:
    if ttl is None:
        return None
    for start in (64, 128, 255):
        if ttl <= start:
            return start - ttl
    return None


def _grab_banner(ip: str, port: int, timeout: float = 1.2) -> str:
    """Open a TCP connection, optionally send a probe, return first ~256 bytes."""
    probes = {
        80: b"HEAD / HTTP/1.0\r\nHost: " + ip.encode() + b"\r\n\r\n",
        8080: b"HEAD / HTTP/1.0\r\nHost: " + ip.encode() + b"\r\n\r\n",
        8000: b"HEAD / HTTP/1.0\r\nHost: " + ip.encode() + b"\r\n\r\n",
        443: None,  # skip TLS raw — just note it's open
        8443: None,
    }
    try:
        with socket.create_connection((ip, port), timeout=timeout) as s:
            probe = probes.get(port, b"")
            if probe:
                s.sendall(probe)
            s.settimeout(timeout)
            try:
                data = s.recv(512)
                return data.decode("utf-8", errors="replace").split("\n")[0].strip()[:200]
            except Exception:
                return ""
    except Exception:
        return ""


def _parse_banner(port: int, raw: str) -> tuple[str, str]:
    """Return (display_raw, server_string)."""
    service = FULL_PORTS.get(port, f"port/{port}")
    server = ""
    if raw.startswith("SSH-"):
        parts = raw.split("-", 2)
        server = parts[2].strip() if len(parts) > 2 else raw
    elif "Server:" in raw or "server:" in raw:
        m = re.search(r"[Ss]erver:\s*(.+)", raw)
        if m: server = m.group(1).strip()
    elif raw.startswith("HTTP/"):
        server = raw[:60]
    elif raw:
        server = raw[:60]
    return raw[:120], server


def _http_title(ip: str, port: int = 80, timeout: float = 2.0) -> str:
    try:
        probe = f"GET / HTTP/1.0\r\nHost: {ip}\r\n\r\n".encode()
        with socket.create_connection((ip, port), timeout=timeout) as s:
            s.sendall(probe)
            s.settimeout(timeout)
            data = b""
            while len(data) < 4096:
                chunk = s.recv(1024)
                if not chunk: break
                data += chunk
        text = data.decode("utf-8", errors="replace")
        m = re.search(r"<title[^>]*>([^<]{1,120})</title>", text, re.I)
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


def _mdns_names(ip: str) -> list[str]:
    """Query mDNS .local hostname for this IP via dns-sd / avahi."""
    names: list[str] = []
    try:
        # Reverse mDNS lookup via dns-sd -Q (macOS)
        out = subprocess.run(
            ["dns-sd", "-Q", _reverse_arpa(ip), "PTR"],
            capture_output=True, text=True, timeout=2,
        ).stdout
        for line in out.splitlines():
            m = re.search(r"([\w\-]+\.local\.?)", line)
            if m:
                n = m.group(1).rstrip(".")
                if n not in names:
                    names.append(n)
    except Exception:
        pass
    return names


def _nbns_name(ip: str) -> str:
    """NetBIOS node status — reveals Windows machine name."""
    try:
        pkt = (
            b"\x82\x28\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00"
            b"\x20CKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\x00"
            b"\x00\x21\x00\x01"
        )
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1.0)
            s.sendto(pkt, (ip, 137))
            data, _ = s.recvfrom(1024)
        if len(data) < 57:
            return ""
        num = data[56]
        names: list[str] = []
        for i in range(num):
            off = 57 + i * 18
            if off + 15 > len(data):
                break
            name = data[off:off + 15].decode("ascii", errors="ignore").strip()
            flags = int.from_bytes(data[off + 16:off + 18], "big")
            if name and not (flags & 0x8000):
                names.append(name)
        return names[0] if names else ""
    except Exception:
        return ""


def _reverse_arpa(ip: str) -> str:
    parts = ip.split(".")
    return ".".join(reversed(parts)) + ".in-addr.arpa"


def probe(dev: scanner.Device, progress_cb=None) -> DeepInfo:
    """Full deep probe of a device. Runs synchronously (call from a thread)."""
    info = DeepInfo(ip=dev.ip)

    def step(msg):
        if progress_cb:
            progress_cb(msg)

    step("Pinging…")
    info.ping_rtt, info.ttl = _ping_detail(dev.ip)
    info.hops = _estimate_hops(info.ttl)

    step("Scanning all ports…")
    def _probe_port(p: int) -> int | None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return p if s.connect_ex((dev.ip, p)) == 0 else None
    with cf.ThreadPoolExecutor(max_workers=60) as ex:
        for r in ex.map(_probe_port, list(FULL_PORTS)):
            if r is not None:
                info.all_ports.append(r)
    info.all_ports = sorted(info.all_ports)

    step("Grabbing banners…")
    banner_ports = [p for p in info.all_ports if p in (22, 80, 21, 25, 8080, 8000, 8888)]
    for p in banner_ports[:6]:
        raw = _grab_banner(dev.ip, p)
        display, server = _parse_banner(p, raw)
        info.banners.append(Banner(port=p, service=FULL_PORTS.get(p, ""), raw=display, server=server))

    step("Fetching HTTP title…")
    for p in [p for p in (80, 8080, 8000, 3000, 8888) if p in info.all_ports]:
        t = _http_title(dev.ip, p)
        if t:
            info.http_title = t
            break

    step("mDNS lookup…")
    info.mdns_names = _mdns_names(dev.ip)

    step("NetBIOS name…")
    info.nbns_name = _nbns_name(dev.ip)

    step("Done")
    return info
