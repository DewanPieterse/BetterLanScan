"""OS fingerprinting from TTL, open ports and service banners.

No root, no raw sockets — purely heuristic from data already gathered.
Confidence levels: "certain" / "likely" / "guess".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OSGuess:
    name: str          # e.g. "macOS", "Windows 10/11", "Linux"
    confidence: str    # "certain" / "likely" / "guess"
    icon: str          # emoji for display
    detail: str = ""   # extra clue used


_TTL_MAP = {
    (1,  32):  ("Windows 9x",     "guess", "🪟"),
    (33, 64):  ("Linux / Android","likely", "🐧"),
    (65, 128): ("Windows",        "likely", "🪟"),
    (129,255): ("Network device", "likely", "📡"),
}


def _ttl_os(ttl: int) -> tuple[str, str, str]:
    for (lo, hi), val in _TTL_MAP.items():
        if lo <= ttl <= hi:
            return val
    return "Unknown", "guess", "❓"


# ports that strongly suggest an OS
_PORT_RULES: list[tuple[set[int], str, str, str]] = [
    ({3389},             "Windows",     "likely",  "🪟"),   # RDP
    ({445, 139},         "Windows",     "likely",  "🪟"),   # SMB
    ({5985, 5986},       "Windows",     "likely",  "🪟"),   # WinRM
    ({548},              "macOS",       "likely",  "🍎"),   # AFP
    ({49152, 62078},     "iOS / iPadOS","likely",  "📱"),   # lockdownd / iTunes sync
    ({5353},             "Apple",       "guess",   "🍎"),   # mDNS heavy user
    ({1883},             "IoT",         "guess",   "🔌"),   # MQTT
    ({9100, 515, 631},   "Printer",     "certain", "🖨️"),
    ({32400},            "Plex server", "certain", "📺"),
    ({6443, 10250},      "Kubernetes",  "certain", "☸️"),
    ({5900},             "VNC target",  "likely",  "🖥️"),
    ({8883, 1883},       "IoT / MQTT",  "guess",   "🔌"),
]


def _port_os(ports: set[int]) -> tuple[str, str, str] | None:
    for rule_ports, name, conf, icon in _PORT_RULES:
        if rule_ports & ports:
            return name, conf, icon
    return None


def _banner_os(banners: list[str]) -> tuple[str, str, str] | None:
    """Parse SSH / HTTP banners for OS hints."""
    for b in banners:
        bl = b.lower()
        if "ubuntu" in bl: return "Linux (Ubuntu)", "certain", "🐧"
        if "debian" in bl: return "Linux (Debian)", "certain", "🐧"
        if "raspbian" in bl or "raspberry" in bl: return "Raspberry Pi OS", "certain", "🐧"
        if "freebsd" in bl: return "FreeBSD", "certain", "👿"
        if "openbsd" in bl: return "OpenBSD", "certain", "🐡"
        if "macos" in bl or "darwin" in bl: return "macOS", "certain", "🍎"
        if "windows" in bl: return "Windows", "certain", "🪟"
        if "cisco" in bl or "ios" in bl and "cisco" in bl: return "Cisco IOS", "certain", "📡"
        if "mikrotik" in bl: return "MikroTik", "certain", "📡"
        if "openwrt" in bl: return "OpenWRT", "certain", "📡"
        if "dd-wrt" in bl: return "DD-WRT", "certain", "📡"
        if "nginx" in bl or "apache" in bl or "lighttpd" in bl:
            return "Linux", "likely", "🐧"
        if "microsoft-iis" in bl or "iis" in bl:
            return "Windows", "likely", "🪟"
        if "synology" in bl: return "Synology NAS", "certain", "💾"
        if "qnap" in bl: return "QNAP NAS", "certain", "💾"
        if "truenas" in bl or "freenas" in bl: return "TrueNAS", "certain", "💾"
        if "esxi" in bl or "vmware" in bl: return "VMware ESXi", "certain", "🖥️"
        if "proxmox" in bl: return "Proxmox", "certain", "🖥️"
        if "pfsense" in bl: return "pfSense", "certain", "🛡️"
        if "opnsense" in bl: return "OPNsense", "certain", "🛡️"
    return None


def _vendor_os(vendor: str) -> tuple[str, str, str] | None:
    v = vendor.lower()
    if "apple" in v: return "Apple device", "guess", "🍎"
    if "raspberry" in v: return "Raspberry Pi OS", "likely", "🐧"
    if "espressif" in v: return "IoT (ESP)", "likely", "🔌"
    if "amazon" in v: return "Amazon device", "guess", "📦"
    if "google" in v: return "Android / ChromeOS", "guess", "🤖"
    if "samsung" in v: return "Android / Samsung", "guess", "🤖"
    if "cisco" in v or "ubiquiti" in v or "tp-link" in v or "aruba" in v:
        return "Network device", "likely", "📡"
    return None


def guess(ttl: int | None, open_ports: list[int], banners: list[str],
          vendor: str = "", hostname: str = "") -> OSGuess:
    ports = set(open_ports)

    # hostname hints
    hn = (hostname or "").lower()
    if "iphone" in hn or "ipad" in hn: return OSGuess("iOS / iPadOS", "certain", "📱", "hostname")
    if "macbook" in hn or "imac" in hn or "mac-mini" in hn or "apple" in hn:
        return OSGuess("macOS", "certain", "🍎", "hostname")
    if "android" in hn: return OSGuess("Android", "certain", "🤖", "hostname")
    if "router" in hn or "gateway" in hn: return OSGuess("Network device", "likely", "📡", "hostname")
    if "synology" in hn: return OSGuess("Synology NAS", "certain", "💾", "hostname")
    if "proxmox" in hn: return OSGuess("Proxmox", "certain", "🖥️", "hostname")
    if "plex" in hn: return OSGuess("Plex server", "likely", "📺", "hostname")
    if "pi" in hn and "raspberr" in (vendor or "").lower():
        return OSGuess("Raspberry Pi OS", "certain", "🐧", "hostname+vendor")

    # banner (highest confidence)
    b = _banner_os(banners)
    if b and b[1] == "certain": return OSGuess(b[0], b[1], b[2], "banner")

    # port rules (certain)
    p = _port_os(ports)
    if p and p[1] == "certain": return OSGuess(p[0], p[1], p[2], "ports")

    # banner (likely)
    if b: return OSGuess(b[0], b[1], b[2], "banner")

    # port rules (likely / guess)
    if p: return OSGuess(p[0], p[1], p[2], "ports")

    # TTL
    if ttl is not None:
        t = _ttl_os(ttl)
        # refine Linux/Windows from TTL with vendor
        if t[0] == "Linux / Android" and "apple" in (vendor or "").lower():
            return OSGuess("macOS", "likely", "🍎", f"TTL={ttl}+vendor")
        return OSGuess(t[0], t[1], t[2], f"TTL={ttl}")

    # vendor fallback
    v = _vendor_os(vendor)
    if v: return OSGuess(v[0], v[1], v[2], "vendor")

    return OSGuess("Unknown", "guess", "❓")


if __name__ == "__main__":
    cases = [
        (64,  [22, 80],  ["SSH-2.0-OpenSSH_8.9p1 Ubuntu"], "Raspberry Pi", ""),
        (128, [445,3389],[], "Unknown", "DESKTOP-ABC"),
        (64,  [548],     [], "Apple",   "macbook-pro.local"),
        (255, [80, 443], [], "Cisco",   ""),
        (64,  [62078],   [], "Apple",   "iphone"),
        (64,  [1883],    [], "Espressif","sensor-01.local"),
    ]
    for ttl, ports, banners, vendor, host in cases:
        g = guess(ttl, ports, banners, vendor, host)
        print(f"{g.icon} {g.name:<22} ({g.confidence:<7}) via {g.detail}")
