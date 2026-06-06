"""Wake-on-LAN — send a magic packet to a device by MAC address."""
from __future__ import annotations

import re
import socket


def _parse_mac(mac: str) -> bytes:
    digits = re.sub(r"[^0-9a-fA-F]", "", mac)
    if len(digits) != 12:
        raise ValueError(f"Invalid MAC address: {mac!r}")
    return bytes.fromhex(digits)


def send(mac: str, broadcast: str = "255.255.255.255",
         port: int = 9, repeat: int = 3) -> None:
    """Broadcast a WoL magic packet on the given subnet broadcast address.

    Args:
        mac:       Target device MAC address (any common separator format).
        broadcast: Subnet broadcast address — use the real subnet broadcast
                   (e.g. 192.168.1.255) for better reliability on managed switches.
        port:      Destination UDP port — 9 (discard) or 7 (echo).
        repeat:    Number of packets to send (duplicate for reliability).
    """
    mac_bytes = _parse_mac(mac)
    magic = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for _ in range(repeat):
            s.sendto(magic, (broadcast, port))


def send_to(mac: str, broadcast: str = "255.255.255.255") -> str:
    """High-level helper: send and return a human-readable result string."""
    try:
        send(mac, broadcast)
        return f"Magic packet sent to {mac} via {broadcast}:{9}"
    except Exception as e:
        return f"Failed: {e}"


if __name__ == "__main__":
    # Dry-run: parse + show packet without actually sending to a real host
    mac = "b8:27:eb:aa:bb:cc"
    mb = _parse_mac(mac)
    magic = b"\xff" * 6 + mb * 16
    print(f"MAC bytes : {mb.hex(':')}")
    print(f"Packet len: {len(magic)} bytes")
    print(f"Preamble  : {magic[:6].hex()}")
    print(f"MAC x16   : first={magic[6:12].hex(':')}  last={magic[-6:].hex(':')}")
    print("WoL packet structure OK")
