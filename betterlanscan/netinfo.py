"""Local network interface discovery (macOS).

Figures out which interface carries the default route, its IPv4 address,
netmask and the CIDR subnet to scan. Pure stdlib + `ifconfig`/`route`.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
from dataclasses import dataclass, field


@dataclass
class InterfaceInfo:
    name: str = ""
    ipv4: str = ""
    netmask: str = ""
    cidr: str = ""            # e.g. 192.168.1.0/24
    mac: str = ""
    gateway: str = ""
    broadcast: str = ""
    router_ip: str = ""
    dns: list[str] = field(default_factory=list)
    host_count: int = 0


def _run(cmd: list[str], timeout: float = 4.0) -> str:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        ).stdout
    except Exception:
        return ""


def _default_interface() -> str:
    out = _run(["route", "-n", "get", "default"])
    m = re.search(r"interface:\s*(\S+)", out)
    if m:
        return m.group(1)
    # fall back to common names
    for guess in ("en0", "en1"):
        if _run(["ipconfig", "getifaddr", guess]).strip():
            return guess
    return "en0"


def _gateway() -> str:
    out = _run(["route", "-n", "get", "default"])
    m = re.search(r"gateway:\s*(\S+)", out)
    return m.group(1) if m else ""


def _dns_servers() -> list[str]:
    out = _run(["scutil", "--dns"])
    servers: list[str] = []
    for m in re.finditer(r"nameserver\[\d+\]\s*:\s*(\S+)", out):
        ip = m.group(1)
        if ip not in servers:
            servers.append(ip)
    return servers


def _hex_netmask_to_dotted(value: str) -> str:
    """ifconfig reports netmask as hex like 0xffffff00."""
    try:
        n = int(value, 16)
        return socket.inet_ntoa(n.to_bytes(4, "big"))
    except Exception:
        return value


def get_interface_info(name: str | None = None) -> InterfaceInfo:
    iface = name or _default_interface()
    info = InterfaceInfo(name=iface)
    info.ipv4 = _run(["ipconfig", "getifaddr", iface]).strip()

    cfg = _run(["ifconfig", iface])
    if not info.ipv4:
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", cfg)
        if m:
            info.ipv4 = m.group(1)

    m = re.search(r"netmask (0x[0-9a-fA-F]+|\d+\.\d+\.\d+\.\d+)", cfg)
    if m:
        info.netmask = (
            _hex_netmask_to_dotted(m.group(1))
            if m.group(1).startswith("0x")
            else m.group(1)
        )
    m = re.search(r"broadcast (\d+\.\d+\.\d+\.\d+)", cfg)
    if m:
        info.broadcast = m.group(1)
    m = re.search(r"ether ([0-9a-fA-F:]{17})", cfg)
    if m:
        info.mac = m.group(1).lower()

    info.gateway = _gateway()
    info.router_ip = info.gateway
    info.dns = _dns_servers()

    if info.ipv4 and info.netmask:
        try:
            net = ipaddress.IPv4Network(
                f"{info.ipv4}/{info.netmask}", strict=False
            )
            info.cidr = str(net)
            info.host_count = net.num_addresses - 2 if net.num_addresses > 2 else net.num_addresses
        except Exception:
            pass
    elif info.ipv4:
        net = ipaddress.IPv4Network(f"{info.ipv4}/24", strict=False)
        info.cidr = str(net)
        info.host_count = net.num_addresses - 2

    return info


def hosts_for_cidr(cidr: str) -> list[str]:
    """Return list of host IPs to probe for a CIDR string."""
    net = ipaddress.IPv4Network(cidr, strict=False)
    if net.num_addresses <= 2:
        return [str(net.network_address)]
    return [str(h) for h in net.hosts()]


if __name__ == "__main__":
    import json
    info = get_interface_info()
    print(json.dumps(info.__dict__, indent=2))
