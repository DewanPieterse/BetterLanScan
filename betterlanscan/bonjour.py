"""Bonjour / mDNS service discovery via dns-sd (macOS).

Browses common service types on the local network and maps them
to IP addresses. Runs with a timeout — no persistent daemon needed.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
from dataclasses import dataclass, field


# Common service types we care about
SERVICE_TYPES: list[tuple[str, str]] = [
    ("_ssh._tcp",          "SSH"),
    ("_sftp-ssh._tcp",     "SFTP"),
    ("_http._tcp",         "HTTP"),
    ("_https._tcp",        "HTTPS"),
    ("_ftp._tcp",          "FTP"),
    ("_smb._tcp",          "SMB"),
    ("_afp._tcp",          "AFP"),
    ("_nfs._tcp",          "NFS"),
    ("_airplay._tcp",      "AirPlay"),
    ("_raop._tcp",         "AirPlay Audio"),
    ("_companion-link._tcp","Apple Companion"),
    ("_ipp._tcp",          "Printer (IPP)"),
    ("_ipps._tcp",         "Printer (IPPS)"),
    ("_pdl-datastream._tcp","Printer (PDL)"),
    ("_scanner._tcp",      "Scanner"),
    ("_homekit._tcp",      "HomeKit"),
    ("_hap._tcp",          "HomeKit Accessory"),
    ("_spotify-connect._tcp","Spotify Connect"),
    ("_googlecast._tcp",   "Chromecast"),
    ("_plex._tcp",         "Plex"),
    ("_plexmediasvr._tcp", "Plex Media Server"),
    ("_daap._tcp",         "iTunes Sharing"),
    ("_dacp._tcp",         "iTunes Remote"),
    ("_workstation._tcp",  "Workstation"),
    ("_rdp._tcp",          "RDP"),
    ("_nvstream._tcp",     "NVIDIA Stream"),
    ("_sleep-proxy._udp",  "Sleep Proxy"),
    ("_mqtt._tcp",         "MQTT"),
]


@dataclass
class BonjourService:
    name: str
    service_type: str
    label: str          # human name e.g. "AirPlay"
    hostname: str = ""
    ip: str = ""
    port: int = 0
    txt: list[str] = field(default_factory=list)


def _resolve_name(name: str, service_type: str, timeout: float = 2.0) -> BonjourService | None:
    """Use dns-sd -L to resolve a service instance."""
    svc = BonjourService(name=name, service_type=service_type,
                         label=dict(SERVICE_TYPES).get(service_type, service_type))
    try:
        proc = subprocess.Popen(
            ["dns-sd", "-L", name, service_type, "local"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        lines: list[str] = []
        def reader():
            for line in proc.stdout:
                lines.append(line)
        t = threading.Thread(target=reader, daemon=True); t.start()
        t.join(timeout)
        proc.terminate()
        for line in lines:
            m = re.search(r"can be reached at (\S+):(\d+)", line)
            if m:
                svc.hostname = m.group(1).rstrip(".")
                svc.port = int(m.group(2))
            m2 = re.search(r"TXT\s+(.+)", line)
            if m2:
                svc.txt = [p.strip('"') for p in m2.group(1).split()]
    except Exception:
        pass
    return svc if svc.hostname else None


def _browse(service_type: str, timeout: float = 2.5) -> list[str]:
    """dns-sd -B — returns list of instance names found."""
    names: list[str] = []
    try:
        proc = subprocess.Popen(
            ["dns-sd", "-B", service_type, "local"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        lines: list[str] = []
        def reader():
            for line in proc.stdout:
                lines.append(line)
        t = threading.Thread(target=reader, daemon=True); t.start()
        t.join(timeout)
        proc.terminate()
        for line in lines:
            # "Add   3   4 local.  _http._tcp.  My Server"
            m = re.search(r"Add\s+\d+\s+\d+\s+\S+\s+\S+\s+(.+)", line)
            if m:
                n = m.group(1).strip()
                if n and n not in names:
                    names.append(n)
    except Exception:
        pass
    return names


def _hostname_to_ip(hostname: str) -> str:
    import socket
    try:
        return socket.gethostbyname(hostname)
    except Exception:
        return ""


def discover(timeout_per_type: float = 2.0,
             max_types: int | None = None) -> list[BonjourService]:
    """Browse all service types and resolve instances. Returns deduplicated list."""
    types = SERVICE_TYPES[:max_types] if max_types else SERVICE_TYPES
    all_svcs: list[BonjourService] = []

    import concurrent.futures as cf

    def browse_one(item: tuple[str, str]) -> list[BonjourService]:
        stype, label = item
        names = _browse(stype, timeout_per_type)
        svcs = []
        for name in names[:8]:   # cap per type
            s = _resolve_name(name, stype, timeout_per_type)
            if s:
                s.ip = _hostname_to_ip(s.hostname)
                svcs.append(s)
        return svcs

    with cf.ThreadPoolExecutor(max_workers=min(len(types), 12)) as ex:
        for result in ex.map(browse_one, types):
            all_svcs.extend(result)

    return all_svcs


def services_for_ip(ip: str, all_services: list[BonjourService]) -> list[BonjourService]:
    return [s for s in all_services if s.ip == ip]


def services_for_hostname(hostname: str, all_services: list[BonjourService]) -> list[BonjourService]:
    hn = hostname.lower().rstrip(".")
    return [s for s in all_services if s.hostname.lower().rstrip(".") == hn
            or s.hostname.lower().rstrip(".").startswith(hn.split(".")[0])]


if __name__ == "__main__":
    print("Browsing Bonjour services (6s)…")
    svcs = discover(timeout_per_type=1.5, max_types=10)
    print(f"Found {len(svcs)} services:")
    for s in svcs:
        print(f"  {s.label:<20} {s.name:<30} {s.hostname}:{s.port}  ip={s.ip}")
